"""TreeDisplayConfigService — the three-level tree-display configuration (#1257).

Database-backed on purpose: the whole point of the service is the
``user > workspace > global > default`` resolution against real rows (a missing
row must *inherit*, never read as "empty"), so a mocked ORM would test nothing.

The module covers, in order:
  * the resolution chain and the reported ``scope``,
  * the reset semantic (``fields=None`` drops the level's entry),
  * the level-specific authorization (write authority for a workspace override,
    admin for the tenant-wide default),
  * the validation contract (unknown scope, bad payload, snake_case custom keys),
  * the defensive read of a hand-edited row.
"""
from __future__ import annotations

import uuid

import pytest

from application.tree_display_config_service import (
    SCOPE_DEFAULT,
    SCOPE_GLOBAL,
    SCOPE_USER,
    SCOPE_WORKSPACE,
    TreeDisplayConfigService,
)
from attribute_definitions.tree_fields import DEFAULT_TREE_DISPLAY_FIELDS
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    TREE_DISPLAY_SCOPE_GLOBAL,
    TREE_DISPLAY_SCOPE_WORKSPACE,
    TreeDisplayConfig,
    UserDisplayPreference,
)
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

ITEM_TYPE = "Requirement"


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="TreeCfg", slug=f"treecfg-{uuid.uuid4().hex[:8]}")


def _user(tenant: Tenant, label: str) -> User:
    return User.objects.create(
        username=f"{label}-{uuid.uuid4().hex[:6]}",
        email=f"{label}{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="TreeCfg WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


def _ctx(user: User, tenant: Tenant, roles: tuple[str, ...]) -> AuthContext:
    return AuthContext(
        user_id=user.pk,
        tenant_id=tenant.pk,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def admin(tenant: Tenant) -> User:
    return _user(tenant, "admin")


@pytest.fixture
def editor(tenant: Tenant) -> User:
    return _user(tenant, "editor")


@pytest.fixture
def viewer(tenant: Tenant) -> User:
    return _user(tenant, "viewer")


@pytest.fixture
def admin_ctx(admin: User, tenant: Tenant) -> AuthContext:
    return _ctx(admin, tenant, ("admin",))


@pytest.fixture
def editor_ctx(editor: User, tenant: Tenant) -> AuthContext:
    return _ctx(editor, tenant, ("editor",))


@pytest.fixture
def viewer_ctx(viewer: User, tenant: Tenant) -> AuthContext:
    return _ctx(viewer, tenant, ("viewer",))


def _keys(payload: dict) -> list[str]:
    return [entry["key"] for entry in payload["fields"]]


# ---------------------------------------------------------------------------
# Resolution chain
# ---------------------------------------------------------------------------


class TestResolution:
    def test_no_row_anywhere_resolves_to_the_builtin_default(
        self, editor_ctx: AuthContext, workspace: Workspace
    ) -> None:
        payload = TreeDisplayConfigService().get_config(
            editor_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )

        assert payload["scope"] == SCOPE_DEFAULT
        assert _keys(payload) == list(DEFAULT_TREE_DISPLAY_FIELDS)
        assert payload["item_type"] == ITEM_TYPE
        # The catalogue travels with every read so a picker can render.
        assert {entry["key"] for entry in payload["catalog"]} >= {
            "uid",
            "level",
            "status",
            "updated_at",
        }

    def test_global_applies_when_no_workspace_or_user_entry_exists(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_GLOBAL,
            item_type=ITEM_TYPE,
            fields=["status", "uid"],
        )

        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_GLOBAL
        assert _keys(payload) == ["status", "uid"]

    def test_workspace_overrides_global(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["status"]
        )
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["uid", "level"],
            workspace_id=workspace.id,
        )

        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_WORKSPACE
        assert _keys(payload) == ["uid", "level"]

    def test_user_overrides_workspace_and_global(
        self,
        admin_ctx: AuthContext,
        workspace: Workspace,
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["status"]
        )
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["level"],
            workspace_id=workspace.id,
        )
        service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["updated_at"]
        )

        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_USER
        assert _keys(payload) == ["updated_at"]

    def test_other_item_types_are_unaffected(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        """The stored map is keyed per artifact type, not global."""
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["status"]
        )

        other = service.get_config(
            admin_ctx, item_type="Adr", workspace_id=workspace.id
        )
        assert other["scope"] == SCOPE_DEFAULT

    def test_another_workspace_does_not_inherit_a_workspace_override(
        self, admin_ctx: AuthContext, tenant: Tenant, workspace: Workspace
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["status"],
            workspace_id=workspace.id,
        )
        set_request_tenant(tenant.id)
        try:
            sibling = Workspace.objects.create(
                tenant=tenant, name="Sibling", preset={"name": "standard"}
            )
        finally:
            clear_request_tenant()

        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=sibling.id
        )
        assert payload["scope"] == SCOPE_DEFAULT


# ---------------------------------------------------------------------------
# Reset + defensive read
# ---------------------------------------------------------------------------


class TestResetAndDefensiveRead:
    def test_none_drops_the_users_entry_so_resolution_falls_back(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["status"],
            workspace_id=workspace.id,
        )
        service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["uid"]
        )

        reset = service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=None
        )

        # The response describes the level that was written ...
        assert reset["scope"] == SCOPE_USER
        assert reset["fields"] is None
        # ... and resolution now falls through to the workspace override.
        effective = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert effective["scope"] == SCOPE_WORKSPACE
        assert _keys(effective) == ["status"]

    def test_reset_of_the_only_level_resolves_to_the_builtin_default(
        self, admin_ctx: AuthContext
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["uid"]
        )
        reset = service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=None
        )
        assert reset["fields"] is None
        effective = service.get_config(admin_ctx, item_type=ITEM_TYPE)
        assert effective["scope"] == SCOPE_DEFAULT
        assert _keys(effective) == list(DEFAULT_TREE_DISPLAY_FIELDS)

    def test_a_hand_edited_non_dict_row_reads_as_no_configuration(
        self, editor_ctx: AuthContext
    ) -> None:
        """A read path must never raise on a legacy/hand-edited row."""
        set_request_tenant(editor_ctx.tenant_id)
        try:
            UserDisplayPreference.objects.create(
                user_id=editor_ctx.user_id,
                tenant_id=editor_ctx.tenant_id,
                tree_display_fields=["uid"],  # wrong shape on purpose
            )
        finally:
            clear_request_tenant()

        payload = TreeDisplayConfigService().get_config(
            editor_ctx, item_type=ITEM_TYPE
        )
        assert payload["scope"] == SCOPE_DEFAULT

    def test_get_scope_returns_the_stored_map_and_the_catalogue(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["uid"],
            workspace_id=workspace.id,
        )

        payload = service.get_scope(
            admin_ctx, scope=SCOPE_WORKSPACE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_WORKSPACE
        assert _keys_stored(payload["config"][ITEM_TYPE]) == ["uid"]
        assert payload["catalog"]

    def test_get_scope_for_one_item_type_returns_its_fields(
        self, admin_ctx: AuthContext
    ) -> None:
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["owner"]
        )

        payload = service.get_scope(admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE)
        assert _keys_stored(payload["fields"]) == ["owner"]

        absent = service.get_scope(admin_ctx, scope=SCOPE_GLOBAL, item_type="Adr")
        assert absent["fields"] is None


def _keys_stored(entries: list) -> list[str]:
    return [entry["key"] for entry in entries]


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestAuthorization:
    def test_user_level_is_self_service_for_every_role(
        self, viewer_ctx: AuthContext
    ) -> None:
        """``ctx.user_id`` is the whole boundary at the personal level."""
        payload = TreeDisplayConfigService().set_config(
            viewer_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["uid"]
        )
        assert payload["scope"] == SCOPE_USER
        assert _keys(payload) == ["uid"]

    def test_workspace_level_requires_write_authority(
        self, viewer_ctx: AuthContext, workspace: Workspace
    ) -> None:
        with pytest.raises(PermissionDeniedError):
            TreeDisplayConfigService().set_config(
                viewer_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=["uid"],
                workspace_id=workspace.id,
            )

    def test_workspace_level_is_denied_for_an_editor(
        self, editor_ctx: AuthContext, workspace: Workspace
    ) -> None:
        """ENT-C3 = B (Plan C T-C2-10): a workspace default is configuration.

        An ``editor`` holds WRITE in the RBAC matrix, which is no longer
        sufficient — only ``Operation.WORKSPACE_CONFIG`` (the workspace admin)
        may change a default that governs every member. This is the intended
        breaking change of PR-C11.
        """
        with pytest.raises(PermissionDeniedError):
            TreeDisplayConfigService().set_config(
                editor_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=["uid"],
                workspace_id=workspace.id,
            )

    def test_workspace_level_is_allowed_for_a_workspace_admin(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        payload = TreeDisplayConfigService().set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["uid"],
            workspace_id=workspace.id,
        )
        assert payload["scope"] == SCOPE_WORKSPACE

    def test_global_level_requires_the_admin_role(
        self, editor_ctx: AuthContext
    ) -> None:
        with pytest.raises(PermissionDeniedError):
            TreeDisplayConfigService().set_config(
                editor_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["uid"]
            )

    def test_global_level_is_allowed_for_an_admin(
        self, admin_ctx: AuthContext
    ) -> None:
        payload = TreeDisplayConfigService().set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["uid"]
        )
        assert payload["scope"] == SCOPE_GLOBAL

    def test_workspace_level_needs_a_workspace_id(
        self, admin_ctx: AuthContext
    ) -> None:
        with pytest.raises(ValidationError):
            TreeDisplayConfigService().set_config(
                admin_ctx, scope=SCOPE_WORKSPACE, item_type=ITEM_TYPE, fields=["uid"]
            )


# ---------------------------------------------------------------------------
# Lost-update protection (finding R7)
# ---------------------------------------------------------------------------


class TestWriteLocking:
    def test_workspace_write_re_reads_the_row_under_lock(
        self, admin_ctx: AuthContext, workspace: Workspace, monkeypatch
    ) -> None:
        """Two writers of different item types must not overwrite each other.

        ``fields_json`` is one JSON document per level, so the write is a
        read-modify-write. ``get_or_create`` can hand back a row instance read
        *before* a concurrent writer committed; only a re-read under
        ``SELECT ... FOR UPDATE`` keeps the other writer's entry.
        """
        service = TreeDisplayConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["uid"],
            workspace_id=workspace.id,
        )
        row = TreeDisplayConfig.objects.get(
            scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=workspace.id
        )

        original = TreeDisplayConfig.objects.get_or_create
        calls: list[str] = []

        def stale_get_or_create(**kwargs):
            calls.append("called")
            stale, created = original(**kwargs)
            # A concurrent writer committed its Adr entry after this instance
            # was read — the in-memory JSON is now stale.
            TreeDisplayConfig.objects.filter(pk=stale.pk).update(
                fields_json={**stale.fields_json, "Adr": [{"key": "status"}]}
            )
            return stale, created

        monkeypatch.setattr(
            TreeDisplayConfig.objects, "get_or_create", stale_get_or_create
        )
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["owner"],
            workspace_id=workspace.id,
        )

        assert calls == ["called"], "the stale-read fixture never took effect"
        row.refresh_from_db()
        assert "Adr" in row.fields_json, "the concurrent writer's entry was lost"
        assert row.fields_json[ITEM_TYPE][0]["key"] == "owner"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize("scope", ["effective", "default", "", "USER"])
    def test_unknown_scopes_are_rejected(
        self, admin_ctx: AuthContext, scope: str
    ) -> None:
        with pytest.raises(ValidationError):
            TreeDisplayConfigService().set_config(
                admin_ctx, scope=scope, item_type=ITEM_TYPE, fields=["uid"]
            )

    def test_unknown_field_keys_are_rejected(
        self, admin_ctx: AuthContext
    ) -> None:
        with pytest.raises(ValidationError):
            TreeDisplayConfigService().set_config(
                admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["not a key"]
            )

    def test_duplicate_field_keys_are_rejected(
        self, admin_ctx: AuthContext
    ) -> None:
        with pytest.raises(ValidationError):
            TreeDisplayConfigService().set_config(
                admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=["uid", "uid"]
            )

    def test_custom_attribute_names_are_accepted_as_field_keys(
        self, admin_ctx: AuthContext
    ) -> None:
        """Issue #1257 point 2: custom attributes must be configurable."""
        payload = TreeDisplayConfigService().set_config(
            admin_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            fields=["my_custom_attribute"],
        )
        assert _keys(payload) == ["my_custom_attribute"]

    def test_a_stored_row_is_actually_persisted(
        self, admin_ctx: AuthContext, tenant: Tenant
    ) -> None:
        TreeDisplayConfigService().set_config(
            admin_ctx, scope=SCOPE_GLOBAL, item_type=ITEM_TYPE, fields=["uid"]
        )

        set_request_tenant(tenant.id)
        try:
            row = TreeDisplayConfig(
                scope=TREE_DISPLAY_SCOPE_GLOBAL
            )
            assert row.scope == TREE_DISPLAY_SCOPE_GLOBAL
            stored = TreeDisplayConfig.objects.filter(
                scope=TREE_DISPLAY_SCOPE_GLOBAL
            ).first()
            assert stored is not None
            assert stored.fields_json[ITEM_TYPE][0]["key"] == "uid"
        finally:
            clear_request_tenant()

    def test_workspace_rows_are_keyed_by_workspace(
        self, admin_ctx: AuthContext, workspace: Workspace, tenant: Tenant
    ) -> None:
        TreeDisplayConfigService().set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=["uid"],
            workspace_id=workspace.id,
        )

        set_request_tenant(tenant.id)
        try:
            stored = TreeDisplayConfig.objects.filter(
                scope=TREE_DISPLAY_SCOPE_WORKSPACE
            ).first()
            assert stored is not None
            assert stored.workspace_id == workspace.id
        finally:
            clear_request_tenant()
