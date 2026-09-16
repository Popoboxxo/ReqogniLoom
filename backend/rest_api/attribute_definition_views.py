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
from rest_api.auth_enforcer import AdminScopeRequiredMixin, get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# #865 follow-up: every mutating view below is admin-only by *role* (see
# ``_require_admin``) but declares the ADMIN-tier API-key scope through
# ``AdminScopeRequiredMixin`` as well — the REST sibling of the
# ``attribute_definition`` MCP namespace, so an AUTHOR-tier key cannot reshape
# the tenant-wide attribute schema through this transport. Reads are unchanged.
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


def _read_sections(
    request: Request, lang: str
) -> tuple[list[dict[str, Any]] | None, Response | None]:
    """Extract the optional ``sections`` list of a PUT body (Task 8).

    ``None`` (key absent) is a valid, common result — it means "leave the
    row's current sections unchanged", not an error. Only a present-but-
    wrong-shaped value is rejected.
    """
    payload = request.data if isinstance(request.data, dict) else {}
    if "sections" not in payload:
        return None, None
    sections = payload["sections"]
    if not isinstance(sections, list):
        return None, _validation(lang, "'sections', if present, must be a list.")
    return sections, None


def _read_section_flow(
    request: Request, lang: str
) -> tuple[list[dict[str, Any]] | None, Response | None]:
    """Extract the optional ``section_flow`` list of a PUT body (WS4 #938).

    Same contract as :func:`_read_sections`: absent means "leave the row's
    current flow unchanged"; only a present-but-wrong-shaped value is a 400.
    """
    payload = request.data if isinstance(request.data, dict) else {}
    if "section_flow" not in payload:
        return None, None
    section_flow = payload["section_flow"]
    if not isinstance(section_flow, list):
        return None, _validation(lang, "'section_flow', if present, must be a list.")
    return section_flow, None


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


class AttributeDefaultsDetailView(AdminScopeRequiredMixin, APIView):
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
        sections, sections_error = _read_sections(request, lang)
        if sections_error is not None:
            return sections_error
        section_flow, section_flow_error = _read_section_flow(request, lang)
        if section_flow_error is not None:
            return section_flow_error
        try:
            payload = AttributeDefinitionService().update_global(
                ctx, item_type, preset, attributes, sections, section_flow
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


class WorkspaceAttributeDefinitionView(AdminScopeRequiredMixin, APIView):
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
        sections, sections_error = _read_sections(request, lang)
        if sections_error is not None:
            return sections_error
        section_flow, section_flow_error = _read_section_flow(request, lang)
        if section_flow_error is not None:
            return section_flow_error
        try:
            payload = AttributeDefinitionService().update_workspace(
                ctx, item_type, workspace_id, attributes, sections, section_flow
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        """Create one workspace-only attribute (no global counterpart)."""
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attribute = request.data if isinstance(request.data, dict) else {}
        try:
            payload = AttributeDefinitionService().create_workspace(
                ctx, item_type, workspace_id, attribute
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            # create_workspace resolves the workspace's preset through the
            # gate, which raises for a foreign-tenant id. Same guard (and same
            # reason) as WorkspaceAttributeDefinitionView.get — without it a
            # PresetError (NOT a ValueError) falls through to an uncaught 500.
            return _forbidden(lang, str(exc))
        return Response(payload, status=status.HTTP_201_CREATED)

    def delete(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        """Delete one attribute (``?name=``) from the workspace's definition."""
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        name = request.query_params.get("name")
        if not name:
            return _validation(lang, "Query parameter 'name' is required.")
        try:
            payload = AttributeDefinitionService().delete_workspace(
                ctx, item_type, workspace_id, name
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            # Same guard as post() above — delete_workspace resolves the
            # preset through the gate too.
            return _forbidden(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


class AttributeUsageView(APIView):
    """GET /workspaces/{id}/attribute-definitions/{item_type}/usage/?name=&option=.

    Read-only probe the delete/option-removal confirmation flows call before
    showing their warning (Task 5). Admin-only, same gate as every other
    mutation-adjacent endpoint on this resource.
    """

    def get(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        name = request.query_params.get("name")
        if not name:
            return _validation(lang, "Query parameter 'name' is required.")
        count = AttributeDefinitionService().count_usages(
            ctx, item_type, workspace_id, name, request.query_params.get("option")
        )
        return Response({"count": count}, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionResetView(AdminScopeRequiredMixin, APIView):
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


def _read_on_collision(request: Request, payload: dict[str, Any]) -> str:
    """``on_collision`` (Task 10): a query param wins over a same-named key in
    the body, defaulting to ``"skip"`` — the plan's own spec explicitly wants
    both accepted (``?on_collision=`` OR the body carrying it alongside the
    exported document)."""
    return request.query_params.get("on_collision") or payload.get("on_collision") or "skip"


class AttributeDefaultsExportView(APIView):
    """GET /attribute-defaults/{item_type}/{preset}/export/ (Task 10)."""

    def get(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            payload = AttributeDefinitionService().export_definition(
                ctx, item_type, preset=preset
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


class AttributeDefaultsImportView(AdminScopeRequiredMixin, APIView):
    """POST /attribute-defaults/{item_type}/{preset}/import/ (Task 10)."""

    def post(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        try:
            payload = AttributeDefinitionService().import_definition(
                ctx, item_type, body, preset=preset,
                on_collision=_read_on_collision(request, body),
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionExportView(APIView):
    """GET /workspaces/{id}/attribute-definitions/{item_type}/export/ (Task 10)."""

    def get(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            payload = AttributeDefinitionService().export_definition(
                ctx, item_type, workspace_id=workspace_id
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except CrossTenantWorkspaceError as exc:
            # Same guard as WorkspaceAttributeDefinitionView.get — see its
            # comment for why this must not fall through to a 500.
            return _forbidden(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionImportView(AdminScopeRequiredMixin, APIView):
    """POST /workspaces/{id}/attribute-definitions/{item_type}/import/ (Task 10)."""

    def post(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        try:
            payload = AttributeDefinitionService().import_definition(
                ctx, item_type, body, workspace_id=workspace_id,
                on_collision=_read_on_collision(request, body),
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            return _forbidden(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


__all__ = [
    "AttributeDefaultsDetailView",
    "AttributeDefaultsExportView",
    "AttributeDefaultsImportView",
    "AttributeDefaultsListView",
    "AttributeUsageView",
    "WorkspaceAttributeDefinitionExportView",
    "WorkspaceAttributeDefinitionImportView",
    "WorkspaceAttributeDefinitionResetView",
    "WorkspaceAttributeDefinitionView",
]
