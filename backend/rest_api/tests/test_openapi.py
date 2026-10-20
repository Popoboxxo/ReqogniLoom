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


# ---------------------------------------------------------------------------
# #1362(a) — the review queue's mandatory workspace_id must be discoverable
# ---------------------------------------------------------------------------


class TestReviewQueueQueryParameters:
    """#1362(a): ``GET /api/v1/reviews/pending/`` *requires* ``workspace_id``
    (400 "workspace_id is required" without it) while the OpenAPI document
    declared no query parameter at all — an agent could only learn the
    parameter by trying. Same contract gap class as #447.
    """

    FLAT_PATH = "/api/v1/reviews/pending/"
    ROOT_PATH = "/api/v1/reviews/"
    NESTED_PATH = "/api/v1/workspaces/{workspace_id}/reviews/pending/"

    def test_flat_route_documents_the_required_workspace_id(
        self, openapi_schema: dict
    ) -> None:
        params = _query_params(openapi_schema, self.FLAT_PATH)
        assert params["workspace_id"]["required"] is True
        assert {"item_type", "state"}.issubset(set(params))

    def test_collection_root_documents_the_required_workspace_id(
        self, openapi_schema: dict
    ) -> None:
        """``/api/v1/reviews/`` is the same view under its natural URL — it
        must document the same parameters."""
        params = _query_params(openapi_schema, self.ROOT_PATH)
        assert params["workspace_id"]["required"] is True

    def test_path_scoped_route_documents_the_optional_filters(
        self, openapi_schema: dict
    ) -> None:
        """The nested route takes the workspace from its path segment and
        declares the two optional filters."""
        params = _query_params(openapi_schema, self.NESTED_PATH)
        assert {"item_type", "state"}.issubset(set(params))
        assert "workspace_id" not in params
        assert "workspace_id" in {
            p["name"]
            for p in openapi_schema["paths"][self.NESTED_PATH]["get"].get(
                "parameters", []
            )
            if p["in"] == "path"
        }


# ---------------------------------------------------------------------------
# #696 — the login body token is deprecated and must say so
# ---------------------------------------------------------------------------


class TestLoginBodyTokenDeprecation:
    """#696 (review C-3): clients must be able to discover the deprecation.

    The `token` field of the login response body stays for API/CI tooling, but
    an undocumented deprecation is invisible to generated clients — they would
    keep wiring it into JavaScript and re-open the XSS vector REQ-052 closed.
    """

    LOGIN_PATH = "/api/v1/auth/login/"

    def test_login_documents_deprecation_and_the_opt_out_flag(
        self, openapi_schema: dict
    ) -> None:
        post = openapi_schema["paths"][self.LOGIN_PATH]["post"]
        description = post.get("description", "")

        assert "DEPRECATED" in description
        assert "AUTH_LOGIN_INCLUDE_BODY_TOKEN" in description

    def test_login_documents_the_cookie_as_the_supported_path(
        self, openapi_schema: dict
    ) -> None:
        post = openapi_schema["paths"][self.LOGIN_PATH]["post"]
        description = post.get("description", "")

        assert "reqogniloom_access" in description
        # The 401 contract (REQ-L3-AT001-004) stays documented.
        assert "401" in post.get("responses", {})


# ---------------------------------------------------------------------------
# #1383 — the SE-Auditor report's pagination + count contract is discoverable
# ---------------------------------------------------------------------------


AUDIT_PATH = "/api/v1/workspaces/{workspace_id}/audit/"

#: Every query parameter the audit view actually parses (#1383). Before this,
#: the generated document advertised none of them (#447 class of gap).
AUDIT_QUERY_PARAMETERS = {
    "page_size",
    "limit",
    "offset",
    "include_suppressed",
    "scope",
    "scope_artifact_id",
    "rule_id",
    "severity",
    "artifact_type",
}

#: Response-body fields #1382/#1383 make part of the public contract.
AUDIT_REPORT_FIELDS = {
    "tier",
    "scope",
    "scope_artifact_id",
    "counts",
    "page_counts",
    "truncated",
    "total_findings_available",
    "total_blockers_available",
    "total_effective_blockers",
    "total_warnings_available",
    "total_suppressed_available",
    "total_suppressed_blockers_available",
    "suppressed_filtered",
    "offset",
    "next_offset",
    "findings",
}

AUDIT_COUNT_FIELDS = {
    "total",
    "blockers",
    "warnings",
    "suppressed",
    "suppressed_blockers",
}


def _resolve(schema: dict, node: dict) -> dict:
    """Resolve a ``$ref`` (also wrapped in ``allOf``) against the components."""
    while "allOf" in node:
        node = node["allOf"][0]
    ref = node.get("$ref")
    if not ref:
        return node
    return schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]


class TestAuditReportContract:
    """#1383: the audit endpoint must document what it parses and returns."""

    def test_documents_every_accepted_query_parameter(
        self, openapi_schema: dict
    ) -> None:
        params = _query_params(openapi_schema, AUDIT_PATH)
        assert AUDIT_QUERY_PARAMETERS.issubset(set(params))

    def test_page_size_and_limit_document_the_cap_without_a_schema_maximum(
        self, openapi_schema: dict
    ) -> None:
        params = _query_params(openapi_schema, AUDIT_PATH)
        for name in ("page_size", "limit"):
            assert params[name]["schema"]["minimum"] == 1
            # FR-08/#1382: the parser accepts values above 500 and the service
            # caps the window — advertising `maximum: 500` contradicted that.
            assert "maximum" not in params[name]["schema"]
            assert "capped at 500" in params[name]["description"]
        assert params["offset"]["schema"]["minimum"] == 0
        assert set(params["scope"]["schema"]["enum"]) == {
            "document",
            "project",
            "global",
        }
        assert params["include_suppressed"]["schema"]["default"] is True

    def test_pagination_parameters_document_repeat_rejection(
        self, openapi_schema: dict
    ) -> None:
        """FR-10: repeats are a 400 — the description must say so."""
        params = _query_params(openapi_schema, AUDIT_PATH)
        for name in ("page_size", "limit", "offset"):
            assert "at most once" in params[name]["description"]

    def test_include_suppressed_documents_the_accepted_literals(
        self, openapi_schema: dict
    ) -> None:
        """FR-11/#1382: only `true`/`false`, case-insensitive and trimmed.

        The parser accepts `TRUE` and ` False ` (see
        ``_parse_include_suppressed``), so the document must not claim the
        lowercase literals are the only spellings. Repeats are a 400 like the
        pagination parameters.
        """
        params = _query_params(openapi_schema, AUDIT_PATH)
        description = params["include_suppressed"]["description"].lower()
        assert "`true`" in description and "`false`" in description
        assert "case-insensitive" in description
        assert "whitespace" in description
        assert "at most once" in description

    def test_counts_and_page_counts_have_distinguishable_schemas(
        self, openapi_schema: dict
    ) -> None:
        """FR-03: ground truth vs window must not be the same schema."""
        operation = openapi_schema["paths"][AUDIT_PATH]["get"]
        response_schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        report = _resolve(openapi_schema, response_schema)
        properties = report["properties"]

        counts_node = properties["counts"]
        page_node = properties["page_counts"]
        counts = _resolve(openapi_schema, counts_node)
        page_counts = _resolve(openapi_schema, page_node)

        assert counts is not page_counts
        assert set(counts["properties"]) == AUDIT_COUNT_FIELDS
        assert set(page_counts["properties"]) == AUDIT_COUNT_FIELDS

        # The indistinguishable part was `blockers`: waiver-aware in counts,
        # raw in page_counts. Each block must say which one it is.
        counts_blockers = counts["properties"]["blockers"]["description"].lower()
        page_blockers = page_counts["properties"]["blockers"]["description"].lower()
        assert counts_blockers != page_blockers
        assert "waiver" in counts_blockers
        assert "raw" in page_blockers

        # Both blocks document their identity.
        assert "suppressed_blockers" in report["properties"]["counts"]["description"]
        assert "blockers + warnings" in report["properties"]["page_counts"][
            "description"
        ]

    def test_response_documents_counts_page_counts_and_next_offset(
        self, openapi_schema: dict
    ) -> None:
        operation = openapi_schema["paths"][AUDIT_PATH]["get"]
        response_schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        report = _resolve(openapi_schema, response_schema)
        properties = report["properties"]

        assert AUDIT_REPORT_FIELDS.issubset(set(properties))

        counts = _resolve(openapi_schema, properties["counts"])
        page_counts = _resolve(openapi_schema, properties["page_counts"])
        assert set(counts["properties"]) == AUDIT_COUNT_FIELDS
        assert set(page_counts["properties"]) == AUDIT_COUNT_FIELDS

        assert properties["next_offset"]["type"] == "integer"
        assert properties["next_offset"]["nullable"] is True
        assert properties["findings"]["type"] == "array"
        finding_item = _resolve(openapi_schema, properties["findings"]["items"])
        assert finding_item["type"] == "object"

    def test_declares_the_400_validation_response(self, openapi_schema: dict) -> None:
        operation = openapi_schema["paths"][AUDIT_PATH]["get"]
        assert "400" in operation["responses"]
