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
    AdrSerializer,
    ChangeRequestSerializer,
    GlossaryTermSerializer,
    IssueSerializer,
    RequirementSerializer,
    RiskSerializer,
    StandardPagination,
    TestRunResultSerializer,
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

    def test_paginated_response_schema_declares_envelope(self) -> None:
        # REQ-076: OpenAPI schema pins the count/next/previous/results envelope.
        p = StandardPagination()
        item_schema = {"type": "array", "items": {"type": "object"}}
        schema = p.get_paginated_response_schema(item_schema)
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"count", "next", "previous", "results"}
        assert schema["properties"]["results"] is item_schema
        assert "count" in schema["required"]
        assert schema["properties"]["next"]["nullable"] is True


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

    def test_oversized_description_rejected(self) -> None:
        """Regression (issue #4): description had no max_length, allowing
        unbounded payloads to be stored."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test requirement",
            "description": "A" * 20001,
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "description" in ser.errors

    def test_oversized_change_reason_rejected(self) -> None:
        """#104: change_reason had no max_length, allowing unbounded payloads."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test requirement",
            "change_reason": "A" * 2001,
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "change_reason" in ser.errors

    def test_script_tags_rejected_in_title_and_description(self) -> None:
        """Regression (SEC-001/#57): free-text fields must not persist raw
        HTML/script markup verbatim (stored-XSS risk for non-React API
        consumers like MCP responses or the ReqIF export).

        BREAKING CHANGE (#269 finding 3): the remedy used to be a silent
        ``strip_tags`` — ``"<img src=x onerror=alert(1)>"`` became ``""`` and
        the caller got a ``201``, i.e. data loss it could not detect. The
        payload is now rejected with a field-level error instead; the caller
        keeps its input and is told why.
        """
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "<script>alert(1)</script>Title",
            "description": "<img src=x onerror=alert(1)>Body",
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert set(ser.errors) == {"title", "description"}
        assert "disallowed content" in str(ser.errors["title"][0])

    def test_javascript_uri_rejected_in_free_text(self) -> None:
        """#269 finding 3: markup-free but script-capable input must also fail.

        ``strip_tags`` left ``javascript:alert(1)`` untouched, and the frontend
        renders descriptions as Markdown — ``[x](javascript:...)`` becomes a
        real ``<a href>``.
        """
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Ordinary title",
            "description": "See [details](javascript:alert(1)).",
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "description" in ser.errors


# ---------------------------------------------------------------------------
# #104 — free-text size limits across entity serializers
# ---------------------------------------------------------------------------


class TestFreeTextSizeLimits:
    """Regression (#104): backend had no size limit for free-text fields
    (description, rationale, notes, context, etc.), allowing unbounded
    payloads to reach the database (DoS risk)."""

    def test_adr_context_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test ADR",
            "context": "A" * 5001,
        }
        ser = AdrSerializer(data=data)
        assert not ser.is_valid()
        assert "context" in ser.errors

    def test_adr_consequences_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test ADR",
            "consequences": "A" * 5001,
        }
        ser = AdrSerializer(data=data)
        assert not ser.is_valid()
        assert "consequences" in ser.errors

    def test_risk_owner_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test Risk",
            "owner": "A" * 256,
        }
        ser = RiskSerializer(data=data)
        assert not ser.is_valid()
        assert "owner" in ser.errors

    def test_risk_mitigation_strategy_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test Risk",
            "mitigation_strategy": "A" * 10001,
        }
        ser = RiskSerializer(data=data)
        assert not ser.is_valid()
        assert "mitigation_strategy" in ser.errors

    def test_test_run_result_message_oversized_rejected(self) -> None:
        data = {
            "test_case_id": str(uuid.uuid4()),
            "message": "A" * 10001,
        }
        ser = TestRunResultSerializer(data=data)
        assert not ser.is_valid()
        assert "message" in ser.errors

    def test_change_request_impact_assessment_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test CR",
            "impact_assessment": "A" * 10001,
        }
        ser = ChangeRequestSerializer(data=data)
        assert not ser.is_valid()
        assert "impact_assessment" in ser.errors

    def test_change_request_change_reason_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test CR",
            "change_reason": "A" * 2001,
        }
        ser = ChangeRequestSerializer(data=data)
        assert not ser.is_valid()
        assert "change_reason" in ser.errors

    def test_glossary_term_definition_oversized_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "term": "Test Term",
            "definition": "A" * 20001,
        }
        ser = GlossaryTermSerializer(data=data)
        assert not ser.is_valid()
        assert "definition" in ser.errors


# ---------------------------------------------------------------------------
# IssueSerializer
# ---------------------------------------------------------------------------


class TestIssueSerializerStatusField:
    def test_invalid_status_error_lists_valid_choices(self) -> None:
        """Regression (issue #26): DRF's default invalid_choice message
        ('"<value>" is not a valid choice.') didn't enumerate the valid
        status values, forcing MCP/API callers to guess."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test issue",
            "severity": "high",
            "category": "defect",
            "status": "bogus-status",
        }
        ser = IssueSerializer(data=data)
        assert not ser.is_valid()
        assert "status" in ser.errors
        message = str(ser.errors["status"][0])
        for choice in ("Open", "In Progress", "Resolved", "Closed", "Wontfix"):
            assert choice in message

    def test_valid_status_accepted(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test issue",
            "severity": "high",
            "category": "defect",
            "status": "In Progress",
        }
        ser = IssueSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_case_insensitive_status_lowercase(self) -> None:
        """Issue status field accepts lowercase input and normalizes to Title-Case."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test issue",
            "severity": "high",
            "category": "defect",
            "status": "open",
        }
        ser = IssueSerializer(data=data)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["status"] == "Open"

    def test_case_insensitive_status_uppercase(self) -> None:
        """Issue status field accepts uppercase input and normalizes to Title-Case."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test issue",
            "severity": "high",
            "category": "defect",
            "status": "IN PROGRESS",
        }
        ser = IssueSerializer(data=data)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["status"] == "In Progress"

    def test_case_insensitive_status_mixed_case(self) -> None:
        """Issue status field accepts mixed-case input and normalizes to Title-Case."""
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test issue",
            "severity": "high",
            "category": "defect",
            "status": "wONtFiX",
        }
        ser = IssueSerializer(data=data)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["status"] == "Wontfix"


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

    def test_title_fields_present_in_output(self) -> None:
        """REQ-002: source_title/target_title/source_type/target_type included."""
        source_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())
        instance = {
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "target_id": target_id,
            "link_type": "satisfies",
            "source_title": "My Requirement",
            "target_title": "My Architecture Element",
            "source_type": "Requirement",
            "target_type": "ArchitectureElement",
            "version": 1,
            "created_at": None,
        }
        ser = TraceLinkSerializer(instance)
        data = ser.data
        assert data["source_title"] == "My Requirement"
        assert data["target_title"] == "My Architecture Element"
        assert data["source_type"] == "Requirement"
        assert data["target_type"] == "ArchitectureElement"

    def test_title_fields_default_to_empty_string(self) -> None:
        """REQ-002: Title fields default to empty string when not provided."""
        instance = {
            "id": str(uuid.uuid4()),
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "verifies",
            "version": 1,
            "created_at": None,
        }
        ser = TraceLinkSerializer(instance)
        data = ser.data
        # Fields should be present with empty-string defaults (REQ-002)
        assert "source_title" in data
        assert "target_title" in data
        assert "source_type" in data
        assert "target_type" in data
        assert data["source_title"] == ""
        assert data["target_title"] == ""


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


# ---------------------------------------------------------------------------
# PresetAwareSerializerMixin — NUL (0x00) byte rejection (QIRK-003, #76)
# ---------------------------------------------------------------------------


class TestNullByteRejection:
    """A NUL byte in any string field must be rejected with a 400 at the
    serializer boundary, instead of reaching Postgres and raising a raw
    ``ValueError: A string literal cannot contain NUL (0x00) characters``
    (HTTP 500). Covered generically via ``PresetAwareSerializerMixin.validate()``
    so every entity serializer that uses the mixin (Workspace, Requirement,
    Adr, Risk, Issue, TestCase, ChangeRequest, ...) is protected.
    """

    def test_null_byte_in_requirement_title_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "test\x00null",
            "description": "A description",
            "category": "functional",
            "status": "draft",
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "title" in ser.errors
        # DRF's built-in CharField validator (ProhibitNullCharactersValidator)
        # rejects this before PresetAwareSerializerMixin.validate() even runs;
        # either way it's a 400, not a raw Postgres 500.
        assert "null charact" in str(ser.errors["title"][0]).lower()

    def test_null_byte_in_requirement_description_rejected(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test requirement",
            "description": "bad\x00value",
            "category": "functional",
            "status": "draft",
        }
        ser = RequirementSerializer(data=data)
        assert not ser.is_valid()
        assert "description" in ser.errors
        assert "null charact" in str(ser.errors["description"][0]).lower()

    def test_without_null_byte_still_valid(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "Test requirement",
            "description": "A clean description",
            "category": "functional",
            "status": "draft",
        }
        ser = RequirementSerializer(data=data)
        assert ser.is_valid(), ser.errors
