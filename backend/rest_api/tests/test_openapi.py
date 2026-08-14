"""
Tests for COMP-RA-005 OpenApiGenerator.

leaf_id : COMP-RA-005
req_id  : REQ-L2-RA-002
          REQ-L3-RA005-001, REQ-L3-RA005-002

Covers:
  - ErrorResponseSerializer is a valid DRF Serializer.
  - COMMON_ERROR_RESPONSES has expected HTTP codes.
  - openapi.py exports the correct public symbols.
  - Settings have BearerAuth security scheme configured.
"""
from __future__ import annotations

import pytest


class TestErrorResponseSerializer:
    """ErrorResponseSerializer matches REQ-L2-RA-009 format."""

    def test_error_response_serializer_fields(self) -> None:
        from rest_api.openapi import ErrorResponseSerializer

        ser = ErrorResponseSerializer(
            {"error": {"code": "NOT_FOUND", "message": "Not found.", "details": []}}
        )
        data = ser.data
        assert "error" in data

    def test_error_body_serializer_fields(self) -> None:
        from rest_api.openapi import ErrorBodySerializer

        ser = ErrorBodySerializer(
            {"code": "VALIDATION_ERROR", "message": "Fail.", "details": []}
        )
        data = ser.data
        assert "code" in data
        assert "message" in data


class TestCommonErrorResponses:
    """COMMON_ERROR_RESPONSES covers expected HTTP status codes."""

    def test_400_present(self) -> None:
        from rest_api.openapi import COMMON_ERROR_RESPONSES
        assert 400 in COMMON_ERROR_RESPONSES

    def test_401_present(self) -> None:
        from rest_api.openapi import COMMON_ERROR_RESPONSES
        assert 401 in COMMON_ERROR_RESPONSES

    def test_403_present(self) -> None:
        from rest_api.openapi import COMMON_ERROR_RESPONSES
        assert 403 in COMMON_ERROR_RESPONSES

    def test_404_present(self) -> None:
        from rest_api.openapi import COMMON_ERROR_RESPONSES
        assert 404 in COMMON_ERROR_RESPONSES

    def test_500_present(self) -> None:
        from rest_api.openapi import COMMON_ERROR_RESPONSES
        assert 500 in COMMON_ERROR_RESPONSES


class TestSettingsBearerAuthScheme:
    """REQ-L3-RA005-001: SPECTACULAR_SETTINGS has BearerAuth security scheme."""

    def test_bearer_auth_in_append_components(self) -> None:
        from django.conf import settings

        spectacular = getattr(settings, "SPECTACULAR_SETTINGS", {})
        append = spectacular.get("APPEND_COMPONENTS", {})
        schemes = append.get("securitySchemes", {})
        assert "BearerAuth" in schemes, "BearerAuth security scheme missing from SPECTACULAR_SETTINGS"

    def test_bearer_auth_scheme_type(self) -> None:
        from django.conf import settings

        spectacular = getattr(settings, "SPECTACULAR_SETTINGS", {})
        scheme = spectacular["APPEND_COMPONENTS"]["securitySchemes"]["BearerAuth"]
        assert scheme["type"] == "http"
        assert scheme["scheme"] == "bearer"


class TestPublicExports:
    """openapi.py exports the correct public symbols."""

    def test_all_exports(self) -> None:
        from rest_api.openapi import __all__

        required = {
            "ErrorResponseSerializer",
            "ErrorBodySerializer",
            "ErrorDetailSerializer",
            "COMMON_ERROR_RESPONSES",
        }
        assert required.issubset(set(__all__))


# ---------------------------------------------------------------------------
# #447 — query parameters must be declared, not just parsed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    """The generated OpenAPI 3.0 document (same output as GET /api/schema/)."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _query_params(schema: dict, path: str) -> dict:
    """Return ``{name: parameter}`` for the GET operation's query parameters."""
    assert path in schema["paths"], (
        f"{path} missing from the OpenAPI schema; available: "
        f"{sorted(p for p in schema['paths'] if 'bundle' in p or 'search' in p)}"
    )
    operation = schema["paths"][path]["get"]
    return {
        p["name"]: p for p in operation.get("parameters", []) if p["in"] == "query"
    }


class TestDocumentedQueryParameters:
    """#447: drf-spectacular cannot see ``request.query_params.get(...)``.

    Both endpoints below read their inputs straight off ``query_params``, so
    without an explicit ``@extend_schema(parameters=[...])`` the generated
    document advertised no query parameters at all. requirement-bundle
    documented only its path ``id`` while accepting six, and /search/
    documented none while *requiring* two -- a generated client could only
    produce requests the server rejects with 400. That also left the correct
    bundle path undiscoverable from the spec alone (#446).
    """

    BUNDLE_PATH = "/api/v1/architecture/{id}/requirement-bundle/"
    SEARCH_PATH = "/api/v1/search/"

    def test_requirement_bundle_documents_every_accepted_query_param(
        self, openapi_schema: dict
    ) -> None:
        params = _query_params(openapi_schema, self.BUNDLE_PATH)
        assert set(params) == {
            "depth",
            "filter_mode",
            "fields",
            "output_format",
            "mode",
            "async",
        }

    def test_requirement_bundle_enums_match_the_validated_values(
        self, openapi_schema: dict
    ) -> None:
        # The view answers 400 for anything outside these sets, so the schema
        # has to name them or a client cannot avoid the rejection.
        params = _query_params(openapi_schema, self.BUNDLE_PATH)
        assert set(params["mode"]["schema"]["enum"]) == {"raw", "compressed"}
        assert set(params["output_format"]["schema"]["enum"]) == {
            "json",
            "markdown",
            "csv",
        }

    def test_search_documents_its_two_mandatory_params(
        self, openapi_schema: dict
    ) -> None:
        params = _query_params(openapi_schema, self.SEARCH_PATH)
        assert params["q"]["required"] is True
        assert params["workspace_id"]["required"] is True
        assert {"type", "page", "limit"}.issubset(set(params))
