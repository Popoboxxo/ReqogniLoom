"""#569 error-contract tests: the reserved 422, the exception maps, i18n codes.

The approved spec (§3.4.1/D1) makes the status set of the new suppression
surface *disjoint*: none of the new endpoints may ever answer HTTP 422 — that
status stays reserved for ``POST .../audit/remediate/`` ("Adopt not applicable
-> offer Modify"). §3.4.2 additionally requires the three Layer-2 error types to
be registered in ``_EXC_TO_HTTP``/``_EXC_TO_CODE`` with their dedicated codes
and to have DE+EN messages, while the two Layer-1 governance domain errors must
*not* be registered (a leak there is a bug that has to fail loud).

This module pins exactly those cross-cutting contracts; the per-endpoint
behaviour lives in ``test_audit_waivers_569_rest.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from application.base import (
    SuppressionExpiredError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
from auth_tenancy.context import AuthContext, AuthMethod
from baseline.exceptions import GovernanceAuthorityError, GovernanceReasonError
from baseline.models import BaselineGateWaiver
from baseline.waivers import finding_key
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from rest_api.audit_views import (
    WorkspaceAuditRemediateView,
    WorkspaceAuditView,
    WorkspaceAuditWaiverView,
)
from rest_api.serializers import _ERROR_MESSAGES
from rest_api.views import _EXC_TO_CODE, _EXC_TO_HTTP

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    TenantContext.clear_tenant()
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()
    TenantContext.clear_tenant()


def _auth_context(user_id, tenant_id, *, roles=("admin",), scope=None):
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN if scope is None else AuthMethod.API_KEY,
        scope=scope,
    )


def _broken_extended_workspace():
    tenant = Tenant.objects.create(
        id=uuid.uuid4(), name="ec-tenant", slug=f"ec-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"ec-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"ec-{uuid.uuid4().hex[:8]}",
            email=f"ec-{uuid.uuid4().hex[:8]}@example.com",
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Orphan requirement"
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user


def _call(view_cls, method, workspace, ctx, *, body=None, query=""):
    factory = APIRequestFactory()
    if view_cls is WorkspaceAuditWaiverView:
        url = f"/api/v1/workspaces/{workspace.id}/audit/waivers/{query}"
    else:
        url = f"/api/v1/workspaces/{workspace.id}/audit/{query}"
    if method == "post":
        req = factory.post(url, data=body, format="json")
    else:
        req = factory.get(url)
    req.auth_context = ctx
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return view_cls.as_view()(req, workspace_id=str(workspace.id))
    finally:
        TenantContext.clear_tenant()


def _blocking_finding(workspace, ctx):
    from application.audit_service import AuditService
    from traceability.audit import AuditScope

    return AuditService().blocking_findings(
        workspace.id, ctx, scopes=[AuditScope("project")]
    )[0]


def _valid_body(finding, **overrides):
    body = {
        "rule_id": finding.rule_id,
        "artifact_ids": list(finding.artifact_ids),
        "reason": (
            "Accepted deviation, reviewed and signed off in the 2026-09-22 "
            "architecture board."
        ),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# E18 — no new endpoint emits 422 (and the reserved host still does)
# ---------------------------------------------------------------------------


def test_no_new_endpoint_emits_422():
    """Exercise every documented error path; assert the status and code.

    A parametrised table would need a fresh DB per case, so this walks the
    cases in one test with independent workspaces: each case is a callable
    producing ``(response, expected_status, expected_code)``.
    """
    observed: list[tuple[str, int, str]] = []

    def record(label, resp, expected_status, expected_code):
        assert resp.status_code == expected_status, (label, resp.data)
        assert resp.status_code != 422, (label, resp.data)
        assert resp.data["error"]["code"] == expected_code, (label, resp.data)
        observed.append((label, resp.status_code, resp.data["error"]["code"]))

    # E3 malformed body
    _, ws, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, ws.tenant_id)
    record(
        "E3",
        _call(WorkspaceAuditWaiverView, "post", ws, ctx, body={"rule_id": "TRACE-P1"}),
        400,
        "VALIDATION_ERROR",
    )

    # E4 reason policy
    finding = _blocking_finding(ws, ctx)
    record(
        "E4",
        _call(
            WorkspaceAuditWaiverView,
            "post",
            ws,
            ctx,
            body=_valid_body(finding, reason="ok"),
        ),
        400,
        "WAIVER_REASON_REJECTED",
    )

    # E5 not blocking
    record(
        "E5",
        _call(
            WorkspaceAuditWaiverView,
            "post",
            ws,
            ctx,
            body={
                "rule_id": "CONS-P11",
                "artifact_ids": [str(uuid.uuid4())],
                "reason": "Accepted deviation for a finding that is not reported.",
            },
        ),
        400,
        "WAIVER_FINDING_NOT_BLOCKING",
    )

    # E6 editor
    editor_ctx = _auth_context(user.id, ws.tenant_id, roles=("editor",))
    record(
        "E6",
        _call(
            WorkspaceAuditWaiverView,
            "post",
            ws,
            editor_ctx,
            body=_valid_body(finding),
        ),
        403,
        "PERMISSION_DENIED",
    )

    # E7 foreign workspace
    tenant_a, _, user_a = _broken_extended_workspace()
    _, foreign_ws, _ = _broken_extended_workspace()
    foreign_ctx = _auth_context(user_a.id, tenant_a.id)
    record(
        "E7",
        _call(
            WorkspaceAuditWaiverView,
            "post",
            foreign_ws,
            foreign_ctx,
            body={
                "rule_id": "TRACE-P1",
                "artifact_ids": [],
                "reason": "A justification for a workspace in a foreign tenant.",
            },
        ),
        404,
        "NOT_FOUND",
    )

    # E8 expired-only row
    BaselineGateWaiver.unscoped.create(
        workspace_id=ws.id,
        tenant_id=ws.tenant_id,
        finding_key=finding_key(finding.rule_id, finding.artifact_ids),
        rule_id=finding.rule_id,
        artifact_ids=list(finding.artifact_ids),
        scope="project",
        scope_artifact_id="",
        reason="An earlier justification that has since expired.",
        granted_by=str(user.id),
        expires_at=datetime.now(dt_timezone.utc) - timedelta(days=1),
    )
    record(
        "E8",
        _call(
            WorkspaceAuditWaiverView, "post", ws, ctx, body=_valid_body(finding)
        ),
        409,
        "SUPPRESSION_EXPIRED",
    )

    # E9 server error
    _, ws2, user2 = _broken_extended_workspace()
    ctx2 = _auth_context(user2.id, ws2.tenant_id)
    finding2 = _blocking_finding(ws2, ctx2)
    with patch(
        "application.audit_service.AuditService.suppress_finding",
        side_effect=RuntimeError("boom"),
    ):
        record(
            "E9",
            _call(
                WorkspaceAuditWaiverView,
                "post",
                ws2,
                ctx2,
                body=_valid_body(finding2),
            ),
            500,
            "INTERNAL_SERVER_ERROR",
        )

    # E11 unknown state
    record(
        "E11",
        _call(WorkspaceAuditWaiverView, "get", ws2, ctx2, query="?state=x"),
        400,
        "VALIDATION_ERROR",
    )

    # E12 list authority
    record(
        "E12",
        _call(WorkspaceAuditWaiverView, "get", ws2, _auth_context(
            user2.id, ws2.tenant_id, roles=("editor",)
        )),
        403,
        "PERMISSION_DENIED",
    )

    # E13 list foreign workspace
    record(
        "E13",
        _call(WorkspaceAuditWaiverView, "get", foreign_ws, foreign_ctx),
        404,
        "NOT_FOUND",
    )

    # E15 invalid include_suppressed
    record(
        "E15",
        _call(WorkspaceAuditView, "get", ws2, ctx2, query="?include_suppressed=banana"),
        400,
        "VALIDATION_ERROR",
    )

    # E16 report foreign workspace
    record(
        "E16",
        _call(WorkspaceAuditView, "get", foreign_ws, foreign_ctx),
        404,
        "NOT_FOUND",
    )

    # E19 list server error
    with patch(
        "application.audit_service.AuditService.list_suppressions",
        side_effect=RuntimeError("boom"),
    ):
        record(
            "E19",
            _call(WorkspaceAuditWaiverView, "get", ws2, ctx2),
            500,
            "INTERNAL_SERVER_ERROR",
        )

    # E20 report server error
    with patch(
        "application.audit_service.AuditService.run_audit",
        side_effect=RuntimeError("boom"),
    ):
        record(
            "E20",
            _call(WorkspaceAuditView, "get", ws2, ctx2),
            500,
            "INTERNAL_SERVER_ERROR",
        )

    assert {row[0] for row in observed} == {
        "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E11", "E12", "E13",
        "E15", "E16", "E19", "E20",
    }
    assert all(status != 422 for _, status, _ in observed)


def test_remediate_keeps_422_for_the_modify_flip():
    """The reserved host is unchanged: a non-auto-remediable finding is 422."""
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)

    resp = _call(
        WorkspaceAuditRemediateView,
        "post",
        workspace,
        ctx,
        body={"rule_id": "TRACE-P4", "artifact_ids": [str(uuid.uuid4())]},
    )

    assert resp.status_code == 422, resp.data


# ---------------------------------------------------------------------------
# AC-569-29 — exception-map registration (and deliberate non-registration)
# ---------------------------------------------------------------------------


def test_new_error_types_are_registered_in_exc_maps():
    from rest_framework import status as http

    assert _EXC_TO_HTTP[WaiverReasonPolicyViolation] == http.HTTP_400_BAD_REQUEST
    assert _EXC_TO_HTTP[WaiverFindingNotBlockingError] == http.HTTP_400_BAD_REQUEST
    assert _EXC_TO_HTTP[SuppressionExpiredError] == http.HTTP_409_CONFLICT

    assert _EXC_TO_CODE[WaiverReasonPolicyViolation] == "WAIVER_REASON_REJECTED"
    assert (
        _EXC_TO_CODE[WaiverFindingNotBlockingError]
        == "WAIVER_FINDING_NOT_BLOCKING"
    )
    assert _EXC_TO_CODE[SuppressionExpiredError] == "SUPPRESSION_EXPIRED"


def test_governance_domain_errors_are_not_registered():
    """A leaked L1 domain error must stay loud (500), not silently 400."""
    assert GovernanceReasonError not in _EXC_TO_HTTP
    assert GovernanceAuthorityError not in _EXC_TO_HTTP
    assert GovernanceReasonError not in _EXC_TO_CODE
    assert GovernanceAuthorityError not in _EXC_TO_CODE


# ---------------------------------------------------------------------------
# AC-569-32 — bilingual error messages for the three new codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "WAIVER_REASON_REJECTED",
        "WAIVER_FINDING_NOT_BLOCKING",
        "SUPPRESSION_EXPIRED",
    ],
)
def test_new_error_codes_have_de_and_en_messages(code):
    entry = _ERROR_MESSAGES[code]
    assert entry.get("en", "").strip()
    assert entry.get("de", "").strip()
