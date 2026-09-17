"""Thin REST client for ReqogniLoom's /api/v1/ — used by both the slash
command handler (__init__.py) and the dashboard backend (dashboard/plugin_api.py).

POC scope: no retries, no connection pooling, stdlib `urllib` only so the
plugin has zero extra dependencies beyond what Hermes itself ships.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from uuid import UUID


class ReqogniLoomError(RuntimeError):
    """Raised for any non-2xx response or transport failure."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


class ReqogniLoomClient:
    """Config resolved from environment variables:

    - ``REQOGNILOOM_BASE_URL`` (default ``http://localhost:8001``)
    - ``REQOGNILOOM_API_KEY``  (``reqlo_...`` — sent as ``Bearer`` token)
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or _env("REQOGNILOOM_BASE_URL", "http://localhost:8001")).rstrip("/")
        self.api_key = api_key or _env("REQOGNILOOM_API_KEY")

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ReqogniLoomError(f"{exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise ReqogniLoomError(f"could not reach {url}: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReqogniLoomError(f"non-JSON response from {url}: {raw[:200]!r}") from exc

    # -- unauthenticated ---------------------------------------------------

    def version(self) -> Dict[str, Any]:
        """GET /api/v1/version/ — public, no auth required."""
        return self._request("GET", "/api/v1/version/")

    # -- workspaces ----------------------------------------------------------

    def list_workspaces(self) -> List[Dict[str, Any]]:
        result = self._request("GET", "/api/v1/workspaces/")
        return result.get("results", result if isinstance(result, list) else [])

    # -- interviews ----------------------------------------------------------

    def start_interview(self, artifact_type: str, workspace_id: str) -> Dict[str, Any]:
        return self._request(
            "POST", "/api/v1/interviews/", {"artifact_type": artifact_type, "workspace_id": workspace_id}
        )

    def list_interviews(self, workspace_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        qs = f"?workspace_id={workspace_id}"
        if status:
            qs += f"&status={status}"
        result = self._request("GET", f"/api/v1/interviews/{qs}")
        return result.get("results", [])

    def get_state(self, session_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/interviews/{session_id}/state/")

    def answer(self, session_id: str, field: str, value: Any) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/answer/", {"field": field, "value": value})

    def chat(self, session_id: str, message: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/chat/", {"message": message})

    def formalize(self, session_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/formalize/", {})

    def abandon(self, session_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/abandon/", {})

    # -- stats (dashboard POC) -----------------------------------------------

    def stats(self, workspace_id: str) -> Dict[str, Any]:
        """A handful of cheap counts for the dashboard tab. Best-effort: a
        failing sub-call degrades that one number to ``None`` rather than
        failing the whole payload."""

        def _count(path: str) -> Optional[int]:
            try:
                result = self._request("GET", f"{path}?workspace_id={workspace_id}")
            except ReqogniLoomError:
                return None
            if isinstance(result, dict) and "count" in result:
                return result["count"]
            if isinstance(result, dict) and "results" in result:
                return len(result["results"])
            return None

        open_interviews = None
        try:
            open_interviews = len(self.list_interviews(workspace_id, status="in_progress"))
        except ReqogniLoomError:
            pass

        return {
            "workspace_id": workspace_id,
            "requirements": _count("/api/v1/requirements/"),
            "testcases": _count("/api/v1/testcases/"),
            "open_interviews": open_interviews,
        }


def resolve_workspace_id(client: ReqogniLoomClient, explicit: Optional[str] = None) -> str:
    """Resolve a workspace UUID: explicit arg wins, else the first workspace
    the API key can see. Raises ReqogniLoomError if neither works."""
    if explicit:
        try:
            UUID(explicit)
        except ValueError as exc:
            raise ReqogniLoomError(f"'{explicit}' is not a valid workspace UUID") from exc
        return explicit
    workspaces = client.list_workspaces()
    if not workspaces:
        raise ReqogniLoomError(
            "no workspace_id given and no workspaces visible to this API key — "
            "pass one explicitly, e.g. `/reqogniloom start requirement <workspace_id>`"
        )
    return workspaces[0]["id"]
