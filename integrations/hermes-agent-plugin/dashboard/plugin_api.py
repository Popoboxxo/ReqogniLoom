"""ReqogniLoom dashboard plugin backend.

Mounted at /api/plugins/reqogniloom/ by Hermes dashboard.

POC scope: four read-only endpoints backing the ReqogniLoom tab in
``dist/index.js``. No caching, no background scan — every request goes through
the shared client to ReqogniLoom's native MCP server (``POST /mcp/``), the same
pattern as the /reqogniloom slash command in __init__.py. Only the version
endpoint stays on REST (``GET /api/v1/version/``): it is public and has no MCP
tool.

Authentication
--------------
The plugin runs no server of its own: it returns an ``APIRouter`` that an
external Hermes dashboard mounts, and neither plugin.yaml nor
dashboard/manifest.json carries a port, bind address, ``secrets`` or ``env``
field, so the host hands the plugin no credential. The host dashboard's own
auth is therefore the only gate on this read-only surface — the plugin adds no
inbound second factor and reads no credential of its own. (The earlier opt-in
dashboard request-header second factor was removed for exactly that reason: the
host is the authoritative gate, and a secret the host never handed the plugin
cannot be a second factor for it.)

The outbound ``REQOGNILOOM_API_KEY`` stays the tenant credential for the MCP
calls; nothing here re-implements its validation or caches/persists ReqogniLoom
data.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

try:
    from fastapi import APIRouter
except Exception:  # Allows local unit tests without dashboard dependencies.
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn


# reqogniloom_client.py lives one directory up (the plugin root), alongside
# plugin.yaml and __init__.py — dashboard/ is not itself a Python package
# (matches plugins/hermes-achievements/dashboard/'s flat layout), so a
# relative import isn't available; put the plugin root on sys.path instead.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from reqogniloom_client import ReqogniLoomClient, ReqogniLoomError, resolve_workspace_id  # noqa: E402

router = APIRouter()

# These handlers are deliberately sync, not async: reqogniloom_client uses
# blocking urllib, and FastAPI only runs sync path operations in a worker
# threadpool — as async defs they would stall the dashboard event loop for the
# duration of every backend call (/stats makes three sequential ones).


@router.get("/stats")
def stats(workspace_id: str = "") -> Dict[str, Any]:
    """Counts for the resolved workspace; backend failures stay 200+error."""
    try:
        client = ReqogniLoomClient()
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return client.stats(ws_id)
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/workspaces")
def workspaces() -> Dict[str, Any]:
    """Workspaces visible to the configured API key."""
    try:
        client = ReqogniLoomClient()
        return {"workspaces": client.list_workspaces()}
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/version")
def version() -> Dict[str, Any]:
    """ReqogniLoom build version; backend failures stay 200+error."""
    try:
        client = ReqogniLoomClient()
        return client.version()
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/interviews")
def interviews(workspace_id: str = "", status: str = "in_progress") -> Dict[str, Any]:
    """Interviews of one workspace, defaulting to the open ones.

    A count answers "how many" but not "which", so a session left hanging was
    invisible until it aged out; the tab renders these as detail rows.
    Read-only and best-effort, like the other handlers: a backend failure stays
    200+error.
    """
    try:
        client = ReqogniLoomClient()
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return {"workspace_id": ws_id, "interviews": client.list_interviews(ws_id, status or None)}
    except ReqogniLoomError as exc:
        return {"error": str(exc)}
