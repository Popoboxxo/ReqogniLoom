"""ReqogniLoom dashboard plugin backend.

Mounted at /api/plugins/reqogniloom/ by Hermes dashboard.

POC scope: three read-only endpoints backing the (also POC-scope) stats tab
in dist/index.js. No caching, no background scan — every request hits
ReqogniLoom's REST API directly, same pattern as the /reqogniloom slash
command in __init__.py (both share reqogniloom_client.py).

Inbound authentication
----------------------
The plugin runs no server of its own: it returns an ``APIRouter`` that an
external Hermes dashboard mounts, and neither plugin.yaml nor
dashboard/manifest.json carries a port, bind address, ``secrets`` or ``env``
field, so the host hands the plugin no credential. Every endpoint is therefore
gated on a shared secret the operator exports into the environment of the
process that runs the dashboard:

* ``REQOGNILOOM_DASHBOARD_TOKEN`` — expected value of the
  ``X-ReqogniLoom-Dashboard-Token`` request header. Unset or empty rejects
  *every* request: no default token, no dev-mode bypass, no "FastAPI missing,
  allow" escape hatch. Misconfiguration fails closed, not open.
* ``REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS`` — optional comma-separated
  ``Origin`` allowlist. Unset means loopback only (``http://localhost:*``,
  ``http://127.0.0.1:*``, ``http://[::1]:*``); it never widens to ``*``, and a
  wildcard entry is discarded rather than honoured.
* ``REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS`` — optional comma-separated ``Host``
  allowlist with the same loopback default. It blunts DNS-rebinding, which the
  ``Origin`` check cannot see: a rebound name reaches 127.0.0.1 while sending
  an attacker-chosen ``Host``.

The credential travels in a custom request header rather than a cookie because
a custom header forces a CORS preflight for every cross-origin browser
request, so a foreign-origin page can neither attach it silently nor read the
response. Cookies are attached automatically by the browser and are CSRF-able;
query parameters leak into access logs and browser history. Together with the
constant-time comparison below this is the tightest meaningful restriction
available to a host that supplies no credential of its own.

The gate is an edge check, deliberately not a second tenant-auth layer: the
outbound ``REQOGNILOOM_API_KEY`` stays the tenant credential, and nothing here
re-implements its validation or caches/persists ReqogniLoom data.
"""
from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Mapping as MappingABC
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

try:
    from fastapi import APIRouter, Depends, HTTPException, Request
except Exception:  # Allows local unit tests without dashboard dependencies.
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

    Depends = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment,misc]


# reqogniloom_client.py lives one directory up (the plugin root), alongside
# plugin.yaml and __init__.py — dashboard/ is not itself a Python package
# (matches plugins/hermes-achievements/dashboard/'s flat layout), so a
# relative import isn't available; put the plugin root on sys.path instead.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from reqogniloom_client import ReqogniLoomClient, ReqogniLoomError, resolve_workspace_id  # noqa: E402

#: The single request header carrying the inbound dashboard credential.
CREDENTIAL_HEADER = "X-ReqogniLoom-Dashboard-Token"

#: Environment variable holding the expected credential. Unset/empty ⇒ reject.
TOKEN_ENV_VAR = "REQOGNILOOM_DASHBOARD_TOKEN"

#: Optional comma-separated ``Origin`` allowlist; unset ⇒ _DEFAULT_ORIGINS.
ALLOWED_ORIGINS_ENV_VAR = "REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS"

#: Optional comma-separated ``Host`` allowlist; unset ⇒ _DEFAULT_HOSTS.
ALLOWED_HOSTS_ENV_VAR = "REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS"

#: Port wildcard for allowlist entries, e.g. ``http://127.0.0.1:*``.
_ANY_PORT = "*"

#: Tightest default the dashboard's own origin can satisfy: loopback, any
#: port, plain HTTP. Everything else has to be opted into explicitly.
_DEFAULT_ORIGINS: Tuple[str, ...] = ("http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*")
_DEFAULT_HOSTS: Tuple[str, ...] = ("localhost:*", "127.0.0.1:*", "[::1]:*")

_UNAUTHORIZED = 401
_FORBIDDEN = 403


class DashboardAuthError(PermissionError):
    """An inbound request was rejected before it could reach ReqogniLoom.

    ``status_code`` is what the mounted router should answer with; ``detail``
    is deliberately free of any part of the configured secret.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def enforce_dashboard_auth(headers: Optional[Mapping[str, str]]) -> None:
    """Authorise one inbound request, or raise :class:`DashboardAuthError`.

    Framework-free and ReqogniLoom-free on purpose: it reads nothing but the
    request headers and the process environment, so the very same code path is
    exercised by direct unit tests and by the mounted router. A header source
    that is not a string mapping (``None`` included) reads as "no headers at
    all" — the rejection path, never a pass.

    Raises:
        DashboardAuthError: 403 when the guard is unconfigured or the request's
            origin/host is not allowlisted, 401 when the credential is missing
            or wrong.
    """
    expected = _env(TOKEN_ENV_VAR)
    if not expected:
        raise DashboardAuthError(
            _FORBIDDEN,
            f"{TOKEN_ENV_VAR} is not set — the dashboard API rejects every request "
            f"until the operator exports it into the dashboard process environment",
        )
    _check_allowed_origin(headers)
    _check_allowed_host(headers)
    presented = _header(headers, CREDENTIAL_HEADER)
    if not presented:
        raise DashboardAuthError(_UNAUTHORIZED, f"missing {CREDENTIAL_HEADER} request header")
    # Encoding to bytes keeps compare_digest usable for non-ASCII input (it
    # raises on str operands otherwise, which would answer 500, not 401). The
    # comparison leaks nothing but the token's length.
    if not secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise DashboardAuthError(_UNAUTHORIZED, "invalid dashboard credential")


def _env(name: str) -> str:
    """Read one environment variable, empty for unset (read at call time)."""
    return (os.environ.get(name) or "").strip()


def _header(headers: Optional[Mapping[str, str]], name: str) -> str:
    """Case-insensitive, whitespace-trimmed header lookup.

    HTTP header names are case-insensitive while a plain dict is not, so the
    lookup cannot go through ``.get()``. Anything that is not a string mapping
    yields ``""`` — the rejection path.
    """
    if not isinstance(headers, MappingABC):
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == wanted and isinstance(value, str):
            return value.strip()
    return ""


def _allowlist(env_var: str, default: Sequence[str]) -> List[str]:
    """Parse a comma-separated allowlist from the environment.

    An unset (or blank) variable yields the loopback ``default``; a variable
    that parses to no usable entry yields an empty list, which matches nothing
    — an operator typo must narrow access, never widen it.
    """
    raw = _env(env_var)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _check_allowed_origin(headers: Optional[Mapping[str, str]]) -> None:
    """Validate ``Origin`` when the request carries one.

    An absent ``Origin`` is a non-browser caller (a same-origin GET from the
    dashboard page sends none, nor does curl), which the credential check alone
    holds in line. A present-but-unmatchable one — including the bare ``null``
    a sandboxed or ``file://`` page sends — is rejected.
    """
    origin = _header(headers, "Origin")
    if not origin:
        return
    candidate = _split_authority(origin)
    entries = [_split_authority(item) for item in _allowlist(ALLOWED_ORIGINS_ENV_VAR, _DEFAULT_ORIGINS)]
    if candidate is not None and any(
        entry is not None and _matches(entry, candidate, check_scheme=True)
        for entry in entries
    ):
        return
    raise DashboardAuthError(_FORBIDDEN, "origin is not in the dashboard allowlist")


def _check_allowed_host(headers: Optional[Mapping[str, str]]) -> None:
    """Validate ``Host`` when the request carries one (DNS-rebinding guard)."""
    host = _header(headers, "Host")
    if not host:
        return
    candidate = _split_authority(host)
    entries = [_split_authority(item) for item in _allowlist(ALLOWED_HOSTS_ENV_VAR, _DEFAULT_HOSTS)]
    if candidate is not None and any(
        entry is not None and _matches(entry, candidate, check_scheme=False)
        for entry in entries
    ):
        return
    raise DashboardAuthError(_FORBIDDEN, "host is not in the dashboard allowlist")


def _split_authority(value: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Normalise ``[scheme://]host[:port|*]`` into ``(scheme, host, port)``.

    ``port`` is ``None`` when absent and ``"*"`` for an any-port entry.
    Returns ``None`` for anything that names no concrete scheme/host — notably
    the bare ``*`` and the ``null`` origin, neither of which may ever match.
    """
    candidate = value.strip()
    if not candidate:
        return None
    if "://" in candidate:
        parts = urlsplit(candidate)
        scheme, netloc = parts.scheme.lower(), parts.netloc
    else:
        # Host headers and scheme-less allowlist entries are bare authorities.
        scheme, netloc = "http", urlsplit(f"//{candidate}").netloc
    if not scheme or not netloc or "@" in netloc:
        return None
    host, _, port = netloc.rpartition(":")
    if not host or netloc.endswith("]"):
        host, port = netloc, ""
    host = host.lower()
    if host in ("*", "[*]"):
        return None
    if port == _ANY_PORT:
        return (scheme, host, _ANY_PORT)
    return (scheme, host, port or None)


def _matches(
    entry: Tuple[str, str, Optional[str]],
    candidate: Tuple[str, str, Optional[str]],
    *,
    check_scheme: bool,
) -> bool:
    """Compare one allowlist entry against one request authority.

    An entry without a port matches only a request without a port, so an
    allowlist entry is never silently widened; use ``host:*`` for any port.
    """
    if entry[1] != candidate[1]:
        return False
    if check_scheme and entry[0] != candidate[0]:
        return False
    if entry[2] == _ANY_PORT:
        return True
    if entry[2] is None:
        return candidate[2] is None
    return entry[2] == candidate[2]


def _authorize(request: Any) -> None:
    """Run the inbound gate for one request and translate its failure.

    The request is reached through ``getattr`` on purpose: a real FastAPI
    ``Request`` supplies the headers, while a direct call (or the framework-free
    stub path) supplies nothing and is therefore rejected. When FastAPI is
    available the framework-free failure becomes an ``HTTPException`` so the
    mounted router answers 401/403 instead of a 200 carrying an error body.
    """
    headers = getattr(request, "headers", None)
    try:
        enforce_dashboard_auth(headers)
    except DashboardAuthError as exc:
        if HTTPException is None:
            raise
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def _require_dashboard_auth(request: Request = None) -> None:
    """Router-level gate, registered as a dependency on every route."""
    _authorize(request)


#: Empty when FastAPI is absent, so the stub router can swallow the kwarg.
_ROUTE_DEPENDENCIES: List[Any] = [Depends(_require_dashboard_auth)] if Depends is not None else []

router = APIRouter()

# These handlers are deliberately sync, not async: reqogniloom_client uses
# blocking urllib, and FastAPI only runs sync path operations in a worker
# threadpool — as async defs they would stall the dashboard event loop for the
# duration of every backend call (/stats makes three sequential ones).
#
# Each handler re-checks in its body as well as through the route dependency:
# the in-handler gate is the one that holds for a direct call and for a host
# that reassembles the routes without the declared dependencies.


@router.get("/stats", dependencies=_ROUTE_DEPENDENCIES)
def stats(workspace_id: str = "", request: Request = None) -> Dict[str, Any]:
    """Counts for the resolved workspace; backend failures stay 200+error."""
    _authorize(request)
    client = ReqogniLoomClient()
    try:
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return client.stats(ws_id)
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/workspaces", dependencies=_ROUTE_DEPENDENCIES)
def workspaces(request: Request = None) -> Dict[str, Any]:
    """Workspaces visible to the configured API key."""
    _authorize(request)
    client = ReqogniLoomClient()
    try:
        return {"workspaces": client.list_workspaces()}
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/version", dependencies=_ROUTE_DEPENDENCIES)
def version(request: Request = None) -> Dict[str, Any]:
    """ReqogniLoom build version; backend failures stay 200+error."""
    _authorize(request)
    client = ReqogniLoomClient()
    try:
        return client.version()
    except ReqogniLoomError as exc:
        return {"error": str(exc)}
