"""REST endpoints for attribute definitions (spec section 5).

Shaped after ``rest_api/global_default_views.py``: the same admin gate, the same
``build_error_response`` envelope, the same "a missing global reads as
``initialized: false`` instead of 404" contract so the UI can offer an
Initialize affordance.

No ORM in this module by design (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access``): every
read and write goes through ``AttributeDefinitionService``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
    AttributeSchemaError,
)
from auth_tenancy.models import ROLE_ADMIN
from presets.exceptions import CrossTenantWorkspaceError
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _require_admin(request: Request):
    """Return ``(ctx, lang)`` or a 403 Response when the caller is not admin."""
    lang = detect_lang(request)
    ctx = get_auth_context(request)
    if not ctx.has_role(ROLE_ADMIN):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message="Admin role required."),
            status=status.HTTP_403_FORBIDDEN,
        )
    return ctx, lang


def _validation(lang: str, message: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _not_found(lang: str, message: str) -> Response:
    return Response(
        build_error_response("NOT_FOUND", lang, message=message),
        status=status.HTTP_404_NOT_FOUND,
    )


def _forbidden(lang: str, message: str) -> Response:
    return Response(
        build_error_response("PERMISSION_DENIED", lang, message=message),
        status=status.HTTP_403_FORBIDDEN,
    )


def _read_attributes(request: Request, lang: str) -> tuple[list[dict[str, Any]] | None, Response | None]:
    """Extract and shape-check the ``attributes`` list of a PUT body."""
    payload = request.data if isinstance(request.data, dict) else {}
    attributes = payload.get("attributes")
    if not isinstance(attributes, list):
        return None, _validation(lang, "Body must be an object with an 'attributes' list.")
    return attributes, None


class AttributeDefaultsListView(APIView):
    """GET /attribute-defaults/ — list the tenant's global attribute defaults."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        definitions = AttributeDefinitionService().list_global(
            ctx,
            item_type=request.query_params.get("item_type") or None,
            preset=request.query_params.get("preset") or None,
        )
        return Response({"definitions": definitions}, status=status.HTTP_200_OK)


class AttributeDefaultsDetailView(APIView):
    """GET/PUT /attribute-defaults/{item_type}/{preset}/ — one global default."""

    def get(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        return Response(
            AttributeDefinitionService().get_global(ctx, item_type, preset),
            status=status.HTTP_200_OK,
        )

    def put(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attributes, error = _read_attributes(request, lang)
        if error is not None:
            return error
        try:
            payload = AttributeDefinitionService().update_global(
                ctx, item_type, preset, attributes
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request: Request, item_type: str, preset: str) -> Response:
        """Create one new ``kind="extended"`` attribute on the global default."""
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attribute = request.data if isinstance(request.data, dict) else {}
        try:
            payload = AttributeDefinitionService().create_global(
                ctx, item_type, preset, attribute
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_201_CREATED)

    def delete(self, request: Request, item_type: str, preset: str) -> Response:
        """Delete one attribute (``?name=``) from the global default."""
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        name = request.query_params.get("name")
        if not name:
            return _validation(lang, "Query parameter 'name' is required.")
        try:
            payload = AttributeDefinitionService().delete_global(
                ctx, item_type, preset, name
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionView(APIView):
    """GET/PUT /workspaces/{id}/attribute-definitions/{item_type}/.

    GET is open to every tenant member on purpose: applying the configuration to
    your own data is exactly what a non-admin needs it for. PUT is admin-only.
    """

    def get(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            payload = AttributeDefinitionService().resolve(ctx, item_type, workspace_id)
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except CrossTenantWorkspaceError as exc:
            # The workspace exists but belongs to another tenant. Without this
            # handler the gate's correctly-raised exception falls through to an
            # uncaught 500 — the same trap as SYSTEMAUDIT-2026-08-27 AP-6 M-1.
            # 403 matches the established mapping in ``rest_api/views.py``
            # (``_EXC_TO_HTTP[CrossTenantWorkspaceError]``).
            return _forbidden(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)

    def put(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attributes, error = _read_attributes(request, lang)
        if error is not None:
            return error
        try:
            payload = AttributeDefinitionService().update_workspace(
                ctx, item_type, workspace_id, attributes
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionResetView(APIView):
    """POST /workspaces/{id}/attribute-definitions/{item_type}/reset/."""

    def post(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            payload = AttributeDefinitionService().reset_workspace(
                ctx, item_type, workspace_id
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


__all__ = [
    "AttributeDefaultsDetailView",
    "AttributeDefaultsListView",
    "WorkspaceAttributeDefinitionResetView",
    "WorkspaceAttributeDefinitionView",
]
