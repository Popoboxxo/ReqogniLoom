"""REST contract for standalone SE-Auditor suppressions (#569).

Pins the HTTP surface of ``POST/GET /api/v1/workspaces/<id>/audit/waivers/`` and
the ``include_suppressed`` extension of ``GET .../audit/`` against the approved
spec (revision 3, §3.4.1):

* E1/E2 — 201 on create, 200 on an idempotent replay (AC-569-04);
* E3/E4/E5/E8 — the deterministic 400/400/400/409 error split, never 422;
* E6/E7/E12/E13 — 403 ``PERMISSION_DENIED`` / 404 ``NOT_FOUND``;
* E9/E19/E20 — the 500 rows;
* E14/E15/E22 — the report marking + ``include_suppressed``/``state`` parsing;
* AC-569-30 — ``granted_by`` comes from the AuthContext only.

Audit-trail assertions deliberately inspect the *intercepted*
``ServiceBase._audit`` call (the pattern the GH-821 suite already uses) instead
of a persisted ``AuditEntry``: ``AuditEntry`` has no ``details`` column and the
shared writer drops ``details`` — rebuilding that writer is an explicit
Non-Goal of #569 (spec §7), so a test that required persisted ``details`` could
not pass. The service-side audit assertion is pinned separately by the L1/L2
suite (``application/tests/test_audit_waivers_569.py``).
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from baseline.models import BaselineGateWaiver
from baseline.waivers import finding_key
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from rest_api.audit_views import WorkspaceAuditView, WorkspaceAuditWaiverView

pytestmark = pytest.mark.django_db

WAIVER_URL = "/api/v1/workspaces/{ws}/audit/waivers/"
AUDIT_URL = "/api/v1/workspaces/{ws}/audit/"


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    """The preset tier is cached process-wide; keep tests independent."""
    TenantContext.clear_tenant()
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()
    TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _auth_context(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    roles: tuple[str, ...] = ("admin",),
    scope: str | None = None,
) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN if scope is None else AuthMethod.API_KEY,
        scope=scope,
    )


def _broken_extended_workspace():
    """An Extended workspace with guaranteed TRACE-P1 BLOCKER(s).

    Same shape as ``test_baseline_gate_waivers_821_rest.py``: a Requirement
    without any upstream link is the smallest reproducible "workspace the
    auditor declares broken".
    """
    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="w569-tenant",
        slug=f"w569-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"w569-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"w569-{uuid.uuid4().hex[:8]}",
            email=f"w569-{uuid.uuid4().hex[:8]}@example.com",
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


def _document_scoped_workspace():
    """An Extended workspace whose only BLOCKER is a document-scoped TRACE-P7.

    root -> child (in the document subtree) linked to a sibling outside it:
    exactly the cross-scope leak TRACE-P7 reports (see
    ``traceability/tests/test_trace_p7.py``).
    """
    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="w569-doc-tenant",
        slug=f"w569doc-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"w569doc-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"w569doc-{uuid.uuid4().hex[:8]}",
            email=f"w569doc-{uuid.uuid4().hex[:8]}@example.com",
        )
        root = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        child = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement", parent=root
        )
        sibling = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        TraceLink.objects.create(
            tenant=tenant,
            source=child,
            target=sibling,
            link_type="allocated-to",
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user, root, child, sibling


def _blocking_finding(workspace: Workspace, ctx: AuthContext):
    from application.audit_service import AuditService
    from traceability.audit import AuditScope

    findings = AuditService().blocking_findings(
        workspace.id, ctx, scopes=[AuditScope("project")]
    )
    assert findings, "expected the real auditor to report blockers"
    return findings[0]


def _call(view_cls, method: str, workspace, ctx, *, body=None, query=""):
    factory = APIRequestFactory()
    url = (WAIVER_URL if view_cls is WorkspaceAuditWaiverView else AUDIT_URL).format(
        ws=workspace.id
    ) + query
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


def _valid_waiver_body(finding, **overrides: Any) -> dict:
    body = {
        "rule_id": finding.rule_id,
        "artifact_ids": list(finding.artifact_ids),
        "reason": (
            f"Accepted deviation for {finding.rule_id}; reviewed and signed "
            "off in the 2026-09-22 architecture board."
        ),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# E1 / E2 / AC-569-04 — create + idempotency + audit interception
# ---------------------------------------------------------------------------


class TestWaiverCreate:
    def test_create_is_201_and_audit_details_carry_the_trail(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        with patch(
            "application.audit_service.ServiceBase._audit"
        ) as mock_audit:
            resp = _call(
                WorkspaceAuditWaiverView,
                "post",
                workspace,
                ctx,
                body=_valid_waiver_body(finding),
            )

        assert resp.status_code == 201, resp.data
        assert resp.data["rule_id"] == finding.rule_id
        assert resp.data["granted_by"] == str(user.id)
        assert resp.data["state"] == "active"
        # Intercepted audit call — NOT a persisted entry (see module docstring).
        waiver_calls = [
            c
            for c in mock_audit.call_args_list
            if c.kwargs.get("operation") == "baseline.waiver_create"
        ]
        assert len(waiver_calls) == 1
        call = waiver_calls[0]
        assert call.kwargs["entity_type"] == "BaselineGateWaiver"
        assert call.kwargs["change_reason"] == _valid_waiver_body(finding)["reason"]
        assert call.kwargs["details"]["granted_by"] == str(user.id)
        assert call.kwargs["details"]["finding_key"] == resp.data["finding_key"]

        rows = BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)
        assert rows.count() == 1

    def test_idempotent_replay_is_200_without_a_second_audit_entry(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)
        body = _valid_waiver_body(finding)

        with patch("application.audit_service.ServiceBase._audit") as mock_audit:
            first = _call(
                WorkspaceAuditWaiverView, "post", workspace, ctx, body=body
            )
            second = _call(
                WorkspaceAuditWaiverView, "post", workspace, ctx, body=body
            )

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.data["waiver_id"] == first.data["waiver_id"]
        assert BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).count() == 1
        waiver_calls = [
            c
            for c in mock_audit.call_args_list
            if c.kwargs.get("operation") == "baseline.waiver_create"
        ]
        assert len(waiver_calls) == 1

    def test_original_reason_and_author_survive_a_different_replay(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)
        first_body = _valid_waiver_body(finding)
        _call(WorkspaceAuditWaiverView, "post", workspace, ctx, body=first_body)

        second_body = _valid_waiver_body(
            finding, reason="A completely different second justification sentence."
        )
        resp = _call(
            WorkspaceAuditWaiverView, "post", workspace, ctx, body=second_body
        )

        assert resp.status_code == 200
        row = BaselineGateWaiver.unscoped.get(workspace_id=workspace.id)
        assert row.reason == first_body["reason"]
        assert row.granted_by == str(user.id)


# ---------------------------------------------------------------------------
# E3 / E4 / E5 / E8 — the disjoint error contract (never 422)
# ---------------------------------------------------------------------------


class TestWaiverErrorContract:
    @pytest.mark.parametrize(
        "reason",
        [
            "ok",
            "aaaaaaaaaaaaaaa",
            "test test test",
            "   ",
            "TRACE-P1 TRACE-P2",
        ],
    )
    def test_placeholder_reason_is_rejected_with_400_and_dedicated_code(
        self, reason
    ):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding, reason=reason),
        )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "WAIVER_REASON_REJECTED"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_waiver_for_an_unreported_finding_is_rejected_with_dedicated_code(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body={
                "rule_id": "CONS-P11",
                "artifact_ids": [str(uuid.uuid4())],
                "reason": "Accepted deviation for a finding that is not reported.",
            },
        )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "WAIVER_FINDING_NOT_BLOCKING"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_waiver_for_a_warning_finding_is_rejected_with_dedicated_code(self):
        from traceability.audit import Finding, Severity

        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        class _Result:
            findings = [
                Finding(
                    rule_id="TRACE-P1",
                    severity=Severity.WARNING,
                    message="warning only",
                    artifact_ids=("art-1",),
                )
            ]

        with patch(
            "application.audit_service.AuditService._run_engine_uncapped",
            return_value=_Result(),
        ):
            resp = _call(
                WorkspaceAuditWaiverView,
                "post",
                workspace,
                ctx,
                body={
                    "rule_id": "TRACE-P1",
                    "artifact_ids": ["art-1"],
                    "reason": "Accepted deviation for a non-blocking warning only.",
                },
            )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "WAIVER_FINDING_NOT_BLOCKING"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_expired_existing_waiver_returns_409(self):
        from datetime import datetime, timedelta, timezone as dt_timezone

        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)
        BaselineGateWaiver.unscoped.create(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            finding_key=finding_key(finding.rule_id, finding.artifact_ids),
            rule_id=finding.rule_id,
            artifact_ids=list(finding.artifact_ids),
            scope="project",
            scope_artifact_id="",
            reason="An earlier justification that has since expired.",
            granted_by=str(user.id),
            expires_at=datetime.now(dt_timezone.utc) - timedelta(days=1),
        )

        with patch("application.audit_service.ServiceBase._audit") as mock_audit:
            resp = _call(
                WorkspaceAuditWaiverView,
                "post",
                workspace,
                ctx,
                body=_valid_waiver_body(finding),
            )

        assert resp.status_code == 409, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "SUPPRESSION_EXPIRED"
        assert BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).count() == 1
        assert not [
            c
            for c in mock_audit.call_args_list
            if c.kwargs.get("operation") == "baseline.waiver_create"
        ]

    def test_unknown_field_and_granted_by_are_rejected_with_400(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding, granted_by=str(uuid.uuid4())),
        )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    @pytest.mark.parametrize(
        "body",
        [
            {"rule_id": "TRACE-P1"},  # reason missing
            {"rule_id": "TRACE-P1", "reason": ["not", "a", "string"]},  # wrong type
            {
                "rule_id": "TRACE-P1",
                "reason": "A perfectly valid justification sentence here.",
                "scope": "not-a-scope",
            },
        ],
    )
    def test_malformed_body_is_400_validation_error(self, body):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        resp = _call(WorkspaceAuditWaiverView, "post", workspace, ctx, body=body)

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"

    def test_document_scope_without_artifact_id_is_400_validation_error(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding, scope="document"),
        )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    @pytest.mark.parametrize(
        "expires_at",
        [
            "2000-01-01T00:00:00Z",  # already in the past
            "2099-01-01T00:00:00",  # naive (no offset)
        ],
    )
    def test_past_or_naive_expires_at_is_rejected(self, expires_at):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding, expires_at=expires_at),
        )

        assert resp.status_code == 400, resp.data
        assert resp.status_code != 422
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_future_expires_at_is_accepted(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding, expires_at="2099-01-01T00:00:00Z"),
        )

        assert resp.status_code == 201, resp.data
        assert resp.data["expires_at"] is not None


# ---------------------------------------------------------------------------
# E6 / E7 / E12 / E13 — authority and tenant isolation
# ---------------------------------------------------------------------------


class TestWaiverAuthorization:
    def test_editor_waiver_is_rejected_with_403(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id, roles=("editor",))
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding),
        )

        assert resp.status_code == 403, resp.data
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_author_tier_api_key_is_rejected_with_403(self):
        """#865: an AUTHOR-tier key may not perform the governance operation."""
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(
            user.id, workspace.tenant_id, roles=("admin",), scope="author"
        )
        finding = _blocking_finding(workspace, ctx)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding),
        )

        assert resp.status_code == 403, resp.data
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_foreign_workspace_create_is_404(self):
        tenant_a, _, user_a = _broken_extended_workspace()
        _, workspace_b, _ = _broken_extended_workspace()
        ctx = _auth_context(user_a.id, tenant_a.id)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace_b,
            ctx,
            body={
                "rule_id": "TRACE-P1",
                "artifact_ids": [],
                "reason": "A justification for a workspace in a foreign tenant.",
            },
        )

        assert resp.status_code == 404, resp.data
        assert resp.data["error"]["code"] == "NOT_FOUND"

    def test_list_requires_approval_authority(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id, roles=("editor",))

        resp = _call(WorkspaceAuditWaiverView, "get", workspace, ctx)

        assert resp.status_code == 403, resp.data
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"

    def test_foreign_workspace_list_is_404(self):
        tenant_a, _, user_a = _broken_extended_workspace()
        _, workspace_b, _ = _broken_extended_workspace()
        ctx = _auth_context(user_a.id, tenant_a.id)

        resp = _call(WorkspaceAuditWaiverView, "get", workspace_b, ctx)

        assert resp.status_code == 404, resp.data
        assert resp.data["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# E9 / E19 / E20 — the 500 rows
# ---------------------------------------------------------------------------


class TestWaiverServerErrors:
    def test_create_unexpected_error_is_500(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)

        with patch(
            "application.audit_service.AuditService.suppress_finding",
            side_effect=RuntimeError("boom"),
        ):
            resp = _call(
                WorkspaceAuditWaiverView,
                "post",
                workspace,
                ctx,
                body=_valid_waiver_body(finding),
            )

        assert resp.status_code == 500, resp.data
        assert resp.data["error"]["code"] == "INTERNAL_SERVER_ERROR"

    def test_list_unexpected_error_is_500(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        with patch(
            "application.audit_service.AuditService.list_suppressions",
            side_effect=RuntimeError("boom"),
        ):
            resp = _call(WorkspaceAuditWaiverView, "get", workspace, ctx)

        assert resp.status_code == 500, resp.data
        assert resp.data["error"]["code"] == "INTERNAL_SERVER_ERROR"

    def test_report_unexpected_error_is_500(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        with patch(
            "application.audit_service.AuditService.run_audit",
            side_effect=RuntimeError("boom"),
        ):
            resp = _call(WorkspaceAuditView, "get", workspace, ctx)

        assert resp.status_code == 500, resp.data
        assert resp.data["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# E10 / E11 / AC-569-05 — list contract
# ---------------------------------------------------------------------------


def _insert_waiver(workspace, user, *, suffix, expires_at=None, scope="project"):
    return BaselineGateWaiver.unscoped.create(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        finding_key=f"TRACE-P1\x1f{suffix}",
        rule_id="TRACE-P1",
        artifact_ids=[suffix],
        scope=scope,
        scope_artifact_id="",
        reason=f"A justification recorded for finding {suffix}.",
        granted_by=str(user.id),
        expires_at=expires_at,
    )


class TestWaiverList:
    def test_list_filters_by_state_and_renders_identity_key(self):
        from datetime import datetime, timedelta, timezone as dt_timezone

        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        _insert_waiver(workspace, user, suffix="a1")
        _insert_waiver(
            workspace,
            user,
            suffix="a2",
            expires_at=datetime.now(dt_timezone.utc) - timedelta(days=1),
        )

        default = _call(WorkspaceAuditWaiverView, "get", workspace, ctx)
        expired = _call(
            WorkspaceAuditWaiverView, "get", workspace, ctx, query="?state=expired"
        )
        all_states = _call(
            WorkspaceAuditWaiverView, "get", workspace, ctx, query="?state=all"
        )

        assert default.status_code == 200, default.data
        assert [w["state"] for w in default.data["waivers"]] == ["active"]
        assert expired.status_code == 200
        assert [w["state"] for w in expired.data["waivers"]] == ["expired"]
        assert all_states.status_code == 200
        assert len(all_states.data["waivers"]) == 2
        assert all_states.data["counts"] == {"active": 1, "expired": 1}

        row = all_states.data["waivers"][0]
        assert row["finding_key"] == "TRACE-P1\x1fa1"
        # identity_key carries the scope; the persisted finding_key does not.
        assert row["identity_key"] == "TRACE-P1\x1fa1\x1fproject"
        assert row["identity_key"] != row["finding_key"]

    def test_list_rejects_unknown_state_with_400(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        resp = _call(
            WorkspaceAuditWaiverView, "get", workspace, ctx, query="?state=banana"
        )

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# E14 / E15 / AC-569-13 / AC-569-22 / AC-569-27 — report extension
# ---------------------------------------------------------------------------


class TestReportSuppressionExtension:
    def _create_waiver(self, workspace, ctx, finding):
        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body=_valid_waiver_body(finding),
        )
        assert resp.status_code == 201, resp.data

    def test_report_marks_suppressed_findings_by_default(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)
        self._create_waiver(workspace, ctx, finding)

        resp = _call(WorkspaceAuditView, "get", workspace, ctx)

        assert resp.status_code == 200, resp.data
        suppressed = [f for f in resp.data["findings"] if f["suppressed"]]
        assert len(suppressed) == 1
        marked = suppressed[0]
        assert marked["rule_id"] == finding.rule_id
        assert marked["suppression_reason"]
        assert marked["suppression_id"]
        assert marked["suppressed_until"] is None
        counts = resp.data["counts"]
        assert counts["blockers"] + counts["warnings"] == counts["total"]
        assert counts["suppressed"] >= 1
        assert counts["suppressed_blockers"] >= 1

    def test_counts_stay_descriptive_and_totals_stay_absolute_when_filtered(self):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)
        finding = _blocking_finding(workspace, ctx)
        self._create_waiver(workspace, ctx, finding)

        filtered = _call(
            WorkspaceAuditView,
            "get",
            workspace,
            ctx,
            query="?include_suppressed=false",
        )

        assert filtered.status_code == 200, filtered.data
        assert all(not f["suppressed"] for f in filtered.data["findings"])
        counts = filtered.data["counts"]
        # (i) unconditional identity — Severity is binary.
        assert counts["blockers"] + counts["warnings"] == counts["total"]
        assert counts["total"] == len(filtered.data["findings"])
        # (ii) m7: the window is smaller than the full run, explained by the filter.
        assert filtered.data["suppressed_filtered"] >= 1
        assert (
            filtered.data["total_findings_available"]
            == len(filtered.data["findings"])
            + filtered.data["suppressed_filtered"]
        )
        assert (
            counts["total"] != filtered.data["total_findings_available"]
        )

    @pytest.mark.parametrize(
        ("query", "expected_status"),
        [
            ("?include_suppressed=true", 200),
            ("?include_suppressed=false", 200),
            ("?include_suppressed=TRUE", 200),
            ("", 200),
            ("?include_suppressed=1", 400),
            ("?include_suppressed=yes", 400),
            ("?include_suppressed=banana", 400),
        ],
    )
    def test_include_suppressed_query_parsing(self, query, expected_status):
        _, workspace, user = _broken_extended_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        resp = _call(WorkspaceAuditView, "get", workspace, ctx, query=query)

        assert resp.status_code == expected_status, resp.data
        if expected_status == 400:
            assert resp.data["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# AC-569-17 — document-scoped findings are waivable
# ---------------------------------------------------------------------------


class TestDocumentScopedWaiver:
    def test_document_scoped_finding_is_waivable(self):
        _, workspace, user, root, child, sibling = _document_scoped_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body={
                "rule_id": "TRACE-P7",
                "artifact_ids": [str(child.id), str(sibling.id)],
                "scope": "document",
                "scope_artifact_id": str(root.id),
                "reason": (
                    "Cross-scope link accepted until the document subtree is "
                    "re-cut in the next baseline."
                ),
            },
        )

        assert resp.status_code == 201, resp.data
        assert resp.data["scope"] == "document"
        assert resp.data["scope_artifact_id"] == str(root.id)
        row = BaselineGateWaiver.unscoped.get(workspace_id=workspace.id)
        assert row.scope == "document"
        assert row.scope_artifact_id == str(root.id)

    def test_scope_agnostic_call_creates_no_document_scoped_row(self):
        _, workspace, user, root, child, sibling = _document_scoped_workspace()
        ctx = _auth_context(user.id, workspace.tenant_id)

        # Without the document scope the engine's project default does not
        # report the TRACE-P7 finding, so the request is a 400 and stores
        # nothing — never a document-scoped row.
        resp = _call(
            WorkspaceAuditWaiverView,
            "post",
            workspace,
            ctx,
            body={
                "rule_id": "TRACE-P7",
                "artifact_ids": [str(child.id), str(sibling.id)],
                "reason": "Scope-less attempt that must not create a document row.",
            },
        )

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "WAIVER_FINDING_NOT_BLOCKING"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()
