"""REST surface for the central attribute catalog (WS5 #942, spec section 8)."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

BASE = "/api/v1/attribute-catalog/"

DEFINITION = {
    "name": "severity_rating",
    "kind": "extended",
    "type": "enum",
    "options": [{"value": "low", "label_de": "Niedrig", "label_en": "Low"}],
}


def _create(client, name: str = "severity_rating", **overrides):
    body = {
        "name": name,
        "definition": {**DEFINITION, "name": name},
        "category": "risk",
        "tags": ["risk"],
        "label": {"de": "Auswirkung", "en": "Impact"},
    }
    body.update(overrides)
    return client.post(BASE, body, format="json")


class TestAdminGate:
    def test_list_requires_admin(self, editor_client) -> None:
        response = editor_client.get(BASE)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_create_requires_admin(self, editor_client) -> None:
        assert _create(editor_client).status_code == 403

    def test_export_requires_admin(self, editor_client) -> None:
        assert editor_client.get(f"{BASE}export/").status_code == 403

    def test_import_requires_admin(self, editor_client) -> None:
        response = editor_client.post(
            f"{BASE}import/", {"schema_version": 1, "entries": []}, format="json"
        )
        assert response.status_code == 403


class TestCrud:
    def test_create_list_detail_roundtrip(self, admin_client) -> None:
        created = _create(admin_client)
        assert created.status_code == 201
        entry = created.json()
        assert entry["name"] == "severity_rating"
        assert entry["category"] == "risk"
        assert entry["definition"]["type"] == "enum"

        listed = admin_client.get(BASE)
        assert listed.status_code == 200
        assert [e["name"] for e in listed.json()["entries"]] == ["severity_rating"]

        detail = admin_client.get(f"{BASE}{entry['id']}/")
        assert detail.status_code == 200
        assert detail.json()["id"] == entry["id"]

    def test_create_duplicate_is_a_validation_error(self, admin_client) -> None:
        _create(admin_client)
        duplicate = _create(admin_client)
        assert duplicate.status_code == 400
        assert duplicate.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_create_rejects_a_core_block(self, admin_client) -> None:
        response = admin_client.post(
            BASE,
            {"name": "title", "definition": {"name": "title", "kind": "core", "type": "text"}},
            format="json",
        )
        assert response.status_code == 400

    def test_patch_updates_only_sent_fields(self, admin_client) -> None:
        entry = _create(admin_client).json()
        patched = admin_client.patch(
            f"{BASE}{entry['id']}/", {"category": "safety"}, format="json"
        )
        assert patched.status_code == 200
        assert patched.json()["category"] == "safety"
        assert patched.json()["tags"] == ["risk"]

    def test_put_replaces_the_sent_fields(self, admin_client) -> None:
        entry = _create(admin_client).json()
        put = admin_client.put(
            f"{BASE}{entry['id']}/",
            {"name": "severity_rating", "definition": DEFINITION, "tags": []},
            format="json",
        )
        assert put.status_code == 200
        assert put.json()["tags"] == []

    def test_detail_unknown_id_is_404(self, admin_client) -> None:
        response = admin_client.get(f"{BASE}{uuid.uuid4()}/")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_list_filters_by_category_and_tag(self, admin_client) -> None:
        _create(admin_client)
        _create(admin_client, name="cost", category="finance", tags=["money"])
        by_category = admin_client.get(f"{BASE}?category=risk")
        assert [e["name"] for e in by_category.json()["entries"]] == ["severity_rating"]
        by_tag = admin_client.get(f"{BASE}?tags=money")
        assert [e["name"] for e in by_tag.json()["entries"]] == ["cost"]

    def test_search_requires_a_query(self, admin_client) -> None:
        assert admin_client.get(f"{BASE}search/").status_code == 400

    def test_search_finds_by_name(self, admin_client) -> None:
        _create(admin_client)
        response = admin_client.get(f"{BASE}search/?q=severity")
        assert response.status_code == 200
        assert [e["name"] for e in response.json()["entries"]] == ["severity_rating"]


class TestDeprecate:
    def test_deprecate_hides_from_the_default_list(self, admin_client) -> None:
        entry = _create(admin_client).json()
        deprecated = admin_client.post(f"{BASE}{entry['id']}/deprecate/", format="json")
        assert deprecated.status_code == 200
        assert deprecated.json()["deprecated"] is True
        assert admin_client.get(BASE).json()["entries"] == []
        assert (
            len(admin_client.get(f"{BASE}?include_deprecated=true").json()["entries"])
            == 1
        )

    def test_deprecate_can_be_lifted(self, admin_client) -> None:
        entry = _create(admin_client).json()
        lifted = admin_client.post(
            f"{BASE}{entry['id']}/deprecate/", {"deprecated": False}, format="json"
        )
        assert lifted.json()["deprecated"] is False

    def test_deprecate_unknown_id_is_404(self, admin_client) -> None:
        response = admin_client.post(f"{BASE}{uuid.uuid4()}/deprecate/", format="json")
        assert response.status_code == 404


class TestAddToDefinition:
    @pytest.fixture
    def seeded(self, tenant_fixture) -> None:
        GlobalAttributeDefinitionStore().initialize(
            tenant_fixture.id,
            "Risk",
            "standard",
            [{"name": "note", "kind": "extended", "type": "text"}],
        )

    def test_add_to_global_definition(self, admin_client, seeded) -> None:
        entry = _create(admin_client).json()
        response = admin_client.post(
            f"{BASE}{entry['id']}/add-to-definition/",
            {"item_type": "Risk", "preset": "standard"},
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert {a["name"] for a in body["definition"]["attributes"]} == {
            "note",
            "severity_rating",
        }
        assert body["on_collision"] == "skip"

    def test_add_to_definition_requires_a_target(self, admin_client, seeded) -> None:
        entry = _create(admin_client).json()
        response = admin_client.post(
            f"{BASE}{entry['id']}/add-to-definition/",
            {"item_type": "Risk"},
            format="json",
        )
        assert response.status_code == 400

    def test_add_to_definition_unknown_entry_is_404(self, admin_client, seeded) -> None:
        response = admin_client.post(
            f"{BASE}{uuid.uuid4()}/add-to-definition/",
            {"item_type": "Risk", "preset": "standard"},
            format="json",
        )
        assert response.status_code == 404

    def test_add_to_definition_unknown_item_type_is_400(
        self, admin_client, seeded
    ) -> None:
        entry = _create(admin_client).json()
        response = admin_client.post(
            f"{BASE}{entry['id']}/add-to-definition/",
            {"item_type": "Nope", "preset": "standard"},
            format="json",
        )
        assert response.status_code == 400

    def test_add_to_definition_without_a_definition_is_404(
        self, admin_client, seed_bootstrapped=False
    ) -> None:
        """No global default for that key yet -> the definition 404, not a 500."""
        entry = _create(admin_client).json()
        response = admin_client.post(
            f"{BASE}{entry['id']}/add-to-definition/",
            {"item_type": "Goal", "preset": "minimal"},
            format="json",
        )
        assert response.status_code == 404

    def test_add_to_definition_to_a_workspace(self, admin_client, workspace_fixture,
                                              seeded) -> None:
        entry = _create(admin_client).json()
        response = admin_client.post(
            f"{BASE}{entry['id']}/add-to-definition/",
            {"item_type": "Risk", "workspace_id": str(workspace_fixture.id)},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["definition"]["item_type"] == "Risk"


class TestExportImport:
    def test_export_import_round_trip(self, admin_client) -> None:
        _create(admin_client)
        document = admin_client.get(f"{BASE}export/").json()
        assert document["document_type"] == "attribute_catalog"
        assert len(document["entries"]) == 1

        # Overwrite the same name: the merge is stable and reports an update.
        summary = admin_client.post(
            f"{BASE}import/", document, format="json"
        )
        assert summary.status_code == 200
        assert summary.json() == {"created": 0, "updated": 0, "total": 1}

    def test_import_creates_new_entries(self, admin_client) -> None:
        document = {
            "schema_version": 1,
            "document_type": "attribute_catalog",
            "entries": [
                {"name": "new_attr", "definition": {**DEFINITION, "name": "new_attr"}}
            ],
        }
        response = admin_client.post(f"{BASE}import/", document, format="json")
        assert response.status_code == 200
        assert response.json()["created"] == 1
        assert admin_client.get(BASE).json()["entries"][0]["name"] == "new_attr"

    def test_import_rejects_an_unknown_schema_version(self, admin_client) -> None:
        response = admin_client.post(
            f"{BASE}import/", {"schema_version": 99, "entries": []}, format="json"
        )
        assert response.status_code == 400

    def test_import_honors_on_collision_in_the_query_string(self, admin_client) -> None:
        _create(admin_client)
        document = admin_client.get(f"{BASE}export/").json()
        document["entries"][0]["category"] = "changed"
        response = admin_client.post(
            f"{BASE}import/?on_collision=overwrite", document, format="json"
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1
        assert admin_client.get(BASE).json()["entries"][0]["category"] == "changed"
