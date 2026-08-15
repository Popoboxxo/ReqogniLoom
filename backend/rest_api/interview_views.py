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


class InterviewViewSet(viewsets.ViewSet):
    """ViewSet for /api/v1/interviews/ -- start/list/get/state/answer/grounding/formalize/chat.

    Not a BaseEntityViewSet subclass: InterviewSession is not a generic
    Artifact-backed entity (no serializer, no workflow, no soft-delete), so
    the shared CRUD scaffolding would add nothing here -- same reasoning as
    SearchViewSet, which is also a plain viewsets.ViewSet wrapping a single
    ApplicationService.
    """

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/interviews/ -- start a new interview session."""
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            session = InterviewService().start(ctx, request.data.get("artifact_type"), workspace_id)
            result = _state_dict(ctx, session.id)
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
        """POST /api/v1/interviews/{id}/formalize/ -- create/update the target artifact."""
        lang = detect_lang(request)
        session_id, error = parse_uuid_param(pk, lang, name="id")
        if error is not None:
            return error
        try:
            ctx = get_auth_context(request)
            result = InterviewService().formalize(ctx, session_id)
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
