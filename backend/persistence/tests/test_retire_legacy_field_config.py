"""The legacy field-config models are gone; values survived (Decision D3).

Also covers binding (m) (Task 9, SDD ledger): a ``CustomFieldValue`` whose
custom field collided with a core attribute name — and was therefore skipped,
not migrated, by Task 8's data migration — must not silently masquerade as
that core attribute's value after the ``attribute_name`` relink. See
``persistence/migrations/0080_retire_legacy_field_config.py::
drop_collision_orphans``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

import persistence.models as models_module
from persistence.models import Artifact, CustomFieldValue, Tenant, Workspace


def test_legacy_models_are_removed() -> None:
    assert not hasattr(models_module, "AttributeVisibilityConfig")
    assert not hasattr(models_module, "CustomFieldDefinition")
    assert not hasattr(models_module, "CustomFieldType")


def test_custom_field_value_is_keyed_by_attribute_name() -> None:
    field_names = {f.name for f in CustomFieldValue._meta.get_fields()}
    assert "attribute_name" in field_names
    assert "definition" not in field_names


@pytest.mark.django_db
def test_one_value_per_artifact_and_attribute_name() -> None:
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    # Workspace/Artifact/CustomFieldValue are all TenantScopedModel: the
    # default manager's get_queryset() calls TenantContext.get_tenant()
    # unconditionally, even with an explicit tenant_id= kwarg (brief's draft
    # of this test omitted the arming and raised TenantContextNotSetError).
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant_id=tenant.id, name="ws", preset={})
        artifact = Artifact.objects.create(
            tenant_id=tenant.id, workspace=workspace, artifact_type="Requirement",
        )
        CustomFieldValue.objects.create(
            tenant_id=tenant.id, artifact=artifact, attribute_name="Kostenstelle",
            value="A",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomFieldValue.objects.create(
                    tenant_id=tenant.id, artifact=artifact,
                    attribute_name="Kostenstelle", value="B",
                )
    finally:
        TenantContext.clear_tenant()


def test_legacy_services_are_removed() -> None:
    import importlib

    for module in (
        "application.attribute_visibility_service",
        "application.custom_field_service",
        "mcp_server.tools.custom_field",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_legacy_rest_routes_are_removed() -> None:
    from django.urls import NoReverseMatch, reverse

    for name in (
        "attribute-visibility-config-list",
        "workspace-custom-field-definitions",
        "custom-field-definition-detail",
        "artifact-custom-field-values",
    ):
        with pytest.raises(NoReverseMatch):
            reverse(name)


def test_custom_field_mcp_tools_are_gone() -> None:
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    names = {tool["name"] for tool in build_manifest()["tools"]}
    assert not {n for n in names if n.startswith("custom_field.")}


def test_workspace_lookup_no_longer_offers_custom_field_entity_key() -> None:
    """The ENTITY_SPECS lazy-import registry test in
    ``mcp_server/tests/test_mcp_workspace_scope.py`` walks every entry and
    imports its model — a leftover ``"custom_field"`` entry pointing at the
    now-deleted ``CustomFieldDefinition`` would fail there. This test pins the
    intent directly at the source of truth.
    """
    from application.workspace_lookup import ENTITY_SPECS

    assert "custom_field" not in ENTITY_SPECS


# ---------------------------------------------------------------------------
# Binding (m) — collision-skipped custom fields must not become orphaned
# masquerading values (0080_retire_legacy_field_config.drop_collision_orphans)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDropCollisionOrphans:
    """Exercises ``drop_collision_orphans`` directly against the live app
    registry. Unlike ``backfill_attribute_names`` (frozen: it needs the
    now-deleted ``CustomFieldDefinition``), every model this function touches
    — ``CustomFieldValue``, ``Artifact``, ``WorkspaceAttributeDefinition`` —
    is still live, so the real migration function can be driven directly
    instead of only inferred from the schema's end state.
    """

    @staticmethod
    def _migration():
        import importlib

        return importlib.import_module(
            "persistence.migrations.0080_retire_legacy_field_config"
        )

    @staticmethod
    def _make_tenant_workspace():
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
            )
        finally:
            TenantContext.clear_tenant()
        return tenant, workspace

    def test_drops_value_whose_name_collided_with_a_core_attribute(self):
        """The central binding-(m) case: a WorkspaceAttributeDefinition exists
        for this (tenant, workspace, item_type) and does NOT list
        "status" among its attributes as an extended/custom one (Task 8
        skipped it, "core always wins") — the orphaned value must be dropped.
        """
        from attribute_definitions.models import WorkspaceAttributeDefinition
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            WorkspaceAttributeDefinition.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                item_type="Requirement",
                preset="standard",
                definition_json={
                    "attributes": [
                        {"name": "status", "kind": "core"},
                        {"name": "title", "kind": "core"},
                    ]
                },
                is_customized=True,
            )
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            orphan = CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact, attribute_name="status",
                value="collided",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        self._migration().drop_collision_orphans(django.apps.apps, None)

        assert not CustomFieldValue.unscoped.filter(id=orphan.id).exists()

    def test_keeps_a_value_whose_name_is_a_real_custom_attribute(self):
        """A non-colliding custom field IS listed in the
        WorkspaceAttributeDefinition Task 8 wrote — its value must survive.
        """
        from attribute_definitions.models import WorkspaceAttributeDefinition
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            WorkspaceAttributeDefinition.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                item_type="Requirement",
                preset="standard",
                definition_json={
                    "attributes": [
                        {"name": "status", "kind": "core"},
                        {"name": "Kostenstelle", "kind": "extended"},
                    ]
                },
                is_customized=True,
            )
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            survivor = CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Kostenstelle", value="42",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        self._migration().drop_collision_orphans(django.apps.apps, None)

        assert CustomFieldValue.unscoped.filter(id=survivor.id).exists()

    def test_keeps_a_value_whose_item_type_has_no_workspace_attribute_definition(self):
        """No WorkspaceAttributeDefinition row at all for this (workspace,
        item_type) means "unrelated gap", not "collision" — must NOT be
        treated as an orphan (guards against Artifact.artifact_type values
        outside attribute_definitions' bootstrapped item types/casing)."""
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="SomeUncoveredType",
            )
            survivor = CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Whatever", value="42",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        self._migration().drop_collision_orphans(django.apps.apps, None)

        assert CustomFieldValue.unscoped.filter(id=survivor.id).exists()

    def test_logs_a_warning_for_each_dropped_orphan(self, caplog):
        import logging

        from attribute_definitions.models import WorkspaceAttributeDefinition
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            WorkspaceAttributeDefinition.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                item_type="Requirement",
                preset="standard",
                definition_json={"attributes": [{"name": "status", "kind": "core"}]},
                is_customized=True,
            )
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact, attribute_name="status",
                value="collided",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        with caplog.at_level(logging.WARNING):
            self._migration().drop_collision_orphans(django.apps.apps, None)

        assert any(
            "collision-skipped" in record.message and str(tenant.id) in record.message
            for record in caplog.records
        )
