"""Self-service REST for the caller's own display preference (Issue #1096).

``GET``/``PATCH`` ``/api/v1/users/me/display-preferences/`` let any
authenticated user read and change their OWN UI display preference — currently
the single flag ``show_readable_ids`` that decides whether the readable,
per-workspace artifact id (e.g. ``REQ-001``) is rendered. The copy operation is
unaffected: ``<IdChip>`` always copies the system id (UUID); only its visibility
is controlled here.

Self-service only: the ``ctx.user_id`` filter inside
``DisplayPreferenceService`` **is** the authorization boundary. The view takes no
``user_id`` parameter, applies no admin gate, and declares no
``required_operation`` — the same shape as the sibling ``/users/me/*`` views
(``NotificationPreferenceView``, ``admin_ops.theme_rest.UserThemePreferenceView``).
``HasOperationPermission`` rather than the default ``RbacPermission`` because the
URL carries no ``workspace_id`` and ``ctx.active_roles`` may legitimately be
empty.

Layer 3 only: every read and write goes through ``DisplayPreferenceService``
(ADR-01); this module contains no ORM access — the ``rest_api/*_views.py``
ratchet in ``rest_api/tests/test_architecture.py`` enforces that.

Contract (Issue #1096):
  GET   -> 200 ``{"show_readable_ids": <bool>}``  (server default when no row)
  PATCH <- ``{"show_readable_ids": <bool>}``  -> 200 same shape
        unknown key / non-bool -> 400 ``VALIDATION_ERROR`` (#851)
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.display_preference_service import DisplayPreferenceService
from auth_tenancy.rest import HasOperationPermission
from persistence.errors import ValidationError
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import (
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)


class DisplayPreferenceUpdateSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """``{"show_readable_ids": <bool>}`` — a partial display update.

    The declared fields *are* the closed vocabulary: ``UnknownFieldRejectionMixin``
    (#851) turns any other key into a 400 instead of the DRF default of silently
    dropping it, so a typo can never look like a successful save. The field is
    optional so an empty PATCH body is a read-only no-op, not a validation error.
    """

    show_readable_ids = serializers.BooleanField(required=False)


class DisplayPreferenceView(APIView):
    """``/api/v1/users/me/display-preferences/`` — the caller's own display flags.

    GET returns the effective flags straight from the server (default applied
    when the caller has no row). PATCH applies a partial change and returns the
    same fresh payload, so the client renders server truth rather than its own
    optimistic guess.
    """

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        return Response(DisplayPreferenceService().get_display_preferences(ctx))

    def patch(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        serializer = DisplayPreferenceUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": field, "errors": errors}
                        for field, errors in serializer.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            preferences = DisplayPreferenceService().update_display_preferences(
                ctx, dict(serializer.validated_data)
            )
        except ValidationError as exc:
            # A service-level rejection is caller input, not a server fault.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(preferences)


def _authentication_required(lang: str) -> Response:
    """The shared 401 body for both handlers."""
    return Response(
        build_error_response("AUTHENTICATION_REQUIRED", lang),
        status=status.HTTP_401_UNAUTHORIZED,
    )


__all__ = ["DisplayPreferenceUpdateSerializer", "DisplayPreferenceView"]
