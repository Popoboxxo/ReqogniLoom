"""REST endpoints for the LinkTypeCatalog.

Shape mirrors ``rest_api.global_default_views`` (the workflow/permission
global-default endpoints): thin APIViews that map ``application`` exceptions
onto status codes and never touch the ORM themselves.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.link_type_facade import LinkTypeFacade
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from rest_api.auth_enforcer import AdminScopeRequiredMixin
from rest_api.link_type_schema_serializers import (
    GlobalLinkTypePageSerializer,
    GlobalLinkTypeSerializer,
    LinkTypeWriteRequestSerializer,
    WorkspaceLinkTypePageSerializer,
    WorkspaceLinkTypeSerializer,
)
from rest_api.serializers import StandardPagination


# #865 follow-up: every mutating view below declares the ADMIN-tier API-key
# scope through ``AdminScopeRequiredMixin`` — the REST sibling of the
# ``link_type`` MCP namespace (see ``application.link_type_facade`` for the
# admin-role check that already guarded them). Reads are unchanged.
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


def _paginate_list(request: Request, items: list) -> Response:
    """Return *items* through the project-wide ``StandardPagination`` envelope.

    INT-05 (AUD-2026-09-074): the link-type list routes used to answer with a
    bare array and ignored ``page``/``page_size``. The paginator is invoked
    *outside* any broad ``try/except`` — an invalid ``page`` raises DRF's
    ``NotFound`` and must propagate as **404**, never be swallowed into a 500
    (the AUD-2026-09-073 mechanism).
    """
    paginator = StandardPagination()
    page = paginator.paginate_queryset(items, request)
    if page is not None:
        return paginator.get_paginated_response(page)
    return Response(items, status=status.HTTP_200_OK)


class LinkTypeDefaultsListView(AdminScopeRequiredMixin, APIView):
    """GET/POST /api/v1/link-type-defaults/ — tenant-wide templates.

    Capability gate (follow-up to #865): the POST requires the ADMIN-tier
    API-key scope, mirroring the ``link_type`` MCP namespace (the catalog
    defines which trace relations may be created at all). See
    ``rest_api.auth_enforcer.AdminScopeRequiredMixin``.
    """

    @extend_schema(
        tags=["link-types"],
        parameters=[
            OpenApiParameter(
                "page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="1-based page number (default 1).",
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Items per page (default 25, capped at 100).",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=GlobalLinkTypePageSerializer,
                description=(
                    "The tenant-wide templates through the StandardPagination "
                    "envelope (`results` carries the rows)."
                ),
            ),
            403: OpenApiResponse(description="Admin role required."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """GET /api/v1/link-type-defaults/ — paginated tenant-wide templates.

        INT-05 (AUD-2026-09-074): envelope instead of a bare array.
        """
        response = _handle(_facade().list_global, request.auth_context)
        if response.status_code != status.HTTP_200_OK:
            return response
        return _paginate_list(request, response.data)

    @extend_schema(
        tags=["link-types"],
        request=LinkTypeWriteRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=GlobalLinkTypeSerializer,
                description="The created template.",
            ),
            400: OpenApiResponse(
                description="Missing key, or the definition fails validation."
            ),
            403: OpenApiResponse(description="Tenant-admin role required."),
        },
    )
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


class LinkTypeDefaultsDetailView(AdminScopeRequiredMixin, APIView):
    """PUT/DELETE /api/v1/link-type-defaults/<key>/."""

    @extend_schema(
        tags=["link-types"],
        request=LinkTypeWriteRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=GlobalLinkTypeSerializer,
                description="The updated template (with `propagated_to`).",
            ),
            400: OpenApiResponse(description="The definition fails validation."),
            403: OpenApiResponse(description="Tenant-admin role required."),
            404: OpenApiResponse(description="No template with that key."),
        },
    )
    def put(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        definition = (request.data or {}).get("definition")
        return _handle(_facade().update_global, request.auth_context, key, definition)

    @extend_schema(
        tags=["link-types"],
        request=None,
        responses={
            204: OpenApiResponse(description="The template was deleted."),
            403: OpenApiResponse(description="Tenant-admin role required."),
            404: OpenApiResponse(description="No template with that key."),
        },
    )
    def delete(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        return _handle(_facade().delete_global, request.auth_context, key)


class WorkspaceLinkTypeListView(APIView):
    """GET /api/v1/workspaces/<uuid>/link-type-definitions/ — resolved catalog."""

    @extend_schema(
        tags=["link-types"],
        parameters=[
            OpenApiParameter(
                "page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="1-based page number (default 1).",
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Items per page (default 25, capped at 100).",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=WorkspaceLinkTypePageSerializer,
                description=(
                    "The workspace's resolved catalog (inactive rows included) "
                    "through the StandardPagination envelope."
                ),
            ),
            400: OpenApiResponse(description="Malformed workspace_id."),
            404: OpenApiResponse(description="Workspace not in this tenant."),
        },
    )
    def get(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        """GET /api/v1/workspaces/<uuid>/link-type-definitions/ — paginated.

        INT-05 (AUD-2026-09-074): envelope instead of a bare array.
        """
        response = _handle(
            _facade().list_workspace, request.auth_context, workspace_id
        )
        if response.status_code != status.HTTP_200_OK:
            return response
        return _paginate_list(request, response.data)


class WorkspaceLinkTypeDetailView(AdminScopeRequiredMixin, APIView):
    """PUT /api/v1/workspaces/<uuid>/link-type-definitions/<key>/."""

    @extend_schema(
        tags=["link-types"],
        request=LinkTypeWriteRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=WorkspaceLinkTypeSerializer,
                description="The workspace's row after the override.",
            ),
            400: OpenApiResponse(description="The definition fails validation."),
            403: OpenApiResponse(description="Admin role required."),
            404: OpenApiResponse(description="No such link type in this scope."),
        },
    )
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


class WorkspaceLinkTypeResetView(AdminScopeRequiredMixin, APIView):
    """POST /api/v1/workspaces/<uuid>/link-type-definitions/<key>/reset/."""

    @extend_schema(
        tags=["link-types"],
        request=None,
        responses={
            200: OpenApiResponse(
                response=WorkspaceLinkTypeSerializer,
                description="The workspace's row after the reset.",
            ),
            403: OpenApiResponse(description="Admin role required."),
            404: OpenApiResponse(description="No such link type in this scope."),
        },
    )
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
    "LinkTypeDefaultsDetailView",
    "LinkTypeDefaultsListView",
    "WorkspaceLinkTypeDetailView",
    "WorkspaceLinkTypeListView",
    "WorkspaceLinkTypeResetView",
]
