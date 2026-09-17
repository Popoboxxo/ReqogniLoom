"""Self-service REST for the caller's own notification preference (OD-1, Task 28).

``GET``/``PATCH`` ``/api/v1/users/me/notification-preferences/`` let any
authenticated user read and change their OWN delivery preference for the four
notification triggers, from the profile page.

Self-service only: the ``ctx.user_id`` filter inside
``NotificationPreferenceService`` **is** the authorization boundary. The view
takes no ``user_id`` parameter, applies no admin gate, and declares no
``required_operation`` — the same shape as the two sibling ``/users/me/*``
views (``admin_ops.theme_rest.UserThemePreferenceView``,
``memory.memory_rest.MemorySelfServiceView``). ``HasOperationPermission``
rather than the default ``RbacPermission`` because the URL carries no
``workspace_id`` and ``ctx.active_roles`` may legitimately be empty.

**No MCP counterpart, deliberately.** A notification preference is a human
preference and notifications have no agent-facing surface (spec §6): agents do
not read a notification centre.

Layer 3 only: every read and write goes through
``NotificationPreferenceService`` (ADR-01). This module contains no ORM access
— the ``rest_api/*_views.py`` ratchet in
``rest_api/tests/test_architecture.py`` enforces that, which is why the module
name is load-bearing rather than cosmetic.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.notification_preference_service import (
    ALL_KINDS,
    NotificationPreferenceService,
)
from auth_tenancy.rest import HasOperationPermission
from persistence.errors import ValidationError
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import (
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)


class NotificationPreferenceUpdateSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """``{"preferences": {"<kind>": <bool>}}`` — a partial update.

    ``DictField`` keeps the keys free-form at field level so the vocabulary
    check lives in exactly one explicit place below: the closed four-kind list
    is ``application.notification_preference_service.ALL_KINDS`` (itself
    derived from ``Notification.KIND_CHOICES``), never a second literal in
    this module.
    """

    preferences = serializers.DictField(child=serializers.BooleanField())

    def validate_preferences(self, value: dict[str, bool]) -> dict[str, bool]:
        """Reject any key outside the closed trigger vocabulary."""
        unknown = sorted(key for key in value if key not in ALL_KINDS)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown notification trigger(s): {', '.join(unknown)}"
            )
        return value


class NotificationPreferenceView(APIView):
    """``/api/v1/users/me/notification-preferences/`` — the caller's own switches.

    GET returns the *effective* map (``True`` unless a row disables the kind),
    so the client never has to know the vocabulary or invert a disabled list.
    PATCH applies a partial change and returns the same fresh map, so the
    caller renders server truth instead of its own optimistic guess.
    """

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        return Response(
            {"preferences": NotificationPreferenceService().get_effective_preferences(ctx)}
        )

    def patch(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        serializer = NotificationPreferenceUpdateSerializer(data=request.data)
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
            preferences = NotificationPreferenceService().update_preferences(
                ctx, serializer.validated_data["preferences"]
            )
        except ValidationError as exc:
            # A service-level rejection (unknown kind, non-bool) is caller
            # input, not a server fault.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"preferences": preferences})


def _authentication_required(lang: str) -> Response:
    """The shared 401 body for both handlers."""
    return Response(
        build_error_response("AUTHENTICATION_REQUIRED", lang),
        status=status.HTTP_401_UNAUTHORIZED,
    )


__all__ = ["NotificationPreferenceUpdateSerializer", "NotificationPreferenceView"]
