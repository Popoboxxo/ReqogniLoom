"""
COMP-RA-001 HttpEndpointController — views_common — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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



# GH-443: every soft-deleting ``destroy()`` below repeats the same paragraph
# verbatim. That is deliberate duplication, not an oversight: drf-spectacular
# builds each endpoint's OpenAPI ``description`` from the method's ``__doc__``,
# so a shared constant would never reach the published schema — and the
# published schema is exactly where the contract was unreadable before. Where an
# entity genuinely deviates (ArchitectureElement's 404, the TraceLink cascade on
# TestCase/Issue/Risk) the deviation is spelled out in that entity's docstring.

# GH-868/GH-923/#1244: the standard body for a stale ``If-Match``. Declared per
# ETag-enabled PATCH operation (not injected globally) because only those routes
# can answer it — a global 412 on every operation would advertise a precondition
# two thirds of the surface does not enforce. The machine-readable list of the
# operations that declare it (and of the families that must not) lives in
# ``rest_api.conditional_requests``; #1397's gate test asserts the generated
# document against it in both directions.
_PRECONDITION_FAILED_RESPONSE = OpenApiResponse(
    response=ErrorResponseSerializer,
    description=(
        "Precondition failed: the ``If-Match`` precondition did not hold — no "
        "strong entity-tag in the header matches the resource's current "
        "``ETag`` (a stale tag, or a ``W/``-prefixed weak validator, which "
        "``If-Match``'s strong comparison can never match). A stale body "
        "``expected_version`` also lands here when an ``If-Match`` header is "
        "present. Re-read the resource — ``ETag`` is returned by both GET and "
        "PATCH — and retry with the fresh tag. Without an ``If-Match`` header "
        "this status is never answered: a stale ``expected_version`` body "
        "field is a 409 CONFLICT."
    ),
)


# #1397: the request header every 412 above is actually about. Declared once and
# referenced by all four ETag-enabled PATCH operations, so the document cannot
# drift from ``_PRECONDITION_FAILED_RESPONSE`` — before this, the schema
# advertised a 412 on those routes while declaring no header anywhere, leaving a
# generated client unable to build the guarded request at all.
_IF_MATCH_PARAMETER = OpenApiParameter(
    name="If-Match",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Optional strong entity-tag precondition (RFC 9110 § 13.1.1). Send the "
        "``ETag`` value a previous GET or PATCH of this resource returned, "
        "quoted — e.g. ``\"7\"``. ``*`` matches any existing representation and "
        "asserts no revision. Comparison is *strong*, so a weak validator "
        "(``W/\"7\"`` or ``w/\"7\"`` — the prefix is case-insensitive) never "
        "matches. A stale or weak tag answers 412 PRECONDITION_FAILED; a "
        "malformed field-value (unquoted, unbalanced quotes, blank, or a list "
        "containing a bad member) answers 400 INVALID_IF_MATCH. The field-value "
        "is scanned rather than split on commas, so a comma *inside* the quotes "
        "belongs to the tag (``\"a,b\"`` is one tag) and non-ASCII ``obs-text`` "
        "bytes (0x80-0xFF) are legal inside one. One deliberate deviation from "
        "RFC 9110 § 5.6.1: a value that reduces to zero tags — a lone comma, or "
        "only separators and whitespace — answers 400 INVALID_IF_MATCH rather "
        "than acting as an empty list that matches nothing (412). Omitting the "
        "header falls back to the ``expected_version`` body field (stale -> 409 "
        "CONFLICT). When both are sent the header wins."
    ),
)


# #1388/F3: the response half of the same contract. Declaring only the
# ``If-Match`` request header left a generated client with no way to learn
# where the tag it must send comes from — the 412 description says "``ETag`` is
# returned by both GET and PATCH" while no response in the whole document
# declared the header.
#
# drf-spectacular 0.30 publishes a *response* header through an
# ``OpenApiParameter`` whose ``response`` names the status codes it applies to
# (``OpenApiResponse(headers=...)`` is accepted by the type but ignored by
# ``_get_response_for_code`` in this version — verified against the installed
# source). Declaring it once here and referencing the constant from every
# ETag-enabled operation is the same single-source treatment
# ``_IF_MATCH_PARAMETER`` gets, so the two halves of the contract cannot drift.
_ETAG_RESPONSE_HEADER = OpenApiParameter(
    name="ETag",
    type=str,
    location=OpenApiParameter.HEADER,
    response=[200, 201],
    description=(
        "Strong entity-tag of the returned representation (RFC 9110 § 8.8.3), "
        "quoted — e.g. ``\"7\"``. Send it back verbatim as ``If-Match`` to make "
        "a subsequent PATCH conditional; a stale or weak tag answers 412 "
        "PRECONDITION_FAILED. Additive header only — the body is unchanged."
    ),
)


# ---------------------------------------------------------------------------
# Exception → HTTP status mapper (REQ-L3-RA001-002)
# No business logic — purely HTTP-concern translation.
# ---------------------------------------------------------------------------

# NOTE: both maps are keyed by *exact* exception type (see
# ``_service_error_response``), so a subclass needs its own entry — otherwise
# it silently degrades to a 500 "An internal error occurred.".
_EXC_TO_HTTP: dict[type, int] = {
    ValidationError: status.HTTP_400_BAD_REQUEST,
    # GH-513: same 400 as its ValidationError parent, deliberately — only the
    # code differs, so existing clients keep their status-code handling.
    BaselineGateBlockedError: status.HTTP_400_BAD_REQUEST,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    # SYSTEMAUDIT-2026-08-27 AP-6 M-1: access is correctly denied by the gate
    # (presets.gate raises this for a caller-supplied workspace_id owned by a
    # foreign tenant), but without this entry it fell through to the generic
    # 500 branch below. 403, matching the established convention for this
    # exact exception (see presets/tests/test_gate_tenant_guard.py).
    CrossTenantWorkspaceError: status.HTTP_403_FORBIDDEN,
    # GH-914: an agent that tries to confirm or discard its *own* proposal is a
    # policy denial, not a server fault. The guard itself works (the service
    # raises AgentSelfConfirmError), but the exception had no entry here, so
    # the exact-type lookup below degraded it to the generic 500 fallback —
    # indistinguishable from a real defect to every client. 403, matching the
    # established convention for this class of denial.
    AgentSelfConfirmError: status.HTTP_403_FORBIDDEN,
    # #569: the three suppression error types. Same precedent as
    # BaselineGateBlockedError — ValidationError subclasses with their own code
    # and status, registered here so an escape from any view answers the
    # business error instead of the 500 fallback (AC-569-29(iv)). The two L1
    # governance domain errors are deliberately NOT registered: the facades
    # remap them, and a leak would be a bug that must stay loud (AC-569-29(v)).
    WaiverReasonPolicyViolation: status.HTTP_400_BAD_REQUEST,
    WaiverFindingNotBlockingError: status.HTTP_400_BAD_REQUEST,
    SuppressionExpiredError: status.HTTP_409_CONFLICT,
    # ADR-019 WP5 / review finding 003-01: a suggestion production attempt
    # outside an agent/API-key context is fail-closed. A rejected
    # precondition on a well-formed, authorised request, hence 409 (same
    # convention as SuppressionExpiredError above) — never a silent no-op.
    ProducerContextRequiredError: status.HTTP_409_CONFLICT,
    # #1084: a hard delete refused because the workspace still holds
    # append-only baselines. A rejected precondition, not a malformed request,
    # hence 409 — and registering the type is what also forwards the service's
    # own message to the client when the refusal escapes a view that has no
    # dedicated branch (the exact-type lookup degrades to a 500 otherwise).
    BaselineImmutabilityError: status.HTTP_409_CONFLICT,
    # F4.2 review B2/B3: tag input is a request defect (a control character, an
    # over-long value, a collation-level label collision). Registered as its
    # own type because ``_service_error_response`` looks the exception up by
    # *exact* type — a ``ValidationError`` subclass left out of this map degrades
    # to the generic 500 branch, which is precisely the symptom being fixed.
    # Routes that want the machine-readable ``details`` list still catch it
    # explicitly (baseline create / tags / list).
    BaselineTagValidationError: status.HTTP_400_BAD_REQUEST,
    # Plan F F4.4 (SEC-RB-05): the seven baseline-rollback error types. Same
    # exact-type rule as the entries above — without these the domain refusal
    # („plan stale", „not approved", „human only") would surface as a 500 and be
    # indistinguishable from a defect. Each type carries its own stable code
    # below; ``RollbackForbiddenError`` is also a ``PermissionDeniedError``,
    # ``RollbackEmptyError``/``RollbackTooLargeError`` are also
    # ``ValidationError``s — the inherited pair would already answer 403/400 but
    # with the wrong code, so the exact type must be named here explicitly.
    RollbackError: status.HTTP_409_CONFLICT,
    RollbackNotApprovedError: status.HTTP_409_CONFLICT,
    RollbackAlreadyAppliedError: status.HTTP_409_CONFLICT,
    RollbackPlanStaleError: status.HTTP_409_CONFLICT,
    RollbackConflictError: status.HTTP_409_CONFLICT,
    RollbackEmptyError: status.HTTP_400_BAD_REQUEST,
    RollbackTooLargeError: status.HTTP_400_BAD_REQUEST,
    RollbackForbiddenError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    OptimisticLockError: status.HTTP_409_CONFLICT,
    # Plan F F2-T5 / ADR-026 F-3 & §4.2: the two Document domain refusals are
    # ``ValidationError`` subclasses, so without their exact-type entries the
    # generic lookup would answer a 500 — which is precisely the contract the
    # F2-T4 service docstrings reserve for this PR. 409 for both: the release
    # gate is a rejected precondition on a well-formed request, and a frozen
    # field is a state conflict, not a malformed payload.
    FieldFrozenError: status.HTTP_409_CONFLICT,
    # P2: N:1 allocation conflict on the generic TraceLink create path.
    AllocationConflictError: status.HTTP_409_CONFLICT,
    WorkflowFrozenError: status.HTTP_409_CONFLICT,
    DocumentGateFailedError: status.HTTP_409_CONFLICT,
    # Plan F F3-T7 / I-3: deleting a link that still carries inline anchors is
    # a rejected precondition (confirm the count and retry), hence 409.
    AnchorsPresentError: status.HTTP_409_CONFLICT,
    # GH-1396: shared safety net for routes that do not map the header
    # themselves (the workflow-transition special routes). A malformed
    # ``If-Match`` is a request defect (400); a header whose strong tags cannot
    # match is a lost precondition, and on the transition routes that is the
    # CR-08 conflict (409) — never 412, which those routes reserve for nothing.
    InvalidIfMatch: status.HTTP_400_BAD_REQUEST,
    IfMatchMismatch: status.HTTP_409_CONFLICT,
    # #1240: the LLM answered, but its content could not be parsed (non-JSON,
    # empty completion, wrong shape) — an upstream/response fault, not a server
    # defect. 502 (Bad Gateway), alongside LLM_TIMEOUT (504) and LLM_UNAVAILABLE
    # (503); before this entry it fell through to the generic 500 branch.
    LlmResponseError: status.HTTP_502_BAD_GATEWAY,
    # #1416: provider unavailability is not an invalid answer — it is retry-able
    # upstream state. 504 for a timeout, 503 for a transport failure / open
    # circuit (same taxonomy as architecture.decompose, #1165).
    LlmProviderTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    LlmProviderUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    # #1416: the REQ-106 daily budget is a quota refusal, not a bad provider
    # answer. 429 + LLM_TOKEN_LIMIT_EXCEEDED mirrors CapabilityRouter's
    # existing taxonomy for the very same condition.
    LlmTokenLimitExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
    # ADR-028 A1: a release from a state with no release edge is a rejected
    # precondition on a well-formed request, not a malformed payload.
    ReleaseStateError: status.HTTP_409_CONFLICT,
    # GH-1804: a declared fallback only. The release route catches this type
    # first and queues the cascade (202); this entry covers a cascade that
    # escapes a transport with no async substitute (MCP, a direct service
    # caller) — a well-formed request the synchronous ceiling refuses, hence
    # 400 rather than the generic 500 an unregistered subclass would produce.
    ReleaseTooLargeError: status.HTTP_400_BAD_REQUEST,
    # Phase G / #1374 S3: adopting a file whose hash moved is a state conflict.
    AdoptionHashMismatchError: status.HTTP_409_CONFLICT,
}


_EXC_TO_CODE: dict[type, str] = {
    ValidationError: "VALIDATION_ERROR",
    # GH-513: a distinct code so a client can tell "known BLOCKERs, waivable
    # with an override_reason" apart from every other 400 on this endpoint.
    BaselineGateBlockedError: "SE_AUDITOR_BLOCKED",
    PermissionDeniedError: "PERMISSION_DENIED",
    CrossTenantWorkspaceError: "PERMISSION_DENIED",
    # GH-914: same 403 code as every other policy denial. Registering the type
    # here is also what forwards the service's own message ("An AI agent may
    # not confirm a proposed trace link.") to the client — a static domain
    # sentence with no internals, exactly like PermissionDeniedError.
    AgentSelfConfirmError: "PERMISSION_DENIED",
    # #569: dedicated codes so a client can tell "justification rejected" apart
    # from "named finding is not a blocker" and "the existing row expired".
    WaiverReasonPolicyViolation: "WAIVER_REASON_REJECTED",
    WaiverFindingNotBlockingError: "WAIVER_FINDING_NOT_BLOCKING",
    SuppressionExpiredError: "SUPPRESSION_EXPIRED",
    ProducerContextRequiredError: "PRODUCER_CONTEXT_REQUIRED",
    BaselineImmutabilityError: "CONFLICT",
    # F4.2 review B2/B3: same code as every other validation failure, so a
    # client keeps one 400 branch; only the shape of ``details`` differs.
    BaselineTagValidationError: "VALIDATION_ERROR",
    # Plan F F4.4 (SEC-RB-05): one stable code per rollback failure so a client
    # can branch on the reason ("re-read the plan" vs "get it approved" vs "an
    # agent may not execute this") instead of inferring it from a 409.
    RollbackError: "ROLLBACK_ERROR",
    RollbackNotApprovedError: "ROLLBACK_NOT_APPROVED",
    RollbackAlreadyAppliedError: "ROLLBACK_ALREADY_APPLIED",
    RollbackPlanStaleError: "ROLLBACK_PLAN_STALE",
    RollbackConflictError: "ROLLBACK_CONFLICT",
    RollbackEmptyError: "ROLLBACK_EMPTY",
    RollbackTooLargeError: "ROLLBACK_TOO_LARGE",
    RollbackForbiddenError: "PERMISSION_DENIED",
    NotFoundError: "NOT_FOUND",
    OptimisticLockError: "CONFLICT",
    # Plan F F2-T5: dedicated codes + structured ``details`` (one entry per
    # frozen field / one per violated gate), per ADR-026 F-3 and §4.2.
    FieldFrozenError: "FIELD_FROZEN",
    AllocationConflictError: "CONFLICT",
    WorkflowFrozenError: "WORKFLOW_FROZEN",
    DocumentGateFailedError: "DOCUMENT_GATE_FAILED",
    # Plan F F3-T7 / I-3: distinct code so a client can read the count and
    # retry with ?confirm_anchor_count=n instead of retrying blindly.
    AnchorsPresentError: "ANCHORS_PRESENT",
    # GH-1396: see _EXC_TO_HTTP. INVALID_IF_MATCH is its own code so a client
    # can tell "your header did not parse" (fix the request) from
    # PRECONDITION_FAILED ("re-read and retry").
    InvalidIfMatch: "INVALID_IF_MATCH",
    IfMatchMismatch: "CONFLICT",
    LlmResponseError: "LLM_OUTPUT_INVALID",
    # #1416: cause-specific codes for the derive flows (see _EXC_TO_HTTP).
    LlmProviderTimeoutError: "LLM_TIMEOUT",
    LlmProviderUnavailableError: "LLM_UNAVAILABLE",
    LlmTokenLimitExceededError: "LLM_TOKEN_LIMIT_EXCEEDED",
    # ADR-028 A1: the client may retry once the item reaches a releasable state.
    ReleaseStateError: "RELEASE_NOT_ALLOWED",
    # GH-1804: distinct code so a client can tell "queue it instead" from a
    # genuinely malformed release request.
    ReleaseTooLargeError: "RELEASE_TOO_LARGE",
    AdoptionHashMismatchError: "CONFLICT",
}



#: Registered exception types whose *message* must NOT be forwarded to the
#: client even though their code/status is (issue #1240). ``LlmResponseError``
#: wraps raw provider/SDK failures, so its text can embed upstream detail (e.g.
#: an authentication error echoing a key fragment). The client gets the static,
#: localised sentence for its code instead; the detail goes to the log. The
#: #1416 subclasses inherit the same provider text and are listed explicitly —
#: the map lookup is by exact type, never by ``isinstance``.
_MESSAGE_NOT_SURFACEABLE: frozenset[type] = frozenset(
    {
        LlmResponseError,
        LlmProviderTimeoutError,
        LlmProviderUnavailableError,
        LlmTokenLimitExceededError,
    }
)



def _resolve_change_reason(request: Request) -> str:
    """Backwards-compatible alias for :func:`rest_api.query_params.parse_change_reason`.

    The resolver moved into ``query_params`` in G1.5 so it sits next to
    ``parse_include_deleted`` and can be reused by every soft-deleting view.
    Kept as a thin delegate because existing tests import it from here.
    """
    return parse_change_reason(request)



#: Shared OpenAPI contract for soft-deleting ``destroy`` handlers (G1.5/#1381).
_SOFT_DELETE_CHANGE_REASON_PARAMETER = OpenApiParameter(
    name="change_reason",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Reason for the soft-delete. The JSON body's `change_reason` wins when "
        "both are sent. Without either, a workspace whose preset mandates a "
        "reason answers 400 VALIDATION_ERROR."
    ),
)



def soft_delete_schema():
    """``@extend_schema`` decorator for a soft-deleting ``destroy`` (G1.5).

    Declares the ``change_reason`` query parameter and states the GH-443
    response contract (204 now, 200 + ``status="outdated"`` on the next GET) so
    the OpenAPI document stops omitting both.
    """
    return extend_schema(
        parameters=[_SOFT_DELETE_CHANGE_REASON_PARAMETER],
        responses={
            204: OpenApiResponse(
                description=(
                    "Soft-deleted; the record is not removed. A subsequent GET "
                    'on the same URL answers 200 with status="outdated".'
                )
            )
        },
    )



def list_schema(
    *,
    status: bool = False,
    search: bool = False,
    strict: bool = False,
    extra: tuple[str, ...] = (),
):
    """Declare the query parameters an artifact list endpoint really reads.

    ``page``/``page_size`` come from ``StandardPagination``; this adds the
    filters the handler passes to its service. ``status`` is declared only
    where the service actually filters on it — declaring it elsewhere would
    repeat the silent no-op G-L16 documented in the OpenAPI instead of fixing
    it.

    ``strict=True`` additionally rejects any *undeclared* query parameter with
    a 400 (C3 / #1668). ``extra`` names endpoint-specific filters that are not
    covered by ``status``/``search`` (e.g. ``allocated``/``level``). The
    allow-list is built from this declaration, so the runtime guard and the
    OpenAPI document cannot drift apart.
    """
    parameters = [
        OpenApiParameter(
            "workspace_id",
            OpenApiTypes.UUID,
            OpenApiParameter.QUERY,
            required=True,
            description="Workspace whose artifacts are listed.",
        ),
        OpenApiParameter(
            "include_deleted",
            OpenApiTypes.BOOL,
            OpenApiParameter.QUERY,
            required=False,
            description=(
                "Include soft-deleted (outdated) records. Defaults to false; "
                "the detail GET still answers 200 with status='outdated'."
            ),
        ),
    ]
    if status:
        parameters.append(
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Only rows whose workflow state matches (or, for "
                    "'outdated', whose soft-delete flag is set)."
                ),
            )
        )
    if search:
        parameters.append(
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description="Case-insensitive match on title, description or uid.",
            )
        )
    for name in extra:
        parameters.append(
            OpenApiParameter(
                name,
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description=f"Endpoint-specific filter '{name}'.",
            )
        )

    allowed = {"workspace_id", "include_deleted", "page", "page_size"}
    if status:
        allowed.add("status")
    if search:
        allowed.add("search")
    allowed.update(extra)

    def decorator(fn):
        if not strict:
            return extend_schema(parameters=parameters)(fn)

        @wraps(fn)
        def guarded(self, request, *args, **kwargs):
            error = reject_unknown_query_params(
                request, allowed, detect_lang(request)
            )
            if error is not None:
                return error
            return fn(self, request, *args, **kwargs)

        return extend_schema(parameters=parameters)(guarded)

    return decorator



def _service_error_response(exc: Exception, lang: str = "en") -> Response:
    """Translate an ApplicationService exception into a standardised error Response.

    REQ-L3-RA001-002: No stack traces leaked; uses ErrorResponseFormatter pattern.

    fix #108: for unmapped exception types (IntegrityError, ProgrammingError,
    KeyError, etc.), ``str(exc)`` can contain SQL fragments, table/column
    names, and constraint names — leaking internals regardless of DEBUG.
    Only the explicitly mapped, safe-to-surface exception types get
    their message forwarded to the client; everything else gets a static
    message, with the real detail going to the log only.

    #1240: a type can be mapped for its code/status yet excluded from message
    forwarding (``_MESSAGE_NOT_SURFACEABLE``) — ``LlmResponseError`` wraps raw
    provider text and reports the static ``LLM_OUTPUT_INVALID`` sentence while
    the detail is logged.

    Plan F F4.4 (SEC-RB-05): a mapped exception that carries a ``details``
    payload has it forwarded into the envelope. Additive only — an exception
    without ``details`` (every other type) produces exactly the previous
    details-less body, so no existing client sees a difference. The rollback
    types use it to name *which* items invalidated a plan (R3: a list) or which
    CR state was hit (R5: a dict); the value is service-built and contains no
    internals.

    #1761: a DRF ``APIException`` is a transport-level signal (invalid
    ``page``/``page_size``, malformed UUID in a path, link-type guard — see
    ``rest_api.serializers.InvalidPageSize``), not a service failure. Several
    views wrap their service call *and* the pagination call in one broad
    ``except Exception``; without this re-raise such an exception would be
    rewritten into a generic 500 — the exact mechanism AUD-2026-09-073 found
    for an invalid ``page``. Re-raising hands it back to DRF's exception
    handling, which is where its status code and envelope are defined.
    """
    if isinstance(exc, APIException):
        raise exc

    exc_type = type(exc)
    http_status = _EXC_TO_HTTP.get(exc_type, status.HTTP_500_INTERNAL_SERVER_ERROR)
    code = _EXC_TO_CODE.get(exc_type, "INTERNAL_SERVER_ERROR")
    if exc_type in _MESSAGE_NOT_SURFACEABLE:
        logger.warning(
            "Service error not surfaced to the client (%s)", exc_type.__name__,
            exc_info=exc,
        )
        message = None
    elif exc_type in _EXC_TO_CODE:
        message = str(exc) or None
    else:
        logger.exception("Unhandled exception in service layer", exc_info=exc)
        message = "An internal error occurred."
    body = build_error_response(
        code=code,
        lang=lang,
        message=message,
        # Only mapped types: an unmapped exception's attributes must not reach
        # the client (they can hold ORM objects, ids the caller may not see).
        details=(getattr(exc, "details", None) if exc_type in _EXC_TO_CODE else None),
    )
    return Response(body, status=http_status)



#: Accepted values of the ``mode`` key on the AI-derivation actions (#1358).
_DERIVATION_MODES = ("preview", "write")

#: Accepted values of the ``policy`` key on the AI-derivation actions.
_DERIVATION_POLICIES = ("manual", "auto")



def _special_route_if_match_error(exc: Exception, lang: str = "en") -> Response:
    """Map an ``If-Match`` resolver failure on a CR-08 special route.

    The ``ETag`` PATCH routes answer **412** for a lost precondition; the
    special routes (``goals/{pk}/outdate|reactivate``, ``adrs/{pk}/supersede``,
    ``main-goals/{pk}/approve``, ``change-requests/{pk}/transition``) guard the
    ``WorkflowItemState`` revision instead, so a mismatch is the **409**
    ``CONFLICT`` CR-08 defines — the same split
    ``WorkflowTransitionsMixin.transitions`` applies to the generic route
    (GH-1396 review finding B3).

    A malformed header is a request defect on every route: 400
    ``INVALID_IF_MATCH``. Any other exception is a bug and is re-raised, never
    disguised as an HTTP answer.
    """
    if isinstance(exc, InvalidIfMatch):
        return Response(
            build_error_response(
                "INVALID_IF_MATCH",
                lang,
                details=[{"reason": exc.reason}] if exc.reason else None,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, IfMatchMismatch):
        return Response(
            build_error_response("CONFLICT", lang),
            status=status.HTTP_409_CONFLICT,
        )
    raise exc



def _parse_derivation_mode_policy(
    request: Request, lang: str
) -> tuple[str, str, Response | None]:
    """Parse the optional ``mode``/``policy`` body keys of an AI-derivation action.

    #1358 (W12a): ``mode="preview"`` (the default) answers the ephemeral draft
    preview only — the response carries ``"ephemeral": true``. ``mode="write"``
    is the canonical persistence path: it persists the drafts through
    ``AiDerivationService.persist_*``, the very same write seam the MCP tools'
    ``mode="write"`` uses, so both transports cannot drift apart.

    Returns ``(mode, policy, error)`` with exactly one of the three ever being
    meaningful — :func:`rest_api.query_params.parse_workspace_id`'s
    ``(value, error)`` convention, so a caller cannot accidentally swallow the
    400 inside a broad ``except``.
    """
    payload = request.data if isinstance(request.data, dict) else {}
    mode = payload.get("mode", "preview")
    policy = payload.get("policy", "manual")
    if mode not in _DERIVATION_MODES:
        return mode, policy, Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message=f"'mode' must be one of {_DERIVATION_MODES}, got '{mode}'.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if policy not in _DERIVATION_POLICIES:
        return mode, policy, Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message=(
                    f"'policy' must be one of {_DERIVATION_POLICIES}, "
                    f"got '{policy}'."
                ),
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return mode, policy, None



# ---------------------------------------------------------------------------
# Base ViewSet mixin: error handling + auth context
# REQ-L3-RA001-004: no business logic — only HTTP translation.
# ---------------------------------------------------------------------------


class MalformedUuidInPath(APIException):
    """400 for a URL path segment that is not a well-formed UUID (issue #271).

    Carries an already-built ``build_error_response`` body as its ``detail`` so
    ``rest_api.error_envelope.reqogniloom_exception_handler`` passes it through
    unchanged (it short-circuits on a dict that already has an ``error`` key).
    That keeps the response byte-compatible with the envelope every explicit
    error in this module produces (REQ-071, REQ-L2-RA-009).
    """

    status_code = status.HTTP_400_BAD_REQUEST



class UnknownDetailRoute(APIException):
    """404 for a detail path whose pk segment is really a custom-action name.

    The DRF router builds a detail action as ``{prefix}/{lookup}/{url_path}/``
    and its default lookup pattern is ``[^/.]+``, so a caller that drops the pk
    — ``GET /api/v1/needs/derive-requirements/`` — still matches the *detail*
    route with ``pk="derive-requirements"``. That is a route which does not
    exist, not an id which is malformed, so it must answer 404 like any other
    routing miss (REQ-128) rather than the 400 that ``MalformedUuidInPath``
    would give it (issue #710).

    Same ``detail``-carries-the-envelope trick as ``MalformedUuidInPath``.
    """

    status_code = status.HTTP_404_NOT_FOUND



class BaseEntityViewSet(
    ETagMixin, FreeTextSanitizationMixin, PresetGateMixin, viewsets.ViewSet
):
    """Shared behaviour: error mapping, auth context, preset gate, pagination.

    Subclasses must implement list(), retrieve(), create(), partial_update(),
    destroy() and set:
      - serializer_class
      - preset_endpoint_key (optional, from PresetGateMixin)

    #269: ``FreeTextSanitizationMixin`` guards every write body here rather
    than in each subclass, because several subclasses read ``request.data``
    directly instead of running ``serializer_class`` (see the mixin docstring).

    GH-868/GH-923: ``ETagMixin`` is inherited here so a subclass can opt into
    ``ETag``/``If-Match`` support with one line per handler
    (``self.with_etag(...)`` / ``self.resolve_expected_version(...)``). It emits
    nothing by itself, so every ViewSet that does not call those helpers is
    unchanged.
    """

    serializer_class: type | None = None
    pagination_class = StandardPagination

    #: URL path kwargs that MUST parse as a UUID (issue #271). Every subclass
    #: resolves its detail routes by UUID today (``UUID(pk)`` in the handler, or
    #: ``UUID(str(...))`` one layer down in the service — verified for
    #: BaselineViewSet, which passes ``pk`` through as a string). A subclass
    #: whose lookup is genuinely *not* a UUID
    #: must narrow this tuple, otherwise its detail route will start 400ing.
    uuid_url_kwargs: tuple[str, ...] = ("pk", "workspace_pk", "workspace_id")

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Run DRF's setup, then reject malformed UUID path segments (#271).

        Ordering matters: ``super().initial()`` performs authentication,
        permission and throttle checks first, so an anonymous or unauthorised
        caller still receives 401/403. Were the UUID check first, the
        400-vs-401 difference would let an unauthenticated prober distinguish
        real routes from garbage.
        """
        super().initial(request, *args, **kwargs)
        self._reject_malformed_uuid_path_kwargs(request)

    def _reject_malformed_uuid_path_kwargs(self, request: Request) -> None:
        """Raise 400 when a ``uuid_url_kwargs`` path segment is not a UUID.

        Previously each detail handler caught the ``ValueError`` from
        ``UUID(pk)`` and answered 404, making "you sent garbage" indis-
        tinguishable from "well-formed id, no such row" (issue #271). Those
        per-handler ``except ValueError`` branches are deliberately left in
        place: they are unreachable for HTTP traffic now, but still guard the
        many unit tests that call ``view.retrieve(request, pk=...)`` directly,
        and any other ``ValueError`` source inside the handler.

        One class of malformed lookup value is not a malformed id at all: a
        pk segment that equals one of this ViewSet's own detail-action
        ``url_path``s, i.e. a caller that asked for the action route and left
        out the pk (``/needs/derive-requirements/``, REQ-128). Reporting that
        as "'pk' must be a well-formed UUID" describes the wrong problem, so
        it 404s as the routing miss it is (issue #710 reopen).
        """
        lang = detect_lang(request)
        # ``dispatch()`` sets ``self.kwargs`` before ``initial()``; the getattr
        # keeps a hand-rolled ``initial()`` call in a unit test from AttributeError.
        url_kwargs = getattr(self, "kwargs", None) or {}
        # Same resolution order the router uses in ``get_lookup_regex()``.
        # ``viewsets.ViewSet`` (unlike GenericViewSet) declares neither
        # attribute, hence the getattr chain rather than plain access.
        lookup_kwarg = getattr(self, "lookup_url_kwarg", None) or getattr(
            self, "lookup_field", "pk"
        )
        for name in self.uuid_url_kwargs:
            raw = url_kwargs.get(name)
            if raw is None:
                continue
            try:
                UUID(str(raw))
            except (ValueError, AttributeError, TypeError):
                if name == lookup_kwarg and str(raw) in self._detail_action_url_paths():
                    raise UnknownDetailRoute(
                        build_error_response(
                            "NOT_FOUND",
                            lang,
                            message=ROUTE_NOT_FOUND_MESSAGE.get(
                                lang, ROUTE_NOT_FOUND_MESSAGE["en"]
                            ),
                        )
                    ) from None
                # The offending value is NOT echoed back — it is fully
                # attacker-controlled and would be reflected into the body.
                raise MalformedUuidInPath(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=f"'{name}' must be a well-formed UUID.",
                    )
                ) from None

    @classmethod
    def _detail_action_url_paths(cls) -> frozenset[str]:
        """URL path segments of every ``@action(detail=True)`` on this ViewSet.

        Read from DRF's own ``get_extra_actions()`` rather than a hand-kept
        list, so an action added later is covered without a second edit.
        ``detail=False`` actions are excluded on purpose: the router registers
        their list routes *before* the detail route, so they never reach a pk
        slot in the first place.
        """
        try:
            extra_actions = cls.get_extra_actions()
        except AttributeError:  # pragma: no cover - non-ViewSet subclass
            return frozenset()
        return frozenset(
            str(action_method.url_path)
            for action_method in extra_actions
            if getattr(action_method, "detail", False)
        )

    @property
    def paginator(self) -> StandardPagination:
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def _paginate(
        self,
        request: Request,
        items: Any,
        serialize: Callable[[Any], Any] | None = None,
        *,
        serialize_page: Callable[[list], Any] | None = None,
    ) -> Response:
        """Paginate *items* and return a paginated Response.

        REQ-034: ``items`` (a QuerySet or in-memory sequence) is handed straight
        to the DRF paginator, which slices lazily — a QuerySet becomes a
        ``LIMIT/OFFSET`` query instead of being materialised in full up front
        (no ``list()``/``len()`` over the whole result set here).

        When ``serialize`` is provided it is applied *only* to the current page,
        so serialisation cost is O(page_size) instead of O(N). Call sites that
        already pass a pre-serialised list may omit ``serialize`` (backwards
        compatible).

        ``serialize_page`` is the batched alternative: it receives the whole
        page (a list, at most ``page_size`` items) in one call instead of once
        per row. Required for any serializer using
        ``WorkflowStateSerializerMixin`` (Datenmodell-Konsolidierung) — a
        per-row ``serialize`` lambda builds a *fresh* serializer instance per
        row, so the mixin's ``many=True`` status-map batching (one query for
        the whole page) never kicks in and every row pays its own
        ``WorkflowItemState`` query instead. Mutually exclusive with
        ``serialize``.

        Response shape follows ``StandardPagination``:
        ``{count, next, previous, page_size, max_page_size, results}`` — the
        last two were added in #571 (reopen) so a clamped ``page_size`` stops
        being silent.
        """
        # G2.1 (#1400): an unordered QuerySet makes OFFSET/LIMIT pagination
        # non-deterministic — the database may return the same row on two pages
        # and drop another. Order every unordered input here, once, so all 16
        # callers are covered; an explicit ORDER BY on the QuerySet still wins.
        if isinstance(items, QuerySet) and not items.ordered:
            field_names = {field.name for field in items.model._meta.fields}
            items = items.order_by(
                *(("created_at", "pk") if "created_at" in field_names else ("pk",))
            )

        page = self.paginator.paginate_queryset(items, request, view=self)
        if page is not None:
            if serialize_page is not None:
                results = serialize_page(list(page))
            else:
                results = [serialize(obj) for obj in page] if serialize else page
            return self.paginator.get_paginated_response(results)
        # Pagination disabled for this request — serialise the full set.
        if serialize_page is not None:
            return Response(serialize_page(list(items)))
        if serialize is not None:
            return Response([serialize(obj) for obj in items])
        return Response(items)

    def list(self, request: Request, **kwargs: Any) -> Response:
        raise NotImplementedError

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError

    def create(self, request: Request, **kwargs: Any) -> Response:
        raise NotImplementedError

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError

    def _apply_artifact_system_fields(
        self, request: Request, item_type: str, entity: Any, ctx: Any
    ) -> None:
        """Write Artifact-level ``owner``/``reporter``/``priority`` (WS2, #936).

        These fields live on ``Artifact``, not on the per-type model, so the
        type-specific create/update service cannot persist them. After that
        service returns, this routes the client's values through the shared
        :class:`ArtifactAttributeGateway` — the same actor-resolution and
        validation path MCP uses — so REST and MCP cannot diverge.

        Only keys actually present in the request are applied, so an unrelated
        PATCH never clears a stored value. A workspace with no bootstrapped
        definition is a no-op, mirroring ``_validate_attribute_definition``'s
        graceful degradation (the fields are not visible without a definition
        anyway).
        """
        raw = getattr(request, "data", None)
        if not isinstance(raw, dict):
            return
        values = {
            name: raw[name]
            for name in _SYSTEM_FIELD_NAMES
            if name in raw
        }
        if not values:
            return
        from application.attribute_definition_service import AttributeDefinitionNotFound

        try:
            ArtifactAttributeGateway().write(
                ctx, item_type, entity, AttributeValues(core=values)
            )
        except AttributeDefinitionNotFound:
            return



#: Attribute-level system field names (Attribut v3 WS2, #936; ADR-006), shared
#: by every REST write/read hook so the wire keys cannot drift.
#:
#: One list with two jobs, which is why it is derived rather than typed out:
#:
#: * ``_apply_artifact_system_fields`` collects *these* keys out of
#:   ``request.data`` and hands them to ``ArtifactAttributeGateway.write`` — the
#:   value never reaches the type-specific service, which does not own the
#:   backing Artifact (or, for ``deciders``/``assignee``, the relation).
#: * the create/update handlers pop *these* names out of ``validated_data``
#:   before splatting the rest into the service. Without the pop, a name the
#:   service does not accept raises ``TypeError`` (500) — so the pop list and the
#:   gateway list MUST be the same set, by construction.
#:
#: The Artifact-level names come from the application layer (which owns the
#: carrier routing) and the carrier-backed names from the attribute vocabulary
#: (which owns which item type declares what), composed by the one function the
#: MCP side calls too (``mcp_server.tools.system_fields.SYSTEM_FIELD_NAMES``) —
#: so REST and MCP cannot disagree about which fields a transport carries.
_SYSTEM_FIELD_NAMES: tuple[str, ...] = transport_field_names()



def _artifact_custom_fields(entity: Any) -> dict:
    """Return the custom_fields map from an entity's backing Artifact.

    REQ-L2-AS-037: custom_fields lives on Artifact; every artifact-backed
    entity exposes it via its OneToOne ``artifact`` relation. Missing/NULL
    normalizes to an empty dict so the API contract stays stable.
    """
    artifact = getattr(entity, "artifact", None)
    if artifact is None:
        return getattr(entity, "custom_fields", None) or {}
    return getattr(artifact, "custom_fields", None) or {}
