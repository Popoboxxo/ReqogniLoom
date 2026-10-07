"""Thin REST client for ReqogniLoom's /api/v1/ — used by both the slash
command handler (__init__.py) and the dashboard backend (dashboard/plugin_api.py).

POC scope: no retries, no connection pooling, stdlib `urllib` only so the
plugin has zero extra dependencies beyond what Hermes itself ships.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

#: Per-request socket timeout. This bounds each socket operation, not the
#: whole response: a slow-drip backend can still exceed it in total.
REQUEST_TIMEOUT_SECONDS = 10

#: Used when neither the ``base_url`` argument nor ``REQOGNILOOM_BASE_URL``
#: configures a target. Kept as the documented local-dev default; the failure
#: path below makes it loud rather than letting a request hit it silently.
_DEFAULT_BASE_URL = "http://localhost:8001"

_AUTH_STATUS_CODES = (401, 403)


class ReqogniLoomError(RuntimeError):
    """Raised for any non-2xx response or transport failure."""


class _AuthError(ReqogniLoomError):
    """API key missing or rejected. A configuration problem, not a data
    problem: callers that degrade failures to ``None`` must re-raise this,
    because a null payload reads as "nothing there" rather than "no key"."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _validate_base_url(value: str) -> None:
    """Reject a base URL that cannot address a ReqogniLoom instance.

    An empty or non-http(s) value is a configuration mistake: failing here
    names the variable and the offending value at construction, instead of
    surfacing later as a puzzling transport error against a malformed URL.
    """
    if value and value.startswith(("http://", "https://")):
        return
    raise ReqogniLoomError(
        f"invalid REQOGNILOOM_BASE_URL {value!r}: expected an http:// or https:// URL, "
        f"e.g. REQOGNILOOM_BASE_URL=http://localhost:8001"
    )


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

    An unset ``REQOGNILOOM_BASE_URL`` still falls back to the local default, but
    a transport failure then says so explicitly: a silent miss against
    ``localhost`` is the hardest misconfiguration to spot from the terse
    ``URLError`` alone.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        if base_url is not None:
            configured = base_url.strip()
            self._using_default_base_url = False
        else:
            env_value = os.environ.get("REQOGNILOOM_BASE_URL")
            if env_value is None:
                configured = _DEFAULT_BASE_URL
                self._using_default_base_url = True
            else:
                configured = env_value.strip()
                self._using_default_base_url = False
        self.base_url = configured.rstrip("/")
        _validate_base_url(self.base_url)
        self.api_key = api_key or _env("REQOGNILOOM_API_KEY")

    def _unconfigured_target_hint(self) -> str:
        """Actionable suffix for a transport failure when no base URL was
        configured: the request silently went to the default, which is the
        usual cause. Empty when ``REQOGNILOOM_BASE_URL`` (or an explicit
        ``base_url``) is set, so a genuinely mis-addressed instance does not
        get a misleading hint."""
        if not self._using_default_base_url:
            return ""
        return (
            f" — REQOGNILOOM_BASE_URL is not set, so the request went to the "
            f"default {self.base_url}; set REQOGNILOOM_BASE_URL to your "
            f"ReqogniLoom instance (e.g. https://reqogniloom.example.com)"
        )

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
        # ``path`` is normally an app-relative path, but a paginated ``next``
        # link is an absolute URL built by DRF from the request host — accept
        # both so the pagination loop can pass ``next`` straight through.
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
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
            raise ReqogniLoomError(
                f"could not reach {url}: {exc.reason}{self._unconfigured_target_hint()}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            # urlopen only wraps send-side failures in URLError; a timeout or
            # reset while reading the response body surfaces as a bare OSError.
            raise ReqogniLoomError(
                f"could not read {url}: {exc} "
                f"[type={type(exc).__name__}, errno={getattr(exc, 'errno', None)}]"
                f"{self._unconfigured_target_hint()}"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReqogniLoomError(f"non-JSON response from {url}: {raw[:200]!r}") from exc

    def _get_all(self, path: str) -> List[Dict[str, Any]]:
        """GET a paginated list endpoint and follow ``next`` to the last page.

        Returns every item across all pages. DRF sets ``next`` to an absolute
        URL; ``_request`` accepts absolute URLs as well as paths, so the link
        is passed through unchanged. A repeated ``next`` is treated as the end
        of the chain, so a misbehaving server cannot spin this loop forever.
        """
        items: List[Dict[str, Any]] = []
        seen: set[str] = set()
        next_url: Optional[str] = path
        while next_url:
            if next_url in seen:
                logger.warning("pagination: repeated 'next' %r — stopping", next_url)
                break
            seen.add(next_url)
            result = self._request("GET", next_url)
            items.extend(_list_results(result, path))
            candidate = result.get("next") if isinstance(result, dict) else None
            next_url = candidate if isinstance(candidate, str) and candidate else None
        return items

    # -- unauthenticated ---------------------------------------------------

    def version(self) -> Dict[str, Any]:
        """GET /api/v1/version/ — public, no auth required."""
        return self._request("GET", "/api/v1/version/", requires_api_key=False)

    # -- workspaces ----------------------------------------------------------

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """GET /api/v1/workspaces/ — every page, following ``next``."""
        path = "/api/v1/workspaces/"
        return self._get_all(path)

    # -- interviews ----------------------------------------------------------

    def start_interview(
        self,
        artifact_type: Optional[str],
        workspace_id: str,
        *,
        session_kind: str = "single",
        seed_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /api/v1/interviews/ — start a session.

        ``session_kind="multi"`` starts the type-less multi-artifact discovery
        session: it has no ``artifact_type`` (the server rejects one) and the
        LLM proposes several, possibly differently-typed, artifacts over the
        ``chat`` turns; ``proposal()`` reads that pending proposal back.
        ``session_kind="single"`` drives one typed artifact, as before.
        """
        body: Dict[str, Any] = {"workspace_id": workspace_id, "session_kind": session_kind}
        if artifact_type:
            body["artifact_type"] = artifact_type
        if seed_context:
            body["seed_context"] = seed_context
        return self._request("POST", "/api/v1/interviews/", body)

    def proposal(self, session_id: str) -> Any:
        """GET /api/v1/interviews/<id>/propose/ — the session's pending
        multi-artifact proposal.

        Returns the proposal object, or ``None`` while no chat turn has
        produced a parseable one (the normal state of a single-kind session,
        and of a multi session before its first successful chat turn). This is
        a read-out, not a generator: it never triggers an LLM call.
        """
        result = self._request("GET", f"/api/v1/interviews/{session_id}/propose/")
        if isinstance(result, dict) and "proposal" in result:
            return result["proposal"]
        return result

    def _interviews_query(self, workspace_id: str, status: Optional[str] = None) -> str:
        """Path of the interviews list endpoint; shared by list_interviews and
        stats so both address the same collection the same way."""
        qs = f"?workspace_id={workspace_id}"
        if status:
            qs += f"&status={status}"
        return f"/api/v1/interviews/{qs}"

    def list_interviews(self, workspace_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /api/v1/interviews/ — every page, filtered server-side."""
        path = self._interviews_query(workspace_id, status)
        return self._get_all(path)

    def get_state(self, session_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/interviews/{session_id}/state/")

    def answer(self, session_id: str, field: str, value: Any) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/answer/", {"field": field, "value": value})

    def chat(self, session_id: str, message: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/interviews/{session_id}/chat/", {"message": message})

    def formalize(self, session_id: str, confirmed_proposal: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """POST /api/v1/interviews/<id>/formalize/ — turn the session into real
        artifact(s).

        ``confirmed_proposal`` is required for multi-kind sessions: one item
        per artifact (``{"type", "fields", "links"}``), all created in one
        transaction. Single-kind sessions ignore it and create the one artifact
        of their ``artifact_type``.
        """
        body: Dict[str, Any] = {}
        if confirmed_proposal is not None:
            body["confirmed_proposal"] = confirmed_proposal
        return self._request("POST", f"/api/v1/interviews/{session_id}/formalize/", body)

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
            "pass one explicitly, e.g. `/reqogniloom start Requirement <workspace_id>`"
        )
    first = workspaces[0]
    workspace_id = first.get("id") if isinstance(first, dict) else None
    if not workspace_id:
        raise ReqogniLoomError(
            f"malformed workspace entry {first!r} — no 'id' field; pass a workspace_id "
            "explicitly, e.g. `/reqogniloom start Requirement <workspace_id>`"
        )
    return workspace_id
