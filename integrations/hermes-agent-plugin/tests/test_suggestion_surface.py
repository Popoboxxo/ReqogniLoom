"""Tests for the proposal surface wired into the plugin (#1156).

The capture half (``_capture.py``, ``tests/test_listen_mode.py``) is untouched.
This file covers the *new* connection between that existing capture and the
server-side proposal/review path:

* the reused client methods for the ADR-019 surface — ``suggestion.list`` /
  ``suggestion.accept`` / ``suggestion.reject`` and ``review.list_pending`` —
  their exact tool names, arguments and error mapping;
* ``/reqogniloom review pending`` (the server-side queue listing);
* ``/reqogniloom accept`` creating captured artifacts **as proposals, never as
  adopted final requirements**, and the toggle/accept/dismiss paths never
  silently adopting anything.

Run: python -m unittest tests/test_suggestion_surface.py -v
"""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from _loader import load_plugin

plugin = load_plugin()

_PLUGIN_ROOT = Path(plugin.__file__).resolve().parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


client_mod = _load(
    "reqogniloom_client_suggestion_under_test", _PLUGIN_ROOT / "reqogniloom_client.py"
)

#: The client module *as the plugin imported it* — the slash command's
#: ``except ReqogniLoomError`` only matches that module's error classes, not the
#: separately loaded ``client_mod`` above.
plugin_client_mod = importlib.import_module(plugin.__name__ + ".reqogniloom_client")

_API_KEY = "reqlo_test_key"
_BASE_URL = "http://api.test"
_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


class _FakeResponse:
    def __init__(self, body: bytes = b"") -> None:
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        return self._body


def _mcp_success(data: Any) -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(data)}]},
        }
    ).encode("utf-8")


def _http_error(status: int, code: Any, message: str) -> urllib.error.HTTPError:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": message}}
    ).encode("utf-8")
    return urllib.error.HTTPError(
        url=f"{_BASE_URL}/mcp/",
        code=status,
        msg="boom",
        hdrs=email.message.Message(),
        fp=io.BytesIO(body),
    )


class _McpRouter:
    """Fake ``urlopen`` dispatching MCP tools and recording the calls."""

    def __init__(
        self,
        tool_results: dict[str, Any] | None = None,
        errors: dict[str, BaseException] | None = None,
    ) -> None:
        self.tool_results = tool_results or {}
        self.errors = errors or {}
        self.requests: list[urllib.request.Request] = []
        self.tools_called: list[str] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResponse:
        self.requests.append(req)
        frame = json.loads(req.data.decode("utf-8"))
        tool = frame["params"]["name"]
        self.tools_called.append(tool)
        if tool in self.errors:
            raise self.errors[tool]
        if tool not in self.tool_results:
            raise AssertionError(f"unexpected MCP tool: {tool}")
        return _FakeResponse(_mcp_success(self.tool_results[tool]))


def _client(**kwargs: Any) -> Any:
    kwargs.setdefault("api_key", _API_KEY)
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL, **kwargs)


def _args(router: _McpRouter, index: int = 0) -> dict[str, Any]:
    return json.loads(router.requests[index].data.decode("utf-8"))["params"]["arguments"]


class SuggestionClientTests(unittest.TestCase):
    """The new MCP client methods: tool names, arguments, result shapes."""

    def test_list_suggestions_uses_suggestion_list(self) -> None:
        router = _McpRouter({"suggestion.list": {"suggestions": [{"id": "sug-1"}], "count": 1}})
        with patch("urllib.request.urlopen", router):
            result = _client().list_suggestions(_WORKSPACE_ID)
        self.assertEqual(router.tools_called, ["suggestion.list"])
        self.assertEqual(_args(router), {"workspace_id": _WORKSPACE_ID})
        self.assertEqual(result, [{"id": "sug-1"}])

    def test_accept_suggestion_uses_suggestion_accept(self) -> None:
        router = _McpRouter({"suggestion.accept": {"id": "sug-1", "status": "accepted"}})
        with patch("urllib.request.urlopen", router):
            result = _client().accept_suggestion("sug-1")
        self.assertEqual(router.tools_called, ["suggestion.accept"])
        self.assertEqual(_args(router), {"id": "sug-1"})
        self.assertEqual(result["status"], "accepted")

    def test_reject_suggestion_uses_suggestion_reject_with_reason(self) -> None:
        router = _McpRouter({"suggestion.reject": {"id": "sug-1", "status": "rejected"}})
        with patch("urllib.request.urlopen", router):
            _client().reject_suggestion("sug-1", reason="not relevant")
        self.assertEqual(router.tools_called, ["suggestion.reject"])
        self.assertEqual(_args(router), {"id": "sug-1", "reason": "not relevant"})

    def test_reject_suggestion_omits_empty_reason(self) -> None:
        router = _McpRouter({"suggestion.reject": {"id": "sug-1", "status": "rejected"}})
        with patch("urllib.request.urlopen", router):
            _client().reject_suggestion("sug-1")
        self.assertEqual(_args(router), {"id": "sug-1"})

    def test_list_pending_reviews_uses_review_list_pending(self) -> None:
        router = _McpRouter(
            {"review.list_pending": {"items": [{"item_id": "a-1", "item_type": "Requirement"}], "count": 1}}
        )
        with patch("urllib.request.urlopen", router):
            result = _client().list_pending_reviews(_WORKSPACE_ID)
        self.assertEqual(router.tools_called, ["review.list_pending"])
        self.assertEqual(_args(router), {"workspace_id": _WORKSPACE_ID})
        self.assertEqual(result[0]["item_id"], "a-1")

    def test_list_pending_reviews_passes_item_type_filter(self) -> None:
        router = _McpRouter({"review.list_pending": {"items": [], "count": 0}})
        with patch("urllib.request.urlopen", router):
            _client().list_pending_reviews(_WORKSPACE_ID, item_type="Requirement")
        self.assertEqual(
            _args(router), {"workspace_id": _WORKSPACE_ID, "item_type": "Requirement"}
        )

    def test_permission_denied_maps_to_permission_error(self) -> None:
        denied = _http_error(403, -32001, "Insufficient permissions.")
        router = _McpRouter(errors={"suggestion.accept": denied})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod._PermissionError
        ):
            _client().accept_suggestion("sug-1")

    def test_auth_failure_maps_to_auth_error(self) -> None:
        denied = _http_error(401, -32000, "Authentication failed.")
        router = _McpRouter(errors={"review.list_pending": denied})
        with patch("urllib.request.urlopen", router), self.assertRaises(client_mod._AuthError):
            _client().list_pending_reviews(_WORKSPACE_ID)

    def test_missing_suggestions_list_key_raises(self) -> None:
        router = _McpRouter({"suggestion.list": {"detail": "odd"}})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_suggestions(_WORKSPACE_ID)
        self.assertIn("unexpected list response", str(ctx.exception))

    def test_missing_review_items_key_raises(self) -> None:
        router = _McpRouter({"review.list_pending": {"count": 0}})
        with patch("urllib.request.urlopen", router), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_pending_reviews(_WORKSPACE_ID)
        self.assertIn("'items'", str(ctx.exception))

    def test_new_tool_names_exist_in_the_manifest(self) -> None:
        manifest_path = _REPO_ROOT / "docs" / "agent-templates" / "tool-manifest.json"
        self.assertTrue(manifest_path.exists(), f"manifest not found at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = {tool["name"] for tool in manifest["tools"]}
        new_tools = {
            "suggestion.list",
            "suggestion.accept",
            "suggestion.reject",
            "review.list_pending",
        }
        missing = sorted(new_tools - names)
        self.assertEqual(missing, [], f"client uses tools absent from the manifest: {missing}")
        self.assertEqual(new_tools - set(client_mod.MCP_TOOLS.values()), set())


def _suggestion(signature: str = "sig-1", session_id: str = "sess-1", items=None) -> dict:
    return {
        "id": signature,
        "signature": signature,
        "session_id": session_id,
        "source": "listen",
        "created_at": "2026-10-06T23:40:11+0000",
        "items": items
        if items is not None
        else [{"type": "Requirement", "fields": {"title": "Token gate must be opt-in"}}],
    }


class AcceptCreatesProposalsTests(unittest.TestCase):
    """``accept`` creates artifacts as proposals; nothing is silently adopted."""

    def _run(self, command: str, state: dict, client: Any | None = None):
        client = client or MagicMock()
        if client.formalize.return_value is None or isinstance(
            client.formalize.return_value, MagicMock
        ):
            client.formalize.return_value = {
                "resulting_artifact_ids": ["art-1"],
                "status": "proposed",
            }
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state)
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_accept_surfaces_proposed_and_awaiting_review(self) -> None:
        result, _, client = self._run("accept 0", {"suggestions": [_suggestion()]})
        client.formalize.assert_called_once()
        # The reused M1 path: formalize under agent context, not a silent accept.
        client.accept_suggestion.assert_not_called()
        self.assertIn("art-1", result)
        self.assertIn("proposals", result)
        self.assertIn("adopted as final", result)
        self.assertIn("review pending", result)

    def test_accept_passes_the_confirmed_proposal_through_formalize(self) -> None:
        _, _, client = self._run("accept 0", {"suggestions": [_suggestion()]})
        session_id = client.formalize.call_args.args[0]
        kwargs = client.formalize.call_args.kwargs
        self.assertEqual(session_id, "sess-1")
        self.assertEqual(kwargs["confirmed_proposal"][0]["type"], "Requirement")

    def test_accept_failure_keeps_the_suggestion_and_creates_nothing(self) -> None:
        client = MagicMock()
        client.formalize.side_effect = plugin.ReqogniLoomError("boom")
        result, save_mock, _ = self._run("accept all", {"suggestions": [_suggestion()]}, client)
        self.assertIn("Failed, still pending", result)
        self.assertNotIn("Created as proposals", result)
        self.assertEqual(len(save_mock.call_args.args[0]["suggestions"]), 1)

    def test_dismiss_never_touches_the_server(self) -> None:
        result, _, client = self._run("dismiss 0", {"suggestions": [_suggestion()]})
        client.formalize.assert_not_called()
        client.accept_suggestion.assert_not_called()
        client.reject_suggestion.assert_not_called()
        self.assertIn("Nothing was created on the server", result)


class ToggleNeverAdoptsTests(unittest.TestCase):
    """Turning listen mode on/off creates nothing and accepts nothing."""

    def _run(self, command: str, state: dict | None = None, client: Any | None = None):
        client = client or MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state or {})
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_listen_on_creates_nothing(self) -> None:
        result, _, client = self._run(f"listen on {_WORKSPACE_ID}")
        client.formalize.assert_not_called()
        client.accept_suggestion.assert_not_called()
        self.assertIn("Listen mode: on", result)

    def test_listen_off_creates_nothing(self) -> None:
        state = {"listen": {"enabled": True, "workspace_id": _WORKSPACE_ID}}
        result, _, client = self._run("listen off", state)
        client.formalize.assert_not_called()
        client.accept_suggestion.assert_not_called()
        self.assertIn("off", result)


class ReviewPendingTests(unittest.TestCase):
    """``/reqogniloom review pending`` lists the server-side queue, read-only."""

    def _run(self, command: str, state: dict | None = None, client: Any | None = None):
        client = client or MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state or {})
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_lists_workflow_queue_and_suggestion_inbox(self) -> None:
        client = MagicMock()
        client.list_pending_reviews.return_value = [
            {"item_id": "art-1", "item_type": "Requirement", "current_state": "proposed"}
        ]
        client.list_suggestions.return_value = [
            {"id": "sug-1", "kind": "trace_link", "status": "open"}
        ]
        result, _, client = self._run(f"review pending {_WORKSPACE_ID}", client=client)
        client.list_pending_reviews.assert_called_once_with(_WORKSPACE_ID)
        client.list_suggestions.assert_called_once_with(_WORKSPACE_ID)
        self.assertIn("art-1", result)
        self.assertIn("Requirement", result)
        self.assertIn("proposed", result)
        self.assertIn("sug-1", result)
        self.assertIn("trace_link", result)
        self.assertIn("adopted automatically", result)

    def test_uses_listen_workspace_when_none_given(self) -> None:
        client = MagicMock()
        client.list_pending_reviews.return_value = []
        client.list_suggestions.return_value = []
        _, _, client = self._run("review pending", {"listen": {"workspace_id": _WORKSPACE_ID}}, client)
        client.list_pending_reviews.assert_called_once_with(_WORKSPACE_ID)
        client.list_suggestions.assert_called_once_with(_WORKSPACE_ID)

    def test_one_failing_surface_degrades_without_sinking_the_other(self) -> None:
        client = MagicMock()
        client.list_pending_reviews.side_effect = plugin.ReqogniLoomError("queue down")
        client.list_suggestions.return_value = [
            {"id": "sug-1", "kind": "trace_link", "status": "open"}
        ]
        result, _, _ = self._run(f"review pending {_WORKSPACE_ID}", client=client)
        self.assertIn("unavailable (queue down)", result)
        self.assertIn("sug-1", result)

    def test_both_surfaces_empty_is_reported_honestly(self) -> None:
        client = MagicMock()
        client.list_pending_reviews.return_value = []
        client.list_suggestions.return_value = []
        result, _, _ = self._run(f"review pending {_WORKSPACE_ID}", client=client)
        self.assertIn("nothing awaiting review", result)
        self.assertIn("suggestion inbox: empty", result)

    def test_plain_review_still_lists_the_local_queue(self) -> None:
        result, _, client = self._run("review", {"suggestions": [_suggestion()]})
        client.list_pending_reviews.assert_not_called()
        self.assertIn("[0]", result)
        self.assertIn("review pending", result)


class CaptureNeverAdoptsTests(unittest.TestCase):
    """End to end: the (unchanged) capture worker only queues, never adopts."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self._tmp.name
        if str(_PLUGIN_ROOT) not in sys.path:
            sys.path.insert(0, str(_PLUGIN_ROOT))
        self.capture = _load("_capture_suggestion_under_test", _PLUGIN_ROOT / "_capture.py")
        import reqogniloom_state

        self.state = reqogniloom_state

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_home
        self._tmp.cleanup()

    def test_capture_queues_but_never_creates_or_accepts(self) -> None:
        client = MagicMock()
        client.proposal.return_value = [{"type": "Requirement", "fields": {"title": "Gate"}}]
        self.state.save_state(
            {"listen": {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-9"}}
        )
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            queued = self.capture.capture("A" * 100, {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-9"})
        self.assertEqual(queued, 1)
        client.formalize.assert_not_called()
        client.accept_suggestion.assert_not_called()
        stored = self.state.load_state()
        self.assertEqual(len(stored["suggestions"]), 1)


class SuggestionSlashBindingTests(unittest.TestCase):
    """``/reqogniloom suggestion ...`` binds the ADR-019 tools, by explicit id.

    The listing is read-only; accept/reject decide exactly one server-side
    suggestion by id, so no path accepts without an id on the command line.
    """

    def _run(self, command: str, state: dict | None = None, client: Any | None = None):
        client = client or MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state or {})
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, client, save_mock

    def test_list_wires_list_suggestions_and_renders_fields(self) -> None:
        client = MagicMock()
        client.list_suggestions.return_value = [
            {
                "id": "sug-1",
                "kind": "trace_link",
                "status": "open",
                "producer": "agent-7",
            }
        ]
        result, client, _ = self._run(f"suggestion list {_WORKSPACE_ID}", client=client)
        client.list_suggestions.assert_called_once_with(_WORKSPACE_ID)
        client.accept_suggestion.assert_not_called()
        client.reject_suggestion.assert_not_called()
        self.assertIn("sug-1", result)
        self.assertIn("trace_link", result)
        self.assertIn("open", result)
        self.assertIn("agent-7", result)

    def test_list_falls_back_to_the_listen_workspace(self) -> None:
        client = MagicMock()
        client.list_suggestions.return_value = []
        result, client, _ = self._run(
            "suggestion list", {"listen": {"workspace_id": _WORKSPACE_ID}}, client
        )
        client.list_suggestions.assert_called_once_with(_WORKSPACE_ID)
        self.assertIn("No open suggestions", result)

    def test_accept_calls_accept_suggestion_exactly_once(self) -> None:
        client = MagicMock()
        client.accept_suggestion.return_value = {
            "id": "sug-1",
            "kind": "trace_link",
            "status": "accepted",
        }
        result, client, _ = self._run("suggestion accept sug-1", client=client)
        client.accept_suggestion.assert_called_once_with("sug-1")
        client.reject_suggestion.assert_not_called()
        self.assertIn("sug-1", result)
        self.assertIn("accepted", result)
        self.assertIn("trace_link", result)

    def test_reject_passes_the_joined_reason(self) -> None:
        client = MagicMock()
        client.reject_suggestion.return_value = {"id": "sug-1", "status": "rejected"}
        result, client, _ = self._run(
            "suggestion reject sug-1 not relevant here", client=client
        )
        client.reject_suggestion.assert_called_once_with("sug-1", "not relevant here")
        client.accept_suggestion.assert_not_called()
        self.assertIn("rejected", result)

    def test_accept_without_id_shows_usage_and_never_accepts(self) -> None:
        result, client, _ = self._run("suggestion accept")
        client.accept_suggestion.assert_not_called()
        self.assertIn("Usage:", result)
        self.assertIn("suggestion", result)

    def test_reject_without_id_shows_usage_and_never_rejects(self) -> None:
        result, client, _ = self._run("suggestion reject")
        client.reject_suggestion.assert_not_called()
        self.assertIn("Usage:", result)

    def test_unknown_action_shows_usage_and_decides_nothing(self) -> None:
        result, client, _ = self._run("suggestion bogus")
        client.accept_suggestion.assert_not_called()
        client.reject_suggestion.assert_not_called()
        self.assertIn("Usage:", result)

    def test_permission_denied_on_accept_is_readable_not_raised(self) -> None:
        client = MagicMock()
        # The plugin's own class: only it is an instance of the ReqogniLoomError
        # the slash command catches.
        client.accept_suggestion.side_effect = plugin_client_mod._PermissionError(
            "PERMISSION_DENIED: an agent may not accept its own proposal"
        )
        result, _, _ = self._run("suggestion accept sug-1", client=client)
        self.assertIn("ReqogniLoom error", result)
        self.assertIn("PERMISSION_DENIED", result)

    def test_review_pending_behaviour_is_unchanged(self) -> None:
        client = MagicMock()
        client.list_pending_reviews.return_value = [
            {"item_id": "art-1", "item_type": "Requirement", "current_state": "proposed"}
        ]
        client.list_suggestions.return_value = [
            {"id": "sug-1", "kind": "trace_link", "status": "open"}
        ]
        result, client, _ = self._run(f"review pending {_WORKSPACE_ID}", client=client)
        client.list_pending_reviews.assert_called_once_with(_WORKSPACE_ID)
        client.list_suggestions.assert_called_once_with(_WORKSPACE_ID)
        client.accept_suggestion.assert_not_called()
        client.reject_suggestion.assert_not_called()
        self.assertIn("art-1", result)
        self.assertIn("sug-1", result)


if __name__ == "__main__":
    unittest.main()
