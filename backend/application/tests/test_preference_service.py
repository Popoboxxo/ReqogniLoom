"""Q1 preference registry + three-level service (Plan C, T-C2-2).

Deliberately database-backed and mock-free: the contract under test *is* the
interaction between the registry, the ``at_preference_value`` rows, the
tenant-scoped default manager, the audit trail and the transaction boundary, so
a mocked ORM would assert little more than the test's own assumptions.

Covered contract points (T-C2-2 "TDD"): override resolution per level including
``source``; union across global+workspace+user plus default; a level the key does
not allow; reset via ``None``; viewer/editor denied on a workspace write and
admin allowed; global write without the admin role; audit present for a
workspace write and absent for a user write; two tenants isolated; ``UNSET`` for
missing levels; duplicate registration; tenant restore in ``levels_for`` on the
normal *and* the exceptional path; per-key validator rejection leaves nothing
written.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ImproperlyConfigured

from application.preference_registry import (
    PreferenceKey,
    all_preference_keys,
    get_preference_key,
    register_preference_key,
)
from application.preference_service import (
    UNSET,
    PreferenceService,
    levels_for,
    resolve_for,
)
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import PreferenceValue
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

SERVICE_ENTITY_TYPE = "preference_value"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(monkeypatch):
    """Isolate registry mutations: every test gets its own copy of the catalogue.

    ``_REGISTRY`` is rebound (not mutated in place) so ``register_preference_key``
    — which looks the name up at call time — writes into the copy and monkeypatch
    restores the real catalogue afterwards. Needed by the union/validator cases,
    which register temporary keys that no shipped consumer knows about.
    """
    from application import preference_registry as module

    monkeypatch.setattr(module, "_REGISTRY", dict(module._REGISTRY))
    return module


def _make_tenant(label: str) -> Tenant:
    return Tenant.objects.create(name=label, slug=f"pref-{label}-{uuid.uuid4().hex[:8]}")


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    """Create a workspace with the tenant context armed (tenant-scoped manager)."""
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant_id=tenant.id, name=name)
    finally:
        TenantContext.clear_tenant()


def _make_user(tenant: Tenant, label: str) -> User:
    return User.objects.create(
        username=f"{label}-{uuid.uuid4().hex[:6]}",
        email=f"{label}{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


def _make_ctx(
    tenant: Tenant,
    user: User,
    *roles: str,
    workspace: Workspace | None = None,
) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=tuple(roles),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id if workspace is not None else None,
    )


@pytest.fixture
def tenant_a() -> Tenant:
    return _make_tenant("a")


@pytest.fixture
def tenant_b() -> Tenant:
    return _make_tenant("b")


@pytest.fixture
def workspace_a(tenant_a: Tenant) -> Workspace:
    return _make_workspace(tenant_a, "ws-a")


@pytest.fixture
def alice(tenant_a: Tenant) -> User:
    return _make_user(tenant_a, "alice")


@pytest.fixture
def admin_ctx(tenant_a: Tenant, workspace_a: Workspace, alice: User) -> AuthContext:
    return _make_ctx(tenant_a, alice, "admin", workspace=workspace_a)


@pytest.fixture
def editor_ctx(tenant_a: Tenant, workspace_a: Workspace, alice: User) -> AuthContext:
    return _make_ctx(tenant_a, alice, "editor", workspace=workspace_a)


@pytest.fixture
def viewer_ctx(tenant_a: Tenant, workspace_a: Workspace, alice: User) -> AuthContext:
    return _make_ctx(tenant_a, alice, "viewer", workspace=workspace_a)


@pytest.fixture
def service() -> PreferenceService:
    return PreferenceService()


def _set_global_row(tenant: Tenant, key: str, value) -> PreferenceValue:
    """Seed one global row for *tenant* (used by the context-free read tests)."""
    TenantContext.set_tenant(tenant.id)
    try:
        return PreferenceValue.objects.create(
            tenant_id=tenant.id, scope="global", key=key, value=value
        )
    finally:
        TenantContext.clear_tenant()


def _tenant_id(tenant: "Tenant | uuid.UUID") -> uuid.UUID:
    """Accept either a ``Tenant`` row or its id (helpers are called with both)."""
    return tenant.id if isinstance(tenant, Tenant) else tenant


def _rows(tenant: "Tenant | uuid.UUID", **filters) -> list[PreferenceValue]:
    TenantContext.set_tenant(_tenant_id(tenant))
    try:
        return list(PreferenceValue.objects.filter(**filters))
    finally:
        TenantContext.clear_tenant()


def _preference_audits(
    tenant: "Tenant | uuid.UUID", **filters
) -> list[AuditEntry]:
    TenantContext.set_tenant(_tenant_id(tenant))
    try:
        return list(
            AuditEntry.objects.filter(
                entity_type=SERVICE_ENTITY_TYPE, **filters
            ).order_by("timestamp")
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_core_keys_are_registered(self) -> None:
        """The three Q1 keys exist with exactly the specified metadata."""
        ids = get_preference_key("ui.ids.show_readable")
        assert (ids.value_type, ids.default, ids.mode, ids.ui_editor) == (
            "bool",
            True,
            "override",
            "checkbox",
        )
        assert ids.levels == {"global", "workspace", "user"}
        assert ids.owner == "C2"

        toolbar = get_preference_key("ui.markdown.toolbar")
        assert (toolbar.value_type, toolbar.default, toolbar.mode) == (
            "enum",
            "auto",
            "override",
        )
        assert toolbar.choices == ("auto", "on", "off")
        assert toolbar.ui_editor == "select"
        assert toolbar.levels == {"global", "workspace", "user"}

        sidebar = get_preference_key("ui.sidebar.collapsed_groups")
        assert (sidebar.value_type, sidebar.default, sidebar.mode) == (
            "str_list",
            [],
            "override",
        )
        assert sidebar.levels == {"user"}
        assert sidebar.choices == (
            "overview",
            "requirements",
            "architecture",
            "test",
            "admin",
        )
        assert sidebar.ui_editor is None

    def test_all_preference_keys_is_sorted(self) -> None:
        keys = [spec.key for spec in all_preference_keys()]
        assert keys == sorted(keys)
        assert {"ui.ids.show_readable", "ui.markdown.toolbar"} <= set(keys)

    def test_unknown_key_is_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="Unknown preference key"):
            get_preference_key("ui.does.not_exist")

    def test_duplicate_registration_is_improperly_configured(self) -> None:
        spec = get_preference_key("ui.ids.show_readable")
        with pytest.raises(ImproperlyConfigured, match="already registered"):
            register_preference_key(spec)

    @pytest.mark.parametrize(
        "key",
        ["Bad Key", "UPPER.case", "ab", "a" * 129, "dash-key", ""],
    )
    def test_invalid_key_shape_is_improperly_configured(self, key: str) -> None:
        with pytest.raises(ImproperlyConfigured, match="does not match"):
            PreferenceKey(
                key=key,
                value_type="bool",
                default=True,
                levels=frozenset({"user"}),
            )

    def test_unknown_level_is_improperly_configured(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="unknown level"):
            PreferenceKey(
                key="test.levels",
                value_type="bool",
                default=True,
                levels=frozenset({"organization"}),
            )

    def test_enum_without_choices_is_improperly_configured(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="requires 'choices'"):
            PreferenceKey(
                key="test.enum",
                value_type="enum",
                default="a",
                levels=frozenset({"user"}),
            )


# ---------------------------------------------------------------------------
# Override resolution
# ---------------------------------------------------------------------------


class TestOverrideResolution:
    def test_default_when_nothing_is_set(self, service, admin_ctx) -> None:
        result = service.effective(admin_ctx, keys=["ui.markdown.toolbar"])
        assert result["values"]["ui.markdown.toolbar"] == {
            "value": "auto",
            "source": "default",
        }

    def test_each_level_wins_over_the_lower_one(self, service, admin_ctx, workspace_a) -> None:
        key = "ui.markdown.toolbar"

        service.set_level(admin_ctx, scope="global", values={key: "on"})
        assert service.effective(admin_ctx, keys=[key])["values"][key] == {
            "value": "on",
            "source": "global",
        }

        service.set_level(
            admin_ctx, scope="workspace", values={key: "off"}, workspace_id=workspace_a.id
        )
        assert service.effective(
            admin_ctx, workspace_id=workspace_a.id, keys=[key]
        )["values"][key] == {"value": "off", "source": "workspace"}

        service.set_level(admin_ctx, scope="user", values={key: "on"})
        assert service.effective(
            admin_ctx, workspace_id=workspace_a.id, keys=[key]
        )["values"][key] == {"value": "on", "source": "user"}

    def test_workspace_level_is_ignored_without_a_workspace(
        self, service, admin_ctx, workspace_a
    ) -> None:
        key = "ui.ids.show_readable"
        service.set_level(
            admin_ctx, scope="workspace", values={key: False}, workspace_id=workspace_a.id
        )
        effective = service.effective(admin_ctx, keys=[key])["values"][key]
        assert effective == {"value": True, "source": "default"}

    def test_falsy_stored_value_is_not_mistaken_for_unset(
        self, service, admin_ctx
    ) -> None:
        key = "ui.ids.show_readable"
        service.set_level(admin_ctx, scope="user", values={key: False})
        assert service.effective(admin_ctx, keys=[key])["values"][key] == {
            "value": False,
            "source": "user",
        }

    def test_effective_payload_shape_is_deterministic(self, service, admin_ctx) -> None:
        result = service.effective(admin_ctx)
        assert result["workspace_id"] is None
        keys = list(result["values"])
        assert keys == sorted(keys)
        assert all(set(entry) == {"value", "source"} for entry in result["values"].values())

    def test_effective_unknown_filter_key_raises(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="Unknown preference key"):
            service.effective(admin_ctx, keys=["ui.nope"])


# ---------------------------------------------------------------------------
# Union resolution
# ---------------------------------------------------------------------------


class TestUnionResolution:
    @pytest.fixture
    def union_key(self, registry) -> str:
        registry.register_preference_key(
            PreferenceKey(
                key="test.union_ordered",
                value_type="str_list",
                default=["d"],
                levels=frozenset({"global", "workspace", "user"}),
                mode="union",
                choices=("a", "b", "c", "d"),
            )
        )
        return "test.union_ordered"

    def test_union_merges_global_workspace_user_and_default(
        self, service, admin_ctx, workspace_a, union_key
    ) -> None:
        service.set_level(admin_ctx, scope="global", values={union_key: ["b"]})
        service.set_level(
            admin_ctx, scope="workspace", values={union_key: ["c"]}, workspace_id=workspace_a.id
        )
        service.set_level(admin_ctx, scope="user", values={union_key: ["a"]})

        effective = service.effective(
            admin_ctx, workspace_id=workspace_a.id, keys=[union_key]
        )["values"][union_key]
        assert effective == {"value": ["a", "b", "c", "d"], "source": "merged"}

    def test_union_deduplicates(self, service, admin_ctx, union_key) -> None:
        service.set_level(admin_ctx, scope="global", values={union_key: ["b", "a"]})
        service.set_level(admin_ctx, scope="user", values={union_key: ["a", "b"]})

        value, source = resolve_for(
            tenant_id=admin_ctx.tenant_id,
            workspace_id=None,
            user_id=admin_ctx.user_id,
            key=union_key,
        )
        assert (value, source) == (["a", "b", "d"], "merged")

    def test_union_without_choices_keeps_insertion_order(
        self, service, admin_ctx, registry
    ) -> None:
        registry.register_preference_key(
            PreferenceKey(
                key="test.union_free",
                value_type="str_list",
                default=["base"],
                levels=frozenset({"global", "user"}),
                mode="union",
            )
        )
        service.set_level(admin_ctx, scope="global", values={"test.union_free": ["w"]})
        service.set_level(admin_ctx, scope="user", values={"test.union_free": ["u"]})

        value, _source = resolve_for(
            tenant_id=admin_ctx.tenant_id,
            workspace_id=None,
            user_id=admin_ctx.user_id,
            key="test.union_free",
        )
        assert value == ["base", "w", "u"]


# ---------------------------------------------------------------------------
# Writes: validation, reset, atomicity
# ---------------------------------------------------------------------------


class TestWrites:
    def test_disallowed_level_raises(self, service, admin_ctx, workspace_a) -> None:
        """``ui.sidebar.collapsed_groups`` is user-only."""
        with pytest.raises(ValidationError, match="cannot be set at level 'workspace'"):
            service.set_level(
                admin_ctx,
                scope="workspace",
                values={"ui.sidebar.collapsed_groups": ["test"]},
                workspace_id=workspace_a.id,
            )
        assert _rows(admin_ctx.tenant_id, key="ui.sidebar.collapsed_groups") == []

    def test_unknown_key_writes_nothing(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="Unknown preference key"):
            service.set_level(
                admin_ctx,
                scope="user",
                values={"ui.ids.show_readable": False, "ui.unknown": True},
            )
        assert _rows(admin_ctx.tenant_id, key="ui.ids.show_readable") == []

    def test_wrong_type_writes_nothing(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="must be a boolean"):
            service.set_level(
                admin_ctx,
                scope="user",
                values={"ui.ids.show_readable": "yes"},
            )
        assert _rows(admin_ctx.tenant_id) == []

    def test_value_outside_choices_writes_nothing(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="must be one of"):
            service.set_level(
                admin_ctx, scope="user", values={"ui.markdown.toolbar": "sometimes"}
            )
        assert _rows(admin_ctx.tenant_id) == []

    def test_str_list_item_outside_choices_writes_nothing(
        self, service, admin_ctx
    ) -> None:
        with pytest.raises(ValidationError, match="unknown item"):
            service.set_level(
                admin_ctx,
                scope="user",
                values={"ui.sidebar.collapsed_groups": ["overview", "nope"]},
            )
        assert _rows(admin_ctx.tenant_id) == []

    def test_reset_with_none_deletes_the_row(self, service, admin_ctx) -> None:
        key = "ui.markdown.toolbar"
        service.set_level(admin_ctx, scope="user", values={key: "off"})
        assert len(_rows(admin_ctx.tenant_id, key=key)) == 1

        payload = service.set_level(admin_ctx, scope="user", values={key: None})
        assert payload["values"] == {}
        assert _rows(admin_ctx.tenant_id, key=key) == []
        assert service.effective(admin_ctx, keys=[key])["values"][key]["source"] == "default"

    def test_reset_of_absent_row_is_a_no_op(self, service, admin_ctx) -> None:
        payload = service.set_level(
            admin_ctx, scope="user", values={"ui.markdown.toolbar": None}
        )
        assert payload["values"] == {}
        assert _preference_audits(admin_ctx.tenant_id) == []

    def test_get_level_returns_only_set_keys_sorted(self, service, admin_ctx) -> None:
        service.set_level(admin_ctx, scope="user", values={"ui.markdown.toolbar": "on"})
        service.set_level(admin_ctx, scope="user", values={"ui.ids.show_readable": False})

        payload = service.get_level(admin_ctx, scope="user")
        assert payload["scope"] == "user"
        assert payload["workspace_id"] is None
        assert list(payload["values"]) == ["ui.ids.show_readable", "ui.markdown.toolbar"]

    def test_workspace_scope_requires_a_workspace_id(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="requires a workspace_id"):
            service.set_level(admin_ctx, scope="workspace", values={})

    def test_unknown_scope_raises(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="Unknown preference scope"):
            service.get_level(admin_ctx, scope="organization")

    def test_values_must_be_a_mapping(self, service, admin_ctx) -> None:
        with pytest.raises(ValidationError, match="must be an object"):
            service.set_level(admin_ctx, scope="user", values=["ui.ids.show_readable"])

    def test_per_key_validator_rejects_and_writes_nothing(
        self, service, admin_ctx, registry
    ) -> None:
        calls: list[list[str]] = []

        def _validator(value) -> None:
            calls.append(list(value))
            if "bad" in value:
                raise ValidationError("rejected by key validator")

        registry.register_preference_key(
            PreferenceKey(
                key="test.validated",
                value_type="str_list",
                default=[],
                levels=frozenset({"global", "workspace", "user"}),
                validator=_validator,
            )
        )
        calls.clear()

        with pytest.raises(ValidationError, match="rejected by key validator"):
            # The *second* entry is invalid: the first must not be written either.
            service.set_level(
                admin_ctx,
                scope="user",
                values={"ui.ids.show_readable": False, "test.validated": ["bad"]},
            )
        assert _rows(admin_ctx.tenant_id) == []
        assert calls == [["bad"]]

        service.set_level(admin_ctx, scope="user", values={"test.validated": ["ok"]})
        assert calls == [["bad"], ["ok"]]
        assert _rows(admin_ctx.tenant_id, key="test.validated")[0].value == ["ok"]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class TestPermissions:
    @pytest.mark.parametrize("role", ["viewer", "editor"])
    def test_workspace_write_requires_workspace_config(
        self, service, tenant_a, workspace_a, alice, role: str
    ) -> None:
        ctx = _make_ctx(tenant_a, alice, role, workspace=workspace_a)
        with pytest.raises(PermissionDeniedError, match="workspace_config"):
            service.set_level(
                ctx,
                scope="workspace",
                values={"ui.markdown.toolbar": "off"},
                workspace_id=workspace_a.id,
            )
        assert _rows(tenant_a.id, scope="workspace") == []

    def test_admin_may_write_the_workspace_level(
        self, service, admin_ctx, workspace_a
    ) -> None:
        payload = service.set_level(
            admin_ctx,
            scope="workspace",
            values={"ui.markdown.toolbar": "off"},
            workspace_id=workspace_a.id,
        )
        assert payload == {
            "scope": "workspace",
            "workspace_id": str(workspace_a.id),
            "values": {"ui.markdown.toolbar": "off"},
        }

    def test_global_write_requires_the_admin_role(
        self, service, editor_ctx
    ) -> None:
        with pytest.raises(PermissionDeniedError, match="role 'admin' required"):
            service.set_level(editor_ctx, scope="global", values={"ui.markdown.toolbar": "on"})
        assert _rows(editor_ctx.tenant_id, scope="global") == []

    def test_admin_may_write_the_global_level(self, service, admin_ctx) -> None:
        payload = service.set_level(
            admin_ctx, scope="global", values={"ui.markdown.toolbar": "on"}
        )
        assert payload["values"] == {"ui.markdown.toolbar": "on"}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class TestAudit:
    def test_workspace_write_is_audited(self, service, admin_ctx, workspace_a) -> None:
        service.set_level(
            admin_ctx,
            scope="workspace",
            values={"ui.markdown.toolbar": "off"},
            workspace_id=workspace_a.id,
        )
        entries = _preference_audits(admin_ctx.tenant_id)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.op == "update"
        assert str(entry.entity_id) == str(workspace_a.id)
        assert entry.details == {
            "scope": "workspace",
            "workspace_id": str(workspace_a.id),
            "key": "ui.markdown.toolbar",
            "old": None,
            "new": "off",
        }

    def test_global_write_is_audited_with_the_tenant_as_entity(
        self, service, admin_ctx
    ) -> None:
        service.set_level(admin_ctx, scope="global", values={"ui.ids.show_readable": False})
        entry = _preference_audits(admin_ctx.tenant_id)[0]
        assert str(entry.entity_id) == str(admin_ctx.tenant_id)
        assert entry.details["scope"] == "global"
        assert entry.details["workspace_id"] is None
        assert (entry.details["old"], entry.details["new"]) == (None, False)

    def test_audit_records_the_previous_value_on_reset(
        self, service, admin_ctx, workspace_a
    ) -> None:
        service.set_level(
            admin_ctx,
            scope="workspace",
            values={"ui.markdown.toolbar": "off"},
            workspace_id=workspace_a.id,
        )
        service.set_level(
            admin_ctx,
            scope="workspace",
            values={"ui.markdown.toolbar": None},
            workspace_id=workspace_a.id,
        )
        entries = _preference_audits(admin_ctx.tenant_id)
        assert len(entries) == 2
        assert {(e.details["old"], e.details["new"]) for e in entries} == {
            (None, "off"),
            ("off", None),
        }

    def test_user_write_is_not_audited(self, service, admin_ctx) -> None:
        service.set_level(admin_ctx, scope="user", values={"ui.markdown.toolbar": "off"})
        service.set_level(admin_ctx, scope="user", values={"ui.markdown.toolbar": None})
        assert _preference_audits(admin_ctx.tenant_id) == []


# ---------------------------------------------------------------------------
# Tenant isolation and context hygiene
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_two_tenants_do_not_see_each_other(self, tenant_a, tenant_b) -> None:
        key = "ui.ids.show_readable"
        _set_global_row(tenant_a, key, False)
        _set_global_row(tenant_b, key, True)

        assert resolve_for(
            tenant_id=tenant_a.id, workspace_id=None, user_id=None, key=key
        ) == (False, "global")
        assert resolve_for(
            tenant_id=tenant_b.id, workspace_id=None, user_id=None, key=key
        ) == (True, "global")

        levels_a = levels_for(
            tenant_id=tenant_a.id, workspace_id=None, user_id=None, key=key
        )
        assert levels_a.global_ is False

    def test_workspace_rows_are_scoped_to_the_workspace(
        self, service, admin_ctx, tenant_a, workspace_a
    ) -> None:
        other = _make_workspace(tenant_a, "ws-other")
        service.set_level(
            admin_ctx,
            scope="workspace",
            values={"ui.markdown.toolbar": "off"},
            workspace_id=workspace_a.id,
        )
        other_level = service.get_level(
            admin_ctx, scope="workspace", workspace_id=other.id
        )
        assert other_level["values"] == {}

    def test_user_rows_are_scoped_to_the_caller(
        self, service, tenant_a, workspace_a
    ) -> None:
        alice = _make_user(tenant_a, "alice")
        bob = _make_user(tenant_a, "bob")
        key = "ui.markdown.toolbar"

        service.set_level(_make_ctx(tenant_a, alice, "editor"), scope="user", values={key: "on"})

        bob_payload = service.get_level(_make_ctx(tenant_a, bob, "editor"), scope="user")
        assert bob_payload["values"] == {}
        bob_effective = service.effective(_make_ctx(tenant_a, bob, "editor"), keys=[key])
        assert bob_effective["values"][key]["source"] == "default"


class TestContextFreeReads:
    def test_levels_for_returns_unset_for_missing_levels(
        self, service, admin_ctx
    ) -> None:
        service.set_level(admin_ctx, scope="user", values={"ui.markdown.toolbar": "on"})
        levels = levels_for(
            tenant_id=admin_ctx.tenant_id,
            workspace_id=None,
            user_id=admin_ctx.user_id,
            key="ui.markdown.toolbar",
        )
        assert levels.global_ is UNSET
        assert levels.workspace is UNSET
        assert levels.user == "on"

    def test_levels_for_uses_a_single_query(self, tenant_a, django_assert_num_queries) -> None:
        key = "ui.ids.show_readable"
        _set_global_row(tenant_a, key, False)
        with django_assert_num_queries(1):
            levels_for(
                tenant_id=tenant_a.id, workspace_id=None, user_id=None, key=key
            )

    def test_levels_for_restores_previous_tenant(self, tenant_a, tenant_b) -> None:
        key = "ui.ids.show_readable"
        _set_global_row(tenant_a, key, False)
        _set_global_row(tenant_b, key, True)

        TenantContext.set_tenant(tenant_a.id)
        levels_for(tenant_id=tenant_b.id, workspace_id=None, user_id=None, key=key)
        assert TenantContext.get_tenant() == tenant_a.id

    def test_levels_for_clears_when_no_tenant_was_set(self, tenant_a) -> None:
        key = "ui.ids.show_readable"
        _set_global_row(tenant_a, key, False)

        TenantContext.clear_tenant()
        levels_for(tenant_id=tenant_a.id, workspace_id=None, user_id=None, key=key)
        assert TenantContext.is_set() is False

    def test_levels_for_restores_previous_tenant_on_exception(
        self, tenant_a, tenant_b
    ) -> None:
        TenantContext.set_tenant(tenant_a.id)
        with pytest.raises(ValidationError, match="Unknown preference key"):
            levels_for(
                tenant_id=tenant_b.id,
                workspace_id=None,
                user_id=None,
                key="ui.does.not_exist",
            )
        assert TenantContext.get_tenant() == tenant_a.id

    def test_resolve_for_restores_previous_tenant_on_exception(
        self, tenant_a, tenant_b
    ) -> None:
        TenantContext.set_tenant(tenant_a.id)
        with pytest.raises(ValidationError, match="Unknown preference key"):
            resolve_for(
                tenant_id=tenant_b.id,
                workspace_id=None,
                user_id=None,
                key="ui.does.not_exist",
            )
        assert TenantContext.get_tenant() == tenant_a.id
