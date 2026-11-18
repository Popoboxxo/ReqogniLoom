"""
COMP-RA-002 DataSerializer — Compatibility facade for the split serializer modules.

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
    InvalidEnumValue,
    InvalidPageSize,
    LOCK_VERSION_HELP_TEXT,
    NormalizedChoiceField,
    PresetAwareSerializerMixin,
    QUERYSET_OPTIMIZATIONS,
    SanitizedCharField,
    SanitizedJSONField,
    StandardPagination,
    TraceLinkPagination,
    UID_HELP_TEXT,
    UNKNOWN_FIELD_MESSAGE,
    UnknownFieldRejectionMixin,
    _ERROR_MESSAGES,
    apply_queryset_optimizations,
    build_error_response,
    detect_lang,
    extract_preset_tier,
    get_error_message,
    normalize_preset_blob,
    reject_unknown_fields,
    unknown_field_errors,
)
from .serializers_entity import (
    ArchitectureAllocationCoverageRequirementSerializer,
    ArchitectureAllocationCoverageSerializer,
    ArchitectureElementSerializer,
    ArtifactSerializer,
    NeedValidationCoverageEntrySerializer,
    NeedValidationCoverageResponseSerializer,
    NeedValidationCoverageSummarySerializer,
    NeedValidationCoverageTestCaseSerializer,
    RequirementSerializer,
    StakeholderNeedSerializer,
    TestCaseSerializer,
    TestStepListField,
)
from .serializers_trace_baseline import (
    BaselineDeltaEntrySerializer,
    BaselineDiffSerializer,
    BaselineRollbackApplyRequestSerializer,
    BaselineRollbackItemSerializer,
    BaselineRollbackPreviewSerializer,
    BaselineRollbackRequestResponseSerializer,
    BaselineRollbackRequestSerializer,
    BaselineRollbackResultSerializer,
    BaselineSerializer,
    BaselineSummarySerializer,
    BaselineTagsRequestSerializer,
    BaselineTagsResponseSerializer,
    BlockerWaiverSerializer,
    DiffItemSerializer,
    FieldChangeSerializer,
    ImpactNodeSerializer,
    ResolvedArtifactSerializer,
    SimilarRequirementSerializer,
    SimilarTraceLinkSerializer,
    TraceLinkSerializer,
    TracePathSerializer,
)
from .serializers_governance import (
    AdrSerializer,
    BulkTransitionRequestSerializer,
    BulkTransitionResponseSerializer,
    BulkTransitionedSerializer,
    BulkUpdateEntrySerializer,
    BulkUpdateErrorSerializer,
    BulkUpdateRequestSerializer,
    BulkUpdateResponseSerializer,
    BulkUpdateUpdatedSerializer,
    ChangeRequestSerializer,
    DocumentReadingCapabilitiesSerializer,
    DocumentReadingChapterSerializer,
    DocumentReadingFieldSerializer,
    DocumentReadingLockedSerializer,
    DocumentReadingProjectionSerializer,
    DocumentReadingSerializer,
    DocumentSerializer,
    GoalSerializer,
    IssueSerializer,
    MainGoalSerializer,
    MilestoneBindBaselineSerializer,
    MilestoneRecordAuditSerializer,
    MilestoneSerializer,
    RiskSerializer,
    TestRunResultBulkSerializer,
    TestRunResultSerializer,
    TestRunSerializer,
    WorkItemSerializer,
    WorkflowDefinitionSerializer,
    WorkspaceSerializer,
)
from .serializers_io import (
    CommentSerializer,
    CsvImportCountsSerializer,
    CsvImportItemCauseSerializer,
    CsvImportItemSerializer,
    CsvImportReportSerializer,
    CsvImportRowErrorSerializer,
    GlossaryTermSerializer,
    IcdParameterSerializer,
    NotificationSerializer,
    SuggestionSerializer,
    UserProfileSerializer,
)



__all__ = [
    "QUERYSET_OPTIMIZATIONS",
    "AdrSerializer",
    "ArchitectureElementSerializer",
    "ArtifactSerializer",
    "BaselineDeltaEntrySerializer",
    "BaselineDiffSerializer",
    "BaselineSerializer",
    "BaselineSummarySerializer",
    "CommentSerializer",
    "CsvImportCountsSerializer",
    "CsvImportItemCauseSerializer",
    "CsvImportItemSerializer",
    "CsvImportReportSerializer",
    "CsvImportRowErrorSerializer",
    "CustomFieldsSerializerMixin",
    "DiffItemSerializer",
    "DocumentSerializer",
    "FieldChangeSerializer",
    "GlossaryTermSerializer",
    "InvalidPageSize",
    "IssueSerializer",
    "NotificationSerializer",
    "PresetAwareSerializerMixin",
    "RequirementSerializer",
    "RiskSerializer",
    "StakeholderNeedSerializer",
    "StandardPagination",
    "SuggestionSerializer",
    "TestCaseSerializer",
    "TestRunResultBulkSerializer",
    "TestRunResultSerializer",
    "TestRunSerializer",
    "TraceLinkPagination",
    "TraceLinkSerializer",
    "UnknownFieldRejectionMixin",
    "UserProfileSerializer",
    "WorkflowDefinitionSerializer",
    "WorkspaceSerializer",
    "apply_queryset_optimizations",
    "build_error_response",
    "detect_lang",
    "extract_preset_tier",
    "get_error_message",
    "normalize_preset_blob",
]
