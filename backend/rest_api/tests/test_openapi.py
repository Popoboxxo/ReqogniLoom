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
