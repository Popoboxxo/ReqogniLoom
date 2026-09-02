"""
COMP-RA-001 HttpEndpointController — DRF ViewSets for all domain operations.

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
from typing import Any, Callable
import uuid
from uuid import UUID

from django.http import Http404, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services import (
    ArtifactService,
    ArtifactDiffService,
    BaselineFacade,
    BaselineGateBlockedError,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    RequirementService,
    ArchitectureService,
    SearchService,
    TestService,
    TestRunService,
    TraceLinkService,
    ValidationError,
    WorkflowFacade,
    WorkspaceService,
    ExportService,
    ReqifExportService,
    ReqifImportService,
    ImportService,
    AdrService,
    RiskService,
    IssueService,
    GlossaryService,
    PgVectorUnavailableError,
    ChangeRequestService,
)
from application.attribute_visibility_service import AttributeVisibilityConfigService
from application.goal_service import GoalService
from application.main_goal_service import MainGoalService
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.requirement_bundle_service import (
    BundleDepthExceededError,
    RequirementBundleQueryService,
)
from presets.exceptions import CrossTenantWorkspaceError
from audit.query import AuditLogQuery, AuditQueryFilters
from rest_api.auth_enforcer import get_auth_context
from rest_api.mixins import FreeTextSanitizationMixin, WorkflowTransitionsMixin

logger = logging.getLogger(__name__)
from rest_api.preset_guard import PresetError, PresetGateMixin
from rest_api.query_params import (
    parse_include_deleted,
    parse_workspace_id,
    require_non_empty_param,
)
from rest_api.serializers import (
    AdrSerializer,
    ArtifactSerializer,
    ArchitectureElementSerializer,
    AttributeVisibilityConfigSerializer,
    CustomFieldDefinitionSerializer,
    CustomFieldValueSerializer,
    BaselineDiffSerializer,
    BaselineSerializer,
    GoalSerializer,
    ImpactNodeSerializer,
    IssueSerializer,
    MainGoalSerializer,
    RequirementSerializer,
    ResolvedArtifactSerializer,
    RiskSerializer,
    SimilarRequirementSerializer,
    SimilarTraceLinkSerializer,
    StakeholderNeedSerializer,
    StandardPagination,
    TestCaseSerializer,
    TestRunSerializer,
    TestRunResultSerializer,
    TraceLinkPagination,
    TraceLinkSerializer,
    TracePathSerializer,
    WorkflowDefinitionSerializer,
    WorkspaceSerializer,
    GlossaryTermSerializer,
    ChangeRequestSerializer,
    build_error_response,
    detect_lang,
    extract_preset_tier,
)

# GH-443: every soft-deleting ``destroy()`` below repeats the same paragraph
# verbatim. That is deliberate duplication, not an oversight: drf-spectacular
# builds each endpoint's OpenAPI ``description`` from the method's ``__doc__``,
# so a shared constant would never reach the published schema — and the
# published schema is exactly where the contract was unreadable before. Where an
# entity genuinely deviates (ArchitectureElement's 404, the TraceLink cascade on
# TestCase/Issue/Risk) the deviation is spelled out in that entity's docstring.

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
    NotFoundError: status.HTTP_404_NOT_FOUND,
    OptimisticLockError: status.HTTP_409_CONFLICT,
}

_EXC_TO_CODE: dict[type, str] = {
    ValidationError: "VALIDATION_ERROR",
    # GH-513: a distinct code so a client can tell "known BLOCKERs, waivable
    # with an override_reason" apart from every other 400 on this endpoint.
    BaselineGateBlockedError: "SE_AUDITOR_BLOCKED",
    PermissionDeniedError: "PERMISSION_DENIED",
    CrossTenantWorkspaceError: "PERMISSION_DENIED",
    NotFoundError: "NOT_FOUND",
    OptimisticLockError: "CONFLICT",
}


def _service_error_response(exc: Exception, lang: str = "en") -> Response:
    """Translate an ApplicationService exception into a standardised error Response.

    REQ-L3-RA001-002: No stack traces leaked; uses ErrorResponseFormatter pattern.

    fix #108: for unmapped exception types (IntegrityError, ProgrammingError,
    KeyError, etc.), ``str(exc)`` can contain SQL fragments, table/column
    names, and constraint names — leaking internals regardless of DEBUG.
    Only the three explicitly mapped, safe-to-surface exception types get
    their message forwarded to the client; everything else gets a static
    message, with the real detail going to the log only.
    """
    exc_type = type(exc)
    http_status = _EXC_TO_HTTP.get(exc_type, status.HTTP_500_INTERNAL_SERVER_ERROR)
    code = _EXC_TO_CODE.get(exc_type, "INTERNAL_SERVER_ERROR")
    if exc_type in _EXC_TO_CODE:
        message = str(exc) or None
    else:
        logger.exception("Unhandled exception in service layer", exc_info=exc)
        message = "An internal error occurred."
    body = build_error_response(
        code=code,
        lang=lang,
        message=message,
    )
    return Response(body, status=http_status)


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


class BaseEntityViewSet(FreeTextSanitizationMixin, PresetGateMixin, viewsets.ViewSet):
    """Shared behaviour: error mapping, auth context, preset gate, pagination.

    Subclasses must implement list(), retrieve(), create(), partial_update(),
    destroy() and set:
      - serializer_class
      - preset_endpoint_key (optional, from PresetGateMixin)

    #269: ``FreeTextSanitizationMixin`` guards every write body here rather
    than in each subclass, because several subclasses read ``request.data``
    directly instead of running ``serializer_class`` (see the mixin docstring).
    """

    serializer_class: type | None = None
    pagination_class = StandardPagination

    #: URL path kwargs that MUST parse as a UUID (issue #271). Every subclass
    #: resolves its detail routes by UUID today (``UUID(pk)`` in the handler, or
    #: ``UUID(str(...))`` one layer down in the service — verified for
    #: BaselineViewSet and CustomFieldDefinitionViewSet, which pass ``pk``
    #: through as a string). A subclass whose lookup is genuinely *not* a UUID
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
        """
        lang = detect_lang(request)
        # ``dispatch()`` sets ``self.kwargs`` before ``initial()``; the getattr
        # keeps a hand-rolled ``initial()`` call in a unit test from AttributeError.
        url_kwargs = getattr(self, "kwargs", None) or {}
        for name in self.uuid_url_kwargs:
            raw = url_kwargs.get(name)
            if raw is None:
                continue
            try:
                UUID(str(raw))
            except (ValueError, AttributeError, TypeError):
                # The offending value is NOT echoed back — it is fully
                # attacker-controlled and would be reflected into the body.
                raise MalformedUuidInPath(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=f"'{name}' must be a well-formed UUID.",
                    )
                ) from None

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

        Response shape follows ``StandardPagination``:
        ``{count, next, previous, page_size, max_page_size, results}`` — the
        last two were added in #571 (reopen) so a clamped ``page_size`` stops
        being silent.
        """
        page = self.paginator.paginate_queryset(items, request, view=self)
        if page is not None:
            results = [serialize(obj) for obj in page] if serialize else page
            return self.paginator.get_paginated_response(results)
        # Pagination disabled for this request — serialise the full set.
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


# ---------------------------------------------------------------------------
# COMP-RA-001: RequirementViewSet
# REQ-L3-RA001-001: CRUD for Requirement entity
# ---------------------------------------------------------------------------


class StakeholderNeedViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Stakeholder Need entity."""

    serializer_class = StakeholderNeedSerializer
    workflow_item_type = "StakeholderNeed"
    # REQ-128 constrained the detail lookup to a UUID shape here so that
    # GET /api/v1/needs/derive-requirements/ (a custom-action path missing its
    # pk) 404ed at routing time instead of reaching retrieve() and 500ing on
    # UUID(pk). That trade-off made needs/goals 404 on *any* non-UUID-shaped
    # pk — including a genuinely malformed one like "not-a-uuid" — while every
    # other BaseEntityViewSet subclass answers 400 for the same input via the
    # generic uuid_url_kwargs guard in initial() (issue #271). Issue #710
    # flagged that asymmetry; #271's guard already turns "derive-requirements"
    # (or any other malformed pk) into a clean 400 instead of the original
    # 500, so the router-level regex is no longer needed to prevent it — it
    # was only reproducing the 500-era behaviour of hiding the segment before
    # it could raise. Removing it lets non-UUID pks reach initial()'s guard
    # and answer 400 here too, matching RequirementViewSet and the rest of
    # the API. (GoalViewSet keeps its own regex: it additionally protects a
    # real, still-nonexistent route alias, /goals/main/ vs /main-goals/
    # current/, which the 400 guard would otherwise misreport as a malformed
    # id rather than an unknown route — see #460 Finding 4.)

    @property
    def service(self):
        from application.stakeholder_need_service import StakeholderNeedService
        from application.preset_policy_service import PresetPolicyService
        return StakeholderNeedService(preset_policy_service=PresetPolicyService())

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        need = self.service.get(ctx, UUID(pk))
        return need.id, need.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self.service.get(ctx, UUID(pk)), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self.service.get(ctx, item_id)
        return {"need": StakeholderNeedSerializer(updated.to_dict()).data}

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
                lambda item: StakeholderNeedSerializer(item.to_dict()).data,
            )
        except NotFoundError as e:
            return Response(build_error_response("NOT_FOUND", lang, message=str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """GET /api/v1/needs/<id>/ — retrieve single need."""
        lang = detect_lang(request)
        try:
            item = self.service.get(get_auth_context(request), kwargs["pk"])
            return Response(StakeholderNeedSerializer(item.to_dict()).data)
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
        for f in ("workspace_id", "parent_id", "change_reason"):
            payload.pop(f, None)
        try:
            item = self.service.create(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                **payload,
            )
            return Response(StakeholderNeedSerializer(item.to_dict()).data, status=status.HTTP_201_CREATED)
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
        for f in ["id", "workspace_id", "parent_id", "uid", "suspect", "version", "created_at", "updated_at"]:
            data.pop(f, None)

        try:
            item = self.service.update(
                ctx=get_auth_context(request),
                need_id=kwargs["pk"],
                change_reason=change_reason,
                expected_version=expected_version,
                **data,
            )
            return Response(StakeholderNeedSerializer(item.to_dict()).data)
        except ValidationError as e:
            return Response(build_error_response("VALIDATION_ERROR", lang, message=str(e)), status=status.HTTP_400_BAD_REQUEST)
        except NotFoundError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("StakeholderNeedViewSet.partial_update: unhandled exception")
            return _service_error_response(exc, lang)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """DELETE /api/v1/needs/<id>/ — soft-delete a stakeholder need. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        TraceLinks pointing at the record survive the delete, and traceability
        coverage ignores outdated records.
        """
        lang = detect_lang(request)
        change_reason = request.data.get("change_reason", "") if isinstance(request.data, dict) else ""
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

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        req = self._svc().get_requirement(UUID(pk), ctx)
        return req.id, req.artifact.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_requirement(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_requirement(item_id, ctx)
        return {"requirement": RequirementSerializer(_dto_from_orm(updated)).data}

    def _svc(self) -> RequirementService:
        return RequirementService()

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
            items = self._svc().list_requirements(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                status=status_filter,
                search=search,
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)

        return self._paginate(
            request, items, lambda item: RequirementSerializer(_dto_from_orm(item)).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/ — retrieve single requirement."""
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
        return Response(RequirementSerializer(_dto_from_orm(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/ — create a requirement. Returns 201.

        REQ-L3-RF003-005: Accepts type-dependent fields (moscow_priority,
        complexity_fibonacci, verification_method).
        """
        lang = detect_lang(request)
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
            item = self._svc().create_requirement(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                acceptance_criteria=data.get("acceptance_criteria", ""),
                category=data.get("category", ""),
                parent_id=data.get("parent_id"),
                type=data.get("type", "SyReq"),
                complexity_fibonacci=data.get("complexity_fibonacci"),
                verification_method=data.get("verification_method"),
                level=data.get("level"),
                uid=data.get("uid"),
                custom_fields=data.get("custom_fields"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RequirementSerializer(_dto_from_orm(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/requirements/{pk}/ — update a requirement. Returns 200.

        REQ-L3-RF003-005: Accepts type-dependent fields (moscow_priority,
        complexity_fibonacci, verification_method).
        """
        lang = detect_lang(request)
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
        # REQ-L2-AS-037: only forward custom_fields when the client actually
        # sent it, so an unrelated PATCH does not wipe existing custom_fields.
        #
        # Issue #409: complexity_fibonacci/verification_method/level are
        # nullable SE fields whose absence from a partial PATCH payload must
        # mean "leave unchanged", not "clear to NULL". update_requirement()
        # already distinguishes the two cases via the ``_UNSET`` sentinel
        # (default), but this view used to always pass ``data.get(...)`` —
        # which is None both when the client omitted the field AND when the
        # client explicitly sent null — collapsing "unchanged" into "clear"
        # and silently wiping the stored value on every unrelated PATCH.
        # Forward these fields only when actually present in the payload, the
        # same way custom_fields already is, so the sentinel default takes
        # over ("leave unchanged") whenever the client didn't send them.
        extra_kwargs: dict[str, Any] = {}
        if "custom_fields" in data:
            extra_kwargs["custom_fields"] = data["custom_fields"]
        if "complexity_fibonacci" in data:
            extra_kwargs["complexity_fibonacci"] = data["complexity_fibonacci"]
        if "verification_method" in data:
            extra_kwargs["verification_method"] = data["verification_method"]
        if "level" in data:
            extra_kwargs["level"] = data["level"]
        try:
            ctx = get_auth_context(request)
            # REQ-143: `status` is intentionally NOT forwarded. The serializer
            # marks it read-only, so a client-sent status is ignored here and the
            # lifecycle state can only change via the transitions endpoint.
            item = self._svc().update_requirement(
                requirement_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                acceptance_criteria=data.get("acceptance_criteria"),
                category=data.get("category"),
                change_reason=data.get("change_reason"),
                type=data.get("type"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
                # uid is read-only via REST: never forward from PATCH data
                # (would overwrite stored uid with None). Set only via service/MCP.
                **extra_kwargs,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RequirementSerializer(_dto_from_orm(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/requirements/{pk}/ — soft-delete a requirement. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` (or
        ``?status=outdated``) to see them, and ``POST .../reactivate/`` to
        restore one. TraceLinks pointing at the record survive, and
        traceability coverage ignores outdated records.
        """
        lang = detect_lang(request)
        change_reason = request.data.get("change_reason", "") if isinstance(request.data, dict) else ""
        try:
            ctx = get_auth_context(request)
            self._svc().delete_requirement(UUID(pk), ctx, change_reason=change_reason)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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

    @action(detail=True, methods=["post"], url_path="derive-testcase")
    def derive_testcase(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/{pk}/derive-testcase/ — AI TestCase draft.

        SysEng 2.0 N5 (test.derive_from_requirement). REQ-L2-AI-001: Draft/Accept
        flow. Proposes a TestCase draft (title, description, steps) verifying
        this requirement without persisting anything. Standard feature — no
        rigor-preset / RuleEngine gate, unlike decompose_next_level.
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_artifact(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    def _svc(self) -> ArchitectureService:
        return ArchitectureService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        # GH-443: ``include_deleted=True`` so the workflow actions stay usable
        # on a soft-deleted element — without it ``POST .../reactivate/`` could
        # never reach the one item it exists for. Unlike the other entity types
        # ArchitectureElement has no denormalized status mirror (see
        # workflow.lifecycle_manager._STATUS_MIRROR_MODELS), so ``retrieve()``
        # keeps hiding outdated elements: a 200 there could not carry the
        # "outdated" marker and would be indistinguishable from a live element.
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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request,
            items,
            lambda item: ArchitectureElementSerializer(_arch_to_dict(item)).data,
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_architecture_element(UUID(pk), ctx)
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
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data, status=status.HTTP_201_CREATED)

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
            item = self._svc().update_architecture_element(
                arch_el_id=UUID(pk),
                ctx=ctx,
                expected_version=data.get("expected_version"),
                title=data.get("title"),
                description=data.get("description"),
                element_type=data.get("element_type"),
                asil_level=data.get("asil_level"),
                make_or_buy=data.get("make_or_buy"),
                # uid is read-only via REST: never forward from PATCH data
                # (would overwrite stored uid with None). Set only via service/MCP.
                **update_kwargs,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/architecture/{pk}/ — soft-delete an element. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated". List endpoints hide outdated elements by
        default; pass ``?include_deleted=true`` to see them, and
        ``POST .../reactivate/`` to restore one. TraceLinks pointing at the
        element survive the delete, and traceability coverage ignores outdated
        elements.

        ArchitectureElement is the one deliberate exception to the "GET after
        DELETE still answers 200 with ``status='outdated'``" rule that the
        other soft-deleting entities follow: it has no denormalized status
        mirror (``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``), so a 200
        here could not carry the "outdated" marker and would be
        indistinguishable from a live element. This URL therefore keeps
        answering 404 after the delete; the soft-delete state stays observable
        via ``GET .../workflow-history/`` and ``?include_deleted=true``.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_architecture_element(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="allocation-coverage")
    def allocation_coverage(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture-elements/{id}/allocation-coverage/

        REQ-L1-042: Returns allocation coverage metrics for this ArchitectureElement.

        Response:
          - allocated_count: Number of allocated Requirements.
          - coverage_ratio: Percentage (0-100) of allocated vs total child requirements.
          - unallocated_requirements: List of unallocated child requirements.
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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

            depth_param = request.query_params.get("depth")
            depth = int(depth_param) if depth_param is not None else None

            filter_mode = request.query_params.get("filter_mode", "all")
            fields_param = request.query_params.get("fields")
            fields = fields_param.split(",") if fields_param else None

            output_format = request.query_params.get("output_format", "json")
            if output_format not in ("json", "markdown", "csv"):
                return Response(
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
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang,
                        message=f"Invalid mode {mode!r}; expected raw or compressed",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = RequirementBundleQueryService().get_bundle(
                ctx,
                root_id=UUID(pk),
                workspace_id=workspace_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
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
        except Exception as exc:
            return _service_error_response(exc, lang)

        if mode == "raw":
            if output_format == "json":
                return Response(format_bundle_json(result))
            if output_format == "markdown":
                return HttpResponse(
                    format_bundle_markdown(result), content_type="text/markdown; charset=utf-8"
                )
            return HttpResponse(format_bundle_csv(result), content_type="text/csv; charset=utf-8")

        # mode == "compressed" — route the same bundle through
        # BundleCompressionService (Plan 2 Task 1/2) instead of the raw
        # formatters above. ?output_format= is not applicable here.
        try:
            from application.bundle_compression_service import (
                BundleCompressionService,
                SYNC_ITEM_COUNT_THRESHOLD,
            )

            force_async = request.query_params.get("async", "").lower() == "true"
            use_async = force_async or len(result.items) > SYNC_ITEM_COUNT_THRESHOLD

            compression_svc = BundleCompressionService()
            if use_async:
                dispatch = compression_svc.compress_async(
                    ctx,
                    result,
                    root_id=UUID(pk),
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
                root_id=UUID(pk),
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
        except Exception as exc:
            return _service_error_response(exc, lang)


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

    def get(self, request: Request, task_id: str, **kwargs: Any) -> Response:
        import dataclasses

        from application.bundle_compression_service import BundleCompressionService

        ctx = get_auth_context(request)
        result = BundleCompressionService().get_compression_status(ctx, task_id)
        return Response(dataclasses.asdict(result))


# ---------------------------------------------------------------------------
# TestCaseViewSet
# ---------------------------------------------------------------------------


class TestCaseViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for TestCase CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TestCaseSerializer
    preset_endpoint_key = ""
    workflow_item_type = "TestCase"

    def _svc(self) -> TestService:
        return TestService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_test_case(UUID(pk), ctx)
        return item.id, item.artifact.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_test_case(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_test_case(item_id, ctx)
        return {"test_case": TestCaseSerializer(_test_to_dict(updated)).data}

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
            items = self._svc().list_test_cases(
                workspace_id=workspace_id,
                ctx=ctx,
                include_deleted=parse_include_deleted(request.query_params),
                search=search,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: TestCaseSerializer(_test_to_dict(item)).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(TestCaseSerializer(_test_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = TestCaseSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_test_case(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                steps=data.get("steps") or None,
                custom_fields=data.get("custom_fields"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        return Response(TestCaseSerializer(response_data).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
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
        try:
            ctx = get_auth_context(request)
            # REQ-165/REQ-166 (CR-08): `status` is intentionally NOT forwarded
            # (and is now read-only on TestCaseSerializer, see there). Change the
            # lifecycle state via POST /api/v1/testcases/{id}/transitions/.
            # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
            # stale expected_version → OptimisticLockError → 409 CONFLICT.
            item = self._svc().update_test_case(
                test_case_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                expected_version=data.get("expected_version"),
                **extra_kwargs,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(TestCaseSerializer(_test_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/testcases/{pk}/ — soft-delete a test case. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        Caveat, unchanged by GH-443: unlike the other soft-deleting entities,
        this one still hard-deletes every TraceLink touching the record, so a
        later reactivate brings the record back without its links.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

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
        except Exception as exc:
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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)


# ---------------------------------------------------------------------------
# TraceLinkViewSet
# ---------------------------------------------------------------------------


class TraceLinkViewSet(BaseEntityViewSet):
    """ViewSet for TraceLink CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TraceLinkSerializer
    preset_endpoint_key = ""
    # Fix #571 (reopen): clients render the traceability graph from the *whole*
    # link set, so they walk every page. 500/page instead of the shared 100
    # turns ~1980 links from 20 serial round-trips into 4 — see
    # TraceLinkPagination for why the ceiling is safe to raise here only.
    pagination_class = TraceLinkPagination

    def _svc(self) -> TraceLinkService:
        return TraceLinkService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/?workspace_id=<id>[&artifact_id=<id>]

        When artifact_id is provided: returns upstream + downstream links for that artifact.
        When only workspace_id is provided: returns every link whose source
        lives in that workspace.

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
            svc = self._svc()
            items: list = []

            if not artifact_id_str:
                links_qs = svc.list_links_for_workspace_queryset(
                    workspace_id=workspace_id, ctx=ctx
                )
                page = self.paginator.paginate_queryset(
                    links_qs, request, view=self
                )
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

            artifact_id = UUID(artifact_id_str)
            seen_ids: set = set()
            for direction in ("upstream", "downstream"):
                try:
                    # Fix (systemaudit 2026-08-29, Bug 1): query_trace_links()
                    # returns NeighborResult projections without the
                    # TraceLink's own primary key — this branch used to paper
                    # over that with a helper (formerly `_neighbor_to_dict`,
                    # removed) that synthesized a deterministic uuid5 from the
                    # endpoint pair. That synthetic id was never a real
                    # TraceLink row, so DELETE /tracelinks/<id>/ against it
                    # 404'd ("TraceLink <uuid> not found") in every UI that
                    # lists links via ?artifact_id= (TraceLinkPanel,
                    # ReqTraceLinkPanel). list_links_for_entity() returns the
                    # persisted TraceLink ORM rows (real .id) instead.
                    #
                    # The endpoint-echo contract from #512 must be kept
                    # as-is here: the frontend classifies each item as
                    # upstream/downstream by comparing this item's own
                    # endpoint against the *raw* artifact_id it queried with
                    # (TraceLinkPanel.tsx: `l.target_id === artifactId` /
                    # `l.source_id === artifactId`) — not the resolved
                    # Artifact id `tl.source_id`/`tl.target_id` actually
                    # stored on the row (which differ whenever the caller
                    # queried by entity id, e.g. an ADR's own `.id`, per the
                    # #512 comment on resolveArtifactRef below). Returning
                    # the raw ORM `tl.source_id`/`tl.target_id` unmodified
                    # here (as `_tracelink_to_dict` does) broke that
                    # classification — both "upstream" and "downstream"
                    # silently rendered zero links because neither endpoint
                    # id matched what the frontend queried with. Only the
                    # TraceLink's own `id` needed to become real; the
                    # endpoint-echo shape must stay exactly like before.
                    results = svc.list_links_for_entity(
                        entity_id=artifact_id,
                        direction=direction,
                        ctx=ctx,
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
                                "link_type": tl.link_type,
                                "version": tl.version,
                                "created_at": tl.created_at,
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

            # REQ-002: batch-resolve titles for all unique artifact IDs so the
            # frontend can display human-readable labels without extra requests.
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
                # UI-P3: see _tracelink_to_dict — a soft-deleted endpoint keeps
                # its link (audit trail) and must be marked, not silently
                # dropped. The *near* endpoint is the raw id the caller queried
                # with (possibly an entity id, per the #512 echo contract), so
                # it never resolves here and stays False — correct, since the
                # artifact being viewed is by definition the live one.
                item["source_is_outdated"] = bool(src.get("is_outdated", False))
                item["target_is_outdated"] = bool(tgt.get("is_outdated", False))
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: TraceLinkSerializer(item).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        # TraceLinkService does not have get_by_id — list and filter
        return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)

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
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        # REQ-002: resolve titles for both endpoints of the created link.
        titles = _resolve_artifact_titles([item.source_id, item.target_id])
        return Response(
            TraceLinkSerializer(_tracelink_to_dict(item, titles=titles)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # TraceLinks are immutable (no update semantics in spec)
        return Response(
            build_error_response("VALIDATION_ERROR", detect_lang(request), message="TraceLinks cannot be updated. Delete and recreate."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_trace_link(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="similar")
    def similar(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/similar/?tracelink_id=<uuid>&limit=10

        REQ-L2-VS-004: Returns the top-N trace links most similar to the query
        link by cosine distance over pgvector embeddings. Returns 400 when the
        link has no embedding, 503 when pgvector is unavailable.
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
            results = self._svc().find_similar_trace_links(
                trace_link_id=tracelink_id,
                ctx=ctx,
                limit=limit,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except PgVectorUnavailableError as exc:
            return Response(
                build_error_response("SERVICE_UNAVAILABLE", lang, message=str(exc)),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
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


class BaselineViewSet(BaseEntityViewSet):
    """ViewSet for Baseline CRUD operations (REQ-L2-RA-001, REQ-L2-RA-008).

    Gated by preset: Baseline endpoints return 404 in Minimal preset.
    The preset gate raises Http404 and deliberately re-raises it past DRF's
    exception handler so callers (tests, middleware) receive the raw Django
    Http404 (REQ-L3-RA004-001).
    """

    serializer_class = BaselineSerializer
    preset_endpoint_key = "baselines"

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

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/baselines/?workspace_id=<id> or /api/v1/workspaces/<workspace_id>/baselines/ — list workspace baselines.

        Issue #49: baselines were only reachable at the flat, root-level
        route, unlike Needs/Permissions/Audit/etc. which are workspace-scoped
        via a nested ``workspaces/<workspace_pk>/...`` path. The nested route
        is now registered too (rest_api/urls.py); the flat route is kept for
        backward compatibility (frontend/MCP callers use ?workspace_id=).
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
            items = self._svc().list_baselines(workspace_id=str(workspace_id), ctx=ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: BaselineSerializer(_baseline_to_dict(item)).data
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
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_baseline(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        self._check_preset(request, workspace_id=str(item.workspace_id))
        return Response(BaselineSerializer(_baseline_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/baselines/ (flat) or /api/v1/workspaces/<workspace_id>/baselines/ (nested) — create baseline.

        Issue #49: the nested-route ``workspace_pk`` URL kwarg (when present)
        takes precedence over a body-supplied ``workspace_id`` so the
        workspace-scoped route works even if the client omits the field.

        SE-Auditor gate (GH-490/GH-513): creation is refused with HTTP 400 and
        error code ``SE_AUDITOR_BLOCKED`` while the workspace has BLOCKER-level
        audit findings in the requested scope. A caller holding the ``admin``
        or ``approver`` role can override that verdict by repeating the request
        with a written ``override_reason``; the waiver is then recorded in the
        audit log and appended to the baseline description. A ``400`` with the
        plain ``VALIDATION_ERROR`` code from the same gate means the auditor
        itself could not be evaluated — that case is *not* overridable.
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
            scope = data.get("scope", "document")
            name = data.get("name", "")
            # The UI create form does not supply a name; generate one so the
            # unique-per-workspace constraint is satisfied.
            if not name or not str(name).strip():
                name = f"Baseline {timezone.now().isoformat()}"
            create_kwargs = {
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
            # document scope requires a root artifact; artifact_id is the
            # view-facing name, the facade/service expect document_id.
            artifact_id = data.get("artifact_id")
            if scope == "document" and artifact_id is None:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message="artifact_id is required for document scope",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if artifact_id is not None:
                create_kwargs["document_id"] = str(artifact_id)
            baseline_id = self._svc().create_baseline(**create_kwargs)
            # Fetch the newly created baseline detail for the response
            item = self._svc().get_baseline(baseline_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(BaselineSerializer(_baseline_to_dict(item)).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="diff")
    def diff(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/baselines/diff/?baseline_a=<uuid>&baseline_b=<uuid>

        Field-level structural diff between two baselines of the same scope
        (REQ-L2-BL-003, REQ-L2-BL-012). Both baselines must be non-equal and
        belong to the caller's tenant.
        """
        lang = detect_lang(request)

        a_str = request.query_params.get("baseline_a")
        b_str = request.query_params.get("baseline_b")
        if not a_str or not b_str:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="baseline_a and baseline_b are required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            a_id = UUID(a_str)
            b_id = UUID(b_str)
        except (ValueError, TypeError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="baseline_a and baseline_b must be valid UUIDs"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if a_id == b_id:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="baseline_a and baseline_b must differ"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            # Tenant-scoping: resolving each baseline via the tenant-scoped
            # store raises NotFoundError for baselines outside the caller's
            # tenant before the diff runs (REQ-L2-TE-011).
            baseline_a = svc.get_baseline(a_id, ctx)
            svc.get_baseline(b_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("BaselineViewSet.diff: unhandled exception")
            return _service_error_response(exc, lang)

        # Issue #398: the preset gate needs a real workspace id. This endpoint
        # carries none in its URL or query string, and the gate's tenant-id
        # fallback resolves to no workspace at all (-> bare Http404 for every
        # caller). Gate on the resolved baseline's own workspace instead —
        # outside the try/except, because the gate signals "endpoint hidden by
        # preset" with Http404, which handle_exception must re-raise verbatim.
        self._check_preset(request, workspace_id=str(baseline_a.workspace_id))

        try:
            result = svc.diff_baselines(a_id, b_id, ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("BaselineViewSet.diff: unhandled exception")
            return _service_error_response(exc, lang)

        all_item_ids = [
            *result.added,
            *result.removed,
            *(changed.id for changed in result.changed),
        ]
        artifact_names = _collect_artifact_names(all_item_ids, ctx.tenant_id)

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

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # Baselines are immutable once created
        return Response(
            build_error_response("VALIDATION_ERROR", detect_lang(request), message="Baselines are immutable. Create a new baseline instead."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # Baselines should not be deleted in normal operations
        return Response(
            build_error_response("PERMISSION_DENIED", detect_lang(request), message="Baselines cannot be deleted."),
            status=status.HTTP_403_FORBIDDEN,
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
        except Exception as exc:
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
            self._svc().transition(
                entity_id=UUID(pk),
                entity_type="Artifact",
                target_state=target_state,
                ctx=ctx,
                change_reason=change_reason,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        "acceptance_criteria": getattr(req, "acceptance_criteria", ""),
        "uid": getattr(req, "uid", None),
        "category": getattr(req, "category", ""),
        "status": getattr(req, "status", "draft"),
        "type": getattr(req, "type", None) or "SyReq",
        "complexity_fibonacci": getattr(req, "complexity_fibonacci", None),
        "verification_method": getattr(req, "verification_method", None) or None,
        "level": getattr(req, "level", None),
        "custom_fields": _artifact_custom_fields(req),
        "version": req.version,
        "created_at": req.created_at,
        "updated_at": req.modified_at,
    }


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


def _tree_node_to_dict(node: Any) -> dict[str, Any]:
    """Convert TreeNodeDTO to dict."""
    if hasattr(node, "as_dict"):
        return node.as_dict()
    return {
        "id": str(getattr(node, "id", "")),
        "artifact_type": getattr(node, "artifact_type", ""),
        "workspace_id": str(getattr(node, "workspace_id", "")),
        "parent_id": str(getattr(node, "parent_id", "")) if getattr(node, "parent_id", None) else None,
    }


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
        "custom_fields": _artifact_custom_fields(el),
        "version": el.version,
        "created_at": el.created_at,
        "updated_at": el.modified_at,
    }


def _test_to_dict(tc: Any) -> dict[str, Any]:
    """Convert TestCase ORM object to dict."""
    return {
        "id": str(tc.id),
        "workspace_id": str(tc.artifact.workspace_id) if hasattr(tc, "artifact") else None,
        "title": tc.title,
        "description": getattr(tc, "description", ""),
        "uid": getattr(tc, "uid", None),
        "status": getattr(tc, "status", "draft"),
        "steps": getattr(tc, "steps", []) or [],
        "custom_fields": _artifact_custom_fields(tc),
        "version": tc.version,
        "created_at": tc.created_at,
        "updated_at": tc.modified_at,
    }


def _resolve_artifact_titles(
    artifact_ids: list[Any],
) -> "dict[str, dict[str, Any]]":
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


def _tracelink_to_dict(tl: Any, titles: "dict[str, dict[str, Any]] | None" = None) -> dict[str, Any]:
    """Convert TraceLink ORM object to dict.

    REQ-002: When *titles* is provided the dict includes source_title,
    target_title, source_type, target_type for human-readable display.
    """
    source_id = str(tl.source_id)
    target_id = str(tl.target_id)
    d: dict[str, Any] = {
        "id": str(tl.id),
        "source_id": source_id,
        "target_id": target_id,
        "link_type": tl.link_type,
        "version": tl.version,
        "created_at": tl.created_at,
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
        "decomposition_link_type": getattr(ws, "decomposition_link_type", "parent-child"),
        "default_link_type": getattr(ws, "default_link_type", "derives-from"),
        "goals_enabled": getattr(ws, "goals_enabled", False),
        "goals_ai_enabled": getattr(ws, "goals_ai_enabled", False),
        "terminology_profile": terminology_profile,
        "language": (ws.preset or {}).get("language", "de"),  # REQ-013: language stored in preset blob
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
        "title": adr.title,
        "description": getattr(adr, "description", ""),
        "context": getattr(adr, "context", ""),
        "decision": getattr(adr, "decision", ""),
        "consequences": getattr(adr, "consequences", ""),
        "uid": getattr(adr, "uid", None),
        "status": getattr(adr, "status", "Draft"),
        "version": adr.version,
        "created_at": adr.created_at,
        "updated_at": adr.updated_at,
    }


def _risk_to_dict(risk: Any) -> dict[str, Any]:
    """Convert Risk ORM object to serializer-compatible dict."""
    return {
        "id": str(risk.id),
        "workspace_id": str(risk.workspace_id),
        "title": risk.title,
        "description": getattr(risk, "description", ""),
        "probability": getattr(risk, "probability", "low"),
        "impact": getattr(risk, "impact", "low"),
        "risk_score": getattr(risk, "risk_score", 1),
        # REQ-L1-029 (FMEA): Risk Priority Number, computed property on the model.
        "rpn": getattr(risk, "rpn", risk.risk_score),
        "severity": getattr(risk, "severity", "low"),
        "category": getattr(risk, "category", "technical"),
        "owner": getattr(risk, "owner", ""),
        "owner_user_id": str(risk.owner_user_id) if getattr(risk, "owner_user_id", None) else None,
        "owner_user_display": getattr(risk.owner_user, "email", None) if getattr(risk, "owner_user_id", None) else None,
        "detection": getattr(risk, "detection", 5),
        "mitigation_strategy": getattr(risk, "mitigation_strategy", ""),
        "uid": getattr(risk, "uid", None),
        "status": getattr(risk, "status", "Identified"),
        "version": risk.version,
        "created_at": risk.created_at,
        "updated_at": risk.updated_at,
    }


def _goal_to_dict(goal: Any) -> dict[str, Any]:
    """Convert Goal ORM object to serializer-compatible dict (Task 6)."""
    return {
        "id": str(goal.id),
        "workspace_id": str(goal.workspace_id),
        # REQ-016 / UI concept ch. 12.11 — see _arch_to_dict for the rationale.
        "artifact_id": str(goal.artifact_id) if getattr(goal, "artifact_id", None) else None,
        "lineage_id": str(goal.lineage_id),
        "sequence_number": goal.sequence_number,
        "title": goal.title,
        "description": getattr(goal, "description", ""),
        "status": getattr(goal, "status", "Entwurf"),
        "version": goal.version,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
    }


def _main_goal_to_dict(main_goal: Any) -> dict[str, Any]:
    """Convert MainGoal ORM object to serializer-compatible dict (Task 6)."""
    return {
        "id": str(main_goal.id),
        "workspace_id": str(main_goal.workspace_id),
        "sequence_number": main_goal.sequence_number,
        "content": main_goal.content,
        "source": getattr(main_goal, "source", "manual"),
        "generated_from_goal_ids": list(getattr(main_goal, "generated_from_goal_ids", []) or []),
        "status": getattr(main_goal, "status", "Entwurf"),
        "version": main_goal.version,
        "created_at": main_goal.created_at,
        "updated_at": main_goal.updated_at,
    }


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    """Convert Issue ORM object to serializer-compatible dict."""
    return {
        "id": str(issue.id),
        "workspace_id": str(issue.workspace_id),
        "title": issue.title,
        "description": getattr(issue, "description", ""),
        "severity": getattr(issue, "severity", "medium"),
        "category": getattr(issue, "category", "defect"),
        "uid": getattr(issue, "uid", None),
        "status": getattr(issue, "status", "Open"),
        "tags": issue.tags if isinstance(issue.tags, list) else [],
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
        "title": cr.title,
        "description": getattr(cr, "description", ""),
        "impact_assessment": getattr(cr, "impact_assessment", ""),
        "change_reason": getattr(cr, "change_reason", ""),
        "status": getattr(cr, "status", "draft"),
        "requestor_id": str(cr.requestor_id) if cr.requestor_id else None,
        "assigned_reviewer_id": str(cr.assigned_reviewer_id) if cr.assigned_reviewer_id else None,
        "version": cr.version,
        "created_at": cr.created_at,
        "updated_at": cr.updated_at,
    }


# ---------------------------------------------------------------------------
# WorkspaceViewSet (read-only — list + retrieve, REQ-L1-017)
# ---------------------------------------------------------------------------


class WorkspaceViewSet(BaseEntityViewSet):
    """ViewSet for Workspace lookup (REQ-L1-017).

    Read-only surface: workspaces are provisioned via seeding / admin tooling
    today. ``list`` returns all workspaces of the active tenant; ``retrieve``
    fetches a single workspace by id. Tenant scoping is enforced by
    WorkspaceService via TenantContext.
    """

    serializer_class = WorkspaceSerializer
    preset_endpoint_key = ""  # Workspaces are always visible

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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: WorkspaceSerializer(_workspace_to_dict(item)).data
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/ — fetch a single workspace by id."""
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
        return Response(WorkspaceSerializer(_workspace_to_dict(item)).data)

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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(
            WorkspaceSerializer(_workspace_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PATCH /api/v1/workspaces/{pk}/ — update workspace metadata.

        Body: {name?, language?, terminology_profile?}
        REQ-L2-RF-012: Workspace-Konfigurations-UI write path.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            ws = None

            # Lifecycle toggle: a client-sent ``is_active`` must not be silently
            # dropped. Route it to the dedicated close/reactivate service methods
            # (admin-gated, set closed_at/closed_by, emit distinct audit ops) so
            # the lifecycle logic is not duplicated or bypassed here (REQ-L1-042).
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
                if desired_active:
                    ws = self._svc().reactivate_workspace(
                        workspace_id=UUID(pk), ctx=ctx
                    )
                else:
                    ws = self._svc().close_workspace(
                        workspace_id=UUID(pk), ctx=ctx
                    )

            # SA-25: validate the supplied fields through the declared
            # serializer (partial=True — DRF's partial mode only validates and
            # returns keys actually present in the body, so this preserves the
            # original "forward only fields the client actually supplied"
            # PATCH semantics while adding real validation/sanitization,
            # notably for ``name`` (SanitizedCharField)).
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
            _patchable = (
                "name",
                "language",
                "theme",
                "decomposition_link_type",
                "default_link_type",
                "terminology_profile",
                "goals_enabled",
                "goals_ai_enabled",
            )
            fields = {
                key: value
                for key, value in patch_ser.validated_data.items()
                if key in _patchable
            }
            if fields:
                ws = self._svc().update_metadata(ctx, UUID(pk), **fields)
            elif ws is None:
                # No recognized field supplied — return current state unchanged.
                ws = self._svc().get_workspace(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(WorkspaceSerializer(_workspace_to_dict(ws)).data)

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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        """
        lang = detect_lang(request)
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
        except ValidationError as exc:
            # Captcha mismatch → 409 Conflict
            return Response(
                build_error_response(
                    "CONFLICT", lang,
                    message=str(exc),
                    details={"code": "confirmation_mismatch"},
                ),
                status=status.HTTP_409_CONFLICT,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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

    def _svc(self) -> AdrService:
        return AdrService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_adr(UUID(pk), ctx)
        return item.id, item.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_adr(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_adr(item_id, ctx)
        return {"adr": AdrSerializer(_adr_to_dict(updated)).data}

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
            items = self._svc().list_adrs(workspace_id=workspace_id, ctx=ctx, include_deleted=include_deleted)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: AdrSerializer(_adr_to_dict(item)).data
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
            item = self._svc().create_adr(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                description=data.get("description", ""),
                ctx=ctx,
                context=data.get("context", ""),
                decision=data.get("decision", ""),
                consequences=data.get("consequences", ""),
                status=data.get("status", "Draft"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data, status=status.HTTP_201_CREATED)

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
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/adrs/{pk}/ — soft-delete an ADR. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        TraceLinks pointing at the record survive the delete, and traceability
        coverage ignores outdated records.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_adr(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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

        Body: ``{superseded_by_id, change_reason?, credential?}``.
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
            item = self._svc().transition_status(
                UUID(pk),
                "Superseded",
                ctx,
                change_reason=request.data.get("change_reason") or "",
                superseded_by_id=UUID(str(superseded_by_raw)),
                credential=request.data.get("credential") or "",
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
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

    def _svc(self) -> RiskService:
        return RiskService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_risk(UUID(pk), ctx)
        return item.id, item.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_risk(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_risk(item_id, ctx)
        return {"risk": RiskSerializer(_risk_to_dict(updated)).data}

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
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: RiskSerializer(_risk_to_dict(item)).data
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
            item = self._svc().create_risk(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                probability=data.get("probability", "medium"),
                impact=data.get("impact", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "technical"),
                owner=data.get("owner", ""),
                mitigation_strategy=data.get("mitigation_strategy", ""),
                status=data.get("status", "Identified"),
                detection=data.get("detection", 5),
                owner_user_id=data.get("owner_user_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/risks/{pk}/ — update a Risk. Returns 200."""
        lang = detect_lang(request)
        invalid = self._validate_patch_payload(
            request,
            lang,
            serializer_cls=RiskSerializer,
            pk=pk,
            ctx=get_auth_context(request),
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
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_risk(
                risk_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                probability=data.get("probability"),
                impact=data.get("impact"),
                category=data.get("category"),
                owner=data.get("owner"),
                mitigation_strategy=data.get("mitigation_strategy"),
                change_reason=data.get("change_reason"),
                detection=data.get("detection"),
                owner_user_id=data.get("owner_user_id"),
                # Optimistic locking (SYSTEMAUDIT_2026-08-29, REST finding 1):
                # stale expected_version → OptimisticLockError → 409 CONFLICT.
                expected_version=data.get("expected_version"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/risks/{pk}/ — soft-delete a Risk. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        Caveat, unchanged by GH-443: unlike the other soft-deleting entities,
        this one still hard-deletes every TraceLink touching the record, so a
        later reactivate brings the record back without its links.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_risk(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)


# ---------------------------------------------------------------------------
# GoalViewSet / MainGoalViewSet — REQ-L2-TE-020 (Task 6 of feat/ziele-hauptziel-design)
# ---------------------------------------------------------------------------


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

    Returns ``(filtered_items, None)`` on success or ``(None, error_response)``
    when a parameter fails validation (HTTP 400) — callers should return the
    error response unchanged.
    """
    params = request.query_params

    status_value = params.get("status")
    if status_value:
        items = [i for i in items if getattr(i, status_field, None) == status_value]

    if source_field:
        source_value = params.get("source")
        if source_value:
            items = [i for i in items if getattr(i, source_field, None) == source_value]

    search_value = params.get("search")
    if search_value and search_fields:
        needle = search_value.lower()
        items = [
            i
            for i in items
            if any(needle in (getattr(i, f, "") or "").lower() for f in search_fields)
        ]

    ordering_value = params.get("ordering")
    if ordering_value:
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
        items = sorted(
            items, key=lambda i: getattr(i, field, None) or "", reverse=descending
        )

    limit_value = params.get("limit")
    if limit_value is not None:
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
        items = items[:limit]

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
        except Exception as exc:
            return _service_error_response(exc, lang)
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
            request, items, lambda item: GoalSerializer(_goal_to_dict(item)).data
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
        try:
            ctx = get_auth_context(request)
            result = self._svc().create_version(
                workspace_id=data["workspace_id"],
                title=data["title"],
                description=data.get("description", ""),
                lineage_id=data.get("lineage_id"),
                ctx=ctx,
            )
            item = self._svc().get(UUID(result["id"]), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        try:
            ctx = get_auth_context(request)
            item = self._svc().archive(UUID(pk), ctx, change_reason=change_reason)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
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
        try:
            ctx = get_auth_context(request)
            item = self._svc().restore(UUID(pk), ctx, change_reason=change_reason)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
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
            items = self._svc().list_all(workspace_id, ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
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
            request, items, lambda item: MainGoalSerializer(_main_goal_to_dict(item)).data
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
        except Exception as exc:
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
        except Exception as exc:
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
            self._svc().approve(UUID(pk), ctx, change_reason=change_reason)
            # Return the FULL serialized MainGoal (not the service's bare
            # {id, sequence_number, status} dict), matching create/generate/
            # current — the frontend replaces its panel state with this
            # response and would otherwise blank out `content`.
            item = self._svc().get(UUID(pk), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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

    def _svc(self) -> IssueService:
        return IssueService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_issue(UUID(pk), ctx)
        return item.id, item.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_issue(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_issue(item_id, ctx)
        return {"issue": IssueSerializer(_issue_to_dict(updated)).data}

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
            )
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: IssueSerializer(_issue_to_dict(item)).data
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
            item = self._svc().create_issue(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                severity=data.get("severity", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "defect"),
                tags=data.get("tags"),
                status=data.get("status", "Open"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/issues/{pk}/ — soft-delete an Issue. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        Caveat, unchanged by GH-443: unlike the other soft-deleting entities,
        this one still hard-deletes every TraceLink touching the record, so a
        later reactivate brings the record back without its links.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_issue(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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

    def _svc(self) -> ChangeRequestService:
        return ChangeRequestService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        item = self._svc().get_change_request(UUID(pk), ctx)
        return item.id, item.workspace_id

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        return getattr(self._svc().get_change_request(UUID(pk), ctx), "status", None)

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict:
        updated = self._svc().get_change_request(item_id, ctx)
        return {"change_request": ChangeRequestSerializer(_cr_to_dict(updated)).data}

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
        except Exception as exc:
            return _service_error_response(exc, lang)
        return self._paginate(
            request, items, lambda item: ChangeRequestSerializer(_cr_to_dict(item)).data
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
            item = self._svc().create_change_request(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                impact_assessment=data.get("impact_assessment", ""),
                change_reason=data.get("change_reason", ""),
                assigned_reviewer_id=data.get("assigned_reviewer_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ChangeRequestSerializer(_cr_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/change-requests/{pk}/ — soft-delete a CR. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 with ``status="outdated"`` — 404 keeps meaning "no such
        record, and there never was one in this tenant". List endpoints hide
        outdated records by default; pass ``?include_deleted=true`` to see
        them, and ``POST .../reactivate/`` to restore one.

        TraceLinks pointing at the record survive the delete, and traceability
        coverage ignores outdated records.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_change_request(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
            item = self._svc().transition_status(
                cr_id=UUID(pk),
                target_status=target_status,
                ctx=ctx,
                change_reason=change_reason or None,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
            except Exception as exc:
                return _service_error_response(exc, lang)
            return Response([_test_run_result_to_dict(r) for r in run.results.all()])

        # POST — add a single result (existing behaviour)
        lang = detect_lang(request)
        test_case_id = request.data.get("test_case_id")
        status_val = request.data.get("status", "not_run")
        if not test_case_id:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="test_case_id is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            result = self._svc().add_result(
                test_run_id=UUID(pk),
                test_case_id=UUID(str(test_case_id)),
                status=str(status_val),
                ctx=ctx,
                message=str(request.data.get("message", "")),
                duration_ms=request.data.get("duration_ms"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(_test_run_result_to_dict(result), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="results/bulk")
    def results_bulk(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/results/bulk/ — add multiple results (CI-friendly)."""
        lang = detect_lang(request)
        results_data = request.data.get("results", [])
        if not results_data or not isinstance(results_data, list):
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
        except Exception as exc:
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
# SearchViewSet — Full-text search across Requirements, ArchitectureElements,
# and TestCases (COMP-AS-010 SearchService).
# REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009
# ---------------------------------------------------------------------------


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
        ],
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
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
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
        return Response(
            {
                "results": serialized_hits,
                "total_count": result.total_count,
                "page": result.page,
                "limit": result.limit,
                "query": result.query,
            }
        )


# ---------------------------------------------------------------------------
# CsvImportView — COMP-AS-009 REST facade (REQ-L0-013, REQ-L2-AS-014)
# ---------------------------------------------------------------------------


class CsvImportView(APIView):
    """POST /api/v1/workspaces/{id}/import/csv/ — Bulk CSV import.

    REQ-L0-013: Effiziente Übernahme bestehender Anforderungsdaten.
    REQ-L2-AS-014: CSV Bulk Import (ApplicationService layer).
    REQ-L2-RF-016: Frontend CSV import UI.

    Body: multipart/form-data with:
        - ``file``: CSV file (RFC 4180, UTF-8).
        - ``entity_type``: "Requirement" | "ArchitectureElement" | "TestCase"

    Returns:
        201 with ImportResult summary on success.
        400 with validation errors (missing file, bad entity_type, malformed CSV,
        row limit exceeded, per-row validation failures).
    """

    _VALID_ENTITY_TYPES = {"Requirement", "ArchitectureElement", "TestCase"}

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
        except Exception as exc:
            return _service_error_response(exc, lang)

        # --- Validate entity_type ---
        entity_type = request.data.get("entity_type")
        if not entity_type:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="entity_type is required. Allowed: Requirement, ArchitectureElement, TestCase",
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

        # --- Validate file ---
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="No CSV file uploaded. Provide a 'file' field in multipart/form-data.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read file content (UTF-8)
        try:
            csv_text = uploaded_file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="CSV file must be UTF-8 encoded.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not csv_text.strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="CSV file is empty.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Delegate to ImportService ---
        try:
            svc = ImportService()
            result = svc.import_csv(
                csv_text=csv_text,
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
            logger.exception("CsvImportView: unhandled exception")
            return _service_error_response(exc, lang)

        # --- Build response ---
        response_data = {
            "success": result.success,
            "imported_count": result.imported_count,
            "skipped_count": result.skipped_count,
            "status": result.status,
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

        http_status = status.HTTP_201_CREATED if result.success else status.HTTP_400_BAD_REQUEST
        return Response(response_data, status=http_status)


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
        except Exception as exc:
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
        except Exception as exc:
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

    Query params:
        - ``dry_run``: "true" | "false" (default "false"). When true, the
          whole import pipeline runs and is rolled back — the response
          report reflects what a real import would do without persisting.

    Returns:
        200 with the import report (counts + errors per entity kind, plus
        relation counts and warnings) on success, including dry-run.
        400 on a hard error (missing/empty file, unparseable XML, ReqIF
        structural violation) — nothing is persisted.
    """

    def post(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """Handle ReqIF import POST request."""
        lang = detect_lang(request)

        if not pk:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Workspace ID is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:
            return _service_error_response(exc, lang)

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="No ReqIF file uploaded. Provide a 'file' field in multipart/form-data.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reqif_text = uploaded_file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="ReqIF file must be UTF-8 encoded.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not reqif_text.strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="ReqIF file is empty.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        dry_run_raw = request.query_params.get("dry_run", "false")
        dry_run = str(dry_run_raw).strip().lower() in ("1", "true", "yes")

        try:
            svc = ReqifImportService()
            result = svc.import_reqif(
                reqif_text=reqif_text,
                workspace_id=pk,
                ctx=ctx,
                dry_run=dry_run,
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
            logger.exception("ReqifImportView: unhandled exception")
            return _service_error_response(exc, lang)

        return Response(result.to_dict(), status=status.HTTP_200_OK)


class GlossaryTermViewSet(WorkflowTransitionsMixin, BaseEntityViewSet):
    """ViewSet for Semantic Project Glossary (REQ-L1-044).

    REQ-173: transitions/ and workflow-history/ via WorkflowTransitionsMixin
    so glossary terms share the same lifecycle machinery as every other
    artifact type.
    """

    serializer_class = GlossaryTermSerializer
    workflow_item_type = "GlossaryTerm"

    def _svc(self) -> GlossaryService:
        return GlossaryService()

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        term = self._svc().get(ctx, UUID(pk))
        return term.id, term.workspace_id

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
            terms = self._svc().list_by_workspace(ctx, workspace_id, include_deleted=include_deleted)
            return self._paginate(
                request, terms, lambda t: GlossaryTermSerializer(t).data
            )
        except Exception as e:
            logger.exception("Error in GlossaryTermViewSet.list")
            return _service_error_response(e, lang)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        try:
            term_id = UUID(pk)
            term = self._svc().get(ctx, term_id)
            return Response(GlossaryTermSerializer(term).data)
        except Exception as e:
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
            term = self._svc().create(
                ctx,
                data["workspace_id"],
                data["term"],
                data["definition"],
                data.get("synonyms"),
                data.get("abbreviation", ""),
            )
            return Response(
                GlossaryTermSerializer(term).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return _service_error_response(e, lang)

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
            )
            return Response(GlossaryTermSerializer(term).data)
        except Exception as e:
            return _service_error_response(e, lang)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/glossary/{pk}/ — soft-delete a glossary term. Returns 204.

        Soft-delete: returns 204, but the record is NOT removed. Its workflow
        state moves to "outdated" and a subsequent GET on this URL still
        answers 200 — 404 keeps meaning "no such record, and there never was
        one in this tenant". List endpoints hide outdated records by default;
        pass ``?include_deleted=true`` to see them, and
        ``POST .../reactivate/`` to restore one.

        Note the field name: GlossaryTerm has no mirrored ``status`` column
        (``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``), so the detail
        response reports the soft-delete as ``lifecycle_status="outdated"``
        where the other entities use ``status="outdated"`` (issue #440).
        """
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        try:
            term_id = UUID(pk)
            self._svc().delete(ctx, term_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return _service_error_response(e, lang)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/glossary/{pk}/versions/ — list GlossaryTermVersions
        chronologically.

        REQ-142: delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = ArtifactDiffService().list_versions_for_glossary_term(
                UUID(pk), ctx
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/glossary/{pk}/diff/?from_version=0&to_version=2

        REQ-142: Structured field-level diff between two GlossaryTermVersions.
        Delegates to ArtifactDiffService (COMP-AS-019); reuses the same
        diff computation as the requirement diff endpoint.
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

            result = ArtifactDiffService().diff_for_glossary_term(
                term_id=term_id,
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
            return _service_error_response(exc, lang)
        return Response(result)


class AttributeSchemaView(APIView):
    """GET /api/v1/attribute-schema/?entity_type=<optional>

    Requirement Bundle Export, Plan 1 Task 5 / Task 4. Lists the known
    attribute names per entity type (currently Requirement only), with each
    attribute's current tenant-level visibility, so callers can discover
    valid field names before making a filter_mode='custom' bundle-export
    request.
    """

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            entity_type = request.query_params.get("entity_type")
            schema = AttributeVisibilityConfigService().describe_schema(
                ctx, entity_type=entity_type
            )
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(schema)


class AttributeVisibilityConfigViewSet(BaseEntityViewSet):
    """ViewSet for AttributeVisibilityConfig (REQ-L1-058 AC2).

    Admin CRUD for field visibility configuration per entity type and workspace.
    Endpoint: /api/v1/attribute-visibility-config/

    Permissions: tenant admins only, enforced by
    AttributeVisibilityConfigService itself (ServiceBase._assert_permission,
    "admin") on every method — NOT by BaseEntityViewSet, which provides no
    role gate of its own (code review finding: this docstring's previous
    claim was inaccurate, and every service method was in fact unguarded;
    any authenticated user of any role could create/update/delete/bulk-
    upsert tenant-wide visibility config).
    """

    serializer_class = AttributeVisibilityConfigSerializer

    def _svc(self):
        """Return the AttributeVisibilityConfigService (REQ-066)."""
        from application.attribute_visibility_service import (
            AttributeVisibilityConfigService,
        )
        return AttributeVisibilityConfigService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/attribute-visibility-config/ — list all visibility configs."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            configs = self._svc().list_configs(ctx)
            serializer = AttributeVisibilityConfigSerializer(configs, many=True)
            return Response(serializer.data)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("AttributeVisibilityConfigViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=False, methods=["post"])
    def bulk_update(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/attribute-visibility-configs/bulk_update/ — upsert configs."""
        lang = detect_lang(request)
        if not isinstance(request.data, list):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Expected a list of configs"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)

            validated_items: list[dict[str, Any]] = []
            for item in request.data:
                item_data = dict(item)
                item_data["tenant_id"] = str(ctx.tenant_id)
                ser = AttributeVisibilityConfigSerializer(data=item_data)
                if not ser.is_valid():
                    return Response(
                        build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                validated_items.append(dict(ser.validated_data))

            results = self._svc().bulk_upsert(ctx, validated_items)
            return Response(AttributeVisibilityConfigSerializer(results, many=True).data, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.exception("AttributeVisibilityConfigViewSet.bulk_update: unhandled exception")
            return _service_error_response(exc, lang)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/attribute-visibility-config/ — create config. Returns 201."""
        lang = detect_lang(request)
        ser = AttributeVisibilityConfigSerializer(data=request.data)
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

            config = self._svc().create_config(
                ctx,
                entity_type=data["entity_type"],
                attribute_name=data["attribute_name"],
                is_visible=data.get("is_visible", True),
                is_required=data.get("is_required", False),
            )
            return Response(
                AttributeVisibilityConfigSerializer(config).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            logger.exception("AttributeVisibilityConfigViewSet.create: unhandled exception")
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/attribute-visibility-config/{pk}/ — update config. Returns 200."""
        lang = detect_lang(request)
        ser = AttributeVisibilityConfigSerializer(data=request.data, partial=True)
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
            config = self._svc().update_config(
                ctx,
                UUID(pk),
                is_visible=data.get("is_visible") if "is_visible" in data else None,
                is_required=data.get("is_required") if "is_required" in data else None,
            )
            return Response(AttributeVisibilityConfigSerializer(config).data)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("AttributeVisibilityConfigViewSet.partial_update: unhandled exception")
            return _service_error_response(exc, lang)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/attribute-visibility-config/{pk}/ — delete config. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_config(ctx, UUID(pk))
            return Response(status=status.HTTP_204_NO_CONTENT)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("AttributeVisibilityConfigViewSet.destroy: unhandled exception")
            return _service_error_response(exc, lang)


# ---------------------------------------------------------------------------
# REQ-016: Custom Fields (workspace-wide definitions + per-artifact values)
# ---------------------------------------------------------------------------


def _validate_custom_value(definition: Any, value: str, lang: str) -> Response | None:
    """Validate a single custom-field ``value`` against its ``definition``.

    Returns a 400 error Response when invalid, or ``None`` when the value is
    acceptable. Empty values are allowed here; required-field enforcement is
    handled by the caller so partial saves are not rejected outright.
    """
    if value == "":
        return None
    if definition.field_type == "number":
        try:
            float(value)
        except (TypeError, ValueError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": "value", "errors": [f"'{value}' is not a valid number."]}],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif definition.field_type == "dropdown":
        if value not in (definition.options or []):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": "value", "errors": [f"'{value}' is not a valid option."]}],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
    return None


class CustomFieldDefinitionViewSet(BaseEntityViewSet):
    """ViewSet for workspace-wide custom field definitions (REQ-016).

    - ``list``   GET  /api/v1/workspaces/<workspace_pk>/custom-field-definitions/
                 — any authenticated tenant member (needed to render forms).
    - ``create`` POST same path — workspace admins only.
    - ``partial_update`` PATCH /api/v1/custom-field-definitions/<pk>/ — admins only.
    - ``destroy`` DELETE /api/v1/custom-field-definitions/<pk>/ — admins only.
    """

    serializer_class = CustomFieldDefinitionSerializer

    def _svc(self):
        """Return the CustomFieldService (REQ-066)."""
        from application.custom_field_service import CustomFieldService
        return CustomFieldService()

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message="Admin role required."),
            status=status.HTTP_403_FORBIDDEN,
        )

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET workspace custom field definitions, ordered by (order, name)."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)  # ensure authenticated
            workspace_id = kwargs["workspace_pk"]
            defs = self._svc().list_definitions(ctx, workspace_id)
            return Response(CustomFieldDefinitionSerializer(defs, many=True).data)
        except Exception as exc:
            logger.exception("CustomFieldDefinitionViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST a new definition to a workspace (admin only). Returns 201."""
        from auth_tenancy.models import ROLE_ADMIN
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        ser = CustomFieldDefinitionSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            workspace_id = kwargs["workspace_pk"]
            definition = self._svc().create_definition(
                ctx,
                workspace_id,
                name=data["name"],
                field_type=data.get("field_type", "text"),
                is_required=data.get("is_required", False),
                options=data.get("options", []),
                order=data.get("order", 0),
            )
            return Response(
                CustomFieldDefinitionSerializer(definition).data,
                status=status.HTTP_201_CREATED,
            )
        except (NotFoundError, ValidationError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("CustomFieldDefinitionViewSet.create: unhandled exception")
            return _service_error_response(exc, lang)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH an existing definition (admin only). Returns 200."""
        from auth_tenancy.models import ROLE_ADMIN
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        try:
            definition = self._svc().get_definition(ctx, pk)
        except NotFoundError:
            return Response(
                build_error_response("NOT_FOUND", lang, message=f"Definition {pk} not found"),
                status=status.HTTP_404_NOT_FOUND,
            )

        ser = CustomFieldDefinitionSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        # Guard: a dropdown must always keep at least one option.
        effective_type = data.get("field_type", definition.field_type)
        effective_options = data.get("options", definition.options)
        if effective_type == "dropdown" and not effective_options:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": "options", "errors": ["Dropdown fields require at least one option."]}]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            definition = self._svc().update_definition(ctx, pk, dict(data))
            return Response(CustomFieldDefinitionSerializer(definition).data)
        except (NotFoundError, ValidationError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("CustomFieldDefinitionViewSet.partial_update: unhandled exception")
            return _service_error_response(exc, lang)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE a definition and its values (admin only). Returns 204."""
        from auth_tenancy.models import ROLE_ADMIN
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            self._svc().delete_definition(ctx, pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except NotFoundError:
            return Response(
                build_error_response("NOT_FOUND", lang, message=f"Definition {pk} not found"),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("CustomFieldDefinitionViewSet.destroy: unhandled exception")
            return _service_error_response(exc, lang)


class ArtifactCustomFieldValuesView(APIView):
    """Read/write custom field values for a single artifact (REQ-016).

    - GET  /api/v1/artifacts/<pk>/custom-field-values/
           → the artifact's workspace definitions merged with current values.
    - PUT  /api/v1/artifacts/<pk>/custom-field-values/
           body: ``[{"definition_id": "...", "value": "..."}]`` — upserts values.

    Any authenticated tenant member may read and write values (form filling).
    """

    def _svc(self):
        """Return the CustomFieldService (REQ-066)."""
        from application.custom_field_service import CustomFieldService
        return CustomFieldService()

    def get(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            workspace_id = svc.get_artifact_workspace_id(ctx, pk)
            return Response(svc.merged_rows(ctx, workspace_id, pk))
        except NotFoundError:
            return Response(
                build_error_response("NOT_FOUND", lang, message="Artifact not found"),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("ArtifactCustomFieldValuesView.get: unhandled exception")
            return _service_error_response(exc, lang)

    def put(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        if not isinstance(request.data, list):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Expected a list of {definition_id, value}."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            svc = self._svc()
            workspace_id = svc.get_artifact_workspace_id(ctx, pk)
            defs = svc.get_definitions_map(ctx, workspace_id)

            # Phase 1: validate every item without touching the database. This is
            # side-effect free, so validating up front is equivalent to the former
            # interleaved-and-rollback flow while keeping HTTP concerns in the view.
            operations: list[tuple[str, str]] = []
            for item in request.data:
                did = str(item.get("definition_id", ""))
                raw = item.get("value")
                value = "" if raw is None else str(raw)
                definition = defs.get(did)
                if definition is None:
                    return Response(
                        build_error_response("VALIDATION_ERROR", lang, details=[{"field": "definition_id", "errors": [f"Unknown definition {did} for this workspace."]}]),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if value == "" and definition.is_required:
                    return Response(
                        build_error_response("VALIDATION_ERROR", lang, details=[{"field": definition.name, "errors": ["This field is required."]}]),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                err = _validate_custom_value(definition, value, lang)
                if err is not None:
                    return err
                operations.append((did, value))

            # Phase 2: persist all operations atomically.
            svc.apply_values(ctx, pk, operations)
            return Response(svc.merged_rows(ctx, workspace_id, pk))
        except NotFoundError:
            return Response(
                build_error_response("NOT_FOUND", lang, message="Artifact not found"),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("ArtifactCustomFieldValuesView.put: unhandled exception")
            return _service_error_response(exc, lang)


__all__ = [
    "StakeholderNeedViewSet",
    "RequirementViewSet",
    "ArtifactViewSet",
    "ArchitectureElementViewSet",
    "TestCaseViewSet",
    "TraceLinkViewSet",
    "TraceabilityViewSet",
    "BaselineViewSet",
    "WorkflowDefinitionViewSet",
    "WorkspaceViewSet",
    "AdrViewSet",
    "RiskViewSet",
    "IssueViewSet",
    "AttributeVisibilityConfigViewSet",
    "CustomFieldDefinitionViewSet",
    "ArtifactCustomFieldValuesView",
    "SearchViewSet",
    "CsvImportView",
    "CsvExportView",
    "ReqifExportView",
    "ArtifactDiffService",
]
