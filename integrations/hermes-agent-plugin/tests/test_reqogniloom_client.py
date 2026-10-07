"""Unit tests for reqogniloom_client.py.

The client is MCP-first: every operation except ``version()`` is a JSON-RPC
2.0 ``tools/call`` to ``POST /mcp/`` carrying ``X-API-Key``; ``version()`` is
the single REST call and must never send the key. These tests pin that
contract, the exact tool names (against the published tool manifest), the
content-block decoding and both server error shapes.

Run: python -m pytest tests/test_reqogniloom_client.py -q
"""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from typing import Self

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


client_mod = _load("reqogniloom_client_under_test", _PLUGIN_ROOT / "reqogniloom_client.py")

_API_KEY = "reqlo_test_key"
_BASE_URL = "http://api.test"


class _FakeResponse:
    """Stand-in for the response object ``urlopen`` returns."""

    def __init__(self, body: bytes = b"", read_error: BaseException | None = None) -> None:
        self._body = body
        self._read_error = read_error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body


def _mcp_success(data: Any) -> bytes:
    """A successful ``tools/call`` frame: one content text block, JSON-encoded."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]},
        }
    ).encode("utf-8")


def _mcp_is_error(message: str) -> bytes:
    """An MCP tool-execution error: HTTP 200 with ``result.isError``."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": f"Error: {message}"}],
                "isError": True,
            },
        }
    ).encode("utf-8")


def _jsonrpc_error(code: Any, message: str) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": message}}
    ).encode("utf-8")


def _http_error(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=f"{_BASE_URL}/mcp/",
        code=status,
        msg="boom",
        hdrs=email.message.Message(),
        fp=io.BytesIO(body),
    )


class _McpRouter:
    """Fake ``urlopen``: serves the version path and dispatches MCP tools.

    ``tool_results`` maps a tool name to the decoded data a successful call
    returns. ``errors`` maps a tool name to an exception raised instead.
    """

    def __init__(
        self,
        tool_results: dict[str, Any] | None = None,
        errors: dict[str, BaseException] | None = None,
        version: Any = None,
    ) -> None:
        self.tool_results = tool_results or {}
        self.errors = errors or {}
        self.version = version if version is not None else {"app_version": "1.8.0"}
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float | None] = []
        self.tools_called: list[str] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResponse:
        self.requests.append(req)
        self.timeouts.append(timeout)
        parts = urllib.parse.urlsplit(req.full_url)
        if parts.path == client_mod.VERSION_PATH:
            return _FakeResponse(json.dumps(self.version).encode("utf-8"))
        frame = json.loads(req.data.decode("utf-8"))
        tool = frame["params"]["name"]
        self.tools_called.append(tool)
        if tool in self.errors:
            error = self.errors[tool]
            if isinstance(error, urllib.error.HTTPError):
                raise error
            raise error
        if tool not in self.tool_results:
            raise AssertionError(f"unexpected MCP tool: {tool}")
        return _FakeResponse(_mcp_success(self.tool_results[tool]))


def _client(**kwargs: Any) -> Any:
    kwargs.setdefault("api_key", _API_KEY)
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL, **kwargs)


def _keyless_client() -> Any:
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL)


def _call_body(router: _McpRouter, index: int = 0) -> dict[str, Any]:
    return json.loads(router.requests[index].data.decode("utf-8"))


class _NoApiKeyEnv:
    """Clears REQOGNILOOM_API_KEY for the duration of a test."""

    def __enter__(self) -> None:
        self._backup = os.environ.pop("REQOGNILOOM_API_KEY", None)

    def __exit__(self, *exc_info: object) -> None:
        if self._backup is not None:
            os.environ["REQOGNILOOM_API_KEY"] = self._backup


class _BaseUrlEnv:
    """Sets ``REQOGNILOOM_BASE_URL`` for a test; passing ``None`` unsets it."""

    def __init__(self, value: str | None) -> None:
        self._value = value

    def __enter__(self) -> None:
        self._backup = os.environ.pop("REQOGNILOOM_BASE_URL", None)
        if self._value is not None:
            os.environ["REQOGNILOOM_BASE_URL"] = self._value

    def __exit__(self, *exc_info: object) -> None:
        if self._backup is None:
            os.environ.pop("REQOGNILOOM_BASE_URL", None)
        else:
            os.environ["REQOGNILOOM_BASE_URL"] = self._backup


class ConfigResolutionTests(unittest.TestCase):
    def test_defaults_when_env_unset(self) -> None:
        env_backup = {k: os.environ.pop(k, None) for k in ("REQOGNILOOM_BASE_URL", "REQOGNILOOM_API_KEY")}
        try:
            client = client_mod.ReqogniLoomClient()
            self.assertEqual(client.base_url, "http://localhost:8001")
            self.assertEqual(client.api_key, "")
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value

    def test_explicit_args_override_env(self) -> None:
        client = client_mod.ReqogniLoomClient(base_url="http://example.test/", api_key="reqlo_abc")
        self.assertEqual(client.base_url, "http://example.test")
        self.assertEqual(client.api_key, "reqlo_abc")

    def test_empty_base_url_env_is_rejected(self) -> None:
        with _BaseUrlEnv(""), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.ReqogniLoomClient()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("''", message)

    def test_non_http_base_url_env_is_rejected(self) -> None:
        with _BaseUrlEnv("ftp://example.test"), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.ReqogniLoomClient()
        self.assertIn("ftp://example.test", str(ctx.exception))

    def test_explicit_non_http_base_url_is_rejected(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.ReqogniLoomClient(base_url="localhost:8001")
        self.assertIn("localhost:8001", str(ctx.exception))

    def test_remote_cleartext_base_url_logs_a_warning(self) -> None:
        with self.assertLogs("reqogniloom_client_under_test", level="WARNING") as captured:
            client_mod.ReqogniLoomClient(base_url="http://reqogniloom.example.com")
        self.assertTrue(any("unencrypted" in line for line in captured.output))

    def test_loopback_cleartext_base_url_does_not_warn(self) -> None:
        with (
            self.assertRaises(AssertionError),
            self.assertLogs("reqogniloom_client_under_test", level="WARNING"),
        ):
            client_mod.ReqogniLoomClient(base_url="http://localhost:8001")

    def test_https_remote_base_url_does_not_warn(self) -> None:
        with (
            self.assertRaises(AssertionError),
            self.assertLogs("reqogniloom_client_under_test", level="WARNING"),
        ):
            client_mod.ReqogniLoomClient(base_url="https://reqogniloom.example.com")


class McpEnvelopeTests(unittest.TestCase):
    """The JSON-RPC 2.0 „tools/call" envelope and its HTTP shape."""

    def test_request_targets_mcp_with_api_key_header(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_workspaces()
        request = router.requests[0]
        self.assertEqual(urllib.parse.urlsplit(request.full_url).path, client_mod.MCP_PATH)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-api-key"), _API_KEY)
        self.assertIsNone(request.get_header("Authorization"))

    def test_frame_is_jsonrpc_tools_call(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_workspaces()
        frame = _call_body(router)
        self.assertEqual(frame["jsonrpc"], "2.0")
        self.assertEqual(frame["id"], 1)
        self.assertEqual(frame["method"], "tools/call")
        self.assertEqual(frame["params"]["name"], "workspace.list")
        self.assertEqual(frame["params"]["arguments"], {})

    def test_timeout_comes_from_module_constant(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_workspaces()
        self.assertEqual(router.timeouts, [client_mod.REQUEST_TIMEOUT_SECONDS])

    def test_content_text_block_is_json_decoded(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [{"id": "ws-1"}], "count": 1}})
        with patch("urllib.request.urlopen", router):
            self.assertEqual(_client().list_workspaces(), [{"id": "ws-1"}])

    def test_non_json_content_block_raises(self) -> None:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "<html>"}]}}
        ).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_FakeResponse(body)), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("non-JSON MCP content", str(ctx.exception))


class DecodeContentTests(unittest.TestCase):
    """``_decode_content`` must fail loudly on every malformed result shape."""

    def test_missing_content_raises(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod._decode_content({}, "my.tool")
        self.assertIn("no content blocks", str(ctx.exception))

    def test_empty_content_raises(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod._decode_content({"content": []}, "my.tool")
        self.assertIn("no content blocks", str(ctx.exception))

    def test_block_without_text_raises(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod._decode_content({"content": [{"type": "text"}]}, "my.tool")
        self.assertIn("no text", str(ctx.exception))

    def test_non_json_text_raises(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod._decode_content({"content": [{"type": "text", "text": "<html>"}]}, "my.tool")
        self.assertIn("non-JSON MCP content", str(ctx.exception))


class ToolNameTests(unittest.TestCase):
    """Every public method must call exactly the documented tool name."""

    def test_workspaces_uses_workspace_list(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_workspaces()
        self.assertEqual(router.tools_called, ["workspace.list"])

    def test_start_interview_uses_interview_start(self) -> None:
        router = _McpRouter({"interview.start": {"id": "s1", "phase": "collecting"}})
        with patch("urllib.request.urlopen", router):
            _client().start_interview("Requirement", "ws-1")
        self.assertEqual(router.tools_called, ["interview.start"])
        arguments = _call_body(router)["params"]["arguments"]
        self.assertEqual(arguments["workspace_id"], "ws-1")
        self.assertEqual(arguments["session_kind"], "single")
        self.assertEqual(arguments["artifact_type"], "Requirement")

    def test_multi_start_omits_artifact_type(self) -> None:
        router = _McpRouter({"interview.start": {"session_id": "s1"}})
        with patch("urllib.request.urlopen", router):
            _client().start_interview(None, "ws-1", session_kind="multi")
        arguments = _call_body(router)["params"]["arguments"]
        self.assertNotIn("artifact_type", arguments)
        self.assertEqual(arguments["session_kind"], "multi")

    def test_proposal_uses_interview_propose(self) -> None:
        router = _McpRouter({"interview.propose": {"proposal": None}})
        with patch("urllib.request.urlopen", router):
            _client().proposal("s1")
        self.assertEqual(router.tools_called, ["interview.propose"])

    def test_list_interviews_uses_interview_list_and_passes_status(self) -> None:
        router = _McpRouter({"interview.list": {"sessions": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_interviews("ws-1", status="in_progress")
        self.assertEqual(router.tools_called, ["interview.list"])
        arguments = _call_body(router)["params"]["arguments"]
        self.assertEqual(arguments, {"workspace_id": "ws-1", "status": "in_progress"})

    def test_get_state_uses_interview_get_state(self) -> None:
        router = _McpRouter({"interview.get_state": {"session_id": "s1"}})
        with patch("urllib.request.urlopen", router):
            _client().get_state("s1")
        self.assertEqual(router.tools_called, ["interview.get_state"])

    def test_answer_uses_interview_answer(self) -> None:
        router = _McpRouter({"interview.answer": {"session_id": "s1"}})
        with patch("urllib.request.urlopen", router):
            _client().answer("s1", "title", "My Requirement")
        self.assertEqual(router.tools_called, ["interview.answer"])
        arguments = _call_body(router)["params"]["arguments"]
        self.assertEqual(arguments, {"session_id": "s1", "field": "title", "value": "My Requirement"})

    def test_chat_uses_interview_chat(self) -> None:
        router = _McpRouter({"interview.chat": {"reply": "hi", "state": {"session_id": "s1"}}})
        with patch("urllib.request.urlopen", router):
            _client().chat("s1", "hello")
        self.assertEqual(router.tools_called, ["interview.chat"])
        self.assertEqual(_call_body(router)["params"]["arguments"], {"session_id": "s1", "message": "hello"})

    def test_formalize_uses_interview_formalize(self) -> None:
        router = _McpRouter({"interview.formalize": {"resulting_artifact_ids": ["a-1"], "status": "completed"}})
        with patch("urllib.request.urlopen", router):
            _client().formalize("s1", confirmed_proposal=[{"type": "Requirement", "fields": {}}])
        self.assertEqual(router.tools_called, ["interview.formalize"])
        arguments = _call_body(router)["params"]["arguments"]
        self.assertEqual(arguments["session_id"], "s1")
        self.assertEqual(arguments["confirmed_proposal"][0]["type"], "Requirement")

    def test_formalize_single_omits_confirmed_proposal(self) -> None:
        router = _McpRouter({"interview.formalize": {"resulting_artifact_ids": [], "status": "completed"}})
        with patch("urllib.request.urlopen", router):
            _client().formalize("s1")
        self.assertNotIn("confirmed_proposal", _call_body(router)["params"]["arguments"])

    def test_abandon_uses_interview_abandon(self) -> None:
        router = _McpRouter({"interview.abandon": {"status": "abandoned"}})
        with patch("urllib.request.urlopen", router):
            _client().abandon("s1")
        self.assertEqual(router.tools_called, ["interview.abandon"])
        self.assertEqual(_call_body(router)["params"]["arguments"], {"session_id": "s1"})


class StateNormalisationTests(unittest.TestCase):
    """MCP's ``session_id``/``grounding_snapshot`` -> the ``id``/``grounding``
    names the plugin's formatting and the capture worker read."""

    def test_get_state_adds_id_and_grounding(self) -> None:
        router = _McpRouter(
            {"interview.get_state": {"session_id": "s1", "grounding_snapshot": {"candidates": []}}}
        )
        with patch("urllib.request.urlopen", router):
            state = _client().get_state("s1")
        self.assertEqual(state["id"], "s1")
        self.assertEqual(state["grounding"], {"candidates": []})
        self.assertEqual(state["session_id"], "s1")

    def test_start_multi_session_state_gets_an_id(self) -> None:
        router = _McpRouter({"interview.start": {"session_id": "s1", "grounding_snapshot": None}})
        with patch("urllib.request.urlopen", router):
            session = _client().start_interview(None, "ws-1", session_kind="multi")
        self.assertEqual(session["id"], "s1")
        self.assertIn("grounding", session)

    def test_chat_normalises_the_nested_state(self) -> None:
        router = _McpRouter(
            {
                "interview.chat": {
                    "reply": "ok",
                    "state": {"session_id": "s1", "grounding_snapshot": {"x": 1}},
                }
            }
        )
        with patch("urllib.request.urlopen", router):
            result = _client().chat("s1", "hi")
        self.assertEqual(result["reply"], "ok")
        self.assertEqual(result["state"]["id"], "s1")
        self.assertEqual(result["state"]["grounding"], {"x": 1})

    def test_proposal_unwraps_and_passes_through_none(self) -> None:
        router = _McpRouter({"interview.propose": {"proposal": None}})
        with patch("urllib.request.urlopen", router):
            self.assertIsNone(_client().proposal("s1"))

    def test_proposal_returns_the_list(self) -> None:
        proposal = [{"type": "Requirement", "fields": {"title": "x"}}]
        router = _McpRouter({"interview.propose": {"proposal": proposal}})
        with patch("urllib.request.urlopen", router):
            self.assertEqual(_client().proposal("s1"), proposal)

    def test_list_interviews_returns_the_session_list(self) -> None:
        router = _McpRouter({"interview.list": {"sessions": [{"id": "s1"}], "count": 1}})
        with patch("urllib.request.urlopen", router):
            self.assertEqual(_client().list_interviews("ws-1"), [{"id": "s1"}])

    def test_missing_list_key_raises_instead_of_returning_empty(self) -> None:
        router = _McpRouter({"workspace.list": {"detail": "nope"}})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().list_workspaces()
        self.assertIn("unexpected list response", str(ctx.exception))


class ErrorShapeTests(unittest.TestCase):
    def test_http_401_is_auth_error(self) -> None:
        error = _http_error(401, _jsonrpc_error(-32000, "Authentication failed."))
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod._AuthError) as ctx:
            _client().list_workspaces()
        self.assertIn("-32000", str(ctx.exception))
        self.assertIn("Authentication failed.", str(ctx.exception))

    def test_http_403_is_auth_error(self) -> None:
        error = _http_error(403, _jsonrpc_error(-32001, "Insufficient permissions."))
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod._AuthError):
            _client().list_workspaces()

    def test_auth_error_is_a_reqogniloom_error(self) -> None:
        self.assertTrue(issubclass(client_mod._AuthError, client_mod.ReqogniLoomError))

    def test_non_auth_protocol_error_is_reqogniloom_error(self) -> None:
        error = _http_error(400, _jsonrpc_error(-32602, "Invalid params"))
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().list_workspaces()
        self.assertNotIsInstance(ctx.exception, client_mod._AuthError)
        self.assertIn("-32602", str(ctx.exception))

    def test_http_500_without_body_reports_status(self) -> None:
        error = _http_error(500, b"")
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().list_workspaces()
        self.assertIn("500", str(ctx.exception))

    def test_200_with_top_level_auth_error_frame_is_auth_error(self) -> None:
        body = _jsonrpc_error(-32000, "Authentication failed.")
        router = _McpRouter()
        router_call = router

        def responder(_req, timeout=None):
            router_call.requests.append(_req)
            return _FakeResponse(body)

        with patch("urllib.request.urlopen", responder), self.assertRaises(client_mod._AuthError):
            _client().list_workspaces()

    def test_200_with_top_level_non_auth_error_frame_is_reqogniloom_error(self) -> None:
        body = _jsonrpc_error(-32603, "Internal error")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(body)), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertNotIsInstance(ctx.exception, client_mod._AuthError)

    def test_string_permission_denied_code_is_auth_error(self) -> None:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": "PERMISSION_DENIED", "message": "denied"}}
        ).encode("utf-8")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(body)), self.assertRaises(
            client_mod._AuthError
        ):
            _client().list_workspaces()

    def test_permission_error_is_a_subclass_of_auth_error(self) -> None:
        self.assertTrue(issubclass(client_mod._PermissionError, client_mod._AuthError))
        self.assertTrue(issubclass(client_mod._PermissionError, client_mod.ReqogniLoomError))

    def test_http_403_is_permission_error(self) -> None:
        error = _http_error(403, _jsonrpc_error(-32001, "Insufficient permissions."))
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._PermissionError
        ):
            _client().list_workspaces()

    def test_http_403_without_body_is_permission_error(self) -> None:
        error = _http_error(403, b"")
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._PermissionError
        ):
            _client().list_workspaces()

    def test_nested_error_code_string_permission_denied_is_permission_error(self) -> None:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"error_code": "PERMISSION_DENIED", "message": "denied"}}
        ).encode("utf-8")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(body)), self.assertRaises(
            client_mod._PermissionError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

    def test_nested_error_code_string_auth_failed_is_not_permission_error(self) -> None:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"error_code": "AUTH_FAILED", "message": "auth"}}
        ).encode("utf-8")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(body)), self.assertRaises(
            client_mod._AuthError
        ) as ctx:
            _client().list_workspaces()
        self.assertNotIsInstance(ctx.exception, client_mod._PermissionError)

    def test_http_error_body_is_truncated_in_message(self) -> None:
        big_body = b"<html>" + (b"x" * 5000) + b"</html>"
        error = _http_error(500, big_body)
        router = _McpRouter(errors={"workspace.list": error})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        message = str(ctx.exception)
        self.assertIn("HTTP 500", message)
        self.assertLessEqual(len(message), len("HTTP 500: ") + 200)

    def test_tool_execution_iserror_is_reqogniloom_error_with_stripped_message(self) -> None:
        body = _mcp_is_error("formalize exploded")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(body)), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().formalize("s1")
        self.assertEqual(str(ctx.exception), "formalize exploded")


class TransportFailureTests(unittest.TestCase):
    def test_unreachable_host_reports_reason_and_default_hint(self) -> None:
        error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with _BaseUrlEnv(None), patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client_mod.ReqogniLoomClient(api_key=_API_KEY).list_workspaces()
        message = str(ctx.exception)
        self.assertIn("could not reach", message)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("default", message)

    def test_read_timeout_becomes_reqogniloom_error(self) -> None:
        response = _FakeResponse(read_error=TimeoutError("timed out"))
        with patch("urllib.request.urlopen", return_value=response), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("timed out", str(ctx.exception))

    def test_configured_target_failure_has_no_default_hint(self) -> None:
        error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertNotIn("REQOGNILOOM_BASE_URL", str(ctx.exception))


class ApiKeyTests(unittest.TestCase):
    def test_missing_key_fails_before_any_request_is_sent(self) -> None:
        router = _McpRouter({"workspace.list": {"workspaces": [], "count": 0}})
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._AuthError
        ) as ctx:
            _keyless_client().list_workspaces()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_API_KEY", message)
        self.assertIn("reqlo_", message)
        self.assertEqual(router.requests, [])

    def test_missing_key_does_not_degrade_stats_to_nulls(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [], "count": 0},
                "test.query": {"test_cases": [], "count": 0},
                "interview.list": {"sessions": [], "count": 0},
            }
        )
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._AuthError
        ):
            _keyless_client().stats("ws-1")
        self.assertEqual(router.requests, [])

    def test_version_works_without_a_key_and_sends_no_credential(self) -> None:
        router = _McpRouter(version={"app_version": "1.8.0"})
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", router):
            self.assertEqual(_keyless_client().version(), {"app_version": "1.8.0"})
        request = router.requests[0]
        self.assertEqual(urllib.parse.urlsplit(request.full_url).path, client_mod.VERSION_PATH)
        self.assertIsNone(request.get_header("X-api-key"))
        self.assertIsNone(request.get_header("Authorization"))

    def test_version_never_sends_the_key_even_when_configured(self) -> None:
        router = _McpRouter(version={"app_version": "1.8.0"})
        with patch("urllib.request.urlopen", router):
            _client().version()
        request = router.requests[0]
        self.assertIsNone(request.get_header("X-api-key"))
        self.assertIsNone(request.get_header("Authorization"))


class StatsTests(unittest.TestCase):
    def test_counts_come_from_the_tool_payload_count(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [{"id": "r"}] * 500, "count": 500},
                "test.query": {"test_cases": [{"id": "t"}] * 120, "count": 120},
                "interview.list": {"sessions": [{"id": "s"}] * 7, "count": 7},
            }
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 500)
        self.assertEqual(stats["testcases"], 120)
        self.assertEqual(stats["open_interviews"], 7)
        self.assertIn("interview.list", router.tools_called)
        interview_args = next(
            _call_body(router, i)["params"]["arguments"]
            for i in range(len(router.requests))
            if _call_body(router, i)["params"]["name"] == "interview.list"
        )
        self.assertEqual(interview_args, {"workspace_id": "ws-1", "status": "in_progress"})

    def test_count_falls_back_to_list_length_when_count_absent(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [{"id": "r-1"}, {"id": "r-2"}]},
                "test.query": {"test_cases": []},
                "interview.list": {"sessions": [{"id": "s-1"}]},
            }
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 2)
        self.assertEqual(stats["testcases"], 0)
        self.assertEqual(stats["open_interviews"], 1)

    def test_payload_without_count_or_list_yields_none(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": {"detail": "odd"},
                "test.query": {"count": 3},
                "interview.list": {"sessions": []},
            }
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertIsNone(stats["requirements"])
        self.assertEqual(stats["testcases"], 3)

    def test_one_incidental_failure_degrades_only_that_number(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [], "count": 3},
                "interview.list": {"sessions": [], "count": 2},
            },
            errors={"test.query": _http_error(500, b"")},
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 3)
        self.assertIsNone(stats["testcases"])
        self.assertEqual(stats["open_interviews"], 2)
        self.assertEqual(stats["workspace_id"], "ws-1")

    def test_rejected_key_propagates_from_stats(self) -> None:
        denied = _http_error(401, _jsonrpc_error(-32000, "Authentication failed."))
        router = _McpRouter(
            {"requirement.query": {"requirements": [], "count": 0}},
            errors={"test.query": denied, "interview.list": denied},
        )
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod._AuthError):
            _client().stats("ws-1")

    def test_permission_denied_on_one_count_degrades_only_that_count(self) -> None:
        denied = _http_error(403, _jsonrpc_error(-32001, "Insufficient permissions."))
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [], "count": 3},
                "interview.list": {"sessions": [], "count": 2},
            },
            errors={"test.query": denied},
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 3)
        self.assertIsNone(stats["testcases"])
        self.assertEqual(stats["open_interviews"], 2)

    def test_permission_denied_on_open_interviews_degrades_only_that_count(self) -> None:
        denied = _http_error(403, _jsonrpc_error(-32001, "Insufficient permissions."))
        router = _McpRouter(
            {
                "requirement.query": {"requirements": [], "count": 3},
                "test.query": {"test_cases": [], "count": 1},
            },
            errors={"interview.list": denied},
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 3)
        self.assertEqual(stats["testcases"], 1)
        self.assertIsNone(stats["open_interviews"])

    def test_auth_401_still_raises_from_stats_even_alongside_a_403(self) -> None:
        router = _McpRouter(
            {"interview.list": {"sessions": [], "count": 2}},
            errors={
                "requirement.query": _http_error(403, _jsonrpc_error(-32001, "denied")),
                "test.query": _http_error(401, _jsonrpc_error(-32000, "Authentication failed.")),
            },
        )
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._AuthError
        ) as ctx:
            _client().stats("ws-1")
        self.assertNotIsInstance(ctx.exception, client_mod._PermissionError)

    def test_bare_list_payload_is_counted_by_length(self) -> None:
        router = _McpRouter(
            {
                "requirement.query": [{"id": "r-1"}, {"id": "r-2"}],
                "test.query": [{"id": "t-1"}],
                "interview.list": [{"id": "s-1"}],
            }
        )
        with patch("urllib.request.urlopen", router):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 2)
        self.assertEqual(stats["testcases"], 1)
        self.assertEqual(stats["open_interviews"], 1)


class ManifestGuardTests(unittest.TestCase):
    """Every tool name the client uses must exist in the published manifest.

    A phantom name would only surface at runtime as UNKNOWN_TOOL; this pins it
    at test time instead.
    """

    def test_every_mcp_tool_exists_in_the_manifest(self) -> None:
        manifest_path = _REPO_ROOT / "docs" / "agent-templates" / "tool-manifest.json"
        self.assertTrue(manifest_path.exists(), f"manifest not found at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = {tool["name"] for tool in manifest["tools"]}
        missing = sorted(set(client_mod.MCP_TOOLS.values()) - names)
        self.assertEqual(missing, [], f"client uses tools absent from the manifest: {missing}")

    def test_tool_table_is_not_empty_and_namespaced(self) -> None:
        self.assertTrue(client_mod.MCP_TOOLS)
        for tool in client_mod.MCP_TOOLS.values():
            self.assertIn(".", tool)


class ResolveWorkspaceIdTests(unittest.TestCase):
    def test_explicit_valid_uuid_is_returned_verbatim(self) -> None:
        client = MagicMock()
        workspace_uuid = "33333333-3333-3333-3333-333333333333"
        result = client_mod.resolve_workspace_id(client, workspace_uuid)
        self.assertEqual(result, workspace_uuid)
        client.list_workspaces.assert_not_called()

    def test_explicit_invalid_uuid_raises(self) -> None:
        client = MagicMock()
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, "not-a-uuid")

    def test_falls_back_to_first_visible_workspace(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = [{"id": "ws-1"}, {"id": "ws-2"}]
        self.assertEqual(client_mod.resolve_workspace_id(client, None), "ws-1")

    def test_raises_when_no_workspaces_visible(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = []
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, None)

    def test_workspace_entry_without_id_raises(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = [{"name": "Demo"}]
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.resolve_workspace_id(client, None)
        self.assertIn("malformed", str(ctx.exception).lower())

    def test_non_dict_workspace_entry_raises(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = ["ws-1"]
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, None)


if __name__ == "__main__":
    unittest.main()
