"""
COMP-RA-001 HttpEndpointController — Compatibility facade for the split DRF view modules.

leaf_id : COMP-RA-001
req_id  : REQ-L2-RA-001 (CRUD endpoints), REQ-L2-RA-003 (performance),
          REQ-L2-RA-007 (audit-log delegation), REQ-L2-RA-009 (error format),
          REQ-L2-RA-012 (no business logic)
          REQ-L3-RA001-001 through REQ-L3-RA001-004

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-001_HttpEndpointController/L3_COMP-RA-001_HttpEndpointController_Architecture.md

Interfaces:
  IF-RA-EXT-IN-001/002  <- HTTP requests from API clients / ReactFrontend
  IF-RA-EXT-OUT-001     -> JSON responses
  IF-RA-EXT-OUT-005     -> ApplicationService (single entry point, ADR-01)
  IF-RA-INT-001         -> COMP-RA-003 AuthEnforcer (via DRF auth classes in settings)
  IF-RA-INT-002         -> COMP-RA-004 PresetGuard (PresetGateMixin)
  IF-RA-INT-003         <-> COMP-RA-002 DataSerializer (serializers)

Design decisions:
  - DRF ViewSets per entity; DRF Router for URL registration.
  - No business logic in views (REQ-L3-RA001-004).
  - All ApplicationService exceptions mapped to HTTP codes without stack-trace leakage.
  - Audit context is passed through to ApplicationService via AuthContext
    (actor identity, operation type carried implicitly by service method).
  - Queryset optimized with select_related/prefetch_related (REQ-L2-RA-013).
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import ProtectedError, QuerySet
from django.http import Http404, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiRequest,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# #1240: the AI-derivation flows signal an unparseable provider response with
# this dedicated exception. It is registered in the exact-type maps below so the
# generic ``except Exception`` branch on those routes answers a described 502
# instead of an opaque 500. #1416 adds the cause-specific subclasses: a provider
# timeout (504 LLM_TIMEOUT), an unavailable provider (503 LLM_UNAVAILABLE) and
# an exhausted daily token budget (429 LLM_TOKEN_LIMIT_EXCEEDED).
from application.ai_derivation_service import (
    LlmProviderTimeoutError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmTokenLimitExceededError,
)
from application.artifact_attribute_gateway import (
    ArtifactAttributeGateway,
    AttributeValues,
    artifact_system_fields,
    transport_field_names,
)
from application.base import (
    AdoptionHashMismatchError,
    AllocationConflictError,
    ReleaseStateError,
    ReleaseTooLargeError,
    WorkflowFrozenError,
    AnchorsPresentError,
    DocumentGateFailedError,
    FieldFrozenError,
    ProducerContextRequiredError,
    SuppressionExpiredError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
# Plan F F4.4 (PR-F11b): the transport half of the additive rollback. The
# service itself is merged (PR-F11a) and is used unchanged — this import only
# adds the error classes to the exact-type HTTP maps below.
from application.baseline_rollback_service import (
    BaselineRollbackService,
    RollbackAlreadyAppliedError,
    RollbackConflictError,
    RollbackEmptyError,
    RollbackError,
    RollbackForbiddenError,
    RollbackNotApprovedError,
    RollbackPlanStaleError,
    RollbackTooLargeError,
)
from application.change_request_service import ChangeRequestDTO
# R3 batch write (docs/superpowers/plans/2026-11-15-document-view-on-document.md):
# one transaction over several artifacts; the entries are built from the
# validated request body, so the service never sees transport data.
from application.bulk_update_service import (
    BulkEntry,
    BulkUpdateService,
    MAX_ENTRIES as MAX_BULK_ENTRIES,
    MAX_TRANSITION_IDS as MAX_BULK_TRANSITION_IDS,
)
# R1 reading view (docs/superpowers/plans/2026-11-15-document-view-on-document.md):
# one read object, no write path.
from application.document_reading_service import DocumentReadingService
# Plan F F2-T5 (PR-F18a): the Document artifact's single write entry point
# (ADR-01). Exposed over REST here; MCP follows in F2-T6.
from application.document_service import DocumentService
from application.goal_service import GoalService
from application.import_idempotency import (
    IdempotencyConflict,
    compute_fingerprint,
)
from application.import_idempotency import (
    abort as abort_idempotency_key,
)
from application.import_idempotency import (
    begin as begin_idempotency_key,
)
from application.import_idempotency import (
    finalize_success as finalize_idempotency_success,
)
from application.main_goal_service import MainGoalService
# Plan B B6-T2 (#879): the Milestone write entry point (ADR-01).
from application.milestone_service import MilestoneService
# Plan F F3-T5: the WorkItem artifact's single write entry point (ADR-01).
from application.work_item_service import WorkItemService
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.requirement_bundle_service import (
    BundleDepthExceededError,
    RequirementBundleQueryService,
    describe_attribute_schema,
)
from application.requirement_update import RequirementUpdate
from application.services import (
    AdrService,
    ArchitectureService,
    ArtifactDiffService,
    ArtifactService,
    BaselineFacade,
    BaselineGateBlockedError,
    BaselineTagValidationError,
    ChangeRequestService,
    ExportService,
    GlossaryService,
    ImportService,
    IssueService,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    PgVectorUnavailableError,
    ReqifExportService,
    ReqifImportResult,
    ReqifImportService,
    ReqifParseError,
    RequirementService,
    RiskService,
    SearchService,
    TestRunService,
    TestService,
    TraceLinkService,
    ValidationError,
    WorkflowFacade,
    WorkspaceService,
)

# GH-914: the trace-link proposal guard raises a service-local exception, like
# BundleDepthExceededError above — imported from its own module rather than
# re-exported through application.services (which only carries the shared
# persistence-layer exceptions).
from application.trace_link_service import AgentSelfConfirmError

# #1084: service-local exception of the workspace hard delete, imported from its
# own module for the same reason as AgentSelfConfirmError above.
from application.workspace_service import BaselineImmutabilityError
from audit.query import AuditLogQuery, AuditQueryFilters
from link_types.defaults import (
    default_decomposition_link_type,
    default_trace_link_type,
)
from presets.exceptions import CrossTenantWorkspaceError
from reqogniloom.health import sunset_header_value
from rest_api.auth_enforcer import get_auth_context
from rest_api.mixins import (
    ETagMixin,
    FreeTextSanitizationMixin,
    IfMatchMismatch,
    InvalidIfMatch,
    WorkflowTransitionsMixin,
)
from rest_api.not_found import ROUTE_NOT_FOUND_MESSAGE

logger = logging.getLogger(__name__)
# INT-06 (findings 075/077/090): the shared error-response schema for the
# documented error cases on the audited endpoints.
from rest_api.openapi import ErrorResponseSerializer
from rest_api.preset_guard import PresetError, PresetGateMixin
from rest_api.query_params import (
    parse_bool_param,
    parse_change_reason,
    parse_include_deleted,
    parse_int_param,
    parse_uuid_param,
    parse_workspace_id,
    reject_unknown_query_params,
    require_non_empty_param,
)
from rest_api.platform_schema_serializers import (
    AllocationListResponseSerializer,
    AttributeSchemaEntrySerializer,
    BundleCompressionStatusSerializer,
    ConsistencyStatusSerializer,
    GroupCreateRequestSerializer,
    GroupListResponseSerializer,
    GroupMemberAddRequestSerializer,
    GroupMemberMoveRequestSerializer,
    GroupMemberRemoveRequestSerializer,
    GroupMembersResponseSerializer,
    GroupMoveMemberResponseSerializer,
    GroupSerializer,
    RequirementHistoryResponseSerializer,
)
from rest_api.schema import ReqLoAutoSchema
from rest_api.serializers import (
    AdrSerializer,
    ArchitectureAllocationCoverageSerializer,
    ArchitectureElementSerializer,
    ArtifactSerializer,
    BaselineDiffSerializer,
    BaselineRollbackApplyRequestSerializer,
    BaselineRollbackPreviewSerializer,
    BaselineRollbackRequestResponseSerializer,
    BaselineRollbackRequestSerializer,
    BaselineRollbackResultSerializer,
    BaselineSerializer,
    BaselineSummarySerializer,
    BaselineTagsRequestSerializer,
    BaselineTagsResponseSerializer,
    BulkTransitionRequestSerializer,
    BulkTransitionResponseSerializer,
    BulkUpdateRequestSerializer,
    BulkUpdateResponseSerializer,
    ChangeRequestSerializer,
    CsvImportReportSerializer,
    DocumentSerializer,
    DocumentReadingSerializer,
    GlossaryTermSerializer,
    GoalSerializer,
    ImpactNodeSerializer,
    IssueSerializer,
    MainGoalSerializer,
    MilestoneBindBaselineSerializer,
    MilestoneRecordAuditSerializer,
    MilestoneSerializer,
    NeedValidationCoverageResponseSerializer,
    RequirementSerializer,
    ResolvedArtifactSerializer,
    RiskSerializer,
    SimilarRequirementSerializer,
    SimilarTraceLinkSerializer,
    StakeholderNeedSerializer,
    StandardPagination,
    TestCaseSerializer,
    TestRunResultBulkSerializer,
    TestRunResultSerializer,
    TestRunSerializer,
    TraceLinkPagination,
    TraceLinkSerializer,
    TracePathSerializer,
    WorkflowDefinitionSerializer,
    WorkItemSerializer,
    WorkspaceSerializer,
    build_error_response,
    detect_lang,
    extract_preset_tier,
    reject_unknown_fields,
)

from .views_common import (
    BaseEntityViewSet,
    MalformedUuidInPath,
    UnknownDetailRoute,
    _DERIVATION_MODES,
    _DERIVATION_POLICIES,
    _ETAG_RESPONSE_HEADER,
    _EXC_TO_CODE,
    _EXC_TO_HTTP,
    _IF_MATCH_PARAMETER,
    _MESSAGE_NOT_SURFACEABLE,
    _PRECONDITION_FAILED_RESPONSE,
    _SOFT_DELETE_CHANGE_REASON_PARAMETER,
    _SYSTEM_FIELD_NAMES,
    _artifact_custom_fields,
    _parse_derivation_mode_policy,
    _resolve_change_reason,
    _service_error_response,
    _special_route_if_match_error,
    list_schema,
    soft_delete_schema,
)
from .views_entity_core import (
    ArchitectureElementViewSet,
    ArtifactBulkTransitionView,
    ArtifactBulkUpdateView,
    ArtifactViewSet,
    DocumentViewSet,
    RequirementHistoryView,
    RequirementViewSet,
    StakeholderNeedViewSet,
    TestCaseViewSet,
    WorkItemViewSet,
    _JsonOnlyContentNegotiation,
    _VIEW_FORMAT_MARKDOWN,
    _WORK_ITEM_RESUME_RESPONSE,
    _WORK_ITEM_TRANSITION_REQUEST,
    _WORK_ITEM_TRANSITION_RESPONSE,
    _arch_to_dict,
    _artifact_to_dict,
    _baseline_drift_summary,
    _document_to_dict,
    _dto_from_orm,
    _need_to_dict,
    _query_flag,
    _service_warnings,
    _test_to_dict,
    _work_item_to_dict,
)
from .views_trace_baseline import (
    BaselineViewSet,
    TraceLinkViewSet,
    TraceabilityViewSet,
    _BASELINE_PRESET_404,
    _BASELINE_TAG_PARAMETER,
    _BASELINE_WORKSPACE_ID_PARAMETER,
    _BaselineAutoSchema,
    _baseline_to_dict,
    _build_baseline_diff_items,
    _caller_may_read_workspace,
    _collect_artifact_names,
    _enrich_tracelink_titles,
    _resolve_artifact_titles,
    _resolve_baseline_diff_ids,
    _rollback_plan_to_dict,
    _rollback_result_to_dict,
    _tracelink_to_dict,
    _workspace_of_artifact,
)
from .views_governance import (
    AdrViewSet,
    ChangeRequestViewSet,
    GoalViewSet,
    IssueViewSet,
    MainGoalViewSet,
    MilestoneViewSet,
    RiskViewSet,
    TestRunViewSet,
    WorkflowDefinitionViewSet,
    WorkspaceViewSet,
    _FALSE_TOKENS,
    _TRUE_TOKENS,
    _WORKSPACE_LOCKS_RESPONSE,
    _adr_to_dict,
    _apply_list_query_limit,
    _apply_list_query_ordering,
    _apply_list_query_params,
    _apply_list_query_search,
    _apply_list_query_source,
    _apply_list_query_status,
    _coerce_bool,
    _cr_to_dict,
    _goal_to_dict,
    _issue_to_dict,
    _main_goal_to_dict,
    _milestone_to_dict,
    _resolve_goal_statuses,
    _result_summary,
    _risk_to_dict,
    _test_run_result_to_dict,
    _test_run_to_dict,
    _workspace_to_dict,
)
from .views_io import (
    CsvExportView,
    CsvImportView,
    ReqifExportView,
    ReqifImportView,
    SearchViewSet,
    _SearchHitSerializer,
    _SearchResponseSerializer,
    _abort_import_idempotency,
    _apply_import_deprecation_headers,
    _begin_import_idempotency,
    _finalize_import_idempotency,
    _idempotency_conflict_response,
    _with_request_id,
)
from .views_catalog import (
    AllocationListView,
    AttributeSchemaView,
    BundleCompressionStatusView,
    ConsistencyStatusView,
    GlossaryTermViewSet,
    GroupViewSet,
)



__all__ = [
    "GroupViewSet",
    "AllocationListView",
    "AdrViewSet",
    "ArchitectureElementViewSet",
    "ArtifactDiffService",
    "ArtifactViewSet",
    "BaselineViewSet",
    "CsvExportView",
    "CsvImportView",
    "DocumentViewSet",
    "IssueViewSet",
    "ReqifExportView",
    "RequirementViewSet",
    "RiskViewSet",
    "SearchViewSet",
    "StakeholderNeedViewSet",
    "TestCaseViewSet",
    "TraceLinkViewSet",
    "TraceabilityViewSet",
    "WorkflowDefinitionViewSet",
    "WorkspaceViewSet",
]
