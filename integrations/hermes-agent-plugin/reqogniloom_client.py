"""Thin client for ReqogniLoom used by both the slash-command handler
(``__init__.py``) and the dashboard backend (``dashboard/plugin_api.py``).

Transport split:

* **MCP** (``POST {base_url}/mcp/``, JSON-RPC 2.0 ``tools/call``, ``X-API-Key``)
  carries every operation. ReqogniLoom's MCP server is the single tool surface
  the rest of the ecosystem speaks, so the plugin speaks it too instead of
  maintaining a second, partial REST client that drifts.
* **REST** is kept for exactly one endpoint, ``GET /api/v1/version/``: it is
  public and has no MCP tool, so there is nothing to route through MCP.

The MCP server rejects a ``Bearer`` JWT with ``bearer_not_supported``; the key
must travel as the ``X-API-Key`` header. Tool results arrive as MCP content
blocks (``result.content[0].text`` holding a JSON string) and are decoded here,
so callers keep receiving plain Python objects. Tool-execution failures arrive
as HTTP 200 with ``result.isError == true``; protocol/auth failures arrive as
JSON-RPC error frames with a non-2xx status.

POC scope: no retries, no connection pooling, stdlib ``urllib`` only so the
plugin has zero extra dependencies beyond what Hermes itself ships.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

logger = logging.getLogger(__name__)

#: Per-request socket timeout. This bounds each socket operation, not the
#: whole response: a slow-drip backend can still exceed it in total.
REQUEST_TIMEOUT_SECONDS = 10

#: Used when neither the ``base_url`` argument nor ``REQOGNILOOM_BASE_URL``
#: configures a target. Kept as the documented local-dev default; the failure
#: path makes it loud rather than letting a request hit it silently.
_DEFAULT_BASE_URL = "http://localhost:8001"

#: JSON-RPC transport path for the native MCP server (also served at
#: ``/api/v1/mcp/``, but ``/mcp/`` is the canonical alias).
MCP_PATH = "/mcp/"

#: The one endpoint that stays on REST: public and without an MCP tool.
VERSION_PATH = "/api/v1/version/"

#: HTTP 401 (credential absent/invalid) vs. 403 (valid credential, missing
#: scope). The distinction matters only for degradation: a 403 on one count
#: tool must not sink the whole dashboard, while a 401 means no usable key.
_AUTH_STATUS_CODE = 401
_PERMISSION_STATUS_CODE = 403

#: Hostnames for which cleartext ``http://`` is not a credential-leak risk.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

#: Canonical name of every MCP tool this client calls. Kept as one table so a
#: rename on the server is a one-line change here, and so tests can assert
#: that no phantom tool name is used (a name absent from the published tool
#: manifest would be an UNKNOWN_TOOL at runtime, not a compile error).
MCP_TOOLS: dict[str, str] = {
    "workspaces": "workspace.list",
    "interview_start": "interview.start",
    "interview_propose": "interview.propose",
    "interview_list": "interview.list",
    "interview_state": "interview.get_state",
    "interview_answer": "interview.answer",
    "interview_chat": "interview.chat",
    "interview_formalize": "interview.formalize",
    "interview_abandon": "interview.abandon",
    "requirements": "requirement.query",
    "testcases": "test.query",
}

#: JSON-RPC server-defined codes emitted by the backend's ErrorFormatter
#: (``protocol_handler.ERROR_CODE_MAP``). ``"code"`` in an error object is the
#: numeric form; the string names are accepted too for defensive symmetry with
#: other surfaces that emit them.
_JSONRPC_AUTH_CODES = frozenset({-32000, -32001})  # AUTH_FAILED, PERMISSION_DENIED
_AUTH_ERROR_NAMES = frozenset({"AUTH_FAILED", "PERMISSION_DENIED"})
_JSONRPC_PERMISSION_CODES = frozenset({-32001})  # PERMISSION_DENIED
_PERMISSION_ERROR_NAMES = frozenset({"PERMISSION_DENIED"})


class ReqogniLoomError(RuntimeError):
    """Raised for any server-reported error or transport failure."""


class _AuthError(ReqogniLoomError):
    """API key missing or rejected. A configuration problem, not a data
    problem: callers that degrade failures to ``None`` must re-raise this,
    because a null payload reads as "nothing there" rather than "no key".

    :class:`_PermissionError` is the one subclass a degrading caller may
    swallow: a valid key that merely lacks scope on a single operation is a
    data-level miss, not a configuration failure.
    """


class _PermissionError(_AuthError):
    """The credential is valid but not permitted (HTTP 403 / JSON-RPC
    ``PERMISSION_DENIED``). Degradable: unlike a 401 it must not abort a
    best-effort aggregate such as :meth:`ReqogniLoomClient.stats`."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _validate_base_url(value: str) -> None:
    """Reject a base URL that cannot address a ReqogniLoom instance.

    An empty or non-http(s) value is a configuration mistake: failing here
    names the variable and the offending value at construction, instead of
    surfacing later as a puzzling transport error against a malformed URL.
    """
    if value and value.startswith(("http://", "https://")):
        _warn_if_cleartext_remote(value)
        return
    raise ReqogniLoomError(
        f"invalid REQOGNILOOM_BASE_URL {value!r}: expected an http:// or https:// URL, "
        f"e.g. REQOGNILOOM_BASE_URL=http://localhost:8001"
    )


def _warn_if_cleartext_remote(value: str) -> None:
    """Warn (never raise) when a remote target is addressed over cleartext.

    ``http://`` to a loopback host is normal in development. To any other host
    it means the ``X-API-Key`` travels in the clear; that is a real exposure but
    a deliberate deployment choice, so this only logs. The default base URL and
    every other validation decision are left untouched.
    """
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
    except ValueError:  # malformed authority (e.g. bad IPv6 literal)
        return
    if parts.scheme != "http" or host in _LOOPBACK_HOSTS:
        return
    logger.warning(
        "REQOGNILOOM_BASE_URL %r uses cleartext http:// for non-loopback host %r; "
        "the API key will travel unencrypted — use https:// in production",
        value,
        host,
    )


def _join_error(code: Any, message: Any) -> str:
    """Join an error code and message into one readable line."""
    code_text = "" if code is None else str(code).strip()
    message_text = "" if message is None else str(message).strip()
    if code_text and message_text:
        return f"{code_text}: {message_text}"
    return code_text or message_text or "unknown server error"


def _error_object(payload: Any) -> dict[str, Any] | None:
    """Return the ``error`` object of a JSON-RPC/REST error body, else ``None``."""
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    return error if isinstance(error, dict) else None


def normalize_error(payload: Any) -> str | None:
    """Normalise either server error shape to ``code: message``, else ``None``.

    * nested: ``{"error": {"code": ..., "message": ...}}`` (JSON-RPC error
      frames carry a numeric ``code``; some legacy surfaces a string one)
    * flat:   ``{"error": "invalid_api_key", "message": ...}``
    """
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if code is None:
            # Some surfaces emit only the string name under ``error_code``.
            code = error.get("error_code")
        message = error.get("message")
        if code is None and not message:
            return None
        return _join_error(code, message)
    if isinstance(error, str) and error:
        return _join_error(error, payload.get("message"))
    return None


def raise_for_error(payload: Any) -> None:
    """Raise :class:`ReqogniLoomError` when *payload* carries an error."""
    normalized = normalize_error(payload)
    if normalized is not None:
        raise ReqogniLoomError(normalized)


def _is_auth_code(code: Any) -> bool:
    """Whether a JSON-RPC error code means "missing/rejected credential"."""
    if isinstance(code, bool):  # bool is an int subclass; never a JSON-RPC code
        return False
    if isinstance(code, int) and code in _JSONRPC_AUTH_CODES:
        return True
    return isinstance(code, str) and code.upper() in _AUTH_ERROR_NAMES


def _is_permission_code(code: Any) -> bool:
    """Whether a JSON-RPC error code means "credential valid, scope missing".

    A subset of :func:`_is_auth_code`; callers classify permission first so
    ``PERMISSION_DENIED`` lands in the degradable :class:`_PermissionError`
    rather than the non-degradable :class:`_AuthError`.
    """
    if isinstance(code, bool):
        return False
    if isinstance(code, int) and code in _JSONRPC_PERMISSION_CODES:
        return True
    return isinstance(code, str) and code.upper() in _PERMISSION_ERROR_NAMES


def _error_code_candidates(error: dict[str, Any]) -> tuple[Any, ...]:
    """Both code shapes an error object may carry: numeric ``code`` and the
    string ``error_code`` alias some surfaces emit."""
    return (error.get("code"), error.get("error_code"))


def _raise_for_error_payload(payload: Any, *, http_status: int | None = None) -> None:
    """Raise the correct error subclass for a decoded error body.

    Permission is decided first (HTTP 403 or ``PERMISSION_DENIED``), then auth
    (HTTP 401 or ``AUTH_FAILED``) — read from both the HTTP status and the
    JSON-RPC code, so transport-level and protocol-level rejections classify
    alike. Both raise :class:`_AuthError`; only the 403/``PERMISSION_DENIED``
    case is the degradable :class:`_PermissionError` subclass.
    """
    error = _error_object(payload)
    codes = _error_code_candidates(error) if error is not None else (None,)
    if http_status == _PERMISSION_STATUS_CODE or any(_is_permission_code(c) for c in codes):
        raise _PermissionError(normalize_error(payload) or "permission denied")
    if http_status == _AUTH_STATUS_CODE or any(_is_auth_code(c) for c in codes):
        raise _AuthError(normalize_error(payload) or "authentication failed")
    raise_for_error(payload)


def _mcp_error_text(result: dict[str, Any]) -> str:
    """Extract the human-readable text from an MCP ``isError`` result."""
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text = block["text"].strip()
                if text.startswith("Error:"):
                    text = text[len("Error:"):].strip()
                return text or "tool reported an error"
    return "tool reported an error"


def _decode_content(result: dict[str, Any], tool: str) -> Any:
    """Decode the JSON payload of a successful MCP ``tools/call`` result.

    The backend emits only ``content`` text blocks (no ``structuredContent``),
    so the data has to be parsed out of the first block's ``text``.
    """
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise ReqogniLoomError(
            f"unexpected MCP result for {tool}: no content blocks"
        )
    block = content[0]
    text = block.get("text") if isinstance(block, dict) else None
    if not isinstance(text, str):
        raise ReqogniLoomError(
            f"unexpected MCP result for {tool}: first content block has no text"
        )
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReqogniLoomError(
            f"non-JSON MCP content for {tool}: {text[:200]!r}"
        ) from exc


def _list_from(payload: Any, key: str) -> list[dict[str, Any]]:
    """Normalise a list-tool payload to a plain list.

    A dict without the expected list key is a shape or auth failure, not an
    empty collection — returning ``[]`` for it would report "nothing to see"
    for a problem the user has to fix.
    """
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return payload[key]
    if isinstance(payload, list):
        return payload
    raise ReqogniLoomError(
        f"unexpected list response: expected an object with a '{key}' list or a "
        f"JSON array, got {type(payload).__name__}"
    )


def _payload_count(payload: Any, key: str) -> int | None:
    """Total number of items behind a tool payload, or ``None``.

    The MCP list tools carry an explicit ``count``; falling back to the list
    length keeps a payload that omits it usable. Anything else is "no count",
    never a silently wrong one.
    """
    if isinstance(payload, dict) and isinstance(payload.get("count"), int):
        return payload["count"]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return len(payload[key])
    if isinstance(payload, list):
        return len(payload)
    return None


def _normalise_state(state: Any) -> dict[str, Any]:
    """Align an MCP interview-state dict with the names callers read.

    MCP uses ``session_id``/``grounding_snapshot``; the plugin's formatting and
    the capture worker read ``id``/``grounding``. Both original keys are kept,
    so nothing that already reads them breaks.
    """
    if not isinstance(state, dict):
        return state
    normalised = dict(state)
    if "id" not in normalised and isinstance(normalised.get("session_id"), str):
        normalised["id"] = normalised["session_id"]
    if "grounding" not in normalised and "grounding_snapshot" in normalised:
        normalised["grounding"] = normalised["grounding_snapshot"]
    return normalised


class ReqogniLoomClient:
    """Config resolved from environment variables:

    - ``REQOGNILOOM_BASE_URL`` (default ``http://localhost:8001``)
    - ``REQOGNILOOM_API_KEY``  (``reqlo_...`` — sent as the ``X-API-Key`` header)

    An unset ``REQOGNILOOM_BASE_URL`` still falls back to the local default, but
    a transport failure then says so explicitly: a silent miss against
    ``localhost`` is the hardest misconfiguration to spot from the terse
    ``URLError`` alone.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
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
        body: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        requires_api_key: bool = False,
    ) -> Any:
        """Perform one HTTP call and return the decoded JSON payload.

        Only ``ReqogniLoomError`` (or a subclass) ever leaves this method — no
        bare ``OSError``/``TimeoutError``/``AttributeError`` may reach the
        slash command, whose ``except ReqogniLoomError`` is its whole error
        contract. The API key is sent only when the caller passes one, so the
        one public endpoint (``version``) can never leak the credential and a
        missing key fails before any socket is opened.
        """
        # ``path`` is normally an app-relative path, but a paginated ``next``
        # link is an absolute URL built by DRF from the request host — accept
        # both so a caller can pass either through.
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
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
            payload: Any = None
            if body_text:
                try:
                    payload = json.loads(body_text)
                except (json.JSONDecodeError, ValueError):
                    payload = None
            if isinstance(payload, dict) and "error" in payload:
                _raise_for_error_payload(payload, http_status=exc.code)
            # No structured error body: fall back to the status and raw text.
            # Bound the snippet: a proxy HTML error page can be many KB, and a
            # multi-KB exception string helps nobody.
            snippet = body_text.strip()[:200] or exc.reason
            message = f"HTTP {exc.code}: {snippet}"
            if exc.code == _PERMISSION_STATUS_CODE:
                raise _PermissionError(message) from exc
            if exc.code == _AUTH_STATUS_CODE:
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
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReqogniLoomError(f"non-JSON response from {url}: {raw[:200]!r}") from exc
        # A 2xx can still carry an error frame (e.g. an auth failure rendered
        # by an intermediate proxy); classify it the same way as a non-2xx.
        if isinstance(payload, dict) and "error" in payload:
            _raise_for_error_payload(payload)
        return payload

    def _mcp_call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call one MCP tool and return its decoded JSON result.

        Raises:
            _AuthError: no key configured, or the server rejected the key.
            ReqogniLoomError: transport failure, protocol error frame, or an
                MCP tool-execution error (``result.isError``).
        """
        frame = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        }
        payload = self._request(
            "POST", MCP_PATH, frame, api_key=self.api_key, requires_api_key=True
        )
        if not isinstance(payload, dict):
            raise ReqogniLoomError(f"unexpected MCP response for {tool}: not a JSON object")
        if "result" not in payload:
            # A frame without a result and without a handled error is malformed.
            raise ReqogniLoomError(f"unexpected MCP response for {tool}: no 'result' field")
        result = payload["result"]
        if isinstance(result, dict) and result.get("isError") is True:
            raise ReqogniLoomError(_mcp_error_text(result))
        if not isinstance(result, dict):
            raise ReqogniLoomError(f"unexpected MCP result for {tool}: not an object")
        return _decode_content(result, tool)

    def _rest_get(self, path: str) -> Any:
        """Unauthenticated GET (used only for the public version endpoint)."""
        return self._request("GET", path, api_key=None, requires_api_key=False)

    # -- unauthenticated ---------------------------------------------------

    def version(self) -> dict[str, Any]:
        """GET /api/v1/version/ — public, no auth required, key never sent."""
        return self._rest_get(VERSION_PATH)

    # -- workspaces ----------------------------------------------------------

    def list_workspaces(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        """MCP ``workspace.list`` — workspaces visible to this API key."""
        arguments: dict[str, Any] = {}
        if include_inactive:
            arguments["include_inactive"] = True
        payload = self._mcp_call(MCP_TOOLS["workspaces"], arguments)
        return _list_from(payload, "workspaces")

    # -- interviews ----------------------------------------------------------

    def start_interview(
        self,
        artifact_type: str | None,
        workspace_id: str,
        *,
        session_kind: str = "single",
        seed_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """MCP ``interview.start`` — start a session.

        ``session_kind="multi"`` starts the type-less multi-artifact discovery
        session: it has no ``artifact_type`` (the server rejects one) and the
        LLM proposes several, possibly differently-typed, artifacts over the
        ``chat`` turns; ``proposal()`` reads that pending proposal back.
        ``session_kind="single"`` drives one typed artifact, as before.

        The result is normalised so it always carries an ``id`` even though a
        multi session's MCP state is keyed ``session_id``.
        """
        arguments: dict[str, Any] = {"workspace_id": workspace_id, "session_kind": session_kind}
        if artifact_type:
            arguments["artifact_type"] = artifact_type
        if seed_context:
            arguments["seed_context"] = seed_context
        return _normalise_state(self._mcp_call(MCP_TOOLS["interview_start"], arguments))

    def proposal(self, session_id: str) -> Any:
        """MCP ``interview.propose`` — the session's pending multi-artifact
        proposal.

        Returns the proposal object, or ``None`` while no chat turn has
        produced a parseable one (the normal state of a single-kind session,
        and of a multi session before its first successful chat turn). This is
        a read-out, not a generator: it never triggers an LLM call.
        """
        result = self._mcp_call(MCP_TOOLS["interview_propose"], {"session_id": session_id})
        if isinstance(result, dict) and "proposal" in result:
            return result["proposal"]
        return result

    def list_interviews(self, workspace_id: str, status: str | None = None) -> list[dict[str, Any]]:
        """MCP ``interview.list`` — sessions of one workspace, filtered server-side."""
        arguments: dict[str, Any] = {"workspace_id": workspace_id}
        if status:
            arguments["status"] = status
        payload = self._mcp_call(MCP_TOOLS["interview_list"], arguments)
        return _list_from(payload, "sessions")

    def get_state(self, session_id: str) -> dict[str, Any]:
        return _normalise_state(
            self._mcp_call(MCP_TOOLS["interview_state"], {"session_id": session_id})
        )

    def answer(self, session_id: str, field: str, value: Any) -> dict[str, Any]:
        return _normalise_state(
            self._mcp_call(
                MCP_TOOLS["interview_answer"],
                {"session_id": session_id, "field": field, "value": value},
            )
        )

    def chat(self, session_id: str, message: str) -> dict[str, Any]:
        result = self._mcp_call(
            MCP_TOOLS["interview_chat"], {"session_id": session_id, "message": message}
        )
        if isinstance(result, dict) and isinstance(result.get("state"), dict):
            normalised = dict(result)
            normalised["state"] = _normalise_state(result["state"])
            return normalised
        return result

    def formalize(self, session_id: str, confirmed_proposal: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """MCP ``interview.formalize`` — turn the session into real artifact(s).

        ``confirmed_proposal`` is required for multi-kind sessions: one item
        per artifact (``{"type", "fields", "links"}``), all created in one
        transaction. Single-kind sessions ignore it and create the one artifact
        of their ``artifact_type``.
        """
        arguments: dict[str, Any] = {"session_id": session_id}
        if confirmed_proposal is not None:
            arguments["confirmed_proposal"] = confirmed_proposal
        return self._mcp_call(MCP_TOOLS["interview_formalize"], arguments)

    def abandon(self, session_id: str) -> dict[str, Any]:
        return self._mcp_call(MCP_TOOLS["interview_abandon"], {"session_id": session_id})

    # -- stats (dashboard POC) -----------------------------------------------

    def stats(self, workspace_id: str) -> dict[str, Any]:
        """A handful of cheap counts for the dashboard tab. Best-effort: a
        failing sub-call degrades that one number to ``None`` rather than
        failing the whole payload. A missing or rejected API key (401 /
        ``AUTH_FAILED``) is not degradation and always propagates; a valid key
        that merely lacks scope on one count tool (403 / ``PERMISSION_DENIED``)
        degrades only that number.

        Counts come from each MCP list tool's ``count`` field (falling back to
        the list length when it is absent) — never from a page size.
        """

        def _count(tool: str, key: str) -> int | None:
            try:
                payload = self._mcp_call(tool, {"workspace_id": workspace_id})
            except _PermissionError:
                return None
            except _AuthError:
                raise
            except ReqogniLoomError:
                return None
            return _payload_count(payload, key)

        try:
            interviews = self._mcp_call(
                MCP_TOOLS["interview_list"], {"workspace_id": workspace_id, "status": "in_progress"}
            )
        except _PermissionError:
            open_interviews = None
        except _AuthError:
            raise
        except ReqogniLoomError:
            open_interviews = None
        else:
            open_interviews = _payload_count(interviews, "sessions")

        return {
            "workspace_id": workspace_id,
            "requirements": _count(MCP_TOOLS["requirements"], "requirements"),
            "testcases": _count(MCP_TOOLS["testcases"], "test_cases"),
            "open_interviews": open_interviews,
        }


def resolve_workspace_id(client: ReqogniLoomClient, explicit: str | None = None) -> str:
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
