"""
COMP-RA-002 DataSerializer — serializers_governance — extracted from rest_api/serializers.py (content-sensible split; public import surface preserved by the facade)..

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
    ClientUidRejectionMixin,
    CustomFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    LOCK_VERSION_HELP_TEXT,
    PresetAwareSerializerMixin,
    SanitizedCharField,
    UID_HELP_TEXT,
    UnknownFieldRejectionMixin,
    normalize_preset_blob,
)




class WorkflowDefinitionSerializer(
    UnknownFieldRejectionMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for WorkflowDefinition entity (REQ-L2-RA-001).

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts, instead of the DRF default of silently dropping them.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    artifact_id = serializers.UUIDField()
    name = SanitizedCharField(max_length=255)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)



class WorkspaceSerializer(
    ExpectedVersionSerializerMixin,
    UnknownFieldRejectionMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for Workspace entity (REQ-L1-017, REQ-L1-042).

    ``terminology_profile`` is sourced from the optional
    ``WorkspacePresetConfig`` one-to-one companion; ``language`` is the
    UI/content language (preset blob), ``ai_language`` the separate setting
    every LLM prompt answers in (S7, spec §7.6).

    Lifecycle fields (REQ-L1-042):
      ``is_active``, ``closed_at``, ``closed_by`` — soft-delete / close metadata.

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts. ``WorkspaceViewSet.create``/``partial_update`` read every
    input key from this serializer's schema (``preset`` through
    ``goals_ai_enabled``) plus the declared read-only lifecycle flag
    ``is_active``, so a typo now answers 400 instead of a hollow 201/200.

    #1244: ``ExpectedVersionSerializerMixin`` declares the write-only
    ``expected_version`` field so ``PATCH /api/v1/workspaces/{id}/`` can be made
    conditional like every artifact endpoint — the version is then compared in
    ``WorkspaceService.update_metadata``'s row-locked transaction, and an
    ``If-Match`` header takes precedence (``ETagMixin.resolve_expected_version``),
    answering 412 when stale.
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
    # SYSTEMAUDIT_2026-08-29 (REST finding 2): read-only, was writable-looking.
    # ``Workspace.ai_prompts`` is a leftover from before #119 moved AI prompt
    # configuration to the versioned ``PromptTemplate`` model; the only value
    # still read from the blob is the ``context_token_budgets`` override, which
    # is administered through MCP. Neither POST nor PATCH ever wrote it, so
    # advertising it as an input field promised a write path that does not
    # exist. Edit prompts via /api/v1/prompt-templates/ instead.
    ai_prompts = serializers.JSONField(read_only=True, default=dict)
    decomposition_link_type = serializers.CharField(
        required=False, default="decomposes", max_length=50
    )
    default_link_type = serializers.CharField(
        required=False, default="derives-from", max_length=50
    )
    goals_enabled = serializers.BooleanField(required=False, default=True)
    goals_ai_enabled = serializers.BooleanField(required=False, default=False)
    # #1266: resolution mode for version-bound glossary reference tokens
    # (``[[glossary:<uuid>@<revision>]]``) rendered in markdown fields.
    glossary_reference_mode = serializers.ChoiceField(
        choices=["pinned", "always_head"],
        required=False,
        default="pinned",
        help_text=(
            "'pinned' (default): a reference keeps the term version stored in "
            "the token; 'always_head': references always resolve against the "
            "term's current head."
        ),
    )
    terminology_profile = serializers.CharField(
        required=False, default="se_mode", max_length=32
    )
    language = serializers.CharField(required=False, default="en", max_length=8)
    # S7 (spec §7.6/E10): one language setting for every LLM prompt of this
    # workspace. ``auto`` inherits ``language`` and keeps the pre-S7 behaviour.
    ai_language = serializers.ChoiceField(
        choices=["auto", "de", "en"],
        required=False,
        default="auto",
        help_text=(
            "Language every AI-generated text uses: 'auto' inherits the "
            "content language, 'de'/'en' override it."
        ),
    )
    theme = serializers.CharField(required=False, default="dark", max_length=32)
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

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Reject a non-string ``name`` instead of silently coercing it.

        DRF's ``CharField`` turns a JSON number into text, so ``{"name": 123}``
        used to validate and persist ``"123"`` — a client-side type bug stored
        as if it were a name. ``WorkspaceViewSet.partial_update`` validates the
        payload before its lifecycle branch (GH-1396 review finding B1: an
        invalid payload must write nothing), and ``{"is_active": false,
        "name": 123}`` is the case that pins it, so the field has to actually
        reject the value for that ordering to be observable.

        Only the *type* is tightened; every string value keeps the previous
        free-text validation. Raising here (rather than in ``validate_name``,
        which only sees the already-coerced ``"123"``) is what preserves the
        distinction between ``123`` and ``"123"``.
        """
        if isinstance(data, Mapping):
            raw_name = data.get("name")
            if raw_name is not None and not isinstance(raw_name, str):
                raise serializers.ValidationError({"name": ["Must be a string."]})
        return super().to_internal_value(data)



class AdrSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for ADR entity (REQ-L1-029, COMP-AS-013)."""

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "Adr"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #1763: id of the backing Artifact. The Inspector's comment panel addresses
    # comments by Artifact, not by per-type entity id, so without this field the
    # ADR comment tab degrades to "not available". Read-only — the Artifact is
    # created by AdrService, never supplied by the client; nullable because the
    # OneToOne is nullable for pre-REQ-L2-TE-020 rows.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = SanitizedCharField(max_length=200)
    # #890: 10000 mirrors the Adr.description TextField(max_length=10000) and
    # AdrService._validate_description (create + update); the previous 20000
    # came from the blanket #4/#26 description cap and accepted payloads the
    # service then rejected, i.e. serializer and domain limit disagreed.
    description = SanitizedCharField(allow_blank=True, default="", max_length=10000)
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
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    # ADR-006: a multi-value **person reference** (ISO 42010 deciders) — real
    # Actor rows, not typed names, so a rename updates every ADR that names them.
    # Wire form is the `multiple` envelope of spec section 4. Persisted through
    # the gateway (`_apply_artifact_system_fields` → `Adr.deciders.set(...)`),
    # which is why `AdrViewSet` never passes it to `AdrService`.
    deciders = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text=(
            'ISO 42010 deciders of this ADR, as '
            '{"multiple": true, "items": [{"kind": "user", "id": "<uuid>"}]}. '
            "Internal users and external placeholders are both Actors."
        ),
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



class RiskSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for Risk entity (REQ-L1-029, COMP-AS-014)."""

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "Risk"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #1763: see AdrSerializer.artifact_id — the Inspector comment panel needs
    # the backing Artifact id, which the DTO supplies, not the client.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
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
    # #1707: writable enum, but deliberately **no** ``default``. A default
    # would make DRF treat the field as ``required=True`` on create (no way to
    # express "not supplied → derive from the score") and would let a PATCH
    # that never mentions ``severity`` reset it to the default. ``required=False``
    # without a default is what makes "omitted means untouched" expressible.
    severity = serializers.ChoiceField(
        choices=["low", "medium", "high"], required=False
    )
    category = serializers.ChoiceField(
        choices=["technical", "operational", "organizational", "business"],
        default="technical",
    )
    # Attribut v3 WS7 (#940): the legacy free-text owner column was renamed to
    # ``owner_name`` (same DB column) so the Artifact-level ``owner`` Actor FK
    # — declared by ArtifactSystemFieldsSerializerMixin — is no longer shadowed
    # at the type model. The AWMS plan risk_owner_to_actor folds this value onto
    # the Actor carrier.
    owner_name = serializers.CharField(allow_blank=True, default="", max_length=255)
    # REQ-L1-029 (FMEA): structured User FK for risk assignment, kept alongside
    # the legacy free-text `owner` field.
    owner_user_id = serializers.UUIDField(allow_null=True, required=False)
    owner_user_display = serializers.CharField(read_only=True, allow_null=True)
    # REQ-L1-029 (FMEA): detectability score (1=easy .. 10=impossible).
    detection = serializers.IntegerField(min_value=1, max_value=10, default=5)
    # #104: narrative field, unbounded before — cap at 10000 chars (DoS risk).
    mitigation_strategy = SanitizedCharField(allow_blank=True, default="", max_length=10000)
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
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



class DocumentSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for the Document artifact (Plan F F2-T5, ADR-026).

    ``Document`` is an artifact-backed entity like Adr/Risk, so it reuses the
    same four shared seams:

    * ``WorkflowStateSerializerMixin`` supplies the read-only ``status`` from
      ``WorkflowItemState`` (the model deliberately has no lifecycle column,
      REQ-143).
    * ``CustomFieldsSerializerMixin`` also carries
      ``UnknownFieldRejectionMixin`` (#851) and the flat-map validation for
      ``custom_fields``.
    * ``ExpectedVersionSerializerMixin`` declares the write-only
      ``expected_version`` used by the HTTP precondition (KA-F-08). The ETag
      itself is emitted by ``DocumentViewSet`` via ``ETagMixin.with_etag``.
    * ``ClientUidRejectionMixin`` keeps ``uid`` system-owned (``DOC-NNN``).

    The Artifact-level system fields (``owner``/``reporter``/``priority``) are
    intentionally **not** declared: ``Document`` is deliberately absent from
    ``SYSTEM_FIELDS_ENABLED_ITEM_TYPES`` (F2-T7 wired the definition, not this
    transport), so the attribute gateway keeps those fields hidden for this
    type. Declaring them here would advertise a write path the gateway cannot
    validate.

    ``frozen_at``/``frozen_fields`` are read-only. They are the F-1 freeze
    bookkeeping the service writes on release; a client can observe that a
    document is frozen, but never set or clear the flag directly.
    """

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "Document"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # REQ-016: the backing Artifact id, needed to attach trace links and
    # comments from the client. Read-only — the service creates the Artifact.
    artifact_id = serializers.UUIDField(read_only=True)
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    title = SanitizedCharField(max_length=255)
    kind = serializers.ChoiceField(
        choices=Document.Kind.choices,
        help_text="Document kind (Spec, Plan, AuditReport, Review, …).",
    )
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    body = SanitizedCharField(
        allow_blank=True,
        default="",
        help_text="Markdown content of the document.",
    )
    doc_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Document date, e.g. derived from a source file name.",
    )
    frozen_at = serializers.DateTimeField(read_only=True, allow_null=True)
    frozen_fields = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
        help_text="Content fields locked by the release (F-1/F-2).",
    )
    # Phase G / #1374 S3: dual-source and projection bookkeeping, written only
    # by import/adopt/confirm. Read-only here so no generic PATCH can forge them.
    owner_mode = serializers.CharField(read_only=True)
    source_path = serializers.CharField(read_only=True)
    source_sha256 = serializers.CharField(read_only=True)
    projection_mode = serializers.CharField(read_only=True)
    projected_sha256 = serializers.CharField(read_only=True)
    projected_version = serializers.IntegerField(read_only=True, allow_null=True)
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)



class DocumentReadingChapterSerializer(serializers.Serializer):
    """One chapter of the document reading view (R1).

    ``anchor`` is the stable slug the reading view uses as a DOM id; ``number``
    is the display number ("1.1") and empty for the unnumbered preamble chapter.
    No body field is HTML — the client renders the Markdown itself.
    """

    number = serializers.CharField(allow_blank=True)
    level = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    anchor = serializers.CharField(allow_blank=True)
    body = serializers.CharField(allow_blank=True)



class DocumentReadingProjectionSerializer(serializers.Serializer):
    """Read-only projection bookkeeping exposed by the reading view (R1)."""

    projection_mode = serializers.CharField(allow_blank=True)
    source_path = serializers.CharField(allow_blank=True)
    projected_sha256 = serializers.CharField(allow_blank=True)



class DocumentReadingLockedSerializer(serializers.Serializer):
    """Why a document field is not editable (R2).

    ``code`` is machine-readable (``PERMISSION`` / ``REPO_EXTERNAL`` /
    ``FIELD_FROZEN``); ``detail`` is the human sentence a surface may show
    without inventing its own wording.
    """

    code = serializers.CharField()
    detail = serializers.CharField()



class DocumentReadingFieldSerializer(serializers.Serializer):
    """One field of the document reading view with its write verdict (R2).

    ``value`` is polymorphic (string, ISO date or the ``custom_fields`` map), so
    it stays a ``JSONField`` — the surface renders it; ``editable``/``locked``
    are the policy answer, identical to what ``PATCH /documents/{id}/`` accepts.
    """

    name = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    editable = serializers.BooleanField()
    locked = DocumentReadingLockedSerializer(allow_null=True)



class DocumentReadingCapabilitiesSerializer(serializers.Serializer):
    """Document-level write capability of the reading view (R2).

    ``read_only_reason`` is ``PERMISSION`` or ``REPO_EXTERNAL`` when nothing may
    be written, ``null`` otherwise — the same reason the per-field ``locked``
    blocks carry first.
    """

    can_write = serializers.BooleanField()
    read_only_reason = serializers.CharField(allow_null=True)



class DocumentReadingSerializer(serializers.Serializer):
    """Response contract of ``GET /api/v1/documents/{id}/view/`` (R1, ADR-026).

    Read-only by construction: the reading view is a *read* object, writes stay
    on ``PATCH /api/v1/documents/{id}/`` (plan §0, "ein Schreibweg je Typ"). The
    shape mirrors ``DocumentViewResult.to_dict()`` one-to-one — this serializer
    exists for the OpenAPI schema, not to transform data.
    """

    id = serializers.UUIDField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    uid = serializers.CharField(read_only=True, allow_null=True)
    title = serializers.CharField()
    kind = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    body = serializers.CharField(allow_blank=True)
    doc_date = serializers.DateField(allow_null=True)
    version = serializers.IntegerField(help_text=LOCK_VERSION_HELP_TEXT)
    status = serializers.CharField()
    frozen_at = serializers.DateTimeField(allow_null=True)
    frozen_fields = serializers.ListField(child=serializers.CharField())
    editable_fields = serializers.ListField(
        child=serializers.CharField(),
        help_text=(
            "Flat list of field names reported as editable in ``fields`` — "
            "same source, same order, so the two cannot disagree."
        ),
    )
    fields = DocumentReadingFieldSerializer(
        many=True,
        help_text=(
            "Per-field value plus the write verdict (R2): ``editable`` matches "
            "what PATCH /documents/{id}/ actually accepts, ``locked`` names the "
            "reason when it does not."
        ),
    )
    capabilities = DocumentReadingCapabilitiesSerializer(
        help_text="Document-level write capability of the caller (R2)."
    )
    chapters = DocumentReadingChapterSerializer(many=True)
    projection = DocumentReadingProjectionSerializer()



# ---------------------------------------------------------------------------
# R3 (document view): PATCH /api/v1/artifacts/bulk-update/
#
# The batch write the editable document view (and the table view it shares this
# contract with) sends: a page of rows in one request, so a single stale version
# cannot leave the page half-saved. The request/response shapes mirror
# ``application.bulk_update_service`` (``BulkEntry`` / ``BulkUpdateResult``) —
# they are not a second contract, only its wire form.
# ---------------------------------------------------------------------------


class BulkUpdateEntrySerializer(UnknownFieldRejectionMixin, serializers.Serializer):
    """One ``entries[]`` item of the bulk-update request (R3.2).

    ``fields`` is deliberately a free-form map: the accepted field *names* depend
    on the artifact's type, and ``BulkUpdateService`` checks them against the
    type's own update signature. Declaring one flat field set here would either
    reject valid keys or advertise keys the type's service does not accept.
    """

    artifact_id = serializers.UUIDField(
        help_text=(
            "UUID of the backing Artifact (the id trace links and the generic "
            "artifact routes use), not the typed row's own id."
        )
    )
    expected_version = serializers.IntegerField(
        min_value=1,
        help_text=(
            "Caller's last-seen version of the row. A stale value fails this "
            "entry with CONFLICT and rolls the whole batch back."
        ),
    )
    fields = serializers.DictField(
        help_text=(
            "Service fields to write, e.g. {\"title\": \"…\", \"body\": \"…\"}. "
            "Names are checked per artifact type; values are validated by that "
            "artifact's own service (freeze gate, syntax, change-reason policy)."
        )
    )



class BulkUpdateRequestSerializer(UnknownFieldRejectionMixin, serializers.Serializer):
    """Body of ``PATCH /api/v1/artifacts/bulk-update/`` (R3.2)."""

    workspace_id = serializers.UUIDField(
        help_text=(
            "Workspace every entry must belong to. An artifact of another "
            "workspace is refused with WORKSPACE_MISMATCH."
        )
    )
    entries = BulkUpdateEntrySerializer(
        many=True,
        allow_empty=False,
        max_length=MAX_ENTRIES,
        help_text=(
            f"1..{MAX_ENTRIES} writes, applied in order in one transaction. The "
            "first failure rolls every entry back."
        ),
    )



class BulkUpdateUpdatedSerializer(serializers.Serializer):
    """One written artifact in the ``updated`` list."""

    artifact_id = serializers.UUIDField()
    version = serializers.IntegerField(
        help_text="Version after the write (the value to send next time)."
    )



class BulkUpdateErrorSerializer(serializers.Serializer):
    """One refused entry in the ``errors`` list."""

    index = serializers.IntegerField(
        help_text="Zero-based position in the request's ``entries`` list."
    )
    artifact_id = serializers.UUIDField(
        allow_null=True, help_text="The entry's artifact id, or null if absent."
    )
    code = serializers.CharField(
        help_text=(
            "NOT_FOUND | WORKSPACE_MISMATCH | UNSUPPORTED_ARTIFACT_TYPE | "
            "UNKNOWN_FIELD | CONFLICT | FIELD_FROZEN | WORKFLOW_FROZEN | "
            "PERMISSION_DENIED | VALIDATION_ERROR"
        )
    )
    message = serializers.CharField()
    field = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Offending field name when the refusal names one.",
    )



class BulkUpdateResponseSerializer(serializers.Serializer):
    """Body of ``200`` and of the ``409`` refusal (same shape, different list)."""

    updated = BulkUpdateUpdatedSerializer(
        many=True,
        help_text="Empty whenever ``errors`` is non-empty — nothing was written.",
    )
    errors = BulkUpdateErrorSerializer(many=True)



# ---------------------------------------------------------------------------
# Slice 2 (Tabellenansicht): POST /api/v1/artifacts/bulk-transition/
#
# "Move the selected rows to one state." Deliberately a second body shape rather
# than a mode on bulk-update: the transition takes no per-row expected_version
# (the workflow row lock serialises concurrent transitions) and is
# **partial-success** by contract, so its result names what moved instead of
# reporting that nothing did. No ``workspace_id``: the workspace is derived from
# the ids, so a caller cannot scope the role check to A while writing B's rows.
# ---------------------------------------------------------------------------


class BulkTransitionRequestSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of ``POST /api/v1/artifacts/bulk-transition/`` (slice 2)."""

    item_type = serializers.CharField(
        help_text=(
            "Artifact type every id must have (e.g. \"Requirement\"), i.e. the "
            "``artifact_type`` the table row reports."
        )
    )
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=MAX_TRANSITION_IDS,
        help_text=(
            f"1..{MAX_TRANSITION_IDS} backing Artifact ids. Missing ids are "
            "reported per row as NOT_FOUND; ids of two workspaces reject the "
            "whole request (400)."
        ),
    )
    to_state = serializers.CharField(
        help_text=(
            "Target state name as declared in the workspace's workflow graph. "
            "The graph decides per row whether the edge exists."
        )
    )
    change_reason = serializers.CharField(
        allow_blank=False,
        help_text=(
            "Reason recorded on every transition. Required: a bulk state change "
            "without a reason is not auditable."
        ),
    )



class BulkTransitionedSerializer(serializers.Serializer):
    """One moved artifact in the ``transitioned`` list."""

    artifact_id = serializers.UUIDField()
    state = serializers.CharField(
        help_text="State the row is in after the transition."
    )



class BulkTransitionResponseSerializer(serializers.Serializer):
    """Body of ``200`` (partial success is the contract, so failures keep 200)."""

    transitioned = BulkTransitionedSerializer(
        many=True,
        help_text="Rows that moved. Empty rows are named in ``failed`` instead.",
    )
    failed = BulkUpdateErrorSerializer(
        many=True,
        help_text=(
            "Rows the graph or a gate refused, with index, artifact_id, code and "
            "message. Codes: VALIDATION_ERROR | NOT_FOUND | FORBIDDEN | CONFLICT."
        ),
    )



class WorkItemSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for the ``WorkItem`` artifact (Plan F F3-T5, #1374).

    Mirrors :class:`DocumentSerializer`: the workflow ``status`` is read-only and
    engine-resolved (REQ-143), ``custom_fields`` lives on the backing Artifact,
    and ``expected_version`` is the write-only half of the ETag contract
    (KA-F-08). ``uid`` stays system-owned (``WI-NNN``).

    ``document_id`` is mandatory on create (concept E11/O7: a work item never
    exists without a document) and immutable afterwards; the view rejects a
    PATCH that tries to move the item to another document, so this serializer
    accepts the key on both paths but never silently drops a change.

    ``actor`` is a write-only free-text identity for the heartbeat (``A-3``);
    ``last_actor``/``approved_by`` are read-only observations of what the
    service actually recorded. An agent has no ``User`` row, so the identity is
    a string rather than an actor FK (spec §3.2).
    """

    workflow_item_type = "WorkItem"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    document_id = serializers.UUIDField(required=True)
    # REQ-016: the backing Artifact id, needed to attach trace links/comments.
    artifact_id = serializers.UUIDField(read_only=True)
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    title = SanitizedCharField(max_length=255)
    kind = serializers.ChoiceField(
        choices=WorkItem.Kind.choices,
        help_text="Work-item kind (Phase, Step, Milestone, OpenPoint, Checkpoint).",
    )
    ordinal = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        help_text="Position inside the document; resume sorts by (ordinal, id).",
    )
    body = SanitizedCharField(
        allow_blank=True,
        default="",
        help_text="Markdown of the section (used by Step/Checkpoint).",
    )
    progress = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=100,
        help_text="Optional 0-100 progress, independent of the workflow state.",
    )
    blocked_reason = SanitizedCharField(
        allow_blank=True,
        default="",
        max_length=20000,
        help_text="Required while the item is 'blocked'; also carries the dismissal reason.",
    )
    next_action = SanitizedCharField(
        allow_blank=True,
        default="",
        max_length=255,
        help_text="Resume hint ('where to continue') for an agent.",
    )
    evidence_ref = SanitizedCharField(
        allow_blank=True,
        default="",
        max_length=512,
        help_text="Evidence (commit, test run, artifact id).",
    )
    last_activity_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_actor = serializers.CharField(read_only=True, allow_blank=True)
    approved_by = serializers.CharField(read_only=True, allow_blank=True)
    approved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    due_date = serializers.DateTimeField(
        required=False, allow_null=True, help_text="Optional due date."
    )
    exit_criteria = SanitizedCharField(
        allow_blank=True,
        default="",
        max_length=20000,
        help_text="Definition of done for this item.",
    )
    #: Write-only heartbeat identity; the service records it as ``last_actor``.
    actor = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        max_length=128,
        help_text="Agent/session identity recorded as last_actor (A-1/A-3).",
    )
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)



class MilestoneSerializer(
    UnknownFieldRejectionMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for the ``Milestone`` entity (Plan B B6-T2, #879).

    A milestone plans a formal review (SRR/PDR/CDR/TRR/ORR), so it is a plain
    tenant-scoped row: no backing ``Artifact``, no ``uid``, no workflow state
    and no trace-link endpoints (ENT-B2 = a). The two relation changes are
    deliberately *not* general purpose fields:

    * ``baseline_id`` is only honoured on create; rebinding afterwards goes
      through ``POST /milestones/{id}/bind-baseline/`` so the cross-workspace
      refusal in ``MilestoneService.bind_baseline`` cannot be bypassed with a
      PATCH body.
    * ``status`` is a plain enum column (no ``WorkflowEngine`` state), so it is
      writable here.
    * ``audit_snapshot`` is read-only: it is the frozen output of the SE-Auditor
      written by ``POST /milestones/{id}/record-audit/``.

    ``ExpectedVersionSerializerMixin`` supplies the write-only
    ``expected_version`` field; ``MilestoneViewSet`` emits the matching
    ``ETag``. ``UnknownFieldRejectionMixin`` (#851) rejects a key no declared
    field accepts instead of silently dropping it.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(
        required=True,
        help_text="Owning workspace (immutable after create).",
    )
    name = SanitizedCharField(
        max_length=200,
        help_text="Human-readable milestone name, e.g. 'PDR Fahrwerk'.",
    )
    review_type = serializers.ChoiceField(
        choices=Milestone.ReviewType.choices,
        help_text="Formal review this milestone plans.",
    )
    target_date = serializers.DateField(
        help_text="Planned review date; the primary sort key of every list.",
    )
    status = serializers.ChoiceField(
        choices=Milestone.Status.choices,
        required=False,
        default=Milestone.Status.PLANNED,
        help_text="Planning/execution state (default 'planned').",
    )
    baseline_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=(
            "Create only: bind a baseline of the same workspace. Rebinding an "
            "existing milestone uses POST /{id}/bind-baseline/."
        ),
    )
    audit_snapshot = serializers.JSONField(
        read_only=True,
        allow_null=True,
        help_text=(
            "Frozen copy of the last SE-Auditor run "
            "({tier, counts, run_at}); written by POST /{id}/record-audit/."
        ),
    )
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)



class MilestoneBindBaselineSerializer(
    UnknownFieldRejectionMixin,
    ExpectedVersionSerializerMixin,
    serializers.Serializer,
):
    """Request body of ``POST /milestones/{id}/bind-baseline/`` (B6-T2).

    The baseline must live in the milestone's own workspace; the service refuses
    a cross-workspace binding with ``ValidationError`` (400). ``expected_version``
    is the body half of the optimistic-lock contract (stale → 409); the ETag
    header is not part of the POST contract here.
    """

    baseline_id = serializers.UUIDField(
        help_text="Baseline of the same workspace to bind."
    )
    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )



class MilestoneRecordAuditSerializer(
    UnknownFieldRejectionMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Request body of ``POST /milestones/{id}/record-audit/`` (B6-T2).

    Both fields are optional, so an empty body is valid: the action freezes the
    workspace's current SE-Auditor counts as
    ``{tier, counts: {total, blockers, warnings}, run_at}``. Recording is a
    record, never a gate, so open blockers do not refuse it.
    """

    change_reason = SanitizedCharField(
        required=False, allow_blank=True, max_length=2000
    )



class GoalSerializer(
    CustomFieldsSerializerMixin,
    WorkflowStateSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for Goal entity (REQ-L2-TE-020, Task 6).

    ``CustomFieldsSerializerMixin`` also carries the ``UnknownFieldRejectionMixin``
    behaviour (#851), so it supersedes the previous explicit base.
    """

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "Goal"

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
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)



class MainGoalSerializer(
    UnknownFieldRejectionMixin,
    WorkflowStateSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for MainGoal entity (REQ-L2-TE-020, Task 6)."""

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "MainGoal"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #1763: see AdrSerializer.artifact_id — Inspector comment panel parity.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    sequence_number = serializers.IntegerField(read_only=True)
    content = SanitizedCharField(max_length=20000)
    source = serializers.ChoiceField(choices=["ai", "manual"], read_only=True)
    generated_from_goal_ids = serializers.ListField(
        child=serializers.CharField(), read_only=True, required=False
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    # UI-28 (Systemaudit 2026-08-27 AP-5): not a persisted column — only
    # `MainGoalViewSet.generate()` ever populates it (from
    # `MainGoalService.generate_ai()`'s response dict), every other action
    # falls back to the default below so a mock-served draft can be flagged
    # to the client right after generation without a schema migration.
    is_mock_fallback = serializers.BooleanField(read_only=True, required=False, default=False)



class TestRunSerializer(
    ClientUidRejectionMixin,
    UnknownFieldRejectionMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for TestRun entity (REQ-L2-AS-030).

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts. ``TestRunViewSet.create`` reads ``test_case_ids`` straight
    off the request body, so that key is declared here (write-only) to keep a
    real create payload valid while a typo still answers 400.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    name = SanitizedCharField(
        max_length=255,
        help_text=(
            "TestRun label (REST-01: equivalent to 'title' on Requirement/Issue/ADR/"
            "Risk artifacts; named 'name' here for consistency with CI job naming)."
        ),
    )
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    status = serializers.CharField(read_only=True)
    # #104: matches TestRun.ci_job_id model field (CharField(max_length=255)).
    ci_job_id = serializers.CharField(allow_blank=True, default="", max_length=255)
    # #1269: version identifier of the artifact under test this run executed
    # against. Read/write; nullable/blank to match the model column.
    tested_artifact_version = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
        help_text=(
            "Version identifier (commit SHA, release tag, build number) of the "
            "artifact under test. Optional."
        ),
    )
    # #851: TestRunViewSet.create reads this key directly to seed the run's
    # per-testcase results. Declared write-only (UUID list) so the unknown-field
    # guard accepts it and validates it here instead of the view coercing raw
    # request.data. Never part of a response.
    test_case_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        write_only=True,
        help_text="Optional TestCase UUIDs to seed the run's result rows.",
    )
    started_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True)
    result_summary = serializers.JSONField(read_only=True, required=False)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)



class TestRunResultSerializer(
    UnknownFieldRejectionMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for TestRunResult entity (REQ-L2-AS-030).

    #851: wired into the ``/results/`` write path, so it carries the shared
    unknown-field guard like every other top-level create/update serializer.
    """

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



class TestRunResultBulkSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Serializer for bulk result ingestion (REQ-L2-AS-031).

    #851: wired into the ``/results/bulk/`` write path. The guard applies at
    this top level (unknown keys next to ``results``) and, through the nested
    child, to every entry in the batch.
    """

    results = TestRunResultSerializer(many=True)



class IssueSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for Issue entity (REQ-L1-029, COMP-AS-015)."""

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer. Was
    # previously a writable field (IssueViewSet.create() accepted a
    # client-supplied initial status) — the WorkflowEngine already ignored
    # that value on create (initialize_workflow_states() always seeds the
    # workflow's own initial state), so the writable field only ever fed the
    # legacy mirror column, never the true state. Aligning it read-only here
    # closes that latent mirror/engine divergence instead of introducing one.
    workflow_item_type = "Issue"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #1763: see AdrSerializer.artifact_id — Inspector comment panel parity.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = SanitizedCharField(max_length=200)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    severity = serializers.ChoiceField(
        choices=["critical", "high", "medium", "low"], default="medium"
    )
    category = serializers.ChoiceField(
        choices=["defect", "improvement", "documentation", "question"],
        default="defect",
    )
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    tags = serializers.JSONField(required=False, default=list)
    # Task 20 finding: `Issue.due_date` (application/issue_service.py's
    # create_issue/update_issue both already accept and persist it) was never
    # declared on this serializer at all — same silent-discard class as Task
    # 19's `owner_user_id` finding, but the model column had no REST field to
    # even alias. This was REST-only: the MCP generic tool group forwards
    # arbitrary params straight to the service and already round-tripped
    # `due_date` (mcp_server/tests/test_generic_tool_group.py) before this fix.
    # Writable/nullable like the rest of the optional Issue fields;
    # `_issue_to_dict` and both view methods below now round-trip it via REST
    # too.
    due_date = serializers.DateTimeField(required=False, allow_null=True, default=None)
    # ADR-006: the multi-value **person reference** — real Actor rows, in the
    # `multiple` envelope of spec section 4. Deliberately NOT an alias of the
    # legacy `assignee_id`: that UUID is owned by `IssueService.assign_issue()`
    # (REQ-L3-ISSUE-008) with its own audit trail and is not serializer-writable
    # at all; folding it onto this carrier is an AWMS value-migration step
    # (issue #940), a separate concern from the carrier landing.
    assignee = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text=(
            "Persons/teams this issue is assigned to, as "
            '{"multiple": true, "items": [{"kind": "user", "id": "<uuid>"}]}. '
            "Not the legacy 'assignee_id' User UUID, which the dedicated "
            "assign action owns."
        ),
    )
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



class ChangeRequestSerializer(
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    WorkflowStateSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for ChangeRequest entity (REQ-157, COMP-AS-017).

    Covers the full CCB approval lifecycle:
    draft → submitted → under_review → approved|rejected → implemented

    ``CustomFieldsSerializerMixin`` also carries the ``UnknownFieldRejectionMixin``
    behaviour (#851), so it supersedes the previous explicit base.
    """

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "ChangeRequest"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #1763 parity / audit 2026-11-15 §5.3: id of the backing Artifact. The
    # Inspector's comment panel addresses comments by Artifact, not by the
    # per-type entity id, so without this field the CR comment tab degrades to
    # "not available". Read-only — the Artifact is created by
    # ChangeRequestService.create_change_request (``ensure_artifact``), never
    # supplied by the client; nullable because the OneToOne is nullable for
    # rows migrated from the pre-Phase-3 data model.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = SanitizedCharField(max_length=255)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # #104: narrative CCB fields, unbounded before (DoS risk).
    impact_assessment = SanitizedCharField(allow_blank=True, default="", max_length=10000)
    change_reason = SanitizedCharField(allow_blank=True, default="", max_length=2000)
    requestor_id = serializers.UUIDField(read_only=True, allow_null=True)
    assigned_reviewer_id = serializers.UUIDField(
        allow_null=True, required=False, default=None
    )
    # #399 (cluster 5) / spec section 4.4: the drift badge's "raise change
    # request" shortcut needs a declared contract for pre-filling the affected
    # items. Write-only and additive: `create_change_request` already validates
    # the ids workspace-/tenant-scoped (`_validate_affected_items`) and
    # snapshots the "before" state, it was only never reachable through REST.
    affected_item_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True,
        help_text=(
            "Optional list of artifact UUIDs to register as affected items "
            "of the new change request."
        ),
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
