"""
COMP-RA-001 HttpEndpointController — views_trace_baseline — extracted from rest_api/views.py (content-sensible split; public import surface preserved by the facade)..

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
    _service_error_response,
)




# ---------------------------------------------------------------------------
# TraceLinkViewSet
# ---------------------------------------------------------------------------


class TraceLinkViewSet(BaseEntityViewSet):
    """ViewSet for TraceLink CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TraceLinkSerializer
    preset_endpoint_key = ""
    # Plan E E2.3: trace links are immutable (no update semantics in the
    # spec), so the detail route publishes no PATCH at all. This is the single
    # authority for that: deleting the old ``partial_update`` stub is not
    # enough on its own — without the restriction DRF would answer 405 from a
    # missing handler anyway, but the OpenAPI document would still advertise
    # PATCH (it derives operations from the router's method map). With the
    # route removed from ``http_method_names`` the schema and the runtime agree.
    http_method_names = ["get", "post", "delete", "head", "options"]
    # Fix #571 (reopen): clients render the traceability graph from the *whole*
    # link set, so they walk every page. 500/page instead of the shared 100
    # turns ~1980 links from 20 serial round-trips into 4 — see
    # TraceLinkPagination for why the ceiling is safe to raise here only.
    pagination_class = TraceLinkPagination

    def _svc(self) -> TraceLinkService:
        return TraceLinkService()

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/trace-links/bulk/ — all-or-nothing allocation (P3.5).

        Body: ``{"items": [{"requirement_id": uuid, "element_id": uuid}]}``.
        One failure rolls the whole batch back; nothing is written.
        """
        from django.db import transaction

        lang = detect_lang(request)
        items = request.data.get("items") if isinstance(request.data, dict) else None
        if not isinstance(items, list) or not items:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="Body must be {\"items\": [{requirement_id, element_id}]}.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            service = self._svc()
            with transaction.atomic():
                results = []
                for item in items:
                    link = service.allocate(
                        requirement_id=UUID(str(item["requirement_id"])),
                        architecture_element_id=UUID(str(item["element_id"])),
                        ctx=ctx,
                    )
                    results.append(
                        {
                            "requirement_id": str(item["requirement_id"]),
                            "element_id": str(item["element_id"]),
                            "trace_link_id": str(link.id),
                        }
                    )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except (KeyError, TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"allocated": results}, status=status.HTTP_201_CREATED)

    def _list_workspace_links(
        self,
        request: Request,
        svc: TraceLinkService,
        workspace_id: Any,
        ctx: Any,
        *,
        link_type: str | None = None,
    ) -> Response:
        """List every TraceLink whose source lives in the workspace.

        Fix #264 (Befund B): this branch used to return an unconditional
        empty page, so the endpoint reported ``count: 0`` for every workspace
        no matter what was stored; ``list_links_for_workspace_queryset`` now
        backs it.

        Fix #571: the branch used to fetch *every* matching TraceLink
        (``select_related`` on both endpoints, embedding vector included) and
        build a dict for each one, all before pagination ever got a chance to
        slice the list. At ~2000 links in a workspace that OOM-killed the
        worker regardless of the requested ``page_size`` (512 MB container
        limit). Pagination now runs on the lazy queryset first
        (``LIMIT``/``OFFSET`` pushed down to the DB), and titles/dicts are
        only built for the current page.

        INT-05 (AUD-2026-09-073): ``paginate_queryset`` raises DRF's
        ``NotFound`` for an invalid ``page`` (0/abc/out-of-range). The caller
        re-raises it so it reaches the framework as a **404** instead of
        being rewritten to a 500.
        """
        links_qs = svc.list_links_for_workspace_queryset(
            workspace_id=workspace_id, ctx=ctx, link_type=link_type
        )
        page = self.paginator.paginate_queryset(links_qs, request, view=self)
        if page is not None:
            titles = _resolve_artifact_titles(
                [tl.source_id for tl in page]
                + [tl.target_id for tl in page]
            )
            results = [
                TraceLinkSerializer(_tracelink_to_dict(tl, titles)).data
                for tl in page
            ]
            return self.paginator.get_paginated_response(results)
        # Pagination disabled for this request — still avoid the
        # eager select_related/embedding fetch, but materialize the
        # (still filtered) queryset only here.
        links = list(links_qs)
        titles = _resolve_artifact_titles(
            [tl.source_id for tl in links] + [tl.target_id for tl in links]
        )
        return Response(
            [
                TraceLinkSerializer(_tracelink_to_dict(tl, titles)).data
                for tl in links
            ]
        )

    def _list_artifact_links(
        self,
        svc: TraceLinkService,
        artifact_id_str: str,
        ctx: Any,
        *,
        link_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List upstream + downstream TraceLinks for one artifact.

        Fix (systemaudit 2026-08-29, Bug 1): ``query_trace_links()`` returns
        NeighborResult projections without the TraceLink's own primary key —
        this branch used to paper over that with a helper (formerly
        `_neighbor_to_dict`, removed) that synthesized a deterministic uuid5
        from the endpoint pair. That synthetic id was never a real TraceLink
        row, so DELETE /tracelinks/<id>/ against it 404'd ("TraceLink <uuid>
        not found") in every UI that lists links via ?artifact_id=
        (TraceLinkPanel, ReqTraceLinkPanel). ``list_links_for_entity()``
        returns the persisted TraceLink ORM rows (real .id) instead.

        The endpoint-echo contract from #512 must be kept as-is here: the
        frontend classifies each item as upstream/downstream by comparing this
        item's own endpoint against the *raw* artifact_id it queried with
        (TraceLinkPanel.tsx: `l.target_id === artifactId` / `l.source_id ===
        artifactId`) — not the resolved Artifact id `tl.source_id`/
        `tl.target_id` actually stored on the row (which differ whenever the
        caller queried by entity id, e.g. an ADR's own `.id`, per the #512
        comment on resolveArtifactRef below). Returning the raw ORM
        `tl.source_id`/`tl.target_id` unmodified here (as
        `_tracelink_to_dict` does) broke that classification — both
        "upstream" and "downstream" silently rendered zero links because
        neither endpoint id matched what the frontend queried with. Only the
        TraceLink's own `id` needed to become real; the endpoint-echo shape
        must stay exactly like before.
        """
        artifact_id = UUID(artifact_id_str)
        items: list[dict[str, Any]] = []
        seen_ids: set = set()
        for direction in ("upstream", "downstream"):
            try:
                results = svc.list_links_for_entity(
                    entity_id=artifact_id,
                    direction=direction,
                    ctx=ctx,
                    link_type=link_type,
                )
                for tl in results:
                    if tl.id in seen_ids:
                        # A self-link (source == target == artifact_id)
                        # would otherwise be listed twice (once per
                        # direction).
                        continue
                    seen_ids.add(tl.id)
                    if direction == "upstream":
                        item_source_id = str(tl.source_id)
                        item_target_id = str(artifact_id)
                    else:
                        item_source_id = str(artifact_id)
                        item_target_id = str(tl.target_id)
                    items.append(
                        {
                            "id": str(tl.id),
                            "source_id": item_source_id,
                            "target_id": item_target_id,
                            # #1270: same unambiguous aliases as _tracelink_to_dict.
                            "source_artifact_id": item_source_id,
                            "target_artifact_id": item_target_id,
                            "link_type": tl.link_type,
                            "version": tl.version,
                            "created_at": tl.created_at,
                            # Q1.6: same three keys as _tracelink_to_dict —
                            # this branch builds its own dict for the
                            # endpoint-echo contract above, so it has to
                            # repeat them or ?artifact_id= would be the one
                            # listing without a rationale.
                            "rationale": getattr(tl, "rationale", "") or "",
                            "suspect_flagged_at": getattr(
                                tl, "suspect_flagged_at", None
                            ),
                            "suspect_source_change": getattr(
                                tl, "suspect_source_change", None
                            ),
                            "source_title": "",
                            "target_title": "",
                            "source_type": "",
                            "target_type": "",
                            "source_is_outdated": False,
                            "target_is_outdated": False,
                        }
                    )
            except Exception:
                # No links in this direction is the common case. An
                # unresolvable artifact_id also lands here — log it so a
                # bad id is not indistinguishable from "no links" (#264).
                logger.debug(
                    "TraceLink %s query failed for artifact=%s",
                    direction,
                    artifact_id,
                    exc_info=True,
                )
        return items

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose links are listed (or filter).",
            ),
            OpenApiParameter(
                "artifact_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Return the upstream + downstream links attached to this "
                    "artifact instead of the workspace-wide list."
                ),
            ),
            OpenApiParameter(
                "link_type",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Only return links of this type (e.g. `verifies`, "
                    "`documented-in`). Filters both the workspace-wide and the "
                    "per-artifact listing (R-X-1, Plan F F2-T5)."
                ),
            ),
        ]
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/?workspace_id=<id>[&artifact_id=<id>][&link_type=<type>]

        When artifact_id is provided: returns upstream + downstream links for that artifact.
        When only workspace_id is provided: returns every link whose source
        lives in that workspace.

        ``link_type`` narrows either branch (R-X-1): before Plan F F2-T5 the
        parameter was silently ignored, so a client filtering by ``verifies``
        saw every link and could not compute coverage from this endpoint.

        Fix #264 (Befund B): the workspace-level branch used to return an
        unconditional empty page, so this endpoint reported ``count: 0`` for
        every workspace no matter what was stored. Anyone verifying a freshly
        created trace link this way concluded the write had been silently
        dropped. TraceLinkService.list_links_for_workspace now backs it.

        Fix #571: the workspace-level branch used to fetch *every* matching
        TraceLink (via ``list_links_for_workspace``, ``select_related`` on
        both endpoints, embedding vector included) and build a dict for each
        one, all before pagination ever got a chance to slice the list. At
        ~2000 links in a workspace that OOM-killed the worker regardless of
        the requested ``page_size`` (512 MB container limit). Pagination now
        runs on the lazy queryset first (``LIMIT``/``OFFSET`` pushed down to
        the DB), and titles/dicts are only built for the current page.
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

            artifact_id_str = request.query_params.get("artifact_id")
            link_type = request.query_params.get("link_type") or None
            svc = self._svc()

            if not artifact_id_str:
                return self._list_workspace_links(
                    request, svc, workspace_id, ctx, link_type=link_type
                )

            items = self._list_artifact_links(
                svc, artifact_id_str, ctx, link_type=link_type
            )
            # REQ-002: batch-resolve titles for all unique artifact IDs so the
            # frontend can display human-readable labels without extra requests.
            _enrich_tracelink_titles(items)
        except NotFound:
            # INT-05 (AUD-2026-09-073): DRF's ``NotFound`` from the paginator is
            # a legitimate 404 — re-raise it so DRF's exception handler renders
            # the status, instead of the broad handlers below converting it to a
            # 500. ``NotFound`` here can only come from pagination (the service
            # raises ``NotFoundError``, which is a separate class).
            raise
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: TraceLinkSerializer(item).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/{id}/ (and the ``trace-links`` alias).

        Plan E E2.3: this handler used to answer an unconditional 404 because
        the service layer had no read-by-id. It now resolves the link through
        :meth:`TraceLinkService.get_trace_link` and renders the same dict the
        list/create branches use.

        QR-S20: the route is fenced on the link's **source** workspace
        (ADR-011/``resource_scope``), so a caller may legitimately reach a link
        whose target lives in a workspace they cannot read. The target title is
        cross-workspace metadata and is therefore blanked to ``null`` unless
        the caller holds READ on the target workspace; the target UID fields
        (none exist on this endpoint today) follow the same rule and would be
        rendered as ``"—"``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            link = self._svc().get_trace_link(UUID(str(pk)), ctx)
        except ValueError:
            # Unreachable for HTTP traffic (``BaseEntityViewSet.initial``
            # rejects malformed UUID path segments with a 400), kept for the
            # direct-call shape used by unit tests — same idiom as ``destroy``.
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        titles = _resolve_artifact_titles([link.source_id, link.target_id])
        payload = _tracelink_to_dict(link, titles=titles)
        if not _caller_may_read_workspace(_workspace_of_artifact(link.target_id), ctx):
            payload["target_title"] = None
        return Response(TraceLinkSerializer(payload).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = TraceLinkSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_trace_link(
                source_id=UUID(str(data["source_id"])),
                target_id=UUID(str(data["target_id"])),
                link_type=data["link_type"],
                ctx=ctx,
                # Q1.6: the serializer declares rationale as writable, so
                # dropping it here would answer 201 while discarding it.
                rationale=data.get("rationale", ""),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        # REQ-002: resolve titles for both endpoints of the created link.
        titles = _resolve_artifact_titles([item.source_id, item.target_id])
        return Response(
            TraceLinkSerializer(_tracelink_to_dict(item, titles=titles)).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/tracelinks/{id}/[?confirm_anchor_count=n].

        Plan F F3-T7 / I-3: a link carrying inline anchors answers
        ``409 ANCHORS_PRESENT`` with ``details.count`` until the caller repeats
        the request with the exact count in ``confirm_anchor_count``. The
        count is validated as a non-negative integer; a missing parameter is
        the "no confirmation seen" case and is handled by the service.
        """
        lang = detect_lang(request)
        raw_count = request.query_params.get("confirm_anchor_count")
        confirm_anchor_count: int | None = None
        if raw_count is not None:
            try:
                confirm_anchor_count = int(raw_count)
            except (TypeError, ValueError):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[
                            {
                                "field": "confirm_anchor_count",
                                "errors": ["Must be an integer."],
                            }
                        ],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if confirm_anchor_count < 0:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        details=[
                            {
                                "field": "confirm_anchor_count",
                                "errors": ["Must be zero or greater."],
                            }
                        ],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            ctx = get_auth_context(request)
            self._svc().delete_trace_link(
                UUID(pk), ctx, confirm_anchor_count=confirm_anchor_count
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/trace-links/{id}/confirm/

        Accept an agent-proposed link: clears ``proposed_by``/``proposed_at``
        so it becomes an ordinary, human-owned edge (spec §5). Idempotent.

        Security review M2: ``TraceLinkService.confirm_proposed_link`` existed
        with no caller at all — the proposal could be created but never
        accepted through any interface.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            link = self._svc().confirm_proposed_link(UUID(pk), ctx)
        except (ValueError, TypeError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(
            TraceLinkSerializer(_tracelink_to_dict(link)).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="discard")
    def discard(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/trace-links/{id}/discard/

        Reject an agent-proposed link by deleting it (spec §5). Only valid on
        a link that is still a proposal; a confirmed link goes through
        ``DELETE`` instead. Counterpart to :meth:`confirm`, same M2 finding.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().discard_proposed_link(UUID(pk), ctx)
        except (ValueError, TypeError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="similar")
    def similar(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/similar/?tracelink_id=<uuid>&limit=10

        REQ-L2-VS-004: Returns the top-N trace links most similar to the query
        link by cosine distance over pgvector embeddings. Returns 400 when the
        link has no embedding, 503 when pgvector is unavailable.

        T-A2-8: the similarity query is scoped to the workspace of the query
        link's **source artifact**, resolved server-side. A client-supplied
        ``workspace_id`` is deliberately not read: it is not an authority. The
        derived workspace is gated on READ, and a link the caller cannot read
        is indistinguishable from a missing one (404) -- the pre-change shape
        answered with a tenant-wide neighbour list instead.
        """
        lang = detect_lang(request)

        tracelink_id_str = request.query_params.get("tracelink_id")
        if not tracelink_id_str:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="tracelink_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tracelink_id = UUID(tracelink_id_str)
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="tracelink_id must be a valid UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            # T-A2-8: scope from the row, never from the request. The READ
            # gate keeps a link in a workspace the caller has no standing in
            # from answering -- with the scope missing the underlying query
            # would fall back to an unscoped (tenant-wide) pgvector result.
            link = svc.get_trace_link(tracelink_id, ctx)
            workspace_id = _workspace_of_artifact(link.source_id)
            if workspace_id is None or not _caller_may_read_workspace(
                workspace_id, ctx
            ):
                raise NotFoundError(f"TraceLink {tracelink_id} not found")
            results = svc.find_similar_trace_links(
                trace_link_id=tracelink_id,
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

        serialized = [SimilarTraceLinkSerializer(r).data for r in results]
        return Response(serialized)

    # -----------------------------------------------------------------------
    # Read-model graph queries (REQ-L2-TE-019) — recursive CTE endpoints.
    # -----------------------------------------------------------------------

    @action(detail=False, methods=["get"], url_path="impact")
    def impact(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/impact/?artifact_id=<uuid>[&direction=&max_depth=&link_types=&limit=]

        Returns all artifacts reachable from *artifact_id* via TraceLinks.
        """
        from traceability.service import (
            DEFAULT_LIMIT,
            DEFAULT_MAX_DEPTH,
            MAX_DEPTH_CAP,
            MAX_LIMIT,
            impact_analysis,
        )

        lang = detect_lang(request)
        artifact_id_str = request.query_params.get("artifact_id")
        if not artifact_id_str:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="artifact_id is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        direction = request.query_params.get("direction", "outgoing")
        if direction not in ("outgoing", "incoming", "both"):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="direction must be outgoing|incoming|both"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            max_depth = int(request.query_params.get("max_depth", DEFAULT_MAX_DEPTH))
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="max_depth and limit must be integers"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_depth > MAX_DEPTH_CAP:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=f"max_depth must be <= {MAX_DEPTH_CAP}"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = min(max(limit, 1), MAX_LIMIT)
        link_types_raw = request.query_params.get("link_types")
        link_types = (
            [lt.strip() for lt in link_types_raw.split(",") if lt.strip()]
            if link_types_raw
            else None
        )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            resolved_id = svc._resolve_artifact_id(UUID(artifact_id_str))
            nodes = impact_analysis(
                artifact_id=resolved_id,
                workspace_id=None,
                tenant_id=ctx.tenant_id,
                link_types=link_types,
                direction=direction,
                max_depth=max_depth,
                limit=limit,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceLinkViewSet.impact: unhandled exception")
            return _service_error_response(exc, lang)

        serialized = [ImpactNodeSerializer(n.to_dict()).data for n in nodes]
        response = Response(serialized)
        if len(nodes) >= limit:
            response["X-Result-Truncated"] = "true"
        return response

    @action(detail=False, methods=["get"], url_path="path")
    def path(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/path/?source_id=<uuid>&target_id=<uuid>[&max_depth=]

        Returns the shortest path(s) between two artifacts, or 404 if none.
        """
        from traceability.service import DEFAULT_MAX_DEPTH, MAX_DEPTH_CAP, find_path

        lang = detect_lang(request)
        source_id_str = request.query_params.get("source_id")
        target_id_str = request.query_params.get("target_id")
        if not source_id_str or not target_id_str:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="source_id and target_id are required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            max_depth = int(request.query_params.get("max_depth", DEFAULT_MAX_DEPTH))
        except ValueError:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="max_depth must be an integer"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_depth > MAX_DEPTH_CAP:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=f"max_depth must be <= {MAX_DEPTH_CAP}"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            resolved_source = svc._resolve_artifact_id(UUID(source_id_str))
            resolved_target = svc._resolve_artifact_id(UUID(target_id_str))
            paths = find_path(
                source_id=resolved_source,
                target_id=resolved_target,
                workspace_id=None,
                tenant_id=ctx.tenant_id,
                max_depth=max_depth,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceLinkViewSet.path: unhandled exception")
            return _service_error_response(exc, lang)

        if paths is None:
            return Response(
                build_error_response("NOT_FOUND", lang, message="No path between the given artifacts"),
                status=status.HTTP_404_NOT_FOUND,
            )
        serialized = [TracePathSerializer(p.to_dict()).data for p in paths]
        return Response(serialized)

    @action(detail=False, methods=["get"], url_path="cycles")
    def cycles(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/cycles/?workspace_id=<uuid>[&limit=]

        Returns cycles detected in the workspace trace graph (list of id lists).
        """
        from traceability.service import detect_cycles

        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"),
            lang,
        )
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            cycles = detect_cycles(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceLinkViewSet.cycles: unhandled exception")
            return _service_error_response(exc, lang)

        return Response({"cycles": cycles, "count": len(cycles)})



# ---------------------------------------------------------------------------
# TraceabilityViewSet (read-model graph queries) — REQ-L2-TE-019
# ---------------------------------------------------------------------------


class TraceabilityViewSet(viewsets.GenericViewSet):
    """Read-only traceability graph queries (REQ-L2-TE-019).

    Exposes the same impact / path / cycles read-model queries as the
    ``/tracelinks/`` actions under a dedicated ``/traceability/`` namespace.
    The ``/tracelinks/`` CRUD ViewSet keeps its own impact/path/cycles actions
    for backward compatibility.
    """

    serializer_class = ImpactNodeSerializer

    def _svc(self) -> TraceLinkService:
        return TraceLinkService()

    @action(detail=False, methods=["get"], url_path="impact")
    def impact(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/traceability/impact/?artifact_id=<uuid>[&direction=&max_depth=&link_types=&limit=]

        Returns all artifacts reachable from *artifact_id* via TraceLinks.
        """
        from traceability.service import (
            DEFAULT_LIMIT,
            DEFAULT_MAX_DEPTH,
            MAX_DEPTH_CAP,
            MAX_LIMIT,
            impact_analysis,
        )

        lang = detect_lang(request)
        artifact_id_str = request.query_params.get("artifact_id")
        if not artifact_id_str:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="artifact_id is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        direction = request.query_params.get("direction", "outgoing")
        if direction not in ("outgoing", "incoming", "both"):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="direction must be outgoing|incoming|both"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            max_depth = int(request.query_params.get("max_depth", DEFAULT_MAX_DEPTH))
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="max_depth and limit must be integers"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_depth > MAX_DEPTH_CAP:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=f"max_depth must be <= {MAX_DEPTH_CAP}"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = min(max(limit, 1), MAX_LIMIT)
        link_types_raw = request.query_params.get("link_types")
        link_types = (
            [lt.strip() for lt in link_types_raw.split(",") if lt.strip()]
            if link_types_raw
            else None
        )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            resolved_id = svc._resolve_artifact_id(UUID(artifact_id_str))
            nodes = impact_analysis(
                artifact_id=resolved_id,
                workspace_id=None,
                tenant_id=ctx.tenant_id,
                link_types=link_types,
                direction=direction,
                max_depth=max_depth,
                limit=limit,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceabilityViewSet.impact: unhandled exception")
            return _service_error_response(exc, lang)

        serialized = [ImpactNodeSerializer(n.to_dict()).data for n in nodes]
        response = Response(serialized)
        if len(nodes) >= limit:
            response["X-Result-Truncated"] = "true"
        return response

    @action(detail=False, methods=["get"], url_path="path")
    def path(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/traceability/path/?source_id=<uuid>&target_id=<uuid>[&max_depth=]

        Returns the shortest path(s) between two artifacts, or 404 if none.
        """
        from traceability.service import DEFAULT_MAX_DEPTH, MAX_DEPTH_CAP, find_path

        lang = detect_lang(request)
        source_id_str = request.query_params.get("source_id")
        target_id_str = request.query_params.get("target_id")
        if not source_id_str or not target_id_str:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="source_id and target_id are required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            max_depth = int(request.query_params.get("max_depth", DEFAULT_MAX_DEPTH))
        except ValueError:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="max_depth must be an integer"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_depth > MAX_DEPTH_CAP:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=f"max_depth must be <= {MAX_DEPTH_CAP}"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            resolved_source = svc._resolve_artifact_id(UUID(source_id_str))
            resolved_target = svc._resolve_artifact_id(UUID(target_id_str))
            paths = find_path(
                source_id=resolved_source,
                target_id=resolved_target,
                workspace_id=None,
                tenant_id=ctx.tenant_id,
                max_depth=max_depth,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceabilityViewSet.path: unhandled exception")
            return _service_error_response(exc, lang)

        if paths is None:
            return Response(
                build_error_response("NOT_FOUND", lang, message="No path between the given artifacts"),
                status=status.HTTP_404_NOT_FOUND,
            )
        serialized = [TracePathSerializer(p.to_dict()).data for p in paths]
        return Response(serialized)

    @action(detail=False, methods=["get"], url_path="cycles")
    def cycles(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/traceability/cycles/?workspace_id=<uuid>[&limit=]

        Returns cycles detected in the workspace trace graph (list of id lists).
        """
        from traceability.service import detect_cycles

        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"),
            lang,
        )
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            cycles = detect_cycles(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceabilityViewSet.cycles: unhandled exception")
            return _service_error_response(exc, lang)

        return Response({"cycles": cycles, "count": len(cycles)})

    @action(detail=False, methods=["get"], url_path="resolve")
    def resolve(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/traceability/resolve/?artifact_ids=<uuid>[,<uuid>...]

        Task 3.2a (UI-Konzept Vollrollout): resolves one or more Artifact ids
        to their backing domain-entity ``(entity_type, entity_id)``, across
        every Generic Artifact Model type (Requirement, ArchitectureElement,
        StakeholderNeed, TestCase, Adr, Risk, Issue, Goal, MainGoal). The
        trace graph (TraceLink, ``impact`` above) is keyed by Artifact id
        while detail routes take domain-entity ids — this closes that gap for
        every type at once, instead of each frontend page maintaining its own
        ad-hoc lookup against an already-loaded list.

        Read-only and tenant-scoped exactly like ``impact``/``path``/``cycles``
        above (see ``traceability.service.resolve_artifacts`` docstring for
        the tenant-isolation argument in detail).

        Unresolvable ids (unknown, belonging to another tenant, or a deleted
        domain row) are never an error: they come back with
        ``resolved: false`` and null entity fields, distinguishing "batch call
        failed" (4xx/5xx) from "this particular id is not openable" (200 with
        ``resolved: false``) — the latter is the caller's (frontend
        ``isOpenable``) responsibility to react to, not this endpoint's.
        """
        from traceability.service import RESOLVE_BATCH_LIMIT, resolve_artifacts

        lang = detect_lang(request)
        raw = request.query_params.get("artifact_ids")
        if not raw:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="artifact_ids is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        id_strs = [s.strip() for s in raw.split(",") if s.strip()]
        if not id_strs:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="artifact_ids is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(id_strs) > RESOLVE_BATCH_LIMIT:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=f"artifact_ids must contain at most {RESOLVE_BATCH_LIMIT} entries",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            parsed_ids = [UUID(s) for s in id_strs]
        except ValueError:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="artifact_ids must be valid UUIDs"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            svc._set_tenant_context(ctx)
            resolutions = resolve_artifacts(parsed_ids, tenant_id=ctx.tenant_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("TraceabilityViewSet.resolve: unhandled exception")
            return _service_error_response(exc, lang)

        serialized = [ResolvedArtifactSerializer(r.to_dict()).data for r in resolutions]
        return Response(serialized)



# ---------------------------------------------------------------------------
# BaselineViewSet (Extended-preset gate)
# ---------------------------------------------------------------------------


class _BaselineAutoSchema(ReqLoAutoSchema):
    """#1380: keep the shared ``list`` schema honest for both of its routes.

    ``BaselineViewSet.list`` serves the flat ``/api/v1/baselines/`` route *and*
    the nested ``/api/v1/workspaces/{workspace_pk}/baselines/`` route (issue
    #49). Only the flat one needs ``?workspace_id=`` — without it the preset
    gate falls back to the tenant id and answers 404 in every preset — while
    the nested route takes the workspace from its path and ignores the query
    value. The parameter is declared once on the handler, so the nested
    operation must not publish it as a requirement it does not have.

    A drf-spectacular ``AutoSchema`` sees ``self.path``/``self.method`` (set in
    ``get_operation`` before the parameters are assembled), which is the only
    place where the two routes can still be told apart for a shared handler.
    """

    def _get_parameters(self) -> list[dict[str, Any]]:
        parameters = super()._get_parameters()
        # ``getattr`` rather than plain access: both attributes are set by
        # ``AutoSchema.get_operation`` before this hook runs, but a defensive
        # read keeps an upstream refactor from crashing schema generation for
        # the whole API over a documentation-only concern.
        if getattr(self, "method", "") == "GET" and "/workspaces/" in getattr(
            self, "path", ""
        ):
            # GH-1396 review finding F8: drop the *query* requirement only. The
            # nested route carries the workspace in its path as
            # ``{workspace_pk}``; a future route reusing the name
            # ``workspace_id`` as a PATH parameter would otherwise lose its
            # required path segment from the document (a generated client
            # would then build a request to a different, incomplete URL).
            # ``.get`` keeps a parameter dict without an ``in`` key — such an
            # entry is not a query parameter, so it must be kept.
            return [
                parameter
                for parameter in parameters
                if not (
                    parameter.get("in") == "query"
                    and parameter.get("name") == "workspace_id"
                )
            ]
        return parameters



# #1380: the collection and detail routes were advertised unconditionally while
# ``PresetGateMixin._guard_preset`` answers a bare ``Http404`` (rendered as the
# opaque route-miss envelope by ``handler404``) whenever the workspace's active
# preset does not enable ``preset_endpoint_key = "baselines"``. Every
# ``list``/``retrieve``/``create`` declaration therefore carries this one
# response instead of the generic "Resource not found." blanket the
# postprocessing hook injects: a generated client can now see that a 404 here
# is a *visibility* answer, not a missing-row answer. Status, error code and
# envelope shape are shared by all three causes on purpose — see
# ``rest_api/not_found.py`` — but the ``message`` is not identical, and the
# description below says so rather than claiming non-disclosure.
_BASELINE_PRESET_404 = OpenApiResponse(
    response=ErrorResponseSerializer,
    description=(
        "Not found — three causes answer with the same 404 status, the same "
        "``NOT_FOUND`` error code and the same envelope shape, but not the same "
        "``message``. (1) **Preset gate**: baselines are only available where "
        "the workspace's active rigor preset enables the feature key "
        "``baselines``; under the ``minimal`` preset the endpoint does not exist "
        "and answers 404 without revealing whether the resource would have. "
        "(2) **Workspace missing or not visible**: the workspace is unknown, or "
        "outside the caller's tenant. On ``list`` and ``create`` this also "
        "covers an omitted or empty ``workspace_id``, because the gate then "
        "falls back to the caller's *tenant* id, which resolves to no workspace "
        "and therefore to 404. Causes (1) and (2) share the generic route-miss "
        "message (\"The requested API endpoint does not exist.\"), so they are "
        "indistinguishable from each other and from an unknown route. (3) "
        "**Baseline unknown**: the requested baseline id does not exist, or "
        "belongs to another tenant; this cause keeps the same envelope but its "
        "message is \"Baseline not found\" (``_service_error_response`` "
        "forwarding ``BaselineNotFoundError``), so it is distinguishable from "
        "(1)/(2). Practical consequence: a 404 here means **not available "
        "here**, never \"does not exist\" — the same baseline id can answer 404 "
        "under one preset, workspace or tenant and resolve under another. Do "
        "not treat this response as proof of absence, and do not rely on the "
        "message being byte-identical across the three causes."
    ),
)


# #1380: the flat collection route has no workspace in its path, so the query
# parameter is what makes the gate resolvable at all: without it the gate falls
# back to the tenant id and answers 404 in *every* preset (the preset cannot
# even be looked up for a tenant id). Declared required for the flat route.
# ``_BaselineAutoSchema`` strips it from the nested
# ``/api/v1/workspaces/{workspace_pk}/baselines/`` operation, which takes the
# workspace from its path; publishing it there would be the mirror image of the
# defect this issue fixes.
_BASELINE_TAG_PARAMETER = OpenApiParameter(
    name="tag",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Optional case-insensitive tag filter (F4.2). Only effective together "
        "with the workspace filter. A baseline matches when it carries the "
        "label in any spelling; the join runs through the baseline relation, "
        "so a tag of the same name on a baseline of another workspace is never "
        "returned. Ordering is unchanged (``-created_at``, tie-breaker id)."
    ),
)


_BASELINE_WORKSPACE_ID_PARAMETER = OpenApiParameter(
    name="workspace_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.QUERY,
    required=True,
    description=(
        "Workspace whose baselines to list. **Required** on this flat route: "
        "omitted (or empty), the preset gate falls back to the caller's tenant "
        "id, resolves no workspace, and answers 404 in every preset. The value "
        "must belong to the caller's tenant; a foreign id also answers 404. Use "
        "``/api/v1/workspaces/{workspace_pk}/baselines/`` to supply the "
        "workspace in the path instead."
    ),
)



def _resolve_baseline_diff_ids(
    request: Request, lang: str
) -> tuple[tuple[UUID, UUID] | None, Response | None]:
    """Parse and validate ``?baseline_a=``/``?baseline_b=`` for the diff route.

    REQ-L2-BL-003, REQ-L2-BL-012: both parameters are required, must be valid
    UUIDs and must differ. Returns ``(None, error_response)`` with HTTP 400 on
    any violation, ``((a_id, b_id), None)`` otherwise.
    """
    a_str = request.query_params.get("baseline_a")
    b_str = request.query_params.get("baseline_b")
    if not a_str or not b_str:
        return None, Response(
            build_error_response(
                "VALIDATION_ERROR", lang, message="baseline_a and baseline_b are required"
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        a_id = UUID(a_str)
        b_id = UUID(b_str)
    except (ValueError, TypeError):
        return None, Response(
            build_error_response(
                "VALIDATION_ERROR", lang, message="baseline_a and baseline_b must be valid UUIDs"
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if a_id == b_id:
        return None, Response(
            build_error_response(
                "VALIDATION_ERROR", lang, message="baseline_a and baseline_b must differ"
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return (a_id, b_id), None



def _build_baseline_diff_items(result: Any, artifact_names: dict[str, str]) -> list[dict[str, Any]]:
    """Build the ``items`` array for the baseline diff response.

    REQ-L2-BL-012: added/removed entries carry ``field_changes=None``; changed
    entries expand ``field_changes`` to a list of ``{field_name, old_value,
    new_value}`` records when the diff carries any.
    """
    items: list[dict[str, Any]] = []
    for item_id in result.added:
        items.append({
            "item_id": item_id,
            "entity_type": "item",
            "status": "added",
            "field_changes": None,
            "artifact_name": artifact_names.get(item_id),
        })
    for item_id in result.removed:
        items.append({
            "item_id": item_id,
            "entity_type": "item",
            "status": "removed",
            "field_changes": None,
            "artifact_name": artifact_names.get(item_id),
        })
    for changed in result.changed:
        field_changes = None
        if changed.field_changes:
            field_changes = [
                {"field_name": name, "old_value": delta.get("old"), "new_value": delta.get("new")}
                for name, delta in changed.field_changes.items()
            ]
        items.append({
            "item_id": changed.id,
            "entity_type": "item",
            "status": "changed",
            "field_changes": field_changes,
            "artifact_name": artifact_names.get(changed.id),
        })
    return items



class BaselineViewSet(BaseEntityViewSet):
    """ViewSet for Baseline CRUD operations (REQ-L2-RA-001, REQ-L2-RA-008).

    Gated by preset: Baseline endpoints return 404 in Minimal preset.
    The preset gate raises Http404 and deliberately re-raises it past DRF's
    exception handler so callers (tests, middleware) receive the raw Django
    Http404 (REQ-L3-RA004-001).
    """

    serializer_class = BaselineSerializer
    preset_endpoint_key = "baselines"
    # #1380: the flat and nested collection routes share ``list``; the nested
    # one must not be documented with the flat route's required query param.
    # An *instance* (not the class): DRF's ``schema`` is a ``ViewInspector``
    # descriptor, and only an instance participates in the ``view`` binding
    # ``@extend_schema`` relies on.
    schema = _BaselineAutoSchema()

    def get_serializer_class(self) -> type:
        """#1078: the list response has no ``entries`` field, by contract.

        ``serializer_class`` stays the detail/create representation (that is
        what the create route and the schema's non-list operations need), but
        the *list* operation documents and declares the summary shape, so the
        generated OpenAPI entry for ``GET /baselines/`` stops promising a field
        the endpoint does not emit. Without this override the schema would
        describe ``entries`` on the list operation — the same contract mismatch
        the issue reports, one layer down.
        """
        if getattr(self, "action", None) == "list":
            return BaselineSummarySerializer
        return BaselineSerializer

    def _svc(self) -> BaselineFacade:
        return BaselineFacade()

    def handle_exception(self, exc: Exception) -> Response:
        """Re-raise Http404 so preset-gated 404s propagate past DRF.

        DRF normally converts Http404 to a Response; for preset-gated
        endpoints we want the raw Http404 to surface (REQ-L3-RA004-001).
        """
        if isinstance(exc, Http404):
            raise
        return super().handle_exception(exc)

    def _check_preset(self, request: Request, workspace_id: str | None = None) -> None:
        """Gate this endpoint by preset. Raises Http404 if not visible.

        Args:
            workspace_id: Resolved workspace id (e.g. from the nested-route
                ``workspace_pk`` URL kwarg, issue #49); takes precedence over
                the request body/query-params/tenant-id fallbacks.
        """
        self.request = request
        self._guard_preset(workspace_id_override=workspace_id)

    @extend_schema(
        parameters=[_BASELINE_WORKSPACE_ID_PARAMETER, _BASELINE_TAG_PARAMETER],
        # #1388: declaring the 404 must not erase the success shape — an
        # operation that documents only failures tells a generated client
        # nothing about what a 200 contains.
        responses={
            200: BaselineSummarySerializer(many=True),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``VALIDATION_ERROR`` — the ``tag`` filter is not a string, "
                    "contains a control character or is longer than 64 "
                    "characters. ``details`` carries the rejected value with "
                    "the reason (F4.2, review B2)."
                ),
            ),
            404: _BASELINE_PRESET_404,
        },
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/baselines/?workspace_id=<id> or /api/v1/workspaces/<workspace_id>/baselines/ — list workspace baselines.

        Issue #49: baselines were only reachable at the flat, root-level
        route, unlike Needs/Permissions/Audit/etc. which are workspace-scoped
        via a nested ``workspaces/<workspace_pk>/...`` path. The nested route
        is now registered too (rest_api/urls.py); the flat route is kept for
        backward compatibility (frontend/MCP callers use ?workspace_id=).

        #1078: the list serialises through ``BaselineSummarySerializer`` (see
        ``get_serializer_class``), so a row has no ``entries`` key at all
        instead of an empty one — the list must not claim a baseline captured
        nothing.

        Preset gate (#1380): this endpoint only exists where the workspace's
        active rigor preset enables the ``baselines`` feature. Under the
        ``minimal`` preset it answers **404** — the same opaque body as an
        unknown workspace or a missing route — without exposing whether the
        baseline would have existed. The flat route also **requires**
        ``?workspace_id=``: without it the gate falls back to the caller's
        tenant id, resolves no workspace, and answers 404 in *every* preset.
        """
        workspace_id_str = kwargs.get("workspace_pk") or request.query_params.get("workspace_id")
        # The preset gate deliberately still runs on the raw value and before
        # validation: it decides whether this endpoint exists for the caller's
        # workspace at all, and reordering it would change which of two
        # simultaneous errors a caller is shown.
        self._check_preset(request, workspace_id=workspace_id_str)
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(workspace_id_str, lang)
            if error is not None:
                return error
            items = self._svc().list_baselines(
                workspace_id=str(workspace_id),
                ctx=ctx,
                tag=request.query_params.get("tag") or None,
            )
        except BaselineTagValidationError as exc:
            # F4.2 review B2: an invalid ``?tag=`` is a client defect. Caught
            # before the generic ``ValidationError`` branch so the response
            # carries the same ``details`` list as the create/PUT actions
            # instead of the details-less fallback.
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message=str(exc), details=exc.details
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            lambda item: BaselineSummarySerializer(_baseline_to_dict(item)).data,
        )

    @extend_schema(
        parameters=[_ETAG_RESPONSE_HEADER],
        responses={
            200: BaselineSerializer,
            404: _BASELINE_PRESET_404,
        }
    )
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/baselines/<pk>/ — full baseline detail incl. entries.

        Issue #398: this used to run the preset gate before loading the
        baseline. With no ``workspace_id`` in the URL or query string, the
        gate's last-resort fallback substitutes the *tenant* id for the
        workspace id; ``presets.gate`` then looks that id up in ``pl_workspace``
        and raises ``DoesNotExist``, which ``_guard_preset`` maps to a bare
        ``Http404``. Every detail request therefore 404ed regardless of preset,
        and the UI's "Captured items" panel hung forever.

        The baseline itself knows its workspace, so it is resolved first (the
        service is tenant-scoped and raises NotFoundError for foreign
        baselines) and the gate is then applied to the *real* workspace. Both
        orders answer 404 to an unauthorised caller, so nothing is leaked.

        Preset gate (#1380): the gate still applies to the resolved baseline's
        workspace, so detail GET answers **404** where the active preset does
        not enable ``baselines`` (``minimal``). That 404 is indistinguishable
        from "no such baseline" — neither the preset nor the existence of a
        hidden row is disclosed.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_baseline(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        self._check_preset(request, workspace_id=str(item.workspace_id))
        return self.with_etag(Response(BaselineSerializer(_baseline_to_dict(item)).data), item)

    @extend_schema(
        parameters=[_ETAG_RESPONSE_HEADER],
        responses={
            201: BaselineSerializer,
            404: _BASELINE_PRESET_404,
        }
    )
    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/baselines/ (flat) or /api/v1/workspaces/<workspace_id>/baselines/ (nested) — create baseline.

        Issue #49: the nested-route ``workspace_pk`` URL kwarg (when present)
        takes precedence over a body-supplied ``workspace_id`` so the
        workspace-scoped route works even if the client omits the field.

        SE-Auditor gate (GH-490/GH-513/GH-821): creation is refused with HTTP 400
        and error code ``SE_AUDITOR_BLOCKED`` while the workspace has BLOCKER-level
        audit findings in the requested scope. Two documented exits exist, both
        requiring the ``admin`` or ``approver`` role and both recorded in the
        audit log:

          * ``waived_findings`` — per-finding waivers
            (``[{rule_id, artifact_ids, reason}]``, GH-821). Each one accepts a
            single reported finding with its own mandatory justification and is
            persisted, so the next baseline build does not have to re-state it.
            Findings that remain unwaived still block.
          * ``override_reason`` — one written justification that waives every
            remaining finding at once (GH-513).

        A ``400`` with the plain ``VALIDATION_ERROR`` code from the same gate
        means the auditor itself could not be evaluated — that case is *not*
        overridable.

        #1079: the 201 carries the same ``ETag`` as the detail GET, so a client
        can start a conditional write against the freshly created baseline.

        Preset gate (#1380): creation only exists where the workspace's active
        rigor preset enables the ``baselines`` feature (``preset_endpoint_key =
        "baselines"``); under ``minimal`` the route answers **404** before the
        body is even validated. On the flat route the workspace comes from the
        body ``workspace_id``, so an omitted value makes the gate fall back to
        the tenant id and answer 404 as well — the same opaque body as an
        unknown workspace.
        """
        workspace_pk = kwargs.get("workspace_pk")
        self._check_preset(request, workspace_id=workspace_pk)
        lang = detect_lang(request)
        data_in = dict(request.data)
        if workspace_pk and not data_in.get("workspace_id"):
            data_in["workspace_id"] = workspace_pk
        ser = BaselineSerializer(data=data_in)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            create_kwargs, invalid = self._baseline_create_kwargs(
                data, workspace_pk, ctx, lang
            )
            if invalid is not None:
                return invalid
            baseline_id = self._svc().create_baseline(**create_kwargs)
            # Fetch the newly created baseline detail for the response
            item = self._svc().get_baseline(baseline_id, ctx)
        except BaselineTagValidationError as exc:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message=str(exc), details=exc.details
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return self.with_etag(
            Response(
                BaselineSerializer(_baseline_to_dict(item)).data,
                status=status.HTTP_201_CREATED,
            ),
            item,
        )

    def _baseline_create_kwargs(
        self, data: dict[str, Any], workspace_pk: str | None, ctx: Any, lang: str
    ) -> tuple[dict[str, Any] | None, Response | None]:
        """Build the facade kwargs for ``create_baseline``.

        Returns ``(create_kwargs, None)`` on success, or ``(None, response)``
        with the ``400 VALIDATION_ERROR`` response when ``artifact_id`` is
        missing for document scope or malformed (GH-724). A missing
        workspace_id key raises ``KeyError`` for the caller's error handler
        exactly like the inline version.
        """
        scope = data.get("scope", "document")
        name = data.get("name", "")
        # The UI create form does not supply a name; generate one so the
        # unique-per-workspace constraint is satisfied.
        if not name or not str(name).strip():
            name = f"Baseline {timezone.now().isoformat()}"
        create_kwargs: dict[str, Any] = {
            "scope": scope,
            "workspace_id": str(workspace_pk or data["workspace_id"]),
            "name": name,
            "description": data.get("description"),
            "ctx": ctx,
        }
        # GH-513: only forwarded when actually supplied — the facade treats
        # a blank reason as "no override" anyway, but not sending the key
        # keeps the default call shape unchanged for every other caller.
        override_reason = data.get("override_reason")
        if override_reason and str(override_reason).strip():
            create_kwargs["override_reason"] = str(override_reason)
        # GH-821: per-finding waivers. Already shape-validated by
        # BaselineSerializer (BlockerWaiverSerializer); the facade re-checks
        # the same shape so the MCP path cannot bypass it.
        waived_findings = data.get("waived_findings") or []
        if waived_findings:
            create_kwargs["waived_findings"] = list(waived_findings)
        # F4.2: optional tags on create. The facade validates/de-duplicates
        # them (single normalisation point shared with MCP).
        tags = data.get("tags") or []
        if tags:
            create_kwargs["tags"] = list(tags)
        # document scope requires a root artifact; artifact_id is the
        # view-facing name, the facade/service expect document_id.
        artifact_id = data.get("artifact_id")
        if scope == "document" and artifact_id is None:
            return None, Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="artifact_id is required for document scope",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if artifact_id is not None:
            # GH-724: reject a malformed (non-UUID) artifact_id here with a
            # clean 400 instead of letting a raw ValueError from the
            # facade's UUID(str(document_id)) conversion escape as a 500.
            try:
                UUID(str(artifact_id))
            except (ValueError, TypeError):
                return None, Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message="artifact_id must be a valid UUID",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            create_kwargs["document_id"] = str(artifact_id)
        return create_kwargs, None

    @extend_schema(
        request=BaselineTagsRequestSerializer,
        responses={
            200: BaselineTagsResponseSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``VALIDATION_ERROR`` — a label is empty, longer than 64 "
                    "characters or contains a disallowed character, or more "
                    "than 20 distinct tags were supplied. ``details`` carries "
                    "one entry per rejected label."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``PERMISSION_DENIED`` — the caller needs the editor role "
                    "in the baseline's workspace. A workspace-fenced API key "
                    "whose fence does not contain that workspace is rejected "
                    "here as well."
                ),
            ),
            404: _BASELINE_PRESET_404,
        },
    )
    @action(detail=True, methods=["put"], url_path="tags")
    def tags(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PUT /api/v1/baselines/{pk}/tags/ — replace the tag set (F4.2).

        Body ``{"tags": ["Release", "RC1"]}`` -> ``200 {"id": "...", "tags":
        ["RC1", "Release"]}`` (sorted, case-insensitively de-duplicated).

        Tags are metadata in their own table: this never UPDATEs the immutable
        snapshot. ``workspace_id`` on the row is derived exclusively from the
        baseline, so a ``workspace_id`` in the body is ignored.

        The replacement is an idempotent PUT with no own version, so this
        operation evaluates no ``If-Match`` and is documented as an ETag-less
        resource (``etag_supported = False``; the E2.6 hook describes it as
        such rather than as a 412-capable route).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            baseline = self._svc().get_baseline(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        # Preset gate with the OBJECT workspace (same pattern as retrieve/diff).
        # Outside the try/except: Http404 must propagate past handle_exception.
        self._check_preset(request, workspace_id=str(baseline.workspace_id))

        ser = BaselineTagsRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": key, "errors": value}
                        for key, value in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            labels = self._svc().set_tags(pk, ser.validated_data["tags"], ctx)
        except BaselineTagValidationError as exc:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message=str(exc), details=exc.details
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        return Response({"id": pk, "tags": labels})

    # F4.2: an idempotent PUT without its own revision counter, so placed
    # outside the ETag contract. The E2.6 documentation hook reads this.
    tags.etag_supported = False

    # ------------------------------------------------------------------
    # Plan F F4.4 — additive baseline rollback (ADR-025, PR-F11b)
    # ------------------------------------------------------------------
    #
    # Three detail actions on the baseline. Each resolves the baseline first
    # (tenant-scoped, raises NotFoundError for a foreign one) and then runs the
    # preset gate against the *object's* workspace — the same order as
    # ``retrieve``/``tags`` (#398: the gate's tenant-id fallback would 404 every
    # request otherwise, and gating after resolution keeps the 404 opaque).
    #
    # None of the three *evaluates* an ``If-Match``: the rollback's conflict
    # protection is the domain's (R3 per-item plan binding, R5 CR row lock +
    # ``expected_version`` on the closing transition), not an entity tag on the
    # baseline. The two POST routes nevertheless keep the E2.4 syntax gate — a
    # present-but-malformed header is a request defect (400
    # ``INVALID_IF_MATCH``) and must be rejected before any side effect. They
    # are declared as ETag-less resources rather than 412-capable routes
    # (``etag_supported = False`` below).

    def _rollback_baseline(
        self, request: Request, pk: str, lang: str
    ) -> tuple[Any | None, Any | None, Response | None]:
        """Resolve the baseline + auth context, then apply the preset gate.

        Returns ``(baseline, ctx, None)`` on success and ``(None, None,
        error_response)`` when the baseline is unknown or not visible. The
        preset gate runs outside the ``try``: its ``Http404`` signals "this
        endpoint does not exist for the workspace" and must propagate verbatim
        past ``handle_exception`` (REQ-L3-RA004-001).
        """
        try:
            ctx = get_auth_context(request)
            baseline = self._svc().get_baseline(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return None, None, _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return None, None, _service_error_response(exc, lang)
        self._check_preset(request, workspace_id=str(baseline.workspace_id))
        return baseline, ctx, None

    @extend_schema(
        responses={
            200: BaselineRollbackPreviewSerializer,
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``PERMISSION_DENIED`` — the caller holds no role in the "
                    "baseline's workspace, or the API key's workspace fence "
                    "excludes it (SEC-RB-01)."
                ),
            ),
            404: _BASELINE_PRESET_404,
        },
    )
    @action(detail=True, methods=["get"], url_path="rollback-preview")
    def rollback_preview(
        self, request: Request, pk: str = None, **kwargs: Any
    ) -> Response:
        """GET /api/v1/baselines/{pk}/rollback-preview/ — what a rollback would change.

        Read-only and open to every workspace member (Viewer included): it
        writes nothing and opens no change request (ADR-025 R8). Items without
        a *read* right are absent from ``items``, from every count of
        ``summary`` and from both link lists — a hidden item must not leak even
        as a count (R7/SEC-RB-06).

        A body is never accepted: the plan is derived server-side from the
        baseline.
        """
        lang = detect_lang(request)
        baseline, ctx, invalid = self._rollback_baseline(request, pk, lang)
        if invalid is not None:
            return invalid
        try:
            plan = BaselineRollbackService().preview(baseline.baseline_id, ctx)
        except (RollbackError, ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_rollback_plan_to_dict(plan))

    @extend_schema(
        request=BaselineRollbackRequestSerializer,
        responses={
            201: BaselineRollbackRequestResponseSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``VALIDATION_ERROR`` — ``change_reason`` is missing or "
                    "blank, or the body carries a field the route does not "
                    "accept (#851). ``ROLLBACK_EMPTY`` — the plan restores "
                    "nothing at all. ``ROLLBACK_TOO_LARGE`` — more than "
                    "``MAX_ROLLBACK_ITEMS`` units of work (ADR-025 R9)."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``PERMISSION_DENIED`` — the caller holds no role in the "
                    "baseline's workspace, or the API key's workspace fence "
                    "excludes it (SEC-RB-01)."
                ),
            ),
            404: _BASELINE_PRESET_404,
        },
    )
    @action(detail=True, methods=["post"], url_path="rollback-request")
    def rollback_request(
        self, request: Request, pk: str = None, **kwargs: Any
    ) -> Response:
        """POST /api/v1/baselines/{pk}/rollback-request/ — open the CCB change request.

        The plan is re-derived and bound to the change request's affected-item
        set (ADR-025 R2), so approval happens against exactly the items the
        rollback would write. The CR starts in ``draft`` and becomes executable
        only after the CCB approves it — a rollback is never implicit.
        """
        lang = detect_lang(request)
        # E2.4 syntax gate only: a malformed ``If-Match`` is a request defect
        # (400 ``INVALID_IF_MATCH``). No tag is evaluated — the rollback's
        # conflict protection is the domain's (R2/R3/R5), not an entity tag on
        # the baseline (see the block comment above).
        if_match_error = self.if_match_parse_error(request)
        if if_match_error is not None:
            return if_match_error
        baseline, ctx, invalid = self._rollback_baseline(request, pk, lang)
        if invalid is not None:
            return invalid

        ser = BaselineRollbackRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": key, "errors": value}
                        for key, value in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cr = BaselineRollbackService().request(
                baseline.baseline_id,
                ctx,
                title=ser.validated_data.get("title") or None,
                change_reason=ser.validated_data["change_reason"],
            )
            affected = ChangeRequestService().list_affected_items(cr.id, ctx)
        except (RollbackError, ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)

        return Response(
            {
                "change_request_id": str(cr.id),
                "status": ChangeRequestDTO.from_orm(cr).status,
                "affected_items": len(affected),
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=BaselineRollbackApplyRequestSerializer,
        responses={
            200: BaselineRollbackResultSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``VALIDATION_ERROR`` — the change request is not linked to "
                    "this baseline or belongs to another workspace (ADR-025 "
                    "R2). ``ROLLBACK_TOO_LARGE`` — more than "
                    "``MAX_ROLLBACK_ITEMS`` units of work (R9)."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``PERMISSION_DENIED`` — item-level WRITE is missing, the "
                    "caller holds no role in the baseline's workspace, or the "
                    "principal is an agent (executing is human-only, R7/R8)."
                ),
            ),
            404: _BASELINE_PRESET_404,
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "``ROLLBACK_NOT_APPROVED`` / ``ROLLBACK_ALREADY_APPLIED`` — "
                    "the change request is not in the ``approved`` state it "
                    "must be in (R5). ``ROLLBACK_PLAN_STALE`` — the plan "
                    "changed since the CR was opened; ``details`` lists the "
                    "affected items with their versions (R3). "
                    "``ROLLBACK_CONFLICT`` — a concurrent CCB decision holds "
                    "the change request (R5)."
                ),
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="rollback")
    def rollback(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """POST /api/v1/baselines/{pk}/rollback/ — execute an approved rollback.

        One transaction: the plan is re-derived, checked against the CR's
        affected-item set (R2), version-bound per item (R3) and written as new
        versions through each type's domain service (R1/R5). The CR ends
        ``implemented``. Any failure rolls the whole run back — nothing is
        written and the CR stays ``approved``.
        """
        lang = detect_lang(request)
        # E2.4 syntax gate only — see ``rollback_request``.
        if_match_error = self.if_match_parse_error(request)
        if if_match_error is not None:
            return if_match_error
        baseline, ctx, invalid = self._rollback_baseline(request, pk, lang)
        if invalid is not None:
            return invalid

        ser = BaselineRollbackApplyRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": key, "errors": value}
                        for key, value in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = BaselineRollbackService().apply(
                baseline.baseline_id, ser.validated_data["change_request_id"], ctx
            )
        except (RollbackError, ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(_rollback_result_to_dict(result))

    # Plan F F4.4: the conflict protection is the domain's (R3/R5), not an
    # entity tag on the baseline — see the block comment above. The E2.6
    # documentation hook reads these flags.
    rollback_preview.etag_supported = False
    rollback_request.etag_supported = False
    rollback.etag_supported = False

    def _load_baseline_diff_context(
        self, request: Request, a_id: UUID, b_id: UUID, lang: str
    ) -> tuple[tuple[Any, Any, Any] | None, Response | None]:
        """Resolve both baselines tenant-scoped before the diff runs.

        Tenant-scoping: resolving each baseline via the tenant-scoped store
        raises NotFoundError for baselines outside the caller's tenant before
        the diff runs (REQ-L2-TE-011). Returns ``(None, error_response)`` on
        failure, else ``((svc, ctx, baseline_a), None)``.
        """
        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            baseline_a = svc.get_baseline(a_id, ctx)
            svc.get_baseline(b_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return None, _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("BaselineViewSet.diff: unhandled exception")
            return None, _service_error_response(exc, lang)
        return (svc, ctx, baseline_a), None

    def _run_baseline_diff(
        self, svc: Any, a_id: UUID, b_id: UUID, ctx: Any, lang: str
    ) -> tuple[Any | None, Response | None]:
        """Run the field-level diff, mirroring the mapped service errors."""
        try:
            return svc.diff_baselines(a_id, b_id, ctx), None
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return None, _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("BaselineViewSet.diff: unhandled exception")
            return None, _service_error_response(exc, lang)

    @action(detail=False, methods=["get"], url_path="diff")
    def diff(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/baselines/diff/?baseline_a=<uuid>&baseline_b=<uuid>

        Field-level structural diff between two baselines of the same scope
        (REQ-L2-BL-003, REQ-L2-BL-012). Both baselines must be non-equal and
        belong to the caller's tenant.
        """
        lang = detect_lang(request)

        ids, invalid = _resolve_baseline_diff_ids(request, lang)
        if invalid is not None:
            return invalid
        a_id, b_id = ids

        context, invalid = self._load_baseline_diff_context(request, a_id, b_id, lang)
        if invalid is not None:
            return invalid
        svc, ctx, baseline_a = context

        # Issue #398: the preset gate needs a real workspace id. This endpoint
        # carries none in its URL or query string, and the gate's tenant-id
        # fallback resolves to no workspace at all (-> bare Http404 for every
        # caller). Gate on the resolved baseline's own workspace instead —
        # outside the try/except, because the gate signals "endpoint hidden by
        # preset" with Http404, which handle_exception must re-raise verbatim.
        self._check_preset(request, workspace_id=str(baseline_a.workspace_id))

        result, invalid = self._run_baseline_diff(svc, a_id, b_id, ctx, lang)
        if invalid is not None:
            return invalid

        all_item_ids = [
            *result.added,
            *result.removed,
            *(changed.id for changed in result.changed),
        ]
        artifact_names = _collect_artifact_names(all_item_ids, ctx.tenant_id)

        items = _build_baseline_diff_items(result, artifact_names)

        payload = {
            "baseline_a_id": str(a_id),
            "baseline_b_id": str(b_id),
            "summary": {
                "added": len(result.added),
                "removed": len(result.removed),
                "changed": len(result.changed),
            },
            "items": items,
        }
        return Response(BaselineDiffSerializer(payload).data)

    @extend_schema(
        # #1397: the header the declared 412 is conditioned on. This is the one
        # route whose ETag is a timestamp rather than a version counter (see
        # ``ETagMixin.compute_etag``); it compares as an opaque tag either way.
        parameters=[_IF_MATCH_PARAMETER],
        responses={
            405: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Baselines are immutable; PATCH is not supported. Create a "
                    "new baseline instead."
                ),
            ),
            412: _PRECONDITION_FAILED_RESPONSE,
        },
    )
    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/baselines/{pk}/ — always 405: baselines are immutable.

        GH-868: the GET carries an ``ETag``, so a client can send it back as
        ``If-Match``. That precondition is evaluated *before* the immutability
        answer — a stale tag is a 412 (the resource changed under the client),
        which is the standard ordering, while a current tag or no header at all
        still gets the 405 below. Any load failure falls through to 405, so no
        existing request changes status because of this branch.
        """
        # GH-1396 review finding F9: the published contract says a malformed
        # If-Match is 400. Parsing it only *after* the row load meant an
        # unknown/foreign baseline id plus a malformed header answered 405 (the
        # immutable-route fallback) — the same request that is a 400 on every
        # other ETag route. The syntactic check needs no row, so it runs first.
        invalid = self.if_match_parse_error(request)
        if invalid is not None:
            return invalid
        if self.uses_if_match(request):
            try:
                current = self._svc().get_baseline(pk, get_auth_context(request))
            except Exception:  # noqa: BLE001 — never let the probe change the 405
                current = None
            if current is not None:
                failed = self.check_if_match(request, current)
                if failed is not None:
                    return failed
        # Baselines are immutable once created
        return Response(
            build_error_response("VALIDATION_ERROR", detect_lang(request), message="Baselines are immutable. Create a new baseline instead."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/baselines/{pk}/ — refused: baselines are immutable.

        GH-1199: this is a *domain* prohibition, not a role denial, so it answers
        403 with the dedicated code ``BASELINE_IMMUTABLE`` instead of the generic
        ``PERMISSION_DENIED`` the hard-coded response used to reuse — which made
        "this resource cannot be deleted, by anyone" indistinguishable from "you
        personally lack the role". The message names the one real removal path:
        the admin-only, audited ``DELETE /api/v1/baselines/{pk}/purge/``.
        """
        return Response(
            build_error_response(
                "BASELINE_IMMUTABLE",
                detect_lang(request),
                message=(
                    "Baselines are content-immutable and cannot be deleted "
                    "through this route. An administrator can remove one via "
                    "the audited administrative route "
                    "DELETE /api/v1/baselines/{id}/purge/."
                ),
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    @action(detail=True, methods=["delete"], url_path="purge")
    def purge(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """DELETE /api/v1/baselines/{pk}/purge/ — audited admin removal (GH-1199).

        The only route that removes a baseline. Admin-only — checked in
        ``BaselineFacade.purge_baseline``, the same role the workspace
        hard-delete requires — and always audited (``operation="baseline.purge"``)
        so the removal of an append-only governance artifact leaves a trail.
        Baselines stay content-immutable: the UPDATE path is untouched, and the
        DELETE only passes the ``bl_raise_immutable`` trigger under the
        transaction-local GUC the service arms (never ``DISABLE TRIGGER``).

        A missing/foreign baseline answers 404; a non-admin answers 403
        ``PERMISSION_DENIED`` (a role denial, distinct from the generic route's
        403 ``BASELINE_IMMUTABLE`` domain prohibition).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().purge_baseline(pk, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:  # noqa: BLE001 — map any service error uniformly
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)



def _resolve_artifact_titles(
    artifact_ids: list[Any],
) -> dict[str, dict[str, Any]]:
    """Batch-resolve artifact IDs to {title, artifact_type} dicts.

    REQ-002: Provides human-readable labels for TraceLink endpoints without N+1
    queries. Runs at most 6 DB queries regardless of the number of links:
    one Artifact query for types + one per domain entity table.

    Args:
        artifact_ids: List of artifact UUIDs (str or UUID).

    Returns:
        Mapping from artifact_id (str) to {"title": str, "artifact_type": str}.

    REQ-066: thin wrapper — the ORM access lives in ArtifactService.
    """
    return ArtifactService().resolve_artifact_titles(artifact_ids)



def _workspace_of_artifact(artifact_id: Any) -> UUID | None:
    """Return the workspace owning *artifact_id*, or ``None`` (QR-S20).

    REQ-066: the ORM traversal lives in ``application.workspace_lookup`` — the
    same resolver the REST fence and the MCP dispatcher use — not in the view.
    """
    from application.workspace_lookup import resolve_owning_workspace_id

    try:
        return resolve_owning_workspace_id("artifact", UUID(str(artifact_id)))
    except (TypeError, ValueError):
        return None



def _caller_may_read_workspace(workspace_id: Any, ctx: Any) -> bool:
    """Return whether *ctx* holds READ in *workspace_id* (Plan E QR-S20).

    The trace-link detail route is fenced on the link's **source** workspace,
    so a caller can legitimately reach a link whose target lives in a workspace
    they have no standing in. The target title is cross-workspace metadata:
    ``TraceLinkViewSet.retrieve`` emits it only when this returns ``True``.

    Fail-closed on every inconclusive path: an unresolvable workspace, an
    API-key workspace fence that excludes it, or a failed role lookup all mean
    "not readable" and keep the title hidden.

    Args:
        workspace_id: Target workspace id (a UUID or ``None``).
        ctx: The request's :class:`~auth_tenancy.context.AuthContext`.
    """
    if workspace_id is None:
        return False

    from auth_tenancy.resource_scope import workspace_fence_denial
    from auth_tenancy.services import AuthorizationService, Operation

    fence = getattr(ctx, "api_key_workspace_ids", ())
    if workspace_fence_denial(fence, workspace_id) is not None:
        return False
    try:
        authz = AuthorizationService()
        roles = authz.active_roles_for(
            user_id=ctx.user_id, workspace_id=workspace_id
        )
    except Exception:  # noqa: BLE001 — hide metadata rather than leak it
        logger.debug(
            "QR-S20: role lookup failed for user=%s workspace=%s",
            getattr(ctx, "user_id", None),
            workspace_id,
            exc_info=True,
        )
        return False
    return authz.decide_access(roles, Operation.READ).allow



def _tracelink_to_dict(tl: Any, titles: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Convert TraceLink ORM object to dict.

    REQ-002: When *titles* is provided the dict includes source_title,
    target_title, source_type, target_type for human-readable display.

    Q1.6: ``rationale`` and the two suspect markers are declared on
    TraceLinkSerializer, but every REST endpoint feeds that serializer from
    *this* dict — a key missing here is a field the API never returns
    (``required=False`` makes DRF skip it silently). The suspect markers stay
    ``None`` until the propagation engine writes them.

    Security review M2: ``proposed_by``/``proposed_at``/``proposed_by_label``
    were declared on TraceLinkSerializer but never added here, so the API
    returned no proposal information at all and a client could not tell an
    agent-proposed link from a human one. Exactly the failure mode the
    paragraph above warns about.
    """
    source_id = str(tl.source_id)
    target_id = str(tl.target_id)
    proposing_key = getattr(tl, "proposed_by", None)
    d: dict[str, Any] = {
        "id": str(tl.id),
        "source_id": source_id,
        "target_id": target_id,
        # #1270: explicit, unambiguous aliases. TraceLink endpoints are canonical
        # *Artifact* ids (never the Requirement/TestCase entity PK), and
        # ``source_id``/``target_id`` were easy to mistake for a Requirement
        # ``id`` — a join on the wrong field produced plausible-but-wrong
        # coverage. Same values under a name that says what it is; the original
        # keys stay for backward compatibility.
        "source_artifact_id": source_id,
        "target_artifact_id": target_id,
        "link_type": tl.link_type,
        "version": tl.version,
        "created_at": tl.created_at,
        "rationale": getattr(tl, "rationale", "") or "",
        "suspect_flagged_at": getattr(tl, "suspect_flagged_at", None),
        "suspect_source_change": getattr(tl, "suspect_source_change", None),
        # ``proposed_by`` is declared with source="proposed_by_id", so the
        # serializer looks this exact key up in the dict.
        "proposed_by_id": getattr(tl, "proposed_by_id", None),
        "proposed_at": getattr(tl, "proposed_at", None),
        "proposed_by_label": getattr(proposing_key, "agent_label", "") or "",
    }
    if titles is not None:
        src = titles.get(source_id, {})
        tgt = titles.get(target_id, {})
        d["source_title"] = src.get("title", "")
        d["target_title"] = tgt.get("title", "")
        d["source_type"] = src.get("artifact_type", "")
        d["target_type"] = tgt.get("artifact_type", "")
        # UI-P3: an endpoint soft-deleted via outdate() keeps its TraceLink
        # (audit trail) — flag it so the client does not render it as live.
        d["source_is_outdated"] = bool(src.get("is_outdated", False))
        d["target_is_outdated"] = bool(tgt.get("is_outdated", False))
    return d



def _enrich_tracelink_titles(items: list[dict[str, Any]]) -> None:
    """Fill title/type/outdated keys from batch-resolved artifact titles.

    REQ-002: batch-resolves titles for all unique artifact IDs so the
    frontend can display human-readable labels without extra requests.

    UI-P3: see ``_tracelink_to_dict`` — a soft-deleted endpoint keeps its
    link (audit trail) and must be marked, not silently dropped. The *near*
    endpoint is the raw id the caller queried with (possibly an entity id, per
    the #512 echo contract), so it never resolves here and stays False —
    correct, since the artifact being viewed is by definition the live one.
    """
    all_artifact_ids = {item["source_id"] for item in items} | {
        item["target_id"] for item in items
    }
    titles = _resolve_artifact_titles(list(all_artifact_ids))
    for item in items:
        src = titles.get(item["source_id"], {})
        tgt = titles.get(item["target_id"], {})
        item["source_title"] = src.get("title", "")
        item["target_title"] = tgt.get("title", "")
        item["source_type"] = src.get("artifact_type", "")
        item["target_type"] = tgt.get("artifact_type", "")
        item["source_is_outdated"] = bool(src.get("is_outdated", False))
        item["target_is_outdated"] = bool(tgt.get("is_outdated", False))



def _collect_artifact_names(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, str]:
    """Batch-resolve ``{item_id: title}`` for baseline-diff items (REQ-006).

    ``item_id`` is the Artifact UUID for ``entity_type == "item"`` entries
    (REQ-L2-BL-001). The concrete domain entity is discovered by
    batch-querying each candidate table on ``artifact_id__in``, mirroring
    ``baseline.state_capture._capture_items``. Non-UUID or unresolved ids
    (e.g. icd/trace_link/glossary_term entries) are simply omitted so callers
    can fall back to the raw id.

    REQ-066: thin wrapper — the ORM access lives in ArtifactService.
    """
    return ArtifactService().collect_artifact_names(item_ids, tenant_id)



def _baseline_to_dict(bl: Any) -> dict[str, Any]:
    """Convert BaselineSummary / BaselineDetail dataclass to dict.

    ``BaselineDetail`` carries ``entries`` (delta index tuples, each with an
    optional full-state ``state`` snapshot, REQ-L2-BL-012); ``BaselineSummary``
    does not. Entries are included only when present so the list endpoint stays
    lightweight.
    """
    result: dict[str, Any] = {
        "id": str(bl.baseline_id),
        "workspace_id": str(bl.workspace_id),
        "name": getattr(bl, "name", ""),
        "scope": getattr(bl, "scope", ""),
        "description": getattr(bl, "description", ""),
        "artifact_id": None,
        "version": getattr(bl, "version", 1),
        "created_at": bl.created_at,
        # F4.2: present on both summary and detail; never None.
        "tags": list(getattr(bl, "tags", []) or []),
    }
    entries = getattr(bl, "entries", None)
    if entries is not None:
        result["entries"] = [
            {
                "item_id": e.item_id,
                "version": e.version,
                "entity_type": e.entity_type,
                "state": getattr(e, "state", None),
            }
            for e in entries
        ]
    return result



def _rollback_plan_to_dict(plan: Any) -> dict[str, Any]:
    """Serialise a ``RollbackPlan`` for the preview response (Plan F F4.4).

    The dataclass is the single source of truth: every value is passed through
    unchanged so the wire contract cannot drift from the service's own summary
    (``RollbackPlan.summary`` already counts per action and per link bucket).
    """
    return {
        "baseline_id": str(plan.baseline_id),
        "summary": plan.summary,
        "items": [
            {
                "item_id": item.item_id,
                "artifact_type": item.artifact_type,
                "action": item.action,
                "field_changes": item.field_changes,
                "unrestorable_fields": list(item.unrestorable_fields),
                "current_version": item.current_version,
            }
            for item in plan.items
        ],
        "links_to_recreate": list(plan.links_to_recreate),
        "skipped_links": list(plan.skipped_links),
    }



def _rollback_result_to_dict(result: Any) -> dict[str, Any]:
    """Serialise a ``RollbackResult`` for the apply response (Plan F F4.4)."""
    return {
        "restored": result.restored,
        "reactivated": result.reactivated,
        "links_recreated": result.links_recreated,
        "change_request_status": result.change_request_status,
        "skipped": list(result.skipped),
    }
