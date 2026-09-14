"""REST endpoints for AWMS value migrations (spec §7, WS7 #940).

Shaped after ``rest_api/attribute_catalog_views.py``: the same admin gate, the
same ``build_error_response`` envelope, the same explicit error mapping
(400/403/404/409). The whole resource is tenant-wide admin tooling, so every
endpoint requires ``admin``.

Routes::

    POST /api/v1/attribute-migration/plan/            preview (dry run)
    POST /api/v1/attribute-migration/apply/           apply a plan
    POST /api/v1/attribute-migration/                 apply (spec alias)
    GET  /api/v1/attribute-migration/runs/            list runs
    GET  /api/v1/attribute-migration/runs/{id}/       one run
    POST /api/v1/attribute-migration/runs/{id}/rollback/  restore snapshots

No ORM in this module by design (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access``): every
read and write goes through
``application.attribute_migration_service.AttributeMigrationService``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.attribute_migration_service import (
    AttributeMigrationConflict,
    AttributeMigrationNotFound,
    AttributeMigrationService,
)
from application.base import PermissionDeniedError
from attribute_definitions.migration_plan import MigrationPlanError
from auth_tenancy.models import ROLE_ADMIN
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _require_admin(request: Request):
    """Return ``(ctx, lang)`` or a 403 Response when the caller is not admin."""
    lang = detect_lang(request)
    ctx = get_auth_context(request)
    if not ctx.has_role(ROLE_ADMIN):
        return Response(
            build_error_response(
                "PERMISSION_DENIED", lang, message="Admin role required."
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return ctx, lang


def _error(code: str, http_status: int, lang: str, message: str) -> Response:
    return Response(build_error_response(code, lang, message=message), status=http_status)


def _handle_common(exc: Exception, lang: str) -> Response | None:
    """Map the migration service exceptions to their REST envelope."""
    if isinstance(exc, PermissionDeniedError):
        return _error("PERMISSION_DENIED", status.HTTP_403_FORBIDDEN, lang, str(exc))
    if isinstance(exc, AttributeMigrationNotFound):
        return _error("NOT_FOUND", status.HTTP_404_NOT_FOUND, lang, str(exc))
    if isinstance(exc, AttributeMigrationConflict):
        return _error("CONFLICT", status.HTTP_409_CONFLICT, lang, str(exc))
    if isinstance(exc, MigrationPlanError):
        return _error(
            "VALIDATION_ERROR", status.HTTP_400_BAD_REQUEST, lang, "; ".join(exc.errors)
        )
    return None


def _body(request: Request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


def _plan_document(request: Request) -> dict[str, Any]:
    """Accept the plan as the request body or wrapped under ``{"plan": ...}``."""
    body = _body(request)
    wrapped = body.get("plan")
    if isinstance(wrapped, dict) and "steps" in wrapped:
        return wrapped
    return body


class AttributeMigrationPlanView(APIView):
    """POST /attribute-migration/plan/ — validate + full dry-run preview."""

    def post(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            report = AttributeMigrationService().dry_run(ctx, _plan_document(request))
        except Exception as exc:  # noqa: BLE001 - routed through _handle_common
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(report, status=status.HTTP_200_OK)


class AttributeMigrationApplyView(APIView):
    """POST /attribute-migration/apply/ — execute a plan for real."""

    def post(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            report = AttributeMigrationService().apply(ctx, _plan_document(request))
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(report, status=status.HTTP_200_OK)


class AttributeMigrationRunListView(APIView):
    """GET /attribute-migration/runs/ — list runs of the active tenant."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        runs = AttributeMigrationService().list_runs(
            ctx,
            plan_id=request.query_params.get("plan_id") or None,
            mode=request.query_params.get("mode") or None,
            status=request.query_params.get("status") or None,
            limit=limit,
        )
        return Response({"runs": runs, "count": len(runs)}, status=status.HTTP_200_OK)


class AttributeMigrationRunDetailView(APIView):
    """GET /attribute-migration/runs/{run_id}/ — one run incl. its report."""

    def get(self, request: Request, run_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            run = AttributeMigrationService().get_run(ctx, run_id)
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(run, status=status.HTTP_200_OK)


class AttributeMigrationRollbackView(APIView):
    """POST /attribute-migration/runs/{run_id}/rollback/ — restore snapshots."""

    def post(self, request: Request, run_id: UUID) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            result = AttributeMigrationService().rollback(ctx, run_id)
        except Exception as exc:  # noqa: BLE001
            mapped = _handle_common(exc, lang)
            if mapped is None:
                raise
            return mapped
        return Response(result, status=status.HTTP_200_OK)


__all__ = [
    "AttributeMigrationApplyView",
    "AttributeMigrationPlanView",
    "AttributeMigrationRollbackView",
    "AttributeMigrationRunDetailView",
    "AttributeMigrationRunListView",
]
