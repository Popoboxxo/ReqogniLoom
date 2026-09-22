"""#569 — gate semantics: suppressed ≠ blocker, reuse is recorded, expiry re-blocks.

Pins the gate half of the specification (revision 3, APPROVED):

* **AC-569-08** — a suppressed BLOCKER does not block; unwaived ones still do.
* **AC-569-COMPAT(c)** — switching the matcher from key-set membership to
  ``suppression_applies`` does not break a persisted GH-821 row in its
  production-real form (``scope="project"``, ``scope_artifact_id=""``).
* **AC-569-19** — a **reused** waiver is reported in ``matched_waiver_ids``
  while the legacy ``waiver_ids`` stays empty.
* **AC-569-10** — an expired waiver re-blocks the build.
* **AC-569-09** — the immutable baseline description names the matched ids and
  the ``baseline.create`` details carry the suppression trail.

``details`` persistence caveat: the v1 ``AuditLogWriter`` drops ``details`` on
this branch (no column; ``log_write`` ignores it) and a writer rebuild is an
explicit Non-Goal (#569 §7), so the details are asserted on the intercepted
``_audit`` call — the same pattern the GH-821 suite already uses.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from application.audit_service import AuditService
from application.base import BaselineGateBlockedError
from application.baseline_facade import BaselineFacade
from baseline.models import BaselineGateWaiver
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import Finding, Severity

pytestmark = pytest.mark.django_db


def _make_ctx(*, roles=("admin",), tenant_id=None, user_id=None):
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    # A real bearer context has scope "write" (== the ADMIN tier); keep that so
    # the #865 scope gate behaves as in production.
    ctx.scope = "write"
    return ctx


def _blocker(rule_id: str = "TRACE-P1", artifact_ids=("art-1",)) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.BLOCKER,
        message="Root Requirement has no derives-from link.",
        artifact_ids=artifact_ids,
    )


def _waiver(rule_id: str = "TRACE-P1", artifact_ids=("art-1",), reason=None):
    return {
        "rule_id": rule_id,
        "artifact_ids": list(artifact_ids),
        "reason": reason or f"Accepted deviation for {rule_id}, tracked in GH-821.",
    }


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="gate-569", slug=f"gate-569-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant,
            name=f"gate-569-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
    finally:
        TenantContext.clear_tenant()


def _gate_patches(*, findings, build_result=None):
    return (
        patch("application.baseline_facade.TenantContext"),
        patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
        patch.object(AuditService, "blocking_findings", return_value=findings),
        patch("baseline.services.build", return_value=build_result or uuid.uuid4()),
        patch("application.baseline_facade.ServiceBase._emit_event"),
        patch("application.baseline_facade.ServiceBase._audit"),
    )


def _rows(workspace):
    return BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)


# ---------------------------------------------------------------------------
# AC-569-08 / AC-569-10 — suppressed does not block; expired re-blocks
# ---------------------------------------------------------------------------


class TestGateDecision:
    def test_suppressed_blocker_does_not_block_but_is_recorded(
        self, tenant, workspace
    ):
        """AC-569-08 / V12: the suppressed one is out, the other two remain."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [
            _blocker("TRACE-P1"),
            _blocker("TRACE-P2", ("art-2",)),
            _blocker("VERIF-P8", ("art-3",)),
        ]

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(BaselineGateBlockedError) as exc_info:
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gate-569-partial",
                    ctx=ctx,
                    waived_findings=[_waiver("TRACE-P1")],
                )

        message = str(exc_info.value)
        assert "2 blocking finding(s)" in message
        assert "TRACE-P2" in message and "VERIF-P8" in message
        assert "TRACE-P1" not in message
        mock_build.assert_not_called()
        # A blocked build rolls its transaction back, so neither the baseline nor
        # the grant persists — the durable record exists once the build succeeds
        # (see test_all_suppressed_builds_the_baseline) or via suppress_finding.
        assert _rows(workspace).count() == 0

    def test_all_suppressed_builds_the_baseline(self, tenant, workspace):
        """AC-569-08: when every blocker is suppressed the build proceeds."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1"), _blocker("VERIF-P8", ("art-2",))]
        baseline_id = uuid.uuid4()

        p1, p2, p3, p4, p5, p6 = _gate_patches(
            findings=findings, build_result=baseline_id
        )
        with p1, p2, p3, p4 as mock_build, p5, p6:
            result = facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gate-569-all",
                ctx=ctx,
                waived_findings=[
                    _waiver("TRACE-P1"),
                    _waiver("VERIF-P8", ("art-2",)),
                ],
            )

        assert result == baseline_id
        mock_build.assert_called_once()
        # The successful build durably records both decisions (rows persist).
        assert _rows(workspace).count() == 2
        assert {row.rule_id for row in _rows(workspace)} == {"TRACE-P1", "VERIF-P8"}

    def test_expired_waiver_re_blocks(self, tenant, workspace):
        """AC-569-10 / V14: an expired waiver no longer suppresses."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        BaselineGateWaiver.unscoped.create(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            rule_id="TRACE-P1",
            finding_key="TRACE-P1\x1fart-1",
            artifact_ids=["art-1"],
            scope="project",
            scope_artifact_id="",
            reason="Expired acceptance, superseded by the re-audit.",
            granted_by=str(ctx.user_id),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker("TRACE-P1")])
        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(BaselineGateBlockedError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gate-569-expired",
                    ctx=ctx,
                )
        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# AC-569-COMPAT(c) / V3 — matcher switch keeps GH-821 rows alive
# ---------------------------------------------------------------------------


class TestGh821CompatibilityAtTheGate:
    def test_pre_569_persisted_project_stamped_waiver_still_suppresses_after_matcher_switch(
        self, tenant, workspace
    ):
        """AC-569-COMPAT(c) / V3: the production-real row form keeps matching.

        The row is created by a **real gate build** (first ``create_baseline``
        with ``waived_findings``), so it carries exactly the production stamp
        ``scope="project"``/``scope_artifact_id=""`` (``finding.scope or scope``).
        A later build that does **not** resend the waiver must still treat the
        finding as suppressed — R2b.

        mutation-probe: removing the R2a/R2b clauses from
        ``baseline.waivers.suppression_applies`` makes this test red (a
        ``scope="project"`` row would no longer suppress a scope-agnostic
        finding).
        """
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1")]

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gate-569-first",
                ctx=ctx,
                waived_findings=[_waiver("TRACE-P1")],
            )

        row = _rows(workspace).get()
        assert row.scope == "project"
        assert row.scope_artifact_id == ""

        # Second build: same finding, waiver NOT resent.
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4, p5, p6:
            outcome = facade._enforce_audit_gate(
                workspace_id=workspace.id,
                scope="project",
                document_id=None,
                ctx=ctx,
            )

        assert [f.rule_id for f in outcome.suppressed] == ["TRACE-P1"]
        assert outcome.matched_waiver_ids == (row.id,)


# ---------------------------------------------------------------------------
# AC-569-19 / AC-569-09 — reuse is reported in the metadata
# ---------------------------------------------------------------------------


class TestReusedWaiverMetadata:
    def test_reused_waiver_is_reported_in_matched_ids(self, tenant, workspace):
        """AC-569-19 / V23: ``waiver_ids`` stays empty, ``matched_waiver_ids`` names the row."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1")]

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gate-569-reuse-1",
                ctx=ctx,
                waived_findings=[_waiver("TRACE-P1")],
            )
        row = _rows(workspace).get()

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4 as mock_build, p5, p6 as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gate-569-reuse-2",
                ctx=ctx,
            )

        create_calls = [
            call
            for call in mock_audit.call_args_list
            if call.kwargs.get("operation") == "baseline.create"
        ]
        assert len(create_calls) == 1
        details = create_calls[0].kwargs["details"]
        assert details["waiver_ids"] == []
        assert details["matched_waiver_ids"] == [str(row.id)]
        assert details["suppressed_blocker_count"] == 1

        description = mock_build.call_args.kwargs["description"]
        assert "[SE-Auditor waiver]" in description
        assert str(row.id) in description

    def test_baseline_create_details_carry_the_suppression_trail(
        self, tenant, workspace
    ):
        """AC-569-09: the ``baseline.create`` details carry the suppression trail.

        Asserted on the intercepted ``_audit`` call: the v1 writer drops
        ``details`` (see the module docstring).
        """
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1")]

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4, p5, p6 as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gate-569-trail",
                ctx=ctx,
                waived_findings=[_waiver("TRACE-P1")],
            )

        create_calls = [
            call
            for call in mock_audit.call_args_list
            if call.kwargs.get("operation") == "baseline.create"
        ]
        assert len(create_calls) == 1
        details = create_calls[0].kwargs["details"]
        assert details["suppressed_blocker_count"] == 1
        assert details["suppressed_finding_keys"] == ["TRACE-P1\x1fart-1"]
        assert len(details["waiver_ids"]) == 1
        assert details["matched_waiver_ids"] == details["waiver_ids"]
