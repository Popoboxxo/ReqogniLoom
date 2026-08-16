"""Prompt variable catalog REST endpoints (spec §3.1, §5).

Mirrors the prompt-template *slot* API (``rest_api/settings_views.py``,
issue #119) one-for-one — same admin gate, same ``?workspace_id=`` scope
parameter, same "PUT publishes, DELETE drops the override, both return the
now-effective state" contract — so the frontend can reuse its scope-switch
and origin-badge patterns unchanged.

  GET    /api/v1/prompt-variables/[?workspace_id=<uuid>]
  PUT    /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]
  DELETE /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]

``name`` is deliberately not validated against the factory registry: a PUT to
an unknown name is how a brand-new ``config`` variable is created (spec §3.2,
"einfach erweiterbar"). Writes to a ``kind="data"`` name are rejected by
``PromptVariableService.set_variable`` with a 400.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.models import ROLE_ADMIN
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


class PromptVariableWriteSerializer(serializers.Serializer):
    """Body of PUT /prompt-variables/<name>/.

    ``value`` is a ``JSONField`` because a variable may be an int, string,
    bool or arbitrary JSON — the concrete type is validated against the
    variable's ``var_type`` inside the service, which owns that knowledge.
    """

    value = serializers.JSONField()
    var_type = serializers.CharField(required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )


class _PromptVariableAdminMixin:
    """Shared admin gate + ``workspace_id`` query-param parsing."""

    def _forbidden(self, lang: str) -> Response:
        """Return the 403 body used by every prompt-variable endpoint."""
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access prompt variables.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    def _parse_workspace_id(self, request: Request) -> "UUID | None":
        """Return the ``?workspace_id=`` scope, or ``None`` for tenant-global.

        Raises:
            ValueError: The parameter was present but not a valid UUID.
        """
        raw = request.query_params.get("workspace_id")
        if raw in (None, ""):
            return None
        return UUID(raw)

    def _bad_workspace_id(self, lang: str) -> Response:
        """Return the 400 body for a malformed ``workspace_id``."""
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message="'workspace_id' must be a valid UUID.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )


class PromptVariableListView(_PromptVariableAdminMixin, APIView):
    """GET /api/v1/prompt-variables/[?workspace_id=<uuid>]."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return every catalog variable with its per-scope state."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        variables = PromptVariableService().list_variables(
            ctx, workspace_id=workspace_id
        )
        return Response(
            {
                "variables": variables,
                "count": len(variables),
                "workspace_id": str(workspace_id) if workspace_id else None,
            }
        )


class PromptVariableDetailView(_PromptVariableAdminMixin, APIView):
    """PUT/DELETE /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]."""

    def put(self, request: Request, name: str, *args: Any, **kwargs: Any) -> Response:
        """Publish a new active version of ``name`` for the requested scope."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        ser = PromptVariableWriteSerializer(data=request.data)
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
            state = PromptVariableService().set_variable(
                ctx,
                name=name,
                value=ser.validated_data["value"],
                workspace_id=workspace_id,
                var_type=ser.validated_data.get("var_type"),
                description=ser.validated_data.get("description"),
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(state)

    def delete(
        self, request: Request, name: str, *args: Any, **kwargs: Any
    ) -> Response:
        """Drop ``name``'s override at the requested scope (idempotent)."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        try:
            state = PromptVariableService().clear_variable(
                ctx, name=name, workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        # 200 with the now-effective state rather than 204: the caller's next
        # question is always "so what applies now?", and the inherited value
        # is not derivable client-side without a second round trip.
        return Response(state)


__all__ = [
    "PromptVariableDetailView",
    "PromptVariableListView",
    "PromptVariableWriteSerializer",
]
