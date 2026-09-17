"""ReqogniLoom dashboard plugin backend.

Mounted at /api/plugins/reqogniloom/ by Hermes dashboard.

POC scope: three read-only endpoints backing the (also POC-scope) stats tab
in dist/index.js. No caching, no background scan — every request hits
ReqogniLoom's REST API directly, same pattern as the /reqogniloom slash
command in __init__.py (both share reqogniloom_client.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

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


@router.get("/stats")
async def stats(workspace_id: str = ""):
    client = ReqogniLoomClient()
    try:
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return client.stats(ws_id)
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/workspaces")
async def workspaces():
    client = ReqogniLoomClient()
    try:
        return {"workspaces": client.list_workspaces()}
    except ReqogniLoomError as exc:
        return {"error": str(exc)}


@router.get("/version")
async def version():
    client = ReqogniLoomClient()
    try:
        return client.version()
    except ReqogniLoomError as exc:
        return {"error": str(exc)}
