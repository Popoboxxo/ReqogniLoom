"""#878 / Plan B B2-T2 — REST action ``GET /api/v1/needs/validation-coverage/``.

Follows the ``requirements/coverage-report/`` pattern: a workspace-scoped
summary plus one row per active StakeholderNeed. Errors: 400 for a missing or
malformed ``workspace_id``, 404 for a workspace that is not the caller's.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(authed_client, tenant, workspace):
    """Two needs, one validated by a manual TestCase."""
    from application.stakeholder_need_service import StakeholderNeedService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import User

    set_request_tenant(tenant.id)
    try:
        user = User.objects.filter(tenant=tenant).first()
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        needs = StakeholderNeedService()
        validated = needs.create(ctx=ctx, workspace_id=workspace.id, title="Validated need")
        needs.create(ctx=ctx, workspace_id=workspace.id, title="Unvalidated need")

        test_cases = TestService()
        test_case = test_cases.create_test_case(
            workspace_id=workspace.id, title="Validating TC", ctx=ctx
        )

        links = TraceLinkService()
        links.create_trace_link(
            source_id=test_case.artifact_id,
            target_id=validated.artifact_id,
            link_type="validates",
            ctx=ctx,
        )
    finally:
        clear_request_tenant()
    return authed_client, workspace, validated


def _get(client, workspace, **params):
    query = {"workspace_id": str(workspace.id), **params}
    return client.get("/api/v1/needs/validation-coverage/", query)


def test_response_shape(seeded):
    client, workspace, validated = seeded

    resp = _get(client, workspace)
    assert resp.status_code == 200, resp.content
    body = resp.json()

    # Exactly the documented envelope.
    assert set(body) == {"summary", "needs"}
    assert body["summary"]["total"] == 2
    assert body["summary"]["covered"] == 1
    assert body["summary"]["percentage"] == 50.0
    assert body["summary"]["pending_ai_review"] == 0

    assert len(body["needs"]) == 2
    assert set(body["needs"][0]) == {"need_id", "uid", "title", "test_cases"}

    by_title = {row["title"]: row for row in body["needs"]}
    covered = by_title["Validated need"]
    assert covered["need_id"] == str(validated.id)
    assert covered["uid"].startswith("NEED-")
    assert len(covered["test_cases"]) == 1
    assert set(covered["test_cases"][0]) == {"id", "title", "latest_result"}
    assert covered["test_cases"][0]["title"] == "Validating TC"

    assert by_title["Unvalidated need"]["test_cases"] == []


def test_requires_a_workspace_id(authed_client):
    resp = authed_client.get("/api/v1/needs/validation-coverage/")
    assert resp.status_code == 400, resp.content


def test_rejects_a_malformed_workspace_id(authed_client):
    resp = authed_client.get(
        "/api/v1/needs/validation-coverage/", {"workspace_id": "not-a-uuid"}
    )
    assert resp.status_code == 400, resp.content


def test_404_for_a_foreign_workspace(seeded):
    """A workspace of another tenant is indistinguishable from "unknown"."""
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, Workspace

    client, _workspace, _validated = seeded
    other_tenant = Tenant.objects.create(
        name="Foreign tenant", slug=f"foreign-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(other_tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=other_tenant, name="Foreign WS")
    finally:
        clear_request_tenant()

    resp = client.get(
        "/api/v1/needs/validation-coverage/", {"workspace_id": str(foreign.id)}
    )
    assert resp.status_code == 404, resp.content


def _login_same_tenant_non_member(tenant) -> APIClient:
    """An ``APIClient`` for a same-tenant user with no role in *tenant*'s
    seeded workspace (their admin role sits in a separate workspace)."""
    from auth_tenancy.models import ROLE_ADMIN, UserRole
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import User, Workspace

    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"cv-stranger-{suffix}",
        email=f"cv-stranger-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        own = Workspace.objects.create(tenant=tenant, name=f"Stranger WS {suffix}")
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=own, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def test_403_for_a_caller_without_read_permission(seeded):
    """A same-tenant non-member gets 403, never an empty 200.

    ``workspace_id`` is a query parameter, so ``auth_tenancy.workspace_scope``
    narrows the caller's roles to that workspace and a non-member resolves to
    no role at all — the RBAC matrix refuses before the view body runs.
    """
    _client, workspace, _validated = seeded
    stranger = _login_same_tenant_non_member(workspace.tenant)

    resp = _get(stranger, workspace)

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_flags_are_honoured(seeded):
    """``include_unreviewed_ai`` switches to the raw view."""
    from application.test_service import TestService
    from application.stakeholder_need_service import StakeholderNeedService
    from application.trace_link_service import TraceLinkService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import User

    client, workspace, _validated = seeded
    tenant_id = workspace.tenant_id
    set_request_tenant(tenant_id)
    try:
        user = User.objects.filter(tenant_id=tenant_id).first()
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant_id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        need = StakeholderNeedService().create(
            ctx=ctx, workspace_id=workspace.id, title="AI-only need"
        )
        ai_tc = TestService().create_test_case(
            workspace_id=workspace.id, title="AI TC", ctx=ctx, origin="ai_generated"
        )
        TraceLinkService().create_trace_link(
            source_id=ai_tc.artifact_id,
            target_id=need.artifact_id,
            link_type="validates",
            ctx=ctx,
        )
    finally:
        clear_request_tenant()

    default = _get(client, workspace).json()
    assert default["summary"]["pending_ai_review"] == 1

    raw = _get(client, workspace, include_unreviewed_ai="true").json()
    assert raw["summary"]["pending_ai_review"] == 0
    assert raw["summary"]["covered"] == default["summary"]["covered"] + 1
