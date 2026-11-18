"""
COMP-RA-002 DataSerializer — serializers_trace_baseline — extracted from rest_api/serializers.py (content-sensible split; public import surface preserved by the facade)..

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
    LOCK_VERSION_HELP_TEXT,
    PresetAwareSerializerMixin,
    SanitizedCharField,
    UnknownFieldRejectionMixin,
)




class TraceLinkSerializer(UnknownFieldRejectionMixin, PresetAwareSerializerMixin, serializers.Serializer):
    """Serializer for TraceLink entity (REQ-L2-RA-001, REQ-002).

    select_related hint: source, target (for N+1 avoidance, REQ-L2-RA-013).

    REQ-002: source_title, target_title, source_type, target_type are included
    in the response so the frontend can render human-readable labels without
    extra round-trips. These fields are optional (read-only) and default to
    empty string / null when the backing entity has no title.
    """

    id = serializers.UUIDField(read_only=True)
    source_id = serializers.UUIDField(
        help_text="Canonical Artifact id of the source endpoint (not the entity PK).",
    )
    target_id = serializers.UUIDField(
        help_text="Canonical Artifact id of the target endpoint (not the entity PK).",
    )
    # #1270: unambiguous aliases of source_id/target_id (read-only), same values.
    source_artifact_id = serializers.UUIDField(read_only=True)
    target_artifact_id = serializers.UUIDField(read_only=True)
    link_type = serializers.CharField(max_length=64)
    # Q1.6: why these two artifacts are connected. Free text on a trust
    # boundary, so sanitized and capped like change_reason (B006/#104) — an
    # unbounded TextField-backed field accepts unbounded payloads.
    rationale = SanitizedCharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text="Why this link exists (optional, free text).",
    )
    # Written only by TraceLinkService.propagate_suspect_status.
    suspect_flagged_at = serializers.DateTimeField(read_only=True, allow_null=True)
    suspect_source_change = serializers.UUIDField(read_only=True, allow_null=True)
    # KI-Vorschlag-als-Zustand spec §5: agent-proposed links carry these
    # instead of a workflow state (a TraceLink has no WorkflowItemState).
    proposed_by = serializers.UUIDField(
        source="proposed_by_id", read_only=True, allow_null=True
    )
    proposed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    proposed_by_label = serializers.SerializerMethodField()

    def get_proposed_by_label(self, obj) -> str:
        """Return the proposing agent's display label, empty for human links.

        Handles both shapes this serializer is fed: the dicts built by
        ``rest_api.views._tracelink_to_dict`` (every REST endpoint — they
        precompute the label so this does not trigger a query per row) and a
        raw ``TraceLink`` instance.
        """
        if isinstance(obj, dict):
            return obj.get("proposed_by_label") or ""
        key = getattr(obj, "proposed_by", None)
        return getattr(key, "agent_label", "") or ""
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
    # UI-P3: soft-deleted endpoints. TraceLinks survive the soft-delete of an
    # endpoint on purpose (audit trail), so the link is still listed here —
    # these flags let the client tell such a link apart from a live one instead
    # of rendering a deleted artifact as a normal neighbour.
    source_is_outdated = serializers.BooleanField(
        read_only=True,
        required=False,
        default=False,
        help_text=(
            "True when the source artifact has been soft-deleted via "
            "workflow outdate(). The link is retained for the audit trail."
        ),
    )
    target_is_outdated = serializers.BooleanField(
        read_only=True,
        required=False,
        default=False,
        help_text=(
            "True when the target artifact has been soft-deleted via "
            "workflow outdate(). The link is retained for the audit trail."
        ),
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



class BlockerWaiverSerializer(serializers.Serializer):
    """One per-finding SE-Auditor waiver on the baseline create payload (GH-821).

    Mirrors ``baseline.waivers.BlockerWaiverRequest``: the caller names the
    finding (``rule_id`` + ``artifact_ids`` exactly as the audit report returned
    them) and justifies accepting *that* deviation. ``reason`` is mandatory —
    an unexplained suppression is not a governance record, and the facade
    rejects a placeholder here as well (see
    ``application.baseline_facade._validate_gate_reason``).

    The scope of a finding is deliberately NOT accepted from the client: the
    waiver is matched against the findings the auditor actually reported, and
    the stored scope is taken from the matched finding. A client cannot
    mis-attribute a waiver.
    """

    rule_id = serializers.CharField(
        max_length=64,
        help_text="SE-Auditor rule being waived, e.g. 'TRACE-P1'.",
    )
    artifact_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
        default=list,
        help_text=(
            "Artifacts the finding concerns, as returned by the audit report "
            "(empty for graph-level findings)."
        ),
    )
    reason = SanitizedCharField(
        max_length=2000,
        allow_blank=False,
        help_text=(
            "Mandatory justification for accepting this single deviation; "
            "recorded on the waiver and in the audit log."
        ),
    )



class BaselineSerializer(
    UnknownFieldRejectionMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """Serializer for Baseline entity (REQ-L2-RA-001).

    ``name`` is optional on create; the view generates a timestamp-based
    default when the UI does not supply one.

    ``entries`` is only present on the detail (retrieve/create) response — the
    list endpoint serialises through :class:`BaselineSummarySerializer` and
    carries no ``entries`` key at all (#1078). Each detail entry may carry a
    full-state ``state`` snapshot (REQ-L2-BL-012).
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
    # GH-821: per-finding waivers. The coarse override above accepts *all*
    # remaining findings at once; this accepts individual ones, each with its
    # own reason, and persists them so a later build does not have to re-state
    # them. Same RBAC gate as override_reason.
    waived_findings = BlockerWaiverSerializer(
        many=True,
        write_only=True,
        required=False,
        default=list,
        help_text=(
            "Per-finding waivers for blocking SE-Auditor findings "
            "(error code SE_AUDITOR_BLOCKED). Each entry accepts one reported "
            "finding; findings that remain unwaived still block the baseline."
        ),
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    entries = BaselineDeltaEntrySerializer(
        many=True, read_only=True, required=False
    )
    # F4.2: optional on create, always echoed read-only. Validation and
    # de-duplication happen in BaselineFacade (single normalisation point for
    # REST and MCP), so the serializer deliberately only enforces the shape.
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64, allow_blank=True),
        required=False,
        default=list,
        help_text="Labels attached to this baseline (F4.2).",
    )



class BaselineSummarySerializer(
    UnknownFieldRejectionMixin, PresetAwareSerializerMixin, serializers.Serializer
):
    """List representation of a Baseline — the detail fields minus ``entries``.

    GitHub #1078 (regression report against closed #585). The list route must
    never emit an ``entries`` key: an empty list reads as "this baseline
    captured nothing", which is a claim the list route cannot support. Using
    :class:`BaselineSerializer` there left the guarantee resting on whether the
    list source happens to lack the attribute — ``_baseline_to_dict`` copies
    ``entries`` whenever it has one, and ``BaselineDetail`` always has one
    (defaulting to ``[]``), so the field could reappear as ``[]`` at any time.

    The field is ABSENT here by construction, whatever the source carries.
    Serialising the entries identically in both representations would mean one
    extra detail query per row on the list, turning a single paged query into
    an N+1 to serve data the list view has never promised. Absence is
    unambiguous: a client renders "load details to see captured items" instead
    of "this baseline captured nothing".

    Only the read fields are declared. The two write-only inputs
    (``override_reason``/``waived_findings``) produce no output and the
    list route never validates a body, so carrying them here would only
    suggest the endpoint accepts writes.
    """

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    scope = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    # F4.2: the list carries the labels too, so a client can render chips
    # without a detail round-trip per row.
    tags = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )



class BaselineTagsRequestSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of ``PUT /api/v1/baselines/{id}/tags/`` (F4.2).

    The replacement set. Individual labels are validated by
    ``BaselineFacade.set_tags`` (format, length, count, de-duplication); this
    serializer only pins the wire shape.

    Guards against silently dropped input (#851): an undeclared key answers
    400 instead of 200, which is the failure class #851 closes.
    ``workspace_id`` is declared even though the route never writes it — the
    persisted workspace comes from the baseline (QR-S09 a) — because the
    ADR-011 authorization seam reads a body ``workspace_id`` as the
    request's target workspace. Declaring it keeps that seam input accepted
    while every genuinely unknown key is still rejected.
    """

    tags = serializers.ListField(
        child=serializers.CharField(max_length=64, allow_blank=True),
        allow_empty=True,
        help_text="Complete replacement set of labels.",
    )
    # Not a write input: only the authorization seam reads it. Declared so it
    # is not mistaken for an unknown key by the #851 guard.
    workspace_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text=(
            "Ignored for persistence — the baseline's own workspace is stored. "
            "Read by the request-scope authorization seam."
        ),
    )



class BaselineTagsResponseSerializer(serializers.Serializer):
    """Read-only response of ``PUT /api/v1/baselines/{id}/tags/`` (F4.2)."""

    id = serializers.UUIDField()
    tags = serializers.ListField(child=serializers.CharField())



class BaselineRollbackItemSerializer(serializers.Serializer):
    """One baseline member as the rollback plan sees it (Plan F F4.4).

    Response-only: the plan is computed by
    ``application.baseline_rollback_service`` and never accepted from a client.
    """

    item_id = serializers.CharField(
        read_only=True,
        help_text=(
            "Delta-index id of the member — the Artifact UUID for "
            "artifact-backed items, the term row id for a glossary entry."
        ),
    )
    artifact_type = serializers.CharField(
        read_only=True,
        allow_blank=True,
        help_text="Canonical ADR item type, or empty when no type is supported.",
    )
    action = serializers.CharField(
        read_only=True,
        help_text=(
            "One of ``restore`` | ``reactivate`` | ``unchanged`` | "
            "``unsupported`` | ``created_since`` (ADR-025 R4)."
        ),
    )
    field_changes = serializers.DictField(
        read_only=True,
        help_text=(
            "``{field: {\"current\": v, \"baseline\": v}}`` for every restorable "
            "field whose value differs."
        ),
    )
    unrestorable_fields = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
        help_text=(
            "Restorable fields the baseline snapshot does not carry. Reported, "
            "never guessed (ADR-025 R4)."
        ),
    )
    current_version = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="Current optimistic-lock version, or null when the row is gone.",
    )



class BaselineRollbackPreviewSerializer(serializers.Serializer):
    """Read-only 200 body of ``GET /api/v1/baselines/{id}/rollback-preview/``.

    Nothing in this payload is writable; the route accepts no body at all.
    """

    baseline_id = serializers.UUIDField(read_only=True)
    summary = serializers.DictField(
        child=serializers.IntegerField(),
        read_only=True,
        help_text=(
            "Counts per action (``restore``, ``reactivate``, ``unchanged``, "
            "``unsupported``, ``created_since``) plus ``links_to_recreate``. "
            "``skipped_links`` carries the number of links that will not be "
            "recreated (an additive key of "
            "``RollbackPlan.summary``)."
        ),
    )
    items = BaselineRollbackItemSerializer(many=True, read_only=True)
    links_to_recreate = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text=(
            "Missing baseline trace links that may be recreated — "
            "``{source_id, target_id, link_type}``."
        ),
    )
    skipped_links = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text=(
            "Missing links that will *not* be recreated, each with a "
            "``reason`` key (system-owned type, unknown type, no snapshot)."
        ),
    )



class BaselineRollbackRequestSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of ``POST /api/v1/baselines/{id}/rollback-request/`` (Plan F F4.4).

    Opens the CCB change request a rollback has to pass through (ADR-025 R2).
    The plan itself is re-derived server-side; the client only names the
    justification and an optional title.

    Guards against silently dropped input (#851): an undeclared key answers
    400 instead of 201.
    """

    change_reason = SanitizedCharField(
        max_length=2000,
        allow_blank=False,
        help_text=(
            "Why the rollback is requested; recorded on the change request "
            "(ADR-025 R2). Mandatory — an unexplained rollback is not a "
            "governance record."
        ),
    )
    title = SanitizedCharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text=(
            "Optional change-request title; defaults to a generated "
            "\"Rollback to baseline '<name>'\"."
        ),
    )



class BaselineRollbackApplyRequestSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of ``POST /api/v1/baselines/{id}/rollback/`` (Plan F F4.4).

    Names the **approved** change request whose plan is executed. The baseline
    comes from the URL, the work from the CR's affected-item set — neither is
    client-controlled.
    """

    change_request_id = serializers.UUIDField(
        help_text=(
            "UUID of the approved change request opened via "
            "/rollback-request/ and linked to this baseline (ADR-025 R2)."
        ),
    )



class BaselineRollbackRequestResponseSerializer(serializers.Serializer):
    """Read-only 201 body of ``POST /api/v1/baselines/{id}/rollback-request/``."""

    change_request_id = serializers.UUIDField(
        read_only=True, help_text="The opened change request (ADR-025 R2)."
    )
    status = serializers.CharField(
        read_only=True,
        help_text=(
            "The change request's workflow state — ``draft`` on creation. It "
            "becomes executable only after the CCB approves it."
        ),
    )
    affected_items = serializers.IntegerField(
        read_only=True,
        help_text=(
            "Number of items the change request binds — the plan's affected-item "
            "set, which ``apply`` re-derives and enforces exactly."
        ),
    )



class BaselineRollbackResultSerializer(serializers.Serializer):
    """Read-only 200 body of ``POST /api/v1/baselines/{id}/rollback/``."""

    restored = serializers.IntegerField(
        read_only=True, help_text="Items written as a new version (ADR-025 R1/R4)."
    )
    reactivated = serializers.IntegerField(
        read_only=True, help_text="Soft-deleted items set back to active (R4)."
    )
    links_recreated = serializers.IntegerField(
        read_only=True, help_text="Missing baseline trace links re-inserted (R4)."
    )
    change_request_status = serializers.CharField(
        read_only=True, help_text="The change request's state after the run."
    )
    skipped = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text=(
            "Everything the run deliberately did not write, as "
            "``{kind, …, reason}``."
        ),
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
