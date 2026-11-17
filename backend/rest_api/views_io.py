"""
COMP-RA-001 HttpEndpointController — views_io — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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
    _service_error_response,
)




def _with_request_id(body: dict[str, Any]) -> dict[str, Any]:
    """Add ``request_id`` to an error envelope body (ADR-014 §1, finding 077).

    The ``X-Request-ID`` response header already exists
    (``reqogniloom.middleware.RequestIdMiddleware``); ADR-014 §1 mirrors the
    same correlation id into the error body so a client can correlate a failed
    request with the server log without depending on a header alone. The copy
    is additive and null when no request context is active (e.g. direct view
    calls in unit tests), never a fabricated id.
    """
    from reqogniloom.middleware import get_request_id

    error = body.get("error")
    if isinstance(error, dict) and "request_id" not in error:
        error["request_id"] = get_request_id()
    return body



# ---------------------------------------------------------------------------
# SearchViewSet — Full-text search across Requirements, ArchitectureElements,
# and TestCases (COMP-AS-010 SearchService).
# REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009
# ---------------------------------------------------------------------------


class _SearchHitSerializer(serializers.Serializer):
    """One ``/api/v1/search/`` result row (documentation-only serializer)."""

    id = serializers.CharField()
    artifact_type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    relevance_score = serializers.FloatField(
        help_text=(
            "Rank-derived relevance in [0, 1]. Comparable within one response "
            "and stable for a given backend, but NOT across backends: under "
            "Qdrant, a hybrid query's semantic leg contributes an RRF fused "
            "score (a rank quantity, not a cosine similarity), so the same "
            "value is not a similarity measure there. Ordering is authoritative; "
            "the absolute number is not."
        )
    )
    workspace_id = serializers.CharField(allow_blank=True)



class _SearchResponseSerializer(serializers.Serializer):
    """The ``/api/v1/search/`` response contract (T-A2-7, OpenAPI DoD).

    ``vector_backend``/``degraded``/``degraded_reason`` are additive: a
    Qdrant outage answers HTTP 200 with ``vector_backend="pgvector"`` and
    ``degraded=true``, never a 500. A failing cross-type semantic leg answers
    200 with ``degraded=true`` and ``degraded_reason="cross_type_query_failed"``
    while ``vector_backend`` keeps naming the backend that served the other
    legs.

    ``relevance_score`` semantics are backend-dependent: on pgvector it derives
    from a cosine similarity, on Qdrant from an RRF fused score (a rank
    quantity), so ``min_score`` filtering keeps a different number of
    semantically matched hits per backend. The ranking itself is unaffected.
    """

    results = _SearchHitSerializer(many=True)
    total_count = serializers.IntegerField()
    page = serializers.IntegerField()
    limit = serializers.IntegerField()
    query = serializers.CharField()
    mode = serializers.CharField()
    vector_backend = serializers.CharField()
    degraded = serializers.BooleanField()
    degraded_reason = serializers.CharField(allow_blank=True)
    # Issue #18: present only when the caller asked for include_summary=true.
    ai_summary = serializers.CharField(allow_null=True, required=False)
    summary_degraded = serializers.BooleanField(required=False)



class SearchViewSet(viewsets.ViewSet):
    """ViewSet for full-text search.

    Delegates to SearchService (COMP-AS-010, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).

    GET /api/v1/search/?q=<query>&workspace_id=<id>[&type=Requirement&page=1&limit=20]
    """

    # #447: the schema documented zero parameters for this endpoint, so a
    # generated client had no way to learn that ``q`` and ``workspace_id`` are
    # both mandatory — it would emit a bare GET and get a 400 back.
    @extend_schema(
        summary="Full-text search across artifacts",
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description=(
                    "Search query. Required and must be non-empty; a blank "
                    "value returns 400 rather than an empty result set."
                ),
            ),
            OpenApiParameter(
                name="workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Workspace UUID to search in.",
            ),
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                many=True,
                description=(
                    "Artifact type filter (Requirement | ArchitectureElement | "
                    "TestCase). May be repeated."
                ),
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=1,
                description="Page number.",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=20,
                description="Page size (max 100).",
            ),
            OpenApiParameter(
                name="mode",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                default="hybrid",
                enum=["hybrid", "keyword", "vector"],
                description=(
                    "Search mode: hybrid (default), keyword (full-text + "
                    "lexical, no embedding call) or vector (semantic only). "
                    "An unknown value answers 400."
                ),
            ),
            OpenApiParameter(
                name="include_summary",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                default=False,
                description=(
                    "Default false. When true the response gains ai_summary "
                    "(string or null) and summary_degraded (bool). Triggers "
                    "one LLM call per request; a provider failure degrades "
                    "instead of failing the search."
                ),
            ),
        ],
        responses={200: _SearchResponseSerializer},
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/search/ — full-text search.

        Query params:
          q             — search query (required)
          workspace_id  — workspace UUID (required)
          type          — optional type filter (Requirement|ArchitectureElement|TestCase)
                          may be repeated
          page          — page number (default 1)
          limit         — page size (default 20, max 100)
          mode          — hybrid (default) | keyword | vector

        The response always carries ``vector_backend``, ``degraded`` and
        ``degraded_reason`` (T-A2-7). A Qdrant outage degrades to pgvector and
        answers 200 with ``degraded=true`` — never a 500. A failing cross-type
        semantic leg also answers 200, with
        ``degraded_reason="cross_type_query_failed"``, and the results are then
        partial (the other passes still ran).
        """
        lang = detect_lang(request)

        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error

        # Issue #460 finding 3: a missing/blank ``q`` used to answer 200 with
        # an empty result set. That silently swallowed the common client bug
        # of sending the wrong parameter name (``?search=`` instead of ``?q=``,
        # as the sibling list endpoints use) — the caller saw "no matches"
        # for a query the server never ran. ``q`` is documented as required,
        # so the honest answer is 400.
        #
        # BREAKING for any caller that relied on the empty-200; the two
        # in-repo callers (frontend/src/api/search.ts via SidebarNavigation
        # and ImpactView) both guard on ``query.trim()`` and never send one.
        # Deliberately scoped to ``q`` alone: rejecting *every* unknown query
        # parameter API-wide would break far more callers than it helps.
        query, error = require_non_empty_param(
            request.query_params.get("q"), lang, name="q"
        )
        if error is not None:
            return error

        # Parse type filter (may be repeated)
        type_filter = request.query_params.getlist("type") or None
        mode = (request.query_params.get("mode") or "hybrid").strip().lower()

        # Issue #18 (scope A): optional AI summary of the returned hits.
        try:
            include_summary = bool(
                parse_bool_param(request.query_params, "include_summary", default=False)
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse pagination
        try:
            page = int(request.query_params.get("page", "1"))
            limit = int(request.query_params.get("limit", "20"))
        except ValueError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="page and limit must be integers"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            result = SearchService().search(
                query=query,
                ctx=ctx,
                workspace_id=workspace_id,
                type_filter=type_filter,
                page=page,
                limit=limit,
                mode=mode,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        # Serialize SearchHit dataclasses to dicts
        serialized_hits = [
            {
                "id": hit.id,
                "artifact_type": hit.artifact_type,
                "title": hit.title,
                "description": hit.description,
                "relevance_score": hit.relevance_score,
                "workspace_id": hit.workspace_id,
            }
            for hit in result.results
        ]
        payload: dict[str, Any] = {
            "results": serialized_hits,
            "total_count": result.total_count,
            "page": result.page,
            "limit": result.limit,
            "query": result.query,
            "mode": mode,
            # T-A2-7: additive contract; a Qdrant outage still answers 200.
            "vector_backend": result.vector_backend,
            "degraded": result.degraded,
            "degraded_reason": result.degraded_reason,
        }
        if include_summary:
            # Issue #18: opt-in only; a provider failure degrades instead of
            # failing the search (ai_summary=None, summary_degraded=True).
            from application.search_summary_service import SearchSummaryService

            summary = SearchSummaryService().summarize(
                query=query, hits=result.results, ctx=ctx
            )
            payload["ai_summary"] = summary.text
            payload["summary_degraded"] = summary.degraded
        return Response(payload)



# ---------------------------------------------------------------------------
# CsvImportView — COMP-AS-009 REST facade (REQ-L0-013, REQ-L2-AS-014)
# ---------------------------------------------------------------------------


def _apply_import_deprecation_headers(response: Response) -> Response:
    """Mark a legacy import-contract response as deprecated (ADR-014 §5).

    The **legacy** (``IMPORT_CONTRACT_V2=false``) response is the deprecated
    side of the 3-phase window — it is removed in phase 3 — so it advertises
    ``Deprecation: true`` and the ``Sunset`` HTTP-date. The boolean ``true`` is
    the earlier IETF draft syntax (``draft-ietf-httpapi-deprecation-header``):
    RFC 9745 later defined ``Deprecation`` as an HTTP-date, but ``true`` is kept
    here for consistency with the rest of the API (ADR-014 §5). The v2
    responses are the replacement and are deliberately *not* marked. Same
    response-mutation pattern as ``HealthAliasView`` (ADR-010 §3); the sunset
    date is the ADR frontmatter value, formatted via the shared helper rather
    than duplicated as a literal.
    """
    response["Deprecation"] = "true"
    response["Sunset"] = sunset_header_value(
        getattr(settings, "IMPORT_CONTRACT_SUNSET", "2026-12-31")
    )
    return response



def _idempotency_conflict_response(
    conflict: IdempotencyConflict, lang: str
) -> Response:
    """Map an :class:`IdempotencyConflict` to 409 + stable cause code."""
    resp = Response(
        build_error_response(conflict.code, lang, message=str(conflict)),
        status=status.HTTP_409_CONFLICT,
    )
    if conflict.retry_after is not None:
        resp["Retry-After"] = str(conflict.retry_after)
    return resp



def _begin_import_idempotency(
    request: Request,
    ctx: Any,
    lang: str,
    raw_body: bytes,
    endpoint: str,
    fingerprint_extra: str,
) -> tuple[str | None, str | None, Response | None]:
    """Validate the optional Idempotency-Key and open its claim (ADR-014 §3).

    Returns ``(key, fingerprint, None)`` when the request may proceed, and
    ``(None, None, response)`` with the response to return instead: 400 for a
    malformed key, 409 ``IdempotencyConflict`` for a reused/in-flight key, or
    the cached replay for a completed key (``idempotent_replay: true`` at the
    stored status). Without the header no claim is opened — all three values
    stay ``None``.
    """
    raw_key = request.headers.get("Idempotency-Key")
    if raw_key is None:
        return None, None, None
    idem_key = raw_key
    if not idem_key or len(idem_key) > 255:
        return (
            None,
            None,
            Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="Idempotency-Key must contain 1 to 255 characters.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    fingerprint = compute_fingerprint(
        method="POST",
        path=request.path,
        payload=raw_body,
        extra=fingerprint_extra,
    )
    try:
        cached = begin_idempotency_key(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            endpoint=endpoint,
            key=idem_key,
            fingerprint=fingerprint,
        )
    except IdempotencyConflict as conflict:
        return None, None, _idempotency_conflict_response(conflict, lang)
    if cached is not None:
        body = dict(cached.body or {})
        body["idempotent_replay"] = True
        return None, None, Response(body, status=cached.status_code)
    return idem_key, fingerprint, None



def _finalize_import_idempotency(
    ctx: Any,
    endpoint: str,
    idem_key: str | None,
    fingerprint: str | None,
    success: bool,
    http_status: int,
    body: dict[str, Any],
) -> None:
    """Cache a terminal import reply or release its claim (ADR-014 §3).

    Only terminal successes are replayable; every other outcome aborts the
    claim so the client can retry with the same key.
    """
    if not idem_key:
        return
    if success:
        finalize_idempotency_success(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            endpoint=endpoint,
            key=idem_key,
            fingerprint=fingerprint,
            status_code=http_status,
            body=body,
        )
    else:
        abort_idempotency_key(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            endpoint=endpoint,
            key=idem_key,
        )



def _abort_import_idempotency(
    ctx: Any, endpoint: str, idem_key: str | None
) -> None:
    """Release a failed import's idempotency claim (ADR-014 §3)."""
    if idem_key:
        abort_idempotency_key(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            endpoint=endpoint,
            key=idem_key,
        )



class CsvImportView(APIView):
    """POST /api/v1/workspaces/{id}/import/csv/ — Bulk CSV import.

    REQ-L0-013: Effiziente Übernahme bestehender Anforderungsdaten.
    REQ-L2-AS-014: CSV Bulk Import (ApplicationService layer).
    REQ-L2-RF-016: Frontend CSV import UI.

    Body: multipart/form-data with:
        - ``file``: CSV file (RFC 4180, UTF-8, optional UTF-8 BOM).
        - ``entity_type``: "Requirement" | "ArchitectureElement" | "TestCase"

    Headers (contract v2 only, ADR-014 §3):
        - ``Idempotency-Key`` (optional, opaque, ≤ 255 chars): a replay of the
          same payload returns the cached body with ``idempotent_replay: true``
          and the same status; a different payload on the same key is 409
          ``IDEMPOTENCY_KEY_REUSED``.

    Returns:
        Contract v2 (ADR-014 §2, default): 201 when ``succeeded > 0`` and
        nothing failed, 200 for a purely-skipped (duplicate-only) import, 207
        for a partial success and 422 when every row failed.

        Legacy (``IMPORT_CONTRACT_V2=false``): 201 on success, 400 on
        validation failure — the pre-ADR response shape, plus ``Deprecation``
        and ``Sunset`` headers marking that path as deprecated (ADR-014 §5).
        ADR-014 §5 / issue #1178: the legacy body additionally carries a
        ``skipped`` list (row, identifier, kind, status, cause) for the rows the
        natural-key dedupe skipped. The key is additive — no pre-existing key
        was renamed or removed.
    """

    _VALID_ENTITY_TYPES = {"Requirement", "ArchitectureElement", "TestCase"}
    _IDEMPOTENCY_ENDPOINT = "workspace-csv-import"

    def _parse_csv_upload(
        self, request: Request, lang: str
    ) -> tuple[str | None, str | None, bytes | None, Response | None]:
        """Validate ``entity_type``/file and decode the CSV payload.

        Returns ``(entity_type, csv_text, raw_body, None)`` on success, or
        ``(None, None, None, response)`` with the first request-level 400
        (ADR-014 §2). The raw bytes are returned besides the decoded text
        because they feed the idempotency fingerprint.
        """

        def _reject(message: str) -> tuple[str | None, str | None, bytes | None, Response | None]:
            return (
                None,
                None,
                None,
                Response(
                    build_error_response("VALIDATION_ERROR", lang, message=message),
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )

        entity_type = request.data.get("entity_type")
        if not entity_type:
            return _reject(
                "entity_type is required. Allowed: Requirement, ArchitectureElement, TestCase"
            )
        if entity_type not in self._VALID_ENTITY_TYPES:
            return _reject(
                f"Unsupported entity_type '{entity_type}'. Allowed: {sorted(self._VALID_ENTITY_TYPES)}"
            )

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return _reject(
                "No CSV file uploaded. Provide a 'file' field in multipart/form-data."
            )

        # ADR-014 §2: read the raw bytes once; they also feed the idempotency
        # fingerprint. Unreadable/0-byte bodies are request-level 400.
        try:
            raw_body = uploaded_file.read()
        except Exception:
            logger.exception("CsvImportView: failed to read uploaded file")
            return _reject("CSV file could not be read.")

        if not raw_body:
            return _reject("CSV file is empty.")

        # Finding 083: decode with ``utf-8-sig`` so an Excel-exported BOM is
        # stripped instead of corrupting the first header cell ("\ufefftitle").
        # ``utf-8-sig`` is identical to ``utf-8`` for a BOM-less file.
        try:
            csv_text = raw_body.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _reject("CSV file must be UTF-8 encoded.")

        if not csv_text.strip():
            return _reject("CSV file is empty.")

        return entity_type, csv_text, raw_body, None

    def _run_csv_import(
        self,
        csv_text: str,
        entity_type: str,
        workspace_id: str,
        ctx: Any,
        lang: str,
        idem_key: str | None,
    ) -> tuple[Any, Response | None]:
        """Run ImportService.import_csv and map failures to Responses.

        Returns ``(result, None)`` on success and ``(None, response)`` for
        ValidationError (400), NotFoundError/PermissionDeniedError (service
        mapping) and unhandled exceptions (logged, service mapping). Every
        failure releases the open idempotency claim (ADR-014 §3).
        """
        try:
            svc = ImportService()
            return (
                svc.import_csv(
                    csv_text=csv_text,
                    entity_type=entity_type,
                    workspace_id=workspace_id,
                    ctx=ctx,
                ),
                None,
            )
        except ValidationError as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            return None, Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            return None, _service_error_response(exc, lang)
        except Exception as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            logger.exception("CsvImportView: unhandled exception")
            return None, _service_error_response(exc, lang)

    @staticmethod
    def _csv_import_status(counts: dict[str, int]) -> int:
        """Map ADR-014 §2 import counts to the contract-v2 HTTP status."""
        if counts["failed"] == 0:
            return (
                status.HTTP_201_CREATED
                if counts["succeeded"] > 0
                else status.HTTP_200_OK
            )
        return (
            status.HTTP_207_MULTI_STATUS
            if counts["succeeded"] > 0
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    @extend_schema(
        # INT-06 finding 078 + #1388/M3: the import reads request.FILES, so the
        # only media type the runtime accepts is multipart/form-data. Declaring
        # the serializer alone let drf-spectacular enumerate every configured
        # parser (JSON and urlencoded too), advertising two request encodings
        # the view answers 400 for. The dict form keys the body by media type,
        # so exactly one encoding is published — schema-only, no parser change.
        request={
            "multipart/form-data": inline_serializer(
                name="CsvImportUpload",
                fields={
                    "file": serializers.FileField(
                        help_text="CSV file (RFC 4180, UTF-8, optional UTF-8 BOM)."
                    ),
                    "entity_type": serializers.CharField(
                        help_text=(
                            "Target entity type: 'Requirement', "
                            "'ArchitectureElement' or 'TestCase'."
                        ),
                    ),
                },
            ),
        },
        # ADR-014 §2 status mapping: 201 all-succeeded, 200 duplicate-only,
        # 207 partial success, 422 every row failed. The concrete code is
        # derived from the row counts, and all four carry the same report.
        responses={
            200: CsvImportReportSerializer,
            201: CsvImportReportSerializer,
            207: CsvImportReportSerializer,
            422: CsvImportReportSerializer,
        },
    )
    def post(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """Handle CSV import POST request."""
        lang = detect_lang(request)

        # --- Validate workspace param ---
        if not pk:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Workspace ID is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        contract_v2 = bool(getattr(settings, "IMPORT_CONTRACT_V2", False))

        entity_type, csv_text, raw_body, upload_error = self._parse_csv_upload(
            request, lang
        )
        if upload_error is not None:
            return upload_error

        # --- Optional Idempotency-Key (ADR-014 §3, contract v2) ---
        idem_key = None
        fingerprint = None
        if contract_v2:
            idem_key, fingerprint, idem_error = _begin_import_idempotency(
                request,
                ctx,
                lang,
                raw_body=raw_body,
                endpoint=self._IDEMPOTENCY_ENDPOINT,
                fingerprint_extra=f"entity_type={entity_type}",
            )
            if idem_error is not None:
                return idem_error

        # --- Delegate to ImportService ---
        result, import_error = self._run_csv_import(
            csv_text, entity_type, pk, ctx, lang, idem_key
        )
        if import_error is not None:
            return import_error

        result.request_id = result.request_id or str(uuid.uuid4())

        # --- Legacy response (ADR-014 §5 Phase 1 rollback, default) ---
        if not contract_v2:
            # Issue #1178: ``skipped_count`` counted the outcome but named no
            # cause, so a client on the legacy contract could not tell a
            # skipped duplicate from a dropped row. The skipped rows are added
            # as a NEW key (``skipped``) that reuses the very same item dicts
            # ``result.to_dict()`` hands to contract v2 — one representation,
            # ordered by row number. Purely additive: every pre-existing key
            # keeps its name and meaning, and the HTTP status mapping is
            # untouched.
            skipped_rows = sorted(
                (
                    item
                    for item in result.items
                    if item.get("status") == "skipped"
                ),
                key=lambda item: item.get("row", 0),
            )
            legacy_body = {
                "success": result.success,
                "imported_count": result.imported_count,
                "skipped_count": result.skipped_count,
                "status": result.status,
                "skipped": [dict(item) for item in skipped_rows],
                "errors": [
                    {
                        "row_number": e.row_number,
                        "field": e.field,
                        "message": e.message,
                    }
                    for e in result.errors
                ],
                "warnings": result.warnings,
            }
            http_status = (
                status.HTTP_201_CREATED if result.success else status.HTTP_400_BAD_REQUEST
            )
            return _apply_import_deprecation_headers(
                Response(legacy_body, status=http_status)
            )

        # --- Contract v2 response (ADR-014 §2) ---
        body = result.to_dict()
        http_status = self._csv_import_status(result.counts)

        _finalize_import_idempotency(
            ctx,
            self._IDEMPOTENCY_ENDPOINT,
            idem_key,
            fingerprint,
            result.success,
            http_status,
            body,
        )

        return Response(body, status=http_status)



# ---------------------------------------------------------------------------
# CsvExportView — COMP-AS-008 REST facade (REQ-L3-EXP-002)
# ---------------------------------------------------------------------------


class CsvExportView(APIView):
    """GET /api/v1/workspaces/{id}/export/csv/ — Bulk CSV export.

    REQ-L3-EXP-002: CSV export (ApplicationService layer, COMP-AS-008).
    C7 (frontend-feedback Cluster C): MVP CSV export for Requirement,
    StakeholderNeed, ArchitectureElement — wires the existing ExportService
    (already implemented, previously not exposed via REST) to a workspace-
    scoped endpoint, mirroring CsvImportView above.

    Query params:
        - ``entity_type``: "Requirement" | "StakeholderNeed" | "ArchitectureElement"
          | "TestCase"

    Returns:
        200 with CSV file (Content-Disposition: attachment).
        400 on missing/invalid entity_type.
    """

    _VALID_ENTITY_TYPES = {
        "Requirement",
        "StakeholderNeed",
        "ArchitectureElement",
        "TestCase",
    }

    @extend_schema(
        # #1388/M3: the runtime answers a text/csv attachment, not JSON. The
        # undiscovered serializer used to publish the permissive JSON object,
        # so a generated client parsed the file as JSON. ``entity_type`` is the
        # only query parameter the handler reads.
        parameters=[
            OpenApiParameter(
                name="entity_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description=(
                    "Entity type to export: Requirement, StakeholderNeed, "
                    "ArchitectureElement or TestCase."
                ),
            ),
        ],
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request: Request, pk: str = None, **kwargs: Any) -> HttpResponse | Response:
        """Handle CSV export GET request."""
        lang = detect_lang(request)

        if not pk:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Workspace ID is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        entity_type = request.query_params.get("entity_type")
        if not entity_type:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message=(
                        "entity_type is required. Allowed: "
                        f"{sorted(self._VALID_ENTITY_TYPES)}"
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if entity_type not in self._VALID_ENTITY_TYPES:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message=f"Unsupported entity_type '{entity_type}'. Allowed: {sorted(self._VALID_ENTITY_TYPES)}",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            svc = ExportService()
            result = svc.export_csv(
                entity_type=entity_type,
                workspace_id=pk,
                ctx=ctx,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("CsvExportView: unhandled exception")
            return _service_error_response(exc, lang)

        response = HttpResponse(result.content, content_type=result.media_type)
        response["Content-Disposition"] = f'attachment; filename="{result.filename}"'
        return response



# ---------------------------------------------------------------------------
# ReqifExportView — COMP-AS-008 REST facade (REQ-146)
# ---------------------------------------------------------------------------


class ReqifExportView(APIView):
    """GET /api/v1/workspaces/{id}/export/reqif/ — ReqIF 1.2 workspace export.

    REQ-146: Exports the workspace's StakeholderNeeds, Requirements, and
    TraceLinks between them as a ReqIF 1.2 XML document (DOORS/Polarion
    interoperability). Mirrors CsvExportView's RBAC/auth handling; wires
    application.reqif_export_service.ReqifExportService.

    Returns:
        200 with a ReqIF XML document (Content-Disposition: attachment,
        filename "<workspace-slug>.reqif").
        404 if the workspace does not exist in the active tenant.
    """

    @extend_schema(
        # INT-06 finding 078: the export returns an XML document, but the
        # generated schema advertised "No response body" — a generated client
        # could not know the media type. Declare it explicitly.
        responses={
            # drf-spectacular's tuple-key form `(status, media_type)` is the
            # supported way to pin a non-JSON media type (the APIView's default
            # renderer is JSON, so the export was documented as "No response
            # body"). The export genuinely serves application/xml.
            (200, "application/xml"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description=(
                    "ReqIF 1.2 XML document "
                    "(Content-Disposition: attachment; filename \"<slug>.reqif\")."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Workspace ID is required (unreachable via the URL route).",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Workspace not found in the active tenant.",
            ),
        },
        description=(
            "Handle ReqIF export GET request.\n\n"
            "Returns `application/xml` (ReqIF 1.2 document). Errors use the "
            "standard error envelope and carry `request_id` (ADR-014 §1)."
        ),
    )
    def get(self, request: Request, pk: str = None, **kwargs: Any) -> HttpResponse | Response:
        """Handle ReqIF export GET request."""
        lang = detect_lang(request)

        if not pk:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Workspace ID is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        try:
            svc = ReqifExportService()
            result = svc.export_reqif(workspace_id=pk, ctx=ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("ReqifExportView: unhandled exception")
            return _service_error_response(exc, lang)

        response = HttpResponse(result.content, content_type=result.media_type)
        response["Content-Disposition"] = f'attachment; filename="{result.filename}"'
        return response



# ---------------------------------------------------------------------------
# ReqifImportView — COMP-AS-008b REST facade (REQ-147)
# ---------------------------------------------------------------------------


class ReqifImportView(APIView):
    """POST /api/v1/workspaces/{id}/import/reqif/ — ReqIF 1.2 import.

    REQ-147: Imports a ReqIF 1.2 XML document (DOORS/Polarion
    interoperability) into the workspace's StakeholderNeeds, Requirements,
    and TraceLinks — the inverse of ReqifExportView (REQ-146). Mirrors
    CsvImportView's multipart upload handling and RBAC; wires
    application.reqif_import_service.ReqifImportService.

    Body: multipart/form-data with:
        - ``file``: ReqIF 1.2 XML file (.reqif / .xml, UTF-8).
        - ``entity_type``: optional; if present it must name a known entity
          type, otherwise the request is rejected with 400.

    Query params:
        - ``dry_run``: "true" | "false" (default "false"). When true, the
          whole import pipeline runs and is rolled back — the response
          report reflects what a real import would do without persisting.

    Headers:
        - ``Idempotency-Key`` (optional, opaque, ≤ 255 chars): the first call
          stores a terminal success; a replay returns the same body/status with
          ``idempotent_replay: true``. A different payload on the same key is
          ``409 IDEMPOTENCY_KEY_REUSED``; a concurrent call is ``409
          IDEMPOTENCY_IN_FLIGHT`` + ``Retry-After`` (ADR-014 §3).

    Returns (ADR-014 §2, contract v2):
        200 — ``failed == 0`` (success, with or without write effect; a
              skipped-only document is a success, never a Created).
        207 Multi-Status — ``succeeded > 0 and failed > 0`` (partial success).
        422 — ``failed > 0 and succeeded == 0`` (total object failure) or a
              file-level ``PARSE_ERROR`` (invalid .reqif XML, REQ-L2-RQ-001 AC5).
        400 — request-level: missing/0-byte file, unknown ``entity_type``,
              size limit, unreadable body, overlong ``Idempotency-Key``.
        409 — idempotency key reused / in flight.

    The legacy ``needs``/``requirements``/``relations`` keys stay additive
    during the deprecation window (§5). Set ``IMPORT_CONTRACT_V2=false`` to
    fall back to the pre-ADR response (``success`` always True, HTTP 200); that
    legacy response carries ``Deprecation``/``Sunset`` headers (ADR-014 §5).
    """

    _VALID_ENTITY_TYPES = {
        "Requirement",
        "StakeholderNeed",
        "ArchitectureElement",
        "TestCase",
    }
    #: Types the ReqIF importer actually derives from the file. The other
    #: members of ``_VALID_ENTITY_TYPES`` have no ReqIF path, so accepting them
    #: would be a silent no-op (F10) — they are refused instead.
    _REQIF_ENTITY_TYPES = {"Requirement", "StakeholderNeed"}
    _IDEMPOTENCY_ENDPOINT = "workspace-reqif-import"

    def _parse_reqif_request(
        self, request: Request, lang: str, contract_v2: bool
    ) -> tuple[str | None, bytes | None, Response | None]:
        """Validate the ReqIF upload and decode it.

        ADR-014 §2: unreadable/0-byte/non-UTF-8 bodies are request-level
        400s. Returns ``(reqif_text, raw_body, None)`` on success, or
        ``(None, None, response)`` with the first request-level 400; the raw
        bytes feed the idempotency fingerprint.
        """

        def _reject(message: str) -> tuple[str | None, bytes | None, Response | None]:
            return (
                None,
                None,
                Response(
                    _with_request_id(
                        build_error_response("VALIDATION_ERROR", lang, message=message)
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )

        # ADR-014 §5: entity_type handling belongs to the v2 contract. Under
        # the legacy rollback (IMPORT_CONTRACT_V2=false) the field is ignored
        # exactly as it was before v2, so the rollback is complete.
        if contract_v2:
            # ADR-014 §2: a ReqIF file derives its own entity type, so the
            # field is accepted only for compatibility. Only types the ReqIF
            # importer can actually act on are accepted — the pre-v2 allowlist
            # contained types with no ReqIF path, where the field was a silent
            # no-op. An unknown *or* ineffective type is a request-level 400.
            entity_type = request.data.get("entity_type")
            if entity_type is not None and entity_type not in self._REQIF_ENTITY_TYPES:
                return _reject(
                    f"Unsupported entity_type '{entity_type}' for ReqIF "
                    f"import. Allowed: {sorted(self._REQIF_ENTITY_TYPES)}"
                )

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return _reject(
                "No ReqIF file uploaded. Provide a 'file' field in multipart/form-data."
            )

        # ADR-014 §2: unreadable/0-byte body is a request-level 400. Read the
        # raw bytes once — they also feed the idempotency fingerprint.
        try:
            raw_body = uploaded_file.read()
        except Exception:
            logger.exception("ReqifImportView: failed to read uploaded file")
            return _reject("ReqIF file could not be read.")
        if not raw_body:
            return _reject("ReqIF file is empty.")
        try:
            reqif_text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return _reject("ReqIF file must be UTF-8 encoded.")

        if not reqif_text.strip():
            return _reject("ReqIF file is empty.")

        return reqif_text, raw_body, None

    def _run_reqif_import(
        self,
        reqif_text: str,
        workspace_id: str,
        ctx: Any,
        lang: str,
        dry_run: bool,
        idem_key: str | None,
    ) -> tuple[Any, Response | None]:
        """Run ReqifImportService.import_reqif and map failures to Responses.

        ADR-014 §2 maps a file-level ``ReqifParseError`` to 422 ``PARSE_ERROR``
        under contract v2 and to 400 under the legacy rollback (§5). Other
        failures follow the service mapping; every failure releases the open
        idempotency claim (ADR-014 §3). Returns ``(result, None)`` on success
        and ``(None, response)`` otherwise.
        """
        contract_v2 = bool(getattr(settings, "IMPORT_CONTRACT_V2", False))
        try:
            svc = ReqifImportService()
            return (
                svc.import_reqif(
                    reqif_text=reqif_text,
                    workspace_id=workspace_id,
                    ctx=ctx,
                    dry_run=dry_run,
                ),
                None,
            )
        except ReqifParseError as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            if contract_v2:
                # ADR-014 §2: file-level parse error -> 422 PARSE_ERROR.
                parse_result = ReqifImportResult.parse_failure(
                    str(exc), dry_run=dry_run, request_id=str(uuid.uuid4())
                )
                return None, Response(
                    parse_result.to_dict(),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return None, Response(
                _with_request_id(
                    build_error_response("VALIDATION_ERROR", lang, message=str(exc))
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            return None, Response(
                _with_request_id(
                    build_error_response("VALIDATION_ERROR", lang, message=str(exc))
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            return None, _service_error_response(exc, lang)
        except Exception as exc:
            _abort_import_idempotency(ctx, self._IDEMPOTENCY_ENDPOINT, idem_key)
            logger.exception("ReqifImportView: unhandled exception")
            return None, _service_error_response(exc, lang)

    @extend_schema(
        # INT-06 finding 078: the import reads request.FILES, but the generated
        # schema declared no requestBody at all — a generated client could not
        # know how to send the file.
        request=OpenApiRequest(
            request=inline_serializer(
                name="ReqifImportUpload",
                fields={
                    "file": serializers.FileField(
                        help_text="ReqIF 1.2 XML file (.reqif / .xml, UTF-8)."
                    ),
                    "entity_type": serializers.CharField(
                        required=False,
                        help_text=(
                            "Optional; if present must be 'Requirement' or "
                            "'StakeholderNeed'."
                        ),
                    ),
                },
            ),
            # The view reads request.FILES, i.e. multipart/form-data only.
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=str,
                location=OpenApiParameter.PATH,
                description="Workspace UUID.",
            ),
            OpenApiParameter(
                name="dry_run",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "When true the whole import pipeline runs and is rolled "
                    "back; the report reflects what a real import would do."
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Import result (ADR-014 contract v2): success "
                    "(`failed == 0`), with or without write effect. Body: "
                    "`success` (bool, `true`), `contract` (`\"v2\"`), "
                    "`dry_run` (bool), `counts` (object with `succeeded`, "
                    "`skipped`, `failed`, `total`), `items` (array of objects "
                    "with `row`, `identifier`, `kind`, `status` and "
                    "`cause: {code, message}`), `warnings` (array of strings), "
                    "`idempotent_replay` (bool), `request_id` (string) and the "
                    "legacy additive `needs`/`requirements`/`relations` reports. "
                    "With `IMPORT_CONTRACT_V2=false` the pre-ADR body is "
                    "returned instead (`success` always `true`)."
                ),
            ),
            207: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Partial success (ADR-014 §2): `succeeded > 0` and "
                    "`failed > 0`. Same v2 envelope as the 200 with "
                    "`success: false`, `counts.failed > 0` and no `counts` "
                    "entry counted twice (`succeeded + skipped + failed == "
                    "total`); `items` pinpoints every rejected object."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Request-level error: missing/0-byte file, unknown "
                    "`entity_type`, size limit, unreadable body, overlong "
                    "`Idempotency-Key`."
                ),
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Idempotency-Key reused (`IDEMPOTENCY_KEY_REUSED`) or in "
                    "flight (`IDEMPOTENCY_IN_FLIGHT`)."
                ),
            ),
            422: OpenApiResponse(
                response=None,
                description=(
                    "Total object failure (ADR-014 §2) or a file-level "
                    "`PARSE_ERROR` (invalid .reqif XML, REQ-L2-RQ-001 AC5)."
                ),
            ),
            500: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Internal server error.",
            ),
        },
    )
    def post(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """Handle ReqIF import POST request.

        Every response body uses the standard error envelope on failure and
        carries ``request_id`` (ADR-014 §1, mirrored from ``X-Request-ID``) so
        a client can correlate a failed import with the server log.
        """
        lang = detect_lang(request)

        if not pk:
            return Response(
                _with_request_id(
                    build_error_response(
                        "VALIDATION_ERROR", lang, message="Workspace ID is required"
                    )
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        # ADR-014 §5: entity_type handling belongs to the v2 contract. Under
        # the legacy rollback (IMPORT_CONTRACT_V2=false) the field is ignored
        # exactly as it was before v2, so the rollback is complete.
        contract_v2 = bool(getattr(settings, "IMPORT_CONTRACT_V2", False))

        reqif_text, raw_body, upload_error = self._parse_reqif_request(
            request, lang, contract_v2
        )
        if upload_error is not None:
            return upload_error

        dry_run_raw = request.query_params.get("dry_run", "false")
        dry_run = str(dry_run_raw).strip().lower() in ("1", "true", "yes")

        # --- Optional Idempotency-Key (ADR-014 §3) ---
        idem_key = None
        fingerprint = None
        if contract_v2:
            idem_key, fingerprint, idem_error = _begin_import_idempotency(
                request,
                ctx,
                lang,
                raw_body=raw_body,
                endpoint=self._IDEMPOTENCY_ENDPOINT,
                fingerprint_extra=f"dry_run={dry_run}",
            )
            if idem_error is not None:
                return idem_error

        result, import_error = self._run_reqif_import(
            reqif_text, pk, ctx, lang, dry_run, idem_key
        )
        if import_error is not None:
            return import_error

        if not contract_v2:
            # ADR-014 §5 rollback: the pre-v2 response (success hard True, 200),
            # marked deprecated via the Deprecation/Sunset headers.
            legacy_body = {
                "success": True,
                "dry_run": result.dry_run,
                "needs": result.needs.to_dict(),
                "requirements": result.requirements.to_dict(),
                "relations": result.relations.to_dict(),
                "warnings": result.warnings,
            }
            return _apply_import_deprecation_headers(
                Response(legacy_body, status=status.HTTP_200_OK)
            )

        body = result.to_dict()
        http_status = result.http_status

        _finalize_import_idempotency(
            ctx,
            self._IDEMPOTENCY_ENDPOINT,
            idem_key,
            fingerprint,
            result.success,
            http_status,
            body,
        )

        return Response(body, status=http_status)
