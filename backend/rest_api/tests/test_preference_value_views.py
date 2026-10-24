"""REST surface of the Q1 three-level preference values (Plan C, T-C2-3).

Covers the six routes end to end against real rows and a real JWT login:

  * ``/api/v1/preference-values/registry/`` — the key catalogue,
  * ``/api/v1/users/me/preference-values/[effective/]`` — self-service,
  * ``/api/v1/workspaces/<id>/preference-values/[effective/]`` — workspace level,
  * ``/api/v1/system/preference-values/`` — tenant-wide default (admin write),

plus every failure edge from the contract: the per-key 400 ``VALIDATION_ERROR``
envelope (unknown key, wrong type, value outside ``choices``, level the key does
not allow, failing key validator, missing/non-object ``values``, unknown ``keys``
filter), the atomicity of a multi-key PATCH, 401 without credentials, 403 for a
workspace write without ``WORKSPACE_CONFIG`` (editor and viewer), 403 for the
global write without admin / with a non-ADMIN-tier key, and 404 for a foreign or
unknown workspace.
"""
from __future__ import annotations

import json
import uuid

import pytest
from rest_framework.test import APIClient

from application.preference_registry import PreferenceKey, register_preference_key
from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.errors import ValidationError
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.tests.conftest import _role_client

pytestmark = pytest.mark.django_db

REGISTRY_PATH = "/api/v1/preference-values/registry/"
USER_EFFECTIVE_PATH = "/api/v1/users/me/preference-values/effective/"
USER_LEVEL_PATH = "/api/v1/users/me/preference-values/"
SYSTEM_PATH = "/api/v1/system/preference-values/"

#: Two registered Q1 keys used across the cases below.
BOOL_KEY = "ui.ids.show_readable"
ENUM_KEY = "ui.markdown.toolbar"
USER_ONLY_KEY = "ui.sidebar.collapsed_groups"


def workspace_path(workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/preference-values/"


def workspace_effective_path(workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/preference-values/effective/"


def _fields(response) -> list[str]:
    """Return the ``field`` names of a 400 envelope's ``details``."""
    return [detail["field"] for detail in response.json()["error"]["details"]]


@pytest.fixture
def other_tenant(db) -> Tenant:
    """A second tenant, used for the foreign-workspace 404."""
    return Tenant.objects.create(
        name="Pref Other Tenant",
        slug=f"pref-other-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture
def other_workspace(other_tenant: Tenant) -> Workspace:
    set_request_tenant(other_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=other_tenant, name="other-ws", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def validated_key(monkeypatch) -> str:
    """Register a temporary key whose validator rejects everything but ``False``.

    ``_REGISTRY`` is rebound (not mutated in place), so both the registry
    lookups and ``PreferenceService`` — which resolve the catalogue at call time —
    see the copy, and ``monkeypatch`` restores the shipped catalogue afterwards.
    """
    from application import preference_registry as registry_module

    monkeypatch.setattr(registry_module, "_REGISTRY", dict(registry_module._REGISTRY))

    def _reject(value):
        if value is not False:
            raise ValidationError("only False is accepted by this key")

    register_preference_key(
        PreferenceKey(
            key="test.validated",
            value_type="bool",
            default=False,
            levels=frozenset({"user"}),
            validator=_reject,
        )
    )
    return "test.validated"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_lists_the_registered_keys_sorted_by_key(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(REGISTRY_PATH)

        assert response.status_code == 200, response.content
        keys = [entry["key"] for entry in response.json()["keys"]]
        assert keys == sorted(keys)
        assert BOOL_KEY in keys
        assert ENUM_KEY in keys

    def test_an_entry_carries_the_full_key_contract(
        self, admin_client: APIClient
    ) -> None:
        body = admin_client.get(REGISTRY_PATH).json()
        entry = next(item for item in body["keys"] if item["key"] == ENUM_KEY)

        assert entry["type"] == "enum"
        assert entry["default"] == "auto"
        assert entry["choices"] == ["auto", "on", "off"]
        assert entry["levels"] == ["global", "user", "workspace"]
        assert entry["mode"] == "override"
        assert entry["ui_editor"] == "select"

    def test_an_unauthenticated_read_is_401(self, db) -> None:
        response = APIClient().get(REGISTRY_PATH)
        assert response.status_code == 401, response.content


# ---------------------------------------------------------------------------
# Effective reads
# ---------------------------------------------------------------------------


class TestEffectiveResolution:
    def test_the_personal_read_is_account_wide_and_starts_at_the_default(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(USER_EFFECTIVE_PATH)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["workspace_id"] is None
        assert body["values"][BOOL_KEY] == {"value": True, "source": "default"}

    def test_the_keys_filter_narrows_the_answer(
        self, admin_client: APIClient
    ) -> None:
        body = admin_client.get(USER_EFFECTIVE_PATH, {"keys": ENUM_KEY}).json()
        assert list(body["values"]) == [ENUM_KEY]

    def test_an_unknown_key_in_the_filter_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(USER_EFFECTIVE_PATH, {"keys": "not.registered"})

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert _fields(response) == ["keys"]

    def test_a_personal_value_is_reported_with_its_level(
        self, admin_client: APIClient
    ) -> None:
        admin_client.patch(
            USER_LEVEL_PATH, {"values": {ENUM_KEY: "on"}}, format="json"
        )

        body = admin_client.get(USER_EFFECTIVE_PATH, {"keys": ENUM_KEY}).json()
        assert body["values"][ENUM_KEY] == {"value": "on", "source": "user"}

    def test_the_workspace_read_includes_the_workspace_level(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        admin_client.patch(
            workspace_path(workspace_fixture),
            {"values": {ENUM_KEY: "off"}},
            format="json",
        )

        response = admin_client.get(workspace_effective_path(workspace_fixture))
        assert response.status_code == 200, response.content
        body = response.json()
        assert body["workspace_id"] == str(workspace_fixture.id)
        assert body["values"][ENUM_KEY] == {"value": "off", "source": "workspace"}


# ---------------------------------------------------------------------------
# Personal level (self-service)
# ---------------------------------------------------------------------------


class TestUserLevel:
    def test_get_without_a_row_returns_an_empty_map(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.get(USER_LEVEL_PATH)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "user"
        assert body["workspace_id"] is None
        assert body["values"] == {}

    def test_patch_stores_and_returns_the_levels_own_values(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH,
            {"values": {BOOL_KEY: False, ENUM_KEY: "on"}},
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "user"
        assert body["values"] == {BOOL_KEY: False, ENUM_KEY: "on"}

        again = admin_client.get(USER_LEVEL_PATH).json()
        assert again["values"] == {BOOL_KEY: False, ENUM_KEY: "on"}

    def test_null_resets_the_key(self, admin_client: APIClient) -> None:
        admin_client.patch(
            USER_LEVEL_PATH, {"values": {BOOL_KEY: False}}, format="json"
        )
        reset = admin_client.patch(
            USER_LEVEL_PATH, {"values": {BOOL_KEY: None}}, format="json"
        )

        assert reset.status_code == 200, reset.content
        assert reset.json()["values"] == {}

    def test_an_unknown_value_key_is_a_400_naming_the_key(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH, {"values": {"no.such.key": True}}, format="json"
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert _fields(response) == ["values.no.such.key"]

    def test_a_wrong_type_is_a_400_naming_the_key(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH, {"values": {BOOL_KEY: "yes"}}, format="json"
        )

        assert response.status_code == 400, response.content
        assert _fields(response) == [f"values.{BOOL_KEY}"]

    def test_a_value_outside_choices_is_a_400_naming_the_key(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH, {"values": {ENUM_KEY: "sometimes"}}, format="json"
        )

        assert response.status_code == 400, response.content
        assert _fields(response) == [f"values.{ENUM_KEY}"]

    def test_a_failing_key_validator_is_a_400_naming_the_key(
        self, admin_client: APIClient, validated_key: str
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH, {"values": {validated_key: True}}, format="json"
        )

        assert response.status_code == 400, response.content
        assert _fields(response) == [f"values.{validated_key}"]
        assert admin_client.get(USER_LEVEL_PATH).json()["values"] == {}

    def test_a_missing_values_object_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(USER_LEVEL_PATH, {}, format="json")

        assert response.status_code == 400, response.content
        assert _fields(response) == ["values"]

    def test_a_non_object_values_payload_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            USER_LEVEL_PATH, {"values": [BOOL_KEY]}, format="json"
        )

        assert response.status_code == 400, response.content
        assert _fields(response) == ["values"]

    def test_an_undeclared_body_key_is_a_400(
        self, admin_client: APIClient
    ) -> None:
        """#851: a typo must not look like a successful save."""
        response = admin_client.patch(
            USER_LEVEL_PATH,
            {"values": {BOOL_KEY: False}, "scope": "user"},
            format="json",
        )

        assert response.status_code == 400, response.content

    def test_one_bad_key_leaves_the_whole_payload_unwritten(
        self, admin_client: APIClient
    ) -> None:
        """Atomicity: validation happens for every key before the first write."""
        response = admin_client.patch(
            USER_LEVEL_PATH,
            {"values": {BOOL_KEY: False, "no.such.key": True}},
            format="json",
        )

        assert response.status_code == 400, response.content
        assert _fields(response) == ["values.no.such.key"]
        assert admin_client.get(USER_LEVEL_PATH).json()["values"] == {}

    def test_an_unauthenticated_write_is_401(self, db) -> None:
        response = APIClient().patch(
            USER_LEVEL_PATH, {"values": {BOOL_KEY: False}}, format="json"
        )
        assert response.status_code == 401, response.content


# ---------------------------------------------------------------------------
# Workspace level
# ---------------------------------------------------------------------------


class TestWorkspaceLevel:
    def test_an_admin_may_set_and_read_the_workspace_level(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        path = workspace_path(workspace_fixture)
        response = admin_client.patch(
            path, {"values": {BOOL_KEY: False}}, format="json"
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "workspace"
        assert body["workspace_id"] == str(workspace_fixture.id)
        assert body["values"] == {BOOL_KEY: False}
        assert admin_client.get(path).json()["values"] == {BOOL_KEY: False}

    def test_a_viewer_may_read_but_not_write(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        viewer = _role_client(tenant_fixture, workspace_fixture, "viewer")
        path = workspace_path(workspace_fixture)

        assert viewer.get(path).status_code == 200
        denied = viewer.patch(path, {"values": {BOOL_KEY: False}}, format="json")

        assert denied.status_code == 403, denied.content
        assert denied.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_an_editor_may_not_set_the_workspace_level(
        self, editor_client: APIClient, workspace_fixture
    ) -> None:
        """ENT-C3 = B: a workspace default requires ``WORKSPACE_CONFIG``."""
        response = editor_client.patch(
            workspace_path(workspace_fixture),
            {"values": {BOOL_KEY: False}},
            format="json",
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_a_user_only_key_is_a_400_at_the_workspace_level(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        response = admin_client.patch(
            workspace_path(workspace_fixture),
            {"values": {USER_ONLY_KEY: []}},
            format="json",
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert _fields(response) == [f"values.{USER_ONLY_KEY}"]

    def test_a_foreign_workspace_is_404_on_read_and_write(
        self, admin_client: APIClient, other_workspace: Workspace
    ) -> None:
        assert admin_client.get(workspace_path(other_workspace)).status_code == 404
        assert (
            admin_client.get(workspace_effective_path(other_workspace)).status_code
            == 404
        )
        denied = admin_client.patch(
            workspace_path(other_workspace),
            {"values": {BOOL_KEY: False}},
            format="json",
        )
        assert denied.status_code == 404, denied.content
        assert denied.json()["error"]["code"] == "NOT_FOUND"

    def test_an_unknown_workspace_is_404(self, admin_client: APIClient) -> None:
        response = admin_client.get(f"/api/v1/workspaces/{uuid.uuid4()}/preference-values/")
        assert response.status_code == 404, response.content


# ---------------------------------------------------------------------------
# Global level
# ---------------------------------------------------------------------------


class TestGlobalLevel:
    def test_an_admin_may_set_the_tenant_wide_default(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.patch(
            SYSTEM_PATH, {"values": {BOOL_KEY: False}}, format="json"
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["scope"] == "global"
        assert body["workspace_id"] is None
        assert body["values"] == {BOOL_KEY: False}

    def test_the_tenant_wide_default_reaches_the_effective_read(
        self, admin_client: APIClient, workspace_fixture
    ) -> None:
        admin_client.patch(SYSTEM_PATH, {"values": {BOOL_KEY: False}}, format="json")

        body = admin_client.get(workspace_effective_path(workspace_fixture)).json()
        assert body["values"][BOOL_KEY] == {"value": False, "source": "global"}

    def test_an_editor_may_not_set_the_tenant_wide_default(
        self, editor_client: APIClient
    ) -> None:
        response = editor_client.patch(
            SYSTEM_PATH, {"values": {BOOL_KEY: False}}, format="json"
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_an_author_tier_key_may_not_set_the_tenant_wide_default(
        self, tenant_fixture: Tenant, workspace_fixture: Workspace
    ) -> None:
        """#865: the capability tier, not the owner's role, denies the write."""
        admin = User.objects.create(
            username=f"pref-author-{uuid.uuid4().hex[:8]}",
            email="pref-author@t.test",
            tenant=tenant_fixture,
        )
        set_request_tenant(tenant_fixture.id)
        try:
            UserRole.objects.create(
                tenant=tenant_fixture,
                user=admin,
                workspace=workspace_fixture,
                role=ROLE_ADMIN,
            )
        finally:
            clear_request_tenant()

        key = AuthenticationService().create_api_key(
            user_id=admin.id,
            tenant_id=tenant_fixture.id,
            name=f"pref-author-key-{uuid.uuid4().hex[:6]}",
            scope="author",
        )
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=key.plaintext)

        response = client.patch(SYSTEM_PATH, {"values": {BOOL_KEY: False}}, format="json")

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# OpenAPI contract (§f.5 / KA-ALL-04)
# ---------------------------------------------------------------------------


class TestOpenApiContract:
    def test_the_schema_contains_all_six_paths(self, db) -> None:
        response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/json")

        assert response.status_code == 200, response.content[:200]
        paths = json.loads(response.content)["paths"]
        for path in (
            "/api/v1/preference-values/registry/",
            "/api/v1/users/me/preference-values/effective/",
            "/api/v1/users/me/preference-values/",
            "/api/v1/workspaces/{workspace_id}/preference-values/effective/",
            "/api/v1/workspaces/{workspace_id}/preference-values/",
            "/api/v1/system/preference-values/",
        ):
            assert path in paths, sorted(paths)
