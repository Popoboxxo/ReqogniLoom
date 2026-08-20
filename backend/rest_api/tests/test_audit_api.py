"""
SE-Auditor REST endpoints (SysEng 2.0 Phase 3) — HTTP boundary tests.

Covers:
  GET  /api/v1/workspaces/<id>/audit/            -> findings + remediation
  POST /api/v1/workspaces/<id>/audit/remediate/  -> Adopt (200) + refusal (422)

Uses APIRequestFactory with a pre-attached AuthContext (unit-style boundary
tests, mirroring rest_api/tests/test_change_request_api.py) against real data,
so the endpoints exercise the AuditService end to end.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from rest_api.audit_views import WorkspaceAuditRemediateView, WorkspaceAuditView
from traceability.audit.registry import TRACE_P5
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Audit API Tenant", slug="audit-api-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="audit-api-user", email="audit-api@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    # The audit endpoint derives the rigor tier from the workspace preset (no
    # tier query param by design). Switch to Extended so the extended-only
    # TRACE-P5 rule is active and the endpoint behaviour is deterministic.
    from presets.services import switch_preset

    with _active(tenant):
        ws = Workspace.objects.create(tenant=tenant, name="Audit-API-WS")
        switch_preset(str(ws.id), "extended")
        return ws


def _ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _p5_scenario(tenant, workspace):
    """Parent -decomposes-> child, no derives-from: raises exactly TRACE-P5."""
    def _req(title):
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        return Requirement.objects.create(tenant=tenant, artifact=art, title=title)

    parent = _req("Parent")
    child = _req("Child")
    TraceLink.objects.create(
        tenant=tenant,
        source=parent.artifact,
        target=child.artifact,
        link_type=LinkType.DECOMPOSES.value,
    )
    return parent, child


class TestAuditGetEndpoint:
    def test_get_returns_200_with_findings(self, tenant, workspace, user):
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        body = resp.data
        assert "findings" in body and body["counts"]["total"] >= 1
        rule_ids = {f["rule_id"] for f in body["findings"]}
        assert TRACE_P5 in rule_ids

    def test_get_rejects_document_scope_without_artifact(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=document"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400

    def test_get_with_limit_returns_a_windowed_response(self, tenant, workspace, user):
        """#622: ?limit=&offset= page past the default truncation cap."""
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=1&offset=0"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        body = resp.data
        assert len(body["findings"]) == 1
        assert body["offset"] == 0

    def test_get_without_limit_omits_pagination_effect(self, tenant, workspace, user):
        """No ?limit= must behave exactly as before #622 (offset always 0)."""
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        assert resp.data["offset"] == 0

    def test_get_rejects_non_integer_limit(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=not-a-number"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400

    def test_get_rejects_non_integer_offset(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=10&offset=abc"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400


class TestAuditRemediateEndpoint:
    def test_post_adopts_trace_p5_and_returns_200(self, tenant, workspace, user):
        with _active(tenant):
            parent, child = _p5_scenario(tenant, workspace)
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={
                    "rule_id": TRACE_P5,
                    "artifact_ids": [str(child.artifact_id), str(parent.artifact_id)],
                },
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

            assert resp.status_code == 200
            assert resp.data["applied"] is True
            assert resp.data["finding_resolved"] is True
            assert TraceLink.objects.filter(
                source_id=child.artifact_id,
                target_id=parent.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

    def test_post_returns_422_when_not_auto_remediable(self, tenant, workspace, user):
        with _active(tenant):
            # TRACE-P4 has no registered remediation -> 422 (manual/Modify).
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={"rule_id": "TRACE-P4", "artifact_ids": ["not-a-real-id"]},
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

        assert resp.status_code == 422

    def test_post_validates_missing_artifact_ids(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={"rule_id": TRACE_P5, "artifact_ids": []},
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

        assert resp.status_code == 400
