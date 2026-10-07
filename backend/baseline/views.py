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
  - The endpoint requires authentication like every other endpoint in the
    project (SA-23 fix): no ``AllowAny`` override, so it falls back to the
    project-wide ``DEFAULT_PERMISSION_CLASSES`` (``RbacPermission``), which
    maps GET to ``Operation.READ`` and returns 401 for anonymous callers.
  - ``scope == "global"`` additionally requires an **administrative
    principal**, resolved from the authenticated ``request.auth_context``:
    either the ``admin`` app role (``ROLE_ADMIN``) or an active tenant-admin
    (``TenantRole``). Django ``is_staff``/``is_superuser`` flags are only a
    fallback for session-authenticated requests. The view returns 403
    otherwise (bug #1198 — previously the check always read the UUID
    ``request.user`` surrogate and rejected every app-admin).
  - For all other scopes, any authenticated user with read access is
    permitted to preview. Tighter per-workspace checks are delegated to the
    AuthAndTenancy layer (REQ-L1-039).

Method contract (bug #1198):
  - The endpoint is **GET-only by design**. A scope preview is a pure read
    (it never mutates state) and reads all of its inputs from the query
    string, so no POST form is offered. Any non-GET method is rejected by
    DRF with ``405 Method Not Allowed`` — this is the intended contract, not
    a defect. Callers that POSTed expecting 200 were following a false
    expectation; REQ-L1-049 is documented here as GET.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from baseline.serializers import ScopePreviewSerializer
from baseline.services import preview_scope_items

logger = logging.getLogger(__name__)


VALID_SCOPES = ("document", "project", "global")


def _django_user_is_admin(user: Any) -> bool:
    """Return whether a Django ``User``-like object is staff/superuser.

    Only a genuine ``User`` reaches the ``True`` branch: ``AnonymousUser``
    has ``is_authenticated is False`` and the UUID string that
    ``AuthTenancyAuthentication`` feeds DRF as ``request.user`` lacks the
    attributes entirely (``getattr`` defaults to ``False``).
    """
    if user is None:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_staff", False)) or bool(
        getattr(user, "is_superuser", False)
    )


def _user_is_global_admin(request: Request) -> bool:
    """Return whether the request's principal may preview ``scope="global"``.

    REQ-L1-049: a global-scope preview spans every workspace of the tenant, so
    only an administrative principal may request it.

    Administrative standing is resolved from the authenticated
    :class:`~auth_tenancy.context.AuthContext` (``request.auth_context``) — the
    single source of truth for roles — **not** from Django's
    ``is_staff``/``is_superuser`` flags. ``AuthTenancyAuthentication`` feeds
    DRF the user id as ``request.user`` (a UUID string), so those flags are
    never present on it and a check against them would reject every caller,
    including a real admin (bug #1198).

    A caller qualifies when either:

    * the AuthContext carries the ``admin`` app role
      (:data:`~auth_tenancy.models.ROLE_ADMIN`) — a workspace or tenant-wide
      ``UserRole``, or
    * the caller holds an active tenant-admin role
      (:class:`~auth_tenancy.models.TenantRole`, the documented System-Admin
      elevation; see ``auth_tenancy.resource_scope._is_tenant_admin``).

    A genuine Django ``User`` with ``is_staff``/``is_superuser`` is still
    honoured as a fallback, covering session-authenticated requests and request
    objects assembled outside the auth seam. The helper fails closed: a
    tenant-admin lookup error denies. Exposed at module level so tests can
    patch it.
    """
    auth_context = getattr(request, "auth_context", None)
    if auth_context is not None:
        from auth_tenancy.models import ROLE_ADMIN

        if auth_context.has_role(ROLE_ADMIN):
            return True
        user_id = getattr(auth_context, "user_id", None)
        tenant_id = getattr(auth_context, "tenant_id", None)
        if user_id is not None and tenant_id is not None:
            try:
                from auth_tenancy.services import AuthorizationService

                if AuthorizationService().is_tenant_admin(
                    user_id=user_id, tenant_id=tenant_id
                ):
                    return True
            except Exception:  # noqa: BLE001 — fail closed on lookup error
                logger.warning(
                    "tenant-admin lookup failed for scope=global preview",
                    exc_info=True,
                )

    return _django_user_is_admin(getattr(request, "user", None))


def _parse_uuid(value: Any, field_name: str) -> uuid.UUID | None:
    """Parse a UUID query parameter, returning None on failure."""
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


@api_view(["GET"])
def scope_preview(request: Request) -> Response:
    """Read-only preview of items that would be included in a Baseline.

    Endpoint: ``GET /api/v1/baselines/scope-preview/``

    The endpoint is GET-only by design (bug #1198): it is a pure read whose
    inputs are query parameters, so a POST has no body contract to honour and
    is rejected with ``405 Method Not Allowed`` — see the module docstring.

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
        401 — unauthenticated caller (SA-23: no anonymous access)
        403 — global scope requested by a non-admin user
        405 — any non-GET method (the endpoint is read-only)
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
            {"detail": "Global scope preview requires an admin role or tenant-admin."},
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
