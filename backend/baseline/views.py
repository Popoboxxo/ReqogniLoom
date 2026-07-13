"""
ARCH-L1-006 BaselineService — DRF views for the scope-preview endpoint.

leaf_id: COMP-BL-005
req_id:  REQ-L1-049 (Baseline scope-select with 3 scopes)

The view is exposed via :mod:`baseline.urls` and is intentionally kept
narrow: it accepts ``scope``, ``workspace_id`` and (optionally)
``artifact_id`` query parameters, and returns a read-only JSON payload with
the count + sample that would be captured by a Baseline of the requested
scope.

Permission semantics:
  - ``scope == "global"`` requires staff/superuser; the view returns 403
    otherwise.
  - For all other scopes, a workspace member with read access to the
    workspace can preview. The current implementation is intentionally
    permissive within a tenant (matches the rest of the baseline service
    surface); tighter per-workspace checks are delegated to the
    AuthAndTenancy layer (REQ-L1-039).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from baseline.serializers import ScopePreviewSerializer
from baseline.services import preview_scope_items

logger = logging.getLogger(__name__)


VALID_SCOPES = ("document", "project", "global")


def _user_is_global_admin(request: Request) -> bool:
    """Return whether the request's user is allowed to preview global scope.

    REQ-L1-049: scope=global requires staff/superuser. Unauthenticated
    requests (request.user is AnonymousUser) and ordinary users are rejected.
    The helper is exposed at module level so tests can patch it.
    """
    user = getattr(request, "user", None)
    if user is None:
        return False
    # Django's User.is_authenticated is False for AnonymousUser
    is_authed = getattr(user, "is_authenticated", False)
    if not is_authed:
        return False
    is_staff = bool(getattr(user, "is_staff", False))
    is_super = bool(getattr(user, "is_superuser", False))
    return is_staff or is_super


def _parse_uuid(value: Any, field_name: str) -> uuid.UUID | None:
    """Parse a UUID query parameter, returning None on failure."""
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


@api_view(["GET"])
@permission_classes([AllowAny])
def scope_preview(request: Request) -> Response:
    """Read-only preview of items that would be included in a Baseline.

    Endpoint: ``GET /api/v1/baselines/scope-preview/``

    Query parameters:
        scope:         "document" | "project" | "global" (required)
        workspace_id:  UUID (required for all scopes)
        artifact_id:   UUID (required when scope == "document")

    Response (200):
        {
            "scope":  "document" | "project" | "global",
            "count":  <int>,
            "sample": [{"id": ..., "title": ..., "type": ...}, ...]
        }

    Errors:
        400 — missing/invalid parameters, document scope without artifact_id
        403 — global scope requested by non-admin user
    """
    params: Mapping[str, str] = request.query_params

    raw_scope = params.get("scope")
    if not raw_scope:
        return Response(
            {"detail": "Query parameter 'scope' is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if raw_scope not in VALID_SCOPES:
        return Response(
            {
                "detail": (
                    f"Invalid scope {raw_scope!r}. "
                    f"Must be one of: {', '.join(VALID_SCOPES)}."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    raw_ws = params.get("workspace_id")
    if not raw_ws:
        return Response(
            {"detail": "Query parameter 'workspace_id' is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    workspace_id = _parse_uuid(raw_ws, "workspace_id")
    if workspace_id is None:
        return Response(
            {"detail": f"Invalid workspace_id: {raw_ws!r}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    artifact_id: uuid.UUID | None = None
    if raw_scope == "document":
        raw_artifact = params.get("artifact_id")
        if not raw_artifact:
            return Response(
                {"detail": "Query parameter 'artifact_id' is required for scope='document'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        artifact_id = _parse_uuid(raw_artifact, "artifact_id")
        if artifact_id is None:
            return Response(
                {"detail": f"Invalid artifact_id: {raw_artifact!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if raw_scope == "global" and not _user_is_global_admin(request):
        return Response(
            {"detail": "Global scope preview requires staff or superuser."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Determine the active tenant. If a TenantContext is set on this thread
    # (typical in a request flow) we honour it; otherwise we fall back to
    # None, which the service treats as "no tenant filter" — appropriate
    # for a read-only preview that the caller has already authorised.
    from persistence.tenancy import TenantContext

    try:
        tenant_id = TenantContext.get_tenant()
    except Exception:  # noqa: BLE001 — TenantContextNotSetError or similar
        tenant_id = None

    try:
        preview = preview_scope_items(
            scope=raw_scope,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            artifact_id=artifact_id,
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:  # noqa: BLE001 — log unexpected failures
        logger.exception("scope_preview failed: %s", exc)
        return Response(
            {"detail": "Internal error while computing scope preview."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    payload = ScopePreviewSerializer(preview.to_dict()).data
    return Response(payload, status=status.HTTP_200_OK)


class BaselineScopePreviewView:
    """Class-based wrapper around :func:`scope_preview`.

    Exposed so test code can resolve the view via a uniform name. The
    function-based ``scope_preview`` is the actual implementation that
    :mod:`baseline.urls` wires up.
    """

    @classmethod
    def as_view(cls):  # pragma: no cover — thin wrapper
        return scope_preview


__all__ = [
    "scope_preview",
    "BaselineScopePreviewView",
    "_user_is_global_admin",
]
