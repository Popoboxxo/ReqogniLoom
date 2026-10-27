"""CreateFormConfigService — the three-level create-dialog form definition (#1263).

Database-backed on purpose: the point of the service is the
``user > workspace > global > definition default`` resolution against real rows
(a missing row must *inherit*, never read as "empty"), so a mocked ORM would
test nothing.

The attribute definition the base is derived from is stubbed through
``_attribute_specs``: resolving a real one needs the bootstrap command, which
would test the attribute engine, not this service.
"""
from __future__ import annotations

import uuid

import pytest

from application.create_form_config_service import (
    SCOPE_DEFAULT,
    SCOPE_GLOBAL,
    SCOPE_USER,
    SCOPE_WORKSPACE,
    CreateFormConfigService,
)
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

#: Two editable attributes and one non-editable one (which must never appear).
SPECS = [
    {"name": "title", "kind": "core", "type": "text", "required": True,
     "visible": True, "editable": True, "default": None},
    {"name": "description", "kind": "core", "type": "text", "required": False,
     "visible": True, "editable": True, "default": None},
    {"name": "status", "kind": "core", "type": "text", "required": False,
     "visible": True, "editable": "workflow", "default": None},
]


@pytest.fixture(autouse=True)
def _stub_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        CreateFormConfigService,
        "_definition",
        lambda self, ctx, item_type, workspace_id: {
            "attributes": [dict(spec) for spec in SPECS],
            "sections": [],
        },
    )


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="FormCfg", slug=f"formcfg-{uuid.uuid4().hex[:8]}")


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
            tenant=tenant, name="FormCfg WS", preset={"name": "standard"}
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
def admin_ctx(tenant: Tenant) -> AuthContext:
    return _ctx(_user(tenant, "admin"), tenant, ("admin",))


@pytest.fixture
def editor_ctx(tenant: Tenant) -> AuthContext:
    return _ctx(_user(tenant, "editor"), tenant, ("editor",))


@pytest.fixture
def viewer_ctx(tenant: Tenant) -> AuthContext:
    return _ctx(_user(tenant, "viewer"), tenant, ("viewer",))


def _keys(payload: dict) -> list[str]:
    return [entry["field_key"] for entry in payload["fields"]]


class TestResolution:
    def test_no_row_anywhere_resolves_to_the_definition_default(
        self, editor_ctx: AuthContext, workspace: Workspace
    ) -> None:
        payload = CreateFormConfigService().get_config(
            editor_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_DEFAULT
        # Only editable attributes are configurable; the workflow-owned status
        # is not part of the create dialog.
        assert _keys(payload) == ["title", "description"]
        assert payload["item_type"] == ITEM_TYPE

    def test_workspace_level_overrides_the_default(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "description", "visible": False, "order": 0}],
            workspace_id=workspace.id,
        )
        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_WORKSPACE
        assert payload["fields"][0]["field_key"] == "description"
        assert payload["fields"][0]["visible"] is False

    def test_user_overrides_workspace(
        self, admin_ctx: AuthContext, editor_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title", "order": 0}],
            workspace_id=workspace.id,
        )
        service.set_config(
            editor_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "description", "order": 0}],
        )
        payload = service.get_config(
            editor_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_USER
        assert _keys(payload) == ["description", "title"]

    def test_global_level_is_used_when_no_closer_level_matches(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_GLOBAL,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
        )
        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_GLOBAL


class TestReset:
    def test_reset_drops_the_level_entry_and_inherits(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
            workspace_id=workspace.id,
        )
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=None,
            workspace_id=workspace.id,
        )
        payload = service.get_config(
            admin_ctx, item_type=ITEM_TYPE, workspace_id=workspace.id
        )
        assert payload["scope"] == SCOPE_DEFAULT
        row = TreeDisplayConfig.objects.get(
            scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=workspace.id
        )
        assert ITEM_TYPE not in row.create_form_json

    def test_user_reset_clears_the_column(
        self, editor_ctx: AuthContext
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            editor_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
        )
        service.set_config(
            editor_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE, fields=None
        )
        row = UserDisplayPreference.objects.get(user_id=editor_ctx.user_id)
        assert row.create_form_fields is None


class TestAuthorization:
    def test_editor_cannot_write_the_global_level(self, editor_ctx: AuthContext) -> None:
        with pytest.raises(PermissionDeniedError):
            CreateFormConfigService().set_config(
                editor_ctx,
                scope=SCOPE_GLOBAL,
                item_type=ITEM_TYPE,
                fields=[{"field_key": "title"}],
            )

    def test_viewer_cannot_write_a_workspace_override(
        self, viewer_ctx: AuthContext, workspace: Workspace
    ) -> None:
        with pytest.raises(PermissionDeniedError):
            CreateFormConfigService().set_config(
                viewer_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=[{"field_key": "title"}],
                workspace_id=workspace.id,
            )

    def test_editor_cannot_write_a_workspace_override(
        self, editor_ctx: AuthContext, workspace: Workspace
    ) -> None:
        # ENT-C3 = B (Plan C T-C2-10): a workspace default is configuration, so
        # an ``editor``'s WRITE is no longer enough — the workspace admin
        # (``Operation.WORKSPACE_CONFIG``) is required. Intended breaking change.
        with pytest.raises(PermissionDeniedError):
            CreateFormConfigService().set_config(
                editor_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=[{"field_key": "title"}],
                workspace_id=workspace.id,
            )

    def test_workspace_admin_can_write_a_workspace_override(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        payload = CreateFormConfigService().set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
            workspace_id=workspace.id,
        )
        assert payload["scope"] == SCOPE_WORKSPACE

    def test_editor_can_write_their_own_level(self, editor_ctx: AuthContext) -> None:
        payload = CreateFormConfigService().set_config(
            editor_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
        )
        assert payload["scope"] == SCOPE_USER


class TestWriteLocking:
    def test_workspace_write_re_reads_the_row_under_lock(
        self, admin_ctx: AuthContext, workspace: Workspace, monkeypatch
    ) -> None:
        """``create_form_json`` is one document per level (finding R7).

        A stale ``get_or_create`` instance must not overwrite the entry a
        concurrent writer of another item type already committed; the write
        re-reads the row under ``SELECT ... FOR UPDATE``.
        """
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
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
            TreeDisplayConfig.objects.filter(pk=stale.pk).update(
                create_form_json={
                    **stale.create_form_json,
                    "Adr": [{"field_key": "title", "visible": True}],
                }
            )
            return stale, created

        monkeypatch.setattr(
            TreeDisplayConfig.objects, "get_or_create", stale_get_or_create
        )
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "description"}],
            workspace_id=workspace.id,
        )

        assert calls == ["called"], "the stale-read fixture never took effect"
        row.refresh_from_db()
        assert "Adr" in row.create_form_json, "the concurrent writer's entry was lost"
        assert row.create_form_json[ITEM_TYPE][0]["field_key"] == "description"


class TestValidation:
    def test_unknown_scope_is_rejected(self, admin_ctx: AuthContext) -> None:
        with pytest.raises(ValidationError):
            CreateFormConfigService().set_config(
                admin_ctx,
                scope="tenant",
                item_type=ITEM_TYPE,
                fields=[],
            )

    def test_workspace_scope_requires_a_workspace_id(
        self, admin_ctx: AuthContext
    ) -> None:
        with pytest.raises(ValidationError):
            CreateFormConfigService().set_config(
                admin_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=[],
            )

    def test_unknown_field_is_rejected(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        with pytest.raises(ValidationError):
            CreateFormConfigService().set_config(
                admin_ctx,
                scope=SCOPE_WORKSPACE,
                item_type=ITEM_TYPE,
                fields=[{"field_key": "does_not_exist"}],
                workspace_id=workspace.id,
            )


class TestRequiredFieldKeys:
    def test_required_keys_follow_the_effective_definition(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[
                {"field_key": "title", "required": False},
                {"field_key": "description", "required": True},
            ],
            workspace_id=workspace.id,
        )
        assert service.required_field_keys(
            admin_ctx, ITEM_TYPE, workspace.id
        ) == ["description"]


class TestExportImport:
    def test_export_then_import_round_trips(
        self, admin_ctx: AuthContext, workspace: Workspace
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            fields=[{"field_key": "title", "visible": False, "order": 0}],
            workspace_id=workspace.id,
        )
        document = service.export_config(
            admin_ctx,
            scope=SCOPE_WORKSPACE,
            item_type=ITEM_TYPE,
            workspace_id=workspace.id,
        )
        assert document["schema_version"] == 1
        assert document["fields"][0]["field_key"] == "title"

        # A fresh level imports the same document.
        service.set_config(
            admin_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            fields=None,
        )
        imported = service.import_config(
            admin_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            payload={**document, "scope": SCOPE_USER},
        )
        assert imported["fields"][0]["field_key"] == "title"
        assert imported["fields"][0]["visible"] is False

    def test_import_rejects_an_unknown_schema_version(
        self, admin_ctx: AuthContext
    ) -> None:
        with pytest.raises(ValidationError):
            CreateFormConfigService().import_config(
                admin_ctx,
                scope=SCOPE_USER,
                item_type=ITEM_TYPE,
                payload={"schema_version": 99, "fields": []},
            )

    def test_import_null_fields_resets(
        self, admin_ctx: AuthContext
    ) -> None:
        service = CreateFormConfigService()
        service.set_config(
            admin_ctx, scope=SCOPE_USER, item_type=ITEM_TYPE,
            fields=[{"field_key": "title"}],
        )
        service.import_config(
            admin_ctx,
            scope=SCOPE_USER,
            item_type=ITEM_TYPE,
            payload={"schema_version": 1, "fields": None},
        )
        row = UserDisplayPreference.objects.get(user_id=admin_ctx.user_id)
        assert row.create_form_fields is None


class TestServerRequiredEnforcement:
    """Issue #1263 point 4 — the form's ``required`` reaches the create path."""

    def test_form_required_field_is_demanded_on_create(
        self,
        admin_ctx: AuthContext,
        workspace: Workspace,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from application.attribute_definition_service import (
            AttributeDefinitionService,
        )
        from attribute_definitions.field_validation import FieldValidationError

        monkeypatch.setattr(
            CreateFormConfigService,
            "required_field_keys",
            lambda self, ctx, item_type, workspace_id: ["description"],
        )
        with pytest.raises(FieldValidationError) as exc:
            AttributeDefinitionService._validate_create_form_required(
                admin_ctx, ITEM_TYPE, workspace.id, {"title": "T"}, SPECS
            )
        assert "description" in exc.value.errors

    def test_satisfied_form_required_field_passes(
        self,
        admin_ctx: AuthContext,
        workspace: Workspace,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from application.attribute_definition_service import (
            AttributeDefinitionService,
        )

        monkeypatch.setattr(
            CreateFormConfigService,
            "required_field_keys",
            lambda self, ctx, item_type, workspace_id: ["description"],
        )
        # No raise when the field is supplied.
        AttributeDefinitionService._validate_create_form_required(
            admin_ctx,
            ITEM_TYPE,
            workspace.id,
            {"title": "T", "description": "D"},
            SPECS,
        )
