"""Regression tests for issue #572 — cross-workspace volatility data leak.

QA finding (2026-08-16, v1.6.0 STABLE): ``GET /api/v1/metrics/?workspace_id=<WS1>``
and ``?workspace_id=<WS2>`` (13 vs. 882 Requirements) returned a byte-identical
``volatility`` block, with titles that only belong to WS1.

Root cause: ``se_metrics.aggregator._fetch_audit_entries`` builds its
``AuditQueryFilters`` from ``entity_type`` + ``timestamp_from`` only — the
``workspace_id`` parameter it receives is never applied to the query.
``AuditEntry`` rows are tenant-scoped (RLS + ``TenantManager``), not
workspace-scoped, so *every* workspace inside the same tenant fed its
volatility calculation from the *same* tenant-wide set of "Requirement
update" audit entries. Coverage, workflow-gaps and risks all pass
``workspace_id`` into their respective service calls and stayed correctly
isolated — only volatility skipped it.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from persistence.tenancy import TenantContext
from se_metrics.aggregator import MetricsAggregator, _fetch_audit_entries

# transaction=True: MetricsAggregator.compute() fans out to a
# ThreadPoolExecutor, and each worker thread gets its own DB connection.
# The default (transaction-wrapped, rolled-back) `db` fixture would make
# fixture data invisible to those other connections; `transaction=True`
# actually commits so cross-thread reads see it (mirrors production).
pytestmark = pytest.mark.django_db(transaction=True)


def _make_workspace_with_requirement(tenant, ws_name: str, req_title: str):
    """Create a Workspace + Requirement (with its Artifact) for *tenant*."""
    from persistence.models import Artifact, Requirement, Workspace

    workspace = Workspace.objects.create(
        tenant=tenant, name=ws_name, preset={"name": "extended"}
    )
    art = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=art,
        workspace=workspace,
        title=req_title,
        status="draft",
    )
    return workspace, req


def _write_update_audit_entries(requirement_id, count: int):
    """Directly persist *count* 'update' AuditEntry rows for a Requirement.

    Bypasses the AuditLogWriter event-bus plumbing on purpose — this test
    only needs rows in the table that ``_fetch_audit_entries`` reads back,
    not the full write-path integration.
    """
    from audit.models import AuditEntry

    for _ in range(count):
        AuditEntry.objects.create(
            actor="tester@example.com",
            actor_type=AuditEntry.ACTOR_TYPE_USER,
            op=AuditEntry.OP_UPDATE,
            entity_type="Requirement",
            entity_id=requirement_id,
        )


@pytest.fixture
def tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(
        name="Volatility Isolation Tenant",
        slug=f"vol-iso-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture
def other_tenant(db):
    """A second, unrelated tenant — for the cross-tenant regression (F5)."""
    from persistence.models import Tenant

    return Tenant.objects.create(
        name="Volatility Isolation Other Tenant",
        slug=f"vol-iso-other-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture
def two_workspaces(tenant):
    """WS1 with 3 volatile-requirement changes, WS2 with 1 (different req)."""
    TenantContext.set_tenant(tenant.id)
    try:
        ws1, req1 = _make_workspace_with_requirement(
            tenant, "WS1", "WS1 requirement"
        )
        ws2, req2 = _make_workspace_with_requirement(
            tenant, "WS2", "WS2 requirement"
        )
        _write_update_audit_entries(req1.id, count=3)
        _write_update_audit_entries(req2.id, count=1)
    finally:
        TenantContext.clear_tenant()
    return tenant, ws1, req1, ws2, req2


class TestFetchAuditEntriesWorkspaceScoping:
    """Unit-level: _fetch_audit_entries must only return entries whose
    Requirement belongs to the requested workspace."""

    def test_fetch_scopes_to_requested_workspace(self, two_workspaces):
        tenant, ws1, req1, ws2, req2 = two_workspaces

        entries_ws1 = _fetch_audit_entries(
            workspace_id=str(ws1.id), timeframe="P30D", tenant_id=tenant.id
        )
        entries_ws2 = _fetch_audit_entries(
            workspace_id=str(ws2.id), timeframe="P30D", tenant_id=tenant.id
        )

        ids_ws1 = {str(e.entity_id) for e in entries_ws1}
        ids_ws2 = {str(e.entity_id) for e in entries_ws2}

        assert len(entries_ws1) == 3, entries_ws1
        assert ids_ws1 == {str(req1.id)}, (
            "WS1's audit-entry fetch must not include WS2's requirement "
            "(#572 cross-workspace leak)"
        )
        assert len(entries_ws2) == 1, entries_ws2
        assert ids_ws2 == {str(req2.id)}, (
            "WS2's audit-entry fetch must not include WS1's requirement "
            "(#572 cross-workspace leak)"
        )


class TestFetchAuditEntriesUsesDbLevelEntityIdsFilter:
    """Review finding F1 pin (mutation-test gap): the previous test suite
    proved the *output* of _fetch_audit_entries is workspace-scoped, but not
    *how* — a Python-side post-filter over a truncated tenant-wide page would
    have passed every existing assertion too (that was the actual bug this
    round's F1 fix replaced). Reverting the F1 fix (routing entity_ids into
    AuditQueryFilters instead of building it there and filtering in Python
    afterwards) must fail this test even though every other test stays green.

    Mocks ``audit_query`` directly so no volume of fixture data is needed to
    prove the DB-level filter is what's actually wired up.
    """

    def test_audit_query_receives_workspace_requirement_entity_ids(
        self, two_workspaces
    ):
        tenant, ws1, req1, ws2, req2 = two_workspaces

        with patch("se_metrics.aggregator.audit_query") as mock_audit_query:
            empty_page = MagicMock()
            empty_page.entries = []
            mock_audit_query.return_value = empty_page

            _fetch_audit_entries(
                workspace_id=str(ws1.id), timeframe="P30D", tenant_id=tenant.id
            )

        mock_audit_query.assert_called_once()
        _, kwargs = mock_audit_query.call_args
        filters = kwargs["filters"]

        assert filters.entity_type == "Requirement"
        assert list(filters.entity_ids) == [req1.id], (
            "AuditQueryFilters.entity_ids passed to audit_query() must be "
            "exactly WS1's own Requirement id set (#572 F1) — the DB-level "
            "filter must actually be wired into the query call, not just "
            "computed and then discarded/post-filtered in Python."
        )
        # req2 (WS2's requirement) must never appear in the filter sent to
        # the DB for a WS1 query.
        assert req2.id not in filters.entity_ids


class TestFetchAuditEntriesTenantIsolation:
    """Review finding F5: the source comment claims the workspace-scoped
    Requirement lookup "can't cross the tenant boundary" — pin that with an
    actual cross-tenant test, not just code-review confidence.

    A caller that (by bug or malice) passes a *workspace_id belonging to
    tenant B* together with *tenant_id=tenant A* must get back an empty
    list, never tenant B's data — not just "different values" but an
    explicit, verified empty result.
    """

    def test_workspace_of_other_tenant_yields_no_entries(
        self, tenant, other_tenant
    ):
        TenantContext.set_tenant(other_tenant.id)
        try:
            ws_b, req_b = _make_workspace_with_requirement(
                other_tenant, "Tenant B WS", "Tenant B requirement"
            )
            _write_update_audit_entries(req_b.id, count=5)
        finally:
            TenantContext.clear_tenant()

        # Attempt to read tenant B's workspace while impersonating tenant A.
        entries = _fetch_audit_entries(
            workspace_id=str(ws_b.id), timeframe="P30D", tenant_id=tenant.id
        )

        assert entries == [], (
            "_fetch_audit_entries must return an empty list — not tenant B's "
            "data — when the workspace belongs to a different tenant than "
            "tenant_id (#572 tenant-boundary regression)"
        )


class TestComputeVolatilityWorkspaceIsolation:
    """End-to-end: MetricsAggregator.compute() volatility must differ per
    workspace (only coverage/gaps/risks sources are mocked)."""

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    def test_volatility_is_not_identical_across_workspaces(
        self, mock_coverage, mock_gaps, mock_risks, two_workspaces
    ):
        tenant, ws1, req1, ws2, req2 = two_workspaces
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        TenantContext.set_tenant(tenant.id)
        try:
            agg = MetricsAggregator()
            result_ws1 = agg.compute(workspace_id=str(ws1.id), timeframe="P30D")
            result_ws2 = agg.compute(workspace_id=str(ws2.id), timeframe="P30D")
        finally:
            TenantContext.clear_tenant()

        def _volatility_signature(volatility):
            return (
                volatility.total_changes,
                volatility.total_requirements,
                volatility.avg_changes_per_req,
                tuple(
                    (r.requirement_id, r.change_count)
                    for r in volatility.top10_volatile
                ),
            )

        # The QA-reported symptom: byte-identical volatility blocks.
        assert _volatility_signature(result_ws1.volatility) != _volatility_signature(
            result_ws2.volatility
        ), "volatility must not be identical across workspaces (#572)"

        assert result_ws1.volatility.total_changes == 3
        assert result_ws1.volatility.total_requirements == 1
        assert {
            r.requirement_id for r in result_ws1.volatility.top10_volatile
        } == {str(req1.id)}

        assert result_ws2.volatility.total_changes == 1
        assert result_ws2.volatility.total_requirements == 1
        assert {
            r.requirement_id for r in result_ws2.volatility.top10_volatile
        } == {str(req2.id)}
