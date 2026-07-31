"""Request -> workspace resolution for workspace-scoped RBAC (GitHub #103).

``UserRole`` is modelled per workspace (the ``workspace`` FK is NOT NULL, so the
data model has no notion of a tenant-wide role). To evaluate RBAC against the
workspace a request actually targets, the request must first be mapped to a
workspace id — that is what :func:`resolve_request_workspace_id` does.

Resolution order (first hit wins), mirroring how the REST adapter itself locates
the workspace in :mod:`rest_api.views` / :mod:`rest_api.preset_guard`:

1. URL kwargs ``workspace_id`` / ``workspace_pk``
   (e.g. ``/api/v1/workspaces/<uuid:workspace_pk>/needs/``).
2. URL kwarg ``pk`` when the matched route is a ``workspaces/`` route
   (e.g. ``/api/v1/workspaces/<uuid:pk>/import/csv/``).
3. Query parameter ``workspace_id``.
4. JSON request body field ``workspace_id`` on unsafe methods (create endpoints
   carry the target workspace in the payload).

Returning ``None`` means "this request does not target one specific workspace"
(login, ``/api/v1/workspaces/`` list, admin-ops health, ...). Callers then keep
the tenant-wide role set, which is the pre-existing behaviour: this module only
*narrows* authority, it never widens it.

req_id: GitHub #103
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

# URL kwargs that unambiguously name a workspace.
_WORKSPACE_URL_KWARGS: tuple[str, ...] = ("workspace_id", "workspace_pk")

# Route prefix under which a bare ``pk`` kwarg denotes a workspace. Compared
# against ``ResolverMatch.route``, which is the URLconf pattern string
# (e.g. ``api/v1/workspaces/<uuid:pk>/import/csv/``) and therefore not
# attacker-controlled.
_WORKSPACE_ROUTE_MARKER = "workspaces/<uuid:pk>"

# Methods whose body may carry the target workspace.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _coerce(value: Any) -> UUID | None:
    """Return ``value`` as a UUID, or ``None`` if it is not a valid UUID.

    Malformed input must never raise here: an unparsable workspace id simply
    means "not resolvable", and the request then falls through to the view,
    which produces the proper 400/404.
    """
    if value is None or isinstance(value, (list, dict, bool)):
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _from_url(request: Any) -> UUID | None:
    """Resolve the workspace from the resolved URL pattern's kwargs."""
    match = getattr(request, "resolver_match", None)
    if match is None:
        return None

    kwargs = getattr(match, "kwargs", None) or {}
    for key in _WORKSPACE_URL_KWARGS:
        resolved = _coerce(kwargs.get(key))
        if resolved is not None:
            return resolved

    route = getattr(match, "route", "") or ""
    if _WORKSPACE_ROUTE_MARKER in route:
        return _coerce(kwargs.get("pk"))
    return None


def _from_query(request: Any) -> UUID | None:
    """Resolve the workspace from the ``workspace_id`` query parameter."""
    params = getattr(request, "query_params", None)
    if params is None:
        params = getattr(request, "GET", None)
    if params is None:
        return None
    return _coerce(params.get("workspace_id"))


def _from_body(request: Any) -> UUID | None:
    """Resolve the workspace from a JSON body's ``workspace_id`` field.

    Restricted to unsafe methods with a JSON content type, and fully guarded:
    body parsing happens during authentication, so a malformed payload must not
    surface as an auth error — it has to reach the view's own 400 handling.
    """
    method = str(getattr(request, "method", "") or "").upper()
    if method not in _BODY_METHODS:
        return None

    content_type = str(getattr(request, "content_type", "") or "").lower()
    if "json" not in content_type:
        return None

    try:
        data = request.data
    except Exception:  # noqa: BLE001 — unparsable body is the view's problem
        return None

    if not isinstance(data, dict):
        return None
    return _coerce(data.get("workspace_id"))


def resolve_request_workspace_id(request: Any) -> UUID | None:
    """Return the workspace a request targets, or ``None`` if not workspace-bound.

    Args:
        request: The DRF/Django request being authenticated.

    Returns:
        The target workspace id, or ``None`` when the request is not scoped to a
        single workspace (callers must then fall back to tenant-wide roles).
    """
    for source in (_from_url, _from_query, _from_body):
        try:
            resolved = source(request)
        except Exception:  # noqa: BLE001 — resolution is best-effort by design
            resolved = None
        if resolved is not None:
            return resolved
    return None


__all__ = ["resolve_request_workspace_id"]
