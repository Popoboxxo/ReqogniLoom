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

#: Per-request socket timeout. This bounds each socket operation, not the
#: whole response: a slow-drip backend can still exceed it in total.
REQUEST_TIMEOUT_SECONDS = 10

_AUTH_STATUS_CODES = (401, 403)


class ReqogniLoomError(RuntimeError):
    """Raised for any non-2xx response or transport failure."""


class _AuthError(ReqogniLoomError):
    """API key missing or rejected. A configuration problem, not a data
    problem: callers that degrade failures to ``None`` must re-raise this,
    because a null payload reads as "nothing there" rather than "no key"."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _list_results(result: Any, path: str) -> List[Dict[str, Any]]:
    """Normalise a list endpoint's payload to a plain list. A dict without
    ``results`` is a shape or auth failure, not an empty collection —
    returning ``[]`` for it would report "nothing to see" for a problem the
    user has to fix."""
    if isinstance(result, dict):
        items = result.get("results")
        if isinstance(items, list):
            return items
    elif isinstance(result, list):
        return result
    raise ReqogniLoomError(
        f"unexpected list response from {path}: expected a paginated object with "
        f"'results' or a JSON array, got {type(result).__name__}"
    )


def _total_count(result: Any) -> Optional[int]:
    """Total number of items behind a paginated envelope, or ``None`` when the
    response carries no ``count``. The length of one page is a page size:
    reporting it as the total is a silently wrong number, not a missing one."""
    if isinstance(result, dict) and isinstance(result.get("count"), int):
        return result["count"]
    return None


class ReqogniLoomClient:
    """Config resolved from environment variables:

    - ``REQOGNILOOM_BASE_URL`` (default ``http://localhost:8001``)
    - ``REQOGNILOOM_API_KEY``  (``reqlo_...`` — sent as ``Bearer`` token)
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or _env("REQOGNILOOM_BASE_URL", "http://localhost:8001")).rstrip("/")
        self.api_key = api_key or _env("REQOGNILOOM_API_KEY")

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        *,
        requires_api_key: bool = True,
    ) -> Any:
        """Perform one REST call.

        Only ``ReqogniLoomError`` (or a subclass) ever leaves this method — no
        bare ``OSError``/``TimeoutError``/``AttributeError`` may reach the
        slash command, whose ``except ReqogniLoomError`` is its whole error
        contract. ``requires_api_key`` defaults to True so that the one
        genuinely public endpoint has to opt out explicitly, and a missing
        key can never be sent as an anonymous request.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif requires_api_key:
            raise _AuthError(
                "REQOGNILOOM_API_KEY is not set — export a ReqogniLoom API key "
                "(a 'reqlo_...' key) to use this plugin"
            )
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Must precede the OSError clause: HTTPError subclasses OSError.
            body_text = exc.read().decode("utf-8", errors="replace")
            message = f"{exc.code}: {body_text}"
            if exc.code in _AUTH_STATUS_CODES:
                raise _AuthError(message) from exc
            raise ReqogniLoomError(message) from exc
        except urllib.error.URLError as exc:
            raise ReqogniLoomError(f"could not reach {url}: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            # urlopen only wraps send-side failures in URLError; a timeout or
            # reset while reading the response body surfaces as a bare OSError.
            raise ReqogniLoomError(
                f"could not read {url}: {exc} "
                f"[type={type(exc).__name__}, errno={getattr(exc, 'errno', None)}]"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReqogniLoomError(f"non-JSON response from {url}: {raw[:200]!r}") from exc

    # -- unauthenticated ---------------------------------------------------

    def version(self) -> Dict[str, Any]:
        """GET /api/v1/version/ — public, no auth required."""
        return self._request("GET", "/api/v1/version/", requires_api_key=False)

    # -- workspaces ----------------------------------------------------------

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """GET /api/v1/workspaces/ — a DRF page or a bare JSON array."""
        path = "/api/v1/workspaces/"
        return _list_results(self._request("GET", path), path)

    # -- interviews ----------------------------------------------------------

    def start_interview(self, artifact_type: str, workspace_id: str) -> Dict[str, Any]:
        return self._request(
            "POST", "/api/v1/interviews/", {"artifact_type": artifact_type, "workspace_id": workspace_id}
        )

    def _interviews_query(self, workspace_id: str, status: Optional[str] = None) -> str:
        """Path of the interviews list endpoint; shared by list_interviews and
        stats so both address the same collection the same way."""
        qs = f"?workspace_id={workspace_id}"
        if status:
            qs += f"&status={status}"
        return f"/api/v1/interviews/{qs}"

    def list_interviews(self, workspace_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /api/v1/interviews/ — one page of sessions, filtered server-side."""
        path = self._interviews_query(workspace_id, status)
        return _list_results(self._request("GET", path), path)

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
        failing the whole payload. A missing or rejected API key is not
        degradation and always propagates.

        Counts come from the DRF ``count`` field only — a page length would
        report the page size as the total.
        """

        def _count(path: str) -> Optional[int]:
            try:
                result = self._request("GET", f"{path}?workspace_id={workspace_id}")
            except _AuthError:
                raise
            except ReqogniLoomError:
                return None
            return _total_count(result)

        try:
            interviews = self._request("GET", self._interviews_query(workspace_id, "in_progress"))
        except _AuthError:
            raise
        except ReqogniLoomError:
            open_interviews = None
        else:
            open_interviews = _total_count(interviews)

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
    first = workspaces[0]
    workspace_id = first.get("id") if isinstance(first, dict) else None
    if not workspace_id:
        raise ReqogniLoomError(
            f"malformed workspace entry {first!r} — no 'id' field; pass a workspace_id "
            "explicitly, e.g. `/reqogniloom start requirement <workspace_id>`"
        )
    return workspace_id
