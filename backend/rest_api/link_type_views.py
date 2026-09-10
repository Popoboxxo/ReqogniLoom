"""REST endpoints for the LinkTypeCatalog.

Shape mirrors ``rest_api.global_default_views`` (the workflow/permission
global-default endpoints): thin APIViews that map ``application`` exceptions
onto status codes and never touch the ORM themselves.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.link_type_facade import LinkTypeFacade
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError


def _facade() -> LinkTypeFacade:
    return LinkTypeFacade()


def _handle(func, *args, success: int = status.HTTP_200_OK, **kwargs) -> Response:
    """Run a facade call and map its exceptions to HTTP status codes."""
    try:
        payload = func(*args, **kwargs)
    except PermissionDeniedError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    except NotFoundError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if payload is None:
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(payload, status=success)


class LinkTypeDefaultsListView(APIView):
    """GET/POST /api/v1/link-type-defaults/ — tenant-wide templates."""

    @extend_schema(tags=["link-types"])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return _handle(_facade().list_global, request.auth_context)

    @extend_schema(tags=["link-types"])
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        key = (request.data or {}).get("key")
        definition = (request.data or {}).get("definition")
        if not key:
            return Response(
                {"detail": "Field 'key' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _handle(
            _facade().create_global,
            request.auth_context,
            key,
            definition,
            success=status.HTTP_201_CREATED,
        )


class LinkTypeDefaultsDetailView(APIView):
    """PUT/DELETE /api/v1/link-type-defaults/<key>/."""

    @extend_schema(tags=["link-types"])
    def put(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        definition = (request.data or {}).get("definition")
        return _handle(_facade().update_global, request.auth_context, key, definition)

    @extend_schema(tags=["link-types"])
    def delete(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        return _handle(_facade().delete_global, request.auth_context, key)


class WorkspaceLinkTypeListView(APIView):
    """GET /api/v1/workspaces/<uuid>/link-type-definitions/ — resolved catalog."""

    @extend_schema(tags=["link-types"])
    def get(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        return _handle(_facade().list_workspace, request.auth_context, workspace_id)


class WorkspaceLinkTypeDetailView(APIView):
    """PUT /api/v1/workspaces/<uuid>/link-type-definitions/<key>/."""

    @extend_schema(tags=["link-types"])
    def put(
        self,
        request: Request,
        workspace_id: UUID,
        key: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        definition = (request.data or {}).get("definition")
        return _handle(
            _facade().update_workspace,
            request.auth_context,
            workspace_id,
            key,
            definition,
        )


class WorkspaceLinkTypeResetView(APIView):
    """POST /api/v1/workspaces/<uuid>/link-type-definitions/<key>/reset/."""

    @extend_schema(tags=["link-types"])
    def post(
        self,
        request: Request,
        workspace_id: UUID,
        key: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        return _handle(
            _facade().reset_workspace, request.auth_context, workspace_id, key
        )


__all__ = [
    "LinkTypeDefaultsListView",
    "LinkTypeDefaultsDetailView",
    "WorkspaceLinkTypeListView",
    "WorkspaceLinkTypeDetailView",
    "WorkspaceLinkTypeResetView",
]
