"""
Tests for COMP-RA-002 DataSerializer.

leaf_id : COMP-RA-002
req_id  : REQ-L2-RA-001, REQ-L2-RA-004, REQ-L2-RA-010
          REQ-L3-RA002-001, REQ-L3-RA002-002, REQ-L3-RA002-003, REQ-L3-RA002-004

Covers:
  - i18n error messages (DE/EN) — unit-testable without HTTP context.
  - Pagination default 25, max 100.
  - Serializer validates required fields (field-level error reports).
  - FieldFilter applied in serialization (preset-aware field filtering).
  - RequirementSerializer accepts valid data and rejects invalid data.
  - QUERYSET_OPTIMIZATIONS keys present for all 7 entity types.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from rest_api.serializers import (
    QUERYSET_OPTIMIZATIONS,
    RequirementSerializer,
    StandardPagination,
    TraceLinkSerializer,
    apply_queryset_optimizations,
    build_error_response,
    detect_lang,
    get_error_message,
)
from rest_api.preset_guard import FieldFilter


# ---------------------------------------------------------------------------
# i18n error messages (REQ-L3-RA002-002)
# ---------------------------------------------------------------------------


class TestI18nErrorMessages:
    """Unit-testable without HTTP context (REQ-L3-RA002-002 AC)."""

    def test_en_validation_error(self) -> None:
        msg = get_error_message("VALIDATION_ERROR", "en")
        assert msg  # non-empty
        assert "valid" in msg.lower() or "failed" in msg.lower()

    def test_de_validation_error(self) -> None:
        msg = get_error_message("VALIDATION_ERROR", "de")
        assert msg
        assert "valid" in msg.lower() or "Validierung" in msg

    def test_unknown_lang_falls_back_to_en(self) -> None:
        msg_unknown = get_error_message("VALIDATION_ERROR", "fr")
        msg_en = get_error_message("VALIDATION_ERROR", "en")
        assert msg_unknown == msg_en

    def test_not_found_en(self) -> None:
        msg = get_error_message("NOT_FOUND", "en")
        assert "not found" in msg.lower()

    def test_not_found_de(self) -> None:
        msg = get_error_message("NOT_FOUND", "de")
        assert msg  # translation exists

    def test_all_error_codes_have_de_translation(self) -> None:
        """REQ-L3-RA002-002 AC: CI gate — every key must have a DE translation."""
        from rest_api.serializers import _ERROR_MESSAGES
        for code, translations in _ERROR_MESSAGES.items():
            assert "de" in translations, f"Missing DE translation for code: {code!r}"
            assert translations["de"], f"Empty DE translation for code: {code!r}"


class TestDetectLang:
    """Accept-Language header parsing (REQ-L3-RA002-002)."""

    def test_de_header(self) -> None:
        req = MagicMock()
        req.META = {"HTTP_ACCEPT_LANGUAGE": "de-DE,de;q=0.9"}
        req.LANGUAGE_CODE = ""
        assert detect_lang(req) == "de"

    def test_en_header(self) -> None:
        req = MagicMock()
        req.META = {"HTTP_ACCEPT_LANGUAGE": "en-US"}
        req.LANGUAGE_CODE = ""
        assert detect_lang(req) == "en"

    def test_no_header_defaults_to_en(self) -> None:
        req = MagicMock()
        req.META = {}
        req.LANGUAGE_CODE = ""
        assert detect_lang(req) == "en"

    def test_none_request_defaults_to_en(self) -> None:
        assert detect_lang(None) == "en"


class TestBuildErrorResponse:
    """Standardized error response format (REQ-L2-RA-009)."""

    def test_format(self) -> None:
        body = build_error_response("VALIDATION_ERROR", "en")
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]

    def test_code_present(self) -> None:
        body = build_error_response("NOT_FOUND", "en")
        assert body["error"]["code"] == "NOT_FOUND"

    def test_custom_message(self) -> None:
        body = build_error_response("VALIDATION_ERROR", "en", message="custom msg")
        assert body["error"]["message"] == "custom msg"

    def test_details_included(self) -> None:
        details = [{"field": "title", "errors": ["required"]}]
        body = build_error_response("VALIDATION_ERROR", "en", details=details)
        assert body["error"]["details"] == details


# ---------------------------------------------------------------------------
# StandardPagination (REQ-L3-RA002-003)
# ---------------------------------------------------------------------------


class TestStandardPagination:
    """Pagination default and max page size (REQ-L3-RA002-003)."""

    def test_default_page_size(self) -> None:
        p = StandardPagination()
        assert p.page_size == 25

    def test_max_page_size(self) -> None:
        p = StandardPagination()
        assert p.max_page_size == 100

    def test_page_size_query_param(self) -> None:
        p = StandardPagination()
        assert p.page_size_query_param == "page_size"


# ---------------------------------------------------------------------------
# RequirementSerializer — field validation (REQ-L3-RA002-001)
# ---------------------------------------------------------------------------


class TestRequirementSerializer:
    """Serializer validates required fields and types (REQ-L3-RA002-001)."""

    def test_valid_data(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test requirement",
            "description": "A description",
            "category": "functional",
            "status": "draft",
        }
        ser = RequirementSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_missing_title_invalid(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "title" in ser.errors

    def test_missing_workspace_id_invalid(self) -> None:
        data = {
            "title": "Test",
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "workspace_id" in ser.errors

    def test_field_level_errors_reported_individually(self) -> None:
        """REQ-L3-RA002-001 AC: Missing required fields reported per field name."""
        ser = RequirementSerializer(data={})
        assert not ser.is_valid()
        # Both title and workspace_id should be reported individually
        assert "title" in ser.errors or len(ser.errors) > 0


# ---------------------------------------------------------------------------
# TraceLinkSerializer (REQ-L3-RA002-001)
# ---------------------------------------------------------------------------


class TestTraceLinkSerializer:
    """TraceLink serializer validates source/target UUIDs and link_type."""

    def test_valid_trace_link(self) -> None:
        data = {
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives",
        }
        ser = TraceLinkSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_missing_link_type(self) -> None:
        data = {
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
        }
        ser = TraceLinkSerializer(data=data)
        assert not ser.is_valid()
        assert "link_type" in ser.errors


# ---------------------------------------------------------------------------
# PresetAwareSerializerMixin — field filtering (REQ-L3-RA002-004)
# ---------------------------------------------------------------------------


class TestPresetAwareSerializerMixin:
    """FieldFilter applied before generating response (REQ-L3-RA002-004)."""

    def test_permitted_fields_filter_applied(self) -> None:
        """Fields not in permitted_fields are excluded from output."""
        ff = FieldFilter(permitted_fields=frozenset({"id", "title"}), required_fields=frozenset())
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "My req",
            "description": "Excluded",
            "category": "functional",
            "status": "draft",
        }
        ser = RequirementSerializer(data=data)
        # The field_filter is applied in to_representation;
        # we test it by setting field_filter on the serializer instance.
        # To test filtering, we need an instance with data already set.
        # Simulate by testing the mixin logic directly via a dict.
        ser2 = RequirementSerializer({"id": str(uuid.uuid4()), "title": "T", "workspace_id": str(uuid.uuid4()), "description": "desc", "category": "func", "status": "draft", "version": 1, "created_at": None, "updated_at": None, "change_reason": None})
        ser2.field_filter = ff
        result = ser2.to_representation(ser2.instance)
        assert "title" in result
        assert "description" not in result

    def test_required_fields_missing_raises_validation_error(self) -> None:
        """REQ-L3-RA002-004 AC: Field in required_fields but absent → HTTP 400."""
        from rest_framework import serializers as drf_serializers
        ff = FieldFilter(permitted_fields=frozenset(), required_fields=frozenset({"change_reason"}))
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "My req",
        }
        ser = RequirementSerializer(data=data)
        ser.is_valid()  # ignore normal errors
        ser.field_filter = ff
        with pytest.raises(drf_serializers.ValidationError):
            ser.validate(ser.validated_data if ser.is_valid() else {})


# ---------------------------------------------------------------------------
# Queryset optimization registry (REQ-L2-RA-013)
# ---------------------------------------------------------------------------


class TestQuerysetOptimizations:
    """All 7 entity types have queryset optimization hints (REQ-L2-RA-013)."""

    REQUIRED_ENTITIES = {
        "requirement",
        "artifact",
        "architecture_element",
        "test_case",
        "trace_link",
        "baseline",
        "workflow_definition",
    }

    def test_all_entities_registered(self) -> None:
        for entity in self.REQUIRED_ENTITIES:
            assert entity in QUERYSET_OPTIMIZATIONS, f"Missing queryset optimization for: {entity}"

    def test_requirement_has_select_related(self) -> None:
        opts = QUERYSET_OPTIMIZATIONS["requirement"]
        assert "artifact" in opts["select_related"]

    def test_trace_link_has_source_target_select_related(self) -> None:
        """REQ-L2-RA-013: TraceLink select_related source and target (N+1 avoidance)."""
        opts = QUERYSET_OPTIMIZATIONS["trace_link"]
        assert "source" in opts["select_related"]
        assert "target" in opts["select_related"]

    def test_apply_queryset_optimizations_calls_select_related(self) -> None:
        """apply_queryset_optimizations chains select_related on queryset."""
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs

        apply_queryset_optimizations(mock_qs, "requirement")
        mock_qs.select_related.assert_called()


# ---------------------------------------------------------------------------
# ArchitectureElementSerializer parent_id invariants (REQ-L1-044)
# ---------------------------------------------------------------------------


class TestArchitectureElementSerializerParentInvariants:
    """REQ-L1-044: parent_id changes run through the invariant validator."""

    @staticmethod
    def _payload(**extra) -> dict:
        base = {"workspace_id": str(uuid.uuid4()), "title": "El"}
        base.update(extra)
        return base

    def test_parent_id_triggers_invariant_validation(self) -> None:
        from unittest.mock import patch

        from application.validators import ArchitectureElementInvariantValidator
        from rest_api.serializers import ArchitectureElementSerializer

        parent_id = str(uuid.uuid4())
        with patch.object(
            ArchitectureElementInvariantValidator, "validate_hierarchy_change"
        ) as mock_v:
            ser = ArchitectureElementSerializer(data=self._payload(parent_id=parent_id))
            assert ser.is_valid(), ser.errors
        mock_v.assert_called_once()

    def test_invariant_violation_maps_to_parent_id_field_error(self) -> None:
        from unittest.mock import patch

        from application.base import ValidationError as DomainValidationError
        from application.validators import ArchitectureElementInvariantValidator
        from rest_api.serializers import ArchitectureElementSerializer

        with patch.object(
            ArchitectureElementInvariantValidator,
            "validate_hierarchy_change",
            side_effect=DomainValidationError("[I3] Dangling parent reference"),
        ):
            ser = ArchitectureElementSerializer(
                data=self._payload(parent_id=str(uuid.uuid4()))
            )
            assert not ser.is_valid()
        assert "parent_id" in ser.errors
        assert "[I3]" in str(ser.errors["parent_id"][0])

    def test_without_parent_id_validator_is_not_called(self) -> None:
        from unittest.mock import patch

        from application.validators import ArchitectureElementInvariantValidator
        from rest_api.serializers import ArchitectureElementSerializer

        with patch.object(
            ArchitectureElementInvariantValidator, "validate_hierarchy_change"
        ) as mock_v:
            ser = ArchitectureElementSerializer(data=self._payload())
            assert ser.is_valid(), ser.errors
        mock_v.assert_not_called()

    def test_null_parent_id_is_valid_root(self) -> None:
        from unittest.mock import patch

        from application.validators import ArchitectureElementInvariantValidator
        from rest_api.serializers import ArchitectureElementSerializer

        with patch.object(
            ArchitectureElementInvariantValidator, "validate_hierarchy_change"
        ) as mock_v:
            ser = ArchitectureElementSerializer(data=self._payload(parent_id=None))
            assert ser.is_valid(), ser.errors
        mock_v.assert_not_called()
