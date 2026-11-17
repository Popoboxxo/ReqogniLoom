"""
COMP-RA-002 DataSerializer — serializers_io — extracted from rest_api/serializers.py (content-sensible split; public import surface preserved by the facade)..

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

from collections.abc import Container, Mapping, Sequence
from typing import Any

from django.utils import translation
from rest_framework import pagination, serializers, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from application.bulk_update_service import MAX_ENTRIES, MAX_TRANSITION_IDS
from application.test_steps import normalize_steps, validate_steps
from persistence.models import (
    Document,
    ElementType,
    Milestone,
    ScenarioKind,
    TestCaseOrigin,
    TestCaseType,
    WorkItem,
)
from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin
from rest_api.mixins.workflow_transitions import _ALWAYS_ALLOWED_PATCH_FIELDS
from rest_api.preset_guard import FieldFilter
from rest_api.sanitization import FreeTextFieldMarker, validate_free_text


from .serializers_common import (
    ArtifactSystemFieldsSerializerMixin,
    CustomFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    LOCK_VERSION_HELP_TEXT,
    SanitizedCharField,
    SanitizedJSONField,
    UnknownFieldRejectionMixin,
)




class IcdParameterSerializer(UnknownFieldRejectionMixin, serializers.Serializer):
    """Serializer for IcdParameter entity (REQ-L2-ICD-002, COMP-ICD-001).

    Structured interface parameter (unit, data type, direction, numeric
    bounds, tolerance) of an ICD's current contract. Task 28c-2 replaced
    ``icd_version_id`` with ``icd_id``: parameters belong to the ICD, not to
    one of its revisions.

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts. ``IcdViewSet.parameters`` reads a body ``version`` directly
    to refuse writes aimed at a historical revision, so that control key is
    declared here (write-only) to keep the existing contract valid while a
    typo answers 400.
    """

    id = serializers.UUIDField(read_only=True)
    icd_id = serializers.UUIDField(read_only=True)
    name = SanitizedCharField(max_length=200)
    # #851: create-only control key (see the class docstring). Write-only so it
    # never appears in a parameter response.
    version = serializers.IntegerField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text=(
            "Optional current ICD revision this write targets; a value other "
            "than the current revision is refused."
        ),
    )
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



# Datenmodell-Konsolidierung Task 28b: GlossaryTermVersionSerializer (dead
# code — never wired to a view; the `/glossary/{pk}/versions/` and `/diff/`
# endpoints below already go through ArtifactDiffService) was removed here
# together with the GlossaryTermVersion model it serialised.


class GlossaryTermSerializer(
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    serializers.Serializer,
):
    """Serializer for GlossaryTerm (REQ-L2-RA-001).

    ``CustomFieldsSerializerMixin`` also carries the ``UnknownFieldRejectionMixin``
    behaviour (#851), so it supersedes the previous explicit base.
    """

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
    # Declared so the GlossaryTerm read endpoints keep reporting the
    # soft-delete state (issue #440): GlossaryTerm has no mirrored model
    # ``status`` column, so the state comes from the DTO. Issue #831 settled
    # the wire key on ``status`` — identical to every other workflow-backed
    # artifact serializer (Requirement/Adr/Risk/Issue/... via
    # WorkflowStateSerializerMixin) — instead of the former
    # ``lifecycle_status`` outlier. The DTO resolves the value from the
    # backing Artifact (``Artifact.lifecycle_status`` plus the workflow
    # soft-delete overlay in GlossaryService.get()).
    #
    # Read-only: lifecycle changes go through DELETE / reactivate / the
    # transitions endpoint. Note that ``_validate_patch_payload`` special-cases
    # the key ``status`` globally (#263): an unchanged echo is accepted and
    # ignored, a differing value is refused with a pointer at
    # ``POST .../transitions/``. GlossaryTermViewSet overrides
    # ``_current_status`` so that comparison can still read the current value.
    status = serializers.CharField(read_only=True)
    # #1266: the stable global UUID of the term (== backing Artifact id), the
    # identity a ``[[glossary:<uuid>@<revision>]]`` reference token pins. Same
    # value and semantics as RequirementSerializer.global_uuid (#1261/#1270).
    global_uuid = serializers.SerializerMethodField()

    def get_global_uuid(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj.get("artifact_id")
        return getattr(obj, "artifact_id", None)

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
                if key == "password":
                    # GitHub #1739: give the caller the route that *does* work.
                    errors[key] = [
                        "This field is read-only here. Use "
                        "POST /api/v1/auth/password/change/ to change your "
                        "password."
                    ]
                else:
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



class CommentSerializer(UnknownFieldRejectionMixin, serializers.Serializer):
    """Wire format for application.models.Comment (Menschen-im-System spec §4).

    Read-only apart from ``text`` — comments are never edited, only created,
    resolved and deleted.

    ``text`` is user-authored prose and therefore guarded free text (#820): it
    was a plain ``CharField``, so markup in a comment was accepted while the
    very same string was a ``400`` on ``Requirement.title`` — the inconsistency
    class #820 reported. ``ArtifactCommentsView`` runs this serializer, and
    ``CommentService.create_comment`` re-checks the same rule for the MCP tool
    group, which never touches DRF.

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts, so a typo in the create body is a 400 instead of a comment
    created without the text the caller thought they sent.
    """

    id = serializers.UUIDField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True)
    text = SanitizedCharField(max_length=10000)
    author_id = serializers.UUIDField(read_only=True, allow_null=True)
    author_display = serializers.SerializerMethodField()
    resolved = serializers.BooleanField(read_only=True)
    resolved_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    resolved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_author_display(self, obj) -> str | None:
        """Return the author's username, or None when the user was deleted."""
        author = getattr(obj, "author", None)
        return getattr(author, "username", None) if author is not None else None



class NotificationSerializer(serializers.Serializer):
    """Wire format for application.models.Notification (spec §5). Read-only."""

    id = serializers.UUIDField(read_only=True)
    kind = serializers.CharField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    message = serializers.CharField(read_only=True)
    read = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)



class CsvImportCountsSerializer(serializers.Serializer):
    """ADR-014 §1 result counters (``ImportResult.counts``)."""

    succeeded = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()
    total = serializers.IntegerField()



class CsvImportItemCauseSerializer(serializers.Serializer):
    """Machine-readable cause of one non-succeeded import row."""

    code = serializers.CharField()
    message = serializers.CharField()



class CsvImportItemSerializer(serializers.Serializer):
    """One structured per-row outcome of a contract-v2 CSV import."""

    row = serializers.IntegerField()
    identifier = serializers.CharField(allow_null=True, allow_blank=True)
    kind = serializers.CharField()
    status = serializers.CharField()
    cause = CsvImportItemCauseSerializer()



class CsvImportRowErrorSerializer(serializers.Serializer):
    """One validation/persistence error row (``ImportRowError``)."""

    row_number = serializers.IntegerField()
    field = serializers.CharField(allow_blank=True)
    message = serializers.CharField()



class CsvImportReportSerializer(serializers.Serializer):
    """``POST /workspaces/{id}/import/csv/`` report, contract v2 (ADR-014 §2).

    Mirrors ``application.import_service.ImportResult.to_dict`` exactly — no
    field is invented and none is omitted (#1388/M3). The deprecated legacy
    envelope (``IMPORT_CONTRACT_V2=false``) answers the same success statuses
    with a reduced shape and ``Deprecation``/``Sunset`` headers; it is a
    rollback path for consumers that have not migrated, not the documented
    contract.
    """

    success = serializers.BooleanField()
    contract = serializers.CharField()
    dry_run = serializers.BooleanField()
    counts = CsvImportCountsSerializer()
    items = CsvImportItemSerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())
    idempotent_replay = serializers.BooleanField()
    request_id = serializers.CharField(allow_blank=True)
    # Legacy additive keys (unchanged meaning, still always present).
    imported_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()
    status = serializers.CharField()
    errors = CsvImportRowErrorSerializer(many=True)



class SuggestionSerializer(serializers.Serializer):
    """Wire format for one ADR-019 suggestion-inbox row (#1388/F6).

    Mirrors ``SuggestionService._serialize`` exactly — the dict every
    ``suggestion.*`` REST handler already returns. ``payload`` stays a free-form
    object on purpose: its shape is owned by the per-kind adapter and is not
    statically describable here.
    """

    id = serializers.UUIDField(read_only=True)
    kind = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    producer = serializers.CharField(read_only=True)
    proposed_by = serializers.UUIDField(read_only=True, allow_null=True)
    proposed_at = serializers.DateTimeField(read_only=True)
    decided_by = serializers.UUIDField(read_only=True, allow_null=True)
    decided_at = serializers.DateTimeField(read_only=True, allow_null=True)
    target_item_type = serializers.CharField(read_only=True, allow_blank=True)
    target_item_id = serializers.UUIDField(read_only=True, allow_null=True)
    payload = serializers.DictField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True, allow_null=True)
