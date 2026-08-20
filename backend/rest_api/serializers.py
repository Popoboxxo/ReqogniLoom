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

from typing import Any, Optional

from django.utils import translation
from rest_framework import pagination, serializers
from rest_framework.request import Request

from rest_api.preset_guard import FieldFilter
from rest_api.sanitization import FreeTextFieldMarker, validate_free_text
from persistence.models import ElementType

# ---------------------------------------------------------------------------
# Lock-counter semantics (issue #213)
# ---------------------------------------------------------------------------

# ``AuditableModel.version`` is an optimistic-concurrency counter, not a
# content revision number. It is exposed so clients can send it back as
# ``expected_version``; it must not be rendered as "this artifact has N
# revisions". Historical values have no retrievable snapshot — real history
# comes from the ``/versions/`` and ``/history/`` endpoints and from Baselines.
LOCK_VERSION_HELP_TEXT = (
    "Optimistic-lock counter for concurrency control (send back as "
    "expected_version). NOT a content revision number: it also increments on "
    "writes that change nothing user-visible, and historical values have no "
    "retrievable snapshot. Use /versions/, /history/ or Baselines for real "
    "history."
)

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
    "SE_AUDITOR_BLOCKED": {
        "en": (
            "The SE-Auditor reported blocking findings; resolve them or supply "
            "a written override justification."
        ),
        "de": (
            "Der SE-Auditor meldet blockierende Findings; beheben Sie diese "
            "oder geben Sie eine schriftliche Ausnahmebegründung an."
        ),
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


def normalize_preset_blob(blob: Any) -> dict[str, Any]:
    """Return ``blob`` with a consistent ``tier``/``name`` pair (issue #271).

    ``Workspace.preset`` is written in three different shapes depending on the
    row's age and provenance::

        {"tier": "standard", ...}              WorkspaceService.create
        {"tier": "x", "name": "x", ...}        WorkspaceService.switch_preset_tier
        {"name": "extended"}                   legacy/seeded rows (e.g. Demo)

    Both keys are emitted, resolved by preferring ``tier`` and falling back to
    ``name``. ``tier`` is authoritative because ``switch_preset_tier`` — the
    only writer that maintains both — always sets them to the same value, so a
    disagreement can only mean ``name`` is a stale leftover.

    Normalisation happens on READ only. Rewriting the stored blobs would need a
    destructive, hard-to-reverse data migration over live tenant rows for what
    is a low-priority hygiene issue; the read path is cheap and reversible.

    Other keys (``language``, ``terminology_profile``) are preserved untouched,
    and the input is never mutated. A missing/``None``/non-dict blob yields
    ``{}`` rather than a fabricated tier — inventing one would mislabel the
    workspace, and callers already default (the frontend falls back to
    ``"standard"``).
    """
    if not isinstance(blob, dict):
        return {}
    resolved = blob.get("tier") or blob.get("name")
    if not resolved:
        return dict(blob)
    return {**blob, "tier": resolved, "name": resolved}


def extract_preset_tier(value: Any) -> Optional[str]:
    """Extract a bare tier string from a workspace-preset write payload (GH-411).

    ``Workspace.preset`` round-trips through the wire as the resolved object
    ``normalize_preset_blob`` above builds on read (``{"tier": "standard",
    "name": "standard", ...}``), but the write side
    (``WorkspaceViewSet.create``/``set_preset`` in rest_api/views.py) used to
    accept only a bare tier string and reject that very same object shape
    with a confusing "Invalid preset '{'tier': 'standard'}'" error — the
    ``str()`` of a dict, not a real validation message.

    Accepts either shape:
      - a plain tier string: ``"standard"``
      - an object carrying it under ``tier`` or ``name``: ``{"tier": "standard"}``

    Returns the extracted string (still unvalidated against the canonical
    tier list — callers pass it on to ``WorkspaceService.create_workspace``/
    ``switch_preset_tier``, which reject an unknown tier explicitly), or
    ``None`` when no tier string could be extracted at all (wrong type, or
    an object without a usable ``tier``/``name`` key) so the caller can
    return a clear 400 instead of a silently-wrong value.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        tier = value.get("tier") or value.get("name")
        return tier if isinstance(tier, str) else None
    return None


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
        # QIRK-003 (#76): Postgres text columns reject NUL (0x00) bytes with a
        # raw DB exception (HTTP 500). Reject such input at the serializer
        # boundary with a proper 400 instead of letting it reach the DB.
        null_byte_fields = [
            field
            for field, value in attrs.items()
            if isinstance(value, str) and "\x00" in value
        ]
        if null_byte_fields:
            raise serializers.ValidationError(
                {
                    field: "This field may not contain NUL (0x00) characters."
                    for field in null_byte_fields
                }
            )
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
# Free-text sanitization (SEC-03)
# ---------------------------------------------------------------------------


class SanitizedCharField(FreeTextFieldMarker, serializers.CharField):
    """CharField that *rejects* HTML markup and script-capable URI schemes.

    B006: XSS/SQLi payloads (e.g. ``<script>alert(1)</script>``) were stored
    verbatim in free-text fields like ``title``/``description`` and echoed
    back unescaped, enabling stored XSS in any consumer that renders the
    value as HTML. SQL injection is not applicable here (the ORM always
    parametrizes queries); this field only addresses the HTML/script-injection
    half of B006.

    #269 changed the remedy from *strip silently* to *reject*: stripping
    turned ``{"title": "<img src=x onerror=alert(1)>"}`` into a ``201`` with an
    empty title, i.e. silent data loss (same failure class as #263), and it
    did not cover ``javascript:`` URIs at all. See
    :mod:`rest_api.sanitization` for the rules and the trade-off.

    Applied to user-authored narrative fields (title, description, and
    similar prose fields) across the entity serializers, not to identifiers,
    UUIDs, enums or read-only fields. Declaring a new field with this class is
    also what enrols it in the ViewSet-level guard
    (``FreeTextSanitizationMixin``), which covers write paths that read
    ``request.data`` without running the serializer.
    """

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        # No field_name here: DRF already nests a field-level error under the
        # field's key, so passing one would produce {"title": {"title": [...]}}.
        return validate_free_text(value)


class SanitizedJSONField(FreeTextFieldMarker, serializers.JSONField):
    """JSONField whose *nested* strings obey the free-text rules.

    ``GlossaryTerm.synonyms`` is a list of user-authored labels. It is as
    renderable as ``definition`` (the SPA and the PDF/ReqIF exporters print
    synonyms verbatim), but the scalar guard skipped it: the value is a
    ``list``, not a ``str``, so every element went to the database raw — #269
    finding 4, one nesting level down.

    ``find_free_text_violation`` walks the structure, so this covers list
    items, dict values and dict keys alike.
    """

    def to_internal_value(self, data: Any) -> Any:
        value = super().to_internal_value(data)
        # As above: DRF nests field errors under the field's own key already.
        return validate_free_text(value)


# ---------------------------------------------------------------------------
# Custom fields mixin (REQ-L2-AS-037)
# ---------------------------------------------------------------------------


class CustomFieldsSerializerMixin(metaclass=serializers.SerializerMetaclass):
    """Adds a writable ``custom_fields`` field with flat-map validation.

    REQ-L2-AS-037: custom_fields lives on the shared Artifact node but is
    exposed on every artifact-backed entity serializer so it can be read and
    written through the entity's own endpoint. Validation is delegated to
    :func:`persistence.custom_fields.validate_custom_fields` (single source of
    truth — no duplicate rules per serializer).

    #290: the ``metaclass=`` is load-bearing, not decoration. DRF collects
    declared fields in ``SerializerMetaclass._get_declared_fields``, which walks
    ``bases`` and only reads a base's ``_declared_fields`` attribute. A *plain*
    mixin never gets that attribute, so ``custom_fields`` stayed an inert class
    attribute: ``'custom_fields' in RequirementSerializer().fields`` was
    ``False``, the key never reached ``validated_data``, and the
    ``if "custom_fields" in data:`` branches in ``rest_api.views`` were dead
    code — every custom-field edit from the UI was silently dropped while the
    request still reported 200. Applying the metaclass here registers the field
    for every serializer mixing this in, which is what revives those branches.

    #269 follow-up: making the field live also made it a *stored-XSS* surface —
    keys and values round-trip byte-identically into the SPA, the PDF/ReqIF
    exporters and MCP responses. It is therefore declared as a
    :class:`SanitizedJSONField`, which (a) rejects markup / script URIs in the
    map's keys and values and (b) enrols ``custom_fields`` in the ViewSet-level
    guard, so the ~9 handlers that read ``request.data`` without running this
    serializer still return a field-scoped 400. The same rule is enforced a
    second time in ``persistence.custom_fields.validate_custom_fields`` for the
    write paths that never see a serializer at all (MCP, ReqIF import).
    """

    custom_fields = SanitizedJSONField(
        required=False,
        help_text=(
            "User-defined custom attributes as a flat key-value map "
            "(REQ-L2-AS-037). Values: string, number, boolean or null. "
            "HTML markup and script-capable URI schemes are rejected in both "
            "keys and values."
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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    # Issue #413/#416: id of the owning Artifact. TraceLink endpoints are
    # Artifact ids, never Requirement ids, so without this field the UI cannot
    # tell whether a link endpoint *is* the requirement it is rendering — the
    # traceability list fell back to raw UUIDs and the requirement editor's
    # hierarchy panel resolved every link back to the artifact itself.
    # ``_dto_from_orm`` has always supplied the value; the serializer just
    # never declared the field, so DRF dropped it. Read-only, nullable,
    # matching StakeholderNeedSerializer / ArchitectureElementSerializer.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # #43: acceptance_criteria describes when the requirement is considered fulfilled.
    acceptance_criteria = SanitizedCharField(allow_blank=True, default="", max_length=20000)
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
        # Must mirror persistence.models.VerificationMethod (migration 0041).
        # 'Demonstration' was missing here, so a ReqIF-imported requirement
        # carrying it 400'd on its next save.
        choices=['Test', 'Review', 'Analysis', 'Inspection', 'Demonstration'],
        required=False,
        allow_null=True,
        help_text="Verification method (visible only for SyReq)",
    )
    # Issue #409: V-model hierarchy level. Model field existed since the
    # RequirementLevel migration but was never exposed by the REST/MCP
    # boundaries — a client could never set it despite it being a real,
    # queryable column used by the traceability audit rules.
    level = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=4,
        help_text=(
            "V-model hierarchy level (0=System, 1=Subsystem, 2=Component, "
            "3=Part, 4=Material). NULL until assigned explicitly."
        ),
    )
    uid = serializers.CharField(
        max_length=64,
        read_only=True,
        required=False,
        allow_null=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    # B006/#104: bounded like other short justification fields — unbounded
    # TextField-backed CharFields allow unbounded-size payloads (DoS risk).
    change_reason = SanitizedCharField(required=False, allow_blank=True, max_length=2000)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    # #45 (IEEE 29148 §5.2.4): non-blocking hint — null when the title has no
    # 'and'/'or' conjunction, otherwise the distinct conjunction words found.
    atomicity_warning = serializers.SerializerMethodField(
        help_text=(
            "Non-blocking atomicity hint (#45). Lists 'and'/'or' conjunctions "
            "found in the title, which often indicate a bundled, non-atomic "
            "requirement (IEEE 29148 §5.2.4). Null when none are found."
        )
    )

    def get_atomicity_warning(self, obj: Any) -> Optional[list[str]]:
        from application.requirement_service import detect_non_atomic_terms

        # `obj` is a plain dict from `_dto_from_orm()` on every real call site
        # (see rest_api/views.py) rather than a model/DTO instance — dicts have
        # no `.title` attribute, so `getattr` alone would silently always
        # return "".
        title = obj.get("title", "") if isinstance(obj, dict) else getattr(obj, "title", "")
        return detect_non_atomic_terms(title or "") or None

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
    # REQ-016: id of the owning Artifact. StakeholderNeedDTO has carried this
    # since REQ-001, but the serializer never declared it, so DRF dropped it
    # from every response — the UI could not address the custom-field value
    # endpoint for a need (UI concept ch. 12.11). Read-only.
    artifact_id = serializers.UUIDField(read_only=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True, read_only=True)
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    # #104: bounded — see RequirementSerializer.change_reason.
    change_reason = SanitizedCharField(
        write_only=True, required=False, allow_blank=True, max_length=2000
    )
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
    # REQ-016: id of the owning Artifact, needed by the UI to read/write
    # workspace-defined custom fields (UI concept ch. 12.11). Read-only —
    # the Artifact is created by the service, never supplied by the client.
    artifact_id = serializers.UUIDField(read_only=True)
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # REQ-006 (D5): free-form field — no longer restricted to ElementType.choices,
    # so users can introduce new workspace-defined element types.
    element_type = serializers.CharField(
        max_length=64, allow_blank=True, default=ElementType.COMPONENT
    )
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    level = serializers.IntegerField(read_only=True)
    # SysEng 2.0 §1.2: structural role derived from tree position at runtime
    # (root → system, inner → subsystem, leaf → component). Read-only and never
    # accepted as input — element_type stays a separate free-text descriptor.
    role = serializers.CharField(read_only=True)
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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    uid = serializers.CharField(read_only=True, allow_null=True)
    # REQ-165/REQ-166 (CR-08): `status` is a read-only mirror of the WorkflowEngine
    # state, same pattern as RequirementSerializer.status (REQ-143). Neither
    # create_test_case() nor update_test_case() (application/test_service.py)
    # accept a client-supplied status, so marking the field read-only here makes
    # the OpenAPI contract match the actual (already-correct) behavior instead of
    # silently advertising a writable field that PATCH has always ignored. Change
    # the lifecycle state via POST /api/v1/testcases/{id}/transitions/.
    status = serializers.CharField(
        read_only=True,
        help_text=(
            "Lifecycle state, read-only mirror of the WorkflowEngine (REQ-165). "
            "Writes are ignored; transition via "
            "POST /api/v1/testcases/{id}/transitions/."
        ),
    )
    suspect = serializers.BooleanField(required=False, default=False)
    # SysEng 2.0 N5 (test.derive_from_requirement): test steps, previously
    # persisted on the model but not exposed through the API.
    steps = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    # SysEng 2.0 N5: optional requirement to auto-link on create (write-only —
    # mirrors the MCP test.create `linked_req_id` convention, ADR-L3-MC005-01).
    linked_requirement_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text=(
            "Optional requirement UUID; creates a 'verifies' TraceLink on "
            "create."
        ),
    )
    # SysEng 2.0 N5: result of the auto-link attempt above — read-only,
    # returned on create() so the client can detect a silently failed link
    # instead of only getting a 201 with no signal (ADR-L3-MC005-01, mirrors
    # the MCP test.create `trace_link_id` convention). Null/absent on any
    # response that didn't attempt a link (e.g. retrieve/list/update), or if
    # linked_requirement_id was omitted, or if the link creation failed.
    verifies_link_id = serializers.UUIDField(
        read_only=True, allow_null=True, required=False, default=None
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject unknown keys with 400 instead of silently dropping them (#580).

        The ``TestCase`` model has no ``acceptance_criteria``/``category``
        columns (unlike Requirement/StakeholderNeed, which do), so a client
        sending them previously got a 201 with the fields simply absent from
        both the response and the persisted row — indistinguishable from a
        successful save. Same QIRK-002/#73 pattern as UserProfileSerializer:
        an unrecognised key is a client error, not silent no-op data loss.
        """
        supplied = getattr(self, "initial_data", None)
        if not isinstance(supplied, dict):
            return attrs
        errors = {
            key: ["Unknown field."] for key in supplied if key not in self.fields
        }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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


class ResolvedArtifactSerializer(serializers.Serializer):
    """Serializer for one ``artifact_id -> (entity_type, entity_id)`` resolution
    (Task 3.2a, UI-Konzept Vollrollout, REQ-L2-TE-019).

    ``entity_type``/``entity_id`` are ``None`` when ``resolved`` is False
    (unknown/foreign-tenant/deleted artifact_id) — the frontend keeps such
    entries visible-but-not-clickable rather than treating this as an error.
    """

    artifact_id = serializers.UUIDField(read_only=True)
    resolved = serializers.BooleanField(read_only=True)
    entity_type = serializers.CharField(read_only=True, allow_null=True)
    entity_id = serializers.UUIDField(read_only=True, allow_null=True)


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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    name = SanitizedCharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    scope = serializers.CharField(max_length=32)
    description = SanitizedCharField(allow_blank=True, required=False, default="", max_length=20000)
    artifact_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # GH-513: written justification for creating the baseline despite BLOCKER
    # findings from the SE-Auditor. Write-only — it is echoed back as part of
    # the baseline description and recorded in the audit log, not as a field.
    override_reason = SanitizedCharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        max_length=2000,
        help_text=(
            "Justification for creating this baseline although the SE-Auditor "
            "reports blocking findings (error code SE_AUDITOR_BLOCKED). "
            "Requires the 'admin' or 'approver' role; recorded in the audit "
            "log and appended to the baseline description."
        ),
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    name = SanitizedCharField(max_length=255)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    # #71: free-text name field — sanitize consistent with other narrative
    # fields (SEC-03/B006) so HTML/script markup is stripped, not stored verbatim.
    name = SanitizedCharField(max_length=255)
    # #271: passthrough on write, normalised on read — see to_representation.
    # As a JSONField this already accepts either shape (bare tier string or
    # {"tier": ...} object) at the serializer level; GH-411's actual 400 came
    # from WorkspaceViewSet.create/set_preset (rest_api/views.py) reading
    # request.data directly and never going through this serializer for
    # input — see extract_preset_tier() above for the shared parsing used
    # by both of those handlers now.
    preset = serializers.JSONField(required=False, default=dict)
    ai_prompts = serializers.JSONField(required=False, default=dict)
    decomposition_link_type = serializers.CharField(
        required=False, default="parent-child", max_length=50
    )
    default_link_type = serializers.CharField(
        required=False, default="derives-from", max_length=50
    )
    goals_enabled = serializers.BooleanField(required=False, default=False)
    goals_ai_enabled = serializers.BooleanField(required=False, default=False)
    terminology_profile = serializers.CharField(
        required=False, default="se_mode", max_length=32
    )
    language = serializers.CharField(required=False, default="en", max_length=8)
    is_active = serializers.BooleanField(read_only=True, default=True)
    closed_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)
    closed_by = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Emit a single, canonical ``preset`` shape regardless of storage (#271)."""
        data = super().to_representation(instance)
        data["preset"] = normalize_preset_blob(data.get("preset"))
        return data


class AdrSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for ADR entity (REQ-L1-029, COMP-AS-013)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = SanitizedCharField(max_length=200)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # #104: matches the Adr.context/consequences model TextField(max_length=5000)
    # cap — previously unbounded at the serializer layer, allowing oversized
    # payloads to reach the model layer (where TextField.max_length is a
    # form-validator only, not a DB constraint, and is not enforced here since
    # this serializer doesn't call full_clean()).
    context = SanitizedCharField(allow_blank=True, default="", max_length=5000)
    # #373: standard ADR terminology field (context/decision/consequences),
    # previously missing — matches Adr.decision model TextField(max_length=5000).
    decision = SanitizedCharField(allow_blank=True, default="", max_length=5000)
    consequences = SanitizedCharField(allow_blank=True, default="", max_length=5000)
    uid = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        default="Draft",
    )
    # #290: AdrViewSet.partial_update forwards ``data.get("change_reason")`` to
    # AdrService.update_adr(), which records it on the audit event. The field was
    # never declared here, so DRF dropped it from validated_data and the audit
    # trail silently recorded ``None`` for every edit. Same silent-drop class as
    # the custom_fields bug, different cause (missing declaration, not a
    # metaclass-less mixin). Bounded like RequirementSerializer.change_reason.
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class RiskSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Risk entity (REQ-L1-029, COMP-AS-014)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = SanitizedCharField(max_length=200)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    probability = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    impact = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    risk_score = serializers.IntegerField(read_only=True)
    # REQ-L1-029 (FMEA): Risk Priority Number = probability * impact * detection.
    # Computed property on the model, never persisted.
    rpn = serializers.IntegerField(read_only=True)
    severity = serializers.ChoiceField(
        choices=["low", "medium", "high"], default="medium"
    )
    category = serializers.ChoiceField(
        choices=["technical", "operational", "organizational", "business"],
        default="technical",
    )
    # #104: matches Risk.owner model field (CharField(max_length=255)).
    owner = serializers.CharField(allow_blank=True, default="", max_length=255)
    # REQ-L1-029 (FMEA): structured User FK for risk assignment, kept alongside
    # the legacy free-text `owner` field.
    owner_user_id = serializers.UUIDField(allow_null=True, required=False)
    owner_user_display = serializers.CharField(read_only=True, allow_null=True)
    # REQ-L1-029 (FMEA): detectability score (1=easy .. 10=impossible).
    detection = serializers.IntegerField(min_value=1, max_value=10, default=5)
    # #104: narrative field, unbounded before — cap at 10000 chars (DoS risk).
    mitigation_strategy = SanitizedCharField(allow_blank=True, default="", max_length=10000)
    uid = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=["Identified", "Monitored", "Mitigated", "Accepted", "Closed"],
        default="Identified",
    )
    # #290: see AdrSerializer.change_reason — RiskViewSet.partial_update
    # forwards it to RiskService.update_risk() but DRF dropped it.
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class GoalSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Goal entity (REQ-L2-TE-020, Task 6)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # REQ-016: id of the owning Artifact, needed by the UI to read/write
    # workspace-defined custom fields (UI concept ch. 12.11). Read-only —
    # the Artifact is created by the service, never supplied by the client.
    artifact_id = serializers.UUIDField(read_only=True)
    lineage_id = serializers.UUIDField(required=False, allow_null=True)
    sequence_number = serializers.IntegerField(read_only=True)
    title = SanitizedCharField(max_length=255)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    status = serializers.CharField(read_only=True)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class MainGoalSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for MainGoal entity (REQ-L2-TE-020, Task 6)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    sequence_number = serializers.IntegerField(read_only=True)
    content = SanitizedCharField(max_length=20000)
    source = serializers.ChoiceField(choices=["ai", "manual"], read_only=True)
    generated_from_goal_ids = serializers.ListField(
        child=serializers.CharField(), read_only=True, required=False
    )
    status = serializers.CharField(read_only=True)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class TestRunSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TestRun entity (REQ-L2-AS-030)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    name = SanitizedCharField(
        max_length=255,
        help_text=(
            "TestRun label (REST-01: equivalent to 'title' on Requirement/Issue/ADR/"
            "Risk artifacts; named 'name' here for consistency with CI job naming)."
        ),
    )
    uid = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    # #104: matches TestRun.ci_job_id model field (CharField(max_length=255)).
    ci_job_id = serializers.CharField(allow_blank=True, default="", max_length=255)
    started_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True)
    result_summary = serializers.JSONField(read_only=True, required=False)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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
    # #104: test log/failure message, unbounded before — cap at 10000 chars
    # (DoS risk; long enough for typical stack traces/assertion output).
    message = serializers.CharField(allow_blank=True, default="", max_length=10000)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)


class TestRunResultBulkSerializer(serializers.Serializer):
    """Serializer for bulk result ingestion (REQ-L2-AS-031)."""

    results = TestRunResultSerializer(many=True)


class NormalizedChoiceField(serializers.ChoiceField):
    """ChoiceField that normalizes input string to Title-Case before validation.

    Allows API clients to send "open", "OPEN", or "Open" — all normalize to "Open"
    (or the appropriate Title-Case variant) before choice validation.
    """

    def to_internal_value(self, data):
        """Normalize string input to Title-Case before validating against choices."""
        if isinstance(data, str):
            data = data.title()
        return super().to_internal_value(data)


class IssueSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for Issue entity (REQ-L1-029, COMP-AS-015)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = SanitizedCharField(max_length=200)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    severity = serializers.ChoiceField(
        choices=["critical", "high", "medium", "low"], default="medium"
    )
    category = serializers.ChoiceField(
        choices=["defect", "improvement", "documentation", "question"],
        default="defect",
    )
    uid = serializers.CharField(read_only=True, allow_null=True)
    # REQ-165/REQ-166 (CR-08): stays writable (unlike RequirementSerializer/
    # TestCaseSerializer.status) because IssueViewSet.create() legitimately
    # accepts an initial status (no prior WorkflowItemState to diverge from) and
    # several unit tests (test_serializers.py) validate/normalize this field
    # directly. IssueViewSet.partial_update() deliberately does NOT forward
    # `status` from PATCH to update_issue() — the WorkflowEngine is the single
    # source of truth once the item exists (ADR-status-single-source.md); change
    # the lifecycle state via POST /api/v1/issues/{id}/transitions/.
    status = NormalizedChoiceField(
        choices=["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
        default="Open",
        error_messages={
            "invalid_choice": (
                '"{input}" is not a valid choice. Valid choices are: '
                "Open, In Progress, Resolved, Closed, Wontfix."
            )
        },
    )
    tags = serializers.JSONField(required=False, default=list)
    # #290: see AdrSerializer.change_reason — IssueViewSet.partial_update
    # forwards it to IssueService.update_issue() but DRF dropped it.
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ChangeRequestSerializer(PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for ChangeRequest entity (REQ-157, COMP-AS-017).

    Covers the full CCB approval lifecycle:
    draft → submitted → under_review → approved|rejected → implemented
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    title = SanitizedCharField(max_length=255)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # #104: narrative CCB fields, unbounded before (DoS risk).
    impact_assessment = SanitizedCharField(allow_blank=True, default="", max_length=10000)
    change_reason = SanitizedCharField(allow_blank=True, default="", max_length=2000)
    status = serializers.ChoiceField(
        choices=["draft", "submitted", "under_review", "approved", "rejected", "implemented"],
        default="draft",
    )
    requestor_id = serializers.UUIDField(read_only=True, allow_null=True)
    assigned_reviewer_id = serializers.UUIDField(
        allow_null=True, required=False, default=None
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class IcdParameterSerializer(serializers.Serializer):
    """Serializer for IcdParameter entity (REQ-L2-ICD-002, COMP-ICD-001).

    Structured, version-specific interface parameter (unit, data type,
    direction, numeric bounds, tolerance) attached to an IcdVersion.
    """

    id = serializers.UUIDField(read_only=True)
    icd_version_id = serializers.UUIDField(read_only=True)
    name = SanitizedCharField(max_length=200)
    description = SanitizedCharField(
        allow_blank=True, default="", max_length=2000
    )
    unit = serializers.CharField(allow_blank=True, default="", max_length=50)
    data_type = serializers.ChoiceField(
        choices=["float", "int", "string", "boolean", "enum", "other"],
        default="other",
    )
    direction = serializers.ChoiceField(
        choices=["input", "output", "bidirectional"],
        default="input",
    )
    min_value = serializers.DecimalField(
        max_digits=20, decimal_places=6, required=False, allow_null=True, default=None
    )
    max_value = serializers.DecimalField(
        max_digits=20, decimal_places=6, required=False, allow_null=True, default=None
    )
    nominal_value = serializers.CharField(
        allow_blank=True, default="", max_length=200
    )
    tolerance = serializers.CharField(allow_blank=True, default="", max_length=100)
    ordering = serializers.IntegerField(default=0)
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
        help_text=LOCK_VERSION_HELP_TEXT,
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

    # Custom field names end up as object keys wherever the frontend indexes a
    # value map by field name; these three are unsafe there (prototype
    # pollution via `obj[name] = value` bracket assignment) even though they
    # are inert as plain Django CharField values (QA-66).
    _RESERVED_NAMES = frozenset({"__proto__", "constructor", "prototype"})

    def validate_name(self, value: str) -> str:
        if value.strip().lower() in self._RESERVED_NAMES:
            raise serializers.ValidationError(
                f"'{value}' is a reserved name and cannot be used as a custom field name."
            )
        return value

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
    # #104: custom field values are user-authored free text (field_type=="text")
    # and were unbounded before — cap to prevent oversized payloads (DoS risk).
    value = serializers.CharField(
        allow_blank=True, allow_null=True, required=False, default="", max_length=5000
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
    # #104: matches GlossaryTermSerializer.definition — unbounded before (DoS risk).
    definition = SanitizedCharField(max_length=20000)
    # #269/4: both fields are user-authored prose that the SPA, the PDF report
    # and the ReqIF export render verbatim, yet neither was guarded — only
    # ``term``/``definition`` were. ``synonyms`` needs the JSON variant because
    # its payload sits inside a list, which the scalar guard skipped.
    synonyms = SanitizedJSONField(required=False, default=list)
    abbreviation = SanitizedCharField(
        required=False, allow_blank=True, default=""
    )
    created_at = serializers.DateTimeField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)


class GlossaryTermSerializer(serializers.Serializer):
    """Serializer for GlossaryTerm (REQ-L2-RA-001)."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    term = SanitizedCharField(
        max_length=255,
        help_text=(
            "GlossaryTerm label (REST-01: equivalent to 'title' on Requirement/Issue/"
            "ADR/Risk artifacts; named 'term' here per domain terminology)."
        ),
    )
    # #104: narrative definition field, unbounded before (DoS risk).
    definition = SanitizedCharField(max_length=20000)
    # #269/4: both fields are user-authored prose that the SPA, the PDF report
    # and the ReqIF export render verbatim, yet neither was guarded — only
    # ``term``/``definition`` were. ``synonyms`` needs the JSON variant because
    # its payload sits inside a list, which the scalar guard skipped.
    synonyms = SanitizedJSONField(required=False, default=list)
    abbreviation = SanitizedCharField(
        required=False, allow_blank=True, default=""
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
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

    QIRK-002 (#73): any other key in the payload is rejected with HTTP 400
    rather than silently dropped. Silently returning 200 made callers believe a
    password or privilege change had been applied when it had not.
    """

    #: Writable via this endpoint. Everything else in the payload is an error.
    WRITABLE_FIELDS = ("first_name", "last_name")

    #: Security/identity fields that a caller must never set here. Listed
    #: explicitly so the 400 can carry a targeted, actionable message.
    PROTECTED_FIELDS = (
        "password",
        "is_admin",
        "is_superuser",
        "is_staff",
        "is_active",
        "roles",
        "role",
        "tenant_id",
        "tenant",
        "username",
        "email",
        "id",
    )

    id = serializers.UUIDField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    # #269: user-authored and rendered in the navigation shell / audit trail,
    # so they belong to the same free-text class as title/description.
    first_name = SanitizedCharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    last_name = SanitizedCharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    is_active = serializers.BooleanField(read_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject protected and unknown keys with 400 (QIRK-002, #73).

        DRF ignores non-writable keys by default, which is safe (no mass
        assignment) but misleading: the caller gets 200 for an operation that
        never happened. Validation happens before ``update()``, so a payload
        mixing legal and rejected fields applies nothing at all.
        """
        supplied = getattr(self, "initial_data", None)
        if not isinstance(supplied, dict):
            return attrs

        errors: dict[str, list[str]] = {}
        for key in supplied:
            if key in self.WRITABLE_FIELDS:
                continue
            if key == "password":
                errors[key] = [
                    "Passwords cannot be changed via this endpoint. Use the "
                    "administrative user management instead."
                ]
            elif key in self.PROTECTED_FIELDS:
                errors[key] = [
                    "This field is read-only and cannot be changed via "
                    "/auth/me/."
                ]
            else:
                errors[key] = ["Unknown field."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

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
    "normalize_preset_blob",
    "extract_preset_tier",
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
