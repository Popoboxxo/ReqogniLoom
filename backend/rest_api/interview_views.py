"""REST facade for interview.* (Interview-Management Web Widget spec §3.1).

Thin adapter over application.interview_service.InterviewService, the
same service the interview.* MCP tool group wraps -- same dual-protocol
pattern already used for requirement_bundle (see
rest_api/views.py:RequirementBundleQueryService usage). No business logic
lives here (REQ-L3-RA001-004): every handler below just translates HTTP
in/out around a single InterviewService call.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from application.interview_service import InterviewService
from rest_api.mixins.free_text_sanitization import FreeTextSanitizationMixin
from rest_api.query_params import parse_uuid_param
from rest_api.views import (
    _service_error_response,
    detect_lang,
    get_auth_context,
    parse_workspace_id,
)

#: Every ApplicationService exception InterviewService can raise, mapped to
#: HTTP codes by rest_api.views._service_error_response. Grouped once here
#: (instead of per-handler tuples) so every action's except clause stays in
#: sync if a new InterviewService method starts raising one of these.
_SERVICE_EXCEPTIONS = (ValidationError, NotFoundError, PermissionDeniedError, OptimisticLockError)


def _session_to_dict(
    session: Any, status_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Bare session summary -- used by list()/retrieve(), which don't need
    the full get_state() computation (phase/missing_fields/grounding).

    Datenmodell-Konsolidierung Phase 1: ``status`` is no longer written by
    the workflow engine, so it must be resolved through
    ``workflow.state_reader``. Task 12: the column itself is dropped.
    ``retrieve()`` hands this a *session* that already went through
    ``InterviewService.get()`` -> ``InterviewService._get_session()``, which
    resolves ``.status`` in memory before returning -- no *status_map* needed
    there. ``list()`` iterates a raw queryset, so it passes a pre-batched
    *status_map* (mirrors ``mcp_server.tools.interview._session_to_dict``/
    ``resolve_engine_status`` — same seam, REST just resolves it inline
    instead of importing the MCP-layer helper); ``session.status`` is never
    read in that branch, since a raw queryset row (unlike the
    ``_get_session()`` case) has no in-memory value to read -- it would raise
    ``AttributeError`` now that the column is gone.
    """
    if status_map is not None:
        from workflow import state_reader

        resolved_status = status_map.get(str(session.id)) or state_reader.initial_state(
            "Interview"
        )
    else:
        resolved_status = session.status
    return {
        "id": str(session.id),
        "workspace_id": str(session.workspace_id),
        "artifact_type": session.artifact_type,
        "status": resolved_status,
    }


def _state_dict(ctx: Any, session_id: UUID) -> dict[str, Any]:
    """InterviewService.get_state()'s dict, normalised to an "id" key.

    get_state() itself returns "session_id" (its own internal convention,
    shared with the MCP tool group) -- the REST facade exposes "id" instead
    to match every other ViewSet's response shape. Both callers of this
    helper (create/state/answer/chat) need the identical normalisation, so
    it is factored out here rather than repeated at each call site.
    """
    result = InterviewService().get_state(ctx, session_id)
    result["id"] = result.pop("session_id")
    return result


def _started_session_state(ctx: Any, session: Any) -> dict[str, Any]:
    """State payload for a freshly started interview session (REST create()).

    Multi-kind sessions deliberately bypass InterviewService.get_state():
    it resolves the per-artifact-type protocol via get_protocol(), which
    has no answer for a multi session's ``artifact_type=None``
    (ProtocolValidationError -- proven in multi-artifact plan Tasks 5/6,
    and ProtocolValidationError is not in _SERVICE_EXCEPTIONS, so the
    unguarded _state_dict() call in create() would surface as a 500).
    Same decision as the MCP facade's InterviewToolGroup
    ._started_session_state (Task 6): inline state mirroring
    InterviewService._generate_multi_chat_turn's shape minus phase/
    missing_fields, which do not exist in multi mode. Single-kind
    sessions keep the unchanged _state_dict()/get_state() path.

    Key-naming note: unlike the MCP handler this helper already emits the
    REST-facade "id" key (not "session_id"), matching the _state_dict()
    normalisation every other action in this ViewSet answers with.
    """
    # Literal, not persistence.models.InterviewSession.SESSION_KIND_MULTI:
    # this view module is guarded by test_architecture.py's
    # no-model-import ratchet (interview_views.py is not allowlisted), and
    # "multi" is the stable DB-choice value InterviewSession.SESSION_KIND_MULTI
    # stores -- same literal the REST callers send as session_kind.
    if session.session_kind == "multi":
        # Task 12: *session* here is the bare object InterviewService.start()
        # just created, not one resolved through _get_session() -- it has no
        # in-memory ``.status`` to read (the column is dropped), so resolve
        # via the engine directly, same fallback as InterviewService._get_session.
        from workflow import state_reader

        resolved_status = state_reader.current_state(
            "Interview", session.id
        ) or state_reader.initial_state("Interview")
        return {
            "id": str(session.id),
            "status": resolved_status,
            # Same key get_state() emits in both its branches (final-review
            # finding B2): this inline payload is the one multi-mode state a
            # client sees that never passes through get_state(), so it has to
            # carry the discriminator too or the shape silently differs.
            "session_kind": session.session_kind,
            "collected_fields": session.collected_fields,
            "grounding_snapshot": session.grounding_snapshot,
            "transcript": session.transcript,
        }
    return _state_dict(ctx, session.id)


# ---------------------------------------------------------------------------
# Contract serializers (#1388)
# ---------------------------------------------------------------------------
#
# Contract-only. Every handler below hands ``InterviewService``'s dict straight
# to ``Response`` (``_session_to_dict`` / ``_state_dict`` /
# ``_started_session_state`` only rename ``session_id`` to ``id``), and that
# stays exactly as it is — these serializers transcribe the dicts for the
# generated document only.


class InterviewSessionSummarySerializer(serializers.Serializer):
    """Bare session summary (``_session_to_dict``)."""

    id = serializers.CharField()
    workspace_id = serializers.CharField()
    #: ``null`` for a multi-kind session: it targets several artifact types.
    artifact_type = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField()


class InterviewSessionListResponseSerializer(serializers.Serializer):
    """``GET /interviews/`` — AUD-112 explicit ``count`` + the (unpaginated) rows."""

    count = serializers.IntegerField()
    results = InterviewSessionSummarySerializer(many=True)


class InterviewStartRequestSerializer(serializers.Serializer):
    """Body of ``POST /interviews/``.

    ``artifact_type`` is omitted for a multi-kind discovery session; an unknown
    ``session_kind`` is rejected by the service, not here.
    """

    workspace_id = serializers.UUIDField()
    artifact_type = serializers.CharField(required=False, allow_null=True)
    session_kind = serializers.ChoiceField(
        choices=["single", "multi"], required=False, default="single"
    )


class InterviewStateSerializer(serializers.Serializer):
    """``InterviewService.get_state()``, keyed by ``id`` instead of ``session_id``.

    One component for both session kinds: ``phase``/``missing_fields`` exist only
    for a single-kind session, ``transcript_summary`` only for single-kind chat
    turns (compression never runs in multi mode), and the multi-only chat turn
    omits the pair entirely — hence ``required=False`` throughout.
    """

    id = serializers.CharField()
    status = serializers.CharField()
    #: "single" or "multi"; the discriminator every consumer branches on.
    session_kind = serializers.CharField(required=False)
    phase = serializers.CharField(required=False)
    collected_fields = serializers.DictField(required=False)
    #: Protocol field descriptors of the current phase's still-open fields.
    missing_fields = serializers.ListField(child=serializers.JSONField(), required=False)
    #: ``{"candidates": [...]}``; the entries are grounding snapshots.
    grounding_snapshot = serializers.DictField(required=False, allow_null=True)
    transcript = serializers.ListField(child=serializers.JSONField(), required=False)
    transcript_summary = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class InterviewByArtifactResponseSerializer(serializers.Serializer):
    """``GET /interviews/by-artifact/{artifact_id}/`` — provenance lookup."""

    session_id = serializers.CharField(required=False, allow_null=True)


class InterviewAnswerRequestSerializer(serializers.Serializer):
    """Body of ``POST /interviews/{id}/answer/``."""

    field = serializers.CharField()
    #: Data type follows the field's declaration, so it stays free-form.
    value = serializers.JSONField(allow_null=True)


class InterviewFormalizeRequestSerializer(serializers.Serializer):
    """Body of ``POST /interviews/{id}/formalize/``.

    ``confirmed_proposal`` is required for a multi-kind session and ignored by a
    single-kind one (whose artifacts come from the protocol's collected fields).
    """

    confirmed_proposal = serializers.ListField(
        child=serializers.JSONField(), required=False, allow_null=True
    )


class InterviewFormalizeResponseSerializer(serializers.Serializer):
    """Union of the single-kind and multi-kind ``formalize()`` results.

    A single-kind session answers ``resulting_artifact_ids``; a multi-kind one
    answers ``created``. ``status`` is always present.
    """

    status = serializers.CharField()
    resulting_artifact_ids = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    created = serializers.ListField(child=serializers.JSONField(), required=False)


class InterviewProposalResponseSerializer(serializers.Serializer):
    """``GET /interviews/{id}/propose/`` — the pending proposal, if any."""

    proposal = serializers.ListField(
        child=serializers.JSONField(), required=False, allow_null=True
    )


class InterviewChatRequestSerializer(serializers.Serializer):
    """Body of ``POST /interviews/{id}/chat/``."""

    message = serializers.CharField(required=False, allow_blank=True)


class InterviewChatResponseSerializer(serializers.Serializer):
    """``POST /interviews/{id}/chat/`` — one server-generated turn."""

    reply = serializers.CharField()
    state = InterviewStateSerializer()
    #: Multi-kind sessions only: a newly parsed artifact proposal.
    proposal = serializers.ListField(
        child=serializers.JSONField(), required=False, allow_null=True
    )


class InterviewAbandonResponseSerializer(serializers.Serializer):
    """``POST /interviews/{id}/abandon/`` — the session's new status."""

    status = serializers.CharField()


class InterviewSetTargetRequestSerializer(serializers.Serializer):
    """Body of ``POST /interviews/{id}/set_target/``."""

    artifact_id = serializers.UUIDField()


class InterviewGroundingResponseSerializer(serializers.Serializer):
    """``GET /interviews/{id}/grounding/`` — ``{"candidates": [...]}``.

    The candidate entries are produced by the structural matcher and (when a
    real provider is configured) AI-ranked on top, so they stay free-form.
    """

    candidates = serializers.ListField(child=serializers.JSONField())


class InterviewViewSet(FreeTextSanitizationMixin, viewsets.ViewSet):
    """ViewSet for /api/v1/interviews/ -- start/list/get/state/answer/grounding/formalize/chat.

    Not a BaseEntityViewSet subclass: InterviewSession is not a generic
    Artifact-backed entity (no serializer, no workflow, no soft-delete), so
    the shared CRUD scaffolding would add nothing here -- same reasoning as
    SearchViewSet, which is also a plain viewsets.ViewSet wrapping a single
    ApplicationService. Malformed-UUID-400 is already handled per-action via
    ``parse_uuid_param`` (see state()/answer()/... below), which is why this
    class does not additionally need BaseEntityViewSet's
    ``uuid_url_kwargs``/``initial()`` mechanism -- routing a PATCH/DELETE onto
    a stub that raises NotImplementedError (as inheriting BaseEntityViewSet
    verbatim would) is exactly the fix #235 regression class, and this
    ViewSet genuinely has no update/destroy semantics.

    SA-20: ``FreeTextSanitizationMixin`` *is* composed in on its own --
    answer()'s ``value`` and chat()'s ``message`` are free-form, persisted
    user prose (session transcript / collected_fields) with no serializer in
    front of them, the same "read request.data straight into a service call"
    shape #269 finding 4 flagged. No preset feature key for interview
    endpoints exists in presets.registry.FEATURE_KEYS, so there is nothing to
    wire up for a Preset-Gate here yet.
    """

    free_text_extra_fields = ("value", "message")

    @extend_schema(
        summary="Start an interview session",
        description=(
            "Starts a single-kind session for a named `artifact_type`, or a "
            "multi-kind discovery session when `artifact_type` is omitted."
        ),
        request=InterviewStartRequestSerializer,
        responses={
            201: InterviewStateSerializer,
            400: OpenApiResponse(
                description="Invalid workspace_id, unknown session_kind/artifact_type, or protocol violation."
            ),
            403: OpenApiResponse(description="Write role required in the workspace."),
        },
    )
    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/ -- start a new interview session."""
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            session = InterviewService().start(
                ctx,
                request.data.get("artifact_type"),
                workspace_id,
                # Review-2 fix m2b: `or "single"` (not the .get default) so an
                # explicitly-null/empty session_kind in JSON also normalises to
                # single instead of reaching start() as None. Valid values
                # ("single"/"multi") pass through unchanged -- same
                # falsy-normalisation the MCP facade's _handle_start already
                # applies; unknown non-empty values are rejected by the
                # service-side whitelist gate.
                session_kind=request.data.get("session_kind") or "single",
            )
            result = _started_session_state(ctx, session)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="interviews_list",
        description=(
            "List interview sessions for a workspace. Explicit list id to keep "
            "it distinct from the session retrieve (#1388)."
        ),
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose sessions are listed.",
            ),
            OpenApiParameter(
                "status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional lifecycle-state filter.",
            ),
        ],
        responses={
            200: InterviewSessionListResponseSerializer,
            400: OpenApiResponse(description="workspace_id missing or not a valid UUID."),
        },
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/?workspace_id=...[&status=...] -- list sessions."""
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.query_params.get("workspace_id"), lang)
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            sessions = list(
                InterviewService().list_sessions(
                    ctx, workspace_id, status=request.query_params.get("status")
                )
            )
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        from workflow import state_reader

        status_map = state_reader.current_states("Interview", (s.id for s in sessions))
        # AUD-112: expose a `count` so clients that only trust the DRF count
        # field (e.g. the Hermes Python plugin's stats()) never mistake one
        # page length for a total or degrade `open interviews` to None. The
        # list itself is not paginated, so count == len(results) and there is
        # no next/previous link.
        return Response(
            {
                "count": len(sessions),
                "results": [_session_to_dict(s, status_map=status_map) for s in sessions],
            }
        )

    @extend_schema(
        summary="Resolve the interview session that created an artifact",
        responses={
            200: InterviewByArtifactResponseSerializer,
            400: OpenApiResponse(description="artifact_id is not a valid UUID."),
        },
    )
    @action(detail=False, methods=["get"], url_path="by-artifact/(?P<artifact_id>[^/.]+)")
    def by_artifact(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/by-artifact/{artifact_id}/ -- provenance lookup.

        Resolves the multi-mode interview session that created *artifact_id*
        via InterviewService.provenance_session_id(); answers
        ``{"session_id": null}`` for artifacts without an interview
        provenance row instead of 404, so callers can distinguish "exists,
        not interview-created" from "unknown endpoint".
        """
        lang = detect_lang(request)
        parsed_artifact_id, error = parse_uuid_param(artifact_id, lang, name="artifact_id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            session_id = InterviewService().provenance_session_id(ctx, parsed_artifact_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response({"session_id": session_id})

    @extend_schema(
        summary="Read a session's bare summary",
        responses={
            200: InterviewSessionSummarySerializer,
            400: OpenApiResponse(description="id is not a valid UUID."),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/{id}/ -- bare session summary."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            session = InterviewService().get(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(_session_to_dict(session))

    @extend_schema(
        summary="Read the full interview state snapshot",
        responses={
            200: InterviewStateSerializer,
            400: OpenApiResponse(description="id is not a valid UUID."),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["get"], url_path="state")
    def state(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/{id}/state/ -- full get_state() snapshot."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = _state_dict(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        summary="Answer one protocol field of the current phase",
        request=InterviewAnswerRequestSerializer,
        responses={
            200: InterviewStateSerializer,
            400: OpenApiResponse(
                description="Unknown field, wrong value type, or a multi-kind session."
            ),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="answer")
    def answer(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/{id}/answer/ {"field": ..., "value": ...}."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            InterviewService().answer(ctx, session_id, request.data.get("field"), request.data.get("value"))
            result = _state_dict(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        summary="Compute structural (+ AI-ranked) grounding candidates",
        responses={
            200: InterviewGroundingResponseSerializer,
            400: OpenApiResponse(description="id is not a valid UUID."),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["get"], url_path="grounding")
    def grounding(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/{id}/grounding/ -- structural + AI-ranked candidates."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().grounding_context(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        summary="Turn the collected answers into artifact(s)",
        request=InterviewFormalizeRequestSerializer,
        responses={
            200: InterviewFormalizeResponseSerializer,
            400: OpenApiResponse(
                description="Interview incomplete, multi-kind proposal missing/invalid, or session not in progress."
            ),
            403: OpenApiResponse(description="Write role required in the workspace."),
            404: OpenApiResponse(description="Session not found or target artifact gone."),
        },
    )
    @action(detail=True, methods=["post"], url_path="formalize")
    def formalize(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/{id}/formalize/ -- create/update the target artifact.

        Multi-kind sessions take a caller-confirmed ``confirmed_proposal``
        (list of proposal items) -- ignored by single-mode sessions, whose
        artifacts come from the protocol's collected_fields instead.
        """
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().formalize(ctx, session_id, request.data.get("confirmed_proposal"))
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        summary="Read the pending multi-artifact proposal, if any",
        responses={
            200: InterviewProposalResponseSerializer,
            400: OpenApiResponse(description="id is not a valid UUID."),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["get"], url_path="propose")
    def propose(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/{id}/propose/ -- current pending multi-artifact proposal, if any."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            proposal = InterviewService().propose(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response({"proposal": proposal})

    @extend_schema(
        summary="Abandon an in-progress interview session",
        request=None,
        responses={
            200: InterviewAbandonResponseSerializer,
            400: OpenApiResponse(description="Session is not in progress."),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="abandon")
    def abandon(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/{id}/abandon/ -- user-initiated cancel."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().abandon(ctx, session_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        summary="Pin an existing Requirement as this session's formalize target",
        request=InterviewSetTargetRequestSerializer,
        responses={
            200: InterviewStateSerializer,
            400: OpenApiResponse(
                description="Invalid artifact_id, non-Requirement target, or session not in progress."
            ),
            404: OpenApiResponse(description="Session or artifact not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="set_target")
    def set_target(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/{id}/set_target/ {"artifact_id": ...}.

        MCP-parity for interview.set_target (issue #1164): pins an existing
        Requirement as this session's formalize() update target. Delegates
        straight to InterviewService.set_target(); the Requirement-only and
        in_progress guards live in the service and surface through
        _SERVICE_EXCEPTIONS (ValidationError -> 400, NotFoundError -> 404).
        """
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        # Parse the body UUID here rather than handing a raw string to the
        # service: an invalid artifact_id would otherwise make the ORM raise
        # django.core.exceptions.ValidationError inside the service's
        # ``Requirement.objects.filter(artifact_id=...)`` and surface as a 500
        # (issue #460 class). The MCP handler validates the same param via
        # require_uuid, so this keeps both protocols rejecting malformed input
        # with the same clean 400.
        artifact_id, error = parse_uuid_param(
            request.data.get("artifact_id"), lang, name="artifact_id"
        )
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().set_target(ctx, session_id, artifact_id)
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        # set_target() returns InterviewService.get_state()'s raw dict (keyed
        # "session_id"); normalise it the same way _state_dict()/chat() do, so
        # every state-returning REST action keeps the ViewSet's "id" contract
        # rather than leaking the service's internal key.
        if isinstance(result, dict) and "session_id" in result:
            result["id"] = result.pop("session_id")
        return Response(result)

    @extend_schema(
        summary="Drive one server-generated conversational turn",
        request=InterviewChatRequestSerializer,
        responses={
            200: InterviewChatResponseSerializer,
            400: OpenApiResponse(
                description="No LLM provider available, or session not in progress."
            ),
            404: OpenApiResponse(description="Session not found."),
        },
    )
    @action(detail=True, methods=["post"], url_path="chat")
    def chat(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/{id}/chat/ {"message": ...} -- server-generated turn (spec §5)."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().generate_chat_turn(ctx, session_id, request.data.get("message", ""))
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        # generate_chat_turn()'s "state" is InterviewService.get_state()'s raw
        # dict (still keyed "session_id") -- normalise it the same way
        # _state_dict() does elsewhere in this ViewSet, for a consistent
        # response shape across every action that embeds session state.
        if isinstance(result.get("state"), dict) and "session_id" in result["state"]:
            result["state"]["id"] = result["state"].pop("session_id")
        return Response(result)
