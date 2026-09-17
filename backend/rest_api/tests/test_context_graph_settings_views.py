"""Issue #377 (Workspace Context Graph, Task 9) — settings REST endpoint tests.

Covers:
- GET/PUT /api/v1/workspaces/{workspace_id}/context-graph-settings/ (admin-only).
- GET with no row yet returns defaults (enabled=False) WITHOUT creating a row.
- PUT enabling for the first time triggers an async rebuild (mocked .delay).
- PUT disabling does not delete existing ContextEdge rows.
- POST .../rebuild/ triggers a manual rebuild (202) without touching `enabled`.
- Non-admin roles are rejected with 403.
- Unknown generator name is rejected with 400.

Same JWT + APIClient pattern as test_review_policy_views.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

# transaction=True (not the default django_db): update_settings() schedules
# the rebuild task via transaction.on_commit, which never fires inside the
# default rolled-back-per-test wrapping transaction.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def cg_settings_tenant(db):
    tenant = Tenant.objects.create(name="CG T", slug="cg-t", is_active=True)
    admin = User.objects.create(username="cgadmin", email="cgadmin@t.test", tenant=tenant)
    admin.set_password("cgpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(username="cgeditor", email="cgeditor@t.test", tenant=tenant)
    editor.set_password("cgpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="CG WS")
        UserRole.objects.create(tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN)
        UserRole.objects.create(tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR)
        yield tenant, workspace
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/", {"username": username, "password": "cgpass123"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@override_settings(**_JWT_OVERRIDES)
def test_get_with_no_row_returns_defaults_without_creating_one(cg_settings_tenant):
    from context_graph.models import WorkspaceContextSettings

    tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/context-graph-settings/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["enabled_generators"] == []

    set_request_tenant(tenant.id)
    try:
        assert not WorkspaceContextSettings.objects.filter(workspace_id=workspace.id).exists()
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
def test_admin_enabling_triggers_async_rebuild(cg_settings_tenant):
    from context_graph.models import WorkspaceContextSettings

    tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay") as mock_delay:
        resp = client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": True, "enabled_generators": ["glossary"]},
            format="json",
        )
        assert resp.status_code == 200
        # on_commit callbacks need an actual commit — django's test client
        # wraps each request in TestCase-style atomic() by default only under
        # SimpleTestCase; APIClient requests here run under pytest-django's
        # normal django_db (transactional per-test rollback), and DRF's
        # APIView.dispatch does not open its own atomic block, so on_commit
        # fires synchronously as soon as the view's transaction.on_commit
        # call is made IF no outer atomic is open. Assert after the request.
        mock_delay.assert_called_once_with(str(workspace.id))

    body = resp.json()
    assert body["enabled"] is True
    assert body["enabled_generators"] == ["glossary"]

    set_request_tenant(tenant.id)
    try:
        row = WorkspaceContextSettings.objects.get(workspace_id=workspace.id)
        assert row.enabled is True
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
def test_re_enabling_already_enabled_workspace_does_not_re_trigger_rebuild(cg_settings_tenant):
    tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay") as mock_delay:
        client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": True, "enabled_generators": ["glossary"]},
            format="json",
        )
        mock_delay.assert_called_once()

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay") as mock_delay_2:
        resp = client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": True, "enabled_generators": ["glossary"]},
            format="json",
        )
        assert resp.status_code == 200
        mock_delay_2.assert_not_called()


@override_settings(**_JWT_OVERRIDES)
def test_disabling_does_not_delete_existing_context_edges(cg_settings_tenant):
    from context_graph.models import ContextEdge
    from persistence.models import Artifact

    tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    set_request_tenant(tenant.id)
    try:
        art1 = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Requirement")
        art2 = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Requirement")
        ContextEdge.objects.create(
            tenant=tenant, source=art1, target=art2, edge_kind="shares-term",
            origin="derived-glossary", confidence=1.0, generator="glossary-v1",
        )
    finally:
        clear_request_tenant()

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay"):
        client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": True}, format="json",
        )
        resp = client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": False}, format="json",
        )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    set_request_tenant(tenant.id)
    try:
        assert ContextEdge.objects.filter(source_id=art1.id).exists()
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
def test_unknown_generator_is_rejected(cg_settings_tenant):
    _tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
        {"enabled": True, "enabled_generators": ["not-a-real-generator"]},
        format="json",
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
def test_non_admin_cannot_read_or_update(cg_settings_tenant):
    _tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgeditor"))

    assert (
        client.get(f"/api/v1/workspaces/{workspace.id}/context-graph-settings/").status_code
        == 403
    )
    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
        {"enabled": True}, format="json",
    )
    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
def test_manual_rebuild_endpoint_requires_existing_settings_row(cg_settings_tenant):
    _tenant, workspace = cg_settings_tenant
    client = APIClient()
    _auth(client, _login(client, "cgadmin"))

    # No settings row yet -> 404, not a silent 202.
    resp = client.post(f"/api/v1/workspaces/{workspace.id}/context-graph-settings/rebuild/")
    assert resp.status_code == 404

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay"):
        client.put(
            f"/api/v1/workspaces/{workspace.id}/context-graph-settings/",
            {"enabled": True}, format="json",
        )

    with patch("context_graph.tasks.rebuild_workspace_graph_task.delay") as mock_delay:
        resp = client.post(f"/api/v1/workspaces/{workspace.id}/context-graph-settings/rebuild/")
        assert resp.status_code == 202
        mock_delay.assert_called_once_with(str(workspace.id))
