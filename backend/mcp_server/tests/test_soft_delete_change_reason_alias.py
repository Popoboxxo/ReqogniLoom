"""P1.10 (finding M-14) — one canonical soft-delete reason, ``reason`` as alias.

The MCP surface spelled the audit reason of a soft-delete ``reason`` on some
tools and ``change_reason`` on others, while every REST ``DELETE`` takes
``change_reason``. A client therefore had to know which transport it was
talking to, and the audit trail of the two transports was not comparable.

This module pins the contract that makes the two transports one vocabulary:

* :func:`mcp_server.tools.base.soft_delete_reason` resolves the reason:
  canonical ``change_reason``, deprecated alias ``reason``, canonical wins when
  both are sent, blank is "not supplied" (truth table below);
* **every** ``*.outdate`` tool in the live catalogue advertises both keys, with
  ``reason`` marked ``deprecated`` — the list is derived from
  ``build_manifest()``, so a tool added later cannot silently skip the alias;
* the handler families route their reason through the helper (source ratchet)
  and hand the resolved value to the **domain service**. The handlers used to
  call ``workflow.services.outdate()``, the engine's escape hatch, which has
  ignored its ``reason`` argument since Phase 4 (it writes neither a history
  entry nor an audit row): it cannot enforce the preset's change-reason policy,
  it cannot honour an item-level write rule, and it leaves the caller's reason
  nowhere. Section 4 therefore asserts the ``delete_*`` service method is what
  runs and that the escape hatch is not touched — a spy on ``outdate()`` would
  pin the bug, not the contract;
* section 5 runs the real services against a real database and pins what the
  routing buys: the item-level write rule (#1716) answers the same refusal
  class on MCP and REST for the same actor, ``change_reason: mandatory``
  answers ``VALIDATION_ERROR`` for a reason-less call and accepts either key,
  and the ``AuditEntry`` of the deletion carries the resolved reason;
* ``*.reactivate`` tools stay reason-less — the audit result of P1.10's
  "verify the reactivate side" step is pinned here.

The ``work_item`` lifecycle added in P2.8 is covered end to end in
``test_work_item_tool_group.py``.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from application.preset_policy_service import get_preset_policy_service
from application.requirement_service import RequirementService
from application.workspace_provisioning import provision_workspace_defaults
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_NONE,
    ITEM_PERMISSION_READ,
    ROLE_EDITOR,
    ItemPermission,
    UserRole,
)
from auth_tenancy.services.permission_cache import PermissionCache
from diagram.models import Diagram
from mcp_server.management.commands.export_tool_manifest import build_manifest
from mcp_server.tools.base import soft_delete_reason
from mcp_server.tools.diagram import DiagramToolGroup
from mcp_server.tools.document import DocumentToolGroup
from mcp_server.tools.generic import GenericCrudToolGroup
from mcp_server.tools.goals import GoalToolGroup
from mcp_server.tools.needs import StakeholderNeedsToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Adr,
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    User,
    Workspace,
)
from presets.services import switch_preset

pytestmark = pytest.mark.django_db

#: The workspace id the fake entities report; nothing is persisted.
WORKSPACE_ID = uuid4()

#: Modules that implement a soft-delete handler. Every one of them must route
#: the reason through ``soft_delete_reason`` — this tuple is the ratchet, not
#: the catalogue: a new module belongs here when it gains an outdate tool.
OUTDATE_FAMILY_MODULES = (
    "architecture.py",
    "diagram.py",
    "document.py",
    "generic.py",
    "goals.py",
    "needs.py",
    "requirements.py",
    "tests.py",
    "work_items.py",
)

#: The six modules whose handler used to call the engine escape hatch directly.
SERVICE_ROUTED_MODULES = (
    "architecture.py",
    "diagram.py",
    "generic.py",
    "needs.py",
    "requirements.py",
    "tests.py",
)


def _ctx() -> AuthContext:
    """An editor context — enough for the DI-based groups (nothing hits a DB)."""
    return AuthContext(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
    )


# ---------------------------------------------------------------------------
# 1. The resolver's truth table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"change_reason": "canonical"}, "canonical"),
        ({"reason": "legacy"}, "legacy"),
        # The canonical value wins when both are present — never merged, never
        # an error, so an old client keeps working unchanged.
        ({"change_reason": "canonical", "reason": "legacy"}, "canonical"),
        ({"change_reason": "canonical", "reason": "canonical"}, "canonical"),
        # A blank canonical value is "not supplied" (a client that serialises
        # an unset optional field as ""), so the alias still applies.
        ({"change_reason": "", "reason": "legacy"}, "legacy"),
        ({"change_reason": "   "}, ""),
        ({"change_reason": None}, ""),
        ({"reason": None}, ""),
        ({}, ""),
        ({"change_reason": "  spaced  "}, "spaced"),
    ],
)
def test_soft_delete_reason_resolution(
    params: dict[str, Any], expected: str
) -> None:
    assert soft_delete_reason(params) == expected


# ---------------------------------------------------------------------------
# 2. Every outdate tool advertises the canonical key and the deprecated alias
# ---------------------------------------------------------------------------


def _catalogue() -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool for tool in build_manifest()["tools"]}


def _properties(tool: dict[str, Any]) -> dict[str, Any]:
    return tool["inputSchema"].get("properties") or {}


def test_every_outdate_tool_advertises_both_reason_keys() -> None:
    """Derived from the live catalogue: a new outdate tool cannot opt out."""
    tools = _catalogue()
    outdate_tools = sorted(name for name in tools if name.endswith(".outdate"))
    # The families P1.10 covers (generic CRUD group + hand-written groups).
    assert {
        "adr.outdate",
        "architecture.outdate",
        "change_request.outdate",
        "diagram.outdate",
        "document.outdate",
        "glossary.outdate",
        "goal.outdate",
        "issue.outdate",
        "needs.outdate",
        "requirement.outdate",
        "risk.outdate",
        "test.outdate",
        "work_item.outdate",
    } <= set(outdate_tools)

    for name in outdate_tools:
        properties = _properties(tools[name])
        assert "change_reason" in properties, (
            f"{name} does not advertise the canonical 'change_reason'"
        )
        assert "reason" in properties, (
            f"{name} does not keep the deprecated 'reason' alias"
        )
        assert properties["reason"].get("deprecated") is True, (
            f"{name} must mark 'reason' deprecated"
        )
        assert "change_reason" in (
            properties["reason"].get("description") or ""
        ), f"{name} must name 'change_reason' as the replacement"
        # Both stay optional: the preset, not the schema, decides mandatory.
        required = set(tools[name]["inputSchema"].get("required") or [])
        assert "change_reason" not in required
        assert "reason" not in required


def test_no_reactivate_tool_accepts_a_reason() -> None:
    """P1.10 audit result: restoring needs no justification, so none is offered.

    Before this suite there was no ``reason`` on any ``*.reactivate`` tool;
    pinning it stops a future edit from inventing one asymmetrically.
    """
    tools = _catalogue()
    reactivate_tools = sorted(
        name for name in tools if name.endswith(".reactivate")
    )
    assert reactivate_tools, "no reactivate tools in the catalogue"
    for name in reactivate_tools:
        properties = _properties(tools[name])
        assert "reason" not in properties, f"{name} must not accept 'reason'"
        # goal.reactivate carries the domain-level change_reason its workflow
        # transition requires; every other group restores without one.
        if name != "goal.reactivate":
            assert "change_reason" not in properties, (
                f"{name} must not accept 'change_reason'"
            )


# ---------------------------------------------------------------------------
# 3. Source ratchets: helper first, service (never the escape hatch) second
# ---------------------------------------------------------------------------


def _imports(source: str) -> set[tuple[str, str]]:
    """Return every ``from <module> import <name>`` pair in *source*."""
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                pairs.add((node.module, alias.name))
    return pairs


def test_outdate_family_routes_the_reason_through_the_helper() -> None:
    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    for module_name in OUTDATE_FAMILY_MODULES:
        source = (tools_dir / module_name).read_text(encoding="utf-8")
        assert "soft_delete_reason(" in source, (
            f"{module_name} must resolve its soft-delete reason through "
            "soft_delete_reason()"
        )
        assert 'params.get("reason"' not in source, (
            f"{module_name} still reads the deprecated 'reason' key directly "
            "instead of going through soft_delete_reason()"
        )


def test_outdate_handlers_do_not_import_the_engine_escape_hatch() -> None:
    """P1.10: the domain service is the deletion path, not ``outdate()``.

    ``workflow.services.outdate()`` ignores its ``reason`` argument since
    Phase 4 — no history entry, no audit row — so a handler that calls it
    bypasses the preset gate, the item-level write rule and the audit reason.
    Checked on the import graph (not on text) so the comments that explain the
    avoidance do not trip the ratchet.
    """
    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    for module_name in SERVICE_ROUTED_MODULES:
        source = (tools_dir / module_name).read_text(encoding="utf-8")
        assert ("workflow.services", "outdate") not in _imports(source), (
            f"{module_name} still imports workflow.services.outdate — the "
            "soft-delete must go through the domain service"
        )


# ---------------------------------------------------------------------------
# 4. Wiring: the resolved reason is what the DOMAIN SERVICE receives
# ---------------------------------------------------------------------------

_WIRING_CASES: tuple[tuple[str, dict[str, Any], str], ...] = (
    ("canonical", {"change_reason": "canonical"}, "canonical"),
    ("alias", {"reason": "legacy"}, "legacy"),
    ("both", {"change_reason": "canonical", "reason": "legacy"}, "canonical"),
)


class _FakeAdrService:
    """Minimal AdrService stand-in (the generic group resolves four methods)."""

    def __init__(self) -> None:
        self.deleted: list[dict[str, Any]] = []

    def get_adr(self, adr_id: Any, ctx: Any) -> Any:
        return SimpleNamespace(workspace_id=WORKSPACE_ID)

    def create_adr(self, ctx: Any, title: str, description: str = "") -> None:
        return None

    def update_adr(self, adr_id: Any, ctx: Any, title: str | None = None) -> None:
        return None

    def delete_adr(self, adr_id: Any, ctx: Any, change_reason: str = "") -> None:
        self.deleted.append({"adr_id": adr_id, "change_reason": change_reason})

    def list_adrs(
        self, ctx: Any, workspace_id: Any, include_deleted: bool = False
    ) -> list[Any]:
        return []


def test_generic_outdate_calls_the_service_delete_with_the_resolved_reason() -> None:
    """Covers the five generated tools (adr/risk/issue/glossary/change_request)."""
    for label, params, expected in _WIRING_CASES:
        service = _FakeAdrService()
        group = GenericCrudToolGroup(
            prefix="adr", service_class=lambda: service, item_type="Adr"
        )
        adr_id = uuid4()
        with patch("workflow.services.outdate") as escape_hatch:
            result = group.execute_tool(
                "adr.outdate",
                {"id": str(adr_id), **params},
                _ctx(),
                "reqlo_test",
            )
        assert result.success is True, f"{label}: {result.message}"
        assert service.deleted == [
            {"adr_id": adr_id, "change_reason": expected}
        ], label
        escape_hatch.assert_not_called()


def test_requirement_outdate_calls_delete_requirement_not_the_escape_hatch() -> None:
    """The handler must reach ``RequirementService.delete_requirement``.

    The pre-P1.10 wiring test spied on ``workflow.services.outdate`` — the very
    call the defect consisted of. This one patches the *service* method (on the
    real class, so the injection point stays exercised) and asserts the escape
    hatch is never touched.
    """
    for label, params, expected in _WIRING_CASES:
        with (
            patch.object(
                RequirementService, "delete_requirement", autospec=True
            ) as delete_call,
            patch("workflow.services.outdate") as escape_hatch,
            patch("mcp_server.tools.requirements.write_mcp_audit") as mcp_audit,
        ):
            req_id = uuid4()
            result = RequirementsToolGroup().execute_tool(
                "requirement.outdate",
                {"id": str(req_id), **params},
                _ctx(),
                "reqlo_test",
            )
        assert result.success is True, f"{label}: {result.message}"
        assert delete_call.call_args.kwargs["change_reason"] == expected, label
        escape_hatch.assert_not_called()
        # The MCP provenance entry (tool name + api-key hash) mirrors the same
        # resolved reason, so both rows of one deletion agree.
        assert mcp_audit.call_args.kwargs["details"] == {
            "change_reason": expected
        }, label


def test_needs_outdate_calls_the_service_delete_with_the_resolved_reason() -> None:
    for label, params, expected in _WIRING_CASES:
        service = MagicMock()
        group = StakeholderNeedsToolGroup(service=service)
        need_id = uuid4()
        with (
            patch("workflow.services.outdate") as escape_hatch,
            patch("mcp_server.tools.needs.write_mcp_audit"),
        ):
            result = group.execute_tool(
                "needs.outdate",
                {"id": str(need_id), **params},
                _ctx(),
                "reqlo_test",
            )
        assert result.success is True, f"{label}: {result.message}"
        assert service.delete.call_args.kwargs["change_reason"] == expected, label
        escape_hatch.assert_not_called()


def test_document_outdate_forwards_the_resolved_reason() -> None:
    """The document group owns no injected service; ``_svc()`` is the seam."""
    for label, params, expected in _WIRING_CASES:
        service = MagicMock()
        with patch.object(DocumentToolGroup, "_svc", return_value=service):
            result = DocumentToolGroup().execute_tool(
                "document.outdate",
                {"id": str(uuid4()), **params},
                _ctx(),
                "reqlo_test",
            )
        assert result.success is True, f"{label}: {result.message}"
        assert service.delete_document.call_args.kwargs["change_reason"] == expected


def test_goal_outdate_forwards_the_resolved_reason() -> None:
    """Goals soft-archive through ``GoalService.archive``, not ``outdate()``."""
    goal = SimpleNamespace(
        id=uuid4(),
        lineage_id=uuid4(),
        sequence_number=1,
        title="Goal",
        description="",
        artifact=None,
    )
    for label, params, expected in _WIRING_CASES:
        service = MagicMock()
        service.archive.return_value = goal
        with patch("mcp_server.tools.goals.GoalService", return_value=service):
            result = GoalToolGroup().execute_tool(
                "goal.outdate",
                {"goal_id": str(goal.id), **params},
                _ctx(),
                "reqlo_test",
            )
        assert result.success is True, f"{label}: {result.message}"
        assert service.archive.call_args.kwargs["change_reason"] == expected


# ---------------------------------------------------------------------------
# 5. Real DB: item-level rule, preset gate and audit reason are the service's
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_permission_cache():
    PermissionCache.clear_thread()
    yield
    PermissionCache.clear_thread()


class _Env(SimpleNamespace):
    """Tenant + workspace + editor + AuthContext of one seeded test database."""

    tenant: Tenant
    workspace: Workspace
    user: User
    ctx: AuthContext


def _make_env(slug: str, *, tier: str = "minimal") -> _Env:
    """Seed a tenant/workspace/editor and provision the workflow defaults."""
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
        user = User.objects.create(
            username=f"{slug}-editor", email=f"{slug}@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        # The REST parity leg logs in over the API, which resolves the editor
        # role from the workspace membership row.
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset=tier,
        )
        if tier != "minimal":
            switch_preset(str(workspace.id), tier)
            get_preset_policy_service().invalidate_cache(str(workspace.id))
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )
    return _Env(tenant=tenant, workspace=workspace, user=user, ctx=ctx)


def _seed(kind: str, env: _Env) -> Any:
    """Create the backing Artifact plus the entity row for *kind*."""
    artifact_type = {
        "Requirement": "requirement",
        "Adr": "adr",
        "StakeholderNeed": "stakeholder_need",
    }[kind]
    set_request_tenant(env.tenant.id)
    try:
        artifact = Artifact.objects.create(
            workspace=env.workspace,
            tenant=env.tenant,
            artifact_type=artifact_type,
        )
        common = {"tenant": env.tenant, "artifact": artifact}
        if kind == "Requirement":
            return Requirement.objects.create(
                **common, workspace=env.workspace, title="Soft-delete subject"
            )
        if kind == "Adr":
            return Adr.objects.create(
                **common, workspace_id=env.workspace.id, title="Soft-delete subject"
            )
        return StakeholderNeed.objects.create(
            **common, title="Soft-delete subject"
        )
    finally:
        clear_request_tenant()


def _seed_diagram(env: _Env) -> Diagram:
    set_request_tenant(env.tenant.id)
    try:
        return Diagram.objects.create(
            tenant=env.tenant,
            workspace=env.workspace,
            name="Soft-delete subject",
            diagram_type="block",
            payload_format="json",
            payload='{"nodes": []}',
        )
    finally:
        clear_request_tenant()


def _grant(env: _Env, artifact: Artifact, level: str) -> None:
    ItemPermission.unscoped.create(
        tenant=env.tenant,
        user=env.user,
        workspace=env.workspace,
        artifact=artifact,
        permission_level=level,
    )


def _is_live(row: Any) -> bool:
    """True when the row's backing Artifact is not flagged outdated."""
    set_request_tenant(row.tenant_id)
    try:
        artifact = Artifact.unscoped.get(pk=row.artifact_id)
        return artifact.lifecycle_status != "outdated"
    finally:
        clear_request_tenant()


def _run(tool: str, params: dict[str, Any], env: _Env, group: Any) -> Any:
    set_request_tenant(env.tenant.id)
    try:
        return group.execute_tool(tool, params, env.ctx, "reqlo_test")
    finally:
        clear_request_tenant()


def _audit_ids(tenant_id: UUID) -> set[UUID]:
    return set(
        AuditEntry.unscoped.filter(tenant_id=tenant_id).values_list("id", flat=True)
    )


def _new_entries(tenant_id: UUID, before: set[UUID]) -> list[AuditEntry]:
    return [
        entry
        for entry in AuditEntry.unscoped.filter(tenant_id=tenant_id)
        if entry.id not in before
    ]


# -- 5a. item-level write rule (#1716) parity with REST ---------------------


@pytest.mark.parametrize(
    ("level", "mcp_code", "rest_status"),
    [
        (ITEM_PERMISSION_READ, "PERMISSION_DENIED", 403),
        (ITEM_PERMISSION_NONE, "NOT_FOUND", 404),
    ],
)
def test_requirement_outdate_obeys_the_item_level_rule_like_rest(
    level: str, mcp_code: str, rest_status: int
) -> None:
    """#1716 parity: the MCP soft-delete is gated exactly like the REST DELETE.

    Before P1.10 the handler called ``workflow.services.outdate()`` directly,
    which never consults an item-level rule — an editor could soft-delete an
    artifact an admin had locked down, while the REST DELETE refused.
    """
    from rest_framework.test import APIClient

    env = _make_env(f"sdr-req-{uuid4().hex[:8]}")
    req = _seed("Requirement", env)
    _grant(env, req.artifact, level)

    result = _run(
        "requirement.outdate",
        {"id": str(req.id), "change_reason": "obsolete"},
        env,
        RequirementsToolGroup(),
    )

    assert result.success is False
    assert result.error_code == mcp_code, result.message
    assert _is_live(req) is True, "a denied delete must not soft-delete the row"

    # REST parity for the same actor and the same rule: same refusal class.
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": env.user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    response = client.delete(f"/api/v1/requirements/{req.id}/")
    assert response.status_code == rest_status, response.content
    assert _is_live(req) is True


def test_generic_adr_outdate_obeys_the_item_level_rule() -> None:
    """One generic-CRUD type proves the same gate on the generated tools."""
    from application.adr_service import AdrService

    env = _make_env(f"sdr-adr-{uuid4().hex[:8]}")
    adr = _seed("Adr", env)
    _grant(env, adr.artifact, ITEM_PERMISSION_READ)

    result = _run(
        "adr.outdate",
        {"id": str(adr.id), "change_reason": "obsolete"},
        env,
        GenericCrudToolGroup(prefix="adr", service_class=AdrService),
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED", result.message
    assert _is_live(adr) is True


# -- 5b. the preset's change_reason policy ---------------------------------


def test_mandatory_preset_rejects_a_reason_less_outdate() -> None:
    env = _make_env(f"sdr-preset-{uuid4().hex[:8]}", tier="extended")
    req = _seed("Requirement", env)

    result = _run(
        "requirement.outdate", {"id": str(req.id)}, env, RequirementsToolGroup()
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR", result.message
    assert result.message == "change_reason is required by preset policy."
    assert _is_live(req) is True


@pytest.mark.parametrize("key", ["reason", "change_reason"])
def test_mandatory_preset_accepts_either_reason_key(key: str) -> None:
    """The alias resolves to the value the policy is checked against."""
    env = _make_env(f"sdr-preset-{key[:6]}-{uuid4().hex[:6]}", tier="extended")
    req = _seed("Requirement", env)

    result = _run(
        "requirement.outdate",
        {"id": str(req.id), key: "policy satisfied"},
        env,
        RequirementsToolGroup(),
    )

    assert result.success is True, result.message
    assert _is_live(req) is False


def test_mandatory_preset_is_enforced_on_the_generic_and_diagram_handlers() -> None:
    """The handler-level half of the gate (services lacking the policy check)."""
    from application.adr_service import AdrService

    env = _make_env(f"sdr-preset-gen-{uuid4().hex[:8]}", tier="extended")
    adr = _seed("Adr", env)
    diagram = _seed_diagram(env)

    adr_result = _run(
        "adr.outdate",
        {"id": str(adr.id)},
        env,
        GenericCrudToolGroup(prefix="adr", service_class=AdrService),
    )
    assert adr_result.success is False
    assert adr_result.error_code == "VALIDATION_ERROR", adr_result.message
    assert adr_result.message == "change_reason is required by preset policy."
    assert _is_live(adr) is True

    diagram_result = _run(
        "diagram.outdate", {"id": str(diagram.id)}, env, DiagramToolGroup()
    )
    assert diagram_result.success is False
    assert diagram_result.error_code == "VALIDATION_ERROR", diagram_result.message
    assert diagram_result.message == "change_reason is required by preset policy."


# -- 5c. the audit entry carries the resolved reason -----------------------


def test_requirement_outdate_audit_entry_carries_the_reason() -> None:
    env = _make_env(f"sdr-audit-req-{uuid4().hex[:8]}")
    req = _seed("Requirement", env)
    before = _audit_ids(env.tenant.id)

    result = _run(
        "requirement.outdate",
        {"id": str(req.id), "reason": "superseded by REQ-2"},
        env,
        RequirementsToolGroup(),
    )
    assert result.success is True, result.message

    entries = _new_entries(env.tenant.id, before)
    domain = [
        entry
        for entry in entries
        if entry.op == "delete"
        and entry.entity_type == "Requirement"
        and entry.change_reason == "superseded by REQ-2"
    ]
    assert len(domain) == 1, [
        (e.op, e.entity_type, e.change_reason, e.client_name) for e in entries
    ]
    # The MCP provenance row (REQ-L2-MC-012) mirrors the same reason.
    provenance = [
        entry for entry in entries if entry.client_name == "requirement.outdate"
    ]
    assert len(provenance) == 1
    assert provenance[0].details == {"change_reason": "superseded by REQ-2"}


def test_generic_adr_outdate_audit_entry_carries_the_reason() -> None:
    from application.adr_service import AdrService

    env = _make_env(f"sdr-audit-adr-{uuid4().hex[:8]}")
    adr = _seed("Adr", env)
    before = _audit_ids(env.tenant.id)

    result = _run(
        "adr.outdate",
        {"id": str(adr.id), "change_reason": "decision withdrawn"},
        env,
        GenericCrudToolGroup(prefix="adr", service_class=AdrService),
    )
    assert result.success is True, result.message

    entries = _new_entries(env.tenant.id, before)
    domain = [
        entry
        for entry in entries
        if entry.op == "delete"
        and entry.entity_type == "Adr"
        and entry.change_reason == "decision withdrawn"
    ]
    assert len(domain) == 1, [
        (e.op, e.entity_type, e.change_reason) for e in entries
    ]
    assert domain[0].entity_id == adr.id


def test_needs_outdate_audit_entry_carries_the_reason() -> None:
    env = _make_env(f"sdr-audit-need-{uuid4().hex[:8]}")
    need = _seed("StakeholderNeed", env)
    before = _audit_ids(env.tenant.id)

    result = _run(
        "needs.outdate",
        {"id": str(need.id), "change_reason": "stakeholder withdrew"},
        env,
        StakeholderNeedsToolGroup(),
    )
    assert result.success is True, result.message

    entries = _new_entries(env.tenant.id, before)
    domain = [
        entry
        for entry in entries
        if entry.op == "delete"
        and entry.entity_type == "StakeholderNeed"
        and entry.change_reason == "stakeholder withdrew"
    ]
    assert len(domain) == 1, [
        (e.op, e.entity_type, e.change_reason) for e in entries
    ]
    assert domain[0].entity_id == need.id


def test_diagram_outdate_audit_entry_carries_the_reason() -> None:
    """``delete_diagram`` is the one service that had no audit entry at all."""
    env = _make_env(f"sdr-audit-diagram-{uuid4().hex[:8]}")
    diagram = _seed_diagram(env)
    before = _audit_ids(env.tenant.id)

    result = _run(
        "diagram.outdate",
        {"id": str(diagram.id), "change_reason": "superseded sketch"},
        env,
        DiagramToolGroup(),
    )
    assert result.success is True, result.message

    entries = _new_entries(env.tenant.id, before)
    domain = [
        entry
        for entry in entries
        if entry.op == "delete"
        and entry.entity_type == "Diagram"
        and entry.entity_id == diagram.id
        and entry.change_reason == "superseded sketch"
    ]
    assert len(domain) == 1, [
        (e.op, e.entity_type, e.change_reason) for e in entries
    ]
