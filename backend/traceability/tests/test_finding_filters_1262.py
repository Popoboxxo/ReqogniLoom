"""#1262 — unit tests for the shared audit finding filters."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from traceability.audit.finding_filters import (
    apply_report_filters,
    finding_matches,
    normalize_rule_ids,
    normalize_severities,
    resolve_artifact_ids_for_type,
)
from traceability.audit.types import Finding, Severity


def _view(rule_id, severity, artifact_ids=(), suppressed=False):
    return SimpleNamespace(
        finding=Finding(
            rule_id=rule_id,
            severity=severity,
            message="m",
            artifact_ids=tuple(artifact_ids),
        ),
        suppressed=suppressed,
    )


def _report(views, *, suppressed_filtered=0):
    return SimpleNamespace(
        findings=list(views),
        truncated=False,
        offset=0,
        next_offset=None,
        total_findings_available=len(views),
        total_blockers_available=0,
        total_warnings_available=0,
        total_suppressed_available=0,
        total_suppressed_blockers_available=0,
        suppressed_filtered=suppressed_filtered,
    )


class TestNormalizers:
    def test_rule_ids_from_comma_string(self):
        assert normalize_rule_ids("TRACE-P1, TRACE-P2") == {"TRACE-P1", "TRACE-P2"}

    def test_rule_ids_blank_is_empty(self):
        assert normalize_rule_ids("") == frozenset()
        assert normalize_rule_ids(None) == frozenset()

    def test_severities_validated(self):
        assert normalize_severities("blocker") == {"blocker"}
        with pytest.raises(ValueError):
            normalize_severities("catastrophic")


class TestFindingMatches:
    def test_rule_id_filter(self):
        finding = Finding("TRACE-P1", Severity.BLOCKER, "m", ())
        assert finding_matches(finding, rule_ids=frozenset({"TRACE-P1"}))
        assert not finding_matches(finding, rule_ids=frozenset({"TRACE-P2"}))

    def test_severity_filter(self):
        finding = Finding("TRACE-P1", Severity.WARNING, "m", ())
        assert finding_matches(finding, severities=frozenset({"warning"}))
        assert not finding_matches(finding, severities=frozenset({"blocker"}))

    def test_artifact_type_filter(self):
        finding = Finding("IFC-001", Severity.WARNING, "m", ("a1", "a2"))
        assert finding_matches(
            finding, artifact_type_ids=frozenset({"a1"})
        )
        assert not finding_matches(
            finding, artifact_type_ids=frozenset({"zzz"})
        )


class TestApplyReportFilters:
    def test_filters_and_recomputes_summary_counts(self):
        report = _report(
            [
                _view("TRACE-P1", Severity.BLOCKER, ("a",)),
                _view("IFC-001", Severity.WARNING, ("b",)),
                _view("IFC-001", Severity.WARNING, ("b",), suppressed=True),
            ]
        )

        apply_report_filters(report, rule_ids=frozenset({"IFC-001"}))

        assert {v.finding.rule_id for v in report.findings} == {"IFC-001"}
        assert report.total_findings_available == 2
        assert report.total_warnings_available == 2
        assert report.total_blockers_available == 0
        assert report.total_suppressed_available == 1
        assert report.total_suppressed_blockers_available == 0

    def test_limit_and_offset_window_the_filtered_set(self):
        report = _report(
            [_view("IFC-001", Severity.WARNING, (str(i),)) for i in range(3)]
        )

        apply_report_filters(report, severities=frozenset({"warning"}), limit=1, offset=1)

        assert len(report.findings) == 1
        assert report.offset == 1
        assert report.truncated is True
        # #1382: the cursor for the following window (offsets 0..2 exist).
        assert report.next_offset == 2
        assert report.total_findings_available == 3

    def test_last_window_has_no_cursor(self):
        report = _report(
            [_view("IFC-001", Severity.WARNING, (str(i),)) for i in range(3)]
        )

        apply_report_filters(report, severities=frozenset({"warning"}), limit=5, offset=2)

        assert report.truncated is False
        assert report.next_offset is None

    def test_unwindowed_branch_has_no_cursor(self):
        report = _report(
            [_view("IFC-001", Severity.WARNING, (str(i),)) for i in range(3)]
        )

        apply_report_filters(report, severities=frozenset({"warning"}))

        assert report.next_offset is None

    def test_empty_window_never_advertises_a_non_advancing_cursor(self):
        report = _report(
            [_view("IFC-001", Severity.WARNING, (str(i),)) for i in range(3)]
        )

        apply_report_filters(report, severities=frozenset({"warning"}), limit=0, offset=0)

        assert report.findings == []
        assert report.truncated is True
        # Without this guard `next_offset` would equal `offset` (0) and a
        # caller following the cursor would loop forever (#1382/FR-01).
        assert report.next_offset is None

    def test_preserves_the_service_computed_suppressed_filtered(self):
        """#1382/FR-02: filtering must not erase the include_suppressed=False
        explanation the service computed."""
        report = _report(
            [
                _view("IFC-001", Severity.WARNING, ("a",)),
                _view("IFC-001", Severity.WARNING, ("b",), suppressed=True),
            ],
            suppressed_filtered=1,
        )

        apply_report_filters(report, severities=frozenset({"warning"}))

        assert report.suppressed_filtered == 1


@pytest.mark.django_db
class TestResolveArtifactIdsForType:
    def test_resolves_workspace_artifacts_of_type(self, tenant_a, workspace_a):
        from persistence.middleware import clear_request_tenant, set_request_tenant
        from persistence.models import Artifact

        set_request_tenant(tenant_a.id)
        try:
            icd = Artifact.objects.create(
                tenant=tenant_a, workspace=workspace_a, artifact_type="Icd"
            )
            Artifact.objects.create(
                tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
            )
        finally:
            clear_request_tenant()

        resolved = resolve_artifact_ids_for_type(
            artifact_type="Icd",
            tenant_id=tenant_a.id,
            workspace_id=workspace_a.id,
        )
        assert resolved == {str(icd.id)}
