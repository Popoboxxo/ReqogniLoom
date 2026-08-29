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

from rest_framework import status, viewsets
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
from rest_api.views import _service_error_response, detect_lang, get_auth_context, parse_workspace_id

#: Every ApplicationService exception InterviewService can raise, mapped to
#: HTTP codes by rest_api.views._service_error_response. Grouped once here
#: (instead of per-handler tuples) so every action's except clause stays in
#: sync if a new InterviewService method starts raising one of these.
_SERVICE_EXCEPTIONS = (ValidationError, NotFoundError, PermissionDeniedError, OptimisticLockError)


def _session_to_dict(session: Any) -> "dict[str, Any]":
    """Bare session summary -- used by list()/retrieve(), which don't need
    the full get_state() computation (phase/missing_fields/grounding)."""
    return {
        "id": str(session.id),
        "workspace_id": str(session.workspace_id),
        "artifact_type": session.artifact_type,
        "status": session.status,
    }


def _state_dict(ctx: Any, session_id: UUID) -> "dict[str, Any]":
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


def _started_session_state(ctx: Any, session: Any) -> "dict[str, Any]":
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
        return {
            "id": str(session.id),
            "status": session.status,
            "collected_fields": session.collected_fields,
            "grounding_snapshot": session.grounding_snapshot,
            "transcript": session.transcript,
        }
    return _state_dict(ctx, session.id)


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

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/interviews/?workspace_id=...[&status=...] -- list sessions."""
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.query_params.get("workspace_id"), lang)
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            sessions = InterviewService().list_sessions(
                ctx, workspace_id, status=request.query_params.get("status")
            )
        except _SERVICE_EXCEPTIONS as exc:
            return _service_error_response(exc, lang)
        return Response({"results": [_session_to_dict(s) for s in sessions]})

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
