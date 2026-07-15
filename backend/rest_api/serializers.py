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
    """Offset-based pagination: default 25, max 100 (REQ-L3-RA002-003, REQ-076).

    Response envelope::

        {
            "count":    <int>,     # total number of matching items
            "next":     <url|null>,  # absolute URL of the next page (null on last)
            "previous": <url|null>,  # absolute URL of the previous page (null on first)
            "results":  [ ... ]    # page slice of serialized items
        }

    Query parameters (documented in OpenAPI via
    ``get_schema_operation_parameters`` / ``get_paginated_response_schema``):

    - ``page``      — 1-based page number (default 1).
    - ``page_size`` — items per page (default 25, capped at ``max_page_size``).
    """

    #: Default number of items returned per page when ``page_size`` is omitted.
    page_size = 25
    #: Query parameter clients use to override the page size (bounded by max_page_size).
    page_size_query_param = "page_size"
    #: Hard upper bound for client-requested page sizes — protects against abuse.
    max_page_size = 100
    #: Query parameter selecting the 1-based page number.
    page_query_param = "page"

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Declare the exact pagination envelope for drf-spectacular (REQ-076).

        Overrides DRF's default so the generated OpenAPI schema pins the
        ``count``/``next``/``previous``/``results`` contract instead of leaving
        it implicit. *schema* is the item schema of a single ``results`` entry.
        """
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {
                    "type": "integer",
                    "example": 123,
                    "description": "Total number of items across all pages.",
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": (
                        "https://api.example.org/api/v1/requirements/?page=3&page_size=25"
                    ),
                    "description": "Absolute URL of the next page, or null on the last page.",
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": (
                        "https://api.example.org/api/v1/requirements/?page=1&page_size=25"
                    ),
                    "description": "Absolute URL of the previous page, or null on the first page.",
                },
                "results": schema,
            },
        }


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
# Custom fields mixin (REQ-L2-AS-037)
# ---------------------------------------------------------------------------


class CustomFieldsSerializerMixin:
    """Adds a writable ``custom_fields`` field with flat-map validation.

    REQ-L2-AS-037: custom_fields lives on the shared Artifact node but is
    exposed on every artifact-backed entity serializer so it can be read and
    written through the entity's own endpoint. Validation is delegated to
    :func:`persistence.custom_fields.validate_custom_fields` (single source of
    truth — no duplicate rules per serializer).
    """

    custom_fields = serializers.JSONField(
        required=False,
        help_text=(
            "User-defined custom attributes as a flat key-value map "
            "(REQ-L2-AS-037). Values: string, number, boolean or null."
        ),
    )

    def validate_custom_fields(self, value: Any) -> dict:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from persistence.custom_fields import validate_custom_fields

        try:
            return validate_custom_fields(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))


# ---------------------------------------------------------------------------
# Entity Serializers — COMP-RA-002 (REQ-L3-RA002-001)
# All serializers use statically typed fields; no raw dict passed downstream.
# ---------------------------------------------------------------------------


class ArtifactSerializer(
    CustomFieldsSerializerMixin, PresetAwareSerializerMixin, serializers.Serializer
):
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


class RequirementSerializer(
    CustomFieldsSerializerMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for Requirement entity (REQ-L2-RA-001, REQ-L3-RF003-005).

    REQ-L3-RF003-005: Type-dependent fields (complexity_fibonacci,
    verification_method) are included in the serializer but conditionally rendered
    in to_representation() based on the requirement type.

    REQ-L2-RF-025: Includes uid for stable identification.

    select_related hint: artifact, artifact__workspace (for queryset optimization).
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    category = serializers.CharField(max_length=64, allow_blank=True, default="")
    # REQ-143: `status` is a read-only mirror of the WorkflowEngine state. The
    # WorkflowEngine is the single source of truth; any `status` sent by a client
    # is silently ignored (not a 400) and the response always reflects the true,
    # engine-owned value. Change the lifecycle state via
    # POST /api/v1/requirements/{id}/transitions/.
    status = serializers.CharField(
        max_length=64,
        read_only=True,
        help_text=(
            "Lifecycle state, read-only mirror of the WorkflowEngine (REQ-143). "
            "Writes are ignored; transition via "
            "POST /api/v1/requirements/{id}/transitions/."
        ),
    )
    type = serializers.ChoiceField(
        choices=['SyReq', 'UseCase', 'FeatureReq'],
        default='SyReq',
        help_text="Requirement classification per REQ-L3-RF003-005",
    )
    complexity_fibonacci = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Complexity via Fibonacci scale (visible only for SyReq)",
    )
    verification_method = serializers.ChoiceField(
        choices=['Test', 'Review', 'Analysis', 'Inspection'],
        required=False,
        allow_null=True,
        help_text="Verification method (visible only for SyReq)",
    )
    uid = serializers.CharField(
        max_length=64,
        read_only=True,
        required=False,
        allow_null=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    version = serializers.IntegerField(read_only=True)
    change_reason = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Render conditional fields based on requirement type."""
        data = super().to_representation(instance)
        # AC2: complexity_fibonacci and verification_method visible only when type='SyReq'
        req_type = data.get('type')
        if req_type != 'SyReq':
            data.pop('complexity_fibonacci', None)
            data.pop('verification_method', None)
        return data


class StakeholderNeedSerializer(
    CustomFieldsSerializerMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for StakeholderNeed entity.
    
    Represents the user's problem space and needs.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True, read_only=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    category = serializers.CharField(max_length=64, allow_blank=True, default="")
    # REQ-143: read-only mirror of the WorkflowEngine state (see RequirementSerializer).
    # Writes are ignored; the response always reflects the true, engine-owned value.
    status = serializers.CharField(
        max_length=64,
        read_only=True,
        help_text=(
            "Lifecycle state, read-only mirror of the WorkflowEngine (REQ-143). "
            "Writes are ignored."
        ),
    )
    moscow_priority = serializers.ChoiceField(
        choices=['Must', 'Should', 'Could', "Won't"],
        required=False,
        allow_null=True,
        help_text="MoSCoW priority",
    )
    uid = serializers.CharField(read_only=True, allow_null=True)
    suspect = serializers.BooleanField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    change_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="modified_at")


class ArchitectureElementSerializer(
    CustomFieldsSerializerMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for ArchitectureElement entity (REQ-L2-RA-001, REQ-L3-RF004-004).

    REQ-L1-044: ``parent_id`` changes run through the rigor-gated
    hierarchy invariants (I1-I3) in validate().  On update, the view
    provides ``context={"element_id": pk}`` so the validator can resolve
    the element and its workspace.

    REQ-L1-058 AC2: level annotation via CTE manager (get_with_level())
    avoids N+1 queries. Expects pre-annotated 'level' field from queryset.

    REQ-L3-RF004-004: Includes ASIL level and Make-or-Buy decision fields.
    REQ-L2-RF-025 AC3: Includes uid for stable identification.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    # REQ-006 (D5): free-form field — no longer restricted to ElementType.choices,
    # so users can introduce new workspace-defined element types.
    element_type = serializers.CharField(
        max_length=64, allow_blank=True, default=ElementType.COMPONENT
    )
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    level = serializers.IntegerField(read_only=True)
    asil_level = serializers.ChoiceField(
        choices=['QM', 'A', 'B', 'C', 'D'],
        required=False,
        allow_null=True,
        help_text="ASIL level per REQ-L3-RF004-004",
    )
    make_or_buy = serializers.ChoiceField(
        choices=['Make', 'Buy', 'Reuse'],
        required=False,
        allow_null=True,
        help_text="Make-or-Buy decision per REQ-L3-RF004-004",
    )
    uid = serializers.CharField(
        max_length=64,
        read_only=True,
        required=False,
        allow_null=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    expected_version = serializers.IntegerField(
        required=False, write_only=True
    )
    suspect = serializers.BooleanField(required=False, default=False)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        parent_id = attrs.get("parent_id")
        if parent_id is not None:
            # Deferred imports: keep the REST layer decoupled from the
            # application layer at module load time.
            from application.base import ValidationError as DomainValidationError
            from application.validators import (
                ArchitectureElementInvariantValidator,
            )

            try:
                ArchitectureElementInvariantValidator.validate_hierarchy_change(
                    parent_id=parent_id,
                    element_id=self.context.get("element_id"),
                    workspace_id=attrs.get("workspace_id"),
                )
            except DomainValidationError as exc:
                raise serializers.ValidationError({"parent_id": str(exc)})
        return attrs


class TestCaseSerializer(
    CustomFieldsSerializerMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for TestCase entity (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(allow_blank=True, default="")
    uid = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(max_length=64, default="draft")
    suspect = serializers.BooleanField(required=False, default=False)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TraceLinkSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TraceLink entity (REQ-L2-RA-001, REQ-002).

    select_related hint: source, target (for N+1 avoidance, REQ-L2-RA-013).

    REQ-002: source_title, target_title, source_type, target_type are included
    in the response so the frontend can render human-readable labels without
    extra round-trips. These fields are optional (read-only) and default to
    empty string / null when the backing entity has no title.
    """

    id = serializers.UUIDField(read_only=True)
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    link_type = serializers.CharField(max_length=64)
    # REQ-002: human-readable labels for trace endpoints
    source_title = serializers.CharField(
        read_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="Human-readable title of the source artifact (REQ-002).",
    )
    target_title = serializers.CharField(
        read_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="Human-readable title of the target artifact (REQ-002).",
    )
    source_type = serializers.CharField(
        read_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="Artifact type of the source (e.g. Requirement, ArchitectureElement).",
    )
    target_type = serializers.CharField(
        read_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="Artifact type of the target (e.g. Requirement, ArchitectureElement).",
    )
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ImpactNodeSerializer(serializers.Serializer):
    """Serializer for a traceability impact-analysis node (REQ-L2-TE-019)."""

    artifact_id = serializers.UUIDField(read_only=True)
    artifact_type = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True, allow_blank=True)
    uid = serializers.CharField(read_only=True, allow_null=True)
    link_type = serializers.CharField(read_only=True)
    depth = serializers.IntegerField(read_only=True)
    path = serializers.ListField(
        child=serializers.UUIDField(), read_only=True
    )


class SimilarRequirementSerializer(serializers.Serializer):
    """Serializer for a similarity-search hit (REQ-L2-VS-004).

    Read-only projection of SimilarRequirementDTO: identity plus the cosine
    similarity_score (1 - cosine_distance, higher = more similar).
    """

    id = serializers.UUIDField(read_only=True)
    uid = serializers.CharField(read_only=True, allow_null=True)
    title = serializers.CharField(read_only=True, allow_blank=True)
    category = serializers.CharField(read_only=True, allow_blank=True)
    status = serializers.CharField(read_only=True)
    similarity_score = serializers.FloatField(read_only=True)


class SimilarTraceLinkSerializer(serializers.Serializer):
    """Serializer for a trace-link similarity-search hit (REQ-L2-VS-004).

    Read-only projection of SimilarTraceLinkDTO: endpoints, link_type and the
    cosine similarity_score (1 - cosine_distance, higher = more similar).
    """

    id = serializers.UUIDField(read_only=True)
    source_id = serializers.UUIDField(read_only=True)
    target_id = serializers.UUIDField(read_only=True)
    link_type = serializers.CharField(read_only=True)
    similarity_score = serializers.FloatField(read_only=True)


class TracePathSerializer(serializers.Serializer):
    """Serializer for a single traceability path (REQ-L2-TE-019)."""

    nodes = serializers.ListField(child=serializers.UUIDField(), read_only=True)
    length = serializers.IntegerField(read_only=True)


class BaselineDeltaEntrySerializer(serializers.Serializer):
    """Serializer for a single captured Baseline delta entry (REQ-L2-BL-012).

    ``state`` is the full field-level entity snapshot taken at baseline creation
    time. It is ``null`` for legacy entries created before the snapshot feature
    — the frontend degrades gracefully to the version number in that case.
    """

    item_id = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    entity_type = serializers.CharField(read_only=True)
    state = serializers.JSONField(read_only=True, allow_null=True)


class BaselineSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Baseline entity (REQ-L2-RA-001).

    ``name`` is optional on create; the view generates a timestamp-based
    default when the UI does not supply one.

    ``entries`` is only present on the detail (retrieve/create) response — the
    list endpoint returns summaries without entries (lazy loading). Each entry
    may carry a full-state ``state`` snapshot (REQ-L2-BL-012).
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
    entries = BaselineDeltaEntrySerializer(
        many=True, read_only=True, required=False
    )


class FieldChangeSerializer(serializers.Serializer):
    """One field-level change within a changed baseline item (REQ-L2-BL-012).

    ``old_value`` / ``new_value`` are arbitrary JSON scalars/structures taken
    from the captured entity state, so they are serialized as JSON.
    """

    field_name = serializers.CharField(read_only=True)
    old_value = serializers.JSONField(read_only=True, allow_null=True)
    new_value = serializers.JSONField(read_only=True, allow_null=True)


class DiffItemSerializer(serializers.Serializer):
    """A single item in a baseline diff (REQ-L2-BL-003, REQ-L2-BL-012).

    ``status`` is one of ``added`` | ``removed`` | ``changed``. ``field_changes``
    is present only for ``changed`` items that carry a full-state snapshot on
    both baselines; it is ``null`` for added/removed items and for legacy
    changed items where only the version number differs.
    """

    item_id = serializers.CharField(read_only=True)
    entity_type = serializers.CharField(read_only=True, allow_blank=True)
    status = serializers.CharField(read_only=True)
    field_changes = FieldChangeSerializer(
        many=True, read_only=True, required=False, allow_null=True
    )
    artifact_name = serializers.CharField(
        read_only=True, allow_null=True, required=False
    )


class BaselineDiffSerializer(serializers.Serializer):
    """Field-level structural diff between two baselines (REQ-L2-BL-003).

    Flattens ``DiffResult`` (added/removed/changed) into a single ``items``
    list carrying a per-item ``status`` plus a ``summary`` of the counts.
    """

    baseline_a_id = serializers.UUIDField(read_only=True)
    baseline_b_id = serializers.UUIDField(read_only=True)
    summary = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    items = DiffItemSerializer(many=True, read_only=True)


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
    ai_prompts = serializers.JSONField(required=False, default=dict)
    decomposition_link_type = serializers.CharField(
        required=False, default="parent-child", max_length=50
    )
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
    uid = serializers.CharField(read_only=True, allow_null=True)
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
    uid = serializers.CharField(read_only=True, allow_null=True)
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
    uid = serializers.CharField(read_only=True, allow_null=True)
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
    uid = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
        default="Open",
    )
    tags = serializers.JSONField(required=False, default=list)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class AttributeVisibilityConfigSerializer(serializers.Serializer):
    """Serializer for AttributeVisibilityConfig (REQ-L1-058 AC2).

    Admin configuration for field visibility per entity type and workspace.
    Allows controlling which type-dependent fields are visible in the UI
    and whether they are required in forms.

    Constraint: Unique on (tenant_id, entity_type, attribute_name).
    Index: Composite BTree on (tenant_id, entity_type) for fast bulk lookups.
    """

    id = serializers.UUIDField(read_only=True)
    tenant_id = serializers.UUIDField(required=True)
    entity_type = serializers.CharField(
        max_length=64,
        help_text="Target entity type (e.g., 'Requirement', 'ArchitectureElement')",
    )
    attribute_name = serializers.CharField(
        max_length=128,
        help_text="Field name (e.g., 'moscow_priority', 'asil_level')",
    )
    is_visible = serializers.BooleanField(
        default=True,
        help_text="Show/hide toggle for frontend",
    )
    is_required = serializers.BooleanField(
        default=False,
        help_text="Mark as required in forms",
    )
    created_by = serializers.CharField(
        source='created_by.username',
        read_only=True,
        required=False,
        help_text="Audit: username who created this config",
    )
    modified_by = serializers.CharField(
        source='modified_by.username',
        read_only=True,
        required=False,
        allow_null=True,
        help_text="Audit: username who last modified this config",
    )
    created_at = serializers.DateTimeField(read_only=True)
    modified_at = serializers.DateTimeField(read_only=True)
    version = serializers.IntegerField(
        read_only=True,
        help_text="Audit: version counter",
    )


class CustomFieldDefinitionSerializer(serializers.Serializer):
    """Serializer for CustomFieldDefinition (REQ-016).

    Workspace-wide custom field definition. ``options`` is only meaningful for
    ``field_type == "dropdown"`` and must then be a non-empty list of strings.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=128)
    field_type = serializers.ChoiceField(
        choices=["text", "number", "dropdown"],
        default="text",
    )
    is_required = serializers.BooleanField(default=False)
    options = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        default=list,
    )
    order = serializers.IntegerField(required=False, default=0)
    created_at = serializers.DateTimeField(read_only=True)
    modified_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs: dict) -> dict:
        """Enforce that dropdown fields carry at least one option.

        On partial updates ``field_type``/``options`` may be absent; the check
        only fires when a dropdown type is being set without any option.
        """
        field_type = attrs.get("field_type")
        options = attrs.get("options")
        if field_type == "dropdown" and not options:
            raise serializers.ValidationError(
                {"options": "Dropdown fields require at least one option."}
            )
        return attrs


class CustomFieldValueSerializer(serializers.Serializer):
    """Serializer for a persisted CustomFieldValue joined with its definition (REQ-016).

    Read output merges the value with its definition metadata so the frontend can
    render the input control without a second request. On write only
    ``definition_id`` and ``value`` are consumed.
    """

    id = serializers.UUIDField(read_only=True)
    definition_id = serializers.UUIDField()
    artifact_id = serializers.UUIDField(read_only=True)
    value = serializers.CharField(
        allow_blank=True, allow_null=True, required=False, default=""
    )
    # Definition metadata (read-only convenience fields).
    name = serializers.CharField(source="definition.name", read_only=True)
    field_type = serializers.CharField(
        source="definition.field_type", read_only=True
    )
    is_required = serializers.BooleanField(
        source="definition.is_required", read_only=True
    )
    options = serializers.JSONField(source="definition.options", read_only=True)
    order = serializers.IntegerField(source="definition.order", read_only=True)


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


class GlossaryTermVersionSerializer(serializers.Serializer):
    """Serializer for GlossaryTermVersion (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    term_fk_id = serializers.UUIDField(read_only=True)
    term_version = serializers.IntegerField(read_only=True)
    definition = serializers.CharField()
    synonyms = serializers.JSONField(required=False, default=list)
    abbreviation = serializers.CharField(required=False, allow_blank=True, default="")
    created_at = serializers.DateTimeField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)


class GlossaryTermSerializer(serializers.Serializer):
    """Serializer for GlossaryTerm (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    term = serializers.CharField(max_length=255)
    definition = serializers.CharField()
    synonyms = serializers.JSONField(required=False, default=list)
    abbreviation = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="modified_at")
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    modified_by_id = serializers.UUIDField(read_only=True, allow_null=True)


class UserProfileSerializer(serializers.Serializer):
    """User identity + editable profile fields (REQ-006).

    Read fields mirror the ``/auth/me/`` identity payload; ``first_name`` and
    ``last_name`` are the only writable fields (a user may edit their own name
    but not their username, email, tenant or roles). ``update`` applies the
    partial change and persists only the touched columns.
    """

    id = serializers.UUIDField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    is_active = serializers.BooleanField(read_only=True)

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Apply first_name/last_name changes to ``instance`` and persist them.

        Only fields present in ``validated_data`` are touched (PATCH semantics);
        each value is trimmed of surrounding whitespace before saving.
        """
        updated_fields: list[str] = []
        for field in ("first_name", "last_name"):
            if field in validated_data:
                setattr(instance, field, validated_data[field].strip())
                updated_fields.append(field)
        if updated_fields:
            instance.save(update_fields=updated_fields)
        return instance


__all__ = [
    "ArtifactSerializer",
    "StakeholderNeedSerializer",
    "RequirementSerializer",
    "ArchitectureElementSerializer",
    "TestCaseSerializer",
    "TraceLinkSerializer",
    "BaselineSerializer",
    "BaselineDeltaEntrySerializer",
    "FieldChangeSerializer",
    "DiffItemSerializer",
    "BaselineDiffSerializer",
    "WorkflowDefinitionSerializer",
    "WorkspaceSerializer",
    "AdrSerializer",
    "RiskSerializer",
    "IssueSerializer",
    "AttributeVisibilityConfigSerializer",
    "CustomFieldDefinitionSerializer",
    "CustomFieldValueSerializer",
    "TestRunSerializer",
    "TestRunResultSerializer",
    "TestRunResultBulkSerializer",
    "GlossaryTermSerializer",
    "GlossaryTermVersionSerializer",
    "UserProfileSerializer",
    "StandardPagination",
    "PresetAwareSerializerMixin",
    "CustomFieldsSerializerMixin",
    "build_error_response",
    "get_error_message",
    "detect_lang",
    "apply_queryset_optimizations",
    "QUERYSET_OPTIMIZATIONS",
]
