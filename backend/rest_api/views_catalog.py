"""
COMP-RA-001 HttpEndpointController — views_catalog — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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
    _parse_derivation_mode_policy,
    _service_error_response,
    list_schema,
    soft_delete_schema,
)




class BundleCompressionStatusView(APIView):
    """GET /api/v1/bundle-compression-status/{task_id}/

    Requirement Bundle Export, Plan 2 Task 4: polls the Celery task
    dispatched by ``requirement_bundle``'s ``?mode=compressed&async=true``
    branch. Follows ``AttributeSchemaView``'s bare-``APIView`` pattern
    (Plan 1 Task 5) since this is not a CRUD resource.

    Response shape (issue #448)::

        {"task_id": str,
         "status": "pending"|"running"|"done"|"failed"|"not_found",
         "text": str|null,           # completion, mirrors ?mode=compressed
         "is_mock_fallback": bool,
         "provider": str|null,
         "error": str|null,
         "result": dict|null}        # DEPRECATED raw Celery envelope

    ``result`` is the pre-existing, doubly nested ``{"result": "<text>"}``
    envelope; it is retained so existing clients keep working, but new
    clients must read ``text``.
    """

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=BundleCompressionStatusSerializer,
                description=(
                    "The task's state; `text` carries the compressed bundle "
                    "once status='done'."
                ),
            ),
        },
    )
    def get(self, request: Request, task_id: str, **kwargs: Any) -> Response:
        import dataclasses

        from application.bundle_compression_service import BundleCompressionService

        ctx = get_auth_context(request)
        result = BundleCompressionService().get_compression_status(ctx, task_id)
        return Response(dataclasses.asdict(result))



class ConsistencyStatusView(APIView):
    """GET /api/v1/consistency-status/{task_id}/

    GH-796: polls the Celery task dispatched by ``requirement.check_consistency``
    (MCP) / the equivalent application-service call. Before this view existed,
    a caller received a ``task_id`` from ``check_consistency`` with no REST or
    MCP endpoint to ever retrieve the result (orphan task). Follows
    ``BundleCompressionStatusView``'s bare-``APIView`` polling pattern.

    Response shape::

        {"task_id": str,
         "status": "pending"|"running"|"done"|"failed"|"not_found",
         "result": dict|null,   # present when status == "done"
         "error": str|null}     # present when status == "failed"

    An unknown or foreign-tenant task_id reports ``status="not_found"``
    (ADR-03) rather than a 403/404, so a cross-tenant probe cannot learn
    "this task_id exists but isn't mine".
    """

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=ConsistencyStatusSerializer,
                description=(
                    "The task's state; `result` is present when status='done', "
                    "`error` when status='failed'."
                ),
            ),
        },
    )
    def get(self, request: Request, task_id: str, **kwargs: Any) -> Response:
        from application.requirement_service import RequirementService

        ctx = get_auth_context(request)
        result = RequirementService().get_consistency_status(task_id, ctx)
        return Response(result)



class GlossaryTermViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Semantic Project Glossary (REQ-L1-044).

    REQ-173: transitions/ and workflow-history/ via WorkflowTransitionsMixin
    so glossary terms share the same lifecycle machinery as every other
    artifact type.
    """

    serializer_class = GlossaryTermSerializer
    workflow_item_type = "GlossaryTerm"
    attribute_item_type = "GlossaryTerm"

    def _svc(self) -> GlossaryService:
        return GlossaryService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        term = self._svc().get(ctx, UUID(pk))
        return term.id, term.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        # #831: the Glossary serializer now exposes ``status`` like every other
        # artifact, so ``_validate_patch_payload``'s ``status`` branch can run
        # its full guard: an unchanged echo is accepted, a differing value is
        # refused with a pointer at POST .../transitions/. Without this override
        # ``current`` would be None (the mixin default) and a real status change
        # via PATCH would be silently accepted-and-ignored.
        return getattr(self._svc().get(ctx, UUID(pk)), "status", None)

    @list_schema(status=True, search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/glossary/ — list GlossaryTerms in a workspace.

        REQ-006: Excludes soft-deleted terms by default.
        Pass ?include_deleted=true for admin/audit access.
        """
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"),
            lang,
        )
        if error is not None:
            return error

        try:
            # REQ-006: include_deleted=true exposes soft-deleted terms (admin use)
            include_deleted = parse_include_deleted(request.query_params)
            terms = self._svc().list_by_workspace(
                ctx,
                workspace_id,
                include_deleted=include_deleted,
                status=request.query_params.get("status") or None,
                search=request.query_params.get("search") or None,
            )
        except Exception as e:
            logger.exception("Error in GlossaryTermViewSet.list")
            return _service_error_response(e, lang)

        # INT-05 (AUD-2026-09-073): the pagination call is deliberately kept
        # *outside* the ``try/except Exception`` above — DRF's ``NotFound``
        # (invalid ``page``) must propagate to the framework as a **404**
        # instead of being caught by the broad handler and answered as a 500.
        # Mirrors ``WorkspaceViewSet.list``.
        return self._paginate(
            request, terms, lambda t: GlossaryTermSerializer(t).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        try:
            term_id = UUID(pk)
            term = self._svc().get(ctx, term_id)
            return Response(GlossaryTermSerializer(term).data)
        except Exception as e:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(e, lang)

    def create(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        try:
            # SA-25: run the declared serializer so term/definition/synonyms/
            # abbreviation are actually validated (max_length, JSON shape)
            # instead of being read straight off request.data. The XSS guard
            # itself already ran earlier in initial() (FreeTextSanitizationMixin,
            # #269/4) regardless of this call; this closes the remaining gap
            # (no type/length validation at all on this path).
            ser = GlossaryTermSerializer(data=request.data)
            if not ser.is_valid():
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[
                            {"field": k, "errors": v} for k, v in ser.errors.items()
                        ],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            data = ser.validated_data
            definition_error = self._validate_attribute_definition(
                ctx,
                data.get("workspace_id"),
                dict(request.data) if isinstance(request.data, dict) else {},
                None,
            )
            if definition_error is not None:
                return definition_error
            term = self._svc().create(
                ctx,
                data["workspace_id"],
                data["term"],
                data["definition"],
                data.get("synonyms"),
                data.get("abbreviation", ""),
                # REQ-L2-AS-037 / Epic #934 WS1: extended attributes.
                custom_fields=data.get("custom_fields"),
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on the
            # term's backing Artifact; the DTO exposes it via ``.artifact``.
            self._apply_artifact_system_fields(request, "GlossaryTerm", term, ctx)
            return Response(
                GlossaryTermSerializer(term).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(e, lang)

    @extend_schema(
        # #1358 (W12a): the action reads request.data directly (no model
        # serializer backs this payload), so the body is declared explicitly —
        # same pattern as the CSV/ReqIF uploads above.
        request=OpenApiRequest(
            request=inline_serializer(
                name="GlossaryDeriveRequest",
                fields={
                    "workspace_id": serializers.UUIDField(
                        help_text="Workspace UUID to scan for candidate terms."
                    ),
                    "mode": serializers.ChoiceField(
                        choices=["preview", "write"],
                        required=False,
                        default="preview",
                        help_text=(
                            "'preview' (default) returns drafts only and marks "
                            "the response `ephemeral: true`; 'write' is the "
                            "canonical persistence path (persists each draft "
                            "as a GlossaryTerm)."
                        ),
                    ),
                    "policy": serializers.ChoiceField(
                        choices=["manual", "auto"],
                        required=False,
                        default="manual",
                        help_text=(
                            "Only relevant for mode='write': 'manual' (default) "
                            "leaves new terms in their initial state; 'auto' "
                            "best-effort auto-advances them."
                        ),
                    ),
                },
            ),
        ),
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Ephemeral draft preview — persists nothing. Body: `drafts` "
                    "(array of objects with `term`, `definition`, `synonyms` "
                    "(array of strings) and `abbreviation`), `workspace_id` "
                    "(uuid string), `is_mock_fallback` (bool) and `ephemeral` "
                    "(always `true`)."
                ),
            ),
            201: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Write mode: the persistence receipt. Body: `written` "
                    "(array of objects with `id`, `term`, `status` and the "
                    "`proposal` block: `state`, `is_proposal`, `supported`, "
                    "`proposed_by`, `label`, `reason`), `is_mock_fallback` "
                    "(bool), plus `failed` (array of `{draft, error}`) only "
                    "when individual drafts were rejected."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Unknown field, malformed workspace_id, invalid mode/policy.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Caller lacks the editor role (POST requires WRITE).",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Workspace not found in the active tenant.",
            ),
            502: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="LLM_OUTPUT_INVALID — the provider answered unusably.",
            ),
            # #1416: provider failures are classified by cause, not answered as
            # an invalid output.
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="LLM_UNAVAILABLE — the provider is unreachable.",
            ),
            504: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="LLM_TIMEOUT — the provider timed out.",
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "LLM_TOKEN_LIMIT_EXCEEDED — the tenant's daily AI token "
                    "budget is exhausted."
                ),
            ),
        },
        description=(
            "AI glossary derivation for a workspace (REST parity with the MCP "
            "tool `ai_derivation.derive_glossary_from_workspace`, #1358).\n\n"
            "- `mode='preview'` (default): ephemeral drafts, nothing persisted.\n"
            "- `mode='write'`: persists each draft through "
            "`AiDerivationService.persist_glossary_drafts` (born `proposed` "
            "where the workspace's workflow supports it). No trace link is "
            "created."
        ),
    )
    @action(detail=False, methods=["post"], url_path="derive")
    def derive(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/glossary/derive/ — AI glossary term drafts (preview | write).

        Issue #1358 (W12a): REST parity for
        ``ai_derivation.derive_glossary_from_workspace``. The preview response
        is ephemeral (``"ephemeral": true``, #1358); ``mode="write"`` is the
        canonical persistence path and reuses the exact same write seam as the
        MCP tool (``AiDerivationService.persist_glossary_drafts`` →
        ``_write_glossary_term_draft``), so both transports persist
        identically (status ``proposed`` where the workspace's workflow
        supports it, see #1089).

        Body: ``{"workspace_id": <uuid>, "mode"?: "preview"|"write",
        "policy"?: "manual"|"auto"}``. Unknown keys are rejected (#851).
        """
        lang = detect_lang(request)
        invalid = reject_unknown_fields(
            request.data, {"workspace_id", "mode", "policy"}, lang
        )
        if invalid is not None:
            return invalid
        payload = request.data if isinstance(request.data, dict) else {}
        workspace_id, error = parse_workspace_id(payload.get("workspace_id"), lang)
        if error is not None:
            return error
        mode, policy, error = _parse_derivation_mode_policy(request, lang)
        if error is not None:
            return error

        try:
            from application.ai_derivation_service import AiDerivationService

            ctx = get_auth_context(request)
            service = AiDerivationService()
            preview = service.derive_glossary_from_workspace(ctx, workspace_id)
            if mode == "preview":
                return Response(preview, status=status.HTTP_200_OK)
            result = service.persist_glossary_drafts(
                ctx, workspace_id=workspace_id, preview=preview, policy=policy
            )
            return Response(result, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(e)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except NotFoundError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("GlossaryTermViewSet.derive: unhandled exception")
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=GlossaryTermSerializer,
            pk=pk,
            ctx=ctx,
        )
        if invalid is not None:
            return invalid
        # SA-25: partial=True means DRF only validates/returns keys actually
        # present in the body — matching update()'s "None = don't touch this
        # field" sentinel contract — while adding real validation for
        # whichever fields were supplied.
        ser = GlossaryTermSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            term_id = UUID(pk)
            data = ser.validated_data
            # REQ-L2-AS-037 / Epic #934 WS1: forward custom_fields only when the
            # client actually sent it — update()'s ``_UNSET`` sentinel then means
            # "leave unchanged" for an unrelated PATCH.
            update_kwargs: dict[str, Any] = {}
            if "custom_fields" in data:
                update_kwargs["custom_fields"] = data["custom_fields"]
            # #82: `term` was previously dropped here — PATCH silently
            # ignored the label field that POST accepts, so a term's name
            # could never be corrected after creation.
            term = self._svc().update(
                ctx,
                term_id,
                term=data.get("term"),
                definition=data.get("definition"),
                synonyms=data.get("synonyms"),
                abbreviation=data.get("abbreviation"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                **update_kwargs,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on the
            # term's backing Artifact; the DTO exposes it via ``.artifact``.
            self._apply_artifact_system_fields(request, "GlossaryTerm", term, ctx)
            return Response(GlossaryTermSerializer(term).data)
        except Exception as e:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(e, lang)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/glossary/{pk}/ — soft-delete a glossary term. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state) and a subsequent GET on this URL still
        answers 200 — 404 keeps meaning "no such record, and there never was
        one in this tenant". List endpoints hide outdated records by default;
        pass ``?include_deleted=true`` to see them, and
        ``POST .../reactivate/`` to restore one.

        Note the field name (#831): the detail response reports the soft-delete
        as ``status="outdated"``, identical to every other workflow-backed
        artifact. GlossaryTerm has no mirrored model ``status`` column
        (``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``), so the value is
        resolved from the DTO/backing Artifact rather than from a local column —
        but the wire key is ``status`` all the same.
        """
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        try:
            term_id = UUID(pk)
            self._svc().delete(ctx, term_id, change_reason=change_reason)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(e, lang)

    @action(detail=False, methods=["post"], url_path="references/resolve")
    def resolve_references(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/glossary/references/resolve/ — resolve tokens (#1266).

        Body: ``{workspace_id, text}``. Returns the workspace's reference mode
        plus one resolved entry per distinct ``(global_uuid, revision)`` token:
        term, definition at the resolved revision, head revision and drift flag.
        The renderer keeps the original text and swaps each token for a
        highlighted mark using this payload.
        """
        from application.glossary_reference_service import GlossaryReferenceService

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        text = request.data.get("text") or ""
        try:
            payload = GlossaryReferenceService().resolve_text(ctx, workspace_id, text)
        except Exception as exc:  # noqa: BLE001 — taxonomy handled below
            return _service_error_response(exc, lang)
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="references/insert")
    def insert_reference(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/glossary/references/insert/ — insert a reference (#1266).

        Body: ``{workspace_id, source_artifact_id, global_uuid}``. Creates the
        usage trace link (``uses-term`` when the workspace catalog still carries
        it, else ``references``) and returns the token to insert, pinned to the
        term's current revision unless the workspace is in ``always_head`` mode.
        """
        from application.glossary_reference_service import GlossaryReferenceService

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        source_artifact_id, error = parse_uuid_param(
            request.data.get("source_artifact_id"), lang, name="source_artifact_id"
        )
        if error is not None:
            return error
        global_uuid, error = parse_uuid_param(
            request.data.get("global_uuid"), lang, name="global_uuid"
        )
        if error is not None:
            return error
        try:
            payload = GlossaryReferenceService().insert_reference(
                ctx, workspace_id, source_artifact_id, global_uuid
            )
        except Exception as exc:  # noqa: BLE001 — taxonomy handled below
            return _service_error_response(exc, lang)
        return Response(payload, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="references/upgrade-to-head")
    def upgrade_references_to_head(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/glossary/references/upgrade-to-head/ — bulk re-pin (#1266).

        Body: ``{workspace_id, text}``. Rewrites every version-pinned token in
        *text* to its term's current head and returns ``{text, upgraded}`` — the
        "raise the version" bulk action for drifted references.
        """
        from application.glossary_reference_service import GlossaryReferenceService

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        text = request.data.get("text") or ""
        try:
            new_text, upgraded = GlossaryReferenceService().upgrade_text_to_head(
                ctx, workspace_id, text
            )
        except Exception as exc:  # noqa: BLE001 — taxonomy handled below
            return _service_error_response(exc, lang)
        return Response({"text": new_text, "upgraded": upgraded})

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/glossary/{pk}/versions/ — list revisions chronologically.

        REQ-142: delegates to ArtifactDiffService (COMP-AS-019). Task 29
        (Milestone M5): routes through the generic ``list_versions``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            term_id = UUID(pk)
            term = self._svc().get(ctx, term_id)

            result = ArtifactDiffService().list_versions(term.artifact_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/glossary/{pk}/diff/?from_version=0&to_version=2

        REQ-142: Structured field-level diff between two glossary term revisions.
        Delegates to ArtifactDiffService (COMP-AS-019); reuses the same
        diff computation as the requirement diff endpoint. Task 29 (Milestone
        M5): routes through the generic ``diff``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            term_id = UUID(pk)
            term = self._svc().get(ctx, term_id)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get("to_version", str(term.version))
            )

            result = ArtifactDiffService().diff(
                artifact_id=term.artifact_id,
                from_version=from_version,
                to_version=to_version,
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)



class AttributeSchemaView(APIView):
    """GET /api/v1/attribute-schema/?entity_type=<optional>&workspace_id=<uuid>

    Requirement Bundle Export, Plan 1 Task 5 / Task 4. Lists the known
    attribute names per entity type (every type in
    ``attribute_definitions.schema.ITEM_TYPES``, Epic #934 / WS1 #935), with
    each attribute's real, currently-resolved visibility for *workspace_id*
    (GitHub #882), so callers can discover valid field names before making a
    filter_mode='custom' bundle-export request.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="UUID of the workspace whose definition is resolved.",
            ),
            OpenApiParameter(
                "entity_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Restrict the answer to one item type (e.g. 'Requirement'). "
                    "Omitted = every known type."
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=AttributeSchemaEntrySerializer(many=True),
                description=(
                    "A bare JSON array of (entity_type, attribute_name) rows — "
                    "not an envelope."
                ),
            ),
            400: OpenApiResponse(description="Missing or malformed workspace_id."),
            404: OpenApiResponse(description="Unknown entity_type."),
        },
    )
    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id_raw = request.query_params.get("workspace_id")
        if not workspace_id_raw:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace_id = UUID(str(workspace_id_raw))
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            entity_type = request.query_params.get("entity_type")
            schema = describe_attribute_schema(ctx, workspace_id, entity_type)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(schema)



class GroupViewSet(viewsets.ViewSet):
    """Visual requirement groups (P6): CRUD + ordered membership."""

    def _svc(self):
        from application.group_service import GroupService

        return GroupService()

    def _group_dict(self, artifact) -> dict:
        fields = getattr(artifact, "custom_fields", None) or {}
        return {
            "id": str(artifact.id),
            "workspace_id": str(artifact.workspace_id),
            "title": fields.get("title", ""),
            "description": fields.get("description", ""),
        }

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose visual groups are listed.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=GroupListResponseSerializer,
                description="Every visual group of the workspace.",
            ),
            400: OpenApiResponse(description="workspace_id missing or not a UUID."),
            404: OpenApiResponse(description="Workspace not found in this tenant."),
        },
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id = UUID(str(request.query_params.get("workspace_id")))
            groups = self._svc().list_groups(workspace_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"results": [self._group_dict(group) for group in groups]})

    @extend_schema(
        request=GroupCreateRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=GroupSerializer, description="The created group."
            ),
            400: OpenApiResponse(description="Missing/invalid workspace_id or title."),
            403: OpenApiResponse(description="Write role required in the workspace."),
            404: OpenApiResponse(description="Workspace not found in this tenant."),
        },
    )
    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            group = self._svc().create(
                UUID(str(request.data["workspace_id"])),
                str(request.data.get("title") or ""),
                ctx,
                description=str(request.data.get("description") or ""),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (KeyError, TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._group_dict(group), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=GroupMemberAddRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=GroupMembersResponseSerializer,
                description="The group's ordered members after the call.",
            ),
            400: OpenApiResponse(
                description="Invalid requirement_id/after_id or duplicate member."
            ),
            403: OpenApiResponse(description="Write role required to add a member."),
            404: OpenApiResponse(description="Group or requirement not found."),
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        service = self._svc()
        try:
            ctx = get_auth_context(request)
            if request.method == "POST":
                service.add_member(
                    UUID(pk),
                    UUID(str(request.data["requirement_id"])),
                    ctx,
                    after_id=(
                        UUID(str(request.data["after_id"]))
                        if request.data.get("after_id")
                        else None
                    ),
                )
            members = service.members(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (KeyError, TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"members": members})

    @extend_schema(
        request=GroupMemberRemoveRequestSerializer,
        responses={
            204: OpenApiResponse(description="Membership removed (no body)."),
            400: OpenApiResponse(description="Invalid requirement_id."),
            403: OpenApiResponse(description="Write role required in the workspace."),
            404: OpenApiResponse(description="Group or requirement not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="members/remove")
    def remove_member(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().remove_member(
                UUID(pk), UUID(str(request.data["requirement_id"])), ctx
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (KeyError, TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=GroupMemberMoveRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=GroupMoveMemberResponseSerializer,
                description="The moved membership with its new sort_key.",
            ),
            400: OpenApiResponse(
                description="Invalid requirement_id/after_id or unknown member."
            ),
            403: OpenApiResponse(description="Write role required in the workspace."),
            404: OpenApiResponse(description="Group or requirement not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="members/move")
    def move_member(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            link = self._svc().move_member(
                UUID(pk),
                UUID(str(request.data["requirement_id"])),
                ctx,
                after_id=(
                    UUID(str(request.data["after_id"]))
                    if request.data.get("after_id")
                    else None
                ),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (KeyError, TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"trace_link_id": str(link.id), "sort_key": link.sort_key})



class AllocationListView(APIView):
    """GET /api/v1/allocations/ — flat requirement/allocation rows (P2)."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose allocations are listed.",
            ),
            OpenApiParameter(
                "requirement",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one Requirement id.",
            ),
            OpenApiParameter(
                "element",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one allocation target element id.",
            ),
            OpenApiParameter(
                "allocated",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="true = only allocated, false = only unallocated.",
            ),
            OpenApiParameter(
                "tier",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one tier key.",
            ),
            OpenApiParameter(
                "level",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one V-model level.",
            ),
            OpenApiParameter(
                "intent",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one allocation intent.",
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=200,
                description="Page size (1..500).",
            ),
            OpenApiParameter(
                "offset",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=0,
                description="Rows to skip.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=AllocationListResponseSerializer,
                description="One page of allocation rows plus filtered counters.",
            ),
            400: OpenApiResponse(description="Missing/invalid parameter."),
        },
    )
    def get(self, request: Request) -> Response:
        from application.allocation_query_service import AllocationQueryService

        lang = detect_lang(request)
        raw_workspace = request.query_params.get("workspace_id")
        if not raw_workspace:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'workspace_id' is required.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace_id = UUID(raw_workspace)
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )

        def _uuid_param(name: str) -> UUID | None:
            raw = request.query_params.get(name)
            return UUID(raw) if raw else None

        def _bool_param(name: str) -> bool | None:
            raw = request.query_params.get(name)
            if raw is None:
                return None
            return raw.lower() in {"1", "true", "yes"}

        try:
            allocated_raw = request.query_params.get("allocated")
            ctx = get_auth_context(request)
            payload = AllocationQueryService().list(
                workspace_id,
                ctx,
                requirement=_uuid_param("requirement"),
                element=_uuid_param("element"),
                allocated=(
                    None
                    if allocated_raw is None
                    else allocated_raw.lower() in {"1", "true", "yes"}
                ),
                tier=request.query_params.get("tier"),
                level=(
                    int(request.query_params["level"])
                    if request.query_params.get("level")
                    else None
                ),
                intent=request.query_params.get("intent"),
                limit=int(request.query_params.get("page_size") or 200),
                offset=int(request.query_params.get("offset") or 0),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload)
