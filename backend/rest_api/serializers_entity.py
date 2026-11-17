"""
COMP-RA-002 DataSerializer — serializers_entity — extracted from rest_api/serializers.py (content-sensible split; public import surface preserved by the facade)..

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
    AcceptanceCriteriaListField,
    ArtifactSystemFieldsSerializerMixin,
    ClientUidRejectionMixin,
    CustomFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    LOCK_VERSION_HELP_TEXT,
    PresetAwareSerializerMixin,
    SanitizedCharField,
    UID_HELP_TEXT,
)




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
    # P1: fractional sibling order, exposed so a reorder client can compare
    # positions without a second lookup.
    sort_key = serializers.CharField(read_only=True, allow_null=True)
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="modified_at")



class RequirementSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for Requirement entity (REQ-L2-RA-001, REQ-L3-RF003-005).

    REQ-L3-RF003-005: Type-dependent fields (complexity_fibonacci,
    verification_method) are included in the serializer but conditionally rendered
    in to_representation() based on the requirement type.

    REQ-L2-RF-025: Includes uid for stable identification.

    select_related hint: artifact, artifact__workspace (for queryset optimization).
    """

    # REQ-143 / Datenmodell-Konsolidierung: `status` is no longer a model
    # column. It is resolved from WorkflowItemState by the mixin, which keeps
    # the wire key and its vocabulary identical (Decision D-1).
    workflow_item_type = "Requirement"

    id = serializers.UUIDField(
        read_only=True,
        help_text="Entity PK (the Requirement row). Use it for Requirement API paths.",
    )
    workspace_id = serializers.UUIDField(required=True)
    # Issue #413/#416: id of the owning Artifact. TraceLink endpoints are
    # Artifact ids, never Requirement ids, so without this field the UI cannot
    # tell whether a link endpoint *is* the requirement it is rendering — the
    # traceability list fell back to raw UUIDs and the requirement editor's
    # hierarchy panel resolved every link back to the artifact itself.
    # ``_dto_from_orm`` has always supplied the value; the serializer just
    # never declared the field, so DRF dropped it. Read-only, nullable,
    # matching StakeholderNeedSerializer / ArchitectureElementSerializer.
    artifact_id = serializers.UUIDField(
        read_only=True,
        allow_null=True,
        help_text=(
            "Canonical Artifact id. TraceLink endpoints use this id, not `id`; "
            "join trace links against `artifact_id` (#1270)."
        ),
    )
    # #1261: the stable global UUID, exposed as a read-only attribute. Same value
    # as artifact_id under a name that reads as identity — a workspace-local
    # `uid` is reassigned on ReqIF import, this UUID is not. Never settable.
    global_uuid = serializers.SerializerMethodField()

    def get_global_uuid(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj.get("artifact_id")
        return getattr(obj, "artifact_id", None)

    parent_id = serializers.UUIDField(required=False, allow_null=True)
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    # #871/#583 (IEEE 29148 §5.2.6): justification and origin of the requirement.
    rationale = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    source = SanitizedCharField(allow_blank=True, default="", max_length=255)
    # #43: acceptance_criteria describes when the requirement is considered fulfilled.
    acceptance_criteria = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    category = serializers.CharField(max_length=64, allow_blank=True, default="")
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
    #
    # ADR-005: exposed but then made `read_only=True` again, for a different
    # reason. `level` is a **derived** field: it is recomputed from the
    # hierarchy on every hierarchy change
    # (`traceability.audit.hierarchy.recompute_requirement_levels`), and
    # `RequirementService` no longer takes a `level` parameter. It stays
    # declared and readable because it is the only L4 filter TRACE-P5, ARCH-003
    # and VERIF-P8 have (`traceability/audit/hierarchy.py` has no L4 concept of
    # its own), and because the export contract carries it
    # (`application/export_service.py`, `application/requirement_bundle_service.py`).
    # A client that sends it gets a field-level 400 from
    # `RequirementViewSet.partial_update` / `.create` — never a silent drop,
    # which is the same failure class this wave closes for `parent_id`.
    level = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        min_value=1,
        help_text=(
            "P2: permanent integer alias of the requirement's position in the "
            "workspace tier ladder (position + 1). DERIVED and read-only; NULL "
            "when the ladder does not determine a tier. The old 1..4 V-model "
            "assumption is gone: a ladder may have any number of entries."
        ),
    )
    tier_key = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="P2: stable tier key (the workspace ladder entry).",
    )
    # ADR-028 D11: the tier pinned when the requirement was released. Read-only;
    # the release path is the only writer.
    released_tier_key = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="ADR-028 D11: tier_key pinned at release time.",
    )
    # P2 (V5 naming layer): the display name of `tier_key`. Resolved from the
    # workspace ladder map the view puts into the serializer context — one
    # ladder read per request, never a query per requirement. A serialisation
    # whose context carries no map (nested/secondary serializers) answers
    # `null` instead of reading the ladder itself.
    tier_name = serializers.SerializerMethodField(
        help_text=(
            "P2: display name of `tier_key` from the workspace tier ladder "
            "(`en` → `de` → the key itself). Null when the requirement has no "
            "tier or the payload was built without a ladder map."
        )
    )
    allocation_intent = serializers.ChoiceField(
        choices=["allocated", "not_allocatable", "unassigned"],
        required=False,
        help_text=(
            "P2: why the requirement is (not) allocated. 'not_allocatable' "
            "requires no existing allocation."
        ),
    )
    # #1289: provenance of `level`. Read-only, additive to the wire contract.
    level_source = serializers.CharField(
        read_only=True,
        help_text=(
            "'derived' (recomputed from the hierarchy) or 'manual' (an explicit "
            "override set via `level_override`)."
        ),
    )
    # #1289: the explicit manual override. Distinct from `level` so the
    # ADR-005 contract ("`level` is derived, a differing value is refused")
    # stays intact — a client that wants to force a level sends this field
    # instead of `level`. Write-only: `level_source` is the read projection.
    level_override = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=4,
        write_only=True,
        help_text=(
            "Manual override of the derived V-model level (1..4); null clears "
            "the override and restores the derived value. #1289."
        ),
    )
    # #1288: the structured acceptance criteria list. Readable on the main
    # Requirement payload and, since #1609, writable there too: the view
    # persists it through ``RequirementService.set_acceptance_criteria`` (the
    # same contract the dedicated ``.../acceptance-criteria/{index}/`` endpoint
    # uses). It used to be ``read_only``, so a PATCH carrying the list answered
    # 200 and silently dropped it. Individual items are still addressable at
    # ``.../acceptance-criteria/{index}/``.
    acceptance_criteria_items = AcceptanceCriteriaListField(
        required=False,
        help_text=(
            "Ordered acceptance criteria {text, fulfilled, evidence_ref} (#1288). "
            "Writable: a PATCH/POST replaces the whole list (#1609)."
        ),
    )
    # Issue [U2, systemaudit 2026-09-02]: the model field and its propagation
    # logic (TraceLinkService.propagate_suspect_status) already existed;
    # only the serializer never declared it, so DRF silently dropped it from
    # every response. Read-only: only propagate_suspect_status may set it.
    suspect = serializers.BooleanField(read_only=True)
    uid = serializers.CharField(
        max_length=64,
        read_only=True,
        required=False,
        allow_null=True,
        help_text=UID_HELP_TEXT,
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

    def get_atomicity_warning(self, obj: Any) -> list[str] | None:
        from application.requirement_service import detect_non_atomic_terms

        # `obj` is a plain dict from `_dto_from_orm()` on every real call site
        # (see rest_api/views.py) rather than a model/DTO instance — dicts have
        # no `.title` attribute, so `getattr` alone would silently always
        # return "".
        title = obj.get("title", "") if isinstance(obj, dict) else getattr(obj, "title", "")
        return detect_non_atomic_terms(title or "") or None

    def get_tier_name(self, obj: Any) -> str | None:
        """Resolve ``tier_name`` from the view-supplied ladder map (P2, V5).

        The view puts ``{tier_key: display_name}`` into ``context['tier_names']``
        after exactly one ``TierLadderService.get()`` per request, so this
        method never queries — that is what keeps the list endpoint's query
        count independent of the number of requirements. Without the map
        (nested serializers, direct serializer unit tests) the answer is
        ``None`` rather than a per-row ladder read.
        """
        tier_key = (
            obj.get("tier_key")
            if isinstance(obj, dict)
            else getattr(obj, "tier_key", None)
        )
        if not tier_key:
            return None
        names = (getattr(self, "context", None) or {}).get("tier_names")
        if not isinstance(names, dict):
            return None
        return names.get(tier_key)

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
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for StakeholderNeed entity.

    Represents the user's problem space and needs.
    """

    # REQ-143 / Datenmodell-Konsolidierung: see RequirementSerializer.
    workflow_item_type = "StakeholderNeed"

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
    moscow_priority = serializers.ChoiceField(
        choices=['Must', 'Should', 'Could', "Won't"],
        required=False,
        allow_null=True,
        help_text="MoSCoW priority",
    )
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
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



class NeedValidationCoverageTestCaseSerializer(serializers.Serializer):
    """One validating TestCase row of a need (#878)."""

    id = serializers.CharField(help_text="Artifact id of the TestCase.")
    title = serializers.CharField(allow_blank=True)
    latest_result = serializers.CharField(
        help_text=(
            "Display label of the newest TestRunResult, or 'Not Run' when the "
            "test case was never executed (same shape as the VCRM)."
        )
    )



class NeedValidationCoverageEntrySerializer(serializers.Serializer):
    """One StakeholderNeed row of the validation coverage report (#878)."""

    need_id = serializers.CharField()
    uid = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    test_cases = NeedValidationCoverageTestCaseSerializer(many=True)



class NeedValidationCoverageSummarySerializer(serializers.Serializer):
    """Summary block of the validation coverage report (#878)."""

    total = serializers.IntegerField()
    covered = serializers.IntegerField()
    percentage = serializers.FloatField()
    pending_ai_review = serializers.IntegerField(
        help_text="Number of needs covered only by an unreviewed AI TestCase."
    )



class NeedValidationCoverageResponseSerializer(serializers.Serializer):
    """Response contract of ``GET /api/v1/needs/validation-coverage/`` (#878).

    The StakeholderNeed counterpart of the Requirement coverage report: the
    summary plus one row per active need, ordered by ``uid`` then ``need_id``
    (D-SORT). A need counts as validated when at least one ``validates`` link
    comes from a live TestCase that counts as verification evidence (#424).
    """

    summary = NeedValidationCoverageSummarySerializer()
    needs = NeedValidationCoverageEntrySerializer(many=True)



class ArchitectureAllocationCoverageRequirementSerializer(serializers.Serializer):
    """One unallocated Requirement row of the allocation coverage report (#1883)."""

    id = serializers.UUIDField(read_only=True, help_text="Requirement id.")
    uid = serializers.CharField(
        read_only=True,
        allow_blank=True,
        allow_null=True,
        help_text="Stable, workspace-unique Requirement uid (may be empty).",
    )
    title = serializers.CharField(read_only=True, allow_blank=True)



class ArchitectureAllocationCoverageSerializer(serializers.Serializer):
    """Response contract of ``GET /api/v1/architecture/{id}/allocation-coverage/``.

    GH-1883: the route was documented as returning an
    ``ArchitectureElement`` — the body has always been this coverage report
    instead, and ``coverage_ratio`` carried a 0…100 percentage, not a ratio.
    The field is published as ``coverage_percent`` to match the house naming of
    ``MetricsCoverage.coverage_percent``. Every field is read-only: the route
    takes its input from the path only.
    """

    allocated_count = serializers.IntegerField(
        read_only=True,
        help_text="Requirements allocated directly to this ArchitectureElement.",
    )
    not_allocatable_count = serializers.IntegerField(
        read_only=True,
        help_text=(
            "Requirements with allocation_intent='not_allocatable'. Deliberately "
            "excluded from the coverage denominator, never reported as a gap."
        ),
    )
    coverage_percent = serializers.FloatField(
        read_only=True,
        help_text=(
            "Coverage in percent (0…100): allocated_count / allocatable "
            "Requirements * 100. Not a 0…1 ratio."
        ),
    )
    unallocated_requirements = ArchitectureAllocationCoverageRequirementSerializer(
        many=True,
        read_only=True,
        help_text="Workspace Requirements not allocated to this element.",
    )



class ArchitectureElementSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for ArchitectureElement entity (REQ-L2-RA-001, REQ-L3-RF004-004).

    REQ-L1-044: ``parent_id`` changes run through the rigor-gated
    hierarchy invariants (I1-I3) in validate().  On update, the view
    provides ``context={"element_id": pk}`` so the validator can resolve
    the element and its workspace.

    REQ-L1-058 AC2: level annotation via ``ArchitectureElement.annotate_levels()``
    (recursive-CTE, bulk) avoids N+1 queries. Expects pre-annotated 'level' field.

    REQ-L3-RF004-004: Includes ASIL level and Make-or-Buy decision fields.
    REQ-L2-RF-025 AC3: Includes uid for stable identification.

    Epic #934 WS1: ``WorkflowStateSerializerMixin`` adds the read-only
    ``status`` system attribute (``editable="workflow"`` on every bootstrapped
    definition) that the read projection previously omitted, so the Attribute
    Usability Contract's R check holds on REST as well.
    """

    #: ``WorkflowItemState.item_type`` value for this serializer (the mixin).
    workflow_item_type = "ArchitectureElement"

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
        help_text=UID_HELP_TEXT,
    )
    # ``expected_version`` comes from ExpectedVersionSerializerMixin — the
    # inline declaration this replaces was the only one in the codebase.
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



class TestStepListField(serializers.ListField):
    """Typed test steps with legacy read/write normalisation (Issue #1564).

    Reads always return the typed shape. Writes accept the legacy
    ``{step, expected_result}`` form (and the typed one) and validate the
    result, so an old MCP/UI client keeps working while the stored data moves
    to the typed form.
    """

    child = serializers.DictField()
    _normalized_legacy = False

    def _testcase_id(self):
        context = getattr(self, "context", {}) or {}
        return context.get("testcase_id")

    def to_internal_value(self, data):
        normalized = normalize_steps(data, testcase_id=self._testcase_id())
        validate_steps(normalized)
        return normalized

    def to_representation(self, value):
        normalized = normalize_steps(value, testcase_id=self._testcase_id())
        self._normalized_legacy = normalized != (value or [])
        return normalized



class TestCaseSerializer(
    ClientUidRejectionMixin,
    WorkflowStateSerializerMixin,
    CustomFieldsSerializerMixin,
    ArtifactSystemFieldsSerializerMixin,
    ExpectedVersionSerializerMixin,
    PresetAwareSerializerMixin,
    serializers.Serializer,
):
    """Serializer for TestCase entity (REQ-L2-RA-001)."""

    # REQ-165/REQ-166 (CR-08) / Datenmodell-Konsolidierung: see
    # RequirementSerializer. Neither create_test_case() nor update_test_case()
    # (application/test_service.py) accept a client-supplied status, so this
    # matches the already-correct behavior instead of advertising a writable
    # field that PATCH has always ignored. Change the lifecycle state via
    # POST /api/v1/testcases/{id}/transitions/.
    workflow_item_type = "TestCase"

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(required=True)
    # #399 (MAJOR-1): the backing Artifact id, distinct from the TestCase pk.
    # `GET /artifacts/{id}/baseline-membership/` and the `affected_item_ids`
    # prefill key on Artifact ids (#413/#416 for Requirement); without this
    # field the UI has no way to name the artifact it must ask about and sent
    # the entity pk instead. `_test_to_dict` supplies the value. Read-only.
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = SanitizedCharField(max_length=500)
    description = SanitizedCharField(allow_blank=True, default="", max_length=20000)
    uid = serializers.CharField(read_only=True, allow_null=True, help_text=UID_HELP_TEXT)
    suspect = serializers.BooleanField(required=False, default=False)
    # SysEng 2.0 N5 (test.derive_from_requirement): test steps, previously
    # persisted on the model but not exposed through the API.
    steps = TestStepListField(required=False, default=list)
    # Additive read hint: true when the stored row still carried the legacy
    # shape and the response is the normalized form (#1564).
    steps_legacy_normalized = serializers.SerializerMethodField()
    # C-1 (attribute-definitions Task 22 review round 1): `TestCase.test_type`
    # (persistence/migrations/0041_add_testcase_test_type.py, B6a) is a real,
    # writable model column with TestCaseType choices — the bootstrap
    # introspects it as an editable enum attribute (bootstrap_attribute_
    # definitions.py: CLASSIFICATION_FIELDS + _attribute_type's
    # `choices` -> "enum" branch), so the definition-driven
    # TestCaseArtifactForm renders it as a select and PATCHes it back. This
    # serializer never declared it, so the unknown-key guard 400'd
    # every save the moment a user touched the field.
    #
    # #816: this field is now the ONLY representation of a test case's type —
    # the deprecated Title-case value tagged onto `artifact.artifact_type` is
    # gone (migration 0093). Create forwards the value as the service's
    # `test_type_value` alias, which takes precedence over the service's
    # `unit` default and keeps `null` meaning "unspecified" (#953).
    test_type = serializers.ChoiceField(
        choices=TestCaseType.choices, required=False, allow_null=True
    )
    def get_steps_legacy_normalized(self, obj: Any) -> bool:
        """True when the stored row was still legacy and the response is typed."""
        return bool(getattr(self.fields.get("steps"), "_normalized_legacy", False))

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
    # GH-829: the unknown-key guard (then a TestCaseSerializer.validate() copy
    # of #580, now the shared UnknownFieldRejectionMixin.to_internal_value,
    # #851) rejected every PATCH carrying change_reason with HTTP 400 because
    # the field was never declared here — and even past that guard, DRF would
    # have silently dropped it from validated_data. Write-only + optional,
    # mirroring StakeholderNeedSerializer.change_reason: the service records it
    # on the audit trail, so it never belongs in the response body.
    change_reason = SanitizedCharField(
        write_only=True, required=False, allow_blank=True, max_length=2000
    )
    # #424: provenance of the content. Three-valued on the model, but ``unknown``
    # is system/migration-only and deliberately NOT offered here — see
    # ``TestCaseOrigin``. Immutable after creation (rejected in validate()).
    origin = serializers.ChoiceField(
        choices=[TestCaseOrigin.MANUAL, TestCaseOrigin.AI_GENERATED],
        required=False,
        default=TestCaseOrigin.MANUAL,
        help_text=(
            "Provenance of the test-case content: 'manual' (default) or "
            "'ai_generated'. Immutable after creation."
        ),
    )
    # #424: read-only in the representation; set via POST .../review/ (or
    # TestService.mark_reviewed). Writing it here is rejected in validate() —
    # reading ``initial_data``, because DRF discards a read-only field before
    # validate() ever sees it (#851 silent-no-op class).
    reviewed = serializers.BooleanField(read_only=True)
    # #402: off-nominal categorisation (nominal | off_nominal). Editable after
    # creation; `off_nominal` marks negative/boundary cases.
    scenario_kind = serializers.ChoiceField(
        choices=ScenarioKind.choices,
        required=False,
        default=ScenarioKind.NOMINAL,
        help_text="Test-case category: 'nominal' (default) or 'off_nominal'.",
    )
    version = serializers.IntegerField(
        read_only=True, help_text=LOCK_VERSION_HELP_TEXT
    )
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject post-creation writes to the immutable provenance fields (#424).

        Only enforced on update. The spec's canonical instance check
        (``self.instance is not None``) is widened by ``self.partial`` because
        the real view (`TestCaseViewSet.partial_update`) builds this serializer
        without an ``instance`` (it validates field names first and only loads
        the row inside the service call) — an instance-only gate would never
        fire there and the rejection would be a silent no-op, which is exactly
        the #851 class this finding is about. ``create`` constructs the
        serializer with ``partial=False``, so the create contract is untouched.

        ``reviewed`` is read-only on this serializer, so DRF drops it from
        ``attrs`` *before* ``validate()`` runs — checking ``attrs`` would
        silently accept and ignore the write. The check therefore reads
        ``self.initial_data``, the raw request body.
        """
        attrs = super().validate(attrs)
        if self.instance is None and not self.partial:
            return attrs

        errors: dict[str, Any] = {}
        if "origin" in attrs:
            errors["origin"] = "origin is immutable after creation"
        supplied = getattr(self, "initial_data", None)
        if isinstance(supplied, dict) and "reviewed" in supplied:
            errors["reviewed"] = (
                "reviewed is set via POST /api/v1/testcases/{id}/review/"
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
