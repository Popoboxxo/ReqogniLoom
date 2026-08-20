"""
AuditService (SysEng 2.0 Phase 3) — facade + Adopt/Modify remediation tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3. Covers:

* run_audit() returns findings with a remediation proposal attached and a
  JSON-serialisable shape (the findings-retrieval path the GET endpoint uses).
* Adopt regression (negative -> positive) for every automatic remediation:
  a Phase-2 finding exists, remediate() applies the fix, and the *same* re-run
  no longer reports that finding — proving a correct TraceLink was created.
    - TRACE-P5: deterministic (endpoints from the finding).
    - TRACE-P1: unique-candidate (single StakeholderNeed).
    - TRACE-P2: unique-candidate (single ArchitectureElement).
* The not-automatic path: ambiguous candidates (TRACE-P1 with two needs) and a
  rule with no registered remediation (TRACE-P4) both refuse cleanly
  (ValidationError, no crash).
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.audit_service import AuditService
from application.base import ValidationError
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
from traceability.audit import AuditResult, Finding, Severity
from traceability.audit.registry import TRACE_P1, TRACE_P2, TRACE_P4, TRACE_P5
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Audit Tenant", slug="audit-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="audit-user", email="audit@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Audit-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Audit Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(tenant: Tenant, workspace: Workspace, title: str = "Req") -> Requirement:
    art = _artifact(tenant, workspace, "requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _need(tenant: Tenant, workspace: Workspace, title: str = "Need") -> StakeholderNeed:
    art = _artifact(tenant, workspace, "stakeholder-need")
    return StakeholderNeed.objects.create(tenant=tenant, artifact=art, title=title)


def _arch(tenant: Tenant, workspace: Workspace, title: str = "AE") -> ArchitectureElement:
    art = _artifact(tenant, workspace, "architecture-element")
    return ArchitectureElement.objects.create(tenant=tenant, artifact=art, title=title)


def _link(tenant: Tenant, source: Artifact, target: Artifact, link_type: str) -> TraceLink:
    return TraceLink.objects.create(
        tenant=tenant, source=source, target=target, link_type=link_type
    )


def _findings(report, rule_id):
    return [fv for fv in report.findings if fv.finding.rule_id == rule_id]


# ---------------------------------------------------------------------------
# run_audit / findings-retrieval path
# ---------------------------------------------------------------------------


class TestRunAudit:
    def test_report_is_json_serialisable_with_remediation(self, tenant, workspace, ctx):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            report = AuditService().run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["tier"] == "extended"
        assert "counts" in data and data["counts"]["total"] == len(data["findings"])
        # every finding carries a remediation proposal
        for f in data["findings"]:
            assert "remediation" in f
            assert "automatic" in f["remediation"]
            assert "index" in f

    def test_explicit_tier_minimal_yields_no_findings(self, tenant, workspace, ctx):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            report = AuditService().run_audit(workspace.id, ctx, tier="minimal")
        assert report.findings == []

    def test_resolve_tier_falls_back_to_standard(self, monkeypatch, workspace):
        def _boom(_ws):
            raise RuntimeError("no preset")

        monkeypatch.setattr("presets.services.get_preset", _boom)
        assert AuditService.resolve_tier(str(workspace.id)) == "standard"


# ---------------------------------------------------------------------------
# BUG-15 — /audit/ must not return an unbounded findings list (regression).
# ---------------------------------------------------------------------------


class _FixedEngine:
    """Stub RuleEngine that returns a pre-built, arbitrarily large finding set.

    Avoids needing 1000+ real Requirement/Artifact rows in Postgres just to
    prove the truncation guard — the guard operates purely on the
    ``AuditResult`` the RuleEngine hands back, so a fake engine result is
    sufficient and keeps the test fast.
    """

    def __init__(self, findings: list) -> None:
        self._findings = findings

    def run(self, *, tier, workspace_id, tenant_id, scopes=None) -> AuditResult:
        return AuditResult(tier=tier, findings=list(self._findings))


class TestRunAuditTruncation:
    def test_large_result_set_is_capped_with_truncation_metadata(
        self, tenant, workspace, ctx
    ):
        # TRACE-P4 has no registered remediation (see TestNoAutomaticRemediation
        # above) -> _propose_for_finding short-circuits without a DB roundtrip
        # per finding, keeping this test fast for a 4-figure finding count
        # (mirrors the audit's 300-requirements-no-trace-links stress scenario,
        # which produced 4,440 findings in a single response).
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 700
        findings = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message=f"finding {i}",
                artifact_ids=(),
            )
            for i in range(overflow_count)
        ]

        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["truncated"] is True
        assert data["total_findings_available"] == overflow_count
        assert len(data["findings"]) == AuditService.MAX_REPORT_FINDINGS
        # counts.total must stay consistent with the actually-returned list
        # (the dashboard's live-count badges derive from data["findings"]).
        assert data["counts"]["total"] == AuditService.MAX_REPORT_FINDINGS
        # BUG-15 follow-up M3: the *true* severity totals (pre-cap) must be
        # exposed separately from counts.blockers/counts.warnings (which only
        # describe the returned/capped subset) — every finding here is a
        # BLOCKER, so this must reflect the full overflow count, not the cap.
        assert data["total_blockers_available"] == overflow_count
        assert data["total_warnings_available"] == 0

    def test_small_result_set_is_not_flagged_truncated(self, tenant, workspace, ctx):
        findings = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message="only one",
                artifact_ids=(),
            )
        ]
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["truncated"] is False
        assert data["total_findings_available"] == 1
        assert len(data["findings"]) == 1
        assert data["total_blockers_available"] == 1
        assert data["total_warnings_available"] == 0

    def test_truncation_prioritises_blocker_over_warning_findings(
        self, tenant, workspace, ctx
    ):
        # Mixed severities beyond the cap: every BLOCKER must survive
        # truncation before any WARNING does, since blockers gate baseline
        # creation (application.baseline_facade.BaselineFacade) and must stay
        # visible even when the result set as a whole is capped.
        warnings = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.WARNING,
                message=f"warning {i}",
                artifact_ids=(),
            )
            for i in range(AuditService.MAX_REPORT_FINDINGS)
        ]
        blockers = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message=f"blocker {i}",
                artifact_ids=(),
            )
            for i in range(200)
        ]
        # All 200 blockers sit *after* the 500 warnings in engine order — a
        # naive "keep first N" truncation (N=500) would keep zero blockers.
        findings = warnings + blockers

        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["truncated"] is True
        blocker_count = sum(
            1 for f in data["findings"] if f["severity"] == "blocker"
        )
        warning_count = sum(
            1 for f in data["findings"] if f["severity"] == "warning"
        )
        # Every blocker survives truncation; the remaining cap budget
        # (500 - 200) is filled with warnings.
        assert blocker_count == 200
        assert warning_count == AuditService.MAX_REPORT_FINDINGS - 200
        # Pre-cap totals must reflect the full 500/200 split, not the capped one.
        assert data["total_blockers_available"] == 200
        assert data["total_warnings_available"] == AuditService.MAX_REPORT_FINDINGS

    def test_truncation_keeps_original_indices_in_ascending_display_order(
        self, tenant, workspace, ctx
    ):
        # BUG-15 code review L8: the double-sort (severity-first for the cap
        # decision, then back to original index for display) is the trickiest
        # part of the truncation logic and needs its own direct proof: kept
        # findings must (a) carry their original position in the full,
        # pre-cap engine run (not be renumbered 0..N-1) and (b) be rendered
        # back in ascending index order, not grouped by severity.
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 50
        # Every 10th finding (indices 0, 10, 20, ...) is a BLOCKER; the rest
        # are WARNING. With only 50 blockers (well under the cap), the kept
        # set is: every blocker + enough warnings to reach the cap.
        findings = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER if i % 10 == 0 else Severity.WARNING,
                message=f"finding {i}",
                artifact_ids=(),
            )
            for i in range(overflow_count)
        ]

        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["truncated"] is True
        kept_indices = [f["index"] for f in data["findings"]]

        # (a) every blocker's original index (0, 10, 20, ..., 490) is present
        # — none were pushed out by the cap.
        blocker_indices = {i for i in range(overflow_count) if i % 10 == 0}
        assert blocker_indices <= set(kept_indices)
        # (b) display order is strictly ascending by original index, not
        # grouped by severity (which is what the severity-sort pass alone
        # would produce without the re-sort back to index order).
        assert kept_indices == sorted(kept_indices)
        # No index is renumbered/duplicated — every kept index is unique and
        # within the full pre-cap run's index range.
        assert len(set(kept_indices)) == len(kept_indices)
        assert all(0 <= i < overflow_count for i in kept_indices)


# ---------------------------------------------------------------------------
# #622 — limit/offset lets a caller page past MAX_REPORT_FINDINGS instead of
# only ever seeing the default BLOCKER-preferred truncated view.
# ---------------------------------------------------------------------------


class TestRunAuditPagination:
    def _findings(self, count: int) -> list:
        return [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message=f"finding {i}",
                artifact_ids=(),
            )
            for i in range(count)
        ]

    def test_no_limit_preserves_default_truncation_behaviour(
        self, tenant, workspace, ctx
    ):
        """limit=None (the default) must be byte-for-byte the pre-#622 shape."""
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 50
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(self._findings(overflow_count)))
            report = svc.run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["truncated"] is True
        assert data["offset"] == 0
        assert len(data["findings"]) == AuditService.MAX_REPORT_FINDINGS

    def test_limit_returns_a_sequential_window(self, tenant, workspace, ctx):
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 50
        findings = self._findings(overflow_count)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(
                workspace.id, ctx, tier="extended", limit=10, offset=0
            )

        data = report.to_dict()
        assert len(data["findings"]) == 10
        assert data["offset"] == 0
        assert data["truncated"] is True, "more findings exist past this window"
        assert [f["message"] for f in data["findings"]] == [
            f"finding {i}" for i in range(10)
        ]

    def test_limit_with_offset_returns_the_next_window(self, tenant, workspace, ctx):
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 50
        findings = self._findings(overflow_count)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(
                workspace.id, ctx, tier="extended", limit=10, offset=10
            )

        data = report.to_dict()
        assert data["offset"] == 10
        assert [f["message"] for f in data["findings"]] == [
            f"finding {i}" for i in range(10, 20)
        ]

    def test_last_window_is_not_flagged_truncated(self, tenant, workspace, ctx):
        findings = self._findings(25)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(
                workspace.id, ctx, tier="extended", limit=10, offset=20
            )

        data = report.to_dict()
        assert len(data["findings"]) == 5
        assert data["truncated"] is False, "no more findings past this window"

    def test_limit_is_capped_at_max_report_findings(self, tenant, workspace, ctx):
        overflow_count = AuditService.MAX_REPORT_FINDINGS + 700
        findings = self._findings(overflow_count)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(
                workspace.id,
                ctx,
                tier="extended",
                limit=AuditService.MAX_REPORT_FINDINGS + 500,
                offset=0,
            )

        # An oversized limit request never bypasses the payload-size cap.
        assert len(report.to_dict()["findings"]) == AuditService.MAX_REPORT_FINDINGS

    def test_offset_past_the_end_returns_an_empty_window(self, tenant, workspace, ctx):
        findings = self._findings(5)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            report = svc.run_audit(
                workspace.id, ctx, tier="extended", limit=10, offset=100
            )

        data = report.to_dict()
        assert data["findings"] == []
        assert data["truncated"] is False


# ---------------------------------------------------------------------------
# BUG-15 code review H1 (blocker) — Adopt-verification must never consult the
# capped run_audit() report; a finding outside the cap must not read as
# resolved.
# ---------------------------------------------------------------------------


class TestFindingStillPresentIgnoresTheCap:
    def test_target_outside_the_cap_is_still_detected_as_present(
        self, tenant, workspace, ctx
    ):
        # Regression for the H1 finding: _finding_still_present() used to
        # call run_audit() (the capped, dashboard-facing view). Pad the
        # engine result with enough BLOCKER findings to fill the cap, so a
        # single WARNING "target" finding would be entirely dropped by
        # run_audit()'s blocker-priority truncation — if remediate()'s
        # verification step used that capped view, a still-present finding
        # would silently read as resolved.
        target = Finding(
            rule_id=TRACE_P4,
            severity=Severity.WARNING,
            message="the real target",
            artifact_ids=("target-artifact",),
        )
        padding = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message=f"padding {i}",
                artifact_ids=(),
            )
            for i in range(AuditService.MAX_REPORT_FINDINGS)
        ]
        engine_result = [target] + padding
        assert len(engine_result) > AuditService.MAX_REPORT_FINDINGS

        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(engine_result))

            # Sanity check: this padding really does make run_audit() drop
            # the target — otherwise the test would not exercise the bug.
            capped_report = svc.run_audit(workspace.id, ctx, tier="extended")
            assert not any(
                fv.finding.rule_id == target.rule_id
                and frozenset(fv.finding.artifact_ids)
                == frozenset(target.artifact_ids)
                for fv in capped_report.findings
            )

            still_present = svc._finding_still_present(
                target, str(workspace.id), ctx, scope=None, scope_artifact_id=None
            )

        assert still_present is True


# ---------------------------------------------------------------------------
# TRACE-P5 — deterministic Adopt regression (negative -> positive)
# ---------------------------------------------------------------------------


class TestRemediateTraceP5:
    def test_adopt_creates_derives_from_and_clears_finding(self, tenant, workspace, ctx):
        with _active(tenant):
            parent = _requirement(tenant, workspace, "Parent")
            child = _requirement(tenant, workspace, "Child")
            # decomposes parent -> child, but NO matching derives-from child -> parent
            _link(tenant, parent.artifact, child.artifact, LinkType.DECOMPOSES.value)

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p5 = _findings(before, TRACE_P5)
            assert len(p5) == 1
            finding = p5[0].finding
            assert p5[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P5,
                artifact_ids=list(finding.artifact_ids),
            )
            assert result.applied is True
            assert result.finding_resolved is True
            assert result.created_link_id

            # The derives-from link now exists: child -> parent.
            assert TraceLink.objects.filter(
                source_id=child.artifact_id,
                target_id=parent.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P5) == []


# ---------------------------------------------------------------------------
# TRACE-P1 — unique-candidate Adopt + ambiguous refusal
# ---------------------------------------------------------------------------


class TestRemediateTraceP1:
    def test_adopt_links_root_to_unique_need(self, tenant, workspace, ctx):
        with _active(tenant):
            need = _need(tenant, workspace, "The Need")
            root = _requirement(tenant, workspace, "Root")

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p1 = _findings(before, TRACE_P1)
            assert len(p1) == 1
            assert p1[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P1,
                artifact_ids=list(p1[0].finding.artifact_ids),
            )
            assert result.applied is True and result.finding_resolved is True
            assert TraceLink.objects.filter(
                source_id=root.artifact_id,
                target_id=need.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P1) == []

    def test_ambiguous_needs_refuse_automatic_remediation(self, tenant, workspace, ctx):
        with _active(tenant):
            _need(tenant, workspace, "Need A")
            _need(tenant, workspace, "Need B")
            root = _requirement(tenant, workspace, "Root")

            svc = AuditService()
            report = svc.run_audit(workspace.id, ctx, tier="extended")
            p1 = _findings(report, TRACE_P1)
            assert len(p1) == 1
            assert p1[0].remediation.automatic is False

            with pytest.raises(ValidationError):
                svc.remediate(
                    workspace.id,
                    ctx,
                    rule_id=TRACE_P1,
                    artifact_ids=list(p1[0].finding.artifact_ids),
                )


# ---------------------------------------------------------------------------
# TRACE-P2 — unique-candidate Adopt (allocated-to)
# ---------------------------------------------------------------------------


class TestRemediateTraceP2:
    def test_adopt_allocates_to_unique_architecture(self, tenant, workspace, ctx):
        with _active(tenant):
            arch = _arch(tenant, workspace, "The System")
            req = _requirement(tenant, workspace, "Req")

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p2 = _findings(before, TRACE_P2)
            assert len(p2) == 1
            assert p2[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P2,
                artifact_ids=list(p2[0].finding.artifact_ids),
            )
            assert result.applied is True and result.finding_resolved is True
            assert TraceLink.objects.filter(
                source_id=req.artifact_id,
                target_id=arch.artifact_id,
                link_type=LinkType.ALLOCATED_TO.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P2) == []


# ---------------------------------------------------------------------------
# Not-automatic path — rule without a registered remediation
# ---------------------------------------------------------------------------


class TestNoAutomaticRemediation:
    def test_trace_p4_has_no_auto_fix_and_refuses(self, tenant, workspace, ctx):
        with _active(tenant):
            root = _arch(tenant, workspace, "System")
            child = _arch(tenant, workspace, "Sub")
            child.parent = root
            child.save(update_fields=["parent"])
            # Make the parent dangling: soft-delete it -> TRACE-P4 fires.
            # ArchitectureElement has no status mirror (Phase 0) — the
            # soft-delete state lives only in WorkflowItemState, written by
            # workflow.services.outdate(); the dead `lifecycle_status` column
            # is never touched, so flipping it directly (as this test used to)
            # no longer has any effect on "active" detection.
            from workflow.services import create_default_workflow, outdate

            create_default_workflow(
                workspace_id=workspace.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=tenant.id,
            )
            outdate(
                item_id=root.id,
                item_type="ArchitectureElement",
                workspace_id=workspace.id,
                ctx=ctx,
                reason="test soft-delete",
            )

            svc = AuditService()
            report = svc.run_audit(workspace.id, ctx, tier="extended")
            p4 = _findings(report, TRACE_P4)
            assert len(p4) == 1
            assert p4[0].remediation.automatic is False
            assert "manual" in p4[0].remediation.reason.lower()

            with pytest.raises(ValidationError):
                svc.remediate(
                    workspace.id,
                    ctx,
                    rule_id=TRACE_P4,
                    artifact_ids=list(p4[0].finding.artifact_ids),
                )
