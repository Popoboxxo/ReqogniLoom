"""#1385 — query budget, finding snapshot and W20 contract for ``run_audit``.

The SE-Auditor was the slowest read endpoint in the workspace (78 queries,
p95 ~2.8 s, ~397 kB for a mid-sized workspace). The causes were both N+1 in
shape, not rule logic:

* every rule called ``AuditContext.iter_trace_links()``, so one audit run
  issued one full-tenant ``pl_tracelink`` scan per call site;
* ``AuditService.run_audit`` analysed the remediation of *every* returned
  finding, and the candidate-based remediations (TRACE-P1/Trace-P2) re-queried
  the workspace's StakeholderNeeds/ArchitectureElements once per finding.

These tests pin the fix from the outside, i.e. through ``run_audit`` only:

* :func:`test_run_audit_stays_within_query_budget` — an upper bound on the
  query count for a representative workspace. It does not depend on the exact
  current count, so a legitimate extra helper does not break it, while any
  reintroduced per-finding or per-rule query blows straight through it (the
  pre-#1385 code issued ~26 queries more on this very dataset).
* :func:`test_findings_snapshot_is_unchanged` — the finding list itself
  (``rule_id`` + ``severity`` + ``message`` + ``artifact_ids``) is frozen.
  The performance work must not change a single finding, and this is the proof.
* :func:`test_w20_counts_window_and_cursor_contract` — the #1382 contract
  (``counts`` ground truth, ``page_counts`` per window, ``next_offset``
  cursor) still holds on the same dataset.
* :func:`test_remediation_candidates_are_not_cached_across_runs` — the new
  candidate memo is scoped to one run: a workspace change between two runs is
  visible to the second run (no process-wide staleness).

Dataset size is deliberately small (tens of artifacts, not hundreds): query
counts here are driven by the number of rules and findings *kinds*, not by the
artifact count, so a compact fixture reproduces the shape at a fraction of the
runtime. Every row gets a deterministic primary key so the message snapshot is
byte-comparable across runs.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator

import pytest

from application.audit_service import AuditService
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

#: Upper bound for one ``run_audit`` over the fixture below (extended tier).
#: Measured 29 after #1385 (107 before it); 34 leaves room for a new rule
#: helper while still failing loudly on any per-finding regression.
QUERY_BUDGET = 34

#: Frozen snapshot of the fixture's findings — see the class docstring of
#: :func:`test_findings_snapshot_is_unchanged` for how to re-baseline it.
EXPECTED_PER_RULE = {
    "ARCH-003": 1,
    "CONS-P12": 16,
    "TRACE-P2": 8,
    "VERIF-P8": 12,
}
EXPECTED_MESSAGE_SHA256 = (
    "ce8b3f6362243f615b8cd241c9a10e99e79e67539c109bf82a86aae6a67562ee"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Perf Tenant", slug="perf-tenant-1385")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="perf-user-1385", email="perf1385@example.com", tenant=tenant
    )


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Perf Tenant",
    )


class _IdSequence:
    """Deterministic UUIDs, so a message snapshot is stable across runs."""

    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> uuid.UUID:
        value = uuid.UUID(int=self._next)
        self._next += 1
        return value


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str, ids) -> Artifact:
    return Artifact.objects.create(
        id=ids(),
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
    )


def _link(tenant: Tenant, source: Artifact, target: Artifact, link_type: str) -> None:
    TraceLink.objects.create(
        tenant=tenant, source=source, target=target, link_type=link_type
    )


def _build_workspace(tenant: Tenant) -> Workspace:
    """Build a workspace shaped like the #1385 repro (see module docstring).

    Layout: 3 StakeholderNeeds, a 2-level architecture, 4 root Requirements
    (each deriving from a Need) and 12 child Requirements (each deriving from a
    root). 8 of the 16 Requirements are unallocated, which is what makes
    TRACE-P2 emit findings and therefore what exercised the per-finding
    remediation query that dominated the pre-#1385 run.
    """
    ids = _IdSequence()
    TenantContext.set_tenant(tenant.id)
    workspace = make_workspace(tenant, name="Perf-WS-1385")

    needs = []
    for index in range(3):
        artifact = _artifact(tenant, workspace, "StakeholderNeed", ids)
        needs.append(
            StakeholderNeed.objects.create(
                id=ids(), tenant=tenant, artifact=artifact, title=f"Need {index}"
            )
        )

    elements = []
    parent = None
    for index in range(2):
        artifact = _artifact(tenant, workspace, "ArchitectureElement", ids)
        element = ArchitectureElement.objects.create(
            id=ids(), tenant=tenant, artifact=artifact, title=f"Element {index}", parent=parent
        )
        elements.append(element)
        parent = element

    roots = []
    for index in range(4):
        artifact = _artifact(tenant, workspace, "Requirement", ids)
        requirement = Requirement.objects.create(
            id=ids(),
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=f"Root {index}",
        )
        roots.append(requirement)
        _link(tenant, artifact, needs[index % len(needs)].artifact, "derives-from")

    children = []
    for index in range(12):
        artifact = _artifact(tenant, workspace, "Requirement", ids)
        requirement = Requirement.objects.create(
            id=ids(),
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=f"Child {index}",
        )
        children.append(requirement)
        _link(tenant, artifact, roots[index % len(roots)].artifact, "derives-from")

    for index, requirement in enumerate(children[4:]):
        _link(
            tenant,
            requirement.artifact,
            elements[index % len(elements)].artifact,
            "allocated-to",
        )
    return workspace


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return _build_workspace(tenant)


def _run(workspace: Workspace, ctx: AuthContext, **kwargs):
    return AuditService().run_audit(workspace.id, ctx, tier="extended", **kwargs)


def _message_snapshot(report) -> tuple[str, dict[str, int]]:
    """Return ``(sha256 of the normalised finding list, per-rule counts)``."""
    rows = [
        {
            "rule_id": view.finding.rule_id,
            "severity": view.finding.severity.value,
            "message": view.finding.message,
            "artifact_ids": list(view.finding.artifact_ids),
        }
        for view in report.findings
    ]
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    per_rule: dict[str, int] = {}
    for row in rows:
        per_rule[row["rule_id"]] = per_rule.get(row["rule_id"], 0) + 1
    return hashlib.sha256(payload.encode()).hexdigest(), dict(sorted(per_rule.items()))


# ---------------------------------------------------------------------------
# Query budget
# ---------------------------------------------------------------------------


def test_run_audit_stays_within_query_budget(django_assert_max_num_queries, workspace, ctx):
    """One ``run_audit`` must not scale its query count with the finding count.

    The pre-#1385 shape issued one full-tenant trace-link scan per rule call
    site plus one remediation candidate lookup per TRACE-P2 finding, so the
    count grew with the number of findings. ``QUERY_BUDGET`` is an upper bound,
    not an exact count, so a legitimate extra helper does not break it while a
    reintroduced per-finding query immediately does.
    """
    with django_assert_max_num_queries(QUERY_BUDGET):
        report = _run(workspace, ctx)

    assert report.findings


# ---------------------------------------------------------------------------
# Finding snapshot (the fix must not change what the auditor reports)
# ---------------------------------------------------------------------------


def test_findings_snapshot_is_unchanged(workspace, ctx):
    """The finding list is frozen: same rules, severities, messages, artifacts.

    Re-baselining is a deliberate act: if a rule's wording or severity really
    has to change, update ``EXPECTED_PER_RULE``/``EXPECTED_MESSAGE_SHA256`` in
    the same commit and say why in the commit message — a diff here without a
    rule change is a regression in the audit result.
    """
    report = _run(workspace, ctx)
    digest, per_rule = _message_snapshot(report)

    assert per_rule == EXPECTED_PER_RULE
    assert digest == EXPECTED_MESSAGE_SHA256, (
        "the audit finding set changed; if this is intended, re-baseline "
        f"EXPECTED_MESSAGE_SHA256 to {digest!r}"
    )


# ---------------------------------------------------------------------------
# #1382 W20 contract on the same dataset
# ---------------------------------------------------------------------------


def test_w20_counts_window_and_cursor_contract(workspace, ctx):
    """``counts`` = ground truth, ``page_counts`` = window, ``next_offset`` = cursor."""
    full = _run(workspace, ctx)
    total = full.total_findings_available
    assert total == sum(EXPECTED_PER_RULE.values())

    page = _run(workspace, ctx, limit=10, offset=0)
    data = page.to_dict()

    # counts: unchanged by paging (ground truth over the whole run).
    assert data["counts"]["total"] == total
    assert data["total_findings_available"] == total
    # page_counts: describes only the returned window, and always adds up.
    assert data["page_counts"]["total"] == len(data["findings"]) == 10
    assert (
        data["page_counts"]["blockers"] + data["page_counts"]["warnings"]
        == data["page_counts"]["total"]
    )
    # cursor advances monotonically and stops at the end of the run.
    assert data["next_offset"] == 10
    assert data["offset"] == 0
    assert data["truncated"] is True

    last = _run(workspace, ctx, limit=10, offset=total - 1)
    assert last.to_dict()["next_offset"] is None
    assert len(last.findings) == 1


def test_default_run_offers_no_cursor(workspace, ctx):
    """The capped (no ``limit``) branch is not a sequential walk — no cursor."""
    data = _run(workspace, ctx).to_dict()
    assert data["next_offset"] is None
    assert data["page_counts"]["total"] == len(data["findings"])
    assert data["counts"]["total"] == data["total_findings_available"]


# ---------------------------------------------------------------------------
# Run-scoped remediation cache (no cross-run staleness)
# ---------------------------------------------------------------------------


def test_remediation_candidates_are_not_cached_across_runs(tenant: Tenant, ctx):
    """A second run must see a workspace change the first run missed.

    The candidate memo added in #1385 is scoped to a single audit run. If it
    leaked into the process, the TRACE-P2 proposal below would keep saying
    "allocate to the workspace's only ArchitectureElement" even after a second
    element made that target ambiguous — a silently wrong Adopt suggestion.
    """
    ids = _IdSequence()
    TenantContext.set_tenant(tenant.id)
    workspace = make_workspace(tenant, name="Perf-WS-1385-cache")

    need_artifact = _artifact(tenant, workspace, "StakeholderNeed", ids)
    need = StakeholderNeed.objects.create(
        id=ids(), tenant=tenant, artifact=need_artifact, title="Only Need"
    )
    element_artifact = _artifact(tenant, workspace, "ArchitectureElement", ids)
    ArchitectureElement.objects.create(
        id=ids(), tenant=tenant, artifact=element_artifact, title="Only Element"
    )

    root_artifact = _artifact(tenant, workspace, "Requirement", ids)
    Requirement.objects.create(
        id=ids(),
        tenant=tenant,
        artifact=root_artifact,
        workspace=workspace,
        title="Root",
    )
    _link(tenant, root_artifact, need.artifact, "derives-from")

    first = _run(workspace, ctx)
    p2 = [view for view in first.findings if view.finding.rule_id == "TRACE-P2"]
    assert len(p2) == 1
    assert p2[0].remediation.automatic is True

    # A second element makes the allocation target ambiguous.
    second_artifact = _artifact(tenant, workspace, "ArchitectureElement", ids)
    ArchitectureElement.objects.create(
        id=ids(), tenant=tenant, artifact=second_artifact, title="Second Element"
    )

    second = _run(workspace, ctx)
    p2_again = [view for view in second.findings if view.finding.rule_id == "TRACE-P2"]
    assert len(p2_again) == 1
    assert p2_again[0].remediation.automatic is False
    assert "2 ArchitectureElements" in p2_again[0].remediation.reason
