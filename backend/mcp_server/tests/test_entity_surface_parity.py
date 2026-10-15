"""Fails CI the next time an entity is REST-exposed but MCP-unreachable (#1080).

The gap this guards is the one a QA run found in beta.16: TestRun had a live
REST collection (``GET /api/v1/test-runs/`` answered 200 with two rows) and no
MCP tool that could reach it, so every agent saw a workspace with no test runs
at all. Nothing in the suite noticed, because each side was tested on its own
terms -- ``rest_api`` tests the REST ViewSet, ``mcp_server`` tests the tool
groups -- and the *cross-transport* question was never asked.

This module asks it, in the ratchet style of
``attribute_definitions/tests/test_transport_contract_matrix.py``:

* the table in :mod:`mcp_server.tests.entity_surface_matrix` names, per entity,
  the REST collection and the MCP read tools;
* the live registry answers "does that tool exist" (via ``build_manifest()``,
  the same source ``tools/list`` is built from, so no DB, no API key, and no
  staleness window);
* the live URLconf answers "is that collection still routed";
* a *known* gap may be ratcheted in ``entity_surface_baseline.json`` with a
  concrete issue reference, and the suite additionally fails when a baselined
  gap no longer reproduces -- so a closed gap must be deleted from the baseline
  instead of silently rotting there.

The runtime half (``TestRunParity``) closes the loop on the concrete entity:
it drives the real ``ToolRegistry`` and the real HTTP endpoint and asserts that
a run created through one transport is *discoverable* through the other, and
that workspace scoping holds.

``ENTITY_SURFACE_REBASELINE=<path>`` writes a candidate baseline before the
assertions run, which is how a baseline is (re)produced. That is the one
command the shared ratchet framework registers for this suite (#1103 /
REQ-193); a plain run resolves no target and writes nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set
from uuid import uuid4

import pytest
from django.urls import Resolver404, resolve

from mcp_server.management.commands.export_tool_manifest import build_manifest
from mcp_server.tests.entity_surface_matrix import (
    ENTITY_SPECS,
    MCP_ONLY_BY_DESIGN,
    REST_ONLY_BY_DESIGN,
)
from mcp_server.tests.ratchet_framework import (
    BaselineDiff,
    assert_no_stale_entries,
    assert_no_undocumented_gaps,
    entry_point,
    gap_keys,
    maybe_rebaseline,
    split_baseline,
)

BASELINE_PATH = Path(__file__).with_name("entity_surface_baseline.json")

#: This ratchet's row in the shared re-baseline table (#1103 / REQ-193). Every
#: guard below goes through it, so the failure messages name the same command
#: the framework documents.
RATCHET = entry_point("entity-surface-parity")

#: Importing ``build_manifest`` pulls the tool groups, which import the model
#: layer; ``django.setup`` alone is enough for that, but the URLconf resolution
#: below needs the registry, so keep the django_db marker for consistency with
#: the other manifest guards.
pytestmark = pytest.mark.django_db


def _live_tools() -> Dict[str, Dict[str, Any]]:
    """Every tool the live registry advertises, indexed by name.

    ``build_manifest`` is the same walk ``ToolRegistry.list_tools`` performs
    (registry -> per-group ``get_tool_schemas()``), minus the RBAC/scope
    filter. For a caller with write + governance capability -- the figure the
    QA run measured -- the two sets are identical, so this answers the same
    question without needing a tenant, a key, or a request.
    """
    return {tool["name"]: tool for tool in build_manifest()["tools"]}


def _route_exists(collection: str) -> bool:
    """True when *collection* resolves in the live URLconf.

    ``{workspace_id}`` placeholders are substituted with a real UUID so the
    nested routes resolve too. A ``Resolver404`` (or any resolution error)
    means the entity's REST surface is gone, which is exactly as much a
    contract change as a missing MCP tool.
    """
    path = "/api/v1/" + collection.format(workspace_id=uuid4())
    try:
        resolve(path)
    except Resolver404:
        return False
    return True


def _baseline_document() -> Dict[str, Any]:
    """The committed baseline document, or a fresh one when it is absent.

    Handed to the framework as ``document=`` so a re-baseline preserves
    ``_comment`` (the recipe a human reads) and ``measured_at`` — dropping them
    is how a candidate file stops being a drop-in for the committed one.
    """
    if BASELINE_PATH.is_file():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {
        "_comment": [
            "Known REST/MCP entity-surface gaps for "
            "backend/mcp_server/tests/test_entity_surface_parity.py.",
            f"Regenerate with: {RATCHET.command}",
        ],
        "violations": [],
    }


def _candidate_baseline(measured: Iterable[str]) -> Optional[BaselineDiff]:
    """Write the named re-baseline candidate — and only when it is named.

    A re-baseline is a command a human types, never a side effect of a run:
    without ``$ENTITY_SURFACE_REBASELINE`` (or its documented
    ``$ENTITY_SURFACE_DUMP`` alias) this resolves no target and writes no file.
    When it is set, the framework refuses a widening that carries no reason and
    issue, so a genuine regression cannot be re-baselined away (#1103).
    """
    document = _baseline_document()
    return maybe_rebaseline(
        RATCHET,
        measured=measured,
        previous=document,
        document=document,
        default_path=None,
    )


# ---------------------------------------------------------------------------
# Surface contract
# ---------------------------------------------------------------------------


def test_every_rest_exposed_entity_is_readable_over_mcp() -> None:
    """Each spec's MCP read tools must exist and its REST route must resolve.

    Both halves are load-bearing. A missing tool is #1080 recurring; a missing
    route means the table is describing an entity the product no longer
    exposes, and the table must be updated rather than left to rot.
    """
    live = _live_tools()
    problems: list[str] = []

    for key, spec in sorted(ENTITY_SPECS.items()):
        if not _route_exists(spec.rest_collection):
            problems.append(
                f"{key}: REST collection {spec.rest_collection!r} is not routed "
                "any more — update entity_surface_matrix.py"
            )
        for tool in spec.mcp_reads:
            if tool not in live:
                problems.append(
                    f"{key}: {spec.entity} is REST-exposed at "
                    f"{spec.rest_collection!r} but MCP has no {tool!r} tool "
                    "(issue #1080 class: entity unreachable over MCP)"
                )
            elif live[tool]["is_write"]:
                problems.append(
                    f"{key}: {tool!r} is listed as a read tool for "
                    f"{spec.entity} but is classified write — an entity with "
                    "no read path is exactly the #1080 gap"
                )

    if problems:
        _candidate_baseline(problems)
    assert not problems, (
        "REST/MCP entity surface is asymmetric:\n  "
        + "\n  ".join(problems)
        + "\nEither add the MCP read tool, or record the entity in "
        "REST_ONLY_BY_DESIGN with a reason (and an issue if it is still open)."
    )


#: The tool names that list a collection rather than fetching one object.
#: Derived from the live catalogue at import time? No — deliberately a literal
#: list: the point of the check below is that this hand-maintained list and the
#: registry stay in step, and a check that derives its own expectation from the
#: thing it is checking proves nothing. ``test_every_entity_has_a_list_tool``
#: fails loudly when a group renames or adds a collection tool.
_COLLECTION_TOOLS = frozenset(
    {
        "requirement.query",
        "needs.query",
        "architecture.query",
        "test.query",
        "test.run_list",
        "adr.query",
        "risk.query",
        "issue.query",
        "glossary.query",
        "goal.query",
        # #1097: workspace-wide MainGoal enumeration -- the collection tool
        # that closes the main_goal gap this list's ratchet recorded.
        "main_goal.query",
        "change_request.query",
        "icd.query",
        "diagram.query",
        "comment.list",
        "baseline.list",
        "link_type.list",
        "interview.list",
        "workspace.list",
        "artifact.search",
        # #1098: workspace-wide TraceLink enumeration — the collection tool
        # that closes the trace_link gap this list's ratchet guards.
        "traceability.query_links",
    }
)


def test_every_entity_has_a_list_tool_not_just_a_fetch() -> None:
    """A fetch-by-id without a list is the #1080 shape.

    ``test.run_get`` existed and worked; the entity was still unreachable,
    because an agent could only find a TestRun whose id it already held. Every
    entity in the matrix must therefore be reachable through at least one
    collection tool — otherwise the entity is addressable but not
    discoverable, which is the same defect from the agent's side.

    An entity that predates this ratchet and is exempt carries its
    reason in ``collection_gap``; any such exemption has to be justified or
    this assertion fails. No entity uses the escape hatch any more — #1097
    closed the last one by adding ``main_goal.query``.
    """
    for key, spec in sorted(ENTITY_SPECS.items()):
        if not spec.needs_collection_tool:
            assert spec.collection_gap.strip(), (
                f"{key} is exempt from the collection-tool requirement but "
                "documents no reason. Name the gap, or implement the tool."
            )
            continue
        assert set(spec.mcp_reads) & _COLLECTION_TOOLS, (
            f"{key}: none of {spec.mcp_reads} lists the entity. Without a "
            "collection tool the entity is only reachable by an id the caller "
            "already holds — the #1080 failure mode."
        )


def test_the_collection_tool_list_is_itself_current() -> None:
    """A stale :data:`_COLLECTION_TOOLS` would make the check above vacuous."""
    live = _live_tools()
    unknown = sorted(_COLLECTION_TOOLS - set(live))
    assert not unknown, (
        f"_COLLECTION_TOOLS names non-existent tools: {unknown}. Keeping a "
        "renamed or removed collection tool in this list would silently stop "
        "test_every_entity_has_a_list_tool from checking anything."
    )


def test_rest_only_entities_document_why() -> None:
    """The REST-only list is a list of decisions, not of omissions."""
    for exclusion in REST_ONLY_BY_DESIGN:
        assert exclusion.reason.strip(), f"{exclusion.surface} has no reason"
        assert _route_exists(exclusion.surface), (
            f"{exclusion.surface} is in REST_ONLY_BY_DESIGN but is not routed "
            "— remove the stale entry"
        )


def test_mcp_only_entities_exist_in_the_live_registry() -> None:
    """The MCP-only list may not name a tool that has been removed or renamed."""
    live = _live_tools()
    stale = sorted(e.surface for e in MCP_ONLY_BY_DESIGN if e.surface not in live)
    assert not stale, (
        f"MCP_ONLY_BY_DESIGN names non-existent tools: {stale}. Update "
        "mcp_server/tests/entity_surface_matrix.py."
    )


def test_ratchet_is_a_subset_and_strictly_shrinking() -> None:
    """Baseline ratchet: known gaps only, and no stale ones.

    Mirrors ``test_transport_contract_matrix``: a *new* violation whose key is
    absent from the baseline fails (so a newly added entity has to pass), and
    the strict-shrink assertion fails when a baselined violation no longer
    reproduces (so a closed gap is deleted rather than left behind). Both
    halves are :func:`split_baseline` plus the framework's assertions, so the
    messages name the entry and the re-baseline command.
    """
    if not BASELINE_PATH.is_file():
        pytest.fail(
            f"{BASELINE_PATH.name} is missing. It lists the *known* REST/MCP "
            "surface gaps; without it this ratchet cannot distinguish a new "
            "gap from an accepted one. Create it as "
            '{"violations": [], "generated_from": "..."} — an empty list is '
            "the correct content when every entity is reachable."
        )
    # Accepted gaps are validated on LOAD, so a baseline entry without a reason
    # or an issue fails here rather than quietly widening the gate.
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baselined: Set[str] = gap_keys(
        baseline.get("violations", []), source=BASELINE_PATH.name
    )
    live_tools = _live_tools()

    actual: Set[str] = set()
    for key, spec in sorted(ENTITY_SPECS.items()):
        if not _route_exists(spec.rest_collection):
            actual.add(
                f"{key}: REST collection {spec.rest_collection!r} is not routed "
                "any more — update entity_surface_matrix.py"
            )
        for tool in spec.mcp_reads:
            if tool not in live_tools:
                actual.add(
                    f"{key}: {spec.entity} is REST-exposed at "
                    f"{spec.rest_collection!r} but MCP has no {tool!r} tool "
                    "(issue #1080 class: entity unreachable over MCP)"
                )
            elif live_tools[tool]["is_write"]:
                actual.add(
                    f"{key}: {tool!r} is listed as a read tool for "
                    f"{spec.entity} but is classified write — an entity with "
                    "no read path is exactly the #1080 gap"
                )

    diff = split_baseline(actual, baselined)
    # A re-baseline is gated behind the named env var, so this writes nothing
    # on a normal run. The old private dump wrote the *delta*; the framework
    # writes the whole measured set (stale entries dropped, new ones carrying
    # the justification that accepted them), which is what makes the candidate
    # a drop-in replacement for the committed file.
    _candidate_baseline(actual)
    assert_no_undocumented_gaps(diff, RATCHET)
    assert_no_stale_entries(diff, RATCHET)


# ---------------------------------------------------------------------------
# Runtime parity — the concrete #1080 regression
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRunParity:
    """A TestRun must be discoverable over MCP, not just addressable.

    The static matrix above already fails CI if ``test.run_list`` disappears.
    These cases pin the behaviour that made the tool worth adding: the run is
    findable *without* an id, through the real dispatcher with the real
    workspace gate, and it is the same object the REST surface serves.
    """

    def test_a_run_created_over_mcp_is_listable_without_its_id(
        self,
        admin_client,
        e2e_workspace,
        e2e_userrole_admin,
        e2e_api_key_admin: str,
    ) -> None:
        """#1080: ``test.run_list`` must find a run the caller never saw create."""
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        name = f"parity-run-{uuid4().hex[:8]}"
        created = registry.dispatch_request(
            tool_name="test.run_create",
            params={"workspace_id": str(e2e_workspace.id), "name": name},
            api_key=e2e_api_key_admin,
        )
        assert created.success, created.message
        run_id = created.data["test_run"]["id"]

        listed = registry.dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id)},
            api_key=e2e_api_key_admin,
        )
        assert listed.success, listed.message
        names = [run["name"] for run in listed.data["test_runs"]]
        assert name in names, (
            "test.run_list did not return the run that was just created over "
            f"MCP; got {names!r}"
        )
        row = next(r for r in listed.data["test_runs"] if r["name"] == name)
        # A list row must be the same object test.run_get returns, otherwise an
        # agent cannot pick a run out of the list and act on it.
        fetched = registry.dispatch_request(
            tool_name="test.run_get",
            params={"run_id": run_id},
            api_key=e2e_api_key_admin,
        )
        assert fetched.success, fetched.message
        for key in ("id", "workspace_id", "name", "status", "ci_job_id"):
            assert row[key] == fetched.data["test_run"][key], (
                f"list row and get body disagree on {key!r}: "
                f"{row[key]!r} vs {fetched.data['test_run'][key]!r}"
            )
        # The lifecycle's observable evidence travels with the row.
        assert row["result_summary"] == {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "not_run": 0,
        }
        assert row["status"] == "in_progress"
        assert row["finished_at"] is None

    def test_run_list_is_filtered_by_status_and_bounded_by_limit(
        self, admin_client, e2e_workspace, e2e_userrole_admin, e2e_api_key_admin: str
    ) -> None:
        """``status`` and ``limit`` are filters, not hints."""
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        for index in range(3):
            created = registry.dispatch_request(
                tool_name="test.run_create",
                params={
                    "workspace_id": str(e2e_workspace.id),
                    "name": f"parity-filter-{index}",
                },
                api_key=e2e_api_key_admin,
            )
            assert created.success, created.message

        in_progress = registry.dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id), "status": "in_progress"},
            api_key=e2e_api_key_admin,
        )
        assert in_progress.success, in_progress.message
        assert {r["status"] for r in in_progress.data["test_runs"]} == {"in_progress"}

        closed = registry.dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id), "status": "closed"},
            api_key=e2e_api_key_admin,
        )
        assert closed.success, closed.message
        assert closed.data["test_runs"] == []

        bounded = registry.dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id), "limit": 1},
            api_key=e2e_api_key_admin,
        )
        assert bounded.success, bounded.message
        assert len(bounded.data["test_runs"]) == 1
        assert bounded.data["count"] == 1

    def test_run_list_rejects_an_unknown_status_or_limit(
        self, e2e_workspace, e2e_userrole_admin, e2e_api_key_admin: str
    ) -> None:
        """A typo in a filter must not silently return the whole workspace."""
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        for params in (
            {"workspace_id": str(e2e_workspace.id), "status": "In Progress"},
            {"workspace_id": str(e2e_workspace.id), "limit": 0},
            {"workspace_id": str(e2e_workspace.id), "limit": "many"},
            {"workspace_id": str(e2e_workspace.id), "limit": True},
        ):
            result = registry.dispatch_request(
                tool_name="test.run_list", params=params, api_key=e2e_api_key_admin
            )
            assert not result.success, f"{params!r} should have been rejected"
            assert result.error_code == "VALIDATION_ERROR", (
                f"{params!r} -> {result.error_code}: {result.message}"
            )

    def test_run_list_requires_a_workspace_id(
        self, e2e_api_key_admin: str
    ) -> None:
        """Without a workspace the dispatcher has nothing to gate on."""
        from mcp_server.tool_registry import ToolRegistry

        result = ToolRegistry().dispatch_request(
            tool_name="test.run_list", params={}, api_key=e2e_api_key_admin
        )
        assert not result.success
        assert result.error_code == "VALIDATION_ERROR"

    def test_run_list_does_not_leak_another_workspaces_runs(
        self,
        admin_client,
        e2e_workspace,
        e2e_userrole_admin,
        e2e_api_key_admin: str,
        e2e_tenant,
    ) -> None:
        """The list is workspace-scoped: a sibling workspace's runs are absent.

        Both workspaces belong to the same tenant and the caller is admin in
        the seeded one only, so this also exercises the dispatcher's read gate
        (``workspace_id`` required -> roles narrowed to that workspace).
        """
        from mcp_server.tool_registry import ToolRegistry
        from persistence.middleware import clear_request_tenant, set_request_tenant
        from persistence.models import Workspace

        set_request_tenant(e2e_tenant.id)
        try:
            other = Workspace.objects.create(
                tenant=e2e_tenant,
                name="Parity Other Workspace",
                is_active=True,
                preset={"name": "e2e_preset"},
            )
        finally:
            clear_request_tenant()

        registry = ToolRegistry()
        mine = registry.dispatch_request(
            tool_name="test.run_create",
            params={"workspace_id": str(e2e_workspace.id), "name": "mine"},
            api_key=e2e_api_key_admin,
        )
        assert mine.success, mine.message
        theirs = registry.dispatch_request(
            tool_name="test.run_create",
            params={"workspace_id": str(other.id), "name": "theirs"},
            api_key=e2e_api_key_admin,
        )
        # Either the run was created (caller is tenant admin) or the gate
        # refused it; both are correct. What must never happen is the seeded
        # workspace's list containing the other workspace's run.
        listed = registry.dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id)},
            api_key=e2e_api_key_admin,
        )
        assert listed.success, listed.message
        names = {r["name"] for r in listed.data["test_runs"]}
        assert "theirs" not in names, "test.run_list leaked another workspace's run"
        assert "mine" in names

    def test_a_rest_listed_run_is_reachable_over_mcp(
        self,
        admin_client,
        e2e_workspace,
        e2e_user_admin,
        e2e_userrole_admin,
        e2e_api_key_admin: str,
    ) -> None:
        """The QA repro, inverted: REST lists it, MCP must be able to reach it.

        The run is created through the same ``TestRunService`` the REST
        ViewSet calls, so this is not "MCP creating its own row and finding it
        again" — it is the exact #1080 situation, where the run's origin is
        invisible to the agent that did not create it.
        """
        from application.test_run_service import TestRunService
        from auth_tenancy.context import AuthContext, AuthMethod
        from mcp_server.tool_registry import ToolRegistry

        ctx = AuthContext(
            user_id=e2e_user_admin.id,
            tenant_id=e2e_workspace.tenant_id,
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
        )
        run = TestRunService().create_test_run(
            workspace_id=e2e_workspace.id, name="created-outside-mcp", ctx=ctx
        )

        # REST: the collection answers, and it answers with this run.
        rest = admin_client.get(
            "/api/v1/test-runs/", {"workspace_id": str(e2e_workspace.id)}
        )
        assert rest.status_code == 200, rest.content
        assert any(row["id"] == str(run.id) for row in rest.json()["results"]), (
            "REST no longer serves the run the service created — the two "
            "transports have diverged in the other direction"
        )

        listed = ToolRegistry().dispatch_request(
            tool_name="test.run_list",
            params={"workspace_id": str(e2e_workspace.id)},
            api_key=e2e_api_key_admin,
        )
        assert listed.success, listed.message
        assert any(
            row["id"] == str(run.id) for row in listed.data["test_runs"]
        ), "MCP cannot see a run that REST lists — this is issue #1080"


def test_tools_list_and_the_committed_manifest_agree_on_the_count() -> None:
    """One number, two sources — and the docs quote it.

    #1085 point 1 is a drift between the documented catalogue size and reality.
    The manifest guard (``test_tool_manifest_drift.py``) already pins the
    manifest to the live registry field by field; this adds the *human-facing*
    half: the figure a document may quote, with the recipe to re-derive it.
    """
    live = build_manifest()
    committed_path = _committed_manifest_path()
    assert committed_path is not None, (
        "docs/agent-templates/tool-manifest.json is not reachable from "
        f"{Path(__file__).resolve()} — see test_tool_manifest_drift.py"
    )
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    assert committed["tool_count"] == live["tool_count"], (
        f"documented tool count {committed['tool_count']} != live "
        f"{live['tool_count']}"
    )
    groups = {tool["prefix"] for tool in live["tools"]}
    assert len(groups) == 39, (
        f"tool-group prefix count changed to {len(groups)} (expected 39 as of "
        f"v1.8.0-beta.20 / #1263; ADR-019 WP3 added the 'suggestion' "
        f"prefix, #1265 added the 'metrics' prefix, #1257 added the "
        f"'tree_display_config' prefix, #1263 added the "
        f"'create_form_definition' prefix). "
        "If that is intended, update the number in docs/api/MCP-SURFACE.md "
        "together with the version and commit it was measured at."
    )


def _committed_manifest_path() -> Path | None:
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "docs" / "agent-templates" / "tool-manifest.json"
        if candidate.is_file():
            return candidate
    return None
