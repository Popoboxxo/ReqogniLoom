"""#424 — TestCase provenance/review flag and the closed false-green paths.

Cluster-5 spec section 4. Exercises the service contract
(``TestService.create_test_case``/``mark_reviewed``), the shared coverage
predicate and every consumer that must stop counting an unreviewed
AI-generated TestCase as verification evidence:

  * ``CoverageCalculator.coverage`` (AC-424-2/3/4, pending_ai_review)
  * ``CoverageCalculator.get_coverage_data``
  * ``workflow.precondition_rules.check_verification_evidence`` (AC-424-5)

The third consumer (VERIF-P8) lives in
``traceability/tests/test_verif_p8_evidence_424.py``.
"""
from __future__ import annotations

import pytest

from persistence.models import (
    Artifact,
    Requirement,
    TestCase,
    TestCaseOrigin,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-424", slug="t-424")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-424")
    user = User.objects.create(
        username="u-424", email="u-424@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, workspace, user, ctx


def _make_requirement(tenant, workspace, title="Req"):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, req


def _link(source_artifact, target_artifact, tenant, link_type="verifies"):
    from persistence.models import TraceLink

    return TraceLink.objects.create(
        source=source_artifact,
        target=target_artifact,
        link_type=link_type,
        tenant=tenant,
    )


# ---------------------------------------------------------------------------
# AC-424-2 / AC-424-17 — defaults
# ---------------------------------------------------------------------------


def test_manual_default_is_reviewed(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(workspace_id=workspace.id, title="TC", ctx=ctx)

    assert tc.origin == TestCaseOrigin.MANUAL
    assert tc.reviewed is True


def test_ai_generated_defaults_to_unreviewed(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(
        workspace_id=workspace.id,
        title="AI TC",
        ctx=ctx,
        origin=TestCaseOrigin.AI_GENERATED,
    )

    assert tc.origin == TestCaseOrigin.AI_GENERATED
    assert tc.reviewed is False


def test_explicit_reviewed_wins(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(
        workspace_id=workspace.id,
        title="AI TC",
        ctx=ctx,
        origin=TestCaseOrigin.AI_GENERATED,
        reviewed=True,
    )
    assert tc.reviewed is True


def test_unknown_origin_is_accepted_defensively(env):
    """N7: ``unknown`` stays service-accepted (migration/grandfathering)."""
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(
        workspace_id=workspace.id,
        title="Legacy TC",
        ctx=ctx,
        origin=TestCaseOrigin.UNKNOWN,
    )
    assert tc.origin == TestCaseOrigin.UNKNOWN
    # Only `manual` is auto-reviewed; an unknown-provenance row is not claimed
    # to be human-checked.
    assert tc.reviewed is False


def test_invalid_origin_is_rejected(env):
    from application.base import ValidationError
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    with pytest.raises(ValidationError):
        TestService().create_test_case(
            workspace_id=workspace.id, title="TC", ctx=ctx, origin="bogus"
        )


# ---------------------------------------------------------------------------
# AC-424-3 / AC-424-4 — coverage + pending_ai_review
# ---------------------------------------------------------------------------


def _unreviewed_ai_testcase(tenant, workspace, ctx, title="AI TC"):
    from application.test_service import TestService

    return TestService().create_test_case(
        workspace_id=workspace.id,
        title=title,
        ctx=ctx,
        origin=TestCaseOrigin.AI_GENERATED,
    )


def test_unreviewed_ai_testcase_does_not_cover(env):
    from traceability.coverage_calculator import CoverageCalculator

    tenant, workspace, _user, ctx = env
    req_artifact, _req = _make_requirement(tenant, workspace)
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)

    report = CoverageCalculator().coverage(workspace.id)

    assert report.total == 1
    assert report.covered == 0
    assert report.pending_ai_review == 1

    raw = CoverageCalculator().coverage(workspace.id, include_unreviewed_ai=True)
    assert raw.covered == 1
    assert raw.pending_ai_review == 0


def test_reviewing_ai_testcase_restores_coverage(env):
    from application.test_service import TestService
    from traceability.coverage_calculator import CoverageCalculator

    tenant, workspace, _user, ctx = env
    req_artifact, _req = _make_requirement(tenant, workspace)
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)

    TestService().mark_reviewed(tc.id, ctx, reviewed=True)

    report = CoverageCalculator().coverage(workspace.id)
    assert report.covered == 1
    assert report.pending_ai_review == 0


def test_unknown_origin_is_grandfathered(env):
    """AC-424-7: pre-#424 rows (origin='unknown') still count as coverage."""
    from application.test_service import TestService
    from traceability.coverage_calculator import CoverageCalculator

    tenant, workspace, _user, ctx = env
    req_artifact, _req = _make_requirement(tenant, workspace)
    tc = TestService().create_test_case(
        workspace_id=workspace.id,
        title="legacy",
        ctx=ctx,
        origin=TestCaseOrigin.UNKNOWN,
    )
    _link(tc.artifact, req_artifact, tenant)

    report = CoverageCalculator().coverage(workspace.id)
    assert report.covered == 1
    assert report.pending_ai_review == 0


def test_get_coverage_data_carries_provenance(env):
    from traceability.coverage_calculator import CoverageCalculator

    tenant, workspace, _user, ctx = env
    req_artifact, req = _make_requirement(tenant, workspace, title="R1")
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)

    data = CoverageCalculator().get_coverage_data(workspace.id)
    entry = data.entries[0]
    assert entry.title == "R1"
    assert entry.test_cases == []  # unreviewed AI is not evidence

    raw = CoverageCalculator().get_coverage_data(
        workspace.id, include_unreviewed_ai=True
    )
    payload = raw.entries[0].test_cases[0]
    assert payload["origin"] == "ai_generated"
    assert payload["reviewed"] is False
    assert payload["scenario_kind"] == "nominal"
    assert payload["title"]
    assert payload["id"] == str(tc.artifact_id)


def test_coverage_report_to_dict_exposes_pending_ai_review(env):
    from traceability.coverage_calculator import CoverageCalculator

    tenant, workspace, _user, ctx = env
    req_artifact, _req = _make_requirement(tenant, workspace)
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)

    payload = CoverageCalculator().coverage(workspace.id).to_dict()
    assert payload["pending_ai_review"] == 1


# ---------------------------------------------------------------------------
# AC-424-5 — transition evidence (consumer 2)
# ---------------------------------------------------------------------------


def _passing_run(tenant, workspace, test_case):
    from django.utils import timezone

    from persistence.models import TestRun, TestRunResult

    run = TestRun.objects.create(
        tenant=tenant, workspace=workspace, name="run", status="passed"
    )
    return TestRunResult.objects.create(
        tenant=tenant,
        test_run=run,
        test_case=test_case,
        status="passed",
        executed_at=timezone.now(),
    )


def test_unreviewed_ai_evidence_blocks_verified_transition(env):
    from workflow.precondition_rules import check_verification_evidence

    tenant, workspace, _user, ctx = env
    req_artifact, req = _make_requirement(tenant, workspace)
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)
    _passing_run(tenant, workspace, tc)

    error = check_verification_evidence(
        item_type="Requirement", item_id=req.id, target_state="verified"
    )
    assert error is not None
    code, message = error
    # The workflow error-code constants drop the ``EC_`` display prefix
    # (``workflow.precondition_rules``); the AC names the REST-visible code.
    assert code == "VERIFICATION_EVIDENCE_MISSING"
    assert "unreviewed AI-generated" in message


def test_reviewed_ai_evidence_allows_verified_transition(env):
    from application.test_service import TestService
    from workflow.precondition_rules import check_verification_evidence

    tenant, workspace, _user, ctx = env
    req_artifact, req = _make_requirement(tenant, workspace)
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    _link(tc.artifact, req_artifact, tenant)
    _passing_run(tenant, workspace, tc)
    TestService().mark_reviewed(tc.id, ctx, reviewed=True)

    assert (
        check_verification_evidence(
            item_type="Requirement", item_id=req.id, target_state="verified"
        )
        is None
    )


# ---------------------------------------------------------------------------
# AC-424-11 / AC-424-13 — mark_reviewed
# ---------------------------------------------------------------------------


def _audit_entries(entity_id):
    from audit.models import AuditEntry

    return list(
        AuditEntry.unscoped.filter(
            entity_type="TestCase", entity_id=entity_id
        ).order_by("timestamp")
    )


def test_mark_reviewed_bumps_version_once_and_audits(env):
    """AC-424-11 (minus the ``details.reviewed`` clause — see the deviation note).

    ``TestService.mark_reviewed`` passes ``details={"reviewed": ...}`` to
    ``ServiceBase._audit`` exactly as specified, but the v1 audit writer
    (``audit/services.py::log_write`` → ``AuditLogWriter.write``) documents
    ``details`` as "Reserved for v2 field-level diff (ADR-10). Ignored in v1."
    and ``AuditEntry`` has no column to persist it. The AC's
    ``details.reviewed == true`` clause is therefore not verifiable without a
    schema change (out of this cluster's scope); the audited operation itself
    is asserted here instead.
    """
    from application.test_service import TestService

    tenant, workspace, _user, ctx = env
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    service = TestService()

    reviewed = service.mark_reviewed(tc.id, ctx, reviewed=True)
    assert reviewed.reviewed is True
    version_after_first = reviewed.version

    again = service.mark_reviewed(tc.id, ctx, reviewed=True)
    assert again.version == version_after_first  # idempotent

    entries = _audit_entries(tc.id)
    assert entries, "mark_reviewed must write an audit entry"
    assert entries[-1].op == "update"
    assert entries[-1].entity_type == "TestCase"


def test_mark_reviewed_does_not_touch_workflow_state(env):
    """AC-424-13: `reviewed` and the workflow lifecycle are independent."""
    from application.test_service import TestService
    from workflow import state_reader

    tenant, workspace, _user, ctx = env
    tc = _unreviewed_ai_testcase(tenant, workspace, ctx)
    before = state_reader.current_state("TestCase", tc.id)

    TestService().mark_reviewed(tc.id, ctx, reviewed=True)

    assert state_reader.current_state("TestCase", tc.id) == before
    assert TestCase.objects.get(id=tc.id).reviewed is True
