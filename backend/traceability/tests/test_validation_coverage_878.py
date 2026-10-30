"""#878 / Plan B B2-T2 — validation coverage of StakeholderNeeds.

The counterpart of the Requirement → TestCase coverage report: a StakeholderNeed
is "validated" when at least one incoming ``validates`` link comes from a live
TestCase that counts as verification evidence
(:func:`traceability.coverage_calculator.counts_as_verification_evidence`). The
denominator is every active StakeholderNeed of the workspace.

Deliberately no absolute catalog totals (KA-B-03): every assertion is about this
test's own two needs.
"""
from __future__ import annotations

import pytest

from traceability.coverage_calculator import CoverageCalculator
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


def make_need(tenant, workspace, title: str, uid: str):
    """Create Artifact + StakeholderNeed; returns both."""
    from persistence.models import StakeholderNeed

    artifact = make_artifact(tenant, workspace, artifact_type="StakeholderNeed")
    need = StakeholderNeed.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid,
    )
    return artifact, need


class TestValidationCoverage:
    """Validation coverage summary + per-need entries."""

    def test_one_of_two_needs_validated(self, tenant_a, workspace_a):
        """2 needs, one ``validates`` link to need A → 1/2 = 50.0%."""
        with active_tenant(tenant_a):
            need_a_art, need_a = make_need(tenant_a, workspace_a, "Need A", "NEED-001")
            _, need_b = make_need(tenant_a, workspace_a, "Need B", "NEED-002")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "Validating TC")
            make_trace_link(tc_art, need_a_art, tenant_a, "validates")

            report = CoverageCalculator().validation_coverage(workspace_a.id)

        assert report.total == 2
        assert report.covered == 1
        assert report.percentage == 50.0
        assert report.pending_ai_review == 0
        assert report.uncovered == [str(need_b.id)]

        # D-SORT: entries ordered by uid.
        assert [entry.uid for entry in report.entries] == ["NEED-001", "NEED-002"]
        covered_entry = next(e for e in report.entries if e.need_id == str(need_a.id))
        assert covered_entry.title == "Need A"
        assert [row["id"] for row in covered_entry.test_cases] == [str(tc_art.id)]
        assert covered_entry.test_cases[0]["title"] == tc.title
        # VCRM-shaped result label.
        assert covered_entry.test_cases[0]["latest_result"] == "Not Run"

        uncovered_entry = next(e for e in report.entries if e.need_id == str(need_b.id))
        assert uncovered_entry.test_cases == []

    def test_empty_workspace(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            report = CoverageCalculator().validation_coverage(workspace_a.id)

        assert report.total == 0
        assert report.covered == 0
        assert report.percentage == 0.0
        assert report.uncovered == []
        assert report.entries == []

    def test_outdated_test_case_does_not_count_by_default_but_counts_with_flag(
        self, tenant_a, workspace_a
    ):
        """A soft-deleted TestCase is not evidence unless ``include_outdated``."""
        from workflow.services import create_default_workflow, outdate

        class _SystemCtx:
            user_id = "system:test-validation-coverage"

        with active_tenant(tenant_a):
            need_art, _ = make_need(tenant_a, workspace_a, "Need", "NEED-001")
            tc_art, outdated_tc = make_test_case(tenant_a, workspace_a, "Outdated TC")
            create_default_workflow(
                workspace_id=workspace_a.id,
                preset="testcase_default",
                item_type="TestCase",
                tenant_id=tenant_a.id,
            )
            outdate(
                item_id=outdated_tc.id,
                item_type="TestCase",
                workspace_id=workspace_a.id,
                ctx=_SystemCtx(),
                reason="test: mark outdated",
            )
            make_trace_link(tc_art, need_art, tenant_a, "validates")

            report = CoverageCalculator().validation_coverage(workspace_a.id)
            # ``include_outdated`` opts the outdated source back in, so the
            # very same ``validates`` link counts as evidence again.
            with_outdated = CoverageCalculator().validation_coverage(
                workspace_a.id, include_outdated=True
            )

        assert report.total == 1
        assert report.covered == 0
        assert report.percentage == 0.0
        assert report.pending_ai_review == 0

        assert with_outdated.total == 1
        assert with_outdated.covered == 1
        assert with_outdated.percentage == 100.0

    def test_outdated_need_is_excluded_unless_include_outdated(
        self, tenant_a, workspace_a
    ):
        """An outdated Need leaves the denominator by default (#878)."""
        from workflow.services import create_default_workflow, outdate

        class _SystemCtx:
            user_id = "system:test-validation-coverage"

        with active_tenant(tenant_a):
            make_need(tenant_a, workspace_a, "Live need", "NEED-001")
            _, outdated_need = make_need(
                tenant_a, workspace_a, "Outdated need", "NEED-002"
            )
            create_default_workflow(
                workspace_id=workspace_a.id,
                preset="need_default",
                item_type="StakeholderNeed",
                tenant_id=tenant_a.id,
            )
            outdate(
                item_id=outdated_need.id,
                item_type="StakeholderNeed",
                workspace_id=workspace_a.id,
                ctx=_SystemCtx(),
                reason="test: mark outdated",
            )

            report = CoverageCalculator().validation_coverage(workspace_a.id)
            with_outdated = CoverageCalculator().validation_coverage(
                workspace_a.id, include_outdated=True
            )

        # Default: the soft-deleted Need no longer drags the KPI down.
        assert report.total == 1
        assert [entry.uid for entry in report.entries] == ["NEED-001"]
        assert str(outdated_need.id) not in report.uncovered

        # Opted in: it is part of total/entries/uncovered again.
        assert with_outdated.total == 2
        assert [entry.uid for entry in with_outdated.entries] == [
            "NEED-001",
            "NEED-002",
        ]
        assert str(outdated_need.id) in with_outdated.uncovered

    def test_unreviewed_ai_test_case_does_not_count_and_is_reported(
        self, tenant_a, workspace_a
    ):
        """#424 predicate: an AI-generated, unreviewed TC is not evidence."""
        with active_tenant(tenant_a):
            need_art, need = make_need(tenant_a, workspace_a, "Need", "NEED-001")
            tc_art, ai_tc = make_test_case(tenant_a, workspace_a, "AI TC")
            ai_tc.origin = "ai_generated"
            ai_tc.reviewed = False
            ai_tc.save(update_fields=["origin", "reviewed"])
            make_trace_link(tc_art, need_art, tenant_a, "validates")

            report = CoverageCalculator().validation_coverage(workspace_a.id)
            raw = CoverageCalculator().validation_coverage(
                workspace_a.id, include_unreviewed_ai=True
            )

        assert report.total == 1
        assert report.covered == 0
        assert report.pending_ai_review == 1
        assert report.uncovered == [str(need.id)]
        assert report.entries[0].test_cases == []

        # The raw view counts it and reports nothing pending.
        assert raw.covered == 1
        assert raw.pending_ai_review == 0
        assert raw.percentage == 100.0

    def test_reviewed_ai_test_case_counts(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            need_art, _ = make_need(tenant_a, workspace_a, "Need", "NEED-001")
            tc_art, ai_tc = make_test_case(tenant_a, workspace_a, "Reviewed AI TC")
            ai_tc.origin = "ai_generated"
            ai_tc.reviewed = True
            ai_tc.save(update_fields=["origin", "reviewed"])
            make_trace_link(tc_art, need_art, tenant_a, "validates")

            report = CoverageCalculator().validation_coverage(workspace_a.id)

        assert report.covered == 1
        assert report.pending_ai_review == 0

    def test_ordering_is_uid_then_need_id(self, tenant_a, workspace_a):
        """D-SORT: entries and uncovered share one deterministic order."""
        with active_tenant(tenant_a):
            _, need_b = make_need(tenant_a, workspace_a, "B", "NEED-002")
            _, need_a = make_need(tenant_a, workspace_a, "A", "NEED-001")

            report = CoverageCalculator().validation_coverage(workspace_a.id)

        assert [e.uid for e in report.entries] == ["NEED-001", "NEED-002"]
        assert report.uncovered == [str(need_a.id), str(need_b.id)]
