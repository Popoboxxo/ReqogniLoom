"""AttributeCatalogService — Layer-2 facade for the central catalog (WS5 #942)."""
from __future__ import annotations

import uuid

import pytest

from application.attribute_catalog_service import (
    AttributeCatalogNotFound,
    AttributeCatalogService,
)
from application.attribute_definition_service import AttributeSchemaError
from application.base import PermissionDeniedError
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

EXISTING = {
    "name": "note",
    "kind": "extended",
    "type": "textarea",
    "section": "extra",
}
CATALOG_BLOCK = {
    "name": "severity_rating",
    "kind": "extended",
    "type": "enum",
    "options": [{"value": "low", "label_de": "Niedrig", "label_en": "Low"}],
}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="cat-t", slug=f"cat-t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def admin_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def editor_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeCatalogService:
    return AttributeCatalogService()


@pytest.fixture
def seeded(tenant) -> None:
    """A bootstrapped global ``Risk/standard`` definition with one attribute."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [EXISTING]
    )


def _create(service: AttributeCatalogService, ctx: AuthContext, **overrides):
    payload = {
        "name": "severity_rating",
        "definition": CATALOG_BLOCK,
        "category": "risk",
        "tags": ["risk", "severity"],
        "label": {"de": "Auswirkung", "en": "Severity rating"},
        "help_text": {"de": "Wie schlimm?", "en": "How bad?"},
        "origin": "manual",
    }
    payload.update(overrides)
    return service.create_entry(ctx, **payload)


class TestPermissionGate:
    def test_list_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.list_entries(editor_ctx)

    def test_create_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.create_entry(editor_ctx, name="x", definition=CATALOG_BLOCK)

    def test_update_requires_admin(self, service, admin_ctx, editor_ctx) -> None:
        entry = _create(service, admin_ctx)
        with pytest.raises(PermissionDeniedError):
            service.update_entry(editor_ctx, entry["id"], category="other")

    def test_export_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.export_catalog(editor_ctx)


class TestCreate:
    def test_create_normalizes_metadata(self, service, admin_ctx) -> None:
        entry = _create(service, admin_ctx)
        assert entry["name"] == "severity_rating"
        assert entry["category"] == "risk"
        assert entry["tags"] == ["risk", "severity"]
        assert entry["label"] == {"de": "Auswirkung", "en": "Severity rating"}
        assert entry["deprecated"] is False
        # The stored block is the fully normalized attribute shape.
        assert entry["definition"]["kind"] == "extended"
        assert entry["definition"]["section"] == "general"
        assert entry["definition"]["visible"] is True
        assert entry["definition"]["options"][0]["value"] == "low"

    def test_create_rejects_duplicate_name(self, service, admin_ctx) -> None:
        _create(service, admin_ctx)
        with pytest.raises(AttributeSchemaError) as exc:
            _create(service, admin_ctx)
        assert "already exists" in str(exc.value)

    def test_create_rejects_core_definition(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError) as exc:
            service.create_entry(
                admin_ctx,
                name="title",
                definition={"name": "title", "kind": "core", "type": "text"},
            )
        assert "kind='extended'" in str(exc.value)

    def test_create_rejects_malformed_definition(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError):
            service.create_entry(
                admin_ctx, name="broken", definition={"name": "broken"}
            )

    def test_create_rejects_bad_tags(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError):
            _create(service, admin_ctx, tags="risk")

    def test_create_rejects_unknown_label_key(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError):
            _create(service, admin_ctx, label={"fr": "Impact"})

    def test_create_is_audited(self, service, admin_ctx) -> None:
        from audit.models import AuditEntry

        TenantContext.set_tenant(admin_ctx.tenant_id)
        try:
            before = AuditEntry.unscoped.count()
        finally:
            TenantContext.clear_tenant()
        _create(service, admin_ctx)
        TenantContext.set_tenant(admin_ctx.tenant_id)
        try:
            after = AuditEntry.unscoped.count()
        finally:
            TenantContext.clear_tenant()
        assert after == before + 1


class TestListSearch:
    def test_list_and_filters(self, service, admin_ctx) -> None:
        _create(service, admin_ctx)
        _create(
            service, admin_ctx, name="cost", category="finance", tags=["money"]
        )
        assert [e["name"] for e in service.list_entries(admin_ctx)] == [
            "cost",
            "severity_rating",
        ]
        assert [e["name"] for e in service.list_entries(admin_ctx, category="risk")] == [
            "severity_rating"
        ]
        assert [e["name"] for e in service.list_entries(admin_ctx, tags=["money"])] == [
            "cost"
        ]
        assert [e["name"] for e in service.list_entries(admin_ctx, query="severity")] == [
            "severity_rating"
        ]

    def test_deprecated_entries_are_hidden_by_default(self, service, admin_ctx) -> None:
        entry = _create(service, admin_ctx)
        service.deprecate_entry(admin_ctx, entry["id"])
        assert service.list_entries(admin_ctx) == []
        assert len(service.list_entries(admin_ctx, include_deprecated=True)) == 1

    def test_search_requires_a_query(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError):
            service.search_entries(admin_ctx, query="  ")

    def test_get_unknown_entry_raises(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeCatalogNotFound):
            service.get_entry(admin_ctx, uuid.uuid4())

    def test_get_malformed_id_raises_not_found(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeCatalogNotFound):
            service.get_entry(admin_ctx, "not-a-uuid")


class TestUpdate:
    def test_partial_update_leaves_other_fields(self, service, admin_ctx) -> None:
        entry = _create(service, admin_ctx)
        updated = service.update_entry(admin_ctx, entry["id"], category="safety")
        assert updated["category"] == "safety"
        assert updated["tags"] == ["risk", "severity"]
        assert updated["version"] == entry["version"] + 1

    def test_rename_to_existing_name_is_rejected(self, service, admin_ctx) -> None:
        _create(service, admin_ctx)
        other = _create(service, admin_ctx, name="cost")
        with pytest.raises(AttributeSchemaError):
            service.update_entry(admin_ctx, other["id"], name="severity_rating")

    def test_rename_to_own_name_is_accepted(self, service, admin_ctx) -> None:
        """A rename to the entry's own current name is not a collision."""
        entry = _create(service, admin_ctx)
        same = service.update_entry(admin_ctx, entry["id"], name="severity_rating")
        assert same["name"] == "severity_rating"

    def test_empty_update_does_not_bump_version(self, service, admin_ctx) -> None:
        entry = _create(service, admin_ctx)
        assert service.update_entry(admin_ctx, entry["id"])["version"] == 1

    def test_deprecate_toggle(self, service, admin_ctx) -> None:
        entry = _create(service, admin_ctx)
        assert service.deprecate_entry(admin_ctx, entry["id"])["deprecated"] is True
        assert (
            service.deprecate_entry(admin_ctx, entry["id"], deprecated=False)[
                "deprecated"
            ]
            is False
        )

    def test_update_unknown_entry_raises(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeCatalogNotFound):
            service.update_entry(admin_ctx, uuid.uuid4(), category="x")


class TestAddToDefinition:
    def test_copies_block_and_sets_defaults(self, service, admin_ctx, seeded) -> None:
        entry = _create(service, admin_ctx)
        result = service.add_to_definition(
            admin_ctx, entry["id"], "Risk", preset="standard"
        )
        names = {a["name"] for a in result["definition"]["attributes"]}
        assert names == {"severity_rating", "note"}
        copied = next(
            a for a in result["definition"]["attributes"] if a["name"] == "severity_rating"
        )
        assert copied["type"] == "enum"
        assert copied["options"][0]["value"] == "low"
        # The catalog's display metadata is deliberately NOT copied into the
        # definition — it drives the catalog UI only.
        assert copied["label"] == {"de": "", "en": ""}
        assert result["on_collision"] == "skip"

    def test_skip_keeps_the_definition_value(self, service, admin_ctx, seeded) -> None:
        service.create_entry(
            admin_ctx,
            name="note",
            definition={
                "name": "note",
                "kind": "extended",
                "type": "text",
                "label": {"de": "Katalog", "en": "Catalog"},
            },
        )
        entry = next(e for e in service.list_entries(admin_ctx) if e["name"] == "note")
        result = service.add_to_definition(
            admin_ctx, entry["id"], "Risk", preset="standard", on_collision="skip"
        )
        note = next(
            a
            for a in result["definition"]["attributes"]
            if a["name"] == "note"
        )
        assert note["type"] == "textarea"

    def test_overwrite_replaces_the_definition_entry(
        self, service, admin_ctx, seeded
    ) -> None:
        entry = service.create_entry(
            admin_ctx,
            name="note",
            definition={
                "name": "note",
                "kind": "extended",
                "type": "text",
                "label": {"de": "Katalog", "en": "Catalog"},
            },
        )
        result = service.add_to_definition(
            admin_ctx,
            entry["id"],
            "Risk",
            preset="standard",
            on_collision="overwrite",
        )
        notes = [
            a for a in result["definition"]["attributes"] if a["name"] == "note"
        ]
        assert len(notes) == 1
        assert notes[0]["label"] == {"de": "Katalog", "en": "Catalog"}

    def test_rename_suffixes_the_incoming_name(self, service, admin_ctx, seeded) -> None:
        entry = service.create_entry(
            admin_ctx,
            name="note",
            definition={"name": "note", "kind": "extended", "type": "text"},
        )
        result = service.add_to_definition(
            admin_ctx, entry["id"], "Risk", preset="standard", on_collision="rename"
        )
        assert [a["name"] for a in result["definition"]["attributes"]] == [
            "note",
            "note_2",
        ]

    def test_add_to_workspace_definition(
        self, service, admin_ctx, workspace, seeded
    ) -> None:
        entry = _create(service, admin_ctx)
        from unittest.mock import patch

        with patch("presets.services.get_preset") as get_preset:
            get_preset.return_value.preset = "standard"
            result = service.add_to_definition(
                admin_ctx, entry["id"], "Risk", workspace_id=workspace.id
            )
        assert "severity_rating" in [a["name"] for a in result["definition"]["attributes"]]

    def test_requires_a_target(self, service, admin_ctx, seeded) -> None:
        entry = _create(service, admin_ctx)
        with pytest.raises(AttributeSchemaError):
            service.add_to_definition(admin_ctx, entry["id"], "Risk")

    def test_rejects_unknown_item_type(self, service, admin_ctx, seeded) -> None:
        entry = _create(service, admin_ctx)
        with pytest.raises(AttributeSchemaError):
            service.add_to_definition(admin_ctx, entry["id"], "Nope", preset="standard")

    def test_rejects_bad_on_collision(self, service, admin_ctx, seeded) -> None:
        entry = _create(service, admin_ctx)
        with pytest.raises(AttributeSchemaError):
            service.add_to_definition(
                admin_ctx, entry["id"], "Risk", preset="standard", on_collision="merge"
            )

    def test_unknown_catalog_entry(self, service, admin_ctx, seeded) -> None:
        with pytest.raises(AttributeCatalogNotFound):
            service.add_to_definition(
                admin_ctx, uuid.uuid4(), "Risk", preset="standard"
            )


class TestExportImport:
    def test_round_trip_into_an_empty_catalog(self, service, admin_ctx) -> None:
        _create(service, admin_ctx)
        document = service.export_catalog(admin_ctx)
        assert document["schema_version"] == 1
        assert document["document_type"] == "attribute_catalog"
        assert len(document["entries"]) == 1

        # A second service instance on the same tenant; simulate a fresh
        # catalog by importing into a tenant whose entry was removed.
        from persistence.models import AttributeCatalogEntry
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(admin_ctx.tenant_id)
        try:
            AttributeCatalogEntry.objects.all().delete()
        finally:
            TenantContext.clear_tenant()

        summary = service.import_catalog(admin_ctx, document)
        assert summary == {"created": 1, "updated": 0, "total": 1}
        entries = service.list_entries(admin_ctx)
        assert entries[0]["name"] == "severity_rating"
        assert entries[0]["definition"]["type"] == "enum"
        assert entries[0]["category"] == "risk"

    def test_import_collisions(self, service, admin_ctx) -> None:
        _create(service, admin_ctx)
        document = service.export_catalog(admin_ctx)
        document["entries"][0]["category"] = "changed"

        assert service.import_catalog(admin_ctx, document, on_collision="skip")[
            "updated"
        ] == 0
        assert service.list_entries(admin_ctx)[0]["category"] == "risk"

        assert service.import_catalog(admin_ctx, document, on_collision="overwrite")[
            "updated"
        ] == 1
        assert service.list_entries(admin_ctx)[0]["category"] == "changed"

        renamed = service.import_catalog(admin_ctx, document, on_collision="rename")
        assert renamed["created"] == 1
        assert {e["name"] for e in service.list_entries(admin_ctx)} == {
            "severity_rating",
            "severity_rating_2",
        }

    def test_import_rejects_bad_documents(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeSchemaError):
            service.import_catalog(admin_ctx, {"entries": []})
        with pytest.raises(AttributeSchemaError):
            service.import_catalog(
                admin_ctx, {"schema_version": 1, "entries": "nope"}
            )
        with pytest.raises(AttributeSchemaError):
            service.import_catalog(
                admin_ctx,
                {"schema_version": 1, "entries": []},
                on_collision="merge",
            )

    def test_import_is_atomic_on_a_malformed_entry(self, service, admin_ctx) -> None:
        document = {
            "schema_version": 1,
            "entries": [
                {"name": "good", "definition": CATALOG_BLOCK},
                {"name": "broken", "definition": {"name": "broken"}},
            ],
        }
        with pytest.raises(AttributeSchemaError):
            service.import_catalog(admin_ctx, document)
        assert service.list_entries(admin_ctx) == []
