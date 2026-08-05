"""URL routing tests for BaselineViewSet workspace-scoping (issue #49).

Baselines were only reachable at the flat, root-level route
(``/api/v1/baselines/?workspace_id=<id>``), unlike Needs, Permissions, Audit,
Import/Export and Architecture-Decompose which are additionally reachable via
a nested ``/api/v1/workspaces/{id}/...`` route. Requesting
``/api/v1/workspaces/{id}/baselines/`` 404ed.

Fix: register a nested ``workspaces/<workspace_pk>/baselines/`` route
(rest_api/urls.py) that maps to ``BaselineViewSet.list``/``create``, and have
those methods read ``workspace_pk`` from the URL kwargs (falling back to the
flat route's ``?workspace_id=`` query param / body field). The flat route is
kept for backward compatibility (frontend/MCP callers use ?workspace_id=).
"""
from __future__ import annotations

import uuid

import pytest
from django.urls import resolve
from rest_framework.test import APIRequestFactory

from rest_api.views import BaselineViewSet


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def test_nested_baselines_route_resolves_to_baseline_viewset() -> None:
    """GET /api/v1/workspaces/<id>/baselines/ must resolve (issue #49)."""
    ws_id = uuid.uuid4()
    match = resolve(f"/api/v1/workspaces/{ws_id}/baselines/")
    assert match.func.cls.__name__ == "BaselineViewSet"
    assert str(match.kwargs["workspace_pk"]) == str(ws_id)


@pytest.mark.django_db
def test_nested_list_route_returns_200_with_only_own_workspace_baselines() -> None:
    """GET /api/v1/workspaces/<id>/baselines/ returns 200 and is scoped to
    that workspace only — a baseline belonging to a sibling workspace in the
    same tenant must not leak into the response (issue #49)."""
    from application.baseline_facade import BaselineFacade
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(), name="issue49-tenant", slug=f"issue49-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            id=uuid.uuid4(), tenant=tenant, name="issue49-ws-a", preset={"name": "standard"}
        )
        ws_b = Workspace.objects.create(
            id=uuid.uuid4(), tenant=tenant, name="issue49-ws-b", preset={"name": "standard"}
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"issue49-{uuid.uuid4().hex[:8]}",
            email="issue49@example.com",
        )
    finally:
        TenantContext.clear_tenant()

    ctx = _auth_context(user.id, tenant.id)
    facade = BaselineFacade()
    baseline_a_id = facade.create_baseline(
        scope="project", workspace_id=ws_a.id, name="issue49-baseline-a", ctx=ctx
    )
    facade.create_baseline(
        scope="project", workspace_id=ws_b.id, name="issue49-baseline-b", ctx=ctx
    )

    factory = APIRequestFactory()
    req = factory.get(f"/api/v1/workspaces/{ws_a.id}/baselines/")
    req.auth_context = ctx
    view = BaselineViewSet.as_view({"get": "list"})
    # The preset gate (PresetGateMixin._guard_preset) resolves the workspace
    # preset via a tenant-scoped DB query; in production this runs inside the
    # request/response cycle where persistence.middleware has already set the
    # thread-local TenantContext, but a direct view() call bypasses that
    # middleware, so the test sets it explicitly (mirrors service-layer calls
    # like BaselineFacade._set_tenant_context()).
    from persistence.tenancy import TenantContext as _TenantContext

    _TenantContext.set_tenant(tenant.id)
    try:
        response = view(req, workspace_pk=str(ws_a.id))
    finally:
        _TenantContext.clear_tenant()

    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.data["results"]}
    assert str(baseline_a_id) in returned_ids
    assert len(returned_ids) == 1


@pytest.mark.django_db
def test_nested_create_route_uses_workspace_pk_from_url() -> None:
    """POST /api/v1/workspaces/<id>/baselines/ creates a baseline in that
    workspace even when the body omits workspace_id (issue #49)."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(), name="issue49-create-tenant", slug=f"issue49-create-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(), tenant=tenant, name="issue49-create-ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"issue49-create-{uuid.uuid4().hex[:8]}",
            email="issue49-create@example.com",
        )
    finally:
        TenantContext.clear_tenant()

    ctx = _auth_context(user.id, tenant.id)
    factory = APIRequestFactory()
    req = factory.post(
        f"/api/v1/workspaces/{workspace.id}/baselines/",
        data={"scope": "project", "name": "issue49-nested-create"},
        format="json",
    )
    req.auth_context = ctx
    view = BaselineViewSet.as_view({"post": "create"})
    from persistence.tenancy import TenantContext as _TenantContext

    _TenantContext.set_tenant(tenant.id)
    try:
        response = view(req, workspace_pk=str(workspace.id))
    finally:
        _TenantContext.clear_tenant()

    assert response.status_code == 201
    assert response.data["workspace_id"] == str(workspace.id)
