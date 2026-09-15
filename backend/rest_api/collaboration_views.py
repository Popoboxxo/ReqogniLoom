"""REST surface for comments and notifications (Menschen-im-System spec §4/§5).

Layer 3 only: every read and write is delegated to a Layer-2 service
(ADR-01). This module deliberately contains no ORM access — the rest_api
ratchet enforces that.

Notifications have intentionally **no** MCP counterpart: agents do not read a
notification center, so the notification feed is a human-facing surface only.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.comment_service import CommentService
from application.notification_service import NotificationService
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError

from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import (
    CommentSerializer,
    NotificationSerializer,
    build_error_response,
    detect_lang,
)
from rest_api.views import BaseEntityViewSet, _service_error_response

logger = logging.getLogger(__name__)


class ArtifactCommentsView(APIView):
    """``/api/v1/artifacts/<artifact_id>/comments/`` — list and create."""

    def get(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
        """List an artifact's comments, oldest first."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            include_resolved = request.query_params.get("include_resolved", "true").lower() != "false"
            rows = CommentService().list_for_artifact(
                UUID(artifact_id), ctx, include_resolved=include_resolved
            )
            return Response(CommentSerializer(rows, many=True).data)
        except Exception as exc:
            logger.exception("ArtifactCommentsView.get: unhandled exception")
            return _service_error_response(exc, lang)

    def post(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
        """Create a comment on the artifact."""
        lang = detect_lang(request)
        serializer = CommentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in serializer.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            comment = CommentService().create_comment(
                artifact_id=UUID(artifact_id),
                text=serializer.validated_data["text"],
                ctx=ctx,
            )
            return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("ArtifactCommentsView.post: unhandled exception")
            return _service_error_response(exc, lang)


class CommentViewSet(BaseEntityViewSet):
    """``/api/v1/comments/<pk>/`` — resolve and delete."""

    serializer_class = CommentSerializer

    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/comments/<pk>/resolve/ — mark the comment resolved."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            comment = CommentService().resolve_comment(UUID(str(pk)), ctx)
            return Response(CommentSerializer(comment).data)
        except Exception as exc:
            logger.exception("CommentViewSet.resolve: unhandled exception")
            return _service_error_response(exc, lang)

    def destroy(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """DELETE /api/v1/comments/<pk>/ — author or admin only."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            CommentService().delete_comment(UUID(str(pk)), ctx)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            logger.exception("CommentViewSet.destroy: unhandled exception")
            return _service_error_response(exc, lang)


#: Fallback when ``?limit=`` is absent or unparsable. The service clamps the
#: effective value to 200 regardless.
DEFAULT_NOTIFICATION_LIMIT = 50


class NotificationViewSet(BaseEntityViewSet):
    """``/api/v1/notifications/`` — the caller's own notification feed.

    Not paginated: this is a capped feed for a dropdown, not a browsable
    collection. The list response carries the unread count so the bell needs a
    single round trip.
    """

    serializer_class = NotificationSerializer

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/notifications/ — own notifications plus the unread count."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            unread_only = request.query_params.get("unread_only", "").lower() == "true"
            try:
                limit = int(request.query_params.get("limit", DEFAULT_NOTIFICATION_LIMIT))
            except (TypeError, ValueError):
                limit = DEFAULT_NOTIFICATION_LIMIT

            service = NotificationService()
            rows = service.list_for_user(ctx, unread_only=unread_only, limit=limit)
            return Response(
                {
                    "notifications": NotificationSerializer(rows, many=True).data,
                    "unread_count": service.unread_count(ctx),
                }
            )
        except Exception as exc:
            logger.exception("NotificationViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/notifications/<pk>/read/ — mark one notification read."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            row = NotificationService().mark_read(UUID(str(pk)), ctx)
            return Response(NotificationSerializer(row).data)
        except Exception as exc:
            logger.exception("NotificationViewSet.read: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/notifications/mark-all-read/ — mark the whole feed read."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            return Response({"marked": NotificationService().mark_all_read(ctx)})
        except Exception as exc:
            logger.exception("NotificationViewSet.mark_all_read: unhandled exception")
            return _service_error_response(exc, lang)


__all__ = [
    "ArtifactCommentsView",
    "CommentViewSet",
    "DEFAULT_NOTIFICATION_LIMIT",
    "NotificationViewSet",
]
