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
def make_artifact(tenant, workspace):
    """Create a real ``Artifact`` row backing an item type + custom_fields.

    ``count_usages`` (Task 5) queries ``Artifact.custom_fields`` directly, so
    its tests need real rows, not a mocked service — same reasoning as the
    cross-tenant MCP probe in ``test_attribute_definition_tools.py``.
    """
    from persistence.models import Artifact
    from persistence.tenancy import TenantContext

    def _make(item_type: str, custom_fields: dict) -> "Artifact":
        TenantContext.set_tenant(tenant.id)
        try:
            return Artifact.objects.create(
                tenant_id=tenant.id,
                workspace=workspace,
                artifact_type=item_type,
                custom_fields=custom_fields,
            )
        finally:
            TenantContext.clear_tenant()

    return _make


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
        "version": 0, "attributes": [], "sections": [],
    }


@pytest.mark.django_db
def test_update_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.update_global(editor_ctx, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_update_global_persists_a_given_sections_list(service, admin_ctx, seeded) -> None:
    out = service.update_global(
        admin_ctx, "Risk", "standard", [TITLE],
        sections=[{"name": "general", "visible": False, "layout": "half"}],
    )
    assert out["sections"] == [
        {"name": "general", "order": 0, "visible": False, "layout": "half"}
    ]


@pytest.mark.django_db
def test_update_global_preserves_existing_sections_when_omitted(
    service, admin_ctx, seeded
) -> None:
    service.update_global(
        admin_ctx, "Risk", "standard", [TITLE],
        sections=[{"name": "general", "visible": False}],
    )
    out = service.update_global(admin_ctx, "Risk", "standard", [dict(TITLE, order=9)])
    assert out["sections"] == [
        {"name": "general", "order": 0, "visible": False, "layout": "full"}
    ]


@pytest.mark.django_db
def test_update_workspace_persists_a_given_sections_list(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        out = service.update_workspace(
            admin_ctx, "Risk", workspace.id, [TITLE],
            sections=[{"name": "general", "layout": "half"}],
        )
    assert out["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "half"}
    ]


@pytest.mark.django_db
def test_update_global_returns_the_propagated_count(
    service, admin_ctx, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        # The resolve() call below bumps the GLOBAL row's version once on its
        # own (Task 7: ensure_sections backfills 'sections' the first time
        # anything reads a pre-Task-7 row, including via a workspace
        # resolve()) -- version starts at 2, not 1, once update_global runs.
        service.resolve(editor_ctx, "Risk", workspace.id)
        out = service.update_global(
            admin_ctx, "Risk", "standard", [dict(TITLE, section="header")]
        )
    assert out["propagated_workspace_count"] == 1
    assert out["version"] == 3


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


# --- A malformed workspace id is "no such workspace", not a 500 -------------


# --- Task 1: create_global / delete_global --------------------------------


@pytest.mark.django_db
def test_create_global_adds_an_extended_attribute(service, admin_ctx, seeded) -> None:
    out = service.create_global(
        admin_ctx, "Risk", "standard",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
    )
    assert [a["name"] for a in out["attributes"]] == ["risk_comment", "title"]


@pytest.mark.django_db
def test_create_global_rejects_kind_core(service, admin_ctx, seeded) -> None:
    with pytest.raises(AttributeSchemaError):
        service.create_global(
            admin_ctx, "Risk", "standard",
            {"name": "risk_comment", "kind": "core", "type": "text"},
        )


@pytest.mark.django_db
def test_create_global_rejects_a_colliding_name(service, admin_ctx, seeded) -> None:
    with pytest.raises(AttributeSchemaError):
        service.create_global(
            admin_ctx, "Risk", "standard",
            {"name": "title", "kind": "extended", "type": "text"},
        )


@pytest.mark.django_db
def test_create_global_rejects_a_name_matching_a_model_field(
    service, admin_ctx, seeded
) -> None:
    """``description`` is a real column on the ``Risk`` model."""
    with pytest.raises(AttributeSchemaError):
        service.create_global(
            admin_ctx, "Risk", "standard",
            {"name": "description", "kind": "extended", "type": "text"},
        )


@pytest.mark.django_db
def test_create_global_of_an_uninitialized_row_is_not_found(service, admin_ctx) -> None:
    from application.attribute_definition_service import AttributeDefinitionNotFound

    with pytest.raises(AttributeDefinitionNotFound):
        service.create_global(
            admin_ctx, "Icd", "minimal",
            {"name": "severity", "kind": "extended", "type": "text"},
        )


@pytest.mark.django_db
def test_delete_global_removes_an_extended_attribute(service, admin_ctx, tenant) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    out = service.delete_global(admin_ctx, "Risk", "standard", "note")
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_delete_global_rejects_a_core_attribute(service, admin_ctx, seeded) -> None:
    with pytest.raises(AttributeSchemaError):
        service.delete_global(admin_ctx, "Risk", "standard", "title")


@pytest.mark.django_db
def test_delete_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.delete_global(editor_ctx, "Risk", "standard", "title")


# --- Task 2: create_workspace / delete_workspace --------------------------


@pytest.mark.django_db
def test_create_workspace_adds_a_workspace_only_attribute(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.create_workspace(
            admin_ctx, "Risk", workspace.id,
            {"name": "risk_comment", "kind": "extended", "type": "text"},
        )
    assert out["is_customized"] is True
    assert [a["name"] for a in out["attributes"]] == ["risk_comment", "title"]


@pytest.mark.django_db
def test_create_workspace_materializes_on_first_touch(
    service, admin_ctx, workspace, seeded
) -> None:
    """No prior GET/resolve for this item type in this workspace."""
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.create_workspace(
            admin_ctx, "Risk", workspace.id,
            {"name": "risk_comment", "kind": "extended", "type": "text"},
        )
    assert "title" in [a["name"] for a in out["attributes"]]


@pytest.mark.django_db
def test_create_workspace_rejects_a_colliding_name(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        with pytest.raises(AttributeSchemaError):
            service.create_workspace(
                admin_ctx, "Risk", workspace.id,
                {"name": "title", "kind": "extended", "type": "text"},
            )


@pytest.mark.django_db
def test_delete_workspace_removes_a_workspace_only_attribute(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.create_workspace(
            admin_ctx, "Risk", workspace.id,
            {"name": "risk_comment", "kind": "extended", "type": "text"},
        )
        out = service.delete_workspace(admin_ctx, "Risk", workspace.id, "risk_comment")
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_delete_workspace_of_an_inherited_attribute_diverges_and_does_not_come_back(
    service, admin_ctx, workspace, tenant
) -> None:
    """Deleting an attribute the workspace only ever inherited from global.

    ``note`` (kind="extended") is used, not ``title`` — deleting a core
    attribute is correctly rejected regardless of inheritance, that is
    :func:`test_delete_workspace_rejects_a_core_attribute` below.

    Verified against ``GlobalAttributeDefinitionStore._derived_row_filter``:
    propagation only ever rewrites ``is_customized=False`` rows, so once the
    delete flips this row to ``is_customized=True`` a later global update no
    longer reaches it and the deletion is permanent until an explicit reset.
    """
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)  # materialize, no override yet
        out = service.delete_workspace(admin_ctx, "Risk", workspace.id, "note")
        assert out["is_customized"] is True
        assert [a["name"] for a in out["attributes"]] == ["title"]

        # A subsequent global propagation must NOT resurrect it.
        service.update_global(admin_ctx, "Risk", "standard", [TITLE, dict(NOTE, order=9)])
        still = service.resolve(admin_ctx, "Risk", workspace.id)
    assert [a["name"] for a in still["attributes"]] == ["title"]


@pytest.mark.django_db
def test_delete_workspace_rejects_a_core_attribute(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        with pytest.raises(AttributeSchemaError):
            service.delete_workspace(admin_ctx, "Risk", workspace.id, "title")


@pytest.mark.django_db
def test_create_workspace_requires_admin(service, editor_ctx, workspace, seeded) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        with pytest.raises(PermissionDeniedError):
            service.create_workspace(
                editor_ctx, "Risk", workspace.id,
                {"name": "risk_comment", "kind": "extended", "type": "text"},
            )


# --- Task 4: per-attribute "origin" on the workspace-scoped payload -------


@pytest.mark.django_db
def test_resolve_marks_an_unmodified_inherited_attribute_as_global(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.resolve(editor_ctx, "Risk", workspace.id)
    assert out["origins"]["title"] == "global"


@pytest.mark.django_db
def test_delete_workspace_marks_the_surviving_inherited_attribute_as_global_customized(
    service, admin_ctx, workspace, tenant
) -> None:
    """Task 2's finding: is_customized is per-DEFINITION, not per-attribute —
    once ANY workspace edit lands, every surviving inherited attribute reads
    as "global (customized)", not just the one that was actually touched.
    That is documented, expected behaviour here, not a bug."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        service.delete_workspace(admin_ctx, "Risk", workspace.id, "note")
        out = service.resolve(admin_ctx, "Risk", workspace.id)
    assert [a["name"] for a in out["attributes"]] == ["title"]
    assert out["origins"]["title"] == "global_customized"


@pytest.mark.django_db
def test_create_workspace_marks_the_new_attribute_as_workspace_only(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.create_workspace(
            admin_ctx, "Risk", workspace.id,
            {"name": "risk_comment", "kind": "extended", "type": "text"},
        )
    assert out["origins"]["risk_comment"] == "workspace_only"
    assert out["origins"]["title"] == "global_customized"


# --- Task 5: count_usages --------------------------------------------------


@pytest.mark.django_db
def test_count_usages_of_an_unreferenced_attribute_is_zero(
    service, admin_ctx, workspace
) -> None:
    assert service.count_usages(admin_ctx, "Risk", workspace.id, "note") == 0


@pytest.mark.django_db
def test_count_usages_counts_artifacts_referencing_the_attribute(
    service, admin_ctx, workspace, make_artifact
) -> None:
    make_artifact("Risk", {"note": "a"})
    make_artifact("Risk", {"note": "b"})
    make_artifact("Risk", {})  # no 'note' key at all — must not be counted
    make_artifact("Issue", {"note": "a"})  # different item_type — must not be counted
    assert service.count_usages(admin_ctx, "Risk", workspace.id, "note") == 2


@pytest.mark.django_db
def test_count_usages_is_scoped_by_option_value(
    service, admin_ctx, workspace, make_artifact
) -> None:
    make_artifact("Risk", {"category": "a"})
    make_artifact("Risk", {"category": "a"})
    make_artifact("Risk", {"category": "b"})
    assert service.count_usages(admin_ctx, "Risk", workspace.id, "category") == 3
    assert (
        service.count_usages(admin_ctx, "Risk", workspace.id, "category", "a") == 2
    )
    assert (
        service.count_usages(admin_ctx, "Risk", workspace.id, "category", "b") == 1
    )


@pytest.mark.django_db
def test_count_usages_requires_admin(service, editor_ctx, workspace) -> None:
    with pytest.raises(PermissionDeniedError):
        service.count_usages(editor_ctx, "Risk", workspace.id, "note")


# --- Task 9: export_definition / import_definition -------------------------


@pytest.mark.django_db
def test_export_definition_global_produces_a_re_importable_document(
    service, admin_ctx, seeded
) -> None:
    exported = service.export_definition(admin_ctx, "Risk", preset="standard")
    assert exported["schema_version"] == 1
    assert exported["item_type"] == "Risk"
    assert [a["name"] for a in exported["attributes"]] == ["title"]
    assert exported["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"}
    ]

    imported = service.import_definition(admin_ctx, "Risk", exported, preset="standard")
    assert [a["name"] for a in imported["attributes"]] == ["title"]


@pytest.mark.django_db
def test_export_definition_workspace_scope(service, admin_ctx, workspace, seeded) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        exported = service.export_definition(admin_ctx, "Risk", workspace_id=workspace.id)
    assert exported["item_type"] == "Risk"
    assert [a["name"] for a in exported["attributes"]] == ["title"]


@pytest.mark.django_db
def test_import_definition_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.import_definition(
            editor_ctx, "Risk", {"schema_version": 1, "attributes": []}, preset="standard"
        )


@pytest.mark.django_db
def test_import_definition_rejects_an_unrecognized_schema_version(
    service, admin_ctx, seeded
) -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        service.import_definition(
            admin_ctx, "Risk", {"schema_version": 99, "attributes": []}, preset="standard"
        )
    assert "schema_version" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_import_definition_rejects_an_invalid_on_collision(service, admin_ctx, seeded) -> None:
    with pytest.raises(AttributeSchemaError):
        service.import_definition(
            admin_ctx, "Risk", {"schema_version": 1, "attributes": []},
            preset="standard", on_collision="explode",
        )


@pytest.mark.django_db
def test_import_definition_rejects_an_incoming_core_attribute(
    service, admin_ctx, seeded
) -> None:
    with pytest.raises(AttributeSchemaError):
        service.import_definition(
            admin_ctx, "Risk",
            {
                "schema_version": 1,
                "attributes": [{"name": "sneaky", "kind": "core", "type": "text"}],
            },
            preset="standard",
        )


@pytest.mark.django_db
def test_import_definition_skip_leaves_the_existing_entry_and_adds_only_new_names(
    service, admin_ctx, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    out = service.import_definition(
        admin_ctx, "Risk",
        {
            "schema_version": 1,
            "attributes": [
                dict(NOTE, required=True),  # collides with 'note' -- skipped
                {"name": "extra_note", "kind": "extended", "type": "text"},
            ],
        },
        preset="standard", on_collision="skip",
    )
    by_name = {a["name"]: a for a in out["attributes"]}
    assert by_name["note"]["required"] is False  # unchanged
    assert "extra_note" in by_name


@pytest.mark.django_db
def test_import_definition_overwrite_replaces_the_colliding_entry(
    service, admin_ctx, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    out = service.import_definition(
        admin_ctx, "Risk",
        {"schema_version": 1, "attributes": [dict(NOTE, required=True)]},
        preset="standard", on_collision="overwrite",
    )
    by_name = {a["name"]: a for a in out["attributes"]}
    assert by_name["note"]["required"] is True


@pytest.mark.django_db
def test_import_definition_rename_suffixes_colliding_names(
    service, admin_ctx, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE, dict(NOTE, name="note_2")],
    )
    out = service.import_definition(
        admin_ctx, "Risk",
        {"schema_version": 1, "attributes": [dict(NOTE, required=True)]},
        preset="standard", on_collision="rename",
    )
    names = {a["name"] for a in out["attributes"]}
    assert "note_3" in names
    by_name = {a["name"]: a for a in out["attributes"]}
    assert by_name["note"]["required"] is False  # original untouched


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["not-a-uuid", "", "42"])
def test_resolve_maps_a_malformed_workspace_id_to_not_found(admin_ctx, bad) -> None:
    """The lookup raises Django's ValidationError, which no handler maps.

    Reachable since Task 11: the artifact ViewSets pass a workspace id taken
    straight off the request body into ``validate_artifact_fields``.
    """
    from application.attribute_definition_service import AttributeDefinitionNotFound

    with pytest.raises(AttributeDefinitionNotFound):
        AttributeDefinitionService().resolve(admin_ctx, "Risk", bad)


# --- Post-review M1/M2: sections + name validation on import ---------------


@pytest.mark.django_db
def test_import_definition_carries_sections_through_the_round_trip(
    service, admin_ctx, seeded
) -> None:
    """M1: ``export_definition`` emits 'sections'; import used to drop them.

    The target's sections are materialized first (via ``get_global``) so the
    import has a real collision to resolve — the old code let the target's own
    entry survive silently, i.e. a deliberately hidden section came back
    visible after a round trip.
    """
    service.update_global(
        admin_ctx, "Risk", "standard", [TITLE],
        [{"name": "general", "order": 0, "visible": False, "layout": "half"}],
    )
    exported = service.export_definition(admin_ctx, "Risk", preset="standard")
    assert exported["sections"] == [
        {"name": "general", "order": 0, "visible": False, "layout": "half"}
    ]

    assert service.get_global(admin_ctx, "Risk", "minimal")["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"}
    ]
    imported = service.import_definition(
        admin_ctx, "Risk", exported, preset="minimal", on_collision="overwrite"
    )
    assert imported["sections"] == [
        {"name": "general", "order": 0, "visible": False, "layout": "half"}
    ]


@pytest.mark.django_db
def test_import_definition_skip_keeps_the_target_sections_and_adds_new_ones(
    service, admin_ctx, seeded
) -> None:
    service.get_global(admin_ctx, "Risk", "minimal")  # materialize 'general'
    imported = service.import_definition(
        admin_ctx, "Risk",
        {
            "schema_version": 1,
            "attributes": [],
            "sections": [
                {"name": "general", "order": 0, "visible": False, "layout": "half"},
                {"name": "extra", "order": 1, "visible": False, "layout": "half"},
            ],
        },
        preset="minimal", on_collision="skip",
    )
    by_name = {s["name"]: s for s in imported["sections"]}
    assert by_name["general"]["visible"] is True  # existing entry wins
    assert by_name["extra"]["visible"] is False  # new entry added


@pytest.mark.django_db
def test_import_definition_without_a_sections_key_leaves_them_untouched(
    service, admin_ctx, seeded
) -> None:
    service.update_global(
        admin_ctx, "Risk", "standard", [TITLE],
        [{"name": "general", "order": 0, "visible": False, "layout": "full"}],
    )
    imported = service.import_definition(
        admin_ctx, "Risk",
        {"schema_version": 1, "attributes": [NOTE]},
        preset="standard",
    )
    assert imported["sections"] == [
        {"name": "general", "order": 0, "visible": False, "layout": "full"}
    ]


@pytest.mark.django_db
def test_import_definition_rejects_a_name_shadowing_a_model_field(
    service, admin_ctx, seeded
) -> None:
    """M2: 'owner' is a real ``persistence.Risk`` column — ``create_global``
    refuses it, so import must too (spec section 6)."""
    with pytest.raises(AttributeSchemaError) as exc:
        service.import_definition(
            admin_ctx, "Risk",
            {
                "schema_version": 1,
                "attributes": [{"name": "owner", "kind": "extended", "type": "text"}],
            },
            preset="standard",
        )
    assert "model field" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_import_definition_rejects_a_non_snake_case_name(
    service, admin_ctx, seeded
) -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        service.import_definition(
            admin_ctx, "Risk",
            {
                "schema_version": 1,
                "attributes": [{"name": "Created At", "kind": "extended", "type": "text"}],
            },
            preset="standard",
        )
    assert "snake_case" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_import_definition_rejects_a_non_list_sections_key(
    service, admin_ctx, seeded
) -> None:
    with pytest.raises(AttributeSchemaError):
        service.import_definition(
            admin_ctx, "Risk",
            {"schema_version": 1, "attributes": [], "sections": {"general": True}},
            preset="standard",
        )
