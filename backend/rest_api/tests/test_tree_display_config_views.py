"""REST surface of the three-level tree-display configuration (Issue #1257).

Covers the three routes end to end against real rows and a real JWT login:

  * ``/api/v1/users/me/tree-display-config/`` — self-service personal level,
  * ``/api/v1/workspaces/<id>/tree-display-config/`` — workspace override,
  * ``/api/v1/system/tree-display-config/`` — tenant-wide default (admin write),

plus the ``?resolve=effective`` read the navigation tree itself performs, and
the fail-closed edges: a viewer may not set a workspace override, and — since
ENT-C3 = B / Plan C T-C2-10 — neither may an editor, whose WRITE is no longer
enough for workspace *configuration* (reading it stays open to every member).
An editor may still not set the tenant-wide default.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.tests.conftest import _role_client

pytestmark = pytest.mark.django_db

USER_PATH = "/api/v1/users/me/tree-display-config/"
SYSTEM_PATH = "/api/v1/system/tree-display-config/"
ITEM_TYPE = "Requirement"
DEFAULT_KEYS = ["uid", "level", "status", "updated_at", "version"]


def workspace_path(workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/tree-display-config/"


def _keys(entries) -> list[str]:
    return [entry["key"] for entry in entries]


# ---------------------------------------------------------------------------
# Personal level (self-service)
# ---------------------------------------------------------------------------


class TestUserLevel:
    def test_get_without_a_row_returns_an_empty_map_and_the_catalogue(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(USER_PATH)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "user"
        assert body["config"] == {}
        assert {entry["key"] for entry in body["catalog"]} >= set(DEFAULT_KEYS)

    def test_patch_stores_and_returns_the_levels_own_value(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_PATH,
            {
                "item_type": ITEM_TYPE,
                "fields": ["status", {"key": "uid", "width": "half"}],
            },
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "user"
        assert body["item_type"] == ITEM_TYPE
        assert _keys(body["fields"]) == ["status", "uid"]
        assert body["fields"][1]["width"] == "half"

        again = admin_client.get(USER_PATH, {"item_type": ITEM_TYPE})
        assert _keys(again.json()["fields"]) == ["status", "uid"]

    def test_patch_with_null_resets_the_entry(
        self, admin_client: APIClient
    ) -> None:
        admin_client.patch(
            USER_PATH, {"item_type": ITEM_TYPE, "fields": ["uid"]}, format="json"
        )
        reset = admin_client.patch(
            USER_PATH, {"item_type": ITEM_TYPE, "fields": None}, format="json"
        )

        assert reset.status_code == 200, reset.content
        assert reset.json()["fields"] is None
        assert admin_client.get(USER_PATH).json()["config"] == {}

    def test_unknown_field_key_is_a_400(self, admin_client: APIClient) -> None:
        response = admin_client.patch(
            USER_PATH,
            {"item_type": ITEM_TYPE, "fields": ["not a key"]},
            format="json",
        )
        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_an_undeclared_body_key_is_a_400(self, admin_client: APIClient) -> None:
        """#851: a typo must not look like a successful save."""
        response = admin_client.patch(
            USER_PATH,
            {"item_type": ITEM_TYPE, "fields": ["uid"], "order": ["uid"]},
            format="json",
        )
        assert response.status_code == 400, response.content

    def test_a_custom_attribute_key_is_accepted(
        self, admin_client: APIClient
    ) -> None:
        """Issue #1257 point 2: custom attributes must be configurable."""
        response = admin_client.patch(
            USER_PATH,
            {"item_type": ITEM_TYPE, "fields": ["my_custom_attribute"]},
            format="json",
        )
        assert response.status_code == 200, response.content
        assert _keys(response.json()["fields"]) == ["my_custom_attribute"]

    def test_an_unauthenticated_call_is_401(self, db) -> None:
        response = APIClient().get(USER_PATH)
        assert response.status_code == 401, response.content


# ---------------------------------------------------------------------------
# Effective resolution — the read the navigation tree performs
# ---------------------------------------------------------------------------


class TestEffectiveResolution:
    def test_effective_without_item_type_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(USER_PATH, {"resolve": "effective"})
        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_an_unknown_resolve_value_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(
            USER_PATH, {"resolve": "everything", "item_type": ITEM_TYPE}
        )
        assert response.status_code == 400, response.content

    def test_effective_falls_back_to_the_builtin_default(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(
            USER_PATH, {"resolve": "effective", "item_type": ITEM_TYPE}
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "default"
        assert _keys(body["fields"]) == DEFAULT_KEYS

    def test_a_personal_selection_is_reported_with_its_level(
        self, admin_client: APIClient
    ) -> None:
        admin_client.patch(
            USER_PATH, {"item_type": ITEM_TYPE, "fields": ["status"]}, format="json"
        )

        body = admin_client.get(
            USER_PATH, {"resolve": "effective", "item_type": ITEM_TYPE}
        ).json()
        assert body["scope"] == "user"
        assert _keys(body["fields"]) == ["status"]


# ---------------------------------------------------------------------------
# Workspace level
# ---------------------------------------------------------------------------


class TestWorkspaceLevel:
    def test_an_admin_may_set_and_read_the_workspace_override(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        path = workspace_path(workspace_fixture)
        response = admin_client.patch(
            path, {"item_type": ITEM_TYPE, "fields": ["uid", "level"]}, format="json"
        )

        assert response.status_code == 200, response.content
        assert response.json()["scope"] == "workspace"
        assert _keys(
            admin_client.get(path, {"item_type": ITEM_TYPE}).json()["fields"]
        ) == ["uid", "level"]

    def test_an_editor_may_not_set_the_workspace_override(
        self, editor_client: APIClient, workspace_fixture
    ) -> None:
        """ENT-C3 = B: a workspace default is configuration, not content.

        Reading the level stays open to every member (the next test proves
        that); writing it needs the workspace admin.
        """
        path = workspace_path(workspace_fixture)
        response = editor_client.patch(
            path, {"item_type": ITEM_TYPE, "fields": ["uid", "level"]}, format="json"
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
        assert editor_client.get(path, {"item_type": ITEM_TYPE}).status_code == 200

    def test_the_workspace_override_wins_in_the_effective_read(
        self, admin_client: APIClient, editor_client: APIClient, workspace_fixture
    ) -> None:
        """Precedence ``workspace > global`` observed through the real routes."""
        admin_client.patch(
            SYSTEM_PATH, {"item_type": ITEM_TYPE, "fields": ["status"]}, format="json"
        )
        admin_client.patch(
            workspace_path(workspace_fixture),
            {"item_type": ITEM_TYPE, "fields": ["uid"]},
            format="json",
        )

        effective = editor_client.get(
            workspace_path(workspace_fixture),
            {"resolve": "effective", "item_type": ITEM_TYPE},
        )
        assert effective.status_code == 200, effective.content
        body = effective.json()
        assert body["scope"] == "workspace"
        assert _keys(body["fields"]) == ["uid"]

    def test_the_personal_level_wins_over_the_workspace_override(
        self, admin_client: APIClient, editor_client: APIClient, workspace_fixture
    ) -> None:
        """Precedence ``user > workspace`` observed through the real routes."""
        admin_client.patch(
            workspace_path(workspace_fixture),
            {"item_type": ITEM_TYPE, "fields": ["status"]},
            format="json",
        )
        editor_client.patch(
            USER_PATH, {"item_type": ITEM_TYPE, "fields": ["owner"]}, format="json"
        )

        body = editor_client.get(
            workspace_path(workspace_fixture),
            {"resolve": "effective", "item_type": ITEM_TYPE},
        ).json()
        assert body["scope"] == "user"
        assert _keys(body["fields"]) == ["owner"]

    def test_a_viewer_may_not_set_the_workspace_override(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        viewer = _role_client(tenant_fixture, workspace_fixture, "viewer")

        response = viewer.patch(
            workspace_path(workspace_fixture),
            {"item_type": ITEM_TYPE, "fields": ["uid"]},
            format="json",
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_a_viewer_may_still_read_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        viewer = _role_client(tenant_fixture, workspace_fixture, "viewer")
        response = viewer.get(workspace_path(workspace_fixture))
        assert response.status_code == 200, response.content


# ---------------------------------------------------------------------------
# Global level
# ---------------------------------------------------------------------------


class TestGlobalLevel:
    def test_an_admin_may_set_the_tenant_wide_default(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            SYSTEM_PATH, {"item_type": ITEM_TYPE, "fields": ["owner"]}, format="json"
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "global"
        # The level's own value, never the admin's personal override.
        assert _keys(body["fields"]) == ["owner"]

    def test_an_editor_may_not_set_the_tenant_wide_default(
        self, editor_client: APIClient
    ) -> None:
        response = editor_client.patch(
            SYSTEM_PATH, {"item_type": ITEM_TYPE, "fields": ["owner"]}, format="json"
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_the_tenant_wide_default_reaches_a_workspace_effective_read(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        admin_client.patch(
            SYSTEM_PATH, {"item_type": ITEM_TYPE, "fields": ["owner"]}, format="json"
        )

        effective = admin_client.get(
            workspace_path(workspace_fixture),
            {"resolve": "effective", "item_type": ITEM_TYPE},
        )
        assert effective.status_code == 200, effective.content
        assert effective.json()["scope"] == "global"


# ---------------------------------------------------------------------------
# Capability tier (R6): a workspace default is a governance act
# ---------------------------------------------------------------------------


def _workspace_admin_key(tenant: Tenant, workspace: Workspace, scope: str) -> str:
    """API key of *scope* whose owner is an admin in *workspace*.

    The tier belongs to the key, not to the owner: this is the "privileged
    owner, narrow key" case an AUTHOR key must not be able to use on a
    workspace-wide default (same pattern as
    ``test_preference_value_views.py::test_an_author_tier_key_…``).
    """
    admin = User.objects.create(
        username=f"tree-admin-{uuid.uuid4().hex[:8]}",
        email="tree-admin@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return (
        AuthenticationService()
        .create_api_key(
            user_id=admin.id,
            tenant_id=tenant.id,
            name=f"tree-{scope}-{uuid.uuid4().hex[:6]}",
            scope=scope,
        )
        .plaintext
    )


def _key_client(key: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key)
    return client


class TestCapabilityTier:
    def test_an_author_tier_key_may_not_set_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        """R6: the ADMIN tier sits above the role matrix on REST too.

        The key's owner is a workspace admin, so a role-only check would let
        the write through; only the capability tier must stop it.
        """
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "author")
        )
        response = client.patch(
            workspace_path(workspace_fixture),
            {"item_type": ITEM_TYPE, "fields": ["uid"]},
            format="json",
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_an_admin_tier_key_may_set_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "admin")
        )
        response = client.patch(
            workspace_path(workspace_fixture),
            {"item_type": ITEM_TYPE, "fields": ["uid"]},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert response.json()["scope"] == "workspace"

    def test_an_author_tier_key_may_still_read_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "author")
        )
        response = client.get(workspace_path(workspace_fixture))

        assert response.status_code == 200, response.content
