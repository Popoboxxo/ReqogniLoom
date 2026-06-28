"""
COMP-RA-001 — UserWorkspacePreference REST endpoints (REQ-L1-027).

Endpoints:
  GET  /api/v1/users/me/preferences/?workspace_id=<uuid>
      Return the authenticated user's preference for the given workspace.
      404 when no preference row exists yet.

  PATCH /api/v1/users/me/preferences/
      Merge caller-supplied visibility overrides into the preference row.
      Body: {"workspace_id": "<uuid>", "optional_artifact_visibility": {...}}
      Creates the row on first access (get-or-create semantics).

Authentication: Bearer token (global default).
Permissions:    Any authenticated user (RBAC READ/WRITE via RbacPermission).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.services import PreferenceService
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class UserWorkspacePreferenceSerializer(serializers.Serializer):
    """Read serializer — exposes the preference fields."""

    id = serializers.UUIDField(read_only=True)
    user_id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)
    optional_artifact_visibility = serializers.JSONField(read_only=True)


class PreferenceUpdateSerializer(serializers.Serializer):
    """Write serializer — validates PATCH body for visibility overrides."""

    workspace_id = serializers.UUIDField()
    optional_artifact_visibility = serializers.JSONField(required=True)

    def validate_optional_artifact_visibility(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        # Only bool values are allowed
        for k, v in value.items():
            if not isinstance(k, str):
                raise serializers.ValidationError(f"Key must be a string: {k!r}")
            if not isinstance(v, bool):
                raise serializers.ValidationError(
                    f"Value for '{k}' must be a boolean, got {type(v).__name__}"
                )
        return value


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


class UserPreferenceView(APIView):
    """GET/PATCH /api/v1/users/me/preferences/ (REQ-L1-027).

    GET requires ``?workspace_id=<uuid>`` query parameter.
    PATCH requires ``workspace_id`` and ``optional_artifact_visibility`` in body.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._svc = PreferenceService()

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id_str = request.query_params.get("workspace_id")
        if not workspace_id_str:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace_id = UUID(workspace_id_str)
        except (ValueError, TypeError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="Invalid workspace_id"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        ctx = get_auth_context(request)
        pref = self._svc.get_preference(
            user_id=ctx.user_id, workspace_id=workspace_id
        )
        if pref is None:
            return Response(
                build_error_response("NOT_FOUND", lang, message="No preferences found"),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(UserWorkspacePreferenceSerializer(pref).data)

    # ---- PATCH --------------------------------------------------------

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = PreferenceUpdateSerializer(data=request.data)
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
        pref = self._svc.update_visibility(
            user_id=ctx.user_id,
            workspace_id=data["workspace_id"],
            overrides=data["optional_artifact_visibility"],
        )
        return Response(UserWorkspacePreferenceSerializer(pref).data)


__all__ = ["UserPreferenceView"]
