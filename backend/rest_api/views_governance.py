"""
COMP-RA-001 HttpEndpointController — views_governance — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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
    _artifact_custom_fields,
    _parse_derivation_mode_policy,
    _service_error_response,
    _special_route_if_match_error,
    list_schema,
    soft_delete_schema,
)

from .views_trace_baseline import (
    _caller_may_read_workspace,
)




# ---------------------------------------------------------------------------
# WorkflowDefinitionViewSet
# ---------------------------------------------------------------------------


class WorkflowDefinitionViewSet(BaseEntityViewSet):
    """ViewSet for WorkflowDefinition CRUD operations (REQ-L2-RA-001)."""

    serializer_class = WorkflowDefinitionSerializer
    preset_endpoint_key = ""

    def _svc(self) -> WorkflowFacade:
        return WorkflowFacade()

    def list(self, request: Request, **kwargs: Any) -> Response:
        # WorkflowFacade does not expose list — return empty list
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    @action(detail=False, methods=["get"], url_path="definition")
    def definition(self, request: Request, **kwargs: Any) -> Response:
        """GET ``definition/`` — full workflow graph for an entity type (REQ-176).

        Query params: ``workspace_id`` (UUID) and ``item_type`` (e.g.
        "Requirement"). Returns the COMPLETE state machine — every state and
        every transition with its role / change_reason / signature metadata — so
        the Workflow Editor can render the whole graph read-only. When no
        workflow is configured for the workspace/type, returns an empty graph
        with ``initialized: false`` rather than a 404.
        """
        lang = detect_lang(request)
        workspace_id = request.query_params.get("workspace_id")
        item_type = request.query_params.get("item_type")
        if not workspace_id or not item_type:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="workspace_id and item_type are required",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            UUID(str(workspace_id))
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            dto = self._svc().get_definition(
                ctx, item_type=item_type, workspace_id=str(workspace_id)
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        if dto is None:
            return Response(
                {
                    "item_type": item_type,
                    "preset": None,
                    "is_custom": False,
                    # REQ-180 additive on-default/customized signal.
                    "is_customized": False,
                    "on_default": True,
                    "source_global_id": None,
                    "initial_state": None,
                    "initialized": False,
                    "states": [],
                    "transitions": [],
                }
            )
        return Response(self._serialize_definition(dto))

    # -- Edit-mode mutations (REQ-177 — Workflow Editor Phase 2) --------------
    #
    # State identity is the state NAME; transition identity is the
    # ``<from>__<to>`` pair (matching the frontend's derived ids). Admin-gated
    # and workspace-scoped exactly like the read endpoint. All mutations return
    # the full, re-serialised definition graph so the client can refresh in one
    # round-trip. Preset/reference/orphan errors map to precise HTTP statuses.

    @staticmethod
    def _serialize_definition(dto: Any) -> dict[str, Any]:
        is_customized = bool(getattr(dto, "is_customized", False))
        return {
            "item_type": dto.item_type,
            "preset": dto.preset,
            "is_custom": dto.is_custom,
            # REQ-180 additive fields (see WorkflowGraphWorkspace in the contract).
            # ``is_customized`` (new) is UNRELATED to the legacy ``is_custom``.
            "is_customized": is_customized,
            "on_default": not is_customized,
            "source_global_id": getattr(dto, "source_global_id", None),
            "initial_state": dto.initial_state,
            "initialized": True,
            "states": list(dto.states),
            "transitions": [
                {
                    "from_state": tr.from_state,
                    "to_state": tr.to_state,
                    "allowed_roles": list(tr.allowed_roles),
                    "requires_change_reason": tr.requires_change_reason,
                    "signature_gate": tr.signature_gate,
                }
                for tr in dto.transitions
            ],
        }

    def _edit_precheck(
        self, request: Request
    ) -> tuple[Any, str, str, str] | Response:
        """Return (ctx, lang, workspace_id, item_type) or an error Response.

        Enforces the admin gate and validates the required scope parameters,
        accepting them from the JSON body (POST/PATCH) or the query string
        (DELETE has no body).
        """
        from auth_tenancy.models import ROLE_ADMIN

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return Response(
                build_error_response(
                    "PERMISSION_DENIED",
                    lang,
                    message="Editing workflow definitions requires the admin role.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        workspace_id = request.data.get("workspace_id") or request.query_params.get(
            "workspace_id"
        )
        item_type = request.data.get("item_type") or request.query_params.get(
            "item_type"
        )
        if not workspace_id or not item_type:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="workspace_id and item_type are required",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            UUID(str(workspace_id))
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return ctx, lang, str(workspace_id), str(item_type)

    @staticmethod
    def _edit_error_response(exc: Exception, lang: str) -> Response:
        """Map an edit-mode exception to a precise HTTP status."""
        from workflow.services import (
            NoGlobalSourceError,
            OrphanedStateError,
            StateReferencedError,
            WorkflowDefinitionError,
            WorkflowNotConfigurableError,
        )

        if isinstance(exc, NoGlobalSourceError):
            # REQ-180: distinct machine-readable code so the client can offer
            # "initialize from current global" instead of a silent no-op.
            return Response(
                build_error_response("NO_GLOBAL_SOURCE", lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        if isinstance(exc, (OrphanedStateError, StateReferencedError)):
            return Response(
                build_error_response("CONFLICT", lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        if isinstance(exc, WorkflowNotConfigurableError):
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        if isinstance(exc, WorkflowDefinitionError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _service_error_response(exc, lang)

    @action(detail=False, methods=["post"], url_path="definition/states")
    def create_state(self, request: Request, **kwargs: Any) -> Response:
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="name is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            dto = self._svc().add_state(
                ctx, item_type=item_type, workspace_id=workspace_id, name=name
            )
        except Exception as exc:  # noqa: BLE001 — mapped to a precise status
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto), status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["patch", "delete"],
        url_path=r"definition/states/(?P<state_id>[^/]+)",
    )
    def modify_state(self, request: Request, state_id: str, **kwargs: Any) -> Response:
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        from urllib.parse import unquote

        name = unquote(state_id)
        try:
            if request.method == "DELETE":
                dto = self._svc().delete_state(
                    ctx, item_type=item_type, workspace_id=workspace_id, name=name
                )
            else:
                new_name = (request.data.get("name") or "").strip()
                if not new_name:
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR", lang, message="name is required"
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                dto = self._svc().update_state(
                    ctx,
                    item_type=item_type,
                    workspace_id=workspace_id,
                    old_name=name,
                    new_name=new_name,
                )
        except Exception as exc:  # noqa: BLE001
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto))

    @action(detail=False, methods=["post"], url_path="definition/transitions")
    def create_transition(self, request: Request, **kwargs: Any) -> Response:
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        from_state = request.data.get("from_state")
        to_state = request.data.get("to_state")
        if not from_state or not to_state:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="from_state and to_state are required",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            dto = self._svc().add_transition(
                ctx,
                item_type=item_type,
                workspace_id=workspace_id,
                from_state=from_state,
                to_state=to_state,
                allowed_roles=request.data.get("allowed_roles"),
                requires_change_reason=bool(
                    request.data.get("requires_change_reason", False)
                ),
                signature_gate=bool(request.data.get("signature_gate", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto), status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["patch", "delete"],
        url_path=r"definition/transitions/(?P<transition_id>[^/]+)",
    )
    def modify_transition(
        self, request: Request, transition_id: str, **kwargs: Any
    ) -> Response:
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        from urllib.parse import unquote

        decoded = unquote(transition_id)
        parts = decoded.split("__")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="transition id must be '<from>__<to>'",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        from_state, to_state = parts
        try:
            if request.method == "DELETE":
                dto = self._svc().delete_transition(
                    ctx,
                    item_type=item_type,
                    workspace_id=workspace_id,
                    from_state=from_state,
                    to_state=to_state,
                )
            else:
                dto = self._svc().update_transition(
                    ctx,
                    item_type=item_type,
                    workspace_id=workspace_id,
                    from_state=from_state,
                    to_state=to_state,
                    allowed_roles=request.data.get("allowed_roles"),
                    requires_change_reason=request.data.get("requires_change_reason"),
                    signature_gate=request.data.get("signature_gate"),
                )
        except Exception as exc:  # noqa: BLE001
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto))

    @action(detail=False, methods=["post"], url_path="definition/initialize")
    def initialize_definition(self, request: Request, **kwargs: Any) -> Response:
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        try:
            dto = self._svc().initialize_definition(
                ctx, item_type=item_type, workspace_id=workspace_id
            )
        except Exception as exc:  # noqa: BLE001
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="definition/reset")
    def reset_definition(self, request: Request, **kwargs: Any) -> Response:
        """POST ``definition/reset/`` — reset to the global default (REQ-180).

        Admin-gated identically to the other mutation actions. Overwrites
        ``workflow_json`` with ``source_global.workflow_json`` and clears
        ``is_customized``. 409 NO_GLOBAL_SOURCE when nothing is linked.
        """
        pre = self._edit_precheck(request)
        if isinstance(pre, Response):
            return pre
        ctx, lang, workspace_id, item_type = pre
        try:
            dto = self._svc().reset_definition(
                ctx, item_type=item_type, workspace_id=workspace_id
            )
        except Exception as exc:  # noqa: BLE001 — mapped to a precise status
            return self._edit_error_response(exc, lang)
        return Response(self._serialize_definition(dto))

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        return Response(build_error_response("NOT_FOUND", detect_lang(request)), status=status.HTTP_404_NOT_FOUND)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = WorkflowDefinitionSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            self._svc().initialize_workflow_states(
                item_ids=[data["artifact_id"]],
                item_type="Artifact",
                workspace_id=str(data["workspace_id"]),
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response({"message": "Workflow initialized"}, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """Workflow transition via PATCH."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            target_state = request.data.get("target_state")
            change_reason = request.data.get("change_reason", "")
            if not target_state:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="target_state is required"), status=status.HTTP_400_BAD_REQUEST)
            artifact = ArtifactService().get_artifact(UUID(pk), ctx)
            self._svc().transition(
                item_id=artifact.id,
                target_state=target_state,
                change_reason=change_reason,
                ctx=ctx,
                item_type="Artifact",
                workspace_id=artifact.workspace_id,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response({"id": pk, "target_state": target_state})

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        return Response(build_error_response("PERMISSION_DENIED", detect_lang(request), message="Workflow definitions cannot be deleted."), status=status.HTTP_403_FORBIDDEN)



# ---------------------------------------------------------------------------
# DTO helper functions — ORM → dict for serializers
# Pure translation, no business logic (REQ-L3-RA001-004)
# ---------------------------------------------------------------------------


def _result_summary(test_run: Any) -> dict:
    """Compute result summary from a TestRun's results."""
    results = list(getattr(test_run, "_prefetched_results", test_run.results.all() if hasattr(test_run, "results") else []))
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    blocked = sum(1 for r in results if r.status == "blocked")
    not_run = sum(1 for r in results if r.status == "not_run")
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "not_run": not_run,
    }



def _test_run_to_dict(tr: Any) -> dict[str, Any]:
    """Convert TestRun ORM object to serializer-compatible dict."""
    return {
        "id": str(tr.id),
        "workspace_id": str(tr.workspace_id),
        "name": tr.name,
        "uid": getattr(tr, "uid", None),
        "status": tr.status,
        "ci_job_id": getattr(tr, "ci_job_id", ""),
        "started_at": tr.started_at,
        "finished_at": tr.finished_at,
        "result_summary": _result_summary(tr),
        "version": tr.version,
        "created_at": tr.created_at,
        "updated_at": tr.modified_at,
    }



def _test_run_result_to_dict(r: Any) -> dict[str, Any]:
    """Convert TestRunResult ORM object to serializer-compatible dict.

    REQ-L1-035 (A.6): The ``testcase`` (nested id+title), ``result``,
    ``notes`` and ``executed_by`` keys carry the spec'd GET-endpoint shape
    so the frontend UI-chain can render them directly. The legacy flat
    fields (``test_case_id``, ``test_case_title``, ``status``, ``message``)
    are kept on the wire for backwards compatibility with the existing
    addResult / addResultsBulk POST callers.
    """
    # ``test_case`` FK can be null (ON DELETE SET NULL when a TestCase is
    # removed); fall back to the historical ``test_case_title`` string so
    # the UI still has a human-readable label.
    test_case = getattr(r, "test_case", None)
    testcase_payload: dict[str, Any] = {
        "id": str(test_case.id) if test_case and test_case.id else None,
        "title": (
            test_case.title
            if test_case and getattr(test_case, "title", "")
            else getattr(r, "test_case_title", "")
        ),
    }
    # ``created_by`` is the AuditableModel FK; it doubles as the
    # ``executed_by`` proxy because the result has no dedicated executor
    # column. Returns the username string (frontend renders it as a label).
    created_by = getattr(r, "created_by", None)
    executed_by = (
        getattr(created_by, "username", None)
        if created_by is not None
        else None
    )
    return {
        "id": str(r.id),
        "test_run_id": str(r.test_run_id),
        # Legacy flat fields (kept for backwards compat with existing callers)
        "test_case_id": str(r.test_case_id) if r.test_case_id else None,
        "test_case_title": getattr(r, "test_case_title", ""),
        "status": r.status,
        "message": getattr(r, "message", ""),
        # Spec'd nested fields (A.6)
        "testcase": testcase_payload,
        "result": r.status,
        "notes": getattr(r, "message", ""),
        # Shared timestamps / metadata
        "duration_ms": getattr(r, "duration_ms", None),
        "executed_at": r.executed_at,
        "executed_by": executed_by,
        "version": r.version,
        "created_at": r.created_at,
    }



_TRUE_TOKENS = frozenset({"true", "1", "yes", "on"})

_FALSE_TOKENS = frozenset({"false", "0", "no", "off"})



def _coerce_bool(value: Any) -> bool:
    """Coerce a JSON/form value into a bool, mirroring DRF BooleanField.

    Raises ``ValueError`` for values that are not recognizable booleans so the
    caller can return a 400 instead of silently treating them as truthy.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int,)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    raise ValueError(f"Cannot coerce {value!r} to bool")



def _workspace_to_dict(ws: Any) -> dict[str, Any]:
    """Convert Workspace ORM object to serializer-compatible dict.

    ``terminology_profile`` is resolved from the optional
    ``WorkspacePresetConfig`` companion (defaults to ``"se_mode"`` when no
    preset config has been provisioned yet).
    """
    terminology_profile = "se_mode"
    preset_config = getattr(ws, "preset_config", None)
    if preset_config is not None:
        terminology_profile = getattr(
            preset_config, "terminology_profile", terminology_profile
        )
    return {
        "id": str(ws.id),
        "name": ws.name,
        "preset": ws.preset or {},
        "ai_prompts": getattr(ws, "ai_prompts", {}),
        # #989: an empty column falls back to the deployment default, not a
        # hardcoded literal.
        "decomposition_link_type": (
            getattr(ws, "decomposition_link_type", "") or default_decomposition_link_type()
        ),
        "default_link_type": (
            getattr(ws, "default_link_type", "") or default_trace_link_type()
        ),
        "goals_enabled": getattr(ws, "goals_enabled", False),
        "goals_ai_enabled": getattr(ws, "goals_ai_enabled", False),
        # #1266: version-binding mode for glossary reference tokens.
        "glossary_reference_mode": getattr(ws, "glossary_reference_mode", "pinned")
        or "pinned",
        "terminology_profile": terminology_profile,
        "language": (ws.preset or {}).get("language", "de"),  # REQ-013: language stored in preset blob
        # S7 (spec §7.6): the AI language is a dedicated column, not part of
        # the UI preset blob -- the UI language and the AI language are
        # deliberately independent.
        "ai_language": getattr(ws, "ai_language", "") or "auto",
        "theme": (ws.preset or {}).get("theme", "dark"),  # #568: theme stored in preset blob, mirrors language
        "is_active": getattr(ws, "is_active", True),
        "closed_at": ws.closed_at.isoformat() if getattr(ws, "closed_at", None) else None,
        "closed_by": str(ws.closed_by_id) if getattr(ws, "closed_by_id", None) else None,
        "version": ws.version,
        "created_at": ws.created_at,
        "updated_at": ws.modified_at,
    }



def _adr_to_dict(adr: Any) -> dict[str, Any]:
    """Convert Adr ORM object to serializer-compatible dict."""
    return {
        "id": str(adr.id),
        "workspace_id": str(adr.workspace_id),
        # #1763: the Inspector's comment panel is Artifact-addressed, so every
        # artifact-backed entity response carries the backing Artifact id.
        "artifact_id": (
            str(adr.artifact_id) if getattr(adr, "artifact_id", None) else None
        ),
        "title": adr.title,
        "description": getattr(adr, "description", ""),
        "context": getattr(adr, "context", ""),
        "decision": getattr(adr, "decision", ""),
        "consequences": getattr(adr, "consequences", ""),
        "uid": getattr(adr, "uid", None),
        "status": getattr(adr, "status", "Draft"),
        "custom_fields": _artifact_custom_fields(adr),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(adr),
        "version": adr.version,
        "created_at": adr.created_at,
        "updated_at": adr.updated_at,
    }



def _risk_to_dict(risk: Any) -> dict[str, Any]:
    """Convert Risk ORM object to serializer-compatible dict."""
    return {
        "id": str(risk.id),
        "workspace_id": str(risk.workspace_id),
        # #1763: see _adr_to_dict — comment-panel parity for the ARTIFACT id.
        "artifact_id": (
            str(risk.artifact_id) if getattr(risk, "artifact_id", None) else None
        ),
        "title": risk.title,
        "description": getattr(risk, "description", ""),
        "probability": getattr(risk, "probability", "low"),
        "impact": getattr(risk, "impact", "low"),
        "risk_score": getattr(risk, "risk_score", 1),
        # REQ-L1-029 (FMEA): Risk Priority Number, computed property on the model.
        "rpn": getattr(risk, "rpn", risk.risk_score),
        "severity": getattr(risk, "severity", "low"),
        "category": getattr(risk, "category", "technical"),
        # Attribut v3 WS7 (#940): legacy free-text owner column, renamed to
        # owner_name so the Artifact-level owner Actor FK (below) is no longer
        # shadowed. Kept readable for clients that still edit the free text.
        "owner_name": getattr(risk, "owner_name", ""),
        "owner_user_id": str(risk.owner_user_id) if getattr(risk, "owner_user_id", None) else None,
        "owner_user_display": getattr(risk.owner_user, "email", None) if getattr(risk, "owner_user_id", None) else None,
        "detection": getattr(risk, "detection", 5),
        "mitigation_strategy": getattr(risk, "mitigation_strategy", ""),
        "uid": getattr(risk, "uid", None),
        "status": getattr(risk, "status", "Identified"),
        "custom_fields": _artifact_custom_fields(risk),
        # Attribut v3 WS2/WS7 (#936/#940): Artifact-level system fields, actor
        # wire form. Risk is wired now that the legacy column no longer shadows.
        **artifact_system_fields(risk),
        "version": risk.version,
        "created_at": risk.created_at,
        "updated_at": risk.updated_at,
    }



def _milestone_to_dict(milestone: Any) -> dict[str, Any]:
    """Convert a ``Milestone`` ORM row to the serializer-compatible dict.

    The wire key for the house ``modified_at`` column is ``updated_at``, but
    ``Milestone`` keeps its own ``updated_at`` column next to it (Plan B B6-T1
    published both). ``target_date`` stays a ``date`` so DRF renders it as
    ISO-8601; ``audit_snapshot`` is passed through unchanged.
    """
    return {
        "id": str(milestone.id),
        "workspace_id": str(milestone.workspace_id),
        "name": milestone.name,
        "review_type": milestone.review_type,
        "target_date": milestone.target_date,
        "status": milestone.status,
        "baseline_id": (
            str(milestone.baseline_id)
            if getattr(milestone, "baseline_id", None)
            else None
        ),
        "audit_snapshot": getattr(milestone, "audit_snapshot", None),
        "version": milestone.version,
        "created_at": milestone.created_at,
        "updated_at": getattr(milestone, "updated_at", None)
        or getattr(milestone, "modified_at", None),
    }



def _goal_to_dict(goal: Any) -> dict[str, Any]:
    """Convert Goal ORM object to serializer-compatible dict (Task 6).

    Task 12: the `status` column is dropped. ``getattr(goal, "status", ...)``
    still picks up an in-memory value a service-layer caller already
    resolved (e.g. GoalService.transition_status's post-transition
    correction) -- only the *default* used to be the bug: a raw ORM instance
    (GoalService.get()/list_current(), never corrected) has no ``.status``
    attribute at all, so ``getattr`` silently returned the hardcoded literal
    "Entwurf" regardless of the item's real state. The fallback now resolves
    the engine seam instead (batched by the list() call sites via
    _resolve_goal_statuses, to avoid one query per row).
    """
    from workflow import state_reader

    resolved_status = getattr(goal, "status", None) or state_reader.current_state(
        "Goal", goal.id
    ) or state_reader.initial_state("Goal")
    return {
        "id": str(goal.id),
        "workspace_id": str(goal.workspace_id),
        # REQ-016 / UI concept ch. 12.11 — see _arch_to_dict for the rationale.
        "artifact_id": str(goal.artifact_id) if getattr(goal, "artifact_id", None) else None,
        "lineage_id": str(goal.lineage_id),
        "sequence_number": goal.sequence_number,
        "title": goal.title,
        "description": getattr(goal, "description", ""),
        "status": resolved_status,
        # REQ-L2-AS-037 / Epic #934 WS1: extended attributes live on the backing
        # Artifact. Goal responses omitted the key entirely, so the read side of
        # a custom-field write looked like it had been dropped.
        "custom_fields": _artifact_custom_fields(goal),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(goal),
        "version": goal.version,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
    }



def _main_goal_to_dict(main_goal: Any) -> dict[str, Any]:
    """Convert MainGoal ORM object to serializer-compatible dict (Task 6).

    Task 12: see ``_goal_to_dict``'s docstring — identical fix.
    """
    from workflow import state_reader

    resolved_status = getattr(main_goal, "status", None) or state_reader.current_state(
        "MainGoal", main_goal.id
    ) or state_reader.initial_state("MainGoal")
    return {
        "id": str(main_goal.id),
        "workspace_id": str(main_goal.workspace_id),
        # #1763: see _adr_to_dict — comment-panel parity for the ARTIFACT id.
        "artifact_id": (
            str(main_goal.artifact_id)
            if getattr(main_goal, "artifact_id", None)
            else None
        ),
        "sequence_number": main_goal.sequence_number,
        "content": main_goal.content,
        "source": getattr(main_goal, "source", "manual"),
        "generated_from_goal_ids": list(getattr(main_goal, "generated_from_goal_ids", []) or []),
        "status": resolved_status,
        "version": main_goal.version,
        "created_at": main_goal.created_at,
        "updated_at": main_goal.updated_at,
    }



def _resolve_goal_statuses(items: list, item_type: str) -> None:
    """Batch-resolve and set ``.status`` in-memory on every item (Task 12).

    Must run before ``_apply_list_query_params`` (whose ``?status=`` filter
    reads ``getattr(i, "status", None)``) and before ``_goal_to_dict``/
    ``_main_goal_to_dict`` build the response -- one engine query for the
    whole page instead of one per row.
    """
    from workflow import state_reader

    if not items:
        return
    states = state_reader.current_states(item_type, (i.id for i in items))
    initial_state = state_reader.initial_state(item_type)
    for item in items:
        item.status = states.get(str(item.id)) or initial_state



def _issue_to_dict(issue: Any) -> dict[str, Any]:
    """Convert Issue ORM object to serializer-compatible dict."""
    return {
        "id": str(issue.id),
        "workspace_id": str(issue.workspace_id),
        # #1763: see _adr_to_dict — comment-panel parity for the ARTIFACT id.
        "artifact_id": (
            str(issue.artifact_id) if getattr(issue, "artifact_id", None) else None
        ),
        "title": issue.title,
        "description": getattr(issue, "description", ""),
        "severity": getattr(issue, "severity", "medium"),
        "category": getattr(issue, "category", "defect"),
        "uid": getattr(issue, "uid", None),
        "status": getattr(issue, "status", "open"),
        "tags": issue.tags if isinstance(issue.tags, list) else [],
        # Task 20 finding: see IssueSerializer.due_date — the GET side of the
        # same silent-discard gap (the value was never even readable).
        "due_date": getattr(issue, "due_date", None),
        "custom_fields": _artifact_custom_fields(issue),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(issue),
        # GH-737 follow-up audit: `version` was the one field IssueSerializer
        # declares (read-only, LOCK_VERSION_HELP_TEXT) that this dict never
        # supplied. DRF silently drops a missing read-only field instead of
        # erroring, so every Issue response shipped without the lock counter
        # while the OpenAPI schema and the frontend `Issue` type both declared
        # it as present — and GET /issues/{id}/versions/ kept handing out
        # version numbers the entity payload could not be correlated with.
        # Every other versioned entity's _*_to_dict already includes it.
        "version": issue.version,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }



def _cr_to_dict(cr: Any) -> dict[str, Any]:
    """Convert ChangeRequest ORM object to serializer-compatible dict (REQ-157)."""
    return {
        "id": str(cr.id),
        "workspace_id": str(cr.workspace_id),
        # #1763 parity / audit 2026-11-15 §5.3: every artifact-backed entity
        # response carries the backing Artifact id. Without it a client cannot
        # tell which Artifact a ChangeRequest owns (comment/trace/version
        # panels are Artifact-addressed).
        "artifact_id": (
            str(cr.artifact_id) if getattr(cr, "artifact_id", None) else None
        ),
        "title": cr.title,
        "description": getattr(cr, "description", ""),
        "impact_assessment": getattr(cr, "impact_assessment", ""),
        "change_reason": getattr(cr, "change_reason", ""),
        "status": getattr(cr, "status", "draft"),
        "requestor_id": str(cr.requestor_id) if cr.requestor_id else None,
        "assigned_reviewer_id": str(cr.assigned_reviewer_id) if cr.assigned_reviewer_id else None,
        # REQ-L2-AS-037 / Epic #934 WS1: see _goal_to_dict — the extended
        # attributes on the backing Artifact were never read back.
        "custom_fields": _artifact_custom_fields(cr),
        # Attribut v3 WS2 (#936): Artifact-level system fields, actor wire form.
        **artifact_system_fields(cr),
        "version": cr.version,
        "created_at": cr.created_at,
        "updated_at": cr.updated_at,
    }



# ---------------------------------------------------------------------------
# WorkspaceViewSet (read-only — list + retrieve, REQ-L1-017)
# ---------------------------------------------------------------------------

# P4.4: response shape of ``GET /workspaces/{id}/locks/``. Declared explicitly
# so the generated schema does not fall back to the ViewSet's
# ``WorkspaceSerializer`` (which would describe a Workspace body for a map).
_WORKSPACE_LOCKS_RESPONSE = inline_serializer(
    name="WorkspaceLocksResponse",
    fields={
        "locks": serializers.DictField(
            child=serializers.CharField(),
            help_text="Frozen artifacts only: {tree node id: state name}.",
        )
    },
)



class WorkspaceViewSet(BaseEntityViewSet):
    """ViewSet for Workspace lookup (REQ-L1-017).

    Read-only surface: workspaces are provisioned via seeding / admin tooling
    today. ``list`` returns all workspaces of the active tenant; ``retrieve``
    fetches a single workspace by id. Tenant scoping is enforced by
    WorkspaceService via TenantContext.
    """

    serializer_class = WorkspaceSerializer
    preset_endpoint_key = ""  # Workspaces are always visible
    # E1.2: a workspace-scoped API key's ``list`` is filtered to the workspaces
    # it may see instead of being denied (it names no target workspace).
    api_key_fence_mode = "filter"

    def _svc(self) -> WorkspaceService:
        return WorkspaceService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/ — list workspaces in the active tenant."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            items = self._svc().list_workspaces(ctx=ctx)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: WorkspaceSerializer(_workspace_to_dict(item)).data
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/ — fetch a single workspace by id.

        #1244: the response carries ``ETag: "<version>"``; send that value back
        as ``If-Match`` on a PATCH to make the write conditional (412 when
        stale). Additive header only — the body is unchanged.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_workspace(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return self.with_etag(
            Response(WorkspaceSerializer(_workspace_to_dict(item)).data), item
        )

    @action(detail=True, methods=["get"], url_path="tree")
    def tree(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/tree/?type=requirement|architecture.

        P1: the ordered sibling forest of one tree, soft-deleted nodes hidden.
        Roots and every sibling list are sorted by ``sort_key``.
        """
        lang = detect_lang(request)
        raw_type = (request.query_params.get("type") or "requirement").lower()
        artifact_type = {
            "requirement": "Requirement",
            "architecture": "ArchitectureElement",
            "architectureelement": "ArchitectureElement",
        }.get(raw_type)
        if artifact_type is None:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'type' must be 'requirement' or 'architecture'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            roots = ArtifactService().get_workspace_tree(
                workspace_id=UUID(pk), artifact_type=artifact_type, ctx=ctx
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
        return Response(
            {
                "workspace_id": str(pk),
                "type": raw_type,
                "tree": [node.as_dict() for node in roots],
            }
        )

    @action(detail=True, methods=["get", "put"], url_path="tiers")
    def tiers(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET/PUT /api/v1/workspaces/{pk}/tiers/ — the tier ladder (P2)."""
        from application.tier_ladder_service import TierLadderService

        lang = detect_lang(request)
        service = TierLadderService()
        try:
            ctx = get_auth_context(request)
            workspace_id = UUID(pk)
            if request.method == "PUT":
                payload = request.data.get("tiers") if isinstance(request.data, dict) else None
                if not isinstance(payload, list):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR",
                            lang,
                            message="Body must be {\"tiers\": [...]}.",
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                entries = service.replace(workspace_id, payload, ctx)
            else:
                entries = service.get(workspace_id).entries
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "workspace_id": str(pk),
                "tiers": [
                    {
                        "tier_key": entry.tier_key,
                        "name": entry.name,
                        "position": entry.position,
                        "rule": entry.rule,
                        "from_end": entry.from_end,
                        "level": entry.position + 1,
                    }
                    for entry in entries
                ],
            }
        )

    @action(detail=True, methods=["get"], url_path="allocation-view")
    def allocation_view(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/allocation-view/ — flat view (P3).

        Query parameters: ``kind=requirement|element`` narrows the page to one
        row kind (counters stay global, V2/B-1); ``page_size`` is 1..500.
        """
        from application.allocation_view_service import AllocationViewService

        lang = detect_lang(request)
        params = request.query_params

        def _bool(name: str) -> bool | None:
            raw = params.get(name)
            if raw is None:
                return None
            return raw.lower() in {"1", "true", "yes"}

        try:
            ctx = get_auth_context(request)
            payload = AllocationViewService().list(
                UUID(pk),
                ctx,
                allocated=_bool("allocated"),
                intent=params.get("intent"),
                kind=params.get("kind"),
                tier=params.get("tier"),
                type=params.get("type"),
                category=params.get("category"),
                state=params.get("state"),
                element_subtree=(
                    UUID(params["element_subtree"])
                    if params.get("element_subtree")
                    else None
                ),
                q=params.get("q"),
                open=_bool("open"),
                page_size=int(params.get("page_size") or 200),
                offset=int(params.get("offset") or 0),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["requirement", "architecture"],
                description="Which classic tree the returned ids belong to.",
            )
        ],
        responses={200: _WORKSPACE_LOCKS_RESPONSE},
    )
    @action(detail=True, methods=["get"], url_path="locks")
    def locks(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/locks/?type=requirement|architecture.

        P4 (§4.5): the batch read the classic trees use to grey out frozen
        nodes. Returns ``{"locks": {"<id>": "<state name>"}}`` containing only
        the artifacts whose **current workflow state** carries
        ``state_meta.freeze_on_enter`` — an empty dict when none are frozen.

        Semantics are the ones ``AllocationViewService`` already uses for its
        ``locked`` column: the freeze-triggering states of the workspace's
        workflow definition are read once per item type, and
        ``workflow.state_reader.current_states`` resolves every item's state in
        one query. The query count is therefore constant in the number of
        items (10 vs 200 costs the same), which is the point of the endpoint.

        ID SPACE — the keys are exactly the ids the two trees put on their
        ``WorkspaceTreeNode``, and **the two trees differ**:

        * ``type=requirement`` → ``Requirement.id`` (the entity row id). The
          requirement tree renders ``id: req.id``
          (``RequirementList.tsx``), not the backing Artifact id.
        * ``type=architecture`` → ``ArchitectureElement.id`` (the entity row
          id). The architecture tree renders ``id: el.id``
          (``ArchitectureEditors.tsx``); it translates to the backing Artifact
          id only for the move endpoint.

        Neither id space is ``Artifact.id``. ``type`` is required; any other
        value is a 400 naming the field. Unknown or foreign workspaces answer
        the same 404/permission as the neighbouring workspace routes, and a
        caller without READ is refused with 403.
        """
        from application.workspace_lock_service import ITEM_TYPES

        lang = detect_lang(request)
        raw_type = (request.query_params.get("type") or "").strip().lower()
        if raw_type not in ITEM_TYPES:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'type' must be 'requirement' or 'architecture'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            workspace_id = UUID(pk)
            # Tenant-scoped existence check: an unknown or foreign workspace is
            # a 404, like ``tiers``/``allocation-view``. Also installs the
            # tenant context the batched reads below rely on.
            WorkspaceService().get_workspace(workspace_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not _caller_may_read_workspace(workspace_id, ctx):
            return _service_error_response(
                PermissionDeniedError(
                    f"Read access to workspace {workspace_id} is required."
                ),
                lang,
            )

        # The batched read (and the shared freeze definition) lives in the
        # application layer: this adapter performs no ORM access of its own.
        from application.workspace_lock_service import get_workspace_locks

        return Response({"locks": get_workspace_locks(workspace_id, raw_type)})

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/ — create a new workspace + preset config.

        Body: {name, preset?, terminology_profile?, language?, theme?,
        decomposition_link_type?, default_link_type?, goals_enabled?,
        goals_ai_enabled?}
        ``preset`` accepts either a bare tier string (``"standard"``) or an
        object carrying it (``{"tier": "standard"}``) — GH-411: the GET
        response always returns the resolved object shape
        (``normalize_preset_blob``), so a client that round-trips it back on
        write must not be rejected.
        Returns: 201 Created with the serialized Workspace.

        SYSTEMAUDIT_2026-08-29 (REST finding 2): the configuration fields after
        ``language`` used to be advertised by ``WorkspaceSerializer`` — and thus
        by this endpoint's OpenAPI request schema — while this handler forwarded
        only name/preset/terminology_profile/language, so the rest were accepted
        with a 201 and dropped. They are now forwarded to the service, which
        keeps the create schema and the create behaviour in agreement. The one
        field that stays unwritable is ``ai_prompts``: it is superseded by the
        versioned ``PromptTemplate`` model (#119) and no write path exists for
        it on create *or* PATCH, so it is declared ``read_only`` on the
        serializer rather than given a new one.
        """
        lang = detect_lang(request)
        # SA-25: run the declared serializer so ``name`` (a SanitizedCharField)
        # is actually validated/sanitized instead of being read straight off
        # request.data — the rest of the body still uses the pre-existing
        # manual defaulting below, because WorkspaceSerializer's own defaults
        # (e.g. language="en") differ from this endpoint's historical ones
        # (language="de") and swapping them would be a silent behaviour change.
        ser = WorkspaceSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = ser.validated_data["name"]
        preset = extract_preset_tier(request.data.get("preset", "standard"))
        if preset is None:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=(
                        "preset must be a tier string (e.g. 'standard') or "
                        "an object carrying one (e.g. {'tier': 'standard'})."
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        terminology_profile = request.data.get("terminology_profile", "se_mode")
        language = request.data.get("language", "de")
        # Forward the remaining configuration fields only when the client
        # actually sent them: WorkspaceSerializer supplies defaults for all of
        # them, and passing those defaults unconditionally would turn every
        # create into an explicit write of values the caller never chose. The
        # service reads ``None`` as "not supplied" and keeps the model default.
        _creatable = (
            "theme",
            "decomposition_link_type",
            "default_link_type",
            "goals_enabled",
            "goals_ai_enabled",
            "glossary_reference_mode",
            "ai_language",
        )
        supplied = request.data if isinstance(request.data, dict) else {}
        config_kwargs = {
            key: ser.validated_data[key]
            for key in _creatable
            if key in supplied and key in ser.validated_data
        }
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_workspace(
                ctx=ctx,
                name=str(name),
                preset=preset,
                terminology_profile=str(terminology_profile),
                language=str(language),
                **config_kwargs,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            WorkspaceSerializer(_workspace_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        # #1397: the header the declared 412 is conditioned on.
        # #1388/F3: and the response header that supplies the next tag.
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: WorkspaceSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PATCH /api/v1/workspaces/{pk}/ — update workspace metadata.

        Body: {name?, language?, terminology_profile?, expected_version?}
        REQ-L2-RF-012: Workspace-Konfigurations-UI write path.

        #1244: the same optimistic-locking contract as the artifact endpoints.
        An ``If-Match`` header (or an ``expected_version`` body field) must match
        the stored ``version``; a stale ``If-Match`` answers 412
        ``PRECONDITION_FAILED``, a stale body field 409 ``CONFLICT``. Omitting
        both stays last-writer-wins, so existing callers are unaffected. The
        response carries the new ``ETag``.
        """
        lang = detect_lang(request)
        # GH-1396: a malformed If-Match must not be discovered after the
        # close/reactivate branch below has already written.
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid

        # GH-1396 review finding B1: validate the payload *before* the lifecycle
        # branch runs. It used to run after it, so ``{"is_active": false,
        # "name": 123}`` closed the workspace and only then answered 400.
        patch_ser = WorkspaceSerializer(data=request.data, partial=True)
        if not patch_ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v}
                        for k, v in patch_ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ``is_active`` is read-only on the serializer, so it never reaches
        # ``validated_data`` — coerce it here, still before any write.
        desired_active: bool | None = None
        if "is_active" in request.data:
            try:
                desired_active = _coerce_bool(request.data["is_active"])
            except ValueError:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message="is_active must be a boolean",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            ctx = get_auth_context(request)
            ws = None

            # GH-1396 review finding B1: resolve the precondition once, *before*
            # either write branch. It used to be resolved only when a metadata
            # field was present, so a conditional lifecycle toggle (all
            # ``_patchable`` fields absent -> ``resolve_expected_version`` never
            # called) closed the workspace whatever ``If-Match`` said. The value
            # is forwarded into the service, which compares it inside its own
            # row-locked transaction.
            expected_version = self.resolve_expected_version(
                request,
                patch_ser.validated_data,
                current=lambda: self._svc().get_workspace(UUID(pk), ctx),
            )

            # Lifecycle toggle: a client-sent ``is_active`` must not be silently
            # dropped. Route it to the dedicated close/reactivate service methods
            # (admin-gated, set closed_at/closed_by, emit distinct audit ops) so
            # the lifecycle logic is not duplicated or bypassed here (REQ-L1-042).
            lifecycle_written = False
            if desired_active is not None:
                if desired_active:
                    ws = self._svc().reactivate_workspace(
                        workspace_id=UUID(pk),
                        ctx=ctx,
                        expected_version=expected_version,
                    )
                else:
                    ws = self._svc().close_workspace(
                        workspace_id=UUID(pk),
                        ctx=ctx,
                        expected_version=expected_version,
                    )
                lifecycle_written = True

            # SA-25: the serializer above already validated/sanitized the
            # supplied fields (partial=True — DRF's partial mode only validates
            # and returns keys actually present in the body, so this preserves
            # the original "forward only fields the client actually supplied"
            # PATCH semantics while adding real validation, notably for ``name``
            # (SanitizedCharField)).
            _patchable = (
                "name",
                "language",
                "theme",
                "decomposition_link_type",
                "default_link_type",
                "terminology_profile",
                "goals_enabled",
                "goals_ai_enabled",
                "glossary_reference_mode",
                "ai_language",
            )
            fields = {
                key: value
                for key, value in patch_ser.validated_data.items()
                if key in _patchable
            }
            if fields:
                # #1244: an If-Match header wins over the expected_version body
                # field; the resolved value is compared inside the service's
                # row-locked transaction, so the check is race-free.
                # GH-1396: the lazy loader runs only for header shapes that need
                # a real ETag comparison (tag list, non-numeric tag).
                # When the lifecycle branch already applied the precondition,
                # the version it left behind is the new baseline — forwarding
                # the *old* expected version to this second write would make
                # every combined ``{"is_active": ..., "name": ...}`` request
                # conflict with its own earlier write.
                ws = self._svc().update_metadata(
                    ctx,
                    UUID(pk),
                    expected_version=(
                        None if lifecycle_written else expected_version
                    ),
                    **fields,
                )
            elif ws is None:
                # No recognized field supplied — return current state unchanged.
                ws = self._svc().get_workspace(UUID(pk), ctx)
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            # GH-1396: malformed → 400 INVALID_IF_MATCH, unmatchable → 412.
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            # #1244: a failed If-Match is a precondition failure (412); the body
            # field keeps the existing 409 CONFLICT contract (same split as the
            # artifact endpoints).
            if self.uses_if_match(request):
                return self.precondition_failed(request)
            return _service_error_response(exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(WorkspaceSerializer(_workspace_to_dict(ws)).data), ws
        )

    def destroy(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """DELETE /api/v1/workspaces/{pk}/ — captcha-confirmed hard-delete.

        BREAKING (#265): this verb previously performed a *soft-close* and
        answered 204 while the workspace stayed fully usable at the same URL,
        so clients could not distinguish it from a real deletion. It now runs
        the exact same confirmation-gated path as
        ``POST /api/v1/workspaces/{pk}/delete/``:

        * no/empty ``confirmation`` in the body → 400 (nothing happens),
        * wrong ``confirmation`` → 409 (nothing happens),
        * matching ``confirmation`` → 204 and the workspace is really gone.

        The reversible soft-close remains available as
        ``POST /api/v1/workspaces/{pk}/close/``.
        """
        return self._confirmed_hard_delete(request, pk)

    @action(detail=True, methods=["patch"], url_path="preset")
    def set_preset(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PATCH /api/v1/workspaces/{pk}/preset/ — switch active preset tier.

        Body: {preset: "minimal" | "standard" | "extended"} — GH-411: also
        accepts the resolved object shape ``{"tier": "minimal"}`` the GET
        response returns, not just the bare string.
        REQ-L2-RF-007 / REQ-L2-RF-012: Preset switch from Workspace Settings UI.
        An unknown workspace answers 404 ``NOT_FOUND``.
        """
        lang = detect_lang(request)
        target_tier = extract_preset_tier(request.data.get("preset"))
        if target_tier is None:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=(
                        "preset must be a tier string (e.g. 'standard') or "
                        "an object carrying one (e.g. {'tier': 'standard'})."
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            self._svc().switch_preset_tier(ctx, UUID(pk), target_tier)
        except (
            ValidationError,
            NotFoundError,
            PermissionDeniedError,
            # SYSTEMAUDIT-2026-08-27 AP-6 M-1: explicit handler ahead of the
            # generic Exception catch-all below — without it, the gate's
            # correctly-raised CrossTenantWorkspaceError fell through to a
            # masked 500 instead of the 403 it deserves.
            CrossTenantWorkspaceError,
        ) as exc:
            return _service_error_response(exc, lang)
        except ObjectDoesNotExist:
            # The preset gate resolves the raw id through unscoped managers,
            # so a missing workspace arrives as Workspace.DoesNotExist instead
            # of the NotFoundError above. Answer the same 404 retrieve gives.
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response({"id": str(pk), "preset": target_tier})

    @action(detail=True, methods=["get"], url_path="reports/pdf")
    def report_pdf(self, request: Request, pk: str = None, **kwargs: Any) -> HttpResponse:
        """GET /api/v1/workspaces/{pk}/reports/pdf/?layout=...

        REQ-L2-AS-016 / REQ-L1-023: Generate a PDF report for the workspace.

        Query params:
            layout: "requirement_document" (default) | "traceability_matrix"

        Returns:
            application/pdf response with Content-Disposition header.
        """
        lang = detect_lang(request)
        layout = request.query_params.get("layout", "requirement_document")

        try:
            ctx = get_auth_context(request)
            # Verify workspace exists and user has access
            ws = self._svc().get_workspace(UUID(pk), ctx)

            from traceability.pdf_report_generator import generate_pdf_report

            pdf_bytes = generate_pdf_report(
                workspace_id=UUID(pk),
                layout=layout,
                ctx=ctx,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        ws_name = ws.name.replace(" ", "_")
        filename = f"{ws_name}_{layout}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/{pk}/clone/ — clone a workspace.

        Body: {target_name: string}
        """
        lang = detect_lang(request)
        target_name = request.data.get("target_name")
        if not target_name or not str(target_name).strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_name is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            item = self._svc().clone_workspace(
                ctx=ctx,
                source_id=UUID(pk),
                target_name=str(target_name),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            WorkspaceSerializer(_workspace_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    # ---- Lifecycle actions (REQ-L1-042) ----

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/{pk}/close/ — soft-close a workspace.

        REQ-L1-042: Admin-only. Sets is_active=False, closed_at, closed_by.
        Returns 200 with the updated workspace.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().close_workspace(
                workspace_id=UUID(pk), ctx=ctx
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(WorkspaceSerializer(_workspace_to_dict(item)).data)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/{pk}/reactivate/ — re-open a closed workspace.

        REQ-L1-042: Admin-only. Sets is_active=True, clears closed_at/by.
        Returns 200 with the updated workspace.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().reactivate_workspace(
                workspace_id=UUID(pk), ctx=ctx
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(WorkspaceSerializer(_workspace_to_dict(item)).data)

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_workspace(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/{pk}/delete/ — hard-delete with captcha.

        REQ-L1-042: Admin-only. Body must contain ``{"confirmation": "<name>"}``
        matching the workspace name (case-sensitive). On mismatch returns 409.
        On success returns 204.
        """
        return self._confirmed_hard_delete(request, pk)

    def _confirmed_hard_delete(self, request: Request, pk: str | None) -> Response:
        """Single implementation behind ``POST .../delete/`` and ``DELETE ...`` (#265).

        Both verbs must enforce the same captcha and hit the same service call,
        so neither can drift into a silent no-op.

        #1084: a workspace that still holds baselines answers ``409 CONFLICT``
        with ``details.code == "baselines_immutable"`` and a message naming the
        real removal path. Before, that case reached the ``bl_raise_immutable``
        DB trigger and surfaced as a 500, which made ``/delete/`` a dead end for
        exactly those workspaces.

        #1199: ``?force=true`` is deliberately NOT supported and no longer
        silently ignored. It used to be dropped on the floor, so a caller that
        sent it believed it had opted into a cascade the server never performed.
        Rather than hide a second, undocumented deletion path behind a query
        flag, the request is rejected with a 400 naming the audited admin route
        (``DELETE /api/v1/baselines/{id}/purge/``); the captcha semantics below
        stay the only way to delete a workspace.
        """
        lang = detect_lang(request)
        force = request.query_params.get("force")
        if force is not None and str(force).strip().lower() in {"1", "true", "yes"}:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=(
                        "The 'force' parameter is not supported: baselines are "
                        "append-only and are never removed implicitly. Delete "
                        "each baseline through the audited admin route "
                        "DELETE /api/v1/baselines/{id}/purge/ first, then retry "
                        "this hard-delete."
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        confirmation = request.data.get("confirmation", "")
        if not confirmation:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="confirmation field is required",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace_id = UUID(str(pk))
        except (TypeError, ValueError):
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            ctx = get_auth_context(request)
            self._svc().delete_workspace(
                workspace_id=workspace_id,
                confirmation_text=str(confirmation),
                ctx=ctx,
            )
        except BaselineImmutabilityError as exc:
            # Baselines are append-only, so the workspace cannot go away while
            # one exists. 409, and a details code a client can branch on —
            # deliberately ahead of the ValidationError clause below, which
            # would otherwise label this a captcha mismatch.
            return Response(
                build_error_response(
                    "CONFLICT", lang,
                    message=str(exc),
                    details=[{"code": "baselines_immutable"}],
                ),
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            # Captcha mismatch → 409 Conflict
            return Response(
                build_error_response(
                    "CONFLICT", lang,
                    message=str(exc),
                    details=[{"code": "confirmation_mismatch"}],
                ),
                status=status.HTTP_409_CONFLICT,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ProtectedError as exc:
            # #1241 safety net: the cascade order in WorkspaceService now removes
            # the PROTECT-referencing rows explicitly, so this should be
            # unreachable. If a future PROTECT FK is added without a matching
            # cascade step, the delete must still be a described 409 rather than
            # an opaque 500. The referencing model/columns are deliberately NOT
            # echoed (ProtectedError's message names internals); the detail code
            # is what a client branches on.
            logger.warning(
                "Workspace %s hard-delete blocked by a protected foreign key",
                workspace_id,
                exc_info=exc,
            )
            return Response(
                build_error_response(
                    "CONFLICT", lang,
                    details=[{"code": "protected_relations"}],
                ),
                status=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)



# ---------------------------------------------------------------------------
# AdrViewSet — COMP-AS-013 (REQ-L1-029)
# ---------------------------------------------------------------------------


class AdrViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for ADR CRUD operations (REQ-L1-029).

    Delegates to AdrService (COMP-AS-013, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = AdrSerializer
    preset_endpoint_key = ""
    workflow_item_type = "Adr"
    attribute_item_type = "Adr"

    def _svc(self) -> AdrService:
        return AdrService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_adr(UUID(pk), ctx)
        return item.id, item.workspace_id

    # #915: ADR has no denormalized ``status`` column (Task 12); the shared
    # ``_current_status`` resolves the state from the workflow engine.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_adr(item_id, ctx)
        return {"adr": AdrSerializer(_adr_to_dict(updated)).data}

    @list_schema(status=True, search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/adrs/ — list ADRs in a workspace.

        REQ-006: Excludes soft-deleted ADRs by default.
        Pass ?include_deleted=true for admin/audit access.
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
            # REQ-006: include_deleted=true exposes soft-deleted ADRs (admin use)
            include_deleted = parse_include_deleted(request.query_params)
            items = self._svc().list_adrs(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=include_deleted,
                status=request.query_params.get("status") or None,
                search=request.query_params.get("search") or None,
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
            serialize_page=lambda page: AdrSerializer(
                [_adr_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/adrs/{pk}/ — retrieve single ADR."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_adr(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AdrSerializer(_adr_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/adrs/ — create an ADR. Returns 201."""
        lang = detect_lang(request)
        ser = AdrSerializer(data=request.data)
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
            item = self._svc().create_adr(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                description=data.get("description", ""),
                ctx=ctx,
                context=data.get("context", ""),
                decision=data.get("decision", ""),
                consequences=data.get("consequences", ""),
                custom_fields=data.get("custom_fields"),
                # Datenmodell-Konsolidierung Phase 1: a new ADR always starts
                # at the workflow definition's initial_state. AdrSerializer.status
                # is read-only (WorkflowStateSerializerMixin), so `data` (the
                # validated_data) can never carry a client-supplied status, and
                # create_adr() no longer even accepts one — a client-supplied
                # `status` is ignored, not rejected, consistent with
                # ADR-status-single-source.
            )
            self._apply_artifact_system_fields(request, "Adr", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=OpenApiRequest(
            request=inline_serializer(
                name="AdrDeriveFromDecisionRequest",
                fields={
                    "workspace_id": serializers.UUIDField(
                        help_text="Workspace the resulting ADR would belong to."
                    ),
                    "decision_description": serializers.CharField(
                        help_text="Free-text description of the decision to structure."
                    ),
                    "mode": serializers.ChoiceField(
                        choices=["preview", "write"],
                        required=False,
                        default="preview",
                        help_text=(
                            "'preview' (default) returns the draft only and "
                            "marks the response `ephemeral: true`; 'write' is "
                            "the canonical persistence path (persists the ADR)."
                        ),
                    ),
                    "policy": serializers.ChoiceField(
                        choices=["manual", "auto"],
                        required=False,
                        default="manual",
                        help_text=(
                            "Only relevant for mode='write': 'manual' (default) "
                            "leaves the ADR in its initial state; 'auto' "
                            "best-effort auto-advances it."
                        ),
                    ),
                },
            ),
        ),
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Ephemeral ADR draft preview — persists nothing. Body: "
                    "`draft` (object with `title`, `description`, `context`, "
                    "`consequences`), `workspace_id` (uuid string), "
                    "`is_mock_fallback` (bool) and `ephemeral` (always `true`)."
                ),
            ),
            201: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Write mode: the persistence receipt. Body: `written` "
                    "(a single object — the flow has exactly one draft — with "
                    "`id`, `status` and the `proposal` block: `state`, "
                    "`is_proposal`, `supported`, `proposed_by`, `label`, "
                    "`reason`) and `is_mock_fallback` (bool)."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Unknown field, malformed workspace_id, empty "
                    "decision_description, invalid mode/policy."
                ),
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
            "Structure a free-text decision into an ADR draft (REST parity with "
            "the MCP tool `ai_derivation.derive_adr_from_decision`, #1358).\n\n"
            "- `mode='preview'` (default): ephemeral draft, nothing persisted.\n"
            "- `mode='write'`: persists the draft through "
            "`AiDerivationService.persist_adr_draft` (born `proposed` where the "
            "workspace's workflow supports it). No trace link is created (the "
            "input is raw free text, not an existing artifact id)."
        ),
    )
    @action(detail=False, methods=["post"], url_path="derive-from-decision")
    def derive_from_decision(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/adrs/derive-from-decision/ — AI ADR draft (preview | write).

        Issue #1358 (W12a): REST parity for
        ``ai_derivation.derive_adr_from_decision``. The preview response is
        ephemeral (``"ephemeral": true``, #1358); ``mode="write"`` is the
        canonical persistence path and reuses the exact same write seam as the
        MCP tool (``AiDerivationService.persist_adr_draft`` →
        ``_write_adr_draft``), so both transports persist identically (status
        ``proposed`` where the workspace's workflow supports it, see #1089).

        Body: ``{"workspace_id": <uuid>, "decision_description": <str>,
        "mode"?: "preview"|"write", "policy"?: "manual"|"auto"}``. Unknown keys
        are rejected (#851).
        """
        lang = detect_lang(request)
        invalid = reject_unknown_fields(
            request.data,
            {"workspace_id", "decision_description", "mode", "policy"},
            lang,
        )
        if invalid is not None:
            return invalid
        payload = request.data if isinstance(request.data, dict) else {}
        workspace_id, error = parse_workspace_id(payload.get("workspace_id"), lang)
        if error is not None:
            return error
        decision_description = payload.get("decision_description")
        if not isinstance(decision_description, str) or not decision_description.strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'decision_description' must be a non-empty string.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        mode, policy, error = _parse_derivation_mode_policy(request, lang)
        if error is not None:
            return error

        try:
            from application.ai_derivation_service import AiDerivationService

            ctx = get_auth_context(request)
            service = AiDerivationService()
            preview = service.derive_adr_from_decision(
                ctx, workspace_id, decision_description=decision_description
            )
            if mode == "preview":
                return Response(preview, status=status.HTTP_200_OK)
            result = service.persist_adr_draft(
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
            logger.exception("AdrViewSet.derive_from_decision: unhandled exception")
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/adrs/{pk}/ — update an ADR. Returns 200."""
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=AdrSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = AdrSerializer(data=request.data, partial=True)
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
        # REQ-L2-AS-037: only forward custom_fields when the client actually
        # sent it, so an unrelated PATCH does not wipe existing custom_fields
        # (same pattern as RequirementViewSet.partial_update).
        extra_kwargs: dict[str, Any] = {}
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_adr(
                adr_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                context=data.get("context"),
                decision=data.get("decision"),
                consequences=data.get("consequences"),
                change_reason=data.get("change_reason"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                **extra_kwargs,
            )
            self._apply_artifact_system_fields(request, "Adr", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/adrs/{pk}/ — soft-delete an ADR. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. The backing
        Artifact's lifecycle_status moves to "outdated" (Phase 4: an Artifact
        flag, not a workflow state) and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        TraceLinks pointing at the record survive the delete, and traceability
        coverage ignores outdated records.
        """
        lang = detect_lang(request)
        change_reason = parse_change_reason(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_adr(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/adrs/{pk}/diff/?from_version=0&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            adr = self._svc().get_adr(UUID(pk), ctx)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(adr.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff_for_entity(
                entity_type="Adr",
                entity_id=UUID(pk),
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
        """GET /api/v1/adrs/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions_for_entity(
                entity_type="Adr",
                entity_id=UUID(pk),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="supersede")
    def supersede(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/adrs/{pk}/supersede/ — mark this ADR as superseded (REQ-L3-ADR-005).

        UI-32 (Systemaudit 2026-08-27 AP-5): ``AdrService.transition_status``
        has always accepted a ``superseded_by_id`` and recorded the successor
        via a ``decides`` TraceLink, but the generic
        ``WorkflowTransitionsMixin.transitions()`` POST action — the only
        endpoint ``AdrViewSet`` exposed for status changes — calls
        ``WorkflowFacade.transition()`` directly and has no concept of that
        parameter, so the capability was unreachable from the REST API. This
        dedicated action is the missing entry point; it does not duplicate
        the generic transition (role/change_reason/signature gates still run
        inside ``WorkflowFacade.transition``, which this delegates to via
        ``AdrService.transition_status``).

        Body: ``{superseded_by_id, change_reason?, credential?, expected_version?}``.
        """
        lang = detect_lang(request)
        superseded_by_raw = request.data.get("superseded_by_id")
        if not superseded_by_raw:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="superseded_by_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            # AUD-2026-09-282: this special route used to drop any version
            # precondition, leaving it last-writer-wins while the generic
            # ``transitions/`` route is CAS-protected. Forward the client's
            # ``If-Match``/``expected_version`` into the engine (stale -> 409).
            expected_version = self.resolve_expected_version_int(
                request, request.data
            )
            item = self._svc().transition_status(
                UUID(pk),
                "Superseded",
                ctx,
                change_reason=request.data.get("change_reason") or "",
                superseded_by_id=UUID(str(superseded_by_raw)),
                credential=request.data.get("credential") or "",
                expected_version=expected_version,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data)



# ---------------------------------------------------------------------------
# RiskViewSet — COMP-AS-014 (REQ-L1-029)
# ---------------------------------------------------------------------------


class RiskViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Risk CRUD operations (REQ-L1-029).

    Delegates to RiskService (COMP-AS-014, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = RiskSerializer
    preset_endpoint_key = ""
    workflow_item_type = "Risk"
    attribute_item_type = "Risk"

    def _svc(self) -> RiskService:
        return RiskService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_risk(UUID(pk), ctx)
        return item.id, item.workspace_id

    def _severity_is_echoed(
        self, request: Request, pk: str, ctx: Any
    ) -> bool:
        """Whether the PATCH body carries the stored ``severity`` unchanged.

        #1707: only an unchanged echo may bypass the attribute gate (and the
        write), so an ``editable="automation"`` workspace keeps accepting a
        resent form while still refusing a real override. Any read failure
        answers ``False``: the normal path then raises the real error (404,
        403) or the gate explains the violation — never a silent success.
        """
        data = request.data
        if not isinstance(data, dict) or "severity" not in data:
            return False
        try:
            current = self._svc().get_risk(UUID(pk), ctx).severity
        except (NotFoundError, PermissionDeniedError, ValueError, TypeError):
            return False
        return data.get("severity") == current

    # #915: Risk has no denormalized ``status`` column (Task 12); the shared
    # ``_current_status`` resolves the state from the workflow engine.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_risk(item_id, ctx)
        return {"risk": RiskSerializer(_risk_to_dict(updated)).data}

    @list_schema(status=True, search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/risks/ — list all Risks in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            items = self._svc().list_risks(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                status=request.query_params.get("status") or None,
                search=request.query_params.get("search") or None,
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
            serialize_page=lambda page: RiskSerializer(
                [_risk_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/risks/{pk}/ — retrieve single Risk."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_risk(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(RiskSerializer(_risk_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/risks/ — create a Risk. Returns 201."""
        lang = detect_lang(request)
        ser = RiskSerializer(data=request.data)
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
            item = self._svc().create_risk(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                probability=data.get("probability", "medium"),
                impact=data.get("impact", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "technical"),
                owner=data.get("owner_name", ""),
                mitigation_strategy=data.get("mitigation_strategy", ""),
                # Datenmodell-Konsolidierung Phase 1: a new Risk always starts
                # at the workflow definition's initial_state. RiskSerializer.status
                # is read-only (WorkflowStateSerializerMixin), so `data` (the
                # validated_data) can never carry a client-supplied status, and
                # create_risk() no longer even accepts one — a client-supplied
                # `status` is ignored, not rejected, consistent with
                # ADR-status-single-source.
                detection=data.get("detection", 5),
                owner_user_id=data.get("owner_user_id"),
                custom_fields=data.get("custom_fields"),
                # #1707: ``severity`` is a writable enum. Omitting it keeps the
                # score-derived initial value (see ``create_risk``).
                severity=data.get("severity"),
            )
            # Attribut v3 WS7 (#940): Risk is now inside the system-field
            # rollout gate, so owner/reporter/priority route through the shared
            # gateway like every other wired type.
            self._apply_artifact_system_fields(request, "Risk", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/risks/{pk}/ — update a Risk. Returns 200.

        #1707 echo contract: ``severity`` may be ``editable="automation"`` in
        the workspace definition, in which case the attribute gate rejects any
        client-supplied value. Detail panels resend the whole form, though, so
        an *unchanged* echo must stay accepted (same rule as ``status`` #263
        and ``level``/ADR-005). The attribute gate only knows "the row exists",
        not its values (``field_validation``'s ``existing`` contract), so the
        comparison happens here: read the stored value, and only hand
        ``severity`` to the gate when it actually differs.
        """
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        severity_echoed = self._severity_is_echoed(request, pk, ctx)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=RiskSerializer,
            pk=pk,
            ctx=ctx,
            omit_fields=frozenset({"severity"}) if severity_echoed else frozenset(),
        )
        if invalid is not None:
            return invalid
        ser = RiskSerializer(data=request.data, partial=True)
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
        # REQ-L2-AS-037: only forward custom_fields when the client actually
        # sent it, so an unrelated PATCH does not wipe existing custom_fields
        # (same pattern as RequirementViewSet.partial_update).
        extra_kwargs: dict[str, Any] = {}
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        try:
            item = self._svc().update_risk(
                risk_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                probability=data.get("probability"),
                impact=data.get("impact"),
                severity=None if severity_echoed else data.get("severity"),
                category=data.get("category"),
                # WS6/WS7 review (#939/#940) Blocker 1: ``RiskService`` writes
                # this argument into the free-text ``Risk.owner_name`` column
                # (``risk_service.update_risk``: ``risk.owner_name = owner``).
                # The serializer's ``owner`` key is the *Actor* wire value from
                # ``ArtifactSystemFieldsSerializerMixin`` and must never reach
                # the CharField — passing it persisted ``str(dict)`` and dropped
                # the client's real ``owner_name``. The Actor value is applied
                # separately by ``_apply_artifact_system_fields`` below, exactly
                # like the create path.
                owner=data.get("owner_name"),
                mitigation_strategy=data.get("mitigation_strategy"),
                change_reason=data.get("change_reason"),
                detection=data.get("detection"),
                owner_user_id=data.get("owner_user_id"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                **extra_kwargs,
            )
            self._apply_artifact_system_fields(request, "Risk", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/risks/{pk}/ — soft-delete a Risk. Returns 204.

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
            self._svc().delete_risk(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/risks/{pk}/diff/?from_version=0&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            risk = self._svc().get_risk(UUID(pk), ctx)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(risk.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff_for_entity(
                entity_type="Risk",
                entity_id=UUID(pk),
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
        """GET /api/v1/risks/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions_for_entity(
                entity_type="Risk",
                entity_id=UUID(pk),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)



# ---------------------------------------------------------------------------
# GoalViewSet / MainGoalViewSet — REQ-L2-TE-020 (Task 6 of feat/ziele-hauptziel-design)
# ---------------------------------------------------------------------------


def _apply_list_query_status(items: list, params: Any, status_field: str) -> list:
    """Stage 1: ``?status=`` equality filter on ``status_field``."""
    status_value = params.get("status")
    if not status_value:
        return items
    return [i for i in items if getattr(i, status_field, None) == status_value]



def _apply_list_query_source(items: list, params: Any, source_field: str | None) -> list:
    """Stage 2: ``?source=`` equality filter, only when ``source_field`` is set."""
    if not source_field:
        return items
    source_value = params.get("source")
    if not source_value:
        return items
    return [i for i in items if getattr(i, source_field, None) == source_value]



def _apply_list_query_search(items: list, params: Any, search_fields: tuple[str, ...]) -> list:
    """Stage 3: case-insensitive substring search across ``search_fields``."""
    search_value = params.get("search")
    if not search_value or not search_fields:
        return items
    needle = search_value.lower()
    return [
        i
        for i in items
        if any(needle in (getattr(i, f, "") or "").lower() for f in search_fields)
    ]



def _apply_list_query_ordering(
    items: list, params: Any, ordering_fields: tuple[str, ...], lang: str
) -> tuple[list | None, Response | None]:
    """Stage 4: ``?ordering=`` sort; an unknown field answers HTTP 400."""
    ordering_value = params.get("ordering")
    if not ordering_value:
        return items, None
    descending = ordering_value.startswith("-")
    field = ordering_value[1:] if descending else ordering_value
    if field not in ordering_fields:
        return None, Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message=f"Invalid ordering field '{field}'. "
                f"Allowed: {sorted(ordering_fields)}",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return sorted(items, key=lambda i: getattr(i, field, None) or "", reverse=descending), None



def _apply_list_query_limit(
    items: list, params: Any, lang: str
) -> tuple[list | None, Response | None]:
    """Stage 5: ``?limit=`` cap; negative or unparseable answers HTTP 400."""
    limit_value = params.get("limit")
    if limit_value is None:
        return items, None
    try:
        limit = int(limit_value)
    except (TypeError, ValueError):
        limit = -1
    if limit < 0:
        return None, Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message="'limit' must be a non-negative integer",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return items[:limit], None



def _apply_list_query_params(
    items: list,
    request: Request,
    lang: str,
    *,
    search_fields: tuple[str, ...] = (),
    ordering_fields: tuple[str, ...] = (),
    status_field: str = "status",
    source_field: str | None = None,
) -> tuple[list | None, Response | None]:
    """Apply ``?status=``/``?source=``/``?search=``/``?ordering=``/``?limit=``.

    fix #236: GoalViewSet.list()/MainGoalViewSet.list() fetch every current
    version via the service layer and hand the plain in-memory list straight
    to ``_paginate`` — no query parameter besides ``workspace_id`` was ever
    read, so status/source/search/ordering/limit were silently ignored.
    ``_paginate`` (via ``StandardPagination``) only understands ``page``/
    ``page_size``, not the ad-hoc filtering/sorting/limit contract the API
    consumers expect, so this centralises it for both ViewSets rather than
    duplicating the same filter loop twice.

    Runs as five ordered stages — status, source, search, ordering, limit
    (one private helper each). Every stage either narrows the in-memory list
    or yields the 400 error, so the response bodies stay unchanged.

    Returns ``(filtered_items, None)`` on success or ``(None, error_response)``
    when a parameter fails validation (HTTP 400) — callers should return the
    error response unchanged.
    """
    params = request.query_params

    items = _apply_list_query_status(items, params, status_field)
    items = _apply_list_query_source(items, params, source_field)
    items = _apply_list_query_search(items, params, search_fields)
    items, invalid = _apply_list_query_ordering(items, params, ordering_fields, lang)
    if invalid is not None:
        return None, invalid
    items, invalid = _apply_list_query_limit(items, params, lang)
    if invalid is not None:
        return None, invalid

    return items, None



class GoalViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Goal CRUD operations (REQ-L2-TE-020).

    Delegates to GoalService (ADR-01). No business logic in this class
    (REQ-L3-RA001-004). Goal versioning is lineage-based (Variante A): every
    edit creates a brand-new row sharing the same ``lineage_id``.
    """

    serializer_class = GoalSerializer
    preset_endpoint_key = ""
    workflow_item_type = "Goal"
    attribute_item_type = "Goal"
    # Issue #460 finding 4: the DRF router's default pk pattern ([^/.]+) also
    # matched non-id segments, so GET /api/v1/goals/main/ resolved to
    # retrieve(pk="main") and answered 400 "'pk' must be a well-formed UUID"
    # for what is simply a route that does not exist (the aggregated goal
    # lives at /api/v1/main-goals/current/). Pinning the detail lookup to a
    # UUID shape makes routing decline the segment, yielding a plain 404 —
    # same treatment StakeholderNeedViewSet already applies for REQ-128.
    # Issue #271's "malformed pk -> 400" contract is unaffected for anything
    # UUID-shaped: this regex only rejects segments that cannot be an id at
    # all, and BaseEntityViewSet's guard still 400s near-miss UUIDs.
    lookup_value_regex = r"[0-9a-fA-F-]{36}"

    def _svc(self) -> GoalService:
        return GoalService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        goal = self._svc().get(UUID(pk), ctx)
        return goal.id, goal.workspace_id

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/goals/ — list the latest version of every Goal lineage."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            items = self._svc().list_current(workspace_id, ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        # Task 12: `status` column dropped -- batch-resolve it in-memory
        # before the ?status= filter/ordering below reads getattr(i, "status").
        _resolve_goal_statuses(items, "Goal")
        # fix #236: apply status/search/ordering/limit query parameters.
        items, err = _apply_list_query_params(
            items,
            request,
            lang,
            search_fields=("title", "description"),
            ordering_fields=(
                "title",
                "status",
                "sequence_number",
                "created_at",
                "updated_at",
            ),
        )
        if err is not None:
            return err
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: GoalSerializer(
                [_goal_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/goals/{pk}/ — retrieve a single Goal version."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(GoalSerializer(_goal_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/goals/ — create a new Goal version. Returns 201.

        Body may include ``lineage_id`` to append a new version to an
        existing lineage; when omitted, a brand-new lineage is started
        (GoalService.create_version).
        """
        lang = detect_lang(request)
        ser = GoalSerializer(data=request.data)
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
        ctx = get_auth_context(request)
        # ``existing=None`` (create semantics) applies to every version, not
        # only the first: Goal is lineage-based (Variante A) — a new version
        # is always a brand-new row (GoalService.create_version), never a
        # PATCH onto an existing one (partial_update() below 405s), so there
        # is no "update" call site for this ViewSet where an ``existing``
        # marker would apply. Every write must satisfy the required
        # attributes, matching the row it actually creates.
        definition_error = self._validate_attribute_definition(
            ctx,
            data["workspace_id"],
            dict(request.data) if isinstance(request.data, dict) else {},
            None,
        )
        if definition_error is not None:
            return definition_error
        try:
            result = self._svc().create_version(
                workspace_id=data["workspace_id"],
                title=data["title"],
                description=data.get("description", ""),
                lineage_id=data.get("lineage_id"),
                # REQ-L2-AS-037 / Epic #934 WS1: forward the extended attributes
                # the serializer now declares; absent stays None here (create
                # semantics, so there is no stored map to preserve).
                custom_fields=data.get("custom_fields"),
                ctx=ctx,
            )
            item = self._svc().get(UUID(result["id"]), ctx)
            # Attribut v3 WS2 (#936): owner/reporter/priority live on the
            # version's dedicated backing Artifact.
            self._apply_artifact_system_fields(request, "Goal", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            GoalSerializer(_goal_to_dict(item)).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/goals/{pk}/versions/ — all versions of this Goal's lineage."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            goal = self._svc().get(UUID(pk), ctx)
            result = ArtifactDiffService().list_versions_for_goal(goal.lineage_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/goals/{pk}/diff/?from_version=1&to_version=2

        GH-1200: structured field-level diff between two versions of this
        Goal's lineage. Mirrors the ``diff`` action every other artifact
        ViewSet exposes (same ``from_version``/``to_version`` query contract)
        but delegates to ``ArtifactDiffService.diff_for_goal`` — Goal is
        immutable-row-per-version, so the generic entity-diff path cannot
        address its sequence-number namespace (see that method's docstring).
        ``to_version`` defaults to this version's ``sequence_number`` (the
        lineage revision), not the lock-counter ``version``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            goal = self._svc().get(UUID(pk), ctx)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get("to_version", str(goal.sequence_number))
            )

            result = ArtifactDiffService().diff_for_goal(
                lineage_id=goal.lineage_id,
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

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # fix #235: BaseEntityViewSet.partial_update() raises NotImplementedError
        # by default, uncaught by the exception handlers below — DRF's router
        # still wires PATCH to this method for any registered ViewSet, so the
        # request reached the base stub and crashed with an HTML 500 page.
        # Goals are lineage-versioned (Variante A): editing creates a new
        # version via POST /api/v1/goals/ (GoalService.create_version) rather
        # than mutating a row in place, so this now fails cleanly instead of
        # crashing.
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                message="Goals cannot be updated in place. POST a new version instead.",
            ),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # fix #235: see partial_update() above — Goal has no hard-delete
        # semantics (GoalService has no delete method); return a clean 405
        # instead of the base class's NotImplementedError crash. #739: taking
        # a Goal out of active use is available via the dedicated
        # POST .../outdate/ action below — Goal cannot reuse plain DELETE for
        # that the way other artifact types do, because its archived state
        # isn't the generic "outdated" escape hatch (see outdate()'s
        # docstring).
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                message=(
                    "Goals cannot be deleted. POST .../outdate/ to archive "
                    "a Goal version instead."
                ),
            ),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["post"], url_path="outdate")
    def outdate(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/goals/{pk}/outdate/ — archive a Goal version (#739).

        REST parity for the MCP ``goal.delete`` tool. Goals are immutable,
        lineage-versioned rows (see class docstring), so neither a hard
        DELETE (``destroy()`` above) nor the generic
        ``WorkflowTransitionsMixin`` DELETE-based soft-delete convention used
        by other artifact types applies here: that convention force-writes
        the system-wide "outdated" state, which is foreign to the Goal
        workflow and — because ``Goal`` is mirrored into
        ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS`` — would make the
        row slip past the ``Archiviert`` filters ``GoalService.list_current``
        applies (see ``GoalService.archive``'s docstring). This calls that
        exact ``GoalService.archive()`` / ``WorkflowFacade`` path instead —
        the same one the MCP ``goal.delete`` tool uses — so role and
        change_reason gates apply identically. Reversible via
        ``reactivate()`` below.

        Body: ``{"change_reason": "..."}`` (optional, subject to preset
        gates). Returns 200 with the refreshed Goal on success.
        """
        lang = detect_lang(request)
        change_reason = (
            request.data.get("change_reason")
            if isinstance(request.data, dict)
            else None
        )
        # AUD-2026-09-282: forward the client's If-Match/expected_version so
        # this special route is CAS-protected like the generic one; a stale
        # revision answers 409 instead of last-writer-wins.
        # GH-1396 review finding B3: ``InvalidIfMatch``/``IfMatchMismatch`` are
        # deliberately not ``ValueError`` subclasses, so the old single handler
        # let them escape the whole method — past the second ``try`` as well —
        # and ``reqogniloom_exception_handler`` turned both into HTTP 500. They
        # are mapped here exactly like ``transitions/``: malformed -> 400, a lost
        # precondition -> 409 (CR-08, this route's revision is the
        # WorkflowItemState revision, so never 412).
        try:
            expected_version = self.resolve_expected_version_int(
                request, request.data
            )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            return _special_route_if_match_error(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            item = self._svc().archive(
                UUID(pk),
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
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
        return Response(GoalSerializer(_goal_to_dict(item)).data)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/goals/{pk}/reactivate/ — restore an archived Goal version.

        Overrides ``WorkflowTransitionsMixin.reactivate``: the inherited
        action only restores an item whose current state is literally
        "outdated" — the system-wide escape-hatch state ``outdate()`` above
        deliberately avoids for Goal — so the inherited action would always
        answer 400 ("item not currently outdated") for a Goal. This instead
        calls ``GoalService.restore()``, the exact path the MCP
        ``goal.reactivate`` tool uses, which always resets the version to the
        workflow's initial state rather than its pre-archive state (see that
        method's docstring for why).

        Body: ``{"change_reason": "..."}`` (optional; ``GoalService.restore``
        defaults to ``"reactivated"`` when the workspace's Goal workflow
        requires a non-empty reason for this transition). Returns 200 with
        the refreshed Goal on success.
        """
        lang = detect_lang(request)
        change_reason = (
            request.data.get("change_reason")
            if isinstance(request.data, dict)
            else None
        )
        # AUD-2026-09-282: see outdate() above — same CAS precondition.
        # GH-1396 review finding B3: same 400/409 mapping as outdate(); without
        # it the non-ValueError resolver exceptions escaped as HTTP 500.
        try:
            expected_version = self.resolve_expected_version_int(
                request, request.data
            )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            return _special_route_if_match_error(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            item = self._svc().restore(
                UUID(pk),
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
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
        return Response(GoalSerializer(_goal_to_dict(item)).data)



class MainGoalViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for MainGoal operations (REQ-L2-TE-020).

    Delegates to MainGoalService (ADR-01). No business logic in this class
    (REQ-L3-RA001-004). MainGoal is a single workspace-scoped version chain
    (not lineage-based like Goal); ``approve`` transitions a draft to
    ``Freigegeben`` through the generic WorkflowEngine.
    """

    serializer_class = MainGoalSerializer
    preset_endpoint_key = ""
    workflow_item_type = "MainGoal"

    def _svc(self) -> MainGoalService:
        return MainGoalService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        main_goal = self._svc().get(UUID(pk), ctx)
        return main_goal.id, main_goal.workspace_id

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/main-goals/ — list all MainGoal versions in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            items = list(self._svc().list_all(workspace_id, ctx))
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        # Task 12: `status` column dropped -- batch-resolve it in-memory
        # before the ?status= filter/ordering below reads getattr(i, "status").
        _resolve_goal_statuses(items, "MainGoal")
        # fix #236: apply status/source/search/ordering/limit query parameters.
        items, err = _apply_list_query_params(
            items,
            request,
            lang,
            search_fields=("content",),
            ordering_fields=(
                "status",
                "source",
                "sequence_number",
                "created_at",
                "updated_at",
            ),
            source_field="source",
        )
        if err is not None:
            return err
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: MainGoalSerializer(
                [_main_goal_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/main-goals/{pk}/ — retrieve a single MainGoal version.

        fix #235: this override was missing entirely, so DRF's router still
        wired GET .../{pk}/ to BaseEntityViewSet.retrieve(), which raises
        NotImplementedError uncaught by the except-blocks below and crashed
        with an HTML 500 page instead of a JSON response.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(MainGoalSerializer(_main_goal_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/main-goals/ — manually author a new MainGoal draft. Returns 201."""
        lang = detect_lang(request)
        ser = MainGoalSerializer(data=request.data)
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
            result = self._svc().create_manual(
                workspace_id=data["workspace_id"],
                content=data["content"],
                ctx=ctx,
            )
            item = self._svc().get(UUID(result["id"]), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            MainGoalSerializer(_main_goal_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/main-goals/generate/ — aggregate current Goals via LLM. Returns 201."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.data.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            result = self._svc().generate_ai(workspace_id=workspace_id, ctx=ctx)
            item = self._svc().get(UUID(result["id"]), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        # UI-28: `is_mock_fallback` is not a persisted MainGoal field (it only
        # describes how THIS generate call was served), so it must be merged
        # in from the service's response dict here rather than re-derived
        # from the freshly re-fetched `item`.
        data = _main_goal_to_dict(item)
        data["is_mock_fallback"] = bool(result.get("is_mock_fallback", False))
        return Response(
            MainGoalSerializer(data).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/main-goals/{pk}/approve/ — transition to Freigegeben via WorkflowEngine."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            change_reason = request.data.get("change_reason") if hasattr(request, "data") else None
            # AUD-2026-09-282: this special route used to drop any version
            # precondition, leaving it last-writer-wins while the generic
            # ``transitions/`` route is CAS-protected. Forward the client's
            # ``If-Match``/``expected_version`` into the engine (stale -> 409).
            expected_version = self.resolve_expected_version_int(
                request, request.data
            )
            self._svc().approve(
                UUID(pk),
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
            )
            # Return the FULL serialized MainGoal (not the service's bare
            # {id, sequence_number, status} dict), matching create/generate/
            # current — the frontend replaces its panel state with this
            # response and would otherwise blank out `content`.
            item = self._svc().get(UUID(pk), ctx)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(MainGoalSerializer(_main_goal_to_dict(item)).data)

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/main-goals/current/ — newest Freigegeben MainGoal for a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            main_goal = self._svc().get_current(workspace_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        if main_goal is None:
            return Response(None, status=status.HTTP_200_OK)
        return Response(MainGoalSerializer(_main_goal_to_dict(main_goal)).data)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/main-goals/{pk}/versions/ — all versions for this MainGoal's workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            main_goal = self._svc().get(UUID(pk), ctx)
            result = ArtifactDiffService().list_versions_for_main_goal(main_goal.workspace_id, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/main-goals/{pk}/diff/?from_version=1&to_version=2

        GH-1200: structured field-level diff between two versions of the
        workspace's MainGoal chain. Mirrors the ``diff`` action every other
        artifact ViewSet exposes (same ``from_version``/``to_version`` query
        contract) and delegates to ``ArtifactDiffService.diff_for_main_goal``.
        ``to_version`` defaults to this version's ``sequence_number``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            main_goal = self._svc().get(UUID(pk), ctx)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get(
                    "to_version", str(main_goal.sequence_number)
                )
            )

            result = ArtifactDiffService().diff_for_main_goal(
                workspace_id=main_goal.workspace_id,
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

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # fix #235: see GoalViewSet.partial_update() above — MainGoal is an
        # immutable-row-per-version chain (module docstring: "never mutated
        # in place"); editing means POST-ing a new manual/generated version.
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                message="MainGoals cannot be updated in place. POST a new version instead.",
            ),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # fix #235: see GoalViewSet.destroy() above — no delete semantics
        # exist for MainGoal (MainGoalService has no delete method).
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                message="MainGoals cannot be deleted.",
            ),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )



# ---------------------------------------------------------------------------
# IssueViewSet — COMP-AS-015 (REQ-L1-029)
# ---------------------------------------------------------------------------


class IssueViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Issue CRUD operations (REQ-L1-029).

    Delegates to IssueService (COMP-AS-015, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = IssueSerializer
    preset_endpoint_key = ""
    workflow_item_type = "Issue"
    attribute_item_type = "Issue"

    def _svc(self) -> IssueService:
        return IssueService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_issue(UUID(pk), ctx)
        return item.id, item.workspace_id

    # #915: Issue has no denormalized ``status`` column (Task 12); the shared
    # ``_current_status`` resolves the state from the workflow engine.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_issue(item_id, ctx)
        return {"issue": IssueSerializer(_issue_to_dict(updated)).data}

    @list_schema(status=True, search=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/issues/ — list all Issues in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            items = self._svc().list_issues(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                status=request.query_params.get("status") or None,
                search=request.query_params.get("search") or None,
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
            serialize_page=lambda page: IssueSerializer(
                [_issue_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/issues/{pk}/ — retrieve single Issue."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_issue(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(IssueSerializer(_issue_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/issues/ — create an Issue. Returns 201."""
        lang = detect_lang(request)
        ser = IssueSerializer(data=request.data)
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
            item = self._svc().create_issue(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                severity=data.get("severity", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "defect"),
                tags=data.get("tags"),
                due_date=data.get("due_date"),
                custom_fields=data.get("custom_fields"),
                # Datenmodell-Konsolidierung Phase 1: a new Issue always starts at the
                # workflow definition's initial_state. A client-supplied `status` is
                # ignored, not rejected, consistent with ADR-status-single-source.
            )
            self._apply_artifact_system_fields(request, "Issue", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(IssueSerializer(_issue_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/issues/{pk}/ — update an Issue. Returns 200."""
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=IssueSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = IssueSerializer(data=request.data, partial=True)
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
        # Task 20 review finding F-2: `due_date` is nullable, so an absent key
        # (leave unchanged) and an explicit `null` (clear it) must not
        # collapse onto the same `data.get("due_date")` — same class of bug as
        # Issue #409 above (see RequirementViewSet.partial_update). Forward it
        # only when the client actually sent the key; update_issue()'s
        # `_UNSET` sentinel default then means "leave unchanged" whenever it
        # is omitted here.
        extra_kwargs: dict[str, Any] = {}
        if "due_date" in data:
            extra_kwargs["due_date"] = data["due_date"]
        # REQ-L2-AS-037: only forward custom_fields when the client actually
        # sent it, so an unrelated PATCH does not wipe existing custom_fields
        # (same pattern as RequirementViewSet.partial_update).
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        try:
            ctx = get_auth_context(request)
            # REQ-165/REQ-166 (CR-08): `status` is intentionally NOT forwarded.
            # update_issue() has no status parameter — the WorkflowEngine is the
            # single source of truth once the item exists (ADR-status-single-
            # source.md); a client-sent status is ignored here and the lifecycle
            # state can only change via POST /api/v1/issues/{id}/transitions/.
            item = self._svc().update_issue(
                issue_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                severity=data.get("severity"),
                category=data.get("category"),
                tags=data.get("tags"),
                change_reason=data.get("change_reason"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                **extra_kwargs,
            )
            self._apply_artifact_system_fields(request, "Issue", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(IssueSerializer(_issue_to_dict(item)).data)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/issues/{pk}/diff/?from_version=0&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            issue = self._svc().get_issue(UUID(pk), ctx)

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(issue.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff_for_entity(
                entity_type="Issue",
                entity_id=UUID(pk),
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
        """GET /api/v1/issues/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions_for_entity(
                entity_type="Issue",
                entity_id=UUID(pk),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(result)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/issues/{pk}/ — soft-delete an Issue. Returns 204.

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
            self._svc().delete_issue(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)



# ---------------------------------------------------------------------------
# ChangeRequestViewSet — COMP-AS-021 (REQ-157)
# ---------------------------------------------------------------------------


class ChangeRequestViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Change Request CRUD + CCB workflow (REQ-157).

    Delegates to ChangeRequestService (COMP-AS-021).
    No business logic in this class (REQ-L3-RA001-004).

    Endpoints:
      GET    /api/v1/change-requests/?workspace_id=<id>
      POST   /api/v1/change-requests/
      GET    /api/v1/change-requests/{pk}/
      PATCH  /api/v1/change-requests/{pk}/
      DELETE /api/v1/change-requests/{pk}/
      POST   /api/v1/change-requests/{pk}/transition/   (legacy CCB shortcut)
      GET/POST /api/v1/change-requests/{pk}/transitions/  (generic engine, REQ-143)
      GET    /api/v1/change-requests/{pk}/workflow-history/  (REQ-144)
    """

    serializer_class = ChangeRequestSerializer
    preset_endpoint_key = ""
    workflow_item_type = "ChangeRequest"
    attribute_item_type = "ChangeRequest"

    def _svc(self) -> ChangeRequestService:
        return ChangeRequestService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_change_request(UUID(pk), ctx)
        return item.id, item.workspace_id

    # #915: ChangeRequest has no denormalized ``status`` column (Task 12); the
    # shared ``_current_status`` resolves the state from the workflow engine.

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_change_request(item_id, ctx)
        return {"change_request": ChangeRequestSerializer(_cr_to_dict(updated)).data}

    @list_schema(status=True, strict=True)
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/change-requests/?workspace_id=<id> — list CRs in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            status_filter = request.query_params.get("status")
            items = self._svc().list_change_requests(
                workspace_id=workspace_id,
                ctx=ctx,
                status_filter=status_filter,
                include_deleted=parse_include_deleted(request.query_params),
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(
                exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang
            )
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            serialize_page=lambda page: ChangeRequestSerializer(
                [_cr_to_dict(i) for i in page], many=True
            ).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/change-requests/{pk}/ — retrieve a single CR."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_change_request(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ChangeRequestSerializer(_cr_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/change-requests/ — create a CR. Returns 201."""
        lang = detect_lang(request)
        ser = ChangeRequestSerializer(data=request.data)
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
            # Epic #934 WS1: unlike every sibling ViewSet, CR create never ran
            # the resolved AttributeDefinition guard, so an out-of-rule extended
            # value was accepted over REST while MCP rejected it (V parity).
            definition_error = self._validate_attribute_definition(
                ctx,
                data.get("workspace_id"),
                dict(request.data) if isinstance(request.data, dict) else {},
                None,
            )
            if definition_error is not None:
                return definition_error
            item = self._svc().create_change_request(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                impact_assessment=data.get("impact_assessment", ""),
                change_reason=data.get("change_reason", ""),
                assigned_reviewer_id=data.get("assigned_reviewer_id"),
                # REQ-L2-AS-037: extended attributes from the serializer.
                custom_fields=data.get("custom_fields"),
                # #399: write-only prefill from the drift badge's "raise change
                # request" shortcut. The service validates the ids
                # workspace-/tenant-scoped and snapshots their "before" state.
                affected_item_ids=data.get("affected_item_ids"),
            )
            self._apply_artifact_system_fields(request, "ChangeRequest", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            ChangeRequestSerializer(_cr_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/change-requests/{pk}/ — update a CR. Returns 200."""
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=ChangeRequestSerializer,
            pk=pk,
            ctx=get_auth_context(request),
        )
        if invalid is not None:
            return invalid
        ser = ChangeRequestSerializer(data=request.data, partial=True)
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
            # REQ-L2-AS-037 / Epic #934 WS1: forward custom_fields only when the
            # client sent it, so an unrelated PATCH does not wipe the stored map
            # (same sentinel/presence pattern as RequirementViewSet).
            extra_kwargs: dict[str, Any] = {}
            if "custom_fields" in data:
                extra_kwargs["custom_fields"] = data["custom_fields"]
            item = self._svc().update_change_request(
                cr_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                impact_assessment=data.get("impact_assessment"),
                change_reason=data.get("change_reason"),
                assigned_reviewer_id=data.get("assigned_reviewer_id"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                **extra_kwargs,
            )
            self._apply_artifact_system_fields(request, "ChangeRequest", item, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ChangeRequestSerializer(_cr_to_dict(item)).data)

    @soft_delete_schema()
    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/change-requests/{pk}/ — soft-delete a CR. Returns 204.

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
            ctx = get_auth_context(request)
            self._svc().delete_change_request(
                UUID(pk), ctx, change_reason=change_reason
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/change-requests/{pk}/transition/ — CCB workflow transition.

        Body:
          {
            "target_status": "submitted" | "under_review" | "approved" | "rejected" | "implemented" | "draft",
            "change_reason": "..."   (required for submit and reject transitions)
          }

        The WorkflowEngine enforces role checks and change_reason requirements
        according to the ccb_approval preset (REQ-157).
        """
        lang = detect_lang(request)
        target_status = request.data.get("target_status")
        if not target_status:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_status is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        change_reason = request.data.get("change_reason", "") or ""
        try:
            ctx = get_auth_context(request)
            # AUD-2026-09-282: forward the client's If-Match/expected_version so
            # this special route is CAS-protected like the generic one; a stale
            # revision answers 409 instead of last-writer-wins.
            expected_version = self.resolve_expected_version_int(
                request, request.data
            )
            item = self._svc().transition_status(
                cr_id=UUID(pk),
                target_status=target_status,
                ctx=ctx,
                change_reason=change_reason or None,
                expected_version=expected_version,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(ChangeRequestSerializer(_cr_to_dict(item)).data)



# ---------------------------------------------------------------------------
# TestRunViewSet — REQ-L2-AS-030 / REQ-L2-AS-031
# ---------------------------------------------------------------------------


class TestRunViewSet(BaseEntityViewSet):
    """ViewSet for TestRun CRUD and result management.

    Endpoints:
      GET    /api/v1/test-runs/?workspace_id=<id>
      POST   /api/v1/test-runs/
      GET    /api/v1/test-runs/{id}/
      PATCH  /api/v1/test-runs/{id}/
      POST   /api/v1/test-runs/{id}/close/
      POST   /api/v1/test-runs/{id}/complete/             (GH-403, alias of close/)
      GET    /api/v1/test-runs/{id}/results/             (A.6, REQ-L1-035)
      POST   /api/v1/test-runs/{id}/results/
      POST   /api/v1/test-runs/{id}/results/bulk/

    Design note (#22): TestRuns are immutable audit records once created —
    DELETE is intentionally unsupported (see ``destroy`` below), by design,
    not an oversight. To finish a run, use ``POST .../close/`` instead of
    deleting it; the recorded results and their aggregate status remain
    available for audit/compliance even after closing.
    """

    serializer_class = TestRunSerializer
    preset_endpoint_key = ""

    def _svc(self) -> TestRunService:
        return TestRunService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/test-runs/?workspace_id=<id> — list test runs."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            items = self._svc().list_test_runs(workspace_id=workspace_id, ctx=ctx)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(request, items, _test_run_to_dict)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/test-runs/{id}/ — retrieve single test run."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_test_run(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(_test_run_to_dict(item))

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/ — create a test run. Returns 201."""
        lang = detect_lang(request)
        # Issue #460 finding 2: this was the last site where a malformed
        # workspace_id reached ``UUID()`` inside a ``try`` whose ``except
        # Exception`` mapped the resulting ValueError onto HTTP 500. Splitting
        # the two checks also stops a missing workspace_id from being reported
        # under the combined "workspace_id and name are required" wording.
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        # Kept as a dedicated, precisely-worded check (test_api_consistency_460
        # pins this exact message) rather than folding into the serializer
        # error below, whose "required"/"blank" wording differs.
        if not request.data.get("name") or not str(request.data.get("name")).strip():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="name is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        # SA-25: run the declared serializer for name/ci_job_id so ``name``
        # (a SanitizedCharField) is validated/sanitized (length cap, markup
        # rejection) instead of being read straight off request.data.
        # workspace_id keeps using parse_workspace_id above (issue #460 —
        # precise error message for a malformed id) and test_case_ids has no
        # serializer field (it is UUID()-validated below, matching the
        # pre-existing contract), so neither is touched here.
        ser = TestRunSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = ser.validated_data["name"]
        ci_job_id = ser.validated_data.get("ci_job_id", "")
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_test_run(
                workspace_id=workspace_id,
                name=name,
                ctx=ctx,
                ci_job_id=ci_job_id,
                test_case_ids=[UUID(str(tc_id)) for tc_id in request.data.get("test_case_ids", [])],
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item), status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/test-runs/{id}/ — update test run metadata. Returns 200."""
        lang = detect_lang(request)
        # SA-25: partial=True means DRF only validates/returns keys actually
        # present in the body, preserving the pre-existing "None = don't
        # touch this field" sentinel contract of update_test_run() while
        # still validating/sanitizing ``name`` when it is supplied.
        ser = TestRunSerializer(data=request.data, partial=True)
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
            ctx = get_auth_context(request)
            item = self._svc().update_test_run(
                test_run_id=UUID(pk),
                ctx=ctx,
                name=ser.validated_data.get("name"),
                ci_job_id=ser.validated_data.get("ci_job_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item))

    # ---- Actions ----

    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/close/ — close test run, recalc aggregate."""
        return self._close_or_complete(request, pk)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/complete/ — alias for ``close`` (GH-403).

        The 4-phase lifecycle documented for TestRuns (``created ->
        in_progress -> completed/failed -> archived``) has no ``completed``/
        ``archived`` status on the model itself (``TestRun.status`` choices
        are ``in_progress/passed/failed/partial/closed`` — see
        ``TestRunService._compute_aggregate_status``); ``close`` already
        performs the described "finalize the run" transition. This route
        exists so callers reaching for the advertised lifecycle verb
        (``/complete/``) do not 404 — it delegates to the exact same
        ``close_test_run`` call as ``/close/``, no separate logic to drift.
        """
        return self._close_or_complete(request, pk)

    def _close_or_complete(self, request: Request, pk: str) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().close_test_run(test_run_id=UUID(pk), ctx=ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item))

    @action(detail=True, methods=["get", "post"])
    def results(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """List or append per-TestCase execution results for a TestRun.

        REQ-L1-035 (A.6):
          GET  /api/v1/test-runs/{id}/results/ — list all results.
          POST /api/v1/test-runs/{id}/results/ — add a single result.

        GET response uses the spec'd shape: ``id``, ``testcase`` (nested
        id+title), ``result``, ``notes``, ``executed_at``, ``executed_by``,
        plus the legacy flat fields for backwards compatibility.
        """
        # GET — list results for this run
        if request.method == "GET":
            lang = detect_lang(request)
            try:
                ctx = get_auth_context(request)
                run = self._svc().get_test_run(UUID(pk), ctx)
            except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
                return _service_error_response(exc, lang)
            except ValueError:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )
            except Exception as exc:  # noqa: BLE001 — map any service error uniformly
                return _service_error_response(exc, lang)
            return Response([_test_run_result_to_dict(r) for r in run.results.all()])

        # POST — add a single result (existing behaviour). #851: validate with
        # TestRunResultSerializer (which now carries UnknownFieldRejectionMixin)
        # instead of reading request.data key by key, so a key no declared field
        # accepts is a 400 rather than a silent drop.
        lang = detect_lang(request)
        ser = TestRunResultSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = ser.validated_data
        try:
            ctx = get_auth_context(request)
            result = self._svc().add_result(
                test_run_id=UUID(pk),
                test_case_id=payload["test_case_id"],
                status=payload.get("status", "not_run"),
                ctx=ctx,
                message=payload.get("message", ""),
                duration_ms=payload.get("duration_ms"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_test_run_result_to_dict(result), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="results/bulk")
    def results_bulk(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/results/bulk/ — add multiple results (CI-friendly)."""
        # #851: TestRunResultBulkSerializer rejects unknown keys next to
        # ``results`` and inside each entry. The empty-array check stays: an
        # empty batch is valid to DRF but is still a client error here.
        lang = detect_lang(request)
        ser = TestRunResultBulkSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        results_data = ser.validated_data["results"]
        if not results_data:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="results array is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            created = self._svc().add_results_bulk(
                test_run_id=UUID(pk),
                results=results_data,
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            {"results": [_test_run_result_to_dict(r) for r in created], "count": len(created)},
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/test-runs/{id}/ — intentionally unsupported (#22).

        TestRuns are immutable audit records (REQ-L2-AS-030/031): once
        created, their history of executed results must remain available
        for traceability/compliance, so deletion is a permanent design
        decision, not a missing feature. Returns 405 with a message that
        points callers at ``POST .../close/`` — the correct way to finish a
        run instead of removing it.
        """
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                detect_lang(request),
                message=(
                    "Test runs are immutable audit records and cannot be "
                    "deleted. Use POST /api/v1/test-runs/{id}/close/ to "
                    "finish a run instead."
                ),
            ),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )



# ---------------------------------------------------------------------------
# MilestoneViewSet — planned review milestones (Plan B B6-T2, #879)
# PLAN-B-B6-T2: CRUD + baseline binding + audit freezing (ENT-B2 = a, no Measure)
# ---------------------------------------------------------------------------


class MilestoneViewSet(BaseEntityViewSet):
    """REST surface for the ``Milestone`` entity (Plan B B6-T2, #879).

    Delegates every write to :class:`application.milestone_service
    .MilestoneService` (ADR-01) — no business logic in this class
    (REQ-L3-RA001-004). A milestone plans a formal review (SRR/PDR/CDR/TRR/ORR)
    and is deliberately **not** an Artifact: no ``uid``, no workflow state, no
    trace-link endpoints (ENT-B2 = a — only ``Milestone``, no ``Measure``).

    Endpoints::

        GET    /api/v1/milestones/?workspace_id=<id>
        POST   /api/v1/milestones/
        GET    /api/v1/milestones/{id}/
        PATCH  /api/v1/milestones/{id}/
        DELETE /api/v1/milestones/{id}/
        POST   /api/v1/milestones/{id}/bind-baseline/   {"baseline_id": "<uuid>"}
        POST   /api/v1/milestones/{id}/record-audit/

    Contract highlights
    -------------------
    * **ETag / If-Match (KA-B-06).** ``Milestone.version`` is the
      optimistic-lock counter; GET, POST and PATCH emit it as ``ETag`` and a
      PATCH accepts ``If-Match``. A stale strong tag answers ``412``, a stale
      body ``expected_version`` ``409``, a malformed header ``400
      INVALID_IF_MATCH``. The two domain actions accept ``expected_version`` in
      the body (stale → ``409``): they guard the *entity* version, unlike the
      workflow actions that guard ``WorkflowItemState``.
    * **Cross-workspace binding.** ``bind-baseline`` refuses a baseline from
      another workspace with ``400 VALIDATION_ERROR``; the service never
      re-homes the row.
    * **Record, never a gate.** ``record-audit`` freezes the workspace's current
      SE-Auditor counts onto ``audit_snapshot``; open blockers do not refuse it
      (unlike the baseline gate, GH-513).
    * **Ordering (D-SORT).** The list is ordered by ``target_date, id`` in the
      service, so OFFSET/LIMIT pagination is deterministic.
    """

    serializer_class = MilestoneSerializer
    preset_endpoint_key = ""

    def _svc(self) -> MilestoneService:
        return MilestoneService()

    def _current(self, request: Request, pk: str) -> Any:
        """Load the current row for the ``If-Match`` tag-list comparison."""
        return self._svc().get(UUID(pk), get_auth_context(request))

    def _detail_response(self, item: Any, *, status_code: int = status.HTTP_200_OK):
        """Serialize *item* and attach its current ``ETag``."""
        return self.with_etag(
            Response(
                MilestoneSerializer(_milestone_to_dict(item)).data,
                status=status_code,
            ),
            item,
        )

    # ---------- Read ----------

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose milestones are listed.",
            )
        ]
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/milestones/?workspace_id=<id> — list milestones.

        Ordered by ``target_date``, then ``id`` (D-SORT), so OFFSET/LIMIT
        pagination is stable. A foreign or unknown workspace answers ``404``;
        milestones of another tenant are never listed.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"), lang
            )
            if error is not None:
                return error
            items = self._svc().list(workspace_id, ctx)
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
            serialize_page=lambda page: MilestoneSerializer(
                [_milestone_to_dict(item) for item in page], many=True
            ).data,
        )

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/milestones/{id}/ — retrieve a milestone.

        The response carries ``ETag: "<version>"`` for a subsequent conditional
        PATCH. An unknown id (or one of another tenant) answers ``404``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return self._detail_response(item)

    # ---------- Create ----------

    @extend_schema(parameters=[_ETAG_RESPONSE_HEADER])
    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/milestones/ — create a milestone. Returns 201.

        ``workspace_id``, ``name``, ``review_type`` and ``target_date`` are
        required; ``status`` defaults to ``planned``. An optional
        ``baseline_id`` must belong to the same workspace. The 201 carries the
        new ``ETag`` so a client can PATCH conditionally without a second GET.
        """
        lang = detect_lang(request)
        ser = MilestoneSerializer(data=request.data)
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
            item = self._svc().create(
                ctx,
                workspace_id=data["workspace_id"],
                name=data["name"],
                review_type=data["review_type"],
                target_date=data["target_date"],
                status=data.get("status", "planned"),
                baseline_id=data.get("baseline_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._detail_response(item, status_code=status.HTTP_201_CREATED)

    # ---------- Update ----------

    @extend_schema(
        parameters=[_IF_MATCH_PARAMETER, _ETAG_RESPONSE_HEADER],
        responses={
            200: MilestoneSerializer,
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/milestones/{id}/ — update a milestone. Returns 200.

        ``If-Match`` is evaluated first (400 ``INVALID_IF_MATCH`` for a
        malformed header), then the service compares the version (412 for a
        stale strong ``If-Match``, 409 for a stale body ``expected_version``).
        ``workspace_id`` is immutable and ``baseline_id`` is not a PATCH field:
        rebinding goes through ``POST /{id}/bind-baseline/``.
        """
        lang = detect_lang(request)
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        ser = MilestoneSerializer(data=request.data, partial=True)
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

        if "baseline_id" in data:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {
                            "field": "baseline_id",
                            "errors": [
                                "baseline_id is not a PATCH field; use "
                                "POST /api/v1/milestones/{id}/bind-baseline/."
                            ],
                        }
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "workspace_id" in data:
            try:
                current = self._current(request, pk)
            except (NotFoundError, PermissionDeniedError) as exc:
                return _service_error_response(exc, lang)
            except ValueError:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )
            if str(data["workspace_id"]) != str(current.workspace_id):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[
                            {
                                "field": "workspace_id",
                                "errors": [
                                    "workspace_id is immutable; a milestone "
                                    "cannot be moved to another workspace."
                                ],
                            }
                        ],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            ctx = get_auth_context(request)
            item = self._svc().update(
                UUID(pk),
                ctx,
                name=data.get("name"),
                review_type=data.get("review_type"),
                target_date=data.get("target_date"),
                status=data.get("status"),
                change_reason=data.get("change_reason"),
                expected_version=self.resolve_expected_version(
                    request, data, current=lambda: self._current(request, pk)
                ),
            )
        except (InvalidIfMatch, IfMatchMismatch) as exc:
            return self.if_match_error(request, exc)
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._detail_response(item)

    # ---------- Delete ----------

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/milestones/{id}/ — hard-delete a milestone. Returns 204.

        A milestone is a plain planning row (no Artifact, no append-only
        child), so it is removed instead of being soft-deleted. A baseline that
        the milestone references stays untouched; ``Milestone.baseline`` is
        ``PROTECT`` in the other direction. ``change_reason`` may be sent in the
        body or as ``?change_reason=``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete(
                UUID(pk), ctx, change_reason=parse_change_reason(request)
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
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ---------- Domain actions ----------

    @extend_schema(
        request=MilestoneBindBaselineSerializer,
        responses={200: MilestoneSerializer},
        parameters=[_ETAG_RESPONSE_HEADER],
    )
    @action(detail=True, methods=["post"], url_path="bind-baseline")
    def bind_baseline(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/milestones/{id}/bind-baseline/ — bind a baseline.

        ``{"baseline_id": "<uuid>"}`` is required; the baseline must belong to
        the milestone's own workspace (otherwise ``400 VALIDATION_ERROR``). An
        optional ``expected_version`` body field guards the entity version
        (stale → ``409 CONFLICT``), and the response carries the new ``ETag``.
        """
        lang = detect_lang(request)
        ser = MilestoneBindBaselineSerializer(data=request.data)
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
            item = self._svc().bind_baseline(
                UUID(pk),
                data["baseline_id"],
                ctx,
                change_reason=data.get("change_reason"),
                expected_version=data.get("expected_version"),
            )
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._detail_response(item)

    @extend_schema(
        request=MilestoneRecordAuditSerializer,
        responses={200: MilestoneSerializer},
        parameters=[_ETAG_RESPONSE_HEADER],
    )
    @action(detail=True, methods=["post"], url_path="record-audit")
    def record_audit(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/milestones/{id}/record-audit/ — freeze the audit counts.

        Runs the SE-Auditor for the milestone's workspace and stores
        ``{tier, counts: {total, blockers, warnings}, run_at}`` in
        ``audit_snapshot``. Recording is a record, never a gate, so open
        blockers do not refuse it. An optional ``expected_version`` body field
        guards the entity version (stale → ``409 CONFLICT``).
        """
        lang = detect_lang(request)
        ser = MilestoneRecordAuditSerializer(data=request.data)
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
            item = self._svc().record_audit(
                UUID(pk),
                ctx,
                change_reason=data.get("change_reason"),
                expected_version=data.get("expected_version"),
            )
        except OptimisticLockError as exc:
            return self.optimistic_lock_response(request, exc, lang)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._detail_response(item)
