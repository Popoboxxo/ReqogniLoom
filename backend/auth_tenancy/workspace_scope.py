"""Request -> workspace resolution for workspace-scoped RBAC (GitHub #103).

``UserRole`` is modelled per workspace (the ``workspace`` FK is NOT NULL, so the
data model has no notion of a tenant-wide role). To evaluate RBAC against the
workspace a request actually targets, the request must first be mapped to a
workspace id — that is what :func:`resolve_request_workspace_id` does.

Resolution order (first hit wins), mirroring how the REST adapter itself locates
the workspace in :mod:`rest_api.views` / :mod:`rest_api.preset_guard`:

1. URL kwargs ``workspace_id`` / ``workspace_pk``
   (e.g. ``/api/v1/workspaces/<uuid:workspace_pk>/needs/``). A routed workspace
   is structurally authoritative: the view persists it (issue #49), so the
   authorization target must not be overridable from the body.
2. URL kwarg ``pk`` when the matched route is a ``workspaces/`` route
   (e.g. ``/api/v1/workspaces/<uuid:pk>/import/csv/``).
3. On unsafe methods, the request body field ``workspace_id``. On a flat create
   route the body is the value the serializer actually persists, so it is the
   authoritative target — the query parameter must not override it. The body is
   read for ``application/json``, ``application/x-www-form-urlencoded`` **and**
   ``multipart/form-data``: restricting this to JSON left a create bypass
   (SEC-02 review M1, ADR-013) in which a form-encoded create could smuggle a
   foreign ``workspace_id`` past the central seam.
4. Query parameter ``workspace_id``.

When an unsafe request names **two different** workspaces — URL/query on one side
and body on the other — the caller is rejected instead of silently picking a
winner: see :func:`resolve_create_workspace_mismatch` and
``resource_scope.WORKSPACE_TARGET_MISMATCH_DENIAL`` (SEC-02 review residual).

Returning ``None`` means "this request does not target one specific workspace"
(login, ``/api/v1/workspaces/`` list, admin-ops health, ...). Callers then keep
the tenant-wide role set, which is the pre-existing behaviour: this module only
*narrows* authority, it never widens it.

req_id: GitHub #103, ADR-013
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

# Content-type markers whose body may carry the target workspace. A create that
# names the workspace in the body must be resolved for *every* parsed body
# format, not only JSON: the SEC-02 review (M1) found a form-encoded create
# smuggling a foreign ``workspace_id`` past the seam because only "json" was
# recognised.
_BODY_CONTENT_TYPE_MARKERS: tuple[str, ...] = (
    "json",
    "form-urlencoded",
    "multipart",
)


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
    """Resolve the workspace from a parsed request body's ``workspace_id``.

    Covers JSON, form-urlencoded and multipart bodies alike: the body is parsed
    by DRF (``request.data``), which returns a ``dict`` for JSON and a
    ``QueryDict`` for form data; both expose ``.get``. Restricted to unsafe
    methods, and fully guarded: body parsing happens during authentication, so a
    malformed payload must not surface as an auth error — it has to reach the
    view's own 400 handling.
    """
    method = str(getattr(request, "method", "") or "").upper()
    if method not in _BODY_METHODS:
        return None

    content_type = str(getattr(request, "content_type", "") or "").lower()
    if not any(marker in content_type for marker in _BODY_CONTENT_TYPE_MARKERS):
        return None

    try:
        data = request.data
    except Exception:  # noqa: BLE001 — unparsable body is the view's problem
        return None

    # ``QueryDict``/``dict`` expose ``.get``; lists/strings/bytes do not and are
    # rejected here rather than raising.
    getter = getattr(data, "get", None)
    if getter is None or isinstance(data, (list, str, bytes)):
        return None
    return _coerce(getter("workspace_id"))


def _is_unsafe_method(request: Any) -> bool:
    """Return whether *request* may carry a workspace in its body."""
    return str(getattr(request, "method", "") or "").upper() in _BODY_METHODS


def resolve_request_workspace_id(request: Any) -> UUID | None:
    """Return the workspace a request targets, or ``None`` if not workspace-bound.

    Resolution order (see module docstring): URL kwargs first, then — on unsafe
    methods — the **body** (the value the serializer persists), and only then the
    query parameter. Preferring the body over the query for unsafe methods closes
    the residual in which a query parameter named workspace A (so the auth layer
    scoped the caller's roles to A) while the body persisted into workspace B.

    Args:
        request: The DRF/Django request being authenticated.

    Returns:
        The target workspace id, or ``None`` when the request is not scoped to a
        single workspace (callers must then fall back to tenant-wide roles).
    """
    sources = [_from_url]
    if _is_unsafe_method(request):
        sources.append(_from_body)
    sources.append(_from_query)
    for source in sources:
        try:
            resolved = source(request)
        except Exception:  # noqa: BLE001 — resolution is best-effort by design
            resolved = None
        if resolved is not None:
            return resolved
    return None


def resolve_request_named_workspace_id(request: Any) -> UUID | None:
    """Return the workspace named by the URL kwargs or query param, or ``None``.

    Deliberately ignores the body: this is the half of the resolution the auth
    layer uses when *no* body is present (list routes, workspace-named actions).
    """
    for source in (_from_url, _from_query):
        try:
            resolved = source(request)
        except Exception:  # noqa: BLE001 — resolution is best-effort by design
            resolved = None
        if resolved is not None:
            return resolved
    return None


def resolve_body_workspace_id(request: Any) -> UUID | None:
    """Return the workspace named in the request body, or ``None``."""
    try:
        return _from_body(request)
    except Exception:  # noqa: BLE001 — resolution is best-effort by design
        return None


def resolve_create_workspace_mismatch(request: Any) -> bool:
    """Return whether a request names two conflicting workspaces.

    ``True`` only when the request is an unsafe method that names one workspace
    in the URL/query and a **different** one in the body. The seam turns this
    into a fail-closed denial (ADR-013). A request that names only one side, or
    the same workspace on both, is not a mismatch.

    The helper is total: malformed ids resolve to ``None`` and never raise.
    """
    if not _is_unsafe_method(request):
        return False
    named = resolve_request_named_workspace_id(request)
    body = resolve_body_workspace_id(request)
    return named is not None and body is not None and named != body


def workspace_exists(workspace_id: UUID) -> bool:
    """Return whether *workspace_id* exists in the active tenant.

    Must be called **after** tenant activation: ``Workspace.objects`` is
    tenant-scoped, so a workspace of another tenant reads as non-existent. This
    is the single implementation shared by
    ``auth_tenancy.rest._workspace_exists`` (authentication) and
    ``auth_tenancy.resource_scope._workspace_in_active_tenant`` (the seam), so
    the existence check cannot drift between the two (ADR-013 review CODE-3).
    """
    from persistence.models import Workspace  # local import avoids circular dep

    return Workspace.objects.filter(id=workspace_id).exists()


__all__ = [
    "resolve_body_workspace_id",
    "resolve_create_workspace_mismatch",
    "resolve_request_named_workspace_id",
    "resolve_request_workspace_id",
    "workspace_exists",
]
