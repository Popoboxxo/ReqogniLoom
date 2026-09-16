"""Per-blocker SE-Auditor gate waivers and the hardened override policy (GH-821).

The baseline gate used to offer exactly one exit: a single ``override_reason``
that waived *every* BLOCKER with one sentence (GH-513). Issue #821 is the
follow-up — a workspace with 47 findings could not accept three deviations
without also accepting the other 44 in the same breath, and the one lever it did
have accepted ``len(reason) >= 10``, i.e. ten characters of anything.

Three layers are covered here:

  * the waiver flow — matching against the findings the auditor actually
    reported, per-finding mandatory justification, persistence, and the
    "unwaived findings still block" promise;
  * the hardened reason policy — a length check replaced by a content check
    that a padding string or a copy-pasted rule-id list cannot pass;
  * the audit trail — one ``baseline.waiver_create`` entry per newly
    granted waiver plus the ``baseline.create`` summary naming the suppression.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.audit_service import AuditService
from application.base import (
    BaselineGateBlockedError,
    PermissionDeniedError,
    ValidationError,
)
from application.baseline_facade import (
    MIN_OVERRIDE_REASON_LENGTH,
    BaselineFacade,
    _validate_gate_reason,
)
from auth_tenancy.context import AuthContext
from baseline.models import BaselineGateWaiver
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import AuditScope, Finding, Severity

pytestmark = pytest.mark.django_db


def _make_ctx(*, roles=("admin",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
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
    return Tenant.objects.create(name="gh821-tenant", slug=f"gh821-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant,
            name=f"gh821-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
    finally:
        TenantContext.clear_tenant()


def _gate_patches(*, findings, build_result=None):
    """The mock set every wiring test in this module shares."""
    return (
        patch("application.baseline_facade.TenantContext"),
        patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
        patch.object(AuditService, "blocking_findings", return_value=findings),
        patch(
            "baseline.services.build",
            return_value=build_result or uuid.uuid4(),
        ),
        patch("application.baseline_facade.ServiceBase._emit_event"),
        patch("application.baseline_facade.ServiceBase._audit"),
    )


# ---------------------------------------------------------------------------
# Basic waiver flow
# ---------------------------------------------------------------------------


class TestPerBlockerWaiver:
    def test_waiving_every_finding_builds_the_baseline(self, tenant, workspace):
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
                name="gh821-waived",
                ctx=ctx,
                waived_findings=[
                    _waiver("TRACE-P1"),
                    _waiver("VERIF-P8", ("art-2",)),
                ],
            )

        assert result == baseline_id
        mock_build.assert_called_once()

        rows = BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)
        assert rows.count() == 2
        by_rule = {row.rule_id: row for row in rows}
        assert set(by_rule) == {"TRACE-P1", "VERIF-P8"}
        assert "tracked in GH-821" in by_rule["TRACE-P1"].reason
        assert by_rule["TRACE-P1"].artifact_ids == ["art-1"]
        assert by_rule["TRACE-P1"].granted_by == str(ctx.user_id)

    def test_unwaived_findings_still_block(self, tenant, workspace):
        """A waiver is not an override: it must not open the gate for the rest."""
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
                    name="gh821-partial",
                    ctx=ctx,
                    waived_findings=[_waiver("TRACE-P1")],
                )

        message = str(exc_info.value)
        assert "2 blocking finding(s)" in message
        assert "TRACE-P2" in message and "VERIF-P8" in message
        assert "TRACE-P1" not in message
        # Both exits are named, so a client that wants the coarse one can take it.
        assert "waived_findings" in message and "override_reason" in message
        mock_build.assert_not_called()

    def test_waiver_for_a_non_blocking_finding_is_rejected(self, tenant, workspace):
        """Accepting a deviation the auditor is not reporting is refused.

        Storing it would silently suppress that finding if it ever appeared —
        the opposite of what a waiver is for.
        """
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker("TRACE-P1")])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(ValidationError) as exc_info:
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gh821-unknown",
                    ctx=ctx,
                    waived_findings=[_waiver("CONS-P11", ("other-art",))],
                )

        assert "CONS-P11" in str(exc_info.value)
        assert not isinstance(exc_info.value, BaselineGateBlockedError)
        mock_build.assert_not_called()
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_persisted_waiver_suppresses_later_builds(self, tenant, workspace):
        """A granted waiver is durable, not a per-request incantation (GH-821)."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1")]

        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-first",
                ctx=ctx,
                waived_findings=[_waiver("TRACE-P1")],
            )

        # Second build, same findings, no waivers in the request.
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)
        with p1, p2, p3, p4 as mock_build, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-second",
                ctx=ctx,
            )

        mock_build.assert_called_once()

    def test_editor_may_not_grant_a_waiver(self, tenant, workspace):
        """Accepting a compliance deviation stays an approval act."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(PermissionDeniedError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gh821-editor",
                    ctx=ctx,
                    waived_findings=[_waiver()],
                )

        mock_build.assert_not_called()
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_waiver_on_a_clean_workspace_is_inert(self, tenant, workspace):
        """Nothing is reported, so nothing is stored (retry-friendly)."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-clean",
                ctx=ctx,
                waived_findings=[_waiver()],
            )

        mock_build.assert_called_once()
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_global_override_and_per_finding_waivers_coexist(self, tenant, workspace):
        """Both levers record their own decision instead of collapsing into one."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [
            _blocker("TRACE-P1"),
            _blocker("TRACE-P2", ("art-2",)),
        ]
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)

        with p1, p2, p3, p4 as mock_build, p5, p6 as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-mixed",
                ctx=ctx,
                description="Release candidate",
                waived_findings=[_waiver("TRACE-P1")],
                override_reason="Remaining trace finding accepted for the beta cut.",
            )

        details = mock_audit.call_args.kwargs["details"]
        assert details["suppressed_blocker_count"] == 1
        assert details["suppressed_rule_ids"] == ["TRACE-P1"]
        assert details["audit_gate_override"] is True
        assert details["waived_rule_ids"] == ["TRACE-P2"]

        description = mock_build.call_args.kwargs["description"]
        assert description.startswith("Release candidate")
        assert "[SE-Auditor waiver]" in description
        assert "[SE-Auditor override]" in description

    def test_each_new_waiver_gets_its_own_audit_entry(self, tenant, workspace):
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        findings = [_blocker("TRACE-P1"), _blocker("VERIF-P8", ("art-2",))]
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=findings)

        with p1, p2, p3, p4, p5, p6 as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-audited",
                ctx=ctx,
                waived_findings=[
                    _waiver("TRACE-P1"),
                    _waiver("VERIF-P8", ("art-2",)),
                ],
            )

        waiver_entries = [
            call
            for call in mock_audit.call_args_list
            if call.kwargs.get("operation") == "baseline.waiver_create"
        ]
        assert len(waiver_entries) == 2
        assert {c.kwargs["entity_type"] for c in waiver_entries} == {
            "BaselineGateWaiver"
        }
        assert {
            c.kwargs["details"]["rule_id"] for c in waiver_entries
        } == {"TRACE-P1", "VERIF-P8"}
        assert all("tracked in GH-821" in c.kwargs["change_reason"] for c in waiver_entries)

    def test_repeat_waiver_is_idempotent(self, tenant, workspace):
        """Re-sending a waiver must not duplicate rows or justifications."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])
        with p1, p2, p3, p4, p5, p6:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-repeat-1",
                ctx=ctx,
                waived_findings=[_waiver()],
            )
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])
        with p1, p2, p3, p4, p5, p6 as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-repeat-2",
                ctx=ctx,
                waived_findings=[
                    _waiver(reason="A different justification on the second attempt.")
                ],
            )

        assert (
            BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id).count() == 1
        )
        row = BaselineGateWaiver.unscoped.get(workspace_id=workspace.id)
        assert "tracked in GH-821" in row.reason
        assert not [
            call
            for call in mock_audit.call_args_list
            if call.kwargs.get("operation") == "baseline.waiver_create"
        ]


# ---------------------------------------------------------------------------
# Hardened reason policy
# ---------------------------------------------------------------------------


class TestHardenedReasonPolicy:
    @pytest.mark.parametrize(
        "reason",
        [
            "",
            "   ",
            "ok",
            "fix later",
            "a" * (MIN_OVERRIDE_REASON_LENGTH + 5),  # length-only placeholder
            "waiver waiver waiver waiver",  # one token repeated
            "TRACE-P1 TRACE-P2 TRACE-P3 TRACE-P4",  # echoes the verdict
            "12345678901234567890",  # no readable word
        ],
    )
    def test_a_placeholder_is_not_a_justification(self, reason):
        with pytest.raises(ValidationError):
            _validate_gate_reason(reason, label="waiver justification")

    @pytest.mark.parametrize(
        "reason",
        [
            "Open trace findings accepted for the beta cut (GH-821).",
            "We accept the risk for the beta cut.",
            "Accepted deviation, see review protocol 2026-08-15.",
        ],
    )
    def test_a_real_sentence_passes(self, reason):
        assert _validate_gate_reason(reason, label="waiver justification") == reason

    def test_override_reason_is_validated_by_the_same_policy(self, tenant, workspace):
        """The override path must not keep the weaker GH-513 bar."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(ValidationError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gh821-weak-override",
                    ctx=ctx,
                    override_reason="aaaaaaaaaaaaaaaaaaaa",
                )

        mock_build.assert_not_called()

    def test_waiver_reason_placeholder_is_rejected(self, tenant, workspace):
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(ValidationError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gh821-weak-waiver",
                    ctx=ctx,
                    waived_findings=[_waiver(reason="fix fix fix fix")],
                )

        mock_build.assert_not_called()

    @pytest.mark.parametrize(
        "payload",
        [
            "not-a-list",
            [{"artifact_ids": ["art-1"], "reason": "A perfectly fine sentence."}],
            [{"rule_id": "TRACE-P1", "reason": "A perfectly fine sentence.", "artifact_ids": "art-1"}],
            [
                {
                    "rule_id": "TRACE-P1",
                    "artifact_ids": ["art-1"],
                    "reason": "",
                }
            ],
        ],
    )
    def test_malformed_waiver_payloads_are_validation_errors(
        self, tenant, workspace, payload
    ):
        """No AttributeError/TypeError may leak out of the gate as a 500."""
        facade = BaselineFacade()
        ctx = _make_ctx(tenant_id=tenant.id)
        p1, p2, p3, p4, p5, p6 = _gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, p6:
            with pytest.raises(ValidationError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=workspace.id,
                    name="gh821-malformed",
                    ctx=ctx,
                    waived_findings=payload,
                )

        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# End-to-end against the real RuleEngine
# ---------------------------------------------------------------------------


class TestWaiverEndToEnd:
    """The mocked tests above pin the wiring; this one pins the behaviour.

    Real Extended preset, real RuleEngine, real persistence, real audit log —
    the same broken graph shape the QS instance reported (#821: "47 blockers").
    """

    @pytest.fixture(autouse=True)
    def _clear_preset_cache(self):
        yield
        from presets import gate

        with gate._cache_lock:
            gate._tier_cache.clear()

    def _ctx(self, tenant: Tenant) -> AuthContext:
        return AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )

    def _orphan_requirement(self, tenant: Tenant, workspace: Workspace) -> None:
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="requirement"
            )
            Requirement.objects.create(
                tenant=tenant, artifact=artifact, title="Orphan requirement"
            )
        finally:
            TenantContext.clear_tenant()

    def test_real_findings_can_be_waived_one_by_one(self, tenant, workspace):
        self._orphan_requirement(tenant, workspace)
        ctx = self._ctx(tenant)

        findings = AuditService().blocking_findings(
            workspace.id, ctx, scopes=[AuditScope("project")]
        )
        assert findings, "expected the real auditor to report blockers"

        baseline_id = BaselineFacade().create_baseline(
            scope="project",
            workspace_id=workspace.id,
            name="gh821-e2e",
            ctx=ctx,
            waived_findings=[
                {
                    "rule_id": finding.rule_id,
                    "artifact_ids": list(finding.artifact_ids),
                    "reason": (
                        f"Accepted deviation for {finding.rule_id} in the "
                        "gh821 regression test."
                    ),
                }
                for finding in findings
            ],
        )

        assert baseline_id is not None

        TenantContext.set_tenant(tenant.id)
        try:
            rows = BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)
            assert rows.count() == len(findings)
            assert {
                row.rule_id for row in rows
            } == {finding.rule_id for finding in findings}

            # The durable audit trail: one entry per granted waiver, with the
            # justification in the (real, persisted) change_reason column.
            from audit.models import AuditEntry

            waiver_entries = AuditEntry.unscoped.filter(
                op="baseline.waiver_create",
                entity_type="BaselineGateWaiver",
                tenant_id=tenant.id,
            )
            assert waiver_entries.count() == len(findings)
            assert all(entry.change_reason for entry in waiver_entries)

            from baseline.models import BaselineSnapshot

            snapshot = BaselineSnapshot.objects.get(id=baseline_id)
            assert "[SE-Auditor waiver]" in snapshot.description
            assert "[SE-Auditor override]" not in snapshot.description
        finally:
            TenantContext.clear_tenant()

    def test_unwaived_real_findings_still_block(self, tenant, workspace):
        self._orphan_requirement(tenant, workspace)
        ctx = self._ctx(tenant)

        findings = AuditService().blocking_findings(
            workspace.id, ctx, scopes=[AuditScope("project")]
        )
        assert len(findings) >= 2, "expected at least two blockers to leave one out"

        with pytest.raises(BaselineGateBlockedError) as exc_info:
            BaselineFacade().create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="gh821-e2e-partial",
                ctx=ctx,
                waived_findings=[
                    {
                        "rule_id": findings[0].rule_id,
                        "artifact_ids": list(findings[0].artifact_ids),
                        "reason": "Accepted deviation for the first finding.",
                    }
                ],
            )

        assert "blocking finding(s)" in str(exc_info.value)
