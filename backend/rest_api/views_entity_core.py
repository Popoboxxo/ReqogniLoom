"""
COMP-RA-001 HttpEndpointController — views_entity_core — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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
    _ETAG_RESPONSE_HEADER,
    _IF_MATCH_PARAMETER,
    _PRECONDITION_FAILED_RESPONSE,
    _SYSTEM_FIELD_NAMES,
    _artifact_custom_fields,
    _parse_derivation_mode_policy,
    _service_error_response,
    list_schema,
    soft_delete_schema,
)




def _query_flag(request: Request, name: str) -> bool:
    """Read a boolean query flag ('true'/'1'/'yes', any casing).

    Shared by the coverage reports (``/requirements/coverage-report/`` and
    ``/needs/validation-coverage/``) so both read the same flag set.
    """
    return str(request.query_params.get(name, "")).strip().lower() in {
        "true",
        "1",
        "yes",
    }



# ---------------------------------------------------------------------------
# COMP-RA-001: RequirementViewSet
# REQ-L3-RA001-001: CRUD for Requirement entity
# ---------------------------------------------------------------------------


class StakeholderNeedViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Stakeholder Need entity."""

    serializer_class = StakeholderNeedSerializer
    workflow_item_type = "StakeholderNeed"
    attribute_item_type = "StakeholderNeed"
    # REQ-128 constrained the detail lookup to a UUID shape here so that
    # GET /api/v1/needs/derive-requirements/ (a custom-action path missing its
    # pk) 404ed at routing time instead of reaching retrieve() and 500ing on
    # UUID(pk). That trade-off made needs 404 on *any* non-UUID-shaped pk —
    # including a genuinely malformed one like "not-a-uuid" — while every
    # other BaseEntityViewSet subclass answers 400 for the same input via the
    # generic uuid_url_kwargs guard in initial() (issue #271). Issue #710
    # flagged that asymmetry, so the regex is gone; the guard now separates
    # the two cases itself, 404ing a pk segment that matches one of this
    # ViewSet's declared detail-action url_paths and 400ing everything else
    # (see BaseEntityViewSet._reject_malformed_uuid_path_kwargs). Both REQ-128
    # and #710 hold, for every ViewSet with detail actions rather than for
    # needs alone. (GoalViewSet still keeps a regex: "main" in /goals/main/ is
    # not an action name, it is a guessable alias of /main-goals/current/, so
    # only a router-level rule can decline it — see #460 Finding 4.)

    @property
    def service(self):
        from application.preset_policy_service import PresetPolicyService
        from application.stakeholder_need_service import StakeholderNeedService
        return StakeholderNeedService(preset_policy_service=PresetPolicyService())

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        need = self.service.get(ctx, UUID(pk))
        return need.id, need.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self.service.get(ctx, UUID(pk)), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self.service.get(ctx, item_id)
        return {"need": StakeholderNeedSerializer(_need_to_dict(updated)).data}

    @list_schema(search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/needs/?workspace_id=<id> or /api/v1/workspaces/<workspace_id>/needs/ — list workspace needs.

        Issue #267: optional ``?search=<term>`` case-insensitively filters on
        title/description/uid (same root cause as RequirementViewSet).
        """
        lang = detect_lang(request)
        try:
            workspace_id, error = parse_workspace_id(
                kwargs.get("workspace_pk") or request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            search = request.query_params.get("search") or None
            items = self.service.list_by_workspace(
                get_auth_context(request),
                workspace_id,
                include_deleted=parse_include_deleted(request.query_params),
                search=search,
            )
            return self._paginate(
                request,
                items,
                serialize_page=lambda page: StakeholderNeedSerializer(
                    [_need_to_dict(i) for i in page], many=True
                ).data,
            )
        except NotFoundError as e:
            return Response(build_error_response("NOT_FOUND", lang, message=str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Target workspace UUID.",
            ),
            OpenApiParameter(
                name="include_outdated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Include soft-deleted (outdated) StakeholderNeeds and count "
                    "outdated validating TestCases as evidence. Defaults to false."
                ),
            ),
            OpenApiParameter(
                name="include_unreviewed_ai",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Count an origin='ai_generated', unreviewed TestCase as "
                    "validation evidence (the raw view). The default excludes it "
                    "and reports the exclusion as summary.pending_ai_review."
                ),
            ),
        ],
        responses={
            200: NeedValidationCoverageResponseSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Missing or malformed `workspace_id`.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Caller lacks read permission on the workspace.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Unknown workspace, or one outside the caller's tenant.",
            ),
        },
        description=(
            "Validation coverage of the workspace's StakeholderNeeds (#878, "
            "Plan B B2-T2). The counterpart of "
            "`/api/v1/requirements/coverage-report/`: a need is *validated* when "
            "at least one incoming `validates` link comes from a live TestCase "
            "that counts as verification evidence (the same #424 predicate the "
            "`verifies` path uses). Rows are ordered by `uid`, then `need_id`."
        ),
    )
    @action(detail=False, methods=["get"], url_path="validation-coverage")
    def validation_coverage(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/needs/validation-coverage/?workspace_id=<uuid> (#878).

        The StakeholderNeed counterpart of
        ``/api/v1/requirements/coverage-report/``: a need is validated when at
        least one incoming ``validates`` link comes from a live TestCase that
        counts as verification evidence. The published contract (query params,
        200 body, error codes) is the ``extend_schema`` block above.

        Errors: missing/invalid ``workspace_id`` → 400 VALIDATION_ERROR;
        unknown/foreign workspace → 404 NOT_FOUND.
        """
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"),
            lang,
        )
        if error is not None:
            return error

        include_outdated = _query_flag(request, "include_outdated")
        include_unreviewed_ai = _query_flag(request, "include_unreviewed_ai")

        try:
            ctx = get_auth_context(request)
            # Existence check first: an unknown/foreign workspace is a 404, not
            # an empty report that looks like "no needs". Goes through the
            # service layer (no direct model query in a view).
            WorkspaceService().get_workspace(workspace_id, ctx)

            from traceability.coverage_calculator import CoverageCalculator

            report = CoverageCalculator().validation_coverage(
                workspace_id,
                include_outdated=include_outdated,
                include_unreviewed_ai=include_unreviewed_ai,
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception(
                "StakeholderNeedViewSet.validation_coverage: unhandled exception"
            )
            return _service_error_response(exc, lang)

        payload = {
            "summary": {
                "total": report.total,
                "covered": report.covered,
                "percentage": report.percentage,
                "pending_ai_review": report.pending_ai_review,
            },
            "needs": [
                {
                    "need_id": entry.need_id,
                    "uid": entry.uid,
                    "title": entry.title,
                    "test_cases": entry.test_cases,
                }
                for entry in report.entries
            ],
        }
        return Response(NeedValidationCoverageResponseSerializer(payload).data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """GET /api/v1/needs/<id>/ — retrieve single need."""
        lang = detect_lang(request)
        try:
            item = self.service.get(get_auth_context(request), kwargs["pk"])
            return Response(StakeholderNeedSerializer(_need_to_dict(item)).data)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.retrieve: unhandled exception")
            return _service_error_response(exc, lang)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/needs/ (flat) or /api/v1/workspaces/<workspace_id>/needs/ (nested) — create new need.

        CR-06/CR-07: the flat route has no ``workspace_pk`` URL kwarg, so the
        workspace id must be read from the validated request body instead.
        Previously the nested-route kwarg was used unconditionally, which left
        ``workspace_id`` as ``None`` for flat-route requests and made every
        flat POST fail with "Workspace None not found" (404).
        """
        lang = detect_lang(request)
        workspace_id = kwargs.get("workspace_pk")

        data = dict(request.data)
        if "workspace_id" not in data and workspace_id:
            data["workspace_id"] = workspace_id

        ser = StakeholderNeedSerializer(data=data)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Drop kwargs the service does not accept: workspace_id is passed
        # explicitly (would raise "multiple values"), parent_id/change_reason
        # are not part of StakeholderNeedService.create().
        payload = dict(ser.validated_data)
        # Fall back to the body-supplied workspace_id (flat route) when the
        # nested-route URL kwarg is absent.
        workspace_id = workspace_id or payload.pop("workspace_id", None)
        # Attribut v3 WS2 (#936): owner/reporter/priority are Artifact-level and
        # never reach StakeholderNeedService.create() as keyword arguments.
        for f in ("workspace_id", "parent_id", "change_reason", *_SYSTEM_FIELD_NAMES):
            payload.pop(f, None)
        ctx = get_auth_context(request)
        definition_error = self._validate_attribute_definition(
            ctx,
            workspace_id,
            dict(request.data) if isinstance(request.data, dict) else {},
            None,
        )
        if definition_error is not None:
            return definition_error
        try:
            item = self.service.create(
                ctx=ctx,
                workspace_id=workspace_id,
                **payload,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "StakeholderNeed", item, ctx)
            return Response(
                StakeholderNeedSerializer(_need_to_dict(item)).data,
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError as e:
            return Response(build_error_response("NOT_FOUND", lang, message=str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.create: unhandled exception")
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """PATCH /api/v1/needs/<id>/ — update need fields."""
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=StakeholderNeedSerializer,
            pk=kwargs.get("pk"),
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = StakeholderNeedSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Remove write-only/readonly kwargs from validated data before passing to service
        data = dict(ser.validated_data)
        change_reason = data.pop("change_reason", "")
        # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1): popped and
        # forwarded explicitly rather than left to the ``**data`` splat, so the
        # guarantee does not silently depend on a kwarg name matching.
        expected_version = data.pop("expected_version", None)
        # Remove fields that should not be updated via kwargs
        for f in [
            "id",
            "workspace_id",
            "parent_id",
            "uid",
            "suspect",
            "version",
            "created_at",
            "updated_at",
            *_SYSTEM_FIELD_NAMES,
        ]:
            data.pop(f, None)

        try:
            item = self.service.update(
                ctx=get_auth_context(request),
                need_id=kwargs["pk"],
                change_reason=change_reason,
                expected_version=expected_version,
                **data,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(
                request, "StakeholderNeed", item, get_auth_context(request)
            )
            return Response(StakeholderNeedSerializer(_need_to_dict(item)).data)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.partial_update: unhandled exception")
            return _service_error_response(exc, lang)

    @soft_delete_schema()
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """DELETE /api/v1/needs/<id>/ — soft-delete a stakeholder need. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state) and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        TraceLinks pointing at the record survive the delete, and traceability
        coverage ignores outdated records.

        ``change_reason`` is accepted from the request body or from the
        ``?change_reason=`` query parameter (body wins when both are sent).
        """
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        try:
            self.service.delete(get_auth_context(request), kwargs["pk"], change_reason=change_reason)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.destroy: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"], url_path="derive")
    def derive(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/needs/{pk}/derive/ — AI-derive requirement drafts.

        fix #112: delegates to the same working
        ``AiDerivationService.derive_requirements_from_need`` path as
        ``derive_requirements`` below (real need title/text embedded in the
        prompt, synchronous response). Previously called
        ``StakeholderNeedService.derive_requirements_async``, which sent the
        LLM only the need's bare UUID, never persisted a result, and
        returned a task_id with no reachable status endpoint.

        #1358: the response is an *ephemeral* preview (``"ephemeral": true``)
        — nothing is persisted. The canonical persistence path is
        ``POST /api/v1/needs/{pk}/derive-requirements/accept/`` below (or
        ``mode="write"`` on the MCP tool).
        """
        lang = detect_lang(request)
        raw_n = request.data.get("n") if isinstance(request.data, dict) else None
        try:
            # None means "use the workspace's max_requirements_per_need"
            # config variable — an explicit value overrides it for this call.
            n = int(raw_n) if raw_n is not None else None
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="'n' must be an integer"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().derive_requirements_from_need(
                get_auth_context(request), pk, n=n
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.derive: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"], url_path="derive-requirements")
    def derive_requirements(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/needs/{pk}/derive-requirements/ — AI-derive requirement drafts.

        REQ-L2-AI-001 / REQ-L2-AI-002: Explicit, user-triggered Draft/Accept flow.
        Returns proposed system requirements without persisting anything. Body
        may contain ``{"n": <int>}`` to control how many drafts to request.

        #1358: the response is an *ephemeral* preview (``"ephemeral": true``)
        — persist the accepted drafts via
        ``POST .../derive-requirements/accept/`` (canonical path).
        """
        lang = detect_lang(request)
        raw_n = request.data.get("n") if isinstance(request.data, dict) else None
        try:
            # None means "use the workspace's max_requirements_per_need"
            # config variable — an explicit value overrides it for this call.
            n = int(raw_n) if raw_n is not None else None
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="'n' must be an integer"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().derive_requirements_from_need(
                get_auth_context(request), pk, n=n
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.derive_requirements: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"], url_path="derive-requirements/accept")
    def derive_requirements_accept(
        self, request: Request, pk: str, **kwargs: Any
    ) -> Response:
        """POST /api/v1/needs/{pk}/derive-requirements/accept/ — persist accepted drafts.

        Issue #1095: the server-side half of the Draft/Accept accept step. The
        client posts the selected drafts of a ``derive-requirements`` preview and
        gets back the created artefacts — no second ``POST /requirements/`` per
        draft, no hand-built TraceLink, and no ``actor_type`` guessing on the
        client. The domain work is
        ``AiDerivationService.persist_derived_requirements`` (Layer 2, ADR-01);
        this handler is transport only. This is the canonical persistence path
        for a ``derive-requirements`` preview (#1358).

        Request body (every key is required to be declared):

        .. code-block:: json

            {"drafts": [{"title": "...", "description": "...", "rationale": "..."}]}

        Response 201:

        .. code-block:: json

            {
              "count": 1,
              "created": [
                {"id": "...", "status": "proposed", "trace_link_id": "...",
                 "proposal": {"is_proposal": true, "proposed_by": "ai-derivation", ...}}
              ],
              "proposal": {"is_proposal": true, "proposed_by": "ai-derivation",
                           "supported": true, "reason": ""}
            }

        The client flags ``status`` and ``from_ai`` are **forbidden** (#269/#851):
        the workflow state and the AI provenance are derived server-side from the
        seam in ``application.ai_proposal_service``. A client that could set them
        could either fake an AI stamp on hand-written content or force a state
        the workspace's graph does not have — and both would be dropped silently
        before this endpoint tightened the same gap for the preview path.

        Errors: 400 ``VALIDATION_ERROR`` for an undeclared key, a malformed
        ``drafts`` body, or a workspace whose workflow graph has no
        ``"proposed"`` state (the honest answer — the downgrade to ``draft`` is
        exactly what #1089 forbids); 404 ``NOT_FOUND`` for a need outside this
        tenant's scope.
        """
        lang = detect_lang(request)

        # #1095/#851: the accepted top-level keys are exactly {"drafts"}. The
        # check runs BEFORE anything is read or written, so a rejected payload
        # cannot create an artefact on its way to the error.
        invalid = reject_unknown_fields(request.data, {"drafts"}, lang)
        if invalid is not None:
            return invalid

        payload = request.data if isinstance(request.data, dict) else {}
        raw_drafts = payload.get("drafts")
        if not isinstance(raw_drafts, list) or not raw_drafts:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'drafts' must be a non-empty list of accepted drafts.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Same guard per entry: an unknown key inside a draft is the same silent
        # drop one level down (#851). The service also normalizes defensively;
        # this is what makes the rejection reach the client as a 400.
        for entry in raw_drafts:
            invalid = reject_unknown_fields(
                entry, {"title", "description", "rationale"}, lang
            )
            if invalid is not None:
                return invalid

        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().persist_derived_requirements(
                get_auth_context(request), need_id=pk, drafts=raw_drafts
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
            logger.exception(
                "StakeholderNeedViewSet.derive_requirements_accept: unhandled exception"
            )
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/needs/{pk}/diff/?from_version=0&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            need = self.service.get(ctx, pk)
            artifact_id = need.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(need.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
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
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.diff: unhandled exception")
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/needs/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            need = self.service.get(ctx, pk)
            artifact_id = need.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.versions: unhandled exception")
            return _service_error_response(exc, lang)
        return Response(result)




class RequirementViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Requirement CRUD operations.

    Delegates to RequirementService (ApplicationService facade, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).

    REQ-L2-RA-001: GET list, GET detail, POST, PATCH, DELETE.
    REQ-L2-RA-007: Audit context is passed through service methods.
    REQ-L2-RA-013: Queryset uses select_related (applied in service layer).
    REQ-143/REQ-144: transitions/ and workflow-history/ via WorkflowTransitionsMixin.
    """

    serializer_class = RequirementSerializer
    preset_endpoint_key = ""  # Requirements are always visible
    workflow_item_type = "Requirement"
    attribute_item_type = "Requirement"

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        req = self._svc().get_requirement(UUID(pk), ctx)
        return req.id, req.artifact.workspace_id

    # #915: no ``_current_status`` override here. ``get_requirement`` returns the
    # persistence row, and the denormalized ``status`` column was dropped
    # (Datenmodell-Konsolidierung Task 12) — reading it returned ``None`` for
    # every requirement, so a changed ``status`` on PATCH was accepted and
    # ignored instead of refused. The shared
    # ``WorkflowTransitionsMixin._current_status`` resolves the state through
    # ``workflow.state_reader``, the same source GET uses.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_requirement(item_id, ctx)
        return {"requirement": RequirementSerializer(_dto_from_orm(updated)).data}

    def _svc(self) -> RequirementService:
        return RequirementService()

    @staticmethod
    def _tier_names(workspace_id: UUID | None) -> dict[str, str]:
        """Return ``{tier_key: display_name}`` for one requirement response.

        P2 (V5 naming layer): the ladder is read **once per request** and the
        resulting map is handed to ``RequirementSerializer`` through its
        context, so ``tier_name`` costs no query per row. The naming rule is
        the one ``AllocationViewService`` uses (``en`` → ``de`` → the key), so
        the two read surfaces cannot disagree.

        Read-only enrichment: an unknown/absent workspace or a ladder failure
        yields an empty map and the serializer renders ``tier_name: null``
        instead of turning a requirement read into a 500.
        """
        if workspace_id is None:
            return {}
        from application.tier_ladder_service import TierLadderService

        try:
            return TierLadderService().get(workspace_id).name_map()
        except Exception:  # noqa: BLE001 — enrichment must not fail the read
            logger.debug(
                "tier_name: ladder lookup failed for workspace=%s",
                workspace_id,
                exc_info=True,
            )
            return {}

    def _requirement_context(self, workspace_id: UUID | None) -> dict[str, Any]:
        """Serializer context for a Requirement payload (P2 ``tier_name``).

        An empty map is omitted entirely: the serializer then behaves exactly
        like one built without a context (``tier_name`` is ``None``).
        """
        names = self._tier_names(workspace_id)
        return {"tier_names": names} if names else {}

    def _requirement_serializer(
        self, data: Any, workspace_id: UUID | None, *, many: bool = False
    ) -> Any:
        """Build the Requirement serializer with the ladder map in context.

        The ``context`` keyword is only passed when a ladder map exists, so a
        serialisation for an unresolvable workspace is byte-for-byte the
        context-less one (``tier_name: null``).
        """
        context = self._requirement_context(workspace_id)
        if context:
            return RequirementSerializer(data, many=many, context=context)
        return RequirementSerializer(data, many=many)

    # ADR-005: the V-model cascade level is DERIVED, so it is not a request
    # field. The serializer alone cannot express this honestly: a
    # ``read_only=True`` field makes DRF drop the value without a word, which
    # is the "200 and nothing happened" failure class this wave exists to close
    # (the same one ``parent_id`` had). It also cannot be added to
    # ``WorkflowTransitionsMixin._PROTECTED_PATCH_FIELDS``, because that set
    # rejects a field on *every* entity and would break the form round-trip:
    # #263 established that a read-only field echoed back unchanged must be
    # accepted, not refused.
    _DERIVED_LEVEL_MESSAGE = (
        "'level' is derived from the Requirement hierarchy and cannot be set "
        "(ADR-005). It is recomputed on every hierarchy change — create or move "
        "the Requirement, or add/remove a 'decomposes' / 'derives-from' link, "
        "and read the value back."
    )

    def _reject_derived_level(
        self, request: Request, lang: str, *, current: int | None
    ) -> Response | None:
        """Refuse a client-supplied ``level``; return a 400 Response or ``None``.

        Args:
            current: The requirement's stored level, or ``None`` on the create
                path (nothing to echo) and on a failed read.

        Contract, mirroring ``status`` (#263 / #915) so the two read-only
        fields behave alike:

        * a value that **differs** from the stored one (or any value at all on
          create) → **400** naming ``level``, atomically — nothing else in the
          payload is written;
        * an **unchanged echo** → accepted and ignored, so a detail panel that
          resends the whole form keeps the user's other edits.
        """
        data = request.data
        if not isinstance(data, dict) or "level" not in data:
            return None
        sent = data.get("level")
        if current is not None and sent == current:
            return None
        message = self._DERIVED_LEVEL_MESSAGE
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                details=[{"field": "level", "errors": [message]}],
                message=message,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    @list_schema(
        status=True,
        search=True,
        strict=True,
        extra=("allocated", "level"),
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/ — list all requirements.

        REQ-144: optional ``?status=<state>`` filters by the WorkflowEngine
        lifecycle mirror (e.g. ``?status=in_review`` for the review queue).
        Issue #267: optional ``?search=<term>`` case-insensitively filters on
        title/description/uid — previously read but never forwarded to the
        service, so the parameter had no effect.
        GH-443: soft-deleted requirements (``status="outdated"``, the state
        DELETE puts them in) are hidden by default; pass
        ``?include_deleted=true`` to include them, or ``?status=outdated`` to
        list only those.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            status_filter = request.query_params.get("status") or None
            search = request.query_params.get("search") or None
            try:
                allocated = parse_bool_param(
                    request.query_params, "allocated", default=None
                )
                level = parse_int_param(
                    request.query_params, "level", minimum=1, maximum=4
                )
            except ValueError as exc:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items = self._svc().list_requirements(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                status=status_filter,
                search=search,
                allocated=allocated,
                level=level,
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        return self._paginate(
            request,
            items,
            serialize_page=lambda page: self._requirement_serializer(
                [_dto_from_orm(i) for i in page],
                workspace_id,
                many=True,
            ).data,
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/ — retrieve single requirement.

        GH-868: the response carries ``ETag: "<version>"``; send that value back
        as ``If-Match`` on a PATCH to make the write conditional (412 when
        stale). Additive header only — the body is unchanged.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_requirement(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = self._requirement_serializer(
            _dto_from_orm(item),
            item.artifact.workspace_id,
        ).data
        # #399: additive drift summary for the editor header (no extra request).
        payload["baseline_drift"] = _baseline_drift_summary(item.artifact_id, ctx)
        return self.with_etag(Response(payload), item)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/ — create a requirement. Returns 201.

        REQ-L3-RF003-005: Accepts type-dependent fields (moscow_priority,
        complexity_fibonacci, verification_method).

        ADR-005: a ``level`` in the payload is refused with a field-level 400
        (see :meth:`_reject_derived_level`) instead of being read-only-dropped
        by DRF. ``level`` is derived from the hierarchy — a client that sets it
        asks the system to store something the hierarchy does not say, and the
        derivation would overwrite it a moment later. Silently ignoring the
        value would be the same "looks accepted, does nothing" defect this
        wave closes for ``parent_id``.

        #1079: the 201 carries ``ETag: "<version>"`` just like the detail GET
        and PATCH do, so a client can follow the create with a conditional
        PATCH without first looking the new artifact up.
        """
        lang = detect_lang(request)
        level_rejected = self._reject_derived_level(request, lang, current=None)
        if level_rejected is not None:
            return level_rejected
        ser = RequirementSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            definition_error = self._validate_attribute_definition(
                ctx,
                data.get("workspace_id"),
                dict(request.data) if isinstance(request.data, dict) else {},
                None,
            )
            if definition_error is not None:
                return definition_error
            item = self._svc().create_requirement(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                acceptance_criteria=data.get("acceptance_criteria", ""),
                rationale=data.get("rationale", ""),
                source=data.get("source", ""),
                category=data.get("category", ""),
                parent_id=data.get("parent_id"),
                type=data.get("type", "SyReq"),
                complexity_fibonacci=data.get("complexity_fibonacci"),
                verification_method=data.get("verification_method"),
                # ADR-005: no `level` — it is derived from `parent_id` by
                # RequirementService.create_requirement itself.
                uid=data.get("uid"),
                custom_fields=data.get("custom_fields"),
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "Requirement", item, ctx)
            # P2: 'not_allocatable' is a valid create-time intent; 'allocated'
            # without an edge is not (the allocation service owns that).
            requested_intent = data.get("allocation_intent")
            if requested_intent == "allocated":
                raise ValidationError(
                    "Use the allocation endpoint to mark a requirement allocated."
                )
            if requested_intent == "not_allocatable":
                item = self._svc().update_requirement(
                    requirement_id=item.id,
                    ctx=ctx,
                    allocation_intent="not_allocatable",
                )
            # #1289: an explicit manual level override, applied after create so
            # the derivation has already run and the override wins.
            if data.get("level_override") is not None:
                item = self._svc().set_manual_level(
                    item.id,
                    ctx,
                    int(data["level_override"]),
                    change_reason=data.get("change_reason"),
                )
            # #1609: the structured criteria list is a real write path now.
            # Persisted through the same service method the dedicated
            # ``/acceptance-criteria/`` endpoint uses, so the 201 cannot claim
            # a list that was never stored.
            if "acceptance_criteria_items" in data:
                item = self._persist_acceptance_criteria(
                    item,
                    data["acceptance_criteria_items"],
                    data.get("change_reason"),
                    ctx,
                )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        payload = self._requirement_serializer(
            _dto_from_orm(item),
            item.artifact.workspace_id,
        ).data
        # Issue #1178: the duplicate-title warning is additive, so it is added
        # after serialisation (the serializer stays Contract-shaped, exactly
        # like ``baseline_drift`` on the detail GET).
        title_warnings = _service_warnings(item)
        if title_warnings:
            payload["warnings"] = title_warnings
        return self.with_etag(
            Response(payload, status=status.HTTP_201_CREATED),
            item,
        )

    @extend_schema(
        # #1397: the header the declared 412 is conditioned on.
        # #1388/F3: and the response header that supplies the next tag.
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: RequirementSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/requirements/{pk}/ — update a requirement. Returns 200.

        REQ-L3-RF003-005: Accepts type-dependent fields (moscow_priority,
        complexity_fibonacci, verification_method).

        GH-868: a stale ``If-Match`` is refused with 412 PRECONDITION_FAILED,
        and the response carries the new ``ETag``. Both mechanisms are
        available — the body's ``expected_version`` keeps answering 409 when no
        ``If-Match`` is sent (see ``ETagMixin.resolve_expected_version`` for the
        precedence when both are present).

        ADR-005, two contract changes:

        * ``level`` is read-only (derived). A *differing* value is refused with
          a field-level 400; an unchanged echo is accepted and ignored, exactly
          like ``status`` (#263) — the detail panels resend the whole form, and
          throwing away the user's edit over an echoed read-only field was the
          worse bug. See :meth:`_reject_derived_level`.
        * ``parent_id`` is now **applied** instead of silently discarded. It was
          declared by the serializer and dropped on the floor, which is a
          contract break on its own and left ``level`` unreachable for a
          re-parent.
        """
        lang = detect_lang(request)
        # GH-1396: a malformed If-Match is a request defect (400) and is
        # refused before the payload guards below run any read.
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        current_level = self._current_requirement_level(request, pk)
        invalid = self._reject_derived_level(request, lang, current=current_level)
        if invalid is not None:
            return invalid
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=RequirementSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = RequirementSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            logger.error(f"Validation failed for Requirement PATCH {pk}: data={request.data}, errors={ser.errors}")
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        # R2C-003: the "only forward when present" rule now lives in the
        # RequirementUpdate command (issue #409, ADR-005, REQ-L2-AS-037):
        # absent nullable fields stay UNSET ("leave unchanged"), an explicit
        # null is forwarded as None ("clear to NULL").
        try:
            ctx = get_auth_context(request)
            # REQ-143: `status` is intentionally NOT forwarded. The serializer
            # marks it read-only, so a client-sent status is ignored here and the
            # lifecycle state can only change via the transitions endpoint.
            command = RequirementUpdate.from_validated_data(
                data,
                # Optimistic locking (SYSTEMAUDIT_2026-08-29 REST finding 1):
                # stale expected_version → OptimisticLockError → 409; GH-868
                # If-Match takes precedence; GH-1396 skips the loader for a
                # single strong integer tag.
                expected_version=self.resolve_expected_version(
                    request,
                    data,
                    current=lambda: self._svc().get_requirement(UUID(pk), ctx),
                ),
            )
            item = self._svc().update_requirement(
                requirement_id=UUID(pk),
                ctx=ctx,
                command=command,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "Requirement", item, ctx)
            # #1289: a manual level override rides along with the update. A
            # `null` clears it (restores the derived value); a 1..4 forces it.
            if "level_override" in data:
                override = data.get("level_override")
                item = self._svc().set_manual_level(
                    item.id,
                    ctx,
                    None if override is None else int(override),
                    change_reason=data.get("change_reason"),
                )
            # #1609: same write path as create — the list is persisted through
            # ``RequirementService.set_acceptance_criteria`` instead of being
            # dropped by the serializer, and the response is re-read so it
            # carries what is actually stored.
            if "acceptance_criteria_items" in data:
                item = self._persist_acceptance_criteria(
                    item,
                    data["acceptance_criteria_items"],
                    data.get("change_reason"),
                    ctx,
                )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            # GH-1396: a malformed header is a 400 INVALID_IF_MATCH; a header
            # whose strong tags cannot match is 412 — the body field below keeps
            # its 409 CONFLICT contract.
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            # GH-868: a failed If-Match is a precondition failure (412); the
            # body field keeps its existing 409 CONFLICT contract.
            if self.uses_if_match(request):
                return self.precondition_failed(request)
            return _service_error_response(exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(
                self._requirement_serializer(
                    _dto_from_orm(item),
                    item.artifact.workspace_id,
                ).data
            ),
            item,
        )

    def _current_requirement_level(self, request: Request, pk: str) -> Any | None:
        """Resolve the stored ``level`` for the echo-vs-change probe.

        Reads the stored value so an unchanged echo can be told apart from a
        real change (ADR-005). Best-effort: a probe failure returns ``None``,
        which falls through to the reject branch — the safe direction, so the
        caller refuses.
        """
        if not (isinstance(request.data, dict) and "level" in request.data):
            return None
        try:
            return self._svc().get_requirement(UUID(pk), get_auth_context(request)).level
        except Exception:  # noqa: BLE001 — the guard refuses anyway
            return None

    def _persist_acceptance_criteria(
        self,
        item: Any,
        criteria: list[dict[str, Any]],
        change_reason: str | None,
        ctx: Any,
    ) -> Any:
        """Store a payload-supplied criteria list and return the fresh row.

        #1609: the serializer used to declare ``acceptance_criteria_items``
        ``read_only``, so a PATCH answered 200 while the list was dropped. The
        list is now written through ``RequirementService.set_acceptance_criteria``
        — the very method the dedicated ``/acceptance-criteria/`` endpoint and
        the MCP ``requirement.acceptance_criteria_set`` tool use — so every
        write path shares one validator and one audit entry.

        The row is re-read because the service writes its own instance; the
        caller's ``item`` (from ``create_requirement``/``update_requirement``)
        would otherwise serialise the pre-write list back to the client.
        """
        self._svc().set_acceptance_criteria(
            item.id, ctx, criteria, change_reason=change_reason
        )
        return self._svc().get_requirement(item.id, ctx)

    @extend_schema(
        operation_id="requirements_acceptance_criteria_list",
        description=(
            "List the ordered structured acceptance criteria of a requirement. "
            "Explicit list id to keep it distinct from the by-index detail "
            "route (#1388)."
        ),
    )
    @action(detail=True, methods=["get"], url_path="acceptance-criteria")
    def acceptance_criteria(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/acceptance-criteria/ (#1288).

        Returns the ordered structured criteria list as
        ``{"criteria": [...], "total": N}``. Individual items are addressable by
        0-based index at ``.../acceptance-criteria/{index}/``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            criteria = self._svc().list_acceptance_criteria(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )
        return Response({"criteria": criteria, "total": len(criteria)})

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path=r"acceptance-criteria/(?P<index>\d+)",
    )
    def acceptance_criteria_item(
        self, request: Request, pk: str, index: str, **kwargs: Any
    ) -> Response:
        """GET/PATCH a single acceptance criterion by index (#1288).

        PATCH accepts only ``text`` and ``fulfilled`` (plus optional
        ``evidence_ref`` / ``change_reason``) so an external verification tool
        can check a criterion off without resending the whole list.
        """
        lang = detect_lang(request)
        criterion_index = int(index)
        try:
            ctx = get_auth_context(request)
            if request.method == "GET":
                return Response(self._svc().get_acceptance_criterion(UUID(pk), ctx, criterion_index))

            data = request.data if isinstance(request.data, dict) else {}
            unknown = sorted(
                set(data)
                - {"text", "fulfilled", "evidence_ref", "change_reason", "expected_version"}
            )
            if unknown:
                message = f"unknown field(s) for an acceptance criterion: {', '.join(unknown)}"
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[{"field": k, "errors": [message]} for k in unknown],
                        message=message,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                self._svc().update_acceptance_criterion(
                    UUID(pk),
                    ctx,
                    criterion_index,
                    text=data.get("text"),
                    fulfilled=data.get("fulfilled"),
                    evidence_ref=data.get("evidence_ref"),
                    change_reason=data.get("change_reason"),
                )
            )
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/requirements/{pk}/ — soft-delete a requirement. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state) and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` (or
        ``?status=outdated``) to see them, and ``POST .../reactivate/`` to
        restore one. TraceLinks pointing at the record survive, and
        traceability coverage ignores outdated records.

        A workspace whose Requirement type has no provisioned workflow
        definition answers 400 ``VALIDATION_ERROR`` instead of a 500: the
        soft-delete routes through the workflow engine's ``outdate()``, which
        needs that definition to resolve the states.

        ``change_reason`` is accepted from the request body or from the
        ``?change_reason=`` query parameter (body wins when both are sent).
        """
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        from workflow.services import WorkflowDefinitionError

        try:
            ctx = get_auth_context(request)
            self._svc().delete_requirement(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except WorkflowDefinitionError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/diff/?from_version=0&to_version=2

        REQ-L2-AS-032 / REQ-L1-040: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            # Resolve artifact_id from requirement
            req = self._svc().get_requirement(UUID(pk), ctx)
            artifact_id = req.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(req.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
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

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            req = self._svc().get_requirement(UUID(pk), ctx)
            artifact_id = req.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="derive")
    def derive(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/{pk}/derive/ — derive a child requirement
        onto the next system level, allocated to a mandatory architecture element.
        """
        lang = detect_lang(request)
        title = request.data.get("title")
        architecture_element_id = request.data.get("architecture_element_id")
        if not title:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="title is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not architecture_element_id:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="architecture_element_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            result = self._svc().derive_requirement(
                parent_requirement_id=UUID(pk),
                architecture_element_id=UUID(str(architecture_element_id)),
                title=title,
                ctx=ctx,
                description=request.data.get("description", ""),
            )
            child = self._svc().get_requirement(result.children[0].id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            {
                "requirement": RequirementSerializer(_dto_from_orm(child)).data,
                "trace_link_ids": [str(tl_id) for tl_id in result.trace_link_ids],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="suggest-architecture")
    def suggest_architecture(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/{pk}/suggest-architecture/ — AI arch suggestion.

        REQ-L2-AI-001 / REQ-L2-AI-002: Draft/Accept flow. Suggests architecture
        elements that could satisfy this (still unassigned) requirement without
        persisting anything. Returns 400 if the requirement is already assigned.

        #1358: the response is an *ephemeral* preview (``"ephemeral": true``).
        The canonical persistence path for the top-ranked element is
        ``mode="write"`` on the MCP tool (no REST write counterpart yet).
        """
        lang = detect_lang(request)
        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().suggest_architecture_for_requirement(
                get_auth_context(request), pk
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("RequirementViewSet.suggest_architecture: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"], url_path="decompose-next-level")
    def decompose_next_level(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/{pk}/decompose-next-level/ — AI decomposition.

        REQ-L2-AI-001 / REQ-L2-AI-002: Draft/Accept flow. Proposes next-level
        requirement drafts (optionally tagged with a suggested architecture
        element) without persisting anything. Returns 400 if the requirement has
        no allocated architecture element.

        #1358: the response is an *ephemeral* preview (``"ephemeral": true``)
        — the drafts are not persisted. The canonical write paths are
        ``POST /api/v1/requirements/{pk}/decompose-next-level/accept/``
        (#1368, the human Draft/Accept step) and ``mode="write"`` on the MCP
        tool ``ai_derivation.decompose_requirement_next_level`` (agents).
        """
        lang = detect_lang(request)
        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().decompose_requirement_next_level(
                get_auth_context(request), pk
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("RequirementViewSet.decompose_next_level: unhandled exception")
            return _service_error_response(exc, lang)

    @extend_schema(
        request=OpenApiRequest(
            request=inline_serializer(
                name="RequirementDecomposeAcceptRequest",
                fields={
                    "drafts": serializers.ListField(
                        child=serializers.DictField(),
                        help_text=(
                            "The accepted drafts exactly as reviewed — each "
                            "one {'title', 'description', 'rationale'}."
                        ),
                    ),
                },
            ),
        ),
        responses={
            201: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "The persistence receipt. Body: `created` (array of objects "
                    "with `id`, `status`, `trace_link_id` and the `proposal` "
                    "block: `state`, `is_proposal`, `supported`, `proposed_by`, "
                    "`label`, `reason` — one entry per accepted draft), `count` "
                    "(int) and the batch's shared `proposal` block read back "
                    "from the workflow engine."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Unknown key (top-level or inside a draft), malformed "
                    "`drafts` body, or a workspace whose workflow graph has no "
                    "'proposed' state."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Caller lacks the editor role (POST requires WRITE).",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Requirement not found in the active tenant.",
            ),
        },
        description=(
            "Persist the accepted drafts of a `decompose-next-level` preview "
            "(#1368, W12b — the human Draft/Accept step; the preview itself is "
            "`ephemeral: true` and persists nothing, #1358).\n\n"
            "Delegates to `AiDerivationService.persist_decomposed_requirements` "
            "(Layer 2, ADR-01): each accepted draft becomes one child "
            "Requirement linked to this requirement via a 'derives-from' trace "
            "link (child -> parent) and is born `proposed` where the "
            "workspace's workflow supports it (#1089) — so it lands in the "
            "pending-review queue instead of in a draft nobody is shown.\n\n"
            "The client sends neither `status` nor `from_ai` (#269/#851): the "
            "workflow state and the AI provenance are derived server-side."
        ),
    )
    @action(detail=True, methods=["post"], url_path="decompose-next-level/accept")
    def decompose_next_level_accept(
        self, request: Request, pk: str, **kwargs: Any
    ) -> Response:
        """POST /api/v1/requirements/{pk}/decompose-next-level/accept/ (#1368).

        The server-side half of the UI's confirm step for the requirement
        decomposition: the client posts the drafts the human reviewed and gets
        back the created children — no client-side ``POST /requirements/`` per
        draft (which, from a user principal, was born as a plain ``draft`` and
        stayed invisible — the #1089 defect class), no hand-built TraceLink.

        Body: ``{"drafts": [{"title": ..., "description": ...,
        "rationale": ...}]}``. Unknown keys are rejected (#851), the top-level
        ones and the per-draft ones alike.
        """
        lang = detect_lang(request)

        # #1095/#851 convention: the accepted top-level keys are exactly
        # {"drafts"}, checked BEFORE anything is read or written.
        invalid = reject_unknown_fields(request.data, {"drafts"}, lang)
        if invalid is not None:
            return invalid

        payload = request.data if isinstance(request.data, dict) else {}
        raw_drafts = payload.get("drafts")
        if not isinstance(raw_drafts, list) or not raw_drafts:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'drafts' must be a non-empty list of accepted drafts.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        for entry in raw_drafts:
            invalid = reject_unknown_fields(
                entry, {"title", "description", "rationale"}, lang
            )
            if invalid is not None:
                return invalid

        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().persist_decomposed_requirements(
                get_auth_context(request), requirement_id=pk, drafts=raw_drafts
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
            logger.exception(
                "RequirementViewSet.decompose_next_level_accept: unhandled exception"
            )
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"], url_path="derive-testcase")
    def derive_testcase(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/{pk}/derive-testcase/ — AI TestCase draft.

        SysEng 2.0 N5 (test.derive_from_requirement). REQ-L2-AI-001: Draft/Accept
        flow. Proposes a TestCase draft (title, description, steps) verifying
        this requirement without persisting anything. Standard feature — no
        rigor-preset / RuleEngine gate, unlike decompose_next_level.

        #1358: the response is an *ephemeral* preview (``"ephemeral": true``).
        The canonical write path is ``mode="write"`` on the MCP tool
        ``test.derive_from_requirement``.
        """
        lang = detect_lang(request)
        try:
            from application.ai_derivation_service import AiDerivationService

            result = AiDerivationService().derive_testcase_from_requirement(
                get_auth_context(request), pk
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("RequirementViewSet.derive_testcase: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=False, methods=["get"], url_path="coverage-report")
    def coverage_report(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/coverage-report/?workspace_id=<uuid> (#272).

        Requirement→Test coverage report: the summary
        (``CoverageCalculator.coverage``) plus a per-requirement row list with
        its verifying TestCases (``get_coverage_data``). This is the report the
        ``allocation-coverage`` action on ArchitectureElement never provided
        for Requirements.

        Query params:
            workspace_id (required): target workspace UUID.
            include_outdated (default false): include soft-deleted
                Requirements/TestCases.
            include_unreviewed_ai (default false): #424 — count an
                ``origin="ai_generated"``, unreviewed TestCase as coverage
                (the raw view). The default excludes it and reports the
                exclusion count as ``summary.pending_ai_review``.

        Response::

            {
              "summary": {"total": 24, "covered": 21, "percentage": 87.5,
                          "pending_ai_review": 2},
              "requirements": [
                {"requirement_id": "uuid", "uid": "REQ-L1-004", "title": "...",
                 "level": 1, "covered": true,
                 "test_cases": [{"id": "uuid", "uid": "TC-007", "title": "...",
                                 "origin": "manual", "reviewed": true,
                                 "scenario_kind": "off_nominal",
                                 "result": "Passed"}]}
              ]
            }

        Errors: missing/invalid ``workspace_id`` → 400 VALIDATION_ERROR;
        unknown workspace → 404 NOT_FOUND.
        """
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"),
            lang,
        )
        if error is not None:
            return error

        include_outdated = _query_flag(request, "include_outdated")
        include_unreviewed_ai = _query_flag(request, "include_unreviewed_ai")

        try:
            ctx = get_auth_context(request)
            # Existence check first: an unknown workspace is a 404, not an
            # empty report that looks like "no requirements". Goes through the
            # service layer (no direct model query in a view).
            WorkspaceService().get_workspace(workspace_id, ctx)

            from traceability.coverage_calculator import CoverageCalculator

            calculator = CoverageCalculator()
            report = calculator.coverage(
                workspace_id,
                include_outdated=include_outdated,
                include_unreviewed_ai=include_unreviewed_ai,
            )
            data = calculator.get_coverage_data(
                workspace_id,
                include_outdated=include_outdated,
                include_unreviewed_ai=include_unreviewed_ai,
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("RequirementViewSet.coverage_report: unhandled exception")
            return _service_error_response(exc, lang)

        covered_ids = {
            entry.requirement_id for entry in data.entries if entry.test_cases
        }
        requirements_payload = [
            {
                "requirement_id": entry.requirement_id,
                "uid": entry.uid,
                "title": entry.title,
                "level": entry.level,
                "covered": entry.requirement_id in covered_ids,
                "test_cases": entry.test_cases,
            }
            for entry in data.entries
        ]

        return Response(
            {
                "summary": {
                    "total": report.total,
                    "covered": report.covered,
                    "percentage": report.percentage,
                    # #424: TestCases excluded solely for being unreviewed AI
                    # content. 0 on the raw view.
                    "pending_ai_review": report.pending_ai_review,
                },
                "requirements": requirements_payload,
            }
        )

    @action(detail=True, methods=["get"], url_path="allocation")
    def allocation_coverage(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/allocation/ — list allocations.

        REQ-L1-058 AC3: Returns all ArchitectureElements a requirement is
        allocated to (via TraceLink with link_type='allocated-to').

        Response schema:
        {
            "requirement_id": "UUID",
            "requirement_title": "string",
            "allocations": [
                {
                    "architecture_element_id": "UUID",
                    "architecture_element_title": "string",
                    "target_level": 2,
                    "asil_level": "A",
                    "make_or_buy": "Make"
                }
            ]
        }
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            req = self._svc().get_requirement(UUID(pk), ctx)

            # REQ-066: allocation resolution (ORM + prefetch) lives in the
            # service layer (REQ-L2-RA-013 CTE prefetch avoids N+1).
            from application.trace_link_service import TraceLinkService

            allocations = TraceLinkService().get_requirement_allocations(
                req.artifact_id, req.tenant_id, ctx
            )

            return Response({
                "requirement_id": str(req.id),
                "requirement_title": req.title,
                "allocations": allocations,
            })
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("RequirementViewSet.allocation_coverage: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=False, methods=["get"], url_path="similar")
    def similar(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/similar/ — semantic similarity search.

        Query params:
            requirement_id (required): UUID of the query requirement.
            limit (optional): max results, clamped 1..50 (default 10).
            workspace_id (optional): restrict results to a workspace.

        REQ-L2-VS-004: Returns the top-N requirements most similar to the query
        requirement by cosine distance over pgvector embeddings. Returns 503
        when pgvector (package or ``vector`` extension) is unavailable.
        """
        lang = detect_lang(request)

        requirement_id_str = request.query_params.get("requirement_id")
        if not requirement_id_str:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="requirement_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            requirement_id = UUID(requirement_id_str)
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="requirement_id must be a valid UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10

        workspace_id = None
        workspace_id_str = request.query_params.get("workspace_id")
        if workspace_id_str:
            try:
                workspace_id = UUID(workspace_id_str)
            except (ValueError, TypeError):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            ctx = get_auth_context(request)
            results = self._svc().find_similar_requirements(
                requirement_id=requirement_id,
                ctx=ctx,
                limit=limit,
                workspace_id=workspace_id,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except PgVectorUnavailableError as exc:
            return Response(
                build_error_response("SERVICE_UNAVAILABLE", lang, message=str(exc)),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        serialized = [SimilarRequirementSerializer(r).data for r in results]
        return Response(serialized)



# ---------------------------------------------------------------------------
# RequirementHistoryView — REQ-L0-011: Audit-Trail for Requirements
# ---------------------------------------------------------------------------


class RequirementHistoryView(APIView):
    """GET /api/v1/requirements/{pk}/history/ — Audit-Trail für Requirements.

    REQ-L0-011: Returns paginated audit entries from the audit_entry table
    for a specific Requirement. Uses AuditLogQuery (COMP-AL-002) for
    filtered/paginated access with tenant isolation.

    Query params:
        page      — page number (default 1)
        page_size — entries per page (default 50, max 100)
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=1,
                description="1-based page number.",
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=50,
                description="Entries per page (capped at 100).",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=RequirementHistoryResponseSerializer,
                description="One page of audit entries for this requirement.",
            ),
            400: OpenApiResponse(description="page/page_size are not integers."),
            404: OpenApiResponse(description="Requirement not found in this tenant."),
        },
    )
    def get(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            # Verify requirement exists and user has access (also sets tenant context)
            req_service = RequirementService()
            # pk is already a UUID object from Django <uuid:pk> URL converter
            req_pk = pk if isinstance(pk, UUID) else UUID(pk)
            req_service.get_requirement(req_pk, ctx)

            # Parse pagination params
            try:
                page = int(request.query_params.get("page", 1))
                page_size = int(request.query_params.get("page_size", 50))
            except (ValueError, TypeError):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang,
                        message="page and page_size must be integers",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Cap page_size to prevent excessive queries
            page_size = min(page_size, 100)

            # Query audit entries for this requirement
            filters = AuditQueryFilters(
                entity_id=req_pk,
                entity_type="Requirement",
            )
            result = AuditLogQuery.query(
                filters=filters,
                page=page,
                page_size=page_size,
            )

            return Response({
                "results": [
                    {
                        "id": str(e.id),
                        "actor": e.actor,
                        "actor_type": e.actor_type,
                        "operation": e.op,
                        "timestamp": e.timestamp.isoformat(),
                        "change_reason": e.change_reason,
                        "entity_version": e.entity_version,
                        "source": e.source,
                    }
                    for e in result.entries
                ],
                "total": result.total,
                "page": result.page,
                "page_size": result.page_size,
            })
        except (NotFoundError, PermissionDeniedError) as exc:
            logger.error("RequirementHistoryView: auth error %s", exc)
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("RequirementHistoryView: unhandled exception for pk=%s type(pk)=%s", pk, type(pk).__name__)
            return _service_error_response(exc, lang)



# ---------------------------------------------------------------------------
# ArtifactViewSet
# ---------------------------------------------------------------------------


class ArtifactViewSet(BaseEntityViewSet):
    """ViewSet for Artifact CRUD operations (REQ-L2-RA-001)."""

    serializer_class = ArtifactSerializer
    preset_endpoint_key = ""

    def _svc(self) -> ArtifactService:
        return ArtifactService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            # REQ-034: hand the QuerySet directly to the paginator so it slices
            # lazily (LIMIT/OFFSET) instead of loading every row via list().
            # REQ-066: the ORM access lives in ArtifactService.
            qs = self._svc().list_child_summaries(ctx, workspace_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            qs,
            lambda r: {
                "id": str(r["id"]),
                "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
                "artifact_type": r["artifact_type"],
                "name": r.get("name", ""),
            },
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_artifact(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArtifactSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_artifact(
                workspace_id=UUID(str(data["workspace_id"])),
                artifact_type=data.get("artifact_type", "generic"),
                ctx=ctx,
                parent_id=data.get("parent_id"),
                custom_fields=data.get("custom_fields"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArtifactSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        # REQ-L2-AS-037: only forward custom_fields when explicitly provided.
        extra_kwargs: dict[str, Any] = {}
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_artifact(
                artifact_id=UUID(pk),
                ctx=ctx,
                artifact_type=data.get("artifact_type"),
                parent_id=data.get("parent_id"),
                **extra_kwargs,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_artifact(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/artifacts/{pk}/move/ — reparent and/or reorder (P1).

        Body: ``{"parent_id": <uuid|null>, "after_id": <uuid|null>}``.
        ``after_id`` omitted appends at the end, ``null`` inserts first.
        """
        lang = detect_lang(request)
        raw_parent = request.data.get("parent_id", None)
        try:
            parent_id = UUID(str(raw_parent)) if raw_parent else None
        except (TypeError, ValueError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'parent_id' must be a well-formed UUID or null.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "after_id" in request.data:
            raw_after = request.data.get("after_id")
            if raw_after is None:
                after_id: Any = None
            else:
                try:
                    after_id = UUID(str(raw_after))
                except (TypeError, ValueError):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR",
                            lang,
                            message="'after_id' must be a well-formed UUID or null.",
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            from application.artifact_service import UNSET

            after_id = UNSET

        try:
            ctx = get_auth_context(request)
            item = self._svc().move(
                artifact_id=UUID(pk),
                new_parent_id=parent_id,
                after_id=after_id,
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    @action(detail=True, methods=["get"], url_path="baseline-membership")
    def baseline_membership(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/artifacts/{pk}/baseline-membership/ (#399).

        Ans: Baseline-Mitgliedschaft + Drift-Kennzeichnung des Artefakts —
        Decision D1 (no hard block, drift marking instead).

        Response::

            {
              "artifact_id": "uuid",
              "drifted": true,
              "memberships": [
                {"baseline_id": "uuid", "baseline_name": "Release 1.8",
                 "scope": "project", "baselined_at": "...",
                 "baselined_version": 3, "current_version": 4,
                 "drifted": true, "drift_known": true}
              ]
            }

        An empty ``memberships`` list means the artifact is in no baseline
        (``drifted`` is then ``false``). Tenant-scoped through the service's
        tenant-checked loading path.

        Contract note: ``baselined_version``/``current_version`` are
        **informational** — they are the ``Artifact.version`` pair captured
        now vs. at baseline time, not the entity's own version. A content edit
        bumps the entity version without bumping ``Artifact.version``, so the
        two can be equal while the artifact genuinely drifted. ``drifted``
        (from the recorded state) is the authoritative verdict.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            from application.baseline_facade import BaselineFacade

            memberships = BaselineFacade().memberships_for_artifact(
                UUID(pk), ctx
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            {
                "artifact_id": str(pk),
                "drifted": any(m.drifted for m in memberships),
                "memberships": [m.to_dict() for m in memberships],
            }
        )



def _baseline_drift_summary(artifact_id: Any, ctx: Any) -> dict[str, Any]:
    """Return the additive ``baseline_drift`` summary for a retrieve response.

    #399 (cluster 5): document/TestCase ``retrieve`` carry
    ``{"drifted": bool, "count": int}`` so the editor header can render the
    drift badge from the detail response instead of an extra request per row
    (the list badge is deliberately out of scope — it would need a batch
    endpoint, spec D7).

    Fail-open on purpose: a drift *label* must never turn a successful read
    into a 500. Any error yields the neutral ``{drifted: False, count: 0}``.
    """
    try:
        from application.baseline_facade import BaselineFacade

        memberships = BaselineFacade().memberships_for_artifact(
            UUID(str(artifact_id)), ctx
        )
    except Exception:  # noqa: BLE001 — never mask the read itself
        logger.exception(
            "baseline drift summary failed for artifact=%s", artifact_id
        )
        return {"drifted": False, "count": 0}
    drifted = [m for m in memberships if m.drifted]
    return {"drifted": bool(drifted), "count": len(drifted)}



# ---------------------------------------------------------------------------
# ArchitectureElementViewSet
# ---------------------------------------------------------------------------


class _JsonOnlyContentNegotiation(BaseContentNegotiation):
    """Content negotiation that always resolves to the first declared renderer.

    Requirement Bundle Export: the ``requirement_bundle`` action selects its
    own output format from an app-level ``?output_format=`` query param and
    emits markdown/CSV as a raw ``HttpResponse``, bypassing DRF's renderer
    pipeline entirely. DRF's rendering therefore only ever matters for the
    JSON branch — but ``DefaultContentNegotiation`` still runs *before* the
    action body and can hijack the request from the ``Accept`` header or the
    reserved ``?format=`` override, which previously produced a ``200`` with a
    corrupted body (a stub renderer returning the dict unchanged, which
    ``HttpResponse`` then iterated into its concatenated key names), a
    spurious ``406``, or a bare ``404`` that pre-empted the action's own
    ``400 VALIDATION_ERROR``.

    Pinning negotiation to JSON removes that whole channel: whatever the
    client sends in ``Accept``/``?format=``, DRF resolves to
    ``JSONRenderer``, and the action alone decides the real output format.

    Same seam for the document reading view's Markdown export (R7.1): there
    ``?format=markdown`` is the action's own parameter and the body leaves as
    ``text/markdown``, so the reserved override must not answer ``404`` first.
    """

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type



class ArchitectureElementViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for ArchitectureElement CRUD operations (REQ-L2-RA-001).

    REQ-171: transitions/ and workflow-history/ via WorkflowTransitionsMixin so
    the ArchitectureForm drives its lifecycle through the WorkflowEngine like
    every other artifact type.
    """

    serializer_class = ArchitectureElementSerializer
    preset_endpoint_key = ""
    workflow_item_type = "ArchitectureElement"
    attribute_item_type = "ArchitectureElement"

    def _svc(self) -> ArchitectureService:
        return ArchitectureService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        # GH-443: ``include_deleted=True`` so the workflow actions stay usable
        # on a soft-deleted element — without it ``POST .../reactivate/`` could
        # never reach the one item it exists for. ``retrieve()`` needs the same
        # opt-in since G1.5/#1381: the wire status is projected from
        # ``Artifact.lifecycle_status`` via ``workflow.state_reader``, so a
        # soft-deleted element answers 200 + "outdated" like every other type.
        item = self._svc().get_architecture_element(
            UUID(pk), ctx, include_deleted=True
        )
        # ArchitectureElement is scoped via its artifact (no local workspace_id).
        return item.id, item.artifact.workspace_id

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_architecture_element(item_id, ctx)
        return {
            "architecture_element": ArchitectureElementSerializer(
                _arch_to_dict(updated)
            ).data
        }

    @list_schema(search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/architecture-elements/ — list architecture elements.

        Issue #267: optional ``?search=<term>`` case-insensitively filters on
        title/description/uid (same root cause as RequirementViewSet).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            # REQ-006: include_deleted=true exposes soft-deleted elements (admin use)
            include_deleted = parse_include_deleted(request.query_params)
            search = request.query_params.get("search") or None
            items = self._svc().list_architecture_elements(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=include_deleted,
                search=search,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: ArchitectureElementSerializer(
                [_arch_to_dict(item) for item in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_architecture_element(
                UUID(pk), ctx, include_deleted=True
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/architecture-elements/ — create an element. Returns 201.

        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        """
        lang = detect_lang(request)
        ser = ArchitectureElementSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            definition_error = self._validate_attribute_definition(
                ctx,
                data.get("workspace_id"),
                dict(request.data) if isinstance(request.data, dict) else {},
                None,
            )
            if definition_error is not None:
                return definition_error
            item = self._svc().create_architecture_element(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                element_type=data.get("element_type", ""),
                parent_id=data.get("parent_id"),
                asil_level=data.get("asil_level"),
                make_or_buy=data.get("make_or_buy"),
                uid=data.get("uid"),
                custom_fields=data.get("custom_fields"),
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "ArchitectureElement", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=OpenApiRequest(
            request=inline_serializer(
                name="ArchitectureDeriveRisksRequest",
                fields={
                    "mode": serializers.ChoiceField(
                        choices=["preview", "write"],
                        required=False,
                        default="preview",
                        help_text=(
                            "'preview' (default) returns drafts only and marks "
                            "the response `ephemeral: true`; 'write' is the "
                            "canonical persistence path (persists each draft "
                            "as a Risk linked via 'mitigates')."
                        ),
                    ),
                    "policy": serializers.ChoiceField(
                        choices=["manual", "auto"],
                        required=False,
                        default="manual",
                        help_text=(
                            "Only relevant for mode='write': 'manual' (default) "
                            "leaves new risks in their initial state; 'auto' "
                            "best-effort auto-advances them."
                        ),
                    ),
                },
            ),
        ),
        parameters=[
            OpenApiParameter(
                name="pk",
                type=str,
                location=OpenApiParameter.PATH,
                description="UUID of the architecture element to derive risks for.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Ephemeral risk draft preview — persists nothing. Body: "
                    "`drafts` (array of objects with `title`, `description`, "
                    "`probability`, `impact`, `category` — the three enums are "
                    "clamped to the Risk vocabulary), "
                    "`architecture_element_id` (uuid string), "
                    "`is_mock_fallback` (bool) and `ephemeral` (always `true`)."
                ),
            ),
            201: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Write mode: the persistence receipt. Body: `written` "
                    "(array of objects with `id`, `status`, `trace_link_id` and "
                    "the `proposal` block: `state`, `is_proposal`, `supported`, "
                    "`proposed_by`, `label`, `reason`), `is_mock_fallback` "
                    "(bool), plus `failed` (array of `{draft, error}`) only "
                    "when individual drafts were rejected."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Unknown field or invalid mode/policy.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Caller lacks the editor role (POST requires WRITE).",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Architecture element not found in the active tenant.",
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
            "AI risk derivation for an architecture element (REST parity with "
            "the MCP tool `ai_derivation.derive_risks_from_architecture`, "
            "#1358).\n\n"
            "- `mode='preview'` (default): ephemeral drafts, nothing persisted.\n"
            "- `mode='write'`: persists each draft through "
            "`AiDerivationService.persist_risk_drafts`, linked back to the "
            "element via a 'mitigates' trace link (Risk -> ArchitectureElement); "
            "born `proposed` where the workspace's workflow supports it."
        ),
    )
    @action(detail=True, methods=["post"], url_path="derive-risks")
    def derive_risks(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/architecture/{pk}/derive-risks/ — AI risk drafts (preview | write).

        Issue #1358 (W12a): REST parity for
        ``ai_derivation.derive_risks_from_architecture``. The preview response
        is ephemeral (``"ephemeral": true``, #1358); ``mode="write"`` is the
        canonical persistence path and reuses the exact same write seam as the
        MCP tool (``AiDerivationService.persist_risk_drafts`` →
        ``_write_derived_entity`` + ``mitigates`` link), so both transports
        persist identically (status ``proposed`` where the workspace's workflow
        supports it, see #1089).

        Body: ``{"mode"?: "preview"|"write", "policy"?: "manual"|"auto"}`` —
        the source element is the URL pk. Unknown keys are rejected (#851).
        """
        lang = detect_lang(request)
        invalid = reject_unknown_fields(request.data, {"mode", "policy"}, lang)
        if invalid is not None:
            return invalid
        mode, policy, error = _parse_derivation_mode_policy(request, lang)
        if error is not None:
            return error

        try:
            from application.ai_derivation_service import AiDerivationService

            ctx = get_auth_context(request)
            service = AiDerivationService()
            preview = service.derive_risks_from_architecture(ctx, pk)
            if mode == "preview":
                return Response(preview, status=status.HTTP_200_OK)
            result = service.persist_risk_drafts(
                ctx,
                architecture_element_id=pk,
                preview=preview,
                policy=policy,
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
            logger.exception(
                "ArchitectureElementViewSet.derive_risks: unhandled exception"
            )
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/architecture-elements/{pk}/ — update an element. Returns 200.

        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        """
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=ArchitectureElementSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        # REQ-L1-044: element_id context enables hierarchy invariant checks
        ser = ArchitectureElementSerializer(
            data=request.data, partial=True, context={"element_id": pk}
        )
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            update_kwargs: dict[str, Any] = {}
            if "parent_id" in data:
                # Distinguish "omitted" from "set to null (detach)"
                update_kwargs["parent_id"] = data["parent_id"]
            # REQ-L2-AS-037: only forward custom_fields when explicitly provided.
            if "custom_fields" in data:
                update_kwargs["custom_fields"] = data["custom_fields"]
            # Bugfix (code review R-1): asil_level/make_or_buy default to a
            # sentinel (_UNSET) in the service so an omitted key is a no-op.
            # .get() returns None for an omitted key, which the service reads
            # as "explicitly cleared" and NULLs the column — e.g. every
            # reparent-only PATCH ({parent_id} only) was wiping both fields.
            # Same presence-check pattern as parent_id/custom_fields above.
            if "asil_level" in data:
                update_kwargs["asil_level"] = data["asil_level"]
            if "make_or_buy" in data:
                update_kwargs["make_or_buy"] = data["make_or_buy"]
            item = self._svc().update_architecture_element(
                arch_el_id=UUID(pk),
                ctx=ctx,
                expected_version=data.get("expected_version"),
                title=data.get("title"),
                description=data.get("description"),
                element_type=data.get("element_type"),
                # uid is read-only via REST: never forward from PATCH data
                # (would overwrite stored uid with None). Set only via service/MCP.
                **update_kwargs,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "ArchitectureElement", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/architecture/{pk}/ — soft-delete an element. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state). List endpoints hide outdated elements by
        default; pass ``?include_deleted=true`` to see them, and
        ``POST .../reactivate/`` to restore one. TraceLinks pointing at the
        element survive the delete, and traceability coverage ignores outdated
        elements.

        A subsequent GET on this URL answers 200 with ``status="outdated"``,
        identical to every other soft-deleting entity (G1.5/#1381, GH-443):
        the wire status is resolved from ``Artifact.lifecycle_status`` via
        ``workflow.state_reader``, so no per-type status column is needed. The
        former 404 exception ("no status mirror") was based on the pre-Phase-4
        model and no longer applies.
        """
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_architecture_element(
                UUID(pk), ctx, change_reason=change_reason
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        responses={
            200: ArchitectureAllocationCoverageSerializer,
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Unknown ArchitectureElement, or one outside the caller's tenant.",
            ),
        },
        description=(
            "Allocation coverage of this ArchitectureElement (REQ-L1-042, "
            "GH-1883). `coverage_percent` is a percentage (0…100) — the field "
            "was previously published as `coverage_ratio`, although the value "
            "was always a percentage, and the 200 body was wrongly documented "
            "as an `ArchitectureElement`. Membership is decided solely by "
            "`allocated-to` links whose target is this element; allocations on "
            "child elements do not roll up. Requirements with "
            "`allocation_intent='not_allocatable'` are excluded from the "
            "denominator and reported separately."
        ),
    )
    @action(detail=True, methods=["get"], url_path="allocation-coverage")
    def allocation_coverage(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture-elements/{id}/allocation-coverage/

        REQ-L1-042: Returns allocation coverage metrics for this ArchitectureElement.
        The published contract (200 body, error codes) is the ``extend_schema``
        block above.

        Response:
          - allocated_count: Number of Requirements allocated to this element.
          - not_allocatable_count: Requirements deliberately excluded from the
            coverage denominator.
          - coverage_percent: Percentage (0…100) of allocated vs allocatable
            requirements (GH-1883: renamed from ``coverage_ratio``).
          - unallocated_requirements: List of ``{id, uid, title}`` for the
            workspace requirements not allocated to this element.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            from application.trace_link_service import TraceLinkService
            svc = TraceLinkService()
            report = svc.get_allocation_coverage(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(report)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/diff/?from_version=0&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_architecture_element(UUID(pk), ctx)
            artifact_id = item.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(item.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
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

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_architecture_element(UUID(pk), ctx)
            artifact_id = item.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    # #447: drf-spectacular cannot introspect ``request.query_params.get(...)``
    # calls, so this action shipped documenting only the path parameter while
    # accepting six query parameters — the schema was unusable for client
    # generation, and the correct path was undiscoverable for anyone reading
    # the spec instead of the source (#446). Declared explicitly; keep this
    # list in sync with the parsing below.
    @extend_schema(
        summary="Requirement bundle export for an architecture element",
        parameters=[
            OpenApiParameter(
                name="depth",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Maximum number of ALLOCATED_TO levels to walk below this "
                    "element. Omitted = unlimited."
                ),
            ),
            OpenApiParameter(
                name="filter_mode",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["all", "visible", "custom"],
                default="all",
                description="Which requirement fields to include.",
            ),
            OpenApiParameter(
                name="fields",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Comma-separated field whitelist, used with "
                    "``filter_mode=custom``."
                ),
            ),
            OpenApiParameter(
                name="output_format",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["json", "markdown", "csv"],
                default="json",
                description=(
                    "Response format for ``mode=raw``; ignored for "
                    "``mode=compressed``. Deliberately not ``?format=``, which "
                    "is DRF's reserved content-negotiation override."
                ),
            ),
            OpenApiParameter(
                name="mode",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["raw", "compressed"],
                default="raw",
                description=(
                    "``raw`` returns the bundle as stored; ``compressed`` routes "
                    "it through the LLM compression service."
                ),
            ),
            OpenApiParameter(
                name="async",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                default=False,
                description=(
                    "``mode=compressed`` only: dispatch the compression to a "
                    "Celery worker and answer 202 with a ``task_id`` to poll at "
                    "``GET /api/v1/bundle-compression-status/{task_id}/``. "
                    "Forced on for bundles over SYNC_ITEM_COUNT_THRESHOLD items."
                ),
            ),
        ],
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="requirement-bundle",
        # The output format is an app-level concern here, not a DRF rendering
        # one: markdown/CSV leave as a raw HttpResponse. Pinning renderer +
        # negotiation to JSON keeps DRF's Accept/?format= machinery from
        # intercepting the request before this method runs — see
        # _JsonOnlyContentNegotiation.
        renderer_classes=[JSONRenderer],
        content_negotiation_class=_JsonOnlyContentNegotiation,
    )
    def requirement_bundle(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/requirement-bundle/
            ?depth=<int>&filter_mode=<all|visible|custom>&fields=<comma-list>
            &output_format=<json|markdown|csv>&mode=<raw|compressed>&async=<true|false>

        Requirement Bundle Export, Plan 1 Task 5. Raw (non-AI) bundle of every
        Requirement ALLOCATED_TO this element or its ALLOCATED_TO
        sub-elements, up to `depth` levels.

        Requirement Bundle Export, Plan 2 Task 4: ``?mode=compressed`` routes
        the same bundle through ``BundleCompressionService`` instead of the
        raw json/markdown/csv formatters below. ``?output_format=`` is
        ignored in that branch (compressed output is always a single text
        blob). ``&async=true`` (or a bundle over
        ``SYNC_ITEM_COUNT_THRESHOLD`` items) dispatches the compression to a
        Celery worker and returns ``202`` with a ``task_id`` to poll via
        ``GET /api/v1/bundle-compression-status/{task_id}/`` instead of
        blocking the request thread on an LLM call.

        ``mode=compressed`` is lossless, token-density compression for
        machine consumption, not a lossy human summary (issue #442) — every
        fact in the raw bundle must still be recoverable afterward, so it is
        not guaranteed to shrink a bundle whose content is already dense
        attribute data (e.g. every field of every requirement populated).
        Without an LLM provider configured (this project's default is
        ``LLM_PROVIDER=mock``) no compression happens at all — ``provider``
        reports ``mock``, ``is_mock_fallback`` is true, and the text is a
        placeholder prefixed with ``[MOCK FALLBACK] ``. Treat that as "no
        compression available", not as a compressed bundle. To reduce the
        raw size before compression, narrow ``?filter_mode=custom&fields=``
        to the columns actually needed.

        The output format is selected with ``?output_format=`` — deliberately
        *not* ``?format=``, which is DRF's reserved URL_FORMAT_OVERRIDE and
        collides with content negotiation. ``Accept`` and ``?format=`` are
        ignored by this action; an unknown ``output_format`` value returns
        ``400 VALIDATION_ERROR``.

        **Id spaces in the response.** ``items[].requirement_id`` is
        ``Requirement.id`` and resolves directly against
        ``/api/v1/requirements/{id}/``. ``items[].found_under_element_id`` is
        NOT an ``ArchitectureElement.id`` — it is the element's backing
        **Artifact** id (``ArchitectureElement.artifact_id``), while the
        ``{pk}`` this endpoint takes IS an ``ArchitectureElement.id``. The two
        are different UUIDs, so ``GET /api/v1/architecture/{found_under_element_id}/``
        will 404. Correlating a returned value back to a specific element
        requires resolving through the Artifact layer: look the element up by
        its ``artifact_id`` (the inverse mapping, element id -> artifact id,
        is ``TraceLinkService._resolve_artifact_id``). This is a deliberate
        design choice — the allocation walk operates on artifact ids end to
        end — and is documented rather than changed, since the returned
        values are part of the published contract.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            element = self._svc().get_architecture_element(UUID(pk), ctx)
            workspace_id = element.artifact.workspace_id

            query, invalid = self._parse_bundle_query_params(request, lang)
            if invalid is not None:
                return invalid

            result = RequirementBundleQueryService().get_bundle(
                ctx,
                root_id=UUID(pk),
                workspace_id=workspace_id,
                depth=query["depth"],
                filter_mode=query["filter_mode"],
                fields=query["fields"],
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except BundleDepthExceededError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        if query["mode"] == "raw":
            return self._render_raw_bundle(result, query["output_format"])

        # mode == "compressed" — route the same bundle through
        # BundleCompressionService (Plan 2 Task 1/2) instead of the raw
        # formatters above. ?output_format= is not applicable here.
        return self._compress_bundle(
            request,
            ctx,
            result,
            pk,
            query["depth"],
            query["filter_mode"],
            query["fields"],
            workspace_id,
            lang,
        )

    def _parse_bundle_query_params(
        self, request: Request, lang: str
    ) -> tuple[dict[str, Any], Response | None]:
        """Resolve the query parameters shared by both bundle modes.

        Returns the parsed bundle query and ``None``, or ``None`` and the
        ``400 VALIDATION_ERROR`` response for an unknown ``output_format``
        or ``mode`` (validated in that order). A malformed ``depth`` still
        raises ``ValueError`` for the caller's error handler, which keeps
        the documented 400 contract.
        """
        depth_param = request.query_params.get("depth")
        depth = int(depth_param) if depth_param is not None else None

        filter_mode = request.query_params.get("filter_mode", "all")
        fields_param = request.query_params.get("fields")
        fields = fields_param.split(",") if fields_param else None

        output_format = request.query_params.get("output_format", "json")
        if output_format not in ("json", "markdown", "csv"):
            return None, Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message=(
                        f"Invalid output_format {output_format!r}; "
                        "expected json, markdown, or csv"
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        mode = request.query_params.get("mode", "raw")
        if mode not in ("raw", "compressed"):
            return None, Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message=f"Invalid mode {mode!r}; expected raw or compressed",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return {
            "depth": depth,
            "filter_mode": filter_mode,
            "fields": fields,
            "output_format": output_format,
            "mode": mode,
        }, None

    @staticmethod
    def _render_raw_bundle(result: Any, output_format: str) -> Response:
        """Render the raw bundle in the requested ``output_format``."""
        if output_format == "json":
            return Response(format_bundle_json(result))
        if output_format == "markdown":
            return HttpResponse(
                format_bundle_markdown(result), content_type="text/markdown; charset=utf-8"
            )
        return HttpResponse(format_bundle_csv(result), content_type="text/csv; charset=utf-8")

    def _compress_bundle(
        self,
        request: Request,
        ctx: Any,
        result: Any,
        pk: str,
        depth: int | None,
        filter_mode: str,
        fields: list[str] | None,
        workspace_id: Any,
        lang: str,
    ) -> Response:
        """Route the bundle through BundleCompressionService (Plan 2 Task 1/2).

        ``?output_format=`` is not applicable here. Dispatches the
        compression to a Celery worker and answers 202 with a ``task_id``
        (503 if the broker is unconfigured) when ``?async=true`` is sent or
        the bundle exceeds ``SYNC_ITEM_COUNT_THRESHOLD`` items; otherwise
        the compression runs synchronously.
        """
        try:
            from application.bundle_compression_service import (
                SYNC_ITEM_COUNT_THRESHOLD,
                BundleCompressionService,
            )

            force_async = request.query_params.get("async", "").lower() == "true"
            use_async = force_async or len(result.items) > SYNC_ITEM_COUNT_THRESHOLD

            compression_svc = BundleCompressionService()
            root_id = UUID(pk)
            if use_async:
                dispatch = compression_svc.compress_async(
                    ctx,
                    result,
                    root_id=root_id,
                    depth=depth,
                    filter_mode=filter_mode,
                    fields=fields,
                    format="markdown",
                    workspace_id=workspace_id,
                )
                if isinstance(dispatch, dict):  # BROKER_NOT_CONFIGURED
                    return Response(dispatch, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                return Response({"task_id": dispatch}, status=status.HTTP_202_ACCEPTED)

            compression = compression_svc.compress(
                ctx,
                result,
                root_id=root_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
                format="markdown",
                workspace_id=workspace_id,
            )
            return Response({
                "text": compression.text,
                "cache_hit": compression.cache_hit,
                "is_mock_fallback": compression.is_mock_fallback,
                # Issue #442: name the provider that actually produced the
                # text, so a client can distinguish a real AI compression
                # from a mock placeholder without parsing the text.
                "provider": compression.provider,
            })
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)



# ---------------------------------------------------------------------------
# TestCaseViewSet
# ---------------------------------------------------------------------------


class TestCaseViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for TestCase CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TestCaseSerializer
    preset_endpoint_key = ""
    workflow_item_type = "TestCase"
    attribute_item_type = "TestCase"

    def _svc(self) -> TestService:
        return TestService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_test_case(UUID(pk), ctx)
        return item.id, item.artifact.workspace_id

    # #915: like RequirementViewSet, TestCase has no denormalized ``status``
    # column anymore (Datenmodell-Konsolidierung Task 12); the shared
    # ``WorkflowTransitionsMixin._current_status`` resolves it from the engine.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_test_case(item_id, ctx)
        return {"test_case": TestCaseSerializer(_test_to_dict(updated)).data}

    @list_schema(status=True, search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/test-cases/ — list test cases.

        Issue #267: optional ``?search=<term>`` case-insensitively filters on
        title/description/uid (same root cause as RequirementViewSet).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            search = request.query_params.get("search") or None
            status_filter = request.query_params.get("status") or None
            items = self._svc().list_test_cases(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                search=search,
                status=status_filter,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: TestCaseSerializer(
                [_test_to_dict(i) for i in page], many=True
            ).data,
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/testcases/{pk}/ — retrieve a single test case.

        GH-868: the response carries ``ETag: "<version>"``; send it back as
        ``If-Match`` on a PATCH to make the write conditional (412 when stale).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        payload = TestCaseSerializer(_test_to_dict(item)).data
        # #399: additive drift summary for the editor header (no extra request).
        payload["baseline_drift"] = _baseline_drift_summary(item.artifact_id, ctx)
        return self.with_etag(Response(payload), item)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/testcases/ — create a test case. Returns 201.

        #1079: the 201 carries ``ETag: "<version>"`` (baselines fall back to
        ``created_at``, see :func:`compute_etag`) so the response that hands out
        the new id is also the response that hands out the value a following
        ``If-Match`` needs.
        """
        lang = detect_lang(request)
        ser = TestCaseSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        # #816/#953: `create_test_case()` has exactly one test-type
        # representation — the canonical `TestCase.test_type` column (lowercase
        # `TestCaseType` values). The serializer field below maps onto it and
        # is forwarded as `test_type_value`, which the service treats as the
        # deprecated alias of its `test_type` parameter. `None` (field omitted
        # or explicitly null) keeps the column NULL: the REST create contract
        # stays "omitted means unspecified", and the UI dialog preselects the
        # documented `unit` default instead (#953).
        try:
            ctx = get_auth_context(request)
            definition_error = self._validate_attribute_definition(
                ctx,
                data.get("workspace_id"),
                dict(request.data) if isinstance(request.data, dict) else {},
                None,
            )
            if definition_error is not None:
                return definition_error
            item = self._svc().create_test_case(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                steps=data.get("steps") or None,
                custom_fields=data.get("custom_fields"),
                test_type_value=data.get("test_type"),
                # #424: the client states provenance; `reviewed` is NOT part of
                # the API surface (the service derives it from `origin`). This
                # REST path is the productive persistence path of the UI
                # (DeriveTestCasePanel -> testcasesApi.create), which is why it
                # must forward `origin` at all.
                origin=data.get("origin", "manual"),
                # #402: off-nominal categorisation.
                scenario_kind=data.get("scenario_kind", "nominal"),
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "TestCase", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        # SysEng 2.0 N5: optional 'verifies' TraceLink to the source requirement
        # (ADR-L3-MC005-01 convention, mirrored here for the REST create path).
        # Non-fatal: the TestCase is already created, so a link failure never
        # turns the create into an error response. Instead, the outcome is
        # surfaced via 'verifies_link_id' in the response body (present =
        # link created, null = not requested or creation failed) — mirrors
        # the MCP test.create 'trace_link_id' pattern (mcp_server/tools/tests.py).
        linked_requirement_id = data.get("linked_requirement_id")
        verifies_link_id: str | None = None
        if linked_requirement_id:
            try:
                trace_link = TraceLinkService().create_trace_link(
                    source_id=item.artifact_id,
                    target_id=linked_requirement_id,
                    link_type="verifies",
                    ctx=ctx,
                )
                verifies_link_id = str(trace_link.id)
            except Exception:
                logger.warning(
                    "TraceLinkService.create_trace_link failed for TestCase %s "
                    "-> Requirement %s",
                    item.id,
                    linked_requirement_id,
                    exc_info=True,
                )

        response_data = _test_to_dict(item)
        response_data["verifies_link_id"] = verifies_link_id
        # #1079: the 201 carries the new ETag, like the detail GET and PATCH.
        return self.with_etag(
            Response(
                TestCaseSerializer(response_data).data,
                status=status.HTTP_201_CREATED,
            ),
            item,
        )

    @extend_schema(
        # #1397: the header the declared 412 is conditioned on. Both router
        # spellings (``testcases`` and ``test-cases``) document it, because they
        # are this same view.
        # #1388/F3: and the response header that supplies the next tag.
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: TestCaseSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/testcases/{pk}/ — update a test case. Returns 200.

        GH-868: a stale ``If-Match`` is refused with 412 PRECONDITION_FAILED and
        the response carries the new ``ETag``; without an ``If-Match`` the body's
        ``expected_version`` keeps answering 409 CONFLICT unchanged.
        """
        lang = detect_lang(request)
        # GH-1396: malformed header → 400 before the payload guards read anything.
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=TestCaseSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = TestCaseSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        extra_kwargs: dict[str, Any] = {}
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        # Task 22 fix: `steps` is a real, writable `TestCaseSerializer` field
        # (validated above) that `update_test_case()` has always accepted —
        # this view simply never forwarded it, so every steps_editor widget
        # PATCH silently no-op'd (200 OK, unchanged `steps` on the very next
        # GET). Proven live via a real create -> GET -> PATCH -> GET
        # round-trip against a real dev workspace. Same conditional-forward
        # pattern as `custom_fields` above: only touch it when the partial
        # payload actually carries it.
        if "steps" in data:
            extra_kwargs["steps"] = data["steps"]
        # C-1 fix round: same conditional-forward pattern as `steps` above —
        # `test_type` is now a real, writable `TestCaseSerializer` field
        # (validated above); forward it so the introspected select widget's
        # PATCH actually persists instead of only passing validation.
        if "test_type" in data:
            extra_kwargs["test_type"] = data["test_type"]
        # #402: same conditional-forward pattern — `scenario_kind` is writable
        # and `update_test_case()` accepts it. `origin`/`reviewed` are
        # deliberately NOT forwarded (immutable / review-action only); a
        # request carrying them is rejected by the serializer's validate().
        if "scenario_kind" in data:
            extra_kwargs["scenario_kind"] = data["scenario_kind"]
        try:
            ctx = get_auth_context(request)
            # REQ-165/REQ-166 (CR-08): `status` is intentionally NOT forwarded
            # (and is now read-only on TestCaseSerializer, see there). Change the
            # lifecycle state via POST /api/v1/testcases/{id}/transitions/.
            # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
            # stale expected_version → OptimisticLockError → 409 CONFLICT.
            # GH-868: an If-Match header takes precedence (see RequirementViewSet).
            # GH-1396: the lazy loader runs only for header shapes that need a
            # real ETag comparison; a single strong integer tag stays read-free.
            item = self._svc().update_test_case(
                test_case_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                change_reason=data.get("change_reason"),
                expected_version=self.resolve_expected_version(
                    request,
                    data,
                    current=lambda: self._svc().get_test_case(UUID(pk), ctx),
                ),
                **extra_kwargs,
            )
            # Attribut v3 WS2 (#936): owner/reporter/priority live on Artifact.
            self._apply_artifact_system_fields(request, "TestCase", item, ctx)
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            # GH-1396: malformed → 400 INVALID_IF_MATCH, unmatchable → 412.
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            # GH-868: a failed If-Match is a precondition failure (412); the
            # body field keeps its existing 409 CONFLICT contract.
            if self.uses_if_match(request):
                return self.precondition_failed(request)
            return _service_error_response(exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(Response(TestCaseSerializer(_test_to_dict(item)).data), item)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/testcases/{pk}/ — soft-delete a test case. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state) and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        Caveat, unchanged by GH-443: unlike the other soft-deleting entities,
        this one still hard-deletes every TraceLink touching the record, so a
        later reactivate brings the record back without its links.
        """
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_test_case(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/testcases/{pk}/review/ — set the in-content review flag.

        #424: this is the only write path for ``reviewed`` (the serializer
        exposes it read-only and rejects a PATCH carrying it). A manually
        created test case starts reviewed; an ``origin="ai_generated"`` one
        starts unreviewed and stops counting as verification evidence /
        coverage until this endpoint flips it.

        Body (both fields optional)::

            {"reviewed": true, "change_reason": "..."}

        ``reviewed`` defaults to ``true``. The call is idempotent — a second
        call with the same value does not bump ``version`` again.

        A non-object body (list/string/number) is rejected with
        ``400 VALIDATION_ERROR`` rather than coerced to ``{}``: coercing would
        silently apply the ``reviewed=true`` default to a request that never
        carried an intent to review anything. An empty/missing body (``{}``)
        keeps the documented ``reviewed=true`` default.

        Returns the full ``TestCaseSerializer`` representation (200).
        """
        lang = detect_lang(request)
        if not isinstance(request.data, dict):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {
                            "field": "body",
                            "errors": ["Request body must be a JSON object."],
                        }
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = request.data
        reviewed = body.get("reviewed", True)
        if not isinstance(reviewed, bool):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": "reviewed", "errors": ["Must be a boolean."]}
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        change_reason = body.get("change_reason") or ""
        if not isinstance(change_reason, str):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": "change_reason", "errors": ["Must be a string."]}
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            item = self._svc().mark_reviewed(
                UUID(pk), ctx, reviewed=reviewed, change_reason=change_reason
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(TestCaseSerializer(_test_to_dict(item)).data)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/testcases/{pk}/diff/?from_version=0&to_version=2

        REQ-L2-AS-032 / REQ-L1-040: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            test_case = self._svc().get_test_case(UUID(pk), ctx)
            artifact_id = test_case.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(test_case.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
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

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/testcases/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            test_case = self._svc().get_test_case(UUID(pk), ctx)
            artifact_id = test_case.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)



def _dto_from_orm(req: Any) -> dict[str, Any]:
    """Convert Requirement ORM object to serializer-compatible dict.

    #344: ``type``, ``complexity_fibonacci`` and ``verification_method`` used to
    be missing here. Because ``RequirementSerializer.type`` declares
    ``default='SyReq'``, DRF substituted that default on *representation*, so
    every REST response claimed ``type: "SyReq"`` and
    ``complexity_fibonacci: null`` no matter what was stored. The UI reads those
    values back into the form and echoes them on the next save, silently
    reverting a real UseCase/FeatureReq classification (and any stored
    complexity/verification method) on an unrelated description edit. Every
    field the serializer can render must be sourced from the ORM object here.
    """
    return {
        "id": str(req.id),
        "workspace_id": str(req.artifact.workspace_id) if hasattr(req, "artifact") else None,
        "artifact_id": str(req.artifact_id) if getattr(req, "artifact_id", None) else None,
        "parent_id": (
            str(parent_id)
            if (parent_id := getattr(getattr(req, "artifact", None), "parent_id", None))
            else None
        ),
        "title": req.title,
        "description": getattr(req, "description", ""),
        "rationale": getattr(req, "rationale", ""),
        "source": getattr(req, "source", ""),
        "acceptance_criteria": getattr(req, "acceptance_criteria", ""),
        # #1288: structured criteria list, additively exposed read-only.
        "acceptance_criteria_items": getattr(req, "acceptance_criteria_items", None) or [],
        "uid": getattr(req, "uid", None),
        "category": getattr(req, "category", ""),
        "status": getattr(req, "status", "draft"),
        "type": getattr(req, "type", None) or "SyReq",
        "complexity_fibonacci": getattr(req, "complexity_fibonacci", None),
        "verification_method": getattr(req, "verification_method", None) or None,
        "level": getattr(req, "level", None),
        # P2 (V4/V5): the stable ladder key. It was declared on the serializer
        # but never sourced here, so DRF skipped it on every response and
        # ``tier_name`` had nothing to resolve. Additive read field only.
        "tier_key": getattr(req, "tier_key", None),
        # P2: the allocation intent is declared on the serializer but was never
        # sourced here, so DRF skipped it on every response (required=False).
        # The attribute is visible in the bootstrapped definition — a read-back
        # that omits it is the REST half of the parity gap the attribute
        # contract matrix ratchets (#935). Additive read field only: writes
        # still go through the allocation service / the create payload.
        "allocation_intent": getattr(req, "allocation_intent", "unassigned"),
        "level_source": getattr(req, "level_source", "derived"),
        "suspect": getattr(req, "suspect", False),
        "custom_fields": _artifact_custom_fields(req),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(req),
        "version": req.version,
        "created_at": req.created_at,
        "updated_at": req.modified_at,
    }



def _service_warnings(entity: Any) -> list[str]:
    """Return the non-blocking warnings a service attached to *entity*.

    Issue #1178: ``RequirementService.create_requirement`` reports a
    normalized-equal title as a transient ``duplicate_title_warning`` attribute
    on the returned ORM object instead of raising (a rejection would break
    every create client — the issue says "warning, not rejection"). The create
    route mirrors it into the response body as an additive ``warnings`` list;
    the list is omitted entirely when there is nothing to report, so a clean
    create keeps its exact pre-existing body.

    The ``str`` type check is deliberate: a mocked/stubbed service (used by
    several view tests) hands back a mock whose arbitrary attributes are truthy
    non-strings — mirroring one of those into a JSON body would answer a 201
    with an unserialisable value.
    """
    warning = getattr(entity, "duplicate_title_warning", None)
    return [warning] if isinstance(warning, str) and warning else []



def _need_to_dict(need: Any) -> dict[str, Any]:
    """Merge the Artifact-level system fields into a StakeholderNeedDTO dict.

    Attribut v3 WS2 (#936): ``StakeholderNeedService`` returns a DTO whose
    ``to_dict()`` (``asdict``) cannot carry the actor FKs; the DTO does expose
    its backing ``artifact``, so the actor wire values are merged in here rather
    than read from the serializer's ``to_representation`` (which only injects
    for a raw ORM instance, not for this pre-built dict).
    """
    return {**need.to_dict(), **artifact_system_fields(need)}



def _artifact_to_dict(art: Any) -> dict[str, Any]:
    """Convert Artifact ORM object to dict."""
    return {
        "id": str(art.id),
        "workspace_id": str(art.workspace_id) if hasattr(art, "workspace_id") else None,
        "artifact_type": getattr(art, "artifact_type", ""),
        # TODO (hierarchy consolidation): Artifact.parent is deprecated —
        # domain services (Requirement/StakeholderNeed/Adr/...) leave it
        # NULL and express hierarchy via 'derives-from' TraceLinks instead
        # (see persistence/models.py Artifact.parent docstring).
        "parent_id": str(art.parent_id) if getattr(art, "parent_id", None) else None,
        "sort_key": getattr(art, "sort_key", None),
        "custom_fields": getattr(art, "custom_fields", None) or {},
        "version": art.version,
        "created_at": art.created_at,
        "updated_at": art.modified_at,
    }



def _arch_to_dict(el: Any) -> dict[str, Any]:
    """Convert ArchitectureElement ORM object to dict.

    REQ-L2-RA-013: Prefers CTE-annotated 'level' field (from
    ``ArchitectureElement.annotate_levels()``) to avoid N+1 queries. Falls
    back to Python get_level() only if not annotated.
    """
    # Prefer annotated level field (from CTE) over recursive method call
    level = getattr(el, 'level', None)
    if level is None and hasattr(el, 'get_level'):
        level = el.get_level()
    if level is None:
        level = 0

    # SysEng 2.0 §1.2: derived structural role. Prefers the bulk-annotated
    # ``_role_annotated`` (set by ArchitectureService for list responses) and
    # falls back to the single-instance ``role`` property (one EXISTS query) on
    # retrieve/create/update paths.
    role = getattr(el, "role", None)

    return {
        "id": str(el.id),
        "workspace_id": str(el.artifact.workspace_id) if hasattr(el, "artifact") else None,
        # REQ-016 / UI concept ch. 12.11: the frontend needs the owning
        # Artifact id to read and write workspace-defined custom fields via
        # /artifacts/<id>/custom-field-values/. The OneToOne has always
        # existed on the model; only the API never exposed it.
        "artifact_id": str(el.artifact_id) if getattr(el, "artifact_id", None) else None,
        "title": el.title,
        "description": getattr(el, "description", ""),
        "uid": getattr(el, "uid", None),
        "element_type": getattr(el, "element_type", ""),
        "parent_id": str(el.parent_id) if getattr(el, "parent_id", None) else None,
        "level": level,
        "role": role,
        # Task 24 finding: these three columns were missing from this dict
        # entirely. `ArchitectureElementSerializer.asil_level`/`make_or_buy`
        # are `allow_null=True` with no attribute error path other than
        # SkipField, and DRF's `Field.get_attribute` special-cases
        # `allow_null` fields to serialize a missing attribute as `None`
        # rather than skip them — so every GET/LIST/CREATE/PATCH response
        # silently reported `null` regardless of the real stored value.
        # `suspect` has `default=False` on the serializer, so a missing key
        # always resolved to `False` the same way. Live-proven: a real
        # `asil_level="B"`/`make_or_buy="Make"` create round-tripped back as
        # `null`/`null` on the very next GET, while the DB row genuinely held
        # "B"/"Make". Pre-existing since this dict was introduced — the old
        # `ArchitectureForm.tsx` read the same broken response, so its ASIL/
        # Make-or-Buy dropdowns always showed "not set" and every save from
        # it silently cleared any previously-set value (same failure class as
        # the Task 19 `uid`/Task 20 `severity` findings, just on the read side
        # instead of the write side).
        "asil_level": getattr(el, "asil_level", None),
        "make_or_buy": getattr(el, "make_or_buy", None),
        "suspect": getattr(el, "suspect", False),
        "custom_fields": _artifact_custom_fields(el),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(el),
        "version": el.version,
        "created_at": el.created_at,
        "updated_at": el.modified_at,
    }



def _test_to_dict(tc: Any) -> dict[str, Any]:
    """Convert TestCase ORM object to dict."""
    return {
        "id": str(tc.id),
        # #399 (MAJOR-1): the backing Artifact id, distinct from the TestCase
        # entity pk. `GET /artifacts/{id}/baseline-membership/` and
        # `ChangeRequest.affected_item_ids` key on Artifact ids, so the editor
        # header must be able to send this value (it used to send the entity
        # pk, which the membership endpoint answered with a 404).
        "artifact_id": (
            str(tc.artifact_id) if getattr(tc, "artifact_id", None) else None
        ),
        "workspace_id": str(tc.artifact.workspace_id) if hasattr(tc, "artifact") else None,
        "title": tc.title,
        "description": getattr(tc, "description", ""),
        "uid": getattr(tc, "uid", None),
        "status": getattr(tc, "status", "draft"),
        "steps": getattr(tc, "steps", []) or [],
        # C-1 fix round: real, writable model column (see TestCaseSerializer.
        # test_type docstring) — was missing from the read path entirely, so
        # the ArtifactForm's initial value was always empty regardless of
        # what had been saved.
        "test_type": getattr(tc, "test_type", None),
        # #424/#402: provenance, review flag and off-nominal category. Read-only
        # provenance fields; `reviewed` moves via POST .../review/.
        "origin": getattr(tc, "origin", "manual"),
        "reviewed": bool(getattr(tc, "reviewed", False)),
        "scenario_kind": getattr(tc, "scenario_kind", "nominal"),
        "custom_fields": _artifact_custom_fields(tc),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(tc),
        "version": tc.version,
        "created_at": tc.created_at,
        "updated_at": tc.modified_at,
    }



def _document_to_dict(document: Any) -> dict[str, Any]:
    """Convert a ``Document`` ORM row to the serializer-compatible dict.

    ``status`` is intentionally absent: ``DocumentSerializer`` resolves it from
    the workflow engine (``WorkflowStateSerializerMixin``), which is also what
    turns a soft-deleted document into ``"outdated"`` via the state reader's
    lifecycle join. ``doc_date`` is passed through as a ``date``; the DRF
    ``DateField`` renders it as ISO-8601.
    """
    return {
        "id": str(document.id),
        "workspace_id": str(document.workspace_id),
        "artifact_id": (
            str(document.artifact_id)
            if getattr(document, "artifact_id", None)
            else None
        ),
        "uid": getattr(document, "uid", None),
        "title": document.title,
        "kind": document.kind,
        "description": getattr(document, "description", ""),
        "body": getattr(document, "body", ""),
        "doc_date": getattr(document, "doc_date", None),
        "frozen_at": getattr(document, "frozen_at", None),
        "frozen_fields": list(getattr(document, "frozen_fields", None) or []),
        # Phase G / #1374 S3: dual-source and projection bookkeeping (read-only).
        "owner_mode": getattr(document, "owner_mode", "loom"),
        "source_path": getattr(document, "source_path", ""),
        "source_sha256": getattr(document, "source_sha256", ""),
        "projection_mode": getattr(document, "projection_mode", "none"),
        "projected_sha256": getattr(document, "projected_sha256", ""),
        "projected_version": getattr(document, "projected_version", None),
        "custom_fields": _artifact_custom_fields(document),
        "version": document.version,
        "created_at": document.created_at,
        # ``Document`` inherits the house ``modified_at`` column (it does not
        # define its own ``updated_at`` like Adr/Risk); the wire key stays
        # ``updated_at`` so the contract matches every other artifact.
        "updated_at": document.modified_at,
    }



def _work_item_to_dict(item: Any) -> dict[str, Any]:
    """Convert a ``WorkItem`` ORM row to the serializer-compatible dict.

    ``status`` is intentionally absent — ``WorkItemSerializer`` resolves it
    from the workflow engine (``WorkflowStateSerializerMixin``), which is also
    what turns a soft-deleted item into ``"outdated"`` (G1.5). ``due_date``,
    ``approved_at`` and ``last_activity_at`` stay ``datetime`` values so the
    DRF fields render them as ISO-8601. The wire key for the house
    ``modified_at`` column is ``updated_at``, matching every other artifact.
    """
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "document_id": str(item.document_id),
        "artifact_id": (
            str(item.artifact_id) if getattr(item, "artifact_id", None) else None
        ),
        "uid": getattr(item, "uid", None),
        "title": item.title,
        "kind": item.kind,
        "ordinal": item.ordinal,
        "body": getattr(item, "body", ""),
        "progress": item.progress,
        "blocked_reason": getattr(item, "blocked_reason", ""),
        "next_action": getattr(item, "next_action", ""),
        "last_activity_at": item.last_activity_at,
        "last_actor": getattr(item, "last_actor", ""),
        "evidence_ref": getattr(item, "evidence_ref", ""),
        "approved_by": getattr(item, "approved_by", ""),
        "approved_at": item.approved_at,
        "due_date": item.due_date,
        "exit_criteria": getattr(item, "exit_criteria", ""),
        "custom_fields": _artifact_custom_fields(item),
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.modified_at,
    }



# ---------------------------------------------------------------------------
# ArtifactBulkUpdateView — R3.2 (document view batch write)
# ---------------------------------------------------------------------------


class ArtifactBulkUpdateView(APIView):
    """PATCH /api/v1/artifacts/bulk-update/ — write several artifacts at once.

    The batch write of the editable document/table view (plan R3). Deliberately
    an ``APIView`` and **not** a ``ViewSet`` action: the path lives on the
    ``artifacts/`` collection, and a router would have to treat
    ``bulk-update`` as a detail pk (``artifacts/<pk>/`` matches any non-slash
    segment). ``rest_api.urls`` therefore registers it *before* ``router.urls``,
    exactly like ``artifacts/<uuid>/comments/``.

    Contract
    --------
    * **200** — every entry was written; ``{"updated": [{artifact_id, version}],
      "errors": []}``.
    * **409** — at least one entry was refused (stale version, freeze, unknown
      field, foreign workspace, …). **Nothing** was written; the body is the same
      ``{"updated": [], "errors": [...]}`` shape, so a client can mark the row by
      ``index`` instead of re-reading the page.
    * **400** — the request itself is malformed: a bad entry schema, an empty
      ``entries`` list, or more than ``MAX_ENTRIES`` items.
    * **403** — the caller holds no write role in the workspace.

    Every write goes through :class:`application.bulk_update_service
    .BulkUpdateService` (ADR-01); this class only translates.
    """

    @extend_schema(
        tags=["artifacts"],
        summary="Bulk-update several artifacts in one transaction",
        description=(
            "Applies 1..100 per-artifact writes in a single transaction. Either "
            "every entry is written (200) or none is (409) — the errors list "
            "names the refusing entry by index and code. Supports the artifact "
            "types that have their own write service: Document and Requirement."
        ),
        request=BulkUpdateRequestSerializer,
        responses={
            200: BulkUpdateResponseSerializer,
            400: OpenApiResponse(
                description=(
                    "Malformed body, an empty entries list, or more than "
                    f"{MAX_BULK_ENTRIES} entries."
                )
            ),
            403: OpenApiResponse(
                description="The caller has no write role in the workspace."
            ),
            409: BulkUpdateResponseSerializer,
        },
    )
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        serializer = BulkUpdateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": key, "errors": value}
                        for key, value in serializer.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        entries = [
            BulkEntry(
                artifact_id=entry["artifact_id"],
                expected_version=entry["expected_version"],
                fields=entry["fields"],
            )
            for entry in data["entries"]
        ]

        try:
            ctx = get_auth_context(request)
            result = BulkUpdateService().apply(data["workspace_id"], entries, ctx)
        except Exception as exc:  # noqa: BLE001 — mapped by _service_error_response
            return _service_error_response(exc, lang)

        if result.errors:
            # 409 with the same body shape as the success case: the request was
            # well-formed and authorised, it conflicted with the stored state.
            return Response(result.to_dict(), status=status.HTTP_409_CONFLICT)
        return Response(result.to_dict(), status=status.HTTP_200_OK)



# ---------------------------------------------------------------------------
# ArtifactBulkTransitionView — slice 2 of the Tabellenansicht plan
# ---------------------------------------------------------------------------


class ArtifactBulkTransitionView(APIView):
    """POST /api/v1/artifacts/bulk-transition/ — move several rows to one state.

    The bulk accept/reject/release action of the table view (slice 2, spec
    §3.2). Like :class:`ArtifactBulkUpdateView` an ``APIView`` on the
    ``artifacts/`` collection, registered *before* ``router.urls`` so the
    router's ``artifacts/<pk>/`` detail pattern cannot swallow the segment.

    Contract
    --------
    * **200** — every row was processed. ``{"transitioned": [{artifact_id,
      state}], "failed": [{index, artifact_id, code, message}]}``. Partial
      success is the *specified* behaviour (a state graph legitimately refuses a
      subset), so failures keep 200 rather than turning the page into an error.
    * **400** — the request itself is malformed: empty/duplicate id list, more
      than ``MAX_TRANSITION_IDS`` ids, an empty ``change_reason``/``to_state``,
      or ids spanning two workspaces.
    * **403** — the caller holds no write role in the workspace the ids belong
      to (the workspace is derived from the ids, see
      :class:`application.bulk_update_service.BulkUpdateService`).

    No ``If-Match``/412: optimistic locking on this path is the workflow row's
    own CAS, and the route publishes none (contract gate
    ``rest_api/conditional_requests.py``).

    The write itself is never this class's business (ADR-01): every id runs
    through :class:`application.bulk_update_service.BulkUpdateService`
    ``.bulk_transition`` → ``WorkflowFacade.transition``.
    """

    @extend_schema(
        tags=["artifacts"],
        summary="Bulk-transition several artifacts into one workflow state",
        description=(
            f"Moves 1..{MAX_BULK_TRANSITION_IDS} artifacts of one type into one "
            "target state, each through the workspace's own workflow graph. "
            "Partial success: rows the graph or a gate refuses are reported in "
            "failed[] and do not stop the others. The workspace is derived from "
            "the ids (no workspace_id in the body) and the caller must hold a "
            "write role there."
        ),
        request=BulkTransitionRequestSerializer,
        responses={
            200: BulkTransitionResponseSerializer,
            400: OpenApiResponse(
                description=(
                    "Malformed body, an empty/duplicate id list, more than "
                    f"{MAX_BULK_TRANSITION_IDS} ids, or ids of two workspaces."
                )
            ),
            403: OpenApiResponse(
                description=(
                    "The caller has no write role in the workspace the ids "
                    "belong to."
                )
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        serializer = BulkTransitionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": key, "errors": value}
                        for key, value in serializer.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        try:
            ctx = get_auth_context(request)
            result = BulkUpdateService().bulk_transition(
                ctx,
                data["item_type"],
                data["ids"],
                data["to_state"],
                data["change_reason"],
            )
        except Exception as exc:  # noqa: BLE001 — mapped by _service_error_response
            return _service_error_response(exc, lang)

        return Response(result.to_dict(), status=status.HTTP_200_OK)



# ---------------------------------------------------------------------------
# DocumentViewSet — Plan F F2-T5 (PR-F18a, ADR-026)
# ---------------------------------------------------------------------------

#: ``?format=`` value that switches the reading route to the Markdown export
#: (plan R7.1). Consumed by the action itself, never by DRF's renderer override.
_VIEW_FORMAT_MARKDOWN = "markdown"



class DocumentViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """REST surface for the ``Document`` artifact (Plan F F2-T5, ADR-026).

    Delegates every write to :class:`application.document_service.DocumentService`
    (ADR-01) — no business logic in this class (REQ-L3-RA001-004).

    Contract highlights
    -------------------
    * **ETag / If-Match (KA-F-08, ADR-026 §9).** ``Document.version`` is the
      optimistic-lock counter; GET, POST and PATCH emit it as ``ETag`` and a
      PATCH accepts ``If-Match``. A stale strong tag answers ``412``, a stale
      body ``expected_version`` ``409``, a malformed header ``400``. Unlike the
      generic ``transitions/`` route, the Document transition POST also guards
      the **entity** version (the service's ``expected_version``), not the
      ``WorkflowItemState`` revision.
    * **Freeze (F-3).** A PATCH that touches a frozen field answers ``409``
      ``FIELD_FROZEN`` with one ``details`` entry per field.
    * **Gates (G-1…G-4).** A release refused by rule 9 answers ``409``
      ``DOCUMENT_GATE_FAILED`` with one ``details`` entry per violated gate.
    * **Soft delete (G1.5).** ``DELETE`` answers ``204`` and only flips the
      backing Artifact's lifecycle flag; GET still answers ``200`` with
      ``status="outdated"``, lists hide it unless ``?include_deleted=true``,
      and ``POST .../reactivate/`` restores it.
    * **Ordering (G2.1).** The list is ordered by ``-modified_at, id`` in the
      service, so pagination is deterministic.
    """

    serializer_class = DocumentSerializer
    preset_endpoint_key = ""
    workflow_item_type = "Document"

    def _svc(self) -> DocumentService:
        return DocumentService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_document(UUID(pk), ctx)
        return item.id, item.workspace_id

    # ---------- Read ----------

    @list_schema()
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/documents/?workspace_id=<id>[&include_deleted=true]

        Documents are ordered by ``-modified_at, id`` (G2.1), so OFFSET/LIMIT
        pagination is stable. Soft-deleted documents are hidden unless
        ``include_deleted`` is true (G1.5 V4).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"), lang
            )
            if error is not None:
                return error
            items = self._svc().list_documents(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: DocumentSerializer(
                [_document_to_dict(item) for item in page], many=True
            ).data,
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/ — retrieve a document.

        A soft-deleted document still answers ``200`` with ``status="outdated"``
        (G1.5 V3); an unknown id answers ``404``. The response carries
        ``ETag: "<version>"`` for a subsequent conditional PATCH.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_document(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return self.with_etag(
            Response(DocumentSerializer(_document_to_dict(item)).data), item
        )

    @extend_schema(
        parameters=[
            _ETAG_RESPONSE_HEADER,
            OpenApiParameter(
                "format",
                type=str,
                location=OpenApiParameter.QUERY,
                enum=["json", _VIEW_FORMAT_MARKDOWN],
                default="json",
                description=(
                    "Response representation. ``json`` (default) answers the "
                    "reading object; ``markdown`` answers the same chapters as a "
                    "``text/markdown`` document for export — same ETag, same "
                    "permission and not-found behaviour. The value is consumed "
                    "by this action, not by DRF's reserved format override."
                ),
            ),
        ],
        responses={
            (200, "application/json"): DocumentReadingSerializer,
            (200, "text/markdown"): OpenApiTypes.STR,
        },
        description=(
            "Read object of the document reading view (R1): document head, "
            "freeze-derived editable fields and the body split into numbered "
            "Markdown chapters. Read-only — writes stay on PATCH. "
            "Read permission is the RBAC matrix narrowed by any item-level rule. "
            "``?format=markdown`` (R7.1) exports the same chapters — numbers and "
            "order included, no edit markers — as ``text/markdown``; it is the "
            "same operation, so the route inventory is unchanged."
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="view",
        # ``?format=`` is this action's own parameter (markdown export), not a
        # renderer selector: pinning negotiation to JSON keeps DRF's
        # URL_FORMAT_OVERRIDE from 404ing the request before it reaches the
        # handler (same seam as ``requirement_bundle``).
        renderer_classes=[JSONRenderer],
        content_negotiation_class=_JsonOnlyContentNegotiation,
    )
    def view(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/view/ — chaptered reading object.

        Answers ``200`` with :class:`DocumentReadingSerializer` and
        ``ETag: "<version>"`` (the same convention as ``retrieve``, so the client
        can PATCH conditionally without a second GET). An unknown or foreign id
        answers ``404``; a built-in or item-level permission denial ``403``.
        Nothing here writes: the endpoint is the read half of the editable
        document view (plan R1), never a second write path.

        ``?format=markdown`` answers the same request as ``text/markdown``:
        :meth:`DocumentReadingService.read` → ``to_markdown()`` — the chapters
        exactly as the surface shows them (numbers, order, no edit markers),
        with the same ``ETag`` and the same ``403``/``404`` contract (plan R7.1).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            reading = DocumentReadingService().read(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            # Unreachable for HTTP traffic: ``BaseEntityViewSet.initial`` already
            # answers 400 for a malformed ``pk`` (#271). Kept as a guard for unit
            # tests that call the handler directly.
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        if request.query_params.get("format") == _VIEW_FORMAT_MARKDOWN:
            response: HttpResponse | Response = HttpResponse(
                reading.to_markdown(),
                content_type="text/markdown; charset=utf-8",
            )
        else:
            response = Response(DocumentReadingSerializer(reading.to_dict()).data)
        response["ETag"] = f'"{reading.version}"'
        return response

    # ---------- Create ----------

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/documents/ — create a document. Returns 201.

        ``title`` and ``kind`` are required; ``kind`` is one of
        ``Document.Kind``. The local identifier is allocated server-side as
        ``DOC-NNN`` and the initial workflow state is ``Entwurf``. The 201
        carries the new ``ETag`` so a client can PATCH conditionally without a
        second GET.
        """
        lang = detect_lang(request)
        ser = DocumentSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_document(
                workspace_id=UUID(str(data["workspace_id"])),
                ctx=ctx,
                title=data["title"],
                kind=data["kind"],
                description=data.get("description", ""),
                body=data.get("body", ""),
                doc_date=data.get("doc_date"),
                custom_fields=data.get("custom_fields"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(
                DocumentSerializer(_document_to_dict(item)).data,
                status=status.HTTP_201_CREATED,
            ),
            item,
        )

    # ---------- Update ----------

    @extend_schema(
        # KA-F-08: the 412 is conditioned on the declared request header, and
        # the response supplies the next tag.
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: DocumentSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/documents/{pk}/ — update a document. Returns 200.

        Ordering follows ADR-026 F-3 exactly: the ``If-Match`` syntax gate runs
        first (400 ``INVALID_IF_MATCH``), then the service applies the
        frozen-field gate (409 ``FIELD_FROZEN``), then the version compare
        (412 for a stale strong ``If-Match``, 409 for a stale body
        ``expected_version``). ``doc_date`` and ``custom_fields`` stay writable
        while the document is frozen (F-2).
        """
        lang = detect_lang(request)
        # GH-1396: a malformed If-Match is a request defect, refused before any
        # read or write.
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=DocumentSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = DocumentSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        # PATCH semantics: `doc_date` and `custom_fields` use a sentinel in the
        # service, so forwarding `None` for an omitted key would clear the
        # stored value. Only forward what the request actually carried.
        extra_kwargs: dict[str, Any] = {}
        if "doc_date" in data:
            extra_kwargs["doc_date"] = data["doc_date"]
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_document(
                document_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                kind=data.get("kind"),
                description=data.get("description"),
                body=data.get("body"),
                change_reason=data.get("change_reason"),
                expected_version=self.resolve_expected_version(
                    request,
                    data,
                    current=lambda: self._svc().get_document(UUID(pk), ctx),
                ),
                **extra_kwargs,
            )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            # KA-F-08: strong If-Match → 412; body expected_version → 409.
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(DocumentSerializer(_document_to_dict(item)).data), item
        )

    # ---------- Soft delete / restore (G1.5) ----------

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/documents/{pk}/ — soft-delete a document. Returns 204.

        The row is not removed: ``Artifact.lifecycle_status`` moves to
        ``"outdated"`` (G1.5 V1/V2), a subsequent GET still answers ``200`` with
        ``status="outdated"``, and lists hide it unless ``?include_deleted=true``.
        ``change_reason`` may be sent in the body or as ``?change_reason=``; a
        preset that mandates one answers ``400 VALIDATION_ERROR`` without it.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_document(
                UUID(pk), ctx, change_reason=parse_change_reason(request)
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/documents/{pk}/reactivate/ — undo the soft-delete.

        Restores the workflow state the document held throughout (soft delete
        is an orthogonal flag), so a previously released document comes back
        released and still frozen. Delegates to
        ``DocumentService.restore_document`` — the audited service path — rather
        than the generic facade so the restore is recorded on the audit trail.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().restore_document(UUID(pk), ctx)
            new_state = self._svc().current_status(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            {
                "id": str(pk),
                "previous_state": "outdated",
                "new_state": new_state,
                "document": DocumentSerializer(_document_to_dict(item)).data,
            }
        )

    # ---------- Projection and adoption (Phase G / #1374 S3) ----------

    @action(detail=True, methods=["get"], url_path="projection")
    def projection(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/projection/ — deterministic Markdown.

        Read-only: rendering the projection changes no row. The server never
        writes to a repository; a client fetches this payload and reports the
        written hash back via ``confirm-projection`` (or MCP
        ``document.projection_status`` with ``confirm``).
        """
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        lang = detect_lang(request)
        try:
            projected = DocumentProjectionService().project(
                UUID(pk), get_auth_context(request)
            )
        except Exception as exc:  # noqa: BLE001 — uniform service mapping
            return _service_error_response(exc, lang)
        return Response(projected.to_dict())

    @action(detail=False, methods=["post"], url_path="projection-status")
    def projection_status(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/documents/projection-status/ — compare repo hashes.

        Body: ``{"workspace_id": "<uuid>", "files": {"<path>": "<sha256>"},
        "confirm": {"document_id": "<uuid>", "sha256": "<sha256>"}}``.
        ``files`` carries hashes the client computed locally.

        Issue #1880: an empty (or non-object) body used to reach
        ``UUID("")`` and surface as **500** through the generic service
        mapping. Every required member is now validated up front and answers
        **400 VALIDATION_ERROR** with the offending field name, the same
        envelope the sibling actions use.
        """
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        lang = detect_lang(request)
        body = request.data if isinstance(request.data, Mapping) else {}
        details: list[dict[str, Any]] = []
        workspace_id, workspace_error = parse_uuid_param(
            body.get("workspace_id"), lang, name="workspace_id"
        )
        if workspace_error is not None:
            details.append(
                {
                    "field": "workspace_id",
                    "errors": [workspace_error.data["error"]["message"]],
                }
            )
        files = body.get("files") or {}
        if not isinstance(files, dict):
            details.append({"field": "files", "errors": ["Must be an object."]})
            files = {}
        confirm: dict[str, Any] | None = None
        raw_confirm = body.get("confirm")
        if raw_confirm:
            if not isinstance(raw_confirm, Mapping):
                details.append({"field": "confirm", "errors": ["Must be an object."]})
            else:
                confirm_id, confirm_error = parse_uuid_param(
                    raw_confirm.get("document_id"), lang, name="confirm.document_id"
                )
                if confirm_error is not None:
                    details.append(
                        {
                            "field": "confirm.document_id",
                            "errors": [confirm_error.data["error"]["message"]],
                        }
                    )
                confirm = {**raw_confirm, "document_id": confirm_id}
        if details:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=details),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            service = DocumentProjectionService()
            rows = service.status(workspace_id, files, ctx)
            if confirm:
                service.confirm(
                    confirm["document_id"],
                    str(confirm.get("sha256") or ""),
                    ctx,
                )
        except Exception as exc:  # noqa: BLE001 — uniform service mapping
            return _service_error_response(exc, lang)
        return Response(
            {
                "projections": [row.to_dict() for row in rows],
                "confirmed": bool(confirm),
            }
        )

    @action(detail=True, methods=["post"], url_path="confirm-projection")
    def confirm_projection(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/documents/{pk}/confirm-projection/ — record a write."""
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        lang = detect_lang(request)
        try:
            DocumentProjectionService().confirm(
                UUID(pk), str(request.data.get("sha256") or ""), get_auth_context(request)
            )
        except Exception as exc:  # noqa: BLE001 — uniform service mapping
            return _service_error_response(exc, lang)
        return Response({"id": str(pk), "confirmed": True})

    @action(detail=True, methods=["post"], url_path="adopt")
    def adopt(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/documents/{pk}/adopt/ — take over a repository file.

        A mismatching hash is **409**; the document keeps its
        ``repo_external`` ownership until the conflict is resolved.
        """
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        lang = detect_lang(request)
        try:
            document = DocumentProjectionService().adopt(
                UUID(pk),
                file_sha256=str(request.data.get("file_sha256") or ""),
                source_path=str(request.data.get("source_path") or ""),
                freeze=bool(request.data.get("freeze", False)),
                ctx=get_auth_context(request),
            )
        except Exception as exc:  # noqa: BLE001 — uniform service mapping
            return _service_error_response(exc, lang)
        return Response(
            {"document": DocumentSerializer(_document_to_dict(document)).data}
        )

    # ---------- Workflow transitions (F-1/F-5 and gates) ----------

    @action(detail=True, methods=["get", "post"], url_path="transitions")
    def transitions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET/POST /api/v1/documents/{pk}/transitions/.

        GET is inherited from ``WorkflowTransitionsMixin`` but re-expressed for
        this entity: ``version`` is the **Document** revision (the ETag source
        the POST expects), and the workflow-engine revision is preserved under
        ``workflow_version``.

        POST goes through ``DocumentService.transition_status`` instead of the
        generic facade so the F-1 freeze, the F-5 re-open version bump and the
        G-1…G-4 gates cannot be bypassed by this route. ``expected_version`` /
        ``If-Match`` therefore guard the Document version (412 for a stale
        strong tag, 409 for a stale body field) — a deliberate deviation from
        the generic ``transitions/`` contract, which guards the workflow
        revision.
        """
        if request.method.upper() == "GET":
            response = super().transitions(request, pk, **kwargs)
            if response.status_code == status.HTTP_200_OK and isinstance(
                response.data, dict
            ):
                try:
                    ctx = get_auth_context(request)
                    document = self._svc().get_document(UUID(pk), ctx)
                except Exception:  # noqa: BLE001 — keep the parent's answer
                    return response
                response.data["workflow_version"] = response.data.get("version")
                response.data["version"] = document.version
            return response
        return self._post_document_transition(request, pk)

    def _post_document_transition(self, request: Request, pk: str) -> Response:
        """Perform a gated document transition through ``DocumentService``."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._resolve_workflow_target(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        target_state = request.data.get("target_state")
        if not target_state:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_state is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            raw_version = self.resolve_expected_version(
                request,
                request.data,
                current=lambda: self._svc().get_document(UUID(pk), ctx),
            )
            expected_version = int(raw_version) if raw_version is not None else None
        except InvalidIfMatch as exc:
            return Response(
                build_error_response(
                    "INVALID_IF_MATCH",
                    lang,
                    details=[{"reason": exc.reason}] if exc.reason else None,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IfMatchMismatch:
            # Document transition guards the entity ETag, so a lost
            # precondition is the standard 412 (not the generic route's 409).
            return self.precondition_failed(request)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            previous_state = self._svc().current_status(UUID(pk), ctx)
            item = self._svc().transition_status(
                UUID(pk),
                str(target_state),
                ctx,
                change_reason=request.data.get("change_reason") or "",
                credential=request.data.get("credential") or "",
                expected_version=expected_version,
            )
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        return Response(
            {
                "id": str(item.id),
                "previous_state": previous_state,
                "new_state": self._svc().current_status(item.id, ctx),
                # The value the client echoes as ``expected_version``/``If-Match``
                # on its next call — the Document revision, not the workflow one.
                "version": item.version,
                "document": DocumentSerializer(_document_to_dict(item)).data,
            }
        )

    # ---------- Versions / diff ----------

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/versions/ — recorded content revisions.

        Every document starts with revision 1 and gains one on every content
        change and on release/re-open (F-5). Reads the shared
        ``ArtifactVersion`` store through the generic artifact-id API.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_document(UUID(pk), ctx)
            result = ArtifactDiffService().list_versions(item.artifact_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/diff/?from_version=0&to_version=2

        Field-level diff over ``title``/``description``/``body``/``kind``/
        ``doc_date`` (the fields ``snapshot_fields`` records for ``Document``).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_document(UUID(pk), ctx)
            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get("to_version", str(item.version))
            )
            result = ArtifactDiffService().diff(
                artifact_id=item.artifact_id,
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



# ---------------------------------------------------------------------------
# WorkItemViewSet — Plan F F3-T5 (PR-F24b, #1374)
# ---------------------------------------------------------------------------


_WORK_ITEM_RESUME_RESPONSE = inline_serializer(
    name="WorkItemResumeResponse",
    fields={
        "checkpoint": serializers.JSONField(allow_null=True),
        "open_items": serializers.ListField(child=serializers.JSONField()),
    },
)


_WORK_ITEM_TRANSITION_REQUEST = inline_serializer(
    name="WorkItemTransitionRequest",
    fields={
        "target_state": serializers.CharField(),
        "blocked_reason": serializers.CharField(required=False, allow_blank=True),
        "change_reason": serializers.CharField(required=False, allow_blank=True),
        "credential": serializers.CharField(required=False, allow_blank=True),
        "expected_version": serializers.IntegerField(required=False, min_value=1),
    },
)


_WORK_ITEM_TRANSITION_RESPONSE = inline_serializer(
    name="WorkItemTransitionResponse",
    fields={
        "id": serializers.UUIDField(),
        "previous_state": serializers.CharField(),
        "new_state": serializers.CharField(),
        "version": serializers.IntegerField(),
        "work_item": WorkItemSerializer(),
    },
)



class WorkItemViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """REST surface for the ``WorkItem`` artifact (Plan F F3-T5, #1374).

    Delegates every write to :class:`application.work_item_service
    .WorkItemService` (ADR-01). A work item is the explicit, queryable agent
    state store (progress, blocked reason, resume hint, heartbeat), always owned
    by one document.

    Contract highlights
    -------------------
    * **Document is mandatory.** ``POST`` without ``document_id`` answers
      ``400 VALIDATION_ERROR``; a document from another workspace is refused by
      the service instead of being silently re-homed.
    * **ETag / If-Match (KA-F-08).** ``WorkItem.version`` is the
      optimistic-lock counter; GET, POST and PATCH emit it as ``ETag`` and a
      PATCH accepts ``If-Match``. A stale strong tag answers ``412``, a stale
      body ``expected_version`` ``409``, a malformed header ``400
      INVALID_IF_MATCH``. The ``transition/`` POST guards the same entity
      version (412 for a stale strong tag, 409 for the body field).
    * **Resume.** ``GET .../resume/?workspace_id=&document_id=&actor=`` returns
      the newest checkpoint and every open item, sorted ``(ordinal, id)``.
    * **Soft delete (G1.5).** ``DELETE`` answers ``204`` and only flips the
      backing Artifact's lifecycle flag; GET still answers ``200`` with
      ``status="outdated"``, lists hide it unless ``?include_deleted=true``,
      and ``POST .../reactivate/`` restores it.
    * **Ordering (G2.1).** The list is ordered by ``(ordinal, id)`` in the
      service, so pagination is deterministic.
    """

    serializer_class = WorkItemSerializer
    preset_endpoint_key = ""
    workflow_item_type = "WorkItem"

    def _svc(self) -> WorkItemService:
        return WorkItemService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_work_item(UUID(pk), ctx)
        return item.id, item.workspace_id

    # ---------- Read ----------

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose work items are listed.",
            ),
            OpenApiParameter(
                "document_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=False,
                description="Only items of this document.",
            ),
            OpenApiParameter(
                "include_deleted",
                OpenApiTypes.BOOL,
                OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Include soft-deleted (outdated) items. Defaults to false; "
                    "the detail GET still answers 200 with status='outdated'."
                ),
            ),
        ]
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/work-items/?workspace_id=<id>[&document_id=<id>]

        Items are ordered by ``(ordinal, id)`` (G2.1), so OFFSET/LIMIT
        pagination is stable. Soft-deleted items are hidden unless
        ``include_deleted`` is true (G1.5 V4).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"), lang
            )
            if error is not None:
                return error
            document_id = None
            raw_document_id = request.query_params.get("document_id")
            if raw_document_id not in (None, ""):
                document_id, error = parse_uuid_param(
                    raw_document_id, lang, name="document_id"
                )
                if error is not None:
                    return error
            items = self._svc().list_work_items(
                workspace_id=workspace_id,
                ctx=ctx,
                document_id=document_id,
                include_deleted=parse_include_deleted(request.query_params),
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)),
                lang,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: WorkItemSerializer(
                [_work_item_to_dict(item) for item in page], many=True
            ).data,
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/work-items/{pk}/ — retrieve a work item.

        A soft-deleted item still answers ``200`` with ``status="outdated"``
        (G1.5 V3); an unknown id answers ``404``. The response carries
        ``ETag: "<version>"`` for a subsequent conditional PATCH.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_work_item(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return self.with_etag(
            Response(WorkItemSerializer(_work_item_to_dict(item)).data), item
        )

    # ---------- Create ----------

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/work-items/ — create a work item. Returns 201.

        ``workspace_id``, ``document_id``, ``title`` and ``kind`` are required.
        The local identifier is allocated server-side as ``WI-NNN`` and the
        initial workflow state comes from the workspace's tier-matched WorkItem
        definition (``todo``). The 201 carries the new ``ETag``.
        """
        lang = detect_lang(request)
        ser = WorkItemSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_work_item(
                workspace_id=UUID(str(data["workspace_id"])),
                document_id=UUID(str(data["document_id"])),
                ctx=ctx,
                kind=data["kind"],
                title=data["title"],
                body=data.get("body", ""),
                ordinal=data.get("ordinal", 0),
                progress=data.get("progress"),
                blocked_reason=data.get("blocked_reason", ""),
                next_action=data.get("next_action", ""),
                evidence_ref=data.get("evidence_ref", ""),
                due_date=data.get("due_date"),
                exit_criteria=data.get("exit_criteria", ""),
                custom_fields=data.get("custom_fields"),
                actor=data.get("actor") or "",
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(
                WorkItemSerializer(_work_item_to_dict(item)).data,
                status=status.HTTP_201_CREATED,
            ),
            item,
        )

    # ---------- Update ----------

    @extend_schema(
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: WorkItemSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/work-items/{pk}/ — update a work item. Returns 200.

        ``If-Match`` is evaluated first (400 ``INVALID_IF_MATCH`` for a
        malformed header), then the service compares the version (412 for a
        stale strong ``If-Match``, 409 for a stale body ``expected_version``).
        ``document_id`` is immutable: moving an item to another document is
        refused instead of silently ignored.
        """
        lang = detect_lang(request)
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=WorkItemSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = WorkItemSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data

        def _current() -> Any:
            return self._svc().get_work_item(UUID(pk), get_auth_context(request))

        if "document_id" in data:
            try:
                current = _current()
            except (NotFoundError, PermissionDeniedError) as exc:
                return _service_error_response(exc, lang)
            except ValueError:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )
            if str(data["document_id"]) != str(current.document_id):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[
                            {
                                "field": "document_id",
                                "errors": [
                                    "document_id is immutable; a work item "
                                    "cannot be moved to another document."
                                ],
                            }
                        ],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ``progress`` and ``due_date`` use a sentinel in the service, so an
        # explicit ``null`` must be forwarded while an omitted key must not.
        extra_kwargs: dict[str, Any] = {}
        if "progress" in data:
            extra_kwargs["progress"] = data["progress"]
        if "due_date" in data:
            extra_kwargs["due_date"] = data["due_date"]
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]

        try:
            ctx = get_auth_context(request)
            item = self._svc().update_work_item(
                item_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                kind=data.get("kind"),
                body=data.get("body"),
                ordinal=data.get("ordinal"),
                blocked_reason=data.get("blocked_reason"),
                next_action=data.get("next_action"),
                evidence_ref=data.get("evidence_ref"),
                exit_criteria=data.get("exit_criteria"),
                change_reason=data.get("change_reason"),
                expected_version=self.resolve_expected_version(
                    request, data, current=_current
                ),
                actor=data.get("actor") or "",
                **extra_kwargs,
            )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(WorkItemSerializer(_work_item_to_dict(item)).data), item
        )

    # ---------- Soft delete / restore (G1.5) ----------

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/work-items/{pk}/ — soft-delete a work item. Returns 204.

        The row is not removed: ``Artifact.lifecycle_status`` moves to
        ``"outdated"`` (G1.5 V1/V2), a subsequent GET still answers ``200`` with
        ``status="outdated"``, and lists hide it unless ``?include_deleted=true``.
        ``change_reason`` may be sent in the body or as ``?change_reason=``; a
        preset that mandates one answers ``400 VALIDATION_ERROR`` without it.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_work_item(
                UUID(pk), ctx, change_reason=parse_change_reason(request)
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/work-items/{pk}/reactivate/ — undo the soft-delete.

        Restores the workflow state the item held throughout (soft delete is an
        orthogonal flag), so a previously finished item comes back finished.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().restore_work_item(UUID(pk), ctx)
            new_state = self._svc().current_status(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            {
                "id": str(pk),
                "previous_state": "outdated",
                "new_state": new_state,
                "work_item": WorkItemSerializer(_work_item_to_dict(item)).data,
            }
        )

    # ---------- Workflow transition / versions / diff / resume ----------

    @action(detail=True, methods=["get", "post"], url_path="transitions")
    def transitions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET/POST /api/v1/work-items/{pk}/transitions/.

        Both verbs are routed through this class on purpose. The inherited
        generic POST calls ``WorkflowFacade`` directly, which would bypass the
        work-item rules the service owns — rule 10 (a ``blocked_reason`` before
        entering ``blocked``) and the extended preset's human sign-off
        bookkeeping (``approved_by``/``approved_at``). Delegating keeps
        ``POST .../transition/`` and ``POST .../transitions/`` on one code path
        (spec §4/§9).

        GET answers ``{current_state, version, states, allowed_transitions[]}``
        like every other entity, but reports the **entity** revision as
        ``version`` (the ETag source) and keeps the workflow-engine revision
        under ``workflow_version`` — same deviation as ``DocumentViewSet``.
        """
        if request.method.upper() == "GET":
            response = super().transitions(request, pk, **kwargs)
            if response.status_code == status.HTTP_200_OK and isinstance(
                response.data, dict
            ):
                try:
                    ctx = get_auth_context(request)
                    item = self._svc().get_work_item(UUID(pk), ctx)
                except Exception:  # noqa: BLE001 — keep the parent's answer
                    return response
                response.data["workflow_version"] = response.data.get("version")
                response.data["version"] = item.version
            return response
        return self._post_work_item_transition(request, pk)

    @extend_schema(
        request=_WORK_ITEM_TRANSITION_REQUEST,
        responses={200: _WORK_ITEM_TRANSITION_RESPONSE},
    )
    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/work-items/{pk}/transition/ — move the item.

        Body ``{target_state, blocked_reason?, change_reason?, credential?,
        expected_version?}``. The service enforces the tiered graph, rule 10
        (``blocked`` needs a reason) and the human sign-off in the extended
        preset; this route only translates. ``If-Match``/``expected_version``
        guard the item's ``version`` (412 for a stale strong tag, 409 for the
        body field), not the workflow revision.
        """
        return self._post_work_item_transition(request, pk)

    def _post_work_item_transition(self, request: Request, pk: str) -> Response:
        """Perform a gated work-item transition through ``WorkItemService``."""
        lang = detect_lang(request)
        target_state = request.data.get("target_state")
        if not target_state:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_state is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            self._svc().get_work_item(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            expected_version = self.resolve_expected_version(
                request,
                request.data,
                current=lambda: self._svc().get_work_item(UUID(pk), ctx),
            )
        except InvalidIfMatch as exc:
            return Response(
                build_error_response(
                    "INVALID_IF_MATCH",
                    lang,
                    details=[{"reason": exc.reason}] if exc.reason else None,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IfMatchMismatch:
            return self.precondition_failed(request)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)

        try:
            previous_state = self._svc().current_status(UUID(pk), ctx)
            item = self._svc().transition(
                UUID(pk),
                str(target_state),
                ctx,
                blocked_reason=request.data.get("blocked_reason"),
                change_reason=request.data.get("change_reason") or "",
                credential=request.data.get("credential") or "",
                expected_version=expected_version,
                actor=request.data.get("actor") or "",
            )
            new_state = self._svc().current_status(item.id, ctx)
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        return Response(
            {
                "id": str(item.id),
                "previous_state": previous_state,
                "new_state": new_state,
                "version": item.version,
                "work_item": WorkItemSerializer(_work_item_to_dict(item)).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/work-items/{pk}/versions/ — recorded content revisions.

        Every item starts at revision 1 and gains one on every write (the same
        gate that bumps the optimistic-lock counter).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_work_item(UUID(pk), ctx)
            result = ArtifactDiffService().list_versions(item.artifact_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/work-items/{pk}/diff/?from_version=0&to_version=2

        Field-level diff over the item's content fields (``kind``, ``ordinal``,
        ``title``, ``body``, ``progress``, ``blocked_reason``, ``next_action``,
        ``evidence_ref``, ``due_date``, ``exit_criteria``). The workflow state
        is not a column and therefore not part of the diff.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_work_item(UUID(pk), ctx)
            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get("to_version", str(item.version))
            )
            result = ArtifactDiffService().diff(
                artifact_id=item.artifact_id,
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Workspace of the document.",
            ),
            OpenApiParameter(
                "document_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Document whose work state is resumed.",
            ),
            OpenApiParameter(
                "actor",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description="Caller label (informational; not persisted).",
            ),
        ],
        responses={200: _WORK_ITEM_RESUME_RESPONSE},
    )
    @action(detail=False, methods=["get"], url_path="resume")
    def resume(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/work-items/resume/?workspace_id=&document_id=&actor=

        Returns ``{"checkpoint": {...}|null, "open_items": [...]}`` sorted by
        ``(ordinal, id)`` — the single read an agent without repo access needs
        to continue (spec §6). Read-only: it never creates a heartbeat.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"), lang
            )
            if error is not None:
                return error
            document_id, error = parse_uuid_param(
                request.query_params.get("document_id"), lang, name="document_id"
            )
            if error is not None:
                return error
            result = self._svc().resume(
                workspace_id,
                document_id,
                ctx,
                actor=request.query_params.get("actor", "") or "",
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)
