"""The legacy field-config models are gone; values survived (Decision D3).

Also covers binding (m) (Task 9, SDD ledger): a ``CustomFieldValue`` whose
custom field collided with a core attribute name — and was therefore skipped,
not migrated, by Task 8's data migration — must not silently masquerade as
that core attribute's value after the ``attribute_name`` relink. See
``persistence/migrations/0080_retire_legacy_field_config.py::
drop_collision_orphans``.

Also covers code-review finding C-1 (this task's fix round): every surviving
``CustomFieldValue`` row must be folded into ``Artifact.custom_fields`` before
the legacy table is dropped, or its data becomes permanently unreadable. See
``persistence/migrations/0080_retire_legacy_field_config.py::
fold_values_into_custom_fields``.
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


# ---------------------------------------------------------------------------
# C-1 (code review, this task's fix round) — surviving CustomFieldValue rows
# must be folded into Artifact.custom_fields before the legacy table is
# dropped (0080_retire_legacy_field_config.fold_values_into_custom_fields).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFoldValuesIntoCustomFields:
    """Exercises ``fold_values_into_custom_fields`` directly against the live
    app registry, same idiom as ``TestDropCollisionOrphans`` above (every
    model it touches — ``CustomFieldValue``, ``Artifact`` — is still live).
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

    def test_normal_value_folds_into_artifact_custom_fields(self):
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Kostenstelle", value="4711",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        self._migration().fold_values_into_custom_fields(django.apps.apps, None)

        artifact.refresh_from_db()
        assert artifact.custom_fields == {"Kostenstelle": "4711"}

    def test_oversized_value_is_truncated_and_logged(self, caplog):
        import logging

        from persistence.custom_fields import MAX_VALUE_STRING_LENGTH
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            oversized = "x" * (MAX_VALUE_STRING_LENGTH + 500)
            CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Notiz", value=oversized,
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        with caplog.at_level(logging.WARNING):
            self._migration().fold_values_into_custom_fields(django.apps.apps, None)

        artifact.refresh_from_db()
        assert len(artifact.custom_fields["Notiz"]) == MAX_VALUE_STRING_LENGTH
        assert artifact.custom_fields["Notiz"] == oversized[:MAX_VALUE_STRING_LENGTH]
        assert any(
            "truncating oversized" in record.message and str(tenant.id) in record.message
            for record in caplog.records
        )

    def test_dotted_key_is_renamed_and_logged(self, caplog):
        import logging

        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="cost.center", value="42",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        with caplog.at_level(logging.WARNING):
            self._migration().fold_values_into_custom_fields(django.apps.apps, None)

        artifact.refresh_from_db()
        assert "cost.center" not in artifact.custom_fields
        assert artifact.custom_fields["cost_center"] == "42"
        assert any(
            "renaming dotted" in record.message and str(tenant.id) in record.message
            for record in caplog.records
        )

    def test_max_keys_overflow_drops_deterministically_and_logs(self, caplog):
        import logging

        from persistence.custom_fields import MAX_KEYS
        from persistence.tenancy import TenantContext

        tenant, workspace = self._make_tenant_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant_id=tenant.id, workspace=workspace,
                artifact_type="Requirement",
            )
            # MAX_KEYS + 3 distinct, zero-padded names so alphabetic sort
            # order is also numeric order — the last 3 (by attribute_name)
            # must be the ones dropped.
            names = [f"field_{i:03d}" for i in range(MAX_KEYS + 3)]
            for name in names:
                CustomFieldValue.objects.create(
                    tenant_id=tenant.id, artifact=artifact,
                    attribute_name=name, value="v",
                )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        with caplog.at_level(logging.WARNING):
            self._migration().fold_values_into_custom_fields(django.apps.apps, None)

        artifact.refresh_from_db()
        assert len(artifact.custom_fields) == MAX_KEYS
        kept = sorted(names)[:MAX_KEYS]
        dropped = sorted(names)[MAX_KEYS:]
        assert set(artifact.custom_fields) == set(kept)
        for name in dropped:
            assert name not in artifact.custom_fields
        assert sum(
            1 for record in caplog.records
            if "dropping" in record.message and "MAX_KEYS" in record.message
        ) == len(dropped)

    def test_collision_orphan_is_gone_before_fold_runs(self):
        """Ordering proof: drop_collision_orphans must run (and actually
        remove the orphan) before fold_values_into_custom_fields ever sees
        it — verifying the assumption, not just assuming the operations list
        order in the migration file is honored.
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
            orphan = CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact, attribute_name="status",
                value="collided",
            )
            survivor = CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Kostenstelle", value="42",
            )
        finally:
            TenantContext.clear_tenant()

        import django.apps

        migration = self._migration()
        migration.drop_collision_orphans(django.apps.apps, None)
        assert not CustomFieldValue.unscoped.filter(id=orphan.id).exists()

        migration.fold_values_into_custom_fields(django.apps.apps, None)

        artifact.refresh_from_db()
        # Only the surviving, non-colliding value was folded — the orphan
        # was never a candidate because it no longer existed by this point.
        assert artifact.custom_fields == {"Kostenstelle": "42"}
        assert "status" not in artifact.custom_fields
        assert CustomFieldValue.unscoped.filter(id=survivor.id).exists()
