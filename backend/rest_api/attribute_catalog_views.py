"""REST endpoints for the central attribute catalog (spec section 8, WS5 #942).

Shaped after ``rest_api/attribute_definition_views.py``: the same admin gate,
the same ``build_error_response`` envelope, the same explicit error mapping
(400/403/404). The catalog is tenant-wide configuration, so every endpoint —
read and write — requires ``admin``, exactly like the attribute-defaults
resource.

No ORM in this module by design (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access``): every
read and write goes through ``AttributeCatalogService``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.attribute_catalog_service import (
    AttributeCatalogNotFound,
    AttributeCatalogService,
)
from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeSchemaError,
)
from application.base import PermissionDeniedError
from auth_tenancy.models import ROLE_ADMIN
from presets.exceptions import CrossTenantWorkspaceError
from rest_api.auth_enforcer import AdminScopeRequiredMixin, get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# #865 follow-up: every mutating view below is admin-only by *role* (see
# ``_require_admin``) but declares the ADMIN-tier API-key scope through
# ``AdminScopeRequiredMixin`` as well — the REST sibling of the
# ``attribute_catalog`` MCP namespace. Reads are unchanged.
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


def _error(code: str, http_status: int, lang: str, message: str) -> Response:
    return Response(
        build_error_response(code, lang, message=message), status=http_status
    )


def _validation(lang: str, message: str) -> Response:
    return _error("VALIDATION_ERROR", status.HTTP_400_BAD_REQUEST, lang, message)


def _not_found(lang: str, message: str) -> Response:
    return _error("NOT_FOUND", status.HTTP_404_NOT_FOUND, lang, message)


def _forbidden(lang: str, message: str) -> Response:
    return _error("PERMISSION_DENIED", status.HTTP_403_FORBIDDEN, lang, message)


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_tags(request: Request) -> list[str]:
    """Accept ``?tags=a,b`` and/or repeated ``?tag=a&tag=b``."""
    raw: list[str] = list(request.query_params.getlist("tag"))
    joined = request.query_params.get("tags")
    if joined:
        raw.extend(part for part in str(joined).split(",") if part.strip())
    return [tag.strip() for tag in raw if tag.strip()]


def _body(request: Request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


def _handle_common(exc: Exception, lang: str) -> Response | None:
    """Map the catalog/definition service exceptions to their REST envelope."""
    if isinstance(exc, PermissionDeniedError):
        return _forbidden(lang, str(exc))
    if isinstance(exc, (AttributeCatalogNotFound, AttributeDefinitionNotFound)):
        return _not_found(lang, str(exc))
    if isinstance(exc, AttributeSchemaError):
        return _validation(lang, "; ".join(exc.errors))
    if isinstance(exc, CrossTenantWorkspaceError):
        return _forbidden(lang, str(exc))
    return None


class AttributeCatalogListView(AdminScopeRequiredMixin, APIView):
    """GET/POST /attribute-catalog/ — list or create catalog entries."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        entries = AttributeCatalogService().list_entries(
            ctx,
            query=request.query_params.get("query") or request.query_params.get("q"),
            category=request.query_params.get("category") or None,
            tags=_read_tags(request),
            include_deprecated=_as_bool(
                request.query_params.get("include_deprecated"), default=False
            ),
        )
        return Response({"entries": entries}, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = _body(request)
        try:
            entry = AttributeCatalogService().create_entry(
                ctx,
                name=body.get("name", ""),
                definition=body.get("definition"),
                category=body.get("category") or "",
                tags=body.get("tags"),
                label=body.get("label"),
                help_text=body.get("help_text"),
                origin=body.get("origin") or "",
            )
        except Exception as exc:  # noqa: BLE001 - routed through _handle_common
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(entry, status=status.HTTP_201_CREATED)


class AttributeCatalogSearchView(APIView):
    """GET /attribute-catalog/search/?q= — name/category/tag search."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        query = request.query_params.get("q") or request.query_params.get("query")
        try:
            entries = AttributeCatalogService().search_entries(
                ctx,
                query=query,
                category=request.query_params.get("category") or None,
                tags=_read_tags(request),
                include_deprecated=_as_bool(
                    request.query_params.get("include_deprecated"), default=False
                ),
            )
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response({"entries": entries}, status=status.HTTP_200_OK)


class AttributeCatalogExportView(APIView):
    """GET /attribute-catalog/export/ — download a re-importable document."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        document = AttributeCatalogService().export_catalog(
            ctx,
            include_deprecated=_as_bool(
                request.query_params.get("include_deprecated"), default=True
            ),
        )
        return Response(document, status=status.HTTP_200_OK)


class AttributeCatalogImportView(AdminScopeRequiredMixin, APIView):
    """POST /attribute-catalog/import/ — merge an exported document."""

    def post(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = _body(request)
        try:
            summary = AttributeCatalogService().import_catalog(
                ctx,
                body,
                on_collision=(
                    request.query_params.get("on_collision")
                    or body.get("on_collision")
                    or "skip"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(summary, status=status.HTTP_200_OK)


class AttributeCatalogDetailView(AdminScopeRequiredMixin, APIView):
    """GET/PUT/PATCH /attribute-catalog/{entry_id}/ — one catalog entry."""

    def get(self, request: Request, entry_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            entry = AttributeCatalogService().get_entry(ctx, entry_id)
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(entry, status=status.HTTP_200_OK)

    def put(self, request: Request, entry_id: UUID) -> Response:
        return self._update(request, entry_id)

    def patch(self, request: Request, entry_id: UUID) -> Response:
        return self._update(request, entry_id)

    def _update(self, request: Request, entry_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = _body(request)
        # Partial semantics: only keys the caller actually sent are touched.
        kwargs: dict[str, Any] = {
            key: body[key] for key in (
                "name", "definition", "category", "tags", "label",
                "help_text", "origin", "deprecated",
            ) if key in body
        }
        try:
            entry = AttributeCatalogService().update_entry(ctx, entry_id, **kwargs)
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(entry, status=status.HTTP_200_OK)


class AttributeCatalogDeprecateView(AdminScopeRequiredMixin, APIView):
    """POST /attribute-catalog/{entry_id}/deprecate/ — set the deprecated flag."""

    def post(self, request: Request, entry_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = _body(request)
        deprecated = _as_bool(body.get("deprecated"), default=True)
        try:
            entry = AttributeCatalogService().deprecate_entry(
                ctx, entry_id, deprecated=deprecated
            )
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(entry, status=status.HTTP_200_OK)


class AttributeCatalogAddToDefinitionView(AdminScopeRequiredMixin, APIView):
    """POST /attribute-catalog/{entry_id}/add-to-definition/.

    Body: ``{item_type, preset | workspace_id, on_collision?}``. Copies the
    entry's block into the target definition (one-shot; not a binding).
    """

    def post(self, request: Request, entry_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = _body(request)
        workspace_id = body.get("workspace_id")
        try:
            result = AttributeCatalogService().add_to_definition(
                ctx,
                entry_id,
                str(body.get("item_type") or ""),
                preset=body.get("preset") or None,
                workspace_id=UUID(str(workspace_id)) if workspace_id else None,
                on_collision=body.get("on_collision") or "skip",
            )
        except (TypeError, ValueError) as exc:
            return _validation(lang, f"Invalid workspace_id: {exc}")
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(result, status=status.HTTP_200_OK)


__all__ = [
    "AttributeCatalogAddToDefinitionView",
    "AttributeCatalogDeprecateView",
    "AttributeCatalogDetailView",
    "AttributeCatalogExportView",
    "AttributeCatalogImportView",
    "AttributeCatalogListView",
    "AttributeCatalogSearchView",
]
