"""#424 — VERIF-P8 must stop accepting an unreviewed AI TestCase as evidence.

Cluster-5 spec section 4.5 (3) / AC-424-9. The third false-green consumer is
``traceability.audit.rules.coverage_consistency``: VERIF-P8 used the same
``_active_test_cases`` helper TRACE-P6 uses, which only filters ``outdated``.
The new ``_active_verifying_test_cases`` helper applies the shared
``counts_as_verification_evidence`` predicate *for VERIF-P8 only*; TRACE-P6
stays on the unfiltered helper (deliberate — see the helper's docstring).

Mutationsprobe (AC-424-10): neutralising the predicate inside
``_active_verifying_test_cases`` must turn
``test_unreviewed_ai_evidence_reopens_verif_p8`` red.
"""
from __future__ import annotations

import pytest

from persistence.models import TestCaseOrigin
from traceability.audit import RuleEngine
from traceability.audit.registry import TRACE_P6, VERIF_P8
from traceability.tests.conftest import (
    active_tenant,
    make_requirement,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def _set_origin_reviewed(artifact, origin, reviewed):
    """Pin provenance/review directly on the row (audit-focussed fixture)."""
    from persistence.models import TestCase

    row = TestCase.unscoped.get(artifact_id=artifact.id)
    row.origin = origin
    row.reviewed = reviewed
    row.save(update_fields=["origin", "reviewed"])


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


class TestVerifP8Evidence:
    def test_unreviewed_ai_evidence_reopens_verif_p8(self, tenant_a, workspace_a):
        """AC-424-9: the only 'verifies' evidence is unreviewed AI content."""
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="AI TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")
            _set_origin_reviewed(tc_artifact, TestCaseOrigin.AI_GENERATED, False)

            result = _run(tenant_a, workspace_a)

        findings = [
            f
            for f in _findings(result, VERIF_P8)
            if str(req_artifact.id) in f.artifact_ids
        ]
        assert len(findings) == 1

    def test_reviewing_the_ai_testcase_clears_verif_p8(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="AI TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")
            _set_origin_reviewed(tc_artifact, TestCaseOrigin.AI_GENERATED, True)

            result = _run(tenant_a, workspace_a)

        findings = [
            f
            for f in _findings(result, VERIF_P8)
            if str(req_artifact.id) in f.artifact_ids
        ]
        assert findings == []

    def test_unknown_origin_still_counts_as_evidence(self, tenant_a, workspace_a):
        """Grandfathering: pre-#424 rows are not excluded."""
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="Legacy TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")
            _set_origin_reviewed(tc_artifact, TestCaseOrigin.UNKNOWN, False)

            result = _run(tenant_a, workspace_a)

        findings = [
            f
            for f in _findings(result, VERIF_P8)
            if str(req_artifact.id) in f.artifact_ids
        ]
        assert findings == []

    def test_trace_p6_stays_unfiltered_by_review_state(self, tenant_a, workspace_a):
        """TRACE-P6 keeps asking "does it point at a live target?" only.

        A review filter there would silently switch the rule off for
        unreviewed AI test cases — a rule gap, not a rule effect.
        """
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Req")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="AI TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")
            _set_origin_reviewed(tc_artifact, TestCaseOrigin.AI_GENERATED, False)

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, TRACE_P6) == []
