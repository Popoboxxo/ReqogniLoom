"""AttributeDefinitionService — the single Layer-2 facade (ADR-01)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.attribute_definition_service import (
    AttributeDefinitionService,
    AttributeSchemaError,
    FieldValidationError,
)
from application.base import PermissionDeniedError
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, Workspace

TITLE = {"name": "title", "kind": "core", "type": "text", "required": True,
         "ai_elicit": True, "export": True}
NOTE = {"name": "note", "kind": "extended", "type": "text", "section": "extra"}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    """Create the workspace with the tenant context armed.

    ``Workspace`` is a ``TenantScopedModel``: its default manager's
    ``get_queryset()`` calls ``TenantContext.get_tenant()`` unconditionally
    (even when ``tenant_id`` is passed explicitly to ``.create()``), so a
    bare ``Workspace.objects.create(tenant_id=...)`` without an active
    context raises ``TenantContextNotSetError`` — repo-wide convention
    (``test_adr_service.py::te020_workspace``,
    ``test_artifact_version_service.py::env``) sets/clears it around the
    create call. The plan brief's snippet omitted this.
    """
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def admin_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        workspace_id=workspace.id, active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def editor_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        workspace_id=workspace.id, active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeDefinitionService:
    return AttributeDefinitionService()


@pytest.fixture
def seeded(tenant) -> None:
    store = GlobalAttributeDefinitionStore()
    for preset in ("minimal", "standard", "extended"):
        store.initialize(tenant.id, "Risk", preset, [TITLE])


@pytest.mark.django_db
def test_resolve_materializes_for_the_workspace_preset(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.resolve(editor_ctx, "Risk", workspace.id)
    assert out["item_type"] == "Risk"
    assert out["preset"] == "standard"
    assert out["is_customized"] is False
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_resolve_is_allowed_for_a_non_admin(service, editor_ctx, workspace, seeded) -> None:
    """Reading the definition is what applying it requires — never admin-only."""
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(editor_ctx, "Risk", workspace.id)


@pytest.mark.django_db
def test_get_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.get_global(editor_ctx, "Risk", "standard")


@pytest.mark.django_db
def test_get_global_of_a_missing_row_reports_uninitialized(service, admin_ctx) -> None:
    out = service.get_global(admin_ctx, "Icd", "minimal")
    assert out == {
        "item_type": "Icd", "preset": "minimal", "initialized": False,
        "version": 0, "attributes": [],
    }


@pytest.mark.django_db
def test_update_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.update_global(editor_ctx, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_update_global_returns_the_propagated_count(
    service, admin_ctx, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(editor_ctx, "Risk", workspace.id)
        out = service.update_global(
            admin_ctx, "Risk", "standard", [dict(TITLE, section="header")]
        )
    assert out["propagated_workspace_count"] == 1
    assert out["version"] == 2


@pytest.mark.django_db
def test_update_global_writes_an_audit_entry_with_the_update_op(
    service, admin_ctx, seeded
) -> None:
    """#265: an undeclared op string 500s after the mutation. Only OP_UPDATE."""
    with patch.object(AttributeDefinitionService, "_audit") as audit:
        service.update_global(admin_ctx, "Risk", "standard", [dict(TITLE, order=4)])
    assert audit.call_args.kwargs["operation"] == "update"
    assert audit.call_args.kwargs["entity_type"] == "GlobalAttributeDefinition"


@pytest.mark.django_db
def test_update_workspace_sets_is_customized_and_invalidates_the_cache(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with patch(
            "application.attribute_definition_service.invalidate_workspace_caches"
        ) as invalidate:
            out = service.update_workspace(
                admin_ctx, "Risk", workspace.id, [TITLE, NOTE]
            )
    assert out["is_customized"] is True
    invalidate.assert_called_once_with(str(workspace.id))


@pytest.mark.django_db
def test_reset_workspace_restores_the_global(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        service.update_workspace(admin_ctx, "Risk", workspace.id, [TITLE, NOTE])
        out = service.reset_workspace(admin_ctx, "Risk", workspace.id)
    assert out["is_customized"] is False
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_update_workspace_rejects_a_core_rename_with_a_schema_error(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with pytest.raises(AttributeSchemaError):
            service.update_workspace(
                admin_ctx, "Risk", workspace.id,
                [{"name": "headline", "kind": "core", "type": "text"}],
            )


@pytest.mark.django_db
def test_validate_artifact_fields_on_create_demands_required_fields(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        with pytest.raises(FieldValidationError) as exc:
            service.validate_artifact_fields(
                editor_ctx, "Risk", workspace.id, {}, None
            )
    assert "title" in exc.value.errors


@pytest.mark.django_db
def test_validate_artifact_fields_on_update_skips_untouched_fields(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.validate_artifact_fields(
            editor_ctx, "Risk", workspace.id, {"description": "d"}, {"title": ""}
        )


@pytest.mark.django_db
def test_elicit_attributes_returns_only_ai_elicit_entries_in_section_order(
    service, editor_ctx, workspace, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard",
        [TITLE, dict(NOTE, ai_elicit=True), {"name": "quiet", "kind": "extended",
                                             "type": "text", "section": "zzz"}],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.elicit_attributes(editor_ctx, "Risk", workspace.id)
    assert [a["name"] for a in out] == ["note", "title"]


@pytest.mark.django_db
def test_export_attributes_returns_only_export_entries(
    service, editor_ctx, workspace, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.export_attributes(editor_ctx, "Risk", workspace.id)
    assert [a["name"] for a in out] == ["title"]


@pytest.mark.django_db
def test_downgrade_warnings_merges_the_preset_check_with_the_attribute_probe(
    service, admin_ctx, workspace, tenant
) -> None:
    store = GlobalAttributeDefinitionStore()
    store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "extended"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with patch("presets.services.validate_downgrade", return_value=["baselines"]):
            warnings = service.downgrade_warnings(admin_ctx, workspace.id, "minimal")
    assert "baselines" in warnings
    assert any("note" in w for w in warnings)


@pytest.mark.django_db
def test_downgrade_warnings_reports_an_unbootstrapped_target_instead_of_crashing(
    service, admin_ctx, workspace, tenant
) -> None:
    """Ledger binding (i), Task 5 review I-2, consumed here: the target preset

    was never bootstrapped for this item type. Must surface as one more
    warning, not raise (which would abort every other item type's check in
    the same call) and not silently report zero attribute-loss (which used
    to be the case before the fix)."""
    store = GlobalAttributeDefinitionStore()
    store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "extended"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with patch("presets.services.validate_downgrade", return_value=[]):
            warnings = service.downgrade_warnings(admin_ctx, workspace.id, "minimal")
    assert any("Risk" in w and "not been initialized" in w for w in warnings)
