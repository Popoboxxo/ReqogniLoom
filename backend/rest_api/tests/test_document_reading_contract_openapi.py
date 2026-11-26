"""P1.6 — the document reading contract is documented as it behaves.

``GET /api/v1/documents/{id}/view/`` answered ``200``/``400``/``403``/``404`` at
runtime while the operation advertised only the two ``200`` representations, and
its response serializer left most fields without ``help_text`` (and wrongly
marked ``read_only_reason`` required). A generated client therefore could not
see the error contract and had to guess the meaning of ``anchor``,
``projection``, the lock codes and the polymorphic ``value``.

This module pins the *published* contract:

* the operation declares ``200`` for **both** media types plus ``400``/``403``/
  ``404``, each with the real error envelope and a description that names the
  actual cause (not the generic blanket);
* ``read_only_reason`` is optional on the wire (it is not in the schema's
  ``required`` list);
* every declared field of the reading serializer family documents its
  semantics.

The runtime side (the responses these codes describe) is pinned by
``test_document_view_r1.py``; the schema-completeness gate runs separately in
``test_schema_completeness_1388.py``.
"""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

from rest_api.serializers import (
    DocumentReadingCapabilitiesSerializer,
    DocumentReadingChapterSerializer,
    DocumentReadingFieldSerializer,
    DocumentReadingLockedSerializer,
    DocumentReadingProjectionSerializer,
    DocumentReadingSerializer,
)

pytestmark = pytest.mark.django_db

VIEW_PATH = "/api/v1/documents/{id}/view/"

#: Every serializer of the reading object, including the nested ones — the
#: help_text gate below walks each of them.
_READING_SERIALIZERS = (
    DocumentReadingSerializer,
    DocumentReadingChapterSerializer,
    DocumentReadingProjectionSerializer,
    DocumentReadingLockedSerializer,
    DocumentReadingFieldSerializer,
    DocumentReadingCapabilitiesSerializer,
)


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    """The generated OpenAPI 3.0 document (same output as ``GET /api/schema/``)."""
    return SchemaGenerator().get_schema(request=None, public=True)


def _operation(schema: dict) -> dict:
    return schema["paths"][VIEW_PATH]["get"]


def _component_for(schema: dict, required_properties: set[str]) -> dict:
    """Return the single component schema exposing *required_properties*."""
    matches = [
        component
        for component in schema.get("components", {}).get("schemas", {}).values()
        if required_properties
        <= set(component.get("properties", {}))
        and component.get("type") == "object"
    ]
    assert len(matches) == 1, (
        f"expected exactly one component with {sorted(required_properties)}, "
        f"got {len(matches)}"
    )
    return matches[0]


class TestDocumentReadingOperationContract:
    """The operation publishes both representations and every error it can answer."""

    def test_declares_both_success_media_types(self, openapi_schema: dict) -> None:
        success = _operation(openapi_schema)["responses"]["200"]

        assert set(success["content"]) == {"application/json", "text/markdown"}

    @pytest.mark.parametrize("status_code", ["400", "403", "404"])
    def test_declares_the_error_response(
        self, openapi_schema: dict, status_code: str
    ) -> None:
        """Each error carries the documented envelope, not a bare description."""
        response = _operation(openapi_schema)["responses"][status_code]

        assert response["content"]["application/json"]["schema"]
        assert response["description"]

    @pytest.mark.parametrize(
        ("status_code", "expected_fragments"),
        [
            # 400 — the malformed-pk branch of ``BaseEntityViewSet.initial``.
            ("400", {"uuid", "validation_error", "404"}),
            # 403 — RBAC matrix or item-level narrowing.
            ("403", {"permission", "item-level", "rbac"}),
            # 404 — unknown or foreign id, explicitly no existence oracle.
            ("404", {"tenant", "not_found", "existence oracle"}),
        ],
    )
    def test_error_description_names_the_real_cause(
        self,
        openapi_schema: dict,
        status_code: str,
        expected_fragments: set[str],
    ) -> None:
        """The generic pool descriptions would not mention any of these."""
        description = _operation(openapi_schema)["responses"][status_code][
            "description"
        ].lower()

        missing = {fragment for fragment in expected_fragments if fragment not in description}
        assert not missing, (description, missing)

    def test_documents_the_reading_object_as_the_json_body(
        self, openapi_schema: dict
    ) -> None:
        """The 200 JSON entry is the reading serializer, not a free-form object."""
        content = _operation(openapi_schema)["responses"]["200"]["content"]
        json_schema = content["application/json"]["schema"]
        markdown_schema = content["text/markdown"]["schema"]

        assert json_schema.get("$ref", "").endswith("DocumentReading")
        assert markdown_schema == {"type": "string"}


class TestDocumentReadingSerializerContract:
    """``read_only_reason`` is optional and every field explains itself."""

    def test_read_only_reason_is_not_required(self) -> None:
        field = DocumentReadingCapabilitiesSerializer().fields["read_only_reason"]

        assert field.required is False

    def test_schema_does_not_mark_read_only_reason_required(
        self, openapi_schema: dict
    ) -> None:
        component = _component_for(
            openapi_schema, {"can_write", "read_only_reason"}
        )

        assert "read_only_reason" in component["properties"]
        assert "read_only_reason" not in component.get("required", [])

    @pytest.mark.parametrize(
        "serializer",
        _READING_SERIALIZERS,
        ids=lambda serializer: serializer.__name__,
    )
    def test_every_field_documents_its_semantics(self, serializer) -> None:
        """A field without help_text is an undocumented wire promise."""
        undocumented = sorted(
            name
            for name, field in serializer().fields.items()
            if not str(getattr(field, "help_text", "") or "").strip()
        )

        assert not undocumented, (
            f"{serializer.__name__} leaves these fields undocumented: {undocumented}"
        )

    def test_schema_carries_the_field_descriptions(self, openapi_schema: dict) -> None:
        """help_text reaches the published document (not just the Python class)."""
        component = _component_for(openapi_schema, {"chapters", "projection", "fields"})

        for name in ("id", "artifact_id", "uid", "title", "kind", "doc_date", "status"):
            assert component["properties"][name].get("description"), name
