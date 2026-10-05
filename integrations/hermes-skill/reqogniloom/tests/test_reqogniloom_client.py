"""Host-runnable unit tests for the Hermes skill connector.

No Django, no network: ``urllib.request.urlopen`` is monkeypatched and the
client module is loaded directly from its file path.

Run either of::

    python -m pytest integrations/hermes-skill/reqogniloom/tests/test_reqogniloom_client.py -q
    python integrations/hermes-skill/reqogniloom/tests/test_reqogniloom_client.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import patch

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

_API_KEY = "reqlo_test_key"
_BASE_URL = "http://api.test"


def _load_client_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "reqogniloom_skill_client_under_test", _SCRIPTS_DIR / "reqogniloom_client.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client_mod = _load_client_module()


class _FakeResponse:
    """Stand-in for the object ``urlopen`` returns as a context manager."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        return self._body


class _Recorder:
    """Answers every request with *payload* and records request details."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResponse:
        self.requests.append(req)
        body = json.dumps(self.payload).encode("utf-8")
        return _FakeResponse(body)


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=f"{_BASE_URL}/api/v1/workspaces/",
        code=code,
        msg="boom",
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


def _client() -> Any:
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL, api_key=_API_KEY)


class NormalizeErrorTests(unittest.TestCase):
    def test_nested_shape(self) -> None:
        payload = {"error": {"code": "invalid_api_key", "message": "Invalid API key."}}
        self.assertEqual(client_mod.normalize_error(payload), "invalid_api_key: Invalid API key.")

    def test_nested_jsonrpc_numeric_code(self) -> None:
        payload = {"error": {"code": -32000, "message": "API key is required."}}
        self.assertEqual(client_mod.normalize_error(payload), "-32000: API key is required.")

    def test_flat_shape(self) -> None:
        payload = {"error": "invalid_api_key", "message": "Invalid API key."}
        self.assertEqual(client_mod.normalize_error(payload), "invalid_api_key: Invalid API key.")

    def test_non_error_payload_yields_none(self) -> None:
        self.assertIsNone(client_mod.normalize_error({"results": []}))
        self.assertIsNone(client_mod.normalize_error("not a dict"))


class ListWorkspacesTests(unittest.TestCase):
    def test_success_uses_get_and_x_api_key(self) -> None:
        recorder = _Recorder({"count": 1, "results": [{"id": "ws-1"}]})
        with patch("urllib.request.urlopen", recorder):
            result = _client().list_workspaces()
        self.assertEqual(result["results"][0]["id"], "ws-1")
        request = recorder.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.full_url, f"{_BASE_URL}/api/v1/workspaces/")
        self.assertEqual(request.get_header("X-api-key"), _API_KEY)

    def test_nested_error_shape_on_http_error_is_normalised(self) -> None:
        error = _http_error(
            401, '{"error": {"code": "invalid_api_key", "message": "Invalid API key."}}'
        )
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertEqual(str(ctx.exception), "HTTP 401: invalid_api_key: Invalid API key.")

    def test_flat_error_shape_at_http_200_is_raised(self) -> None:
        recorder = _Recorder({"error": "invalid_api_key", "message": "Invalid API key."})
        with patch("urllib.request.urlopen", recorder), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertEqual(str(ctx.exception), "invalid_api_key: Invalid API key.")

    def test_missing_api_key_raises_before_sending(self) -> None:
        recorder = _Recorder({"results": []})
        client = client_mod.ReqogniLoomClient(base_url=_BASE_URL, api_key="")
        with patch("urllib.request.urlopen", recorder), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client.list_workspaces()
        self.assertIn("REQOGNILOOM_API_KEY", str(ctx.exception))
        self.assertEqual(recorder.requests, [])


class McpTests(unittest.TestCase):
    def test_success_builds_tools_call_frame(self) -> None:
        recorder = _Recorder(
            {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "42"}]}}
        )
        with patch("urllib.request.urlopen", recorder):
            result = client_mod.extract_mcp_result(
                _client().call_mcp("requirement_query", {"workspace_id": "ws-1"})
            )
        self.assertEqual(result, {"content": [{"type": "text", "text": "42"}]})
        request = recorder.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, f"{_BASE_URL}/mcp/")
        self.assertEqual(request.get_header("X-api-key"), _API_KEY)
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["jsonrpc"], "2.0")
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(
            sent["params"], {"name": "requirement_query", "arguments": {"workspace_id": "ws-1"}}
        )
        self.assertIn("id", sent)

    def test_jsonrpc_nested_error_at_http_200_is_raised(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "API key is required."},
        }
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload)
        self.assertEqual(str(ctx.exception), "-32000: API key is required.")

    def test_flat_error_shape_at_http_200_is_raised(self) -> None:
        payload = {"error": "invalid_api_key", "message": "Invalid API key."}
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload)
        self.assertEqual(str(ctx.exception), "invalid_api_key: Invalid API key.")

    def test_tool_execution_error_result_is_raised(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Error: tool blew up"}],
                "isError": True,
            },
        }
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload)
        self.assertEqual(str(ctx.exception), "tool blew up")


class CommandLineTests(unittest.TestCase):
    def test_success_prints_result_and_returns_zero(self) -> None:
        recorder = _Recorder({"count": 0, "results": []})
        out = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": _API_KEY}
        with patch.dict(os.environ, env, clear=False), patch(
            "urllib.request.urlopen", recorder
        ), contextlib.redirect_stdout(out):
            rc = client_mod.main(["list-workspaces"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["count"], 0)

    def test_missing_api_key_returns_one_without_traceback(self) -> None:
        err = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stderr(err):
            rc = client_mod.main(["list-workspaces"])
        self.assertEqual(rc, 1)
        self.assertIn("REQOGNILOOM_API_KEY", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_malformed_params_returns_one_without_traceback(self) -> None:
        err = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": _API_KEY}
        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stderr(err):
            rc = client_mod.main(["mcp", "--tool", "requirement_query", "--params", "{not json"])
        self.assertEqual(rc, 1)
        self.assertIn("--params is not valid JSON", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_mcp_tool_error_at_http_200_returns_one_without_traceback(self) -> None:
        recorder = _Recorder(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": "Error: tool blew up"}],
                    "isError": True,
                },
            }
        )
        err = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": _API_KEY}
        with patch.dict(os.environ, env, clear=False), patch(
            "urllib.request.urlopen", recorder
        ), contextlib.redirect_stderr(err):
            rc = client_mod.main(["mcp", "--tool", "requirement_query"])
        self.assertEqual(rc, 1)
        self.assertIn("tool blew up", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_http_error_401_returns_one_without_traceback(self) -> None:
        error = _http_error(
            401, '{"error": {"code": "invalid_api_key", "message": "Invalid API key."}}'
        )
        err = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": _API_KEY}
        with patch.dict(os.environ, env, clear=False), patch(
            "urllib.request.urlopen", side_effect=error
        ), contextlib.redirect_stderr(err):
            rc = client_mod.main(["list-workspaces"])
        self.assertEqual(rc, 1)
        self.assertIn("HTTP 401: invalid_api_key: Invalid API key.", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
