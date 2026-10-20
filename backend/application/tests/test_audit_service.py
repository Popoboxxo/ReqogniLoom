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
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from application.audit_service import AuditService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from baseline.waivers import SuppressionRecord, finding_key
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
from traceability.audit import AuditResult, Finding, Severity
from traceability.audit.finding_filters import finding_matches
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
        return make_workspace(tenant, name="Audit-WS")


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
    art = _artifact(tenant, workspace, "Requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _need(tenant: Tenant, workspace: Workspace, title: str = "Need") -> StakeholderNeed:
    art = _artifact(tenant, workspace, "StakeholderNeed")
    return StakeholderNeed.objects.create(tenant=tenant, artifact=art, title=title)


def _arch(tenant: Tenant, workspace: Workspace, title: str = "AE") -> ArchitectureElement:
    art = _artifact(tenant, workspace, "ArchitectureElement")
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
        # #1382: counts is the ground truth, page_counts the returned window.
        assert data["counts"]["total"] == data["total_findings_available"]
        assert data["page_counts"]["total"] == len(data["findings"])
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

    def run(
        self, *, tier, workspace_id, tenant_id, scopes=None, include_proposal_links=True
    ) -> AuditResult:
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
        # #1382: counts is the ground truth across the full run (a badge must
        # show the real total, not the cap) ...
        assert data["counts"]["total"] == overflow_count
        # ... while page_counts describes what is actually in `findings`.
        assert data["page_counts"]["total"] == AuditService.MAX_REPORT_FINDINGS
        # BUG-15 follow-up M3: the *true* severity totals (pre-cap) must be
        # exposed separately from page_counts.blockers/page_counts.warnings
        # (which only describe the returned/capped subset) — every finding here
        # is a BLOCKER, so this must reflect the full overflow count, not the
        # cap.
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
# #1382 — `counts` is the ground truth over the full run, `page_counts` the
# returned window, `next_offset` the cursor for a sequential walk.
# ---------------------------------------------------------------------------


class TestRunAuditPaginationCounts:
    """#1382 count semantics + cursor on a deliberately small cap.

    ``MAX_REPORT_FINDINGS`` is monkeypatched to 5 so a 12-finding engine result
    exercises multiple windows without large fixtures. ``TRACE-P4`` has no
    registered remediation, so each finding is cheap to build.
    """

    WINDOW = 5
    TOTAL = 12

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

    def _pages(
        self, monkeypatch, tenant, workspace, ctx, *, offsets: tuple[int, ...]
    ) -> list[dict]:
        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", self.WINDOW)
        findings = self._findings(self.TOTAL)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            return [
                svc.run_audit(
                    workspace.id,
                    ctx,
                    tier="extended",
                    limit=self.WINDOW,
                    offset=start,
                ).to_dict()
                for start in offsets
            ]

    def test_windows_are_disjoint_and_complete_with_a_cursor(
        self, monkeypatch, tenant, workspace, ctx
    ):
        pages = self._pages(
            monkeypatch, tenant, workspace, ctx, offsets=(0, 5, 10)
        )

        messages = [f["message"] for page in pages for f in page["findings"]]
        assert messages == [f"finding {i}" for i in range(self.TOTAL)]
        assert len(set(messages)) == self.TOTAL, "windows must not overlap"
        assert [len(page["findings"]) for page in pages] == [5, 5, 2]
        assert [page["next_offset"] for page in pages] == [5, 10, None]
        assert [page["truncated"] for page in pages] == [True, True, False]

    def test_counts_stay_ground_truth_across_every_window(
        self, monkeypatch, tenant, workspace, ctx
    ):
        pages = self._pages(
            monkeypatch, tenant, workspace, ctx, offsets=(0, 5, 10)
        )

        for page in pages:
            counts = page["counts"]
            assert counts["total"] == self.TOTAL
            assert counts["total"] == page["total_findings_available"]
            assert counts["blockers"] == self.TOTAL
            assert counts["warnings"] == 0
            assert counts["suppressed"] == 0
            assert counts["suppressed_blockers"] == 0

            page_counts = page["page_counts"]
            assert page_counts["total"] == len(page["findings"])
            assert page_counts["blockers"] == len(page["findings"])
            # Window counters keep the unconditional binary-severity identity.
            assert (
                page_counts["blockers"] + page_counts["warnings"]
                == page_counts["total"]
            )

    def test_default_cap_has_ground_truth_counts_but_no_cursor(
        self, monkeypatch, tenant, workspace, ctx
    ):
        """The default BLOCKER-preferred cap is not a sequential walk.

        ``counts`` must still describe the whole run (a client asking "how many
        blockers exist?" must not see the cap), while ``next_offset`` stays
        ``None`` because following it would skip/duplicate findings.
        """
        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", self.WINDOW)
        findings = self._findings(self.TOTAL)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(findings))
            data = svc.run_audit(workspace.id, ctx, tier="extended").to_dict()

        assert data["truncated"] is True
        assert data["next_offset"] is None
        assert data["counts"]["total"] == self.TOTAL
        assert data["page_counts"]["total"] == self.WINDOW


class TestRunAuditFindingFilter:
    """#1382/FR-02 — ``finding_filter`` narrows the run *before* cap + totals.

    Regression: the REST/MCP surfaces used to run the audit unfiltered, cap it
    at ``MAX_REPORT_FINDINGS`` and only then filter, so a match outside the cap
    was unreachable and ``counts.total`` could read 0 while matches existed.
    """

    WINDOW = 2
    BLOCKERS = 6
    TARGETS = 3

    def _findings(self) -> list:
        # The target findings come last, so the default BLOCKER-preferred cap
        # would drop every one of them.
        blockers = [
            Finding(
                rule_id=TRACE_P4,
                severity=Severity.BLOCKER,
                message=f"blocker {i}",
                artifact_ids=(),
            )
            for i in range(self.BLOCKERS)
        ]
        targets = [
            Finding(
                rule_id="IFC-001",
                severity=Severity.WARNING,
                message=f"target {i}",
                artifact_ids=(),
            )
            for i in range(self.TARGETS)
        ]
        return blockers + targets

    @staticmethod
    def _is_target(finding: Finding) -> bool:
        return finding.rule_id == "IFC-001"

    def test_filter_is_applied_before_the_cap_and_the_totals(
        self, monkeypatch, tenant, workspace, ctx
    ):
        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", self.WINDOW)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(self._findings()))
            data = svc.run_audit(
                workspace.id,
                ctx,
                tier="extended",
                finding_filter=self._is_target,
            ).to_dict()

        # Ground truth is the *filtered* set — not the cap, not the raw run.
        assert data["counts"]["total"] == self.TARGETS
        assert data["counts"]["warnings"] == self.TARGETS
        assert data["counts"]["blockers"] == 0
        # The default branch still caps the *filtered* list at the window.
        assert data["page_counts"]["total"] == self.WINDOW
        assert len(data["findings"]) == self.WINDOW
        assert {f["rule_id"] for f in data["findings"]} == {"IFC-001"}
        # Original indices are preserved (the pairs were filtered, not
        # re-enumerated): the targets are the last three engine findings.
        assert [f["index"] for f in data["findings"]] == [
            self.BLOCKERS + i for i in range(self.WINDOW)
        ]
        # MAX_REPORT_FINDINGS (2) < the filtered total (3), but the default
        # branch caps without a cursor.
        assert data["truncated"] is True
        assert data["next_offset"] is None

    def test_a_filtered_walk_reaches_matches_past_the_cap(
        self, monkeypatch, tenant, workspace, ctx
    ):
        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", self.WINDOW)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(self._findings()))
            first = svc.run_audit(
                workspace.id,
                ctx,
                tier="extended",
                limit=2,
                offset=0,
                finding_filter=self._is_target,
            ).to_dict()
            second = svc.run_audit(
                workspace.id,
                ctx,
                tier="extended",
                limit=2,
                offset=2,
                finding_filter=self._is_target,
            ).to_dict()

        # Every target is reachable, even though none of them would survive the
        # pre-fix cap that was applied before filtering.
        assert [f["message"] for f in first["findings"]] == ["target 0", "target 1"]
        assert [f["message"] for f in second["findings"]] == ["target 2"]
        assert first["next_offset"] == 2
        assert second["next_offset"] is None
        assert first["counts"]["total"] == self.TARGETS
        assert second["counts"]["total"] == self.TARGETS

    def test_zero_limit_window_advertises_no_cursor(
        self, monkeypatch, tenant, workspace, ctx
    ):
        """``limit=0`` is internal misuse; it must not yield a looping cursor."""
        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", self.WINDOW)
        with _active(tenant):
            svc = AuditService(engine=_FixedEngine(self._findings()))
            data = svc.run_audit(
                workspace.id, ctx, tier="extended", limit=0, offset=0
            ).to_dict()

        assert data["findings"] == []
        assert data["truncated"] is True
        assert data["next_offset"] is None


class TestRunAuditSuppressedAndFiltered:
    """#1382/F-02 — ``include_suppressed=False`` composed with a finding filter.

    The combination was untested: the filter narrows the run first, the
    suppression totals are then computed over that *filtered* set, and
    ``suppressed_filtered`` is subtracted from the visible total before the
    window/cursor is derived. A regression here shows up as a wrong
    ``counts.*`` block or a cursor pointing past the visible end.
    """

    BLOCKER_RULE = "TEST-SUPPRESSED-BLOCKER"
    WARNING_RULE = "TEST-VISIBLE-WARNING"
    EXCLUDED_RULE = "TEST-EXCLUDED"

    def _findings(self) -> list[Finding]:
        return [
            Finding(
                rule_id=self.BLOCKER_RULE,
                severity=Severity.BLOCKER,
                message="suppressed blocker",
                artifact_ids=("art-blocker",),
            ),
            Finding(
                rule_id=self.WARNING_RULE,
                severity=Severity.WARNING,
                message="visible warning",
                artifact_ids=("art-warning",),
            ),
            # Same severity as the suppressed blocker but outside the rule
            # filter: it must not contribute to any count.
            Finding(
                rule_id=self.EXCLUDED_RULE,
                severity=Severity.BLOCKER,
                message="excluded blocker",
                artifact_ids=(),
            ),
        ]

    def _suppression(self) -> SuppressionRecord:
        return SuppressionRecord(
            id=uuid4(),
            finding_key=finding_key(self.BLOCKER_RULE, ("art-blocker",)),
            rule_id=self.BLOCKER_RULE,
            artifact_ids=("art-blocker",),
            scope="",
            scope_artifact_id="",
            reason="accepted deviation",
            granted_by="audit-test",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=None,
        )

    def test_counts_suppressed_filtered_and_cursor_compose(self, tenant, workspace, ctx):
        selected_rules = frozenset({self.BLOCKER_RULE, self.WARNING_RULE})
        with _active(tenant), patch(
            "application.audit_service.load_suppressions",
            return_value=[self._suppression()],
        ):
            svc = AuditService(engine=_FixedEngine(self._findings()))
            data = svc.run_audit(
                workspace.id,
                ctx,
                tier="extended",
                limit=1,
                offset=0,
                include_suppressed=False,
                finding_filter=lambda finding: finding_matches(
                    finding, rule_ids=selected_rules
                ),
            ).to_dict()

        # `counts` describes the filtered ground truth (2), not the raw run (3)
        # and not the window (1). The suppressed blocker is excluded from
        # `blockers` (waiver-aware) but accounted for by `suppressed_blockers`.
        counts = data["counts"]
        assert counts["total"] == 2
        assert counts["blockers"] == 0
        assert counts["warnings"] == 1
        assert counts["suppressed"] == 1
        assert counts["suppressed_blockers"] == 1
        assert (
            counts["blockers"] + counts["warnings"] + counts["suppressed_blockers"]
            == counts["total"]
        )

        # The hidden finding was removed from the window, and the counter
        # explains the page_counts vs counts gap.
        assert data["suppressed_filtered"] == 1
        assert data["page_counts"]["total"] == 1
        assert data["page_counts"]["blockers"] == 0
        assert data["page_counts"]["warnings"] == 1
        assert [f["message"] for f in data["findings"]] == ["visible warning"]
        # Original engine index is preserved (pairs were filtered, not
        # re-enumerated).
        assert [f["index"] for f in data["findings"]] == [1]

        # The only visible finding is the whole visible set, so the walk is
        # done: the cursor must be None, not `offset + window` (which would be
        # the case if `visible_total` forgot `suppressed_filtered`).
        assert data["offset"] == 0
        assert data["truncated"] is False
        assert data["next_offset"] is None



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
