"""
COMP-RA-002 DataSerializer — JSON <-> DTO conversion + validation + pagination.

leaf_id : COMP-RA-002
req_id  : REQ-L2-RA-001 (CRUD serialization), REQ-L2-RA-003 (performance),
          REQ-L2-RA-004 (i18n errors), REQ-L2-RA-008 (preset field filter),
          REQ-L2-RA-009 (error format), REQ-L2-RA-010 (pagination/filter/sort),
          REQ-L2-RA-012 (no business logic), REQ-L2-RA-013 (N+1 avoidance)
          REQ-L3-RA002-001 through REQ-L3-RA002-004

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-002_DataSerializer/L3_COMP-RA-002_DataSerializer_Architecture.md

Interfaces:
  IF-RA-INT-003  COMP-RA-001 <-> COMP-RA-002  (SerializeRequest / ValidatedDTO)
  IF-RA-INT-004  COMP-RA-004 -> COMP-RA-002   (FieldFilter)
  IF-RA-INT-006  COMP-RA-005 -> COMP-RA-002   (SerializerSchemas)

Design:
  - DRF ModelSerializers for all 7 domain entities.
  - Preset-aware field filtering via FieldFilter (set by PresetGuard).
  - i18n error messages via Accept-Language header (DE/EN).
  - Pagination: offset-based, default 25, max 100.
  - Queryset optimization: select_related / prefetch_related defined here,
    applied in ViewSets via get_queryset() (REQ-L2-RA-013).
  - No business logic in serializers — pure translation layer.
"""
from __future__ import annotations

from typing import Any

from django.utils import translation
from rest_framework import pagination, serializers
from rest_framework.request import Request

from rest_api.preset_guard import FieldFilter
from persistence.models import ElementType

# ---------------------------------------------------------------------------
# i18n error translation (REQ-L2-RA-004, REQ-L3-RA002-002)
# ---------------------------------------------------------------------------

# Bilingual error message registry. Every key MUST have both DE and EN entries.
# Missing a DE entry for a new key is treated as a build error (per CI rule).
_ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "VALIDATION_ERROR": {
        "en": "Validation failed.",
        "de": "Validierung fehlgeschlagen.",
    },
    "REQUIRED_FIELD": {
        "en": "This field is required.",
        "de": "Dieses Feld ist erforderlich.",
    },
    "NOT_FOUND": {
        "en": "Resource not found.",
        "de": "Ressource nicht gefunden.",
    },
    "PERMISSION_DENIED": {
        "en": "You do not have permission to perform this action.",
        "de": "Sie haben keine Berechtigung, diese Aktion durchzuführen.",
    },
    "AUTHENTICATION_REQUIRED": {
        "en": "Authentication credentials were not provided.",
        "de": "Es wurden keine Authentifizierungsdaten angegeben.",
    },
    "CONFLICT": {
        "en": "A conflict occurred with existing data.",
        "de": "Es ist ein Konflikt mit vorhandenen Daten aufgetreten.",
    },
    "PRESET_FIELD_REQUIRED": {
        "en": "This field is required by the active workspace preset.",
        "de": "Dieses Feld ist durch das aktive Workspace-Preset erforderlich.",
    },
    "PRESET_FIELD_FORBIDDEN": {
        "en": "This field is not permitted by the active workspace preset.",
        "de": "Dieses Feld ist durch das aktive Workspace-Preset nicht erlaubt.",
    },
    "INTERNAL_SERVER_ERROR": {
        "en": "An internal server error occurred.",
        "de": "Ein interner Serverfehler ist aufgetreten.",
    },
    "SERVICE_UNAVAILABLE": {
        "en": "A required service is temporarily unavailable.",
        "de": "Ein erforderlicher Dienst ist vorübergehend nicht verfügbar.",
    },
}


def get_error_message(code: str, lang: str = "en") -> str:
    """Return a localized error message for the given error code.

    Falls back to English if the language or code is not found.
    Unit-testable without HTTP context (REQ-L3-RA002-002 AC).

    Args:
        code: Error code key (must exist in _ERROR_MESSAGES).
        lang: Two-letter language code ("de" or "en").

    Returns:
        Localized error message string.
    """
    lang_lower = (lang or "en").lower()[:2]
    messages = _ERROR_MESSAGES.get(code, {})
    return messages.get(lang_lower) or messages.get("en", code)


def detect_lang(request: Any) -> str:
    """Extract the preferred language from Accept-Language header.

    Returns "de" or "en". Falls back to "en" (REQ-L3-RA002-002).
    """
    if request is None:
        return "en"
    accept = (
        getattr(request, "META", {}).get("HTTP_ACCEPT_LANGUAGE", "")
        or getattr(request, "LANGUAGE_CODE", "")
    )
    if accept and accept.lower().startswith("de"):
        return "de"
    return "en"


def build_error_response(
    code: str,
    lang: str = "en",
    details: list[dict[str, Any]] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Construct the standardized error response body (REQ-L2-RA-009).

    Format: {"error": {"code": "...", "message": "...", "details": [...]}}
    """
    return {
        "error": {
            "code": code,
            "message": message or get_error_message(code, lang),
            "details": details or [],
        }
    }


# ---------------------------------------------------------------------------
# Pagination (REQ-L2-RA-010, REQ-L3-RA002-003)
# ---------------------------------------------------------------------------


class StandardPagination(pagination.PageNumberPagination):
    """Offset-based pagination: default 25, max 100 (REQ-L3-RA002-003).

    Response format: {"count", "next", "previous", "results"}
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"


# ---------------------------------------------------------------------------
# Preset-aware Serializer mixin (IF-RA-INT-004)
# REQ-L3-RA002-004
# ---------------------------------------------------------------------------


class PresetAwareSerializerMixin:
    """Mixin that applies FieldFilter from PresetGuard to serializer fields.

    Set ``field_filter`` on the serializer instance before calling
    to_representation() to activate filtering.

    REQ-L3-RA002-004: FieldFilter is applied before generating response (not after).
    """

    field_filter: FieldFilter | None = None

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)  # type: ignore[misc]
        ff = self.field_filter
        if ff is not None and ff.permitted_fields:
            # Drop fields not in permitted set
            return {k: v for k, v in data.items() if k in ff.permitted_fields}
        return data

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)  # type: ignore[misc]
        ff = self.field_filter
        if ff is not None and ff.required_fields:
            missing = [f for f in ff.required_fields if f not in attrs]
            if missing:
                raise serializers.ValidationError(
                    {
                        f: get_error_message("PRESET_FIELD_REQUIRED")
                        for f in missing
                    }
                )
        return attrs


# ---------------------------------------------------------------------------
# Entity Serializers — COMP-RA-002 (REQ-L3-RA002-001)
# All serializers use statically typed fields; no raw dict passed downstream.
# ---------------------------------------------------------------------------


class ArtifactSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Artifact entity (REQ-L2-RA-001).

    Uses Serializer (not ModelSerializer) because Artifact is a pure
    adapter DTO — no direct ORM binding at the REST layer.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    artifact_type = serializers.CharField(max_length=64)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="modified_at")


class RequirementSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Requirement entity (REQ-L2-RA-001).

    select_related hint: artifact, artifact__workspace (for queryset optimization).
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    category = serializers.CharField(max_length=64, allow_blank=True, default="")
    status = serializers.CharField(max_length=64, default="draft")
    version = serializers.IntegerField(read_only=True)
    change_reason = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ArchitectureElementSerializer(
    PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for ArchitectureElement entity (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    element_type = serializers.ChoiceField(
        choices=ElementType.choices, allow_blank=True, default=ElementType.COMPONENT
    )
    expected_version = serializers.IntegerField(
        required=False, write_only=True
    )
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TestCaseSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TestCase entity (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    status = serializers.CharField(max_length=64, default="draft")
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TraceLinkSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TraceLink entity (REQ-L2-RA-001).

    select_related hint: source, target (for N+1 avoidance, REQ-L2-RA-013).
    """

    id = serializers.UUIDField(read_only=True)
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    link_type = serializers.CharField(max_length=64)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class BaselineSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Baseline entity (REQ-L2-RA-001).

    ``name`` is optional on create; the view generates a timestamp-based
    default when the UI does not supply one.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    name = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    scope = serializers.CharField(max_length=32)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    artifact_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class WorkflowDefinitionSerializer(
    PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for WorkflowDefinition entity (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    artifact_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class WorkspaceSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Workspace entity (REQ-L1-017, REQ-L1-042).

    ``terminology_profile`` is sourced from the optional
    ``WorkspacePresetConfig`` one-to-one companion; ``language`` is reserved
    for a future per-workspace setting and currently defaults to ``"en"``.

    Lifecycle fields (REQ-L1-042):
      ``is_active``, ``closed_at``, ``closed_by`` — soft-delete / close metadata.
    """

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=255)
    preset = serializers.JSONField(required=False, default=dict)
    terminology_profile = serializers.CharField(
        required=False, default="se_mode", max_length=32
    )
    language = serializers.CharField(required=False, default="en", max_length=8)
    is_active = serializers.BooleanField(read_only=True, default=True)
    closed_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)
    closed_by = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class AdrSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for ADR entity (REQ-L1-029, COMP-AS-013)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    context = serializers.CharField(allow_blank=True, default="")
    consequences = serializers.CharField(allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        default="Draft",
    )
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class RiskSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Risk entity (REQ-L1-029, COMP-AS-014)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    probability = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    impact = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    risk_score = serializers.IntegerField(read_only=True)
    severity = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    category = serializers.ChoiceField(
        choices=["technical", "operational", "organizational", "business"],
        default="technical",
    )
    owner = serializers.CharField(allow_blank=True, default="")
    mitigation_strategy = serializers.CharField(allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["Identified", "Monitored", "Mitigated", "Accepted", "Closed"],
        default="Identified",
    )
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TestRunSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TestRun entity (REQ-L2-AS-030)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    name = serializers.CharField(max_length=255)
    status = serializers.CharField(read_only=True)
    ci_job_id = serializers.CharField(allow_blank=True, default="")
    started_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True)
    result_summary = serializers.JSONField(read_only=True, required=False)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TestRunResultSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TestRunResult entity (REQ-L2-AS-030)."""

    id = serializers.UUIDField(read_only=True)
    test_run_id = serializers.UUIDField(read_only=True)
    test_case_id = serializers.UUIDField(required=True)
    test_case_title = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(
        choices=["passed", "failed", "blocked", "not_run"],
        default="not_run",
    )
    executed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(allow_null=True, required=False)
    message = serializers.CharField(allow_blank=True, default="")
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class TestRunResultBulkSerializer(serializers.Serializer):
    """Serializer for bulk result ingestion (REQ-L2-AS-031)."""

    results = TestRunResultSerializer(many=True)


class IssueSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Issue entity (REQ-L1-029, COMP-AS-015)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    severity = serializers.ChoiceField(
        choices=["critical", "high", "medium", "low"], default="medium"
    )
    category = serializers.ChoiceField(
        choices=["defect", "improvement", "documentation", "question"],
        default="defect",
    )
    status = serializers.ChoiceField(
        choices=["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
        default="Open",
    )
    tags = serializers.JSONField(required=False, default=list)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


# ---------------------------------------------------------------------------
# Queryset optimization helpers (REQ-L2-RA-013, COMP-RA-006 integration point)
# ---------------------------------------------------------------------------

QUERYSET_OPTIMIZATIONS: dict[str, dict[str, list[str]]] = {
    "requirement": {
        "select_related": ["artifact", "artifact__workspace"],
        "prefetch_related": [],
    },
    "artifact": {
        "select_related": ["parent", "workspace"],
        "prefetch_related": [],
    },
    "architecture_element": {
        "select_related": ["artifact", "artifact__workspace"],
        "prefetch_related": [],
    },
    "test_case": {
        "select_related": ["artifact", "artifact__workspace"],
        "prefetch_related": [],
    },
    "trace_link": {
        "select_related": ["source", "target"],
        "prefetch_related": [],
    },
    "baseline": {
        "select_related": ["artifact"],
        "prefetch_related": [],
    },
    "workflow_definition": {
        "select_related": ["artifact"],
        "prefetch_related": [],
    },
}


def apply_queryset_optimizations(queryset: Any, entity_type: str) -> Any:
    """Apply select_related / prefetch_related to avoid N+1 queries.

    REQ-L2-RA-013: Must be called in ViewSet.get_queryset().

    Args:
        queryset: Django QuerySet.
        entity_type: Key in QUERYSET_OPTIMIZATIONS.

    Returns:
        Optimized queryset.
    """
    opts = QUERYSET_OPTIMIZATIONS.get(entity_type, {})
    for rel in opts.get("select_related", []):
        queryset = queryset.select_related(rel)
    for rel in opts.get("prefetch_related", []):
        queryset = queryset.prefetch_related(rel)
    return queryset


__all__ = [
    "ArtifactSerializer",
    "RequirementSerializer",
    "ArchitectureElementSerializer",
    "TestCaseSerializer",
    "TraceLinkSerializer",
    "BaselineSerializer",
    "WorkflowDefinitionSerializer",
    "WorkspaceSerializer",
    "AdrSerializer",
    "RiskSerializer",
    "IssueSerializer",
    "TestRunSerializer",
    "TestRunResultSerializer",
    "TestRunResultBulkSerializer",
    "StandardPagination",
    "PresetAwareSerializerMixin",
    "build_error_response",
    "get_error_message",
    "detect_lang",
    "apply_queryset_optimizations",
    "QUERYSET_OPTIMIZATIONS",
]
