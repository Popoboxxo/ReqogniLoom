"""
Tests for the shared test-factory helpers (``persistence.tests.factories``).

These helpers are imported verbatim by several later feature tasks (see
``.superpowers/sdd/2026-08-24-ai-memory-and-search/task-0-brief.md``), so this
suite locks down their exact behaviour and call shapes.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from persistence.models import User, Workspace
from persistence.tenancy import TenantContextNotSetError
from persistence.tests.factories import (
    active_tenant,
    admin_user_and_token,
    assign_role,
    ctx_for_user,
    editor_ctx,
    editor_user_and_token,
    make_requirement,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.django_db


class TestActiveTenant:
    def test_creates_and_activates_a_real_tenant(self) -> None:
        with active_tenant() as tenant:
            assert tenant.pk is not None
            assert tenant.is_active is True
            # Tenant-scoped query succeeds inside the block.
            ws = make_workspace(tenant)
            assert Workspace.objects.filter(pk=ws.pk).count() == 1

    def test_deactivates_on_exit(self) -> None:
        with active_tenant() as tenant:
            make_workspace(tenant)

        # No active context anymore -> tenant-scoped query must raise before
        # hitting the DB (REQ-L3-PL002-002, matches test_tenant_isolation.py).
        with pytest.raises(TenantContextNotSetError):
            list(Workspace.objects.all())


class TestMakeUserAndWorkspace:
    def test_make_user_creates_real_row_scoped_to_tenant(self) -> None:
        with active_tenant() as tenant:
            user = make_user(tenant)
            assert user.pk is not None
            assert user.tenant_id == tenant.id
            assert User.objects.filter(pk=user.pk).exists()

    def test_make_user_kwargs_override_defaults(self) -> None:
        with active_tenant() as tenant:
            user = make_user(tenant, username="explicit-name")
            assert user.username == "explicit-name"

    def test_make_workspace_creates_real_row_scoped_to_tenant(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            assert ws.pk is not None
            assert ws.tenant_id == tenant.id
            assert Workspace.objects.filter(pk=ws.pk).exists()


class TestAssignRole:
    def test_not_suspended_leaves_suspended_at_none(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            assign_role(user, ws, "editor", suspended=False)
            role = UserRole.objects.get(user=user, workspace=ws)
            assert role.role == "editor"
            assert role.suspended_at is None

    def test_suspended_sets_a_real_timestamp(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            assign_role(user, ws, "viewer", suspended=True)
            role = UserRole.objects.get(user=user, workspace=ws)
            assert role.suspended_at is not None


class TestAuthContextHelpers:
    def test_editor_ctx_has_editor_role_and_right_ids(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            assert isinstance(ctx, AuthContext)
            assert ctx.has_role("editor")
            assert ctx.tenant_id == tenant.id
            assert ctx.workspace_id == ws.id
            # A matching UserRole row was persisted.
            assert UserRole.objects.filter(
                user_id=ctx.user_id, workspace=ws, role="editor"
            ).exists()

    def test_editor_ctx_uses_given_user(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = editor_ctx(tenant, ws, user=user)
            assert ctx.user_id == user.id

    def test_editor_ctx_without_workspace_still_builds_context(self) -> None:
        with active_tenant() as tenant:
            ctx = editor_ctx(tenant)
            assert ctx.has_role("editor")
            assert ctx.workspace_id is None

    def test_ctx_for_user_two_users_two_contexts(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user_a = make_user(tenant)
            user_b = make_user(tenant)
            ctx_a = ctx_for_user(tenant, user_a, workspace=ws, roles=("editor",))
            ctx_b = ctx_for_user(tenant, user_b, workspace=ws, roles=("viewer",))
            assert ctx_a.user_id == user_a.id
            assert ctx_a.has_role("editor")
            assert ctx_b.user_id == user_b.id
            assert ctx_b.has_role("viewer")
            assert ctx_a.user_id != ctx_b.user_id


class TestUserAndTokenHelpers:
    def test_admin_user_and_token_authenticates_and_is_admin(self) -> None:
        with active_tenant() as tenant:
            pass
        user, token = admin_user_and_token(tenant)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Any authenticated user can GET the theme-palette list.
        list_response = client.get("/api/v1/admin/theme-palettes/")
        assert list_response.status_code == 200

        # The tenant-wide theme default PUT is admin-only -> proves the admin role.
        put_response = client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "default", "mode": "dark"},
            format="json",
        )
        assert put_response.status_code == 200, put_response.content
        assert user.pk is not None

    def test_editor_user_and_token_authenticates_but_is_not_admin(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
        user, token = editor_user_and_token(tenant, ws)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        list_response = client.get("/api/v1/admin/theme-palettes/")
        assert list_response.status_code == 200

        put_response = client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "default", "mode": "dark"},
            format="json",
        )
        assert put_response.status_code == 403
        assert user.pk is not None

    def test_editor_user_and_token_without_workspace(self) -> None:
        with active_tenant() as tenant:
            pass
        user, token = editor_user_and_token(tenant)
        assert user.pk is not None
        assert token


class TestMakeRequirement:
    def test_creates_real_requirement_with_title(self) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="My Requirement", description="Some desc")
            assert req.pk is not None
            assert req.title == "My Requirement"
            assert req.description == "Some desc"
            assert req.artifact_id is not None
