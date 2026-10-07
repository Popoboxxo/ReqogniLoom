"""Host-runnable unit tests for the Hermes skill connector.

No Django, no network: ``urllib.request.urlopen`` is monkeypatched and the
client module is loaded directly from its file path.

Run either of::

    python -m pytest integrations/hermes-skill/reqogniloom/tests/test_reqogniloom_client.py -q
    python integrations/hermes-skill/reqogniloom/tests/test_reqogniloom_client.py

On a host whose installed pytest plugins break collection (for example an
unrelated plugin importing ``fcntl`` on Windows), set
``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` for the pytest run; the file itself needs
no plugins.
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


def _sent_frame(recorder: Any) -> dict[str, Any]:
    """Return the JSON-RPC frame of the most recent recorded request."""
    return json.loads(recorder.requests[-1].data.decode("utf-8"))


def _mcp_params(recorder: Any) -> dict[str, Any]:
    """Return ``params`` (name + arguments) of the recorded MCP request."""
    return _sent_frame(recorder)["params"]


def _ok_result(result: Any = None) -> dict[str, Any]:
    """Wrap *result* in a successful MCP ``tools/call`` response.

    The tool payload travels as the JSON string of ``content[0].text``, exactly
    as the backend emits it; the client decodes that string back to *result*.
    """
    payload = result if result is not None else {"ok": True}
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


def _run_memory(argv: list[str], payload: Any, env: dict[str, str] | None = None) -> tuple[int, Any, str, str]:
    """Run ``main(argv)`` against a recorder and return (rc, recorder, out, err)."""
    recorder = _Recorder(payload)
    out, err = io.StringIO(), io.StringIO()
    base_env = {
        "REQOGNILOOM_BASE_URL": _BASE_URL,
        "REQOGNILOOM_API_KEY": _API_KEY,
        "REQOGNILOOM_WORKSPACE_ID": "",
    }
    if env:
        base_env.update(env)
    with patch.dict(os.environ, base_env, clear=False), patch(
        "urllib.request.urlopen", recorder
    ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = client_mod.main(argv)
    return rc, recorder, out.getvalue(), err.getvalue()


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=f"{_BASE_URL}/mcp/",
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
    def test_success_uses_mcp_workspace_list(self) -> None:
        recorder = _Recorder(
            _ok_result({"workspaces": [{"id": "ws-1", "name": "W"}], "count": 1})
        )
        with patch("urllib.request.urlopen", recorder):
            result = _client().list_workspaces()
        self.assertEqual(result, {"count": 1, "workspaces": [{"id": "ws-1", "name": "W"}]})
        request = recorder.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, f"{_BASE_URL}/mcp/")
        self.assertEqual(request.get_header("X-api-key"), _API_KEY)
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(sent["params"], {"name": "workspace.list", "arguments": {}})

    def test_count_falls_back_to_list_length(self) -> None:
        recorder = _Recorder(_ok_result({"workspaces": [{"id": "ws-1"}, {"id": "ws-2"}]}))
        with patch("urllib.request.urlopen", recorder):
            result = _client().list_workspaces()
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["workspaces"]), 2)

    def test_bare_list_payload_is_normalised(self) -> None:
        recorder = _Recorder(_ok_result([{"id": "ws-1"}, {"id": "ws-2"}]))
        with patch("urllib.request.urlopen", recorder):
            result = _client().list_workspaces()
        self.assertEqual(
            result, {"count": 2, "workspaces": [{"id": "ws-1"}, {"id": "ws-2"}]}
        )

    def test_unexpected_shape_raises(self) -> None:
        recorder = _Recorder(_ok_result({"items": []}))
        with patch("urllib.request.urlopen", recorder), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("workspace.list", str(ctx.exception))

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
        recorder = _Recorder(_ok_result({"workspaces": []}))
        client = client_mod.ReqogniLoomClient(base_url=_BASE_URL, api_key="")
        with patch("urllib.request.urlopen", recorder), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client.list_workspaces()
        self.assertIn("REQOGNILOOM_API_KEY", str(ctx.exception))
        self.assertEqual(recorder.requests, [])


class McpTests(unittest.TestCase):
    def test_success_builds_tools_call_frame(self) -> None:
        recorder = _Recorder(_ok_result({"value": 42}))
        with patch("urllib.request.urlopen", recorder):
            result = client_mod.extract_mcp_result(
                _client().call_mcp("requirement.query", {"workspace_id": "ws-1"}),
                "requirement.query",
            )
        self.assertEqual(result, {"value": 42})
        request = recorder.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, f"{_BASE_URL}/mcp/")
        self.assertEqual(request.get_header("X-api-key"), _API_KEY)
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["jsonrpc"], "2.0")
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(
            sent["params"], {"name": "requirement.query", "arguments": {"workspace_id": "ws-1"}}
        )
        self.assertIn("id", sent)

    def test_content_text_is_decoded(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": '{"digest": "sum"}'}]},
        }
        self.assertEqual(client_mod.extract_mcp_result(payload), {"digest": "sum"})

    def test_missing_content_blocks_raises(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"isError": False}}
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload, "some.tool")
        self.assertIn("some.tool", str(ctx.exception))
        self.assertIn("no content blocks", str(ctx.exception))

    def test_empty_content_blocks_raises(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.extract_mcp_result(payload)

    def test_non_json_content_raises(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "not-json"}]},
        }
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload, "some.tool")
        self.assertIn("non-JSON MCP content for some.tool", str(ctx.exception))

    def test_content_block_without_text_raises(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text"}]},
        }
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload)
        self.assertIn("no text", str(ctx.exception))

    def test_non_object_result_raises(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "result": "oops"}
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.extract_mcp_result(payload)
        self.assertIn("not an object", str(ctx.exception))

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
        recorder = _Recorder(_ok_result({"workspaces": [], "count": 0}))
        out = io.StringIO()
        env = {"REQOGNILOOM_BASE_URL": _BASE_URL, "REQOGNILOOM_API_KEY": _API_KEY}
        with patch.dict(os.environ, env, clear=False), patch(
            "urllib.request.urlopen", recorder
        ), contextlib.redirect_stdout(out):
            rc = client_mod.main(["list-workspaces"])
        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["count"], 0)
        self.assertEqual(printed["workspaces"], [])

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
            rc = client_mod.main(["mcp", "--tool", "requirement.query", "--params", "{not json"])
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
            rc = client_mod.main(["mcp", "--tool", "requirement.query"])
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


class MemoryQueryTests(unittest.TestCase):
    def test_success_builds_memory_query_arguments(self) -> None:
        rc, recorder, out, err = _run_memory(
            [
                "memory-query",
                "--query",
                "reviewer",
                "--scope",
                "workspace",
                "--workspace-id",
                "ws-1",
                "--artifact-id",
                "art-1",
                "--top-k",
                "7",
            ],
            _ok_result({"entries": [], "query": "reviewer"}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        params = _mcp_params(recorder)
        self.assertEqual(params["name"], "memory.query")
        self.assertEqual(
            params["arguments"],
            {
                "query": "reviewer",
                "scope": "workspace",
                "workspace_id": "ws-1",
                "artifact_id": "art-1",
                "top_k": 7,
            },
        )
        self.assertEqual(json.loads(out)["query"], "reviewer")
        self.assertEqual(recorder.requests[-1].full_url, f"{_BASE_URL}/mcp/")

    def test_scopes_comma_separated_and_repeatable(self) -> None:
        rc, recorder, _out, err = _run_memory(
            [
                "memory-query",
                "--query",
                "q",
                "--workspace-id",
                "ws-1",
                "--scopes",
                "workspace,user",
                "--scopes",
                "artifact",
                "--artifact-id",
                "art-1",
            ],
            _ok_result({"entries": []}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        arguments = _mcp_params(recorder)["arguments"]
        self.assertEqual(arguments["scopes"], ["workspace", "user", "artifact"])
        self.assertNotIn("scope", arguments)
        # effective set contains workspace/artifact -> both ids are required.
        self.assertEqual(arguments["workspace_id"], "ws-1")
        self.assertEqual(arguments["artifact_id"], "art-1")

    def test_scope_workspace_requires_workspace(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-query", "--query", "q", "--scope", "workspace"],
            _ok_result({"entries": []}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("no workspace id", err)
        self.assertNotIn("Traceback", err)

    def test_scope_artifact_requires_artifact(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-query", "--query", "q", "--scope", "artifact"],
            _ok_result({"entries": []}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("requires --artifact-id", err)
        self.assertNotIn("Traceback", err)

    def test_scopes_workspace_injects_workspace(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-query", "--query", "q", "--scopes", "workspace"],
            _ok_result({"entries": []}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        arguments = _mcp_params(recorder)["arguments"]
        self.assertEqual(arguments["scopes"], ["workspace"])
        self.assertEqual(arguments["workspace_id"], "env-ws")

    def test_scopes_wins_over_scope_for_injection(self) -> None:
        # --scope user alone omits workspace, but --scopes workspace wins, so
        # the effective set drives injection and the contradictory scope key
        # is not sent.
        rc, recorder, _out, err = _run_memory(
            [
                "memory-query",
                "--query",
                "q",
                "--scope",
                "user",
                "--scopes",
                "workspace",
            ],
            _ok_result({"entries": []}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        arguments = _mcp_params(recorder)["arguments"]
        self.assertEqual(arguments["scopes"], ["workspace"])
        self.assertNotIn("scope", arguments)
        self.assertEqual(arguments["workspace_id"], "env-ws")

    def test_scope_user_omits_workspace_and_artifact(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-query", "--query", "q", "--scope", "user"],
            _ok_result({"entries": []}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        arguments = _mcp_params(recorder)["arguments"]
        self.assertEqual(arguments, {"query": "q", "scope": "user"})

    def test_env_workspace_is_used_when_no_flag(self) -> None:
        rc, recorder, _out, _err = _run_memory(
            ["memory-query", "--query", "q"],
            _ok_result({"entries": []}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_mcp_params(recorder)["arguments"]["workspace_id"], "env-ws")

    def test_missing_api_key_sends_no_request(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-query", "--query", "q"],
            _ok_result({"entries": []}),
            env={"REQOGNILOOM_API_KEY": ""},
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("REQOGNILOOM_API_KEY", err)
        self.assertNotIn("Traceback", err)

    def test_tool_execution_error_returns_one(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Error: memory blew up"}],
                "isError": True,
            },
        }
        rc, _recorder, _out, err = _run_memory(["memory-query", "--query", "q"], payload)
        self.assertEqual(rc, 1)
        self.assertIn("memory blew up", err)
        self.assertNotIn("Traceback", err)

    def test_jsonrpc_error_at_http_200_returns_one(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "API key is required."},
        }
        rc, _recorder, _out, err = _run_memory(["memory-query", "--query", "q"], payload)
        self.assertEqual(rc, 1)
        self.assertIn("-32000: API key is required.", err)
        self.assertNotIn("Traceback", err)

    def test_http_error_returns_one_without_traceback(self) -> None:
        error = _http_error(
            403, '{"error": {"code": "permission_denied", "message": "Forbidden."}}'
        )
        err = io.StringIO()
        env = {
            "REQOGNILOOM_BASE_URL": _BASE_URL,
            "REQOGNILOOM_API_KEY": _API_KEY,
            "REQOGNILOOM_WORKSPACE_ID": "",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "urllib.request.urlopen", side_effect=error
        ), contextlib.redirect_stderr(err):
            rc = client_mod.main(["memory-query", "--query", "q"])
        self.assertEqual(rc, 1)
        self.assertIn("HTTP 403: permission_denied: Forbidden.", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class MemoryDigestTests(unittest.TestCase):
    def test_success_uses_env_workspace(self) -> None:
        rc, recorder, out, err = _run_memory(
            ["memory-digest"],
            _ok_result({"digest": "sum"}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        params = _mcp_params(recorder)
        self.assertEqual(params["name"], "memory.digest")
        self.assertEqual(params["arguments"], {"workspace_id": "env-ws"})
        self.assertEqual(json.loads(out)["digest"], "sum")

    def test_success_global_flag_and_artifact(self) -> None:
        rc, recorder, _out, _err = _run_memory(
            ["--workspace-id", "top-ws", "memory-digest", "--artifact-id", "art-1"],
            _ok_result({"digest": "sum"}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            _mcp_params(recorder)["arguments"],
            {"workspace_id": "top-ws", "artifact_id": "art-1"},
        )

    def test_missing_workspace_errors_without_request(self) -> None:
        rc, recorder, _out, err = _run_memory(["memory-digest"], _ok_result({"digest": "x"}))
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("no workspace id", err)
        self.assertIn("REQOGNILOOM_WORKSPACE_ID", err)
        self.assertNotIn("Traceback", err)

    def test_tool_execution_error_returns_one(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "Error: nope"}], "isError": True},
        }
        rc, _recorder, _out, err = _run_memory(
            ["memory-digest", "--workspace-id", "ws-1"], payload
        )
        self.assertEqual(rc, 1)
        self.assertIn("nope", err)


class MemoryAskTests(unittest.TestCase):
    def test_success_with_reasoning_level(self) -> None:
        rc, recorder, out, err = _run_memory(
            [
                "memory-ask",
                "--query",
                "why?",
                "--workspace-id",
                "ws-1",
                "--reasoning-level",
                "high",
            ],
            _ok_result({"answer": "because"}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        params = _mcp_params(recorder)
        self.assertEqual(params["name"], "memory.ask")
        self.assertEqual(
            params["arguments"],
            {"query": "why?", "workspace_id": "ws-1", "reasoning_level": "high"},
        )
        self.assertEqual(json.loads(out)["answer"], "because")

    def test_missing_workspace_errors_without_request(self) -> None:
        rc, recorder, _out, err = _run_memory(["memory-ask", "--query", "why?"], _ok_result({}))
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("no workspace id", err)

    def test_tool_execution_error_returns_one(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "Error: degraded"}], "isError": True},
        }
        rc, _recorder, _out, err = _run_memory(
            ["memory-ask", "--query", "why?", "--workspace-id", "ws-1"], payload
        )
        self.assertEqual(rc, 1)
        self.assertIn("degraded", err)


class MemoryWriteTests(unittest.TestCase):
    def test_scope_workspace_injects_workspace(self) -> None:
        rc, recorder, out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "workspace", "--workspace-id", "ws-1"],
            _ok_result({"entry_id": "e-1", "scope": "workspace"}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        params = _mcp_params(recorder)
        self.assertEqual(params["name"], "memory.write")
        self.assertEqual(
            params["arguments"],
            {"content": "fact", "scope": "workspace", "workspace_id": "ws-1"},
        )
        self.assertEqual(json.loads(out)["entry_id"], "e-1")

    def test_scope_user_omits_workspace_even_with_env(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "user"],
            _ok_result({"entry_id": "e-1", "scope": "user"}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            _mcp_params(recorder)["arguments"], {"content": "fact", "scope": "user"}
        )

    def test_scope_artifact_uses_artifact_only(self) -> None:
        rc, recorder, _out, _err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "artifact", "--artifact-id", "art-1"],
            _ok_result({"entry_id": "e-1", "scope": "artifact"}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            _mcp_params(recorder)["arguments"],
            {"content": "fact", "scope": "artifact", "artifact_id": "art-1"},
        )

    def test_scope_workspace_rejects_artifact_id(self) -> None:
        rc, recorder, _out, err = _run_memory(
            [
                "memory-write",
                "--content",
                "fact",
                "--scope",
                "workspace",
                "--workspace-id",
                "ws-1",
                "--artifact-id",
                "art-1",
            ],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("cannot be combined with --artifact-id", err)
        self.assertNotIn("Traceback", err)

    def test_scope_artifact_rejects_explicit_workspace_id(self) -> None:
        rc, recorder, _out, err = _run_memory(
            [
                "memory-write",
                "--content",
                "fact",
                "--scope",
                "artifact",
                "--workspace-id",
                "ws-1",
                "--artifact-id",
                "art-1",
            ],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("cannot be combined with --workspace-id", err)
        self.assertNotIn("Traceback", err)

    def test_scope_artifact_ignores_implicit_env_workspace(self) -> None:
        # The env default is not user input, so it must not trigger the
        # incompatible-combination error.
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "artifact", "--artifact-id", "art-1"],
            _ok_result({"entry_id": "e-1"}),
            env={"REQOGNILOOM_WORKSPACE_ID": "env-ws"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            _mcp_params(recorder)["arguments"],
            {"content": "fact", "scope": "artifact", "artifact_id": "art-1"},
        )

    def test_scope_user_rejects_explicit_workspace_id(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "user", "--workspace-id", "ws-1"],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("scope=user cannot be combined", err)
        self.assertNotIn("Traceback", err)

    def test_scope_user_rejects_explicit_artifact_id(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "user", "--artifact-id", "art-1"],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("scope=user cannot be combined", err)
        self.assertNotIn("Traceback", err)

    def test_scope_artifact_without_artifact_errors_without_request(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "artifact"],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("requires --artifact-id", err)
        self.assertNotIn("Traceback", err)

    def test_confidence_and_change_reason_are_forwarded(self) -> None:
        rc, recorder, _out, _err = _run_memory(
            [
                "memory-write",
                "--content",
                "fact",
                "--scope",
                "user",
                "--confidence",
                "0.5",
                "--change-reason",
                "manual",
            ],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            _mcp_params(recorder)["arguments"],
            {"content": "fact", "scope": "user", "confidence": 0.5, "change_reason": "manual"},
        )

    def test_scope_workspace_without_workspace_errors(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "workspace"],
            _ok_result({"entry_id": "e-1"}),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("no workspace id", err)

    def test_missing_api_key_sends_no_request(self) -> None:
        rc, recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "user"],
            _ok_result({"entry_id": "e-1"}),
            env={"REQOGNILOOM_API_KEY": ""},
        )
        self.assertEqual(rc, 1)
        self.assertEqual(recorder.requests, [])
        self.assertIn("REQOGNILOOM_API_KEY", err)

    def test_tool_execution_error_returns_one(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Error: VALIDATION_ERROR"}],
                "isError": True,
            },
        }
        rc, _recorder, _out, err = _run_memory(
            ["memory-write", "--content", "fact", "--scope", "user"], payload
        )
        self.assertEqual(rc, 1)
        self.assertIn("VALIDATION_ERROR", err)


if __name__ == "__main__":
    unittest.main()
