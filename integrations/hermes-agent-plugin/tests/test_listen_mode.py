"""Tests for the listen ("hear along") mode: the switch, the review queue, the
``pre_llm_call`` hook and the detached capture worker.

The design contract these pin down: capturing is *suggestions only*. No path in
this feature may create an artifact without an explicit ``/reqogniloom accept``,
and none of it may raise into the agent's turn.

Run: python3 -m unittest tests/test_listen_mode.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from _loader import load_plugin

plugin = load_plugin()

assert plugin.__file__ is not None  # load_plugin() always loads from a real file
PLUGIN_DIR = Path(plugin.__file__).resolve().parent


def _capture_module():
    """Import ``_capture.py`` as a top-level module (that is how the parent
    spawns it: a script, not a package module)."""
    if str(PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGIN_DIR))
    spec = importlib.util.spec_from_file_location("_capture_under_test", PLUGIN_DIR / "_capture.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_capture_under_test"] = module
    spec.loader.exec_module(module)
    return module


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


class WorthCapturingTests(unittest.TestCase):
    def test_short_messages_are_not_captured(self) -> None:
        for text in ("ok", "danke!", "", "   "):
            with self.subTest(text=text):
                self.assertFalse(plugin._worth_capturing(text))

    def test_commands_are_never_captured(self) -> None:
        long_command = "/reqogniloom start Requirement with a fairly long tail of words"
        self.assertFalse(plugin._worth_capturing(long_command))
        self.assertFalse(plugin._worth_capturing("!ls -la /opt/data and then some more text here"))

    def test_substantial_statement_is_captured(self) -> None:
        self.assertTrue(plugin._worth_capturing("A" * plugin.MIN_CAPTURE_CHARS))


class ListenToggleTests(unittest.TestCase):
    def _run(self, command: str, state=None, client=None):
        client = client or MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state or {})
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_listen_on_with_workspace_writes_the_switch(self) -> None:
        result, save_mock, client = self._run("listen on 11111111-1111-1111-1111-111111111111")
        saved = save_mock.call_args.args[0]
        self.assertTrue(saved["listen"]["enabled"])
        self.assertEqual(saved["listen"]["workspace_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(saved["listen"]["min_interval_seconds"], plugin.DEFAULT_MIN_INTERVAL_SECONDS)
        self.assertIn("Listen mode: on", result)
        # Nothing is created by turning the switch on.
        client.formalize.assert_not_called()

    def test_listen_on_without_workspace_uses_the_first_visible_one(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = [{"id": "ws-9", "name": "Demo"}]
        _, save_mock, _ = self._run("listen on", client=client)
        self.assertEqual(save_mock.call_args.args[0]["listen"]["workspace_id"], "ws-9")

    def test_listen_off_keeps_the_rest_of_the_state(self) -> None:
        state = {"listen": {"enabled": True, "workspace_id": "ws-1"}, "suggestions": [_suggestion()]}
        result, save_mock, _ = self._run("listen off", state=state)
        saved = save_mock.call_args.args[0]
        self.assertFalse(saved["listen"]["enabled"])
        self.assertEqual(saved["listen"]["workspace_id"], "ws-1")
        self.assertEqual(len(saved["suggestions"]), 1, "switching off must not drop the review queue")
        self.assertIn("off", result)

    def test_listen_status_reports_the_switch(self) -> None:
        state = {"listen": {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-1"}}
        result, save_mock, _ = self._run("listen", state=state)
        self.assertIn("Listen mode: on", result)
        self.assertIn("ws-1", result)
        save_mock.assert_not_called()

    def test_listen_status_when_never_configured(self) -> None:
        result, _, _ = self._run("listen")
        self.assertIn("Listen mode: off", result)

    def test_unknown_listen_action_is_a_usage_error(self) -> None:
        result, save_mock, _ = self._run("listen maybe")
        self.assertIn("Usage:", result)
        save_mock.assert_not_called()


class ReviewQueueTests(unittest.TestCase):
    def _run(self, command: str, state, client=None):
        client = client or MagicMock()
        client.formalize.return_value = {"resulting_artifact_ids": ["art-1"], "status": "formalized"}
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state)
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_review_lists_pending_suggestions(self) -> None:
        result, _, _ = self._run("review", {"suggestions": [_suggestion()]})
        self.assertIn("[0]", result)
        self.assertIn("Requirement", result)
        self.assertIn("Token gate must be opt-in", result)

    def test_review_with_empty_queue(self) -> None:
        result, _, _ = self._run("review", {})
        self.assertIn("No pending suggestions", result)

    def test_accept_creates_only_the_selected_suggestion(self) -> None:
        state = {"suggestions": [_suggestion("a"), _suggestion("b", "sess-2")]}
        result, save_mock, client = self._run("accept 1", state)
        client.formalize.assert_called_once()
        session_id, kwargs = client.formalize.call_args.args[0], client.formalize.call_args.kwargs
        self.assertEqual(session_id, "sess-2")
        self.assertEqual(kwargs["confirmed_proposal"][0]["type"], "Requirement")
        remaining = save_mock.call_args.args[0]["suggestions"]
        self.assertEqual([entry["signature"] for entry in remaining], ["a"])
        self.assertIn("art-1", result)

    def test_accept_all_creates_every_suggestion(self) -> None:
        state = {"suggestions": [_suggestion("a"), _suggestion("b", "sess-2")]}
        _, save_mock, client = self._run("accept all", state)
        self.assertEqual(client.formalize.call_count, 2)
        self.assertEqual(save_mock.call_args.args[0]["suggestions"], [])

    def test_dismiss_creates_nothing(self) -> None:
        state = {"suggestions": [_suggestion("a"), _suggestion("b", "sess-2")]}
        result, save_mock, client = self._run("dismiss 0", state)
        client.formalize.assert_not_called()
        remaining = save_mock.call_args.args[0]["suggestions"]
        self.assertEqual([entry["signature"] for entry in remaining], ["b"])
        self.assertIn("Dismissed 1", result)

    def test_accept_out_of_range_is_refused(self) -> None:
        result, save_mock, client = self._run("accept 7", {"suggestions": [_suggestion()]})
        self.assertIn("out of range", result)
        client.formalize.assert_not_called()
        save_mock.assert_not_called()

    def test_accept_non_numeric_is_refused(self) -> None:
        result, _, client = self._run("accept first", {"suggestions": [_suggestion()]})
        self.assertIn("not a suggestion index", result)
        client.formalize.assert_not_called()

    def test_accept_without_targets_is_a_usage_error(self) -> None:
        result, _, client = self._run("accept", {"suggestions": [_suggestion()]})
        self.assertIn("Usage:", result)
        client.formalize.assert_not_called()

    def test_accept_reports_a_server_failure_without_dropping_the_suggestion(self) -> None:
        # plugin.ReqogniLoomError, not a freshly imported one: the class object
        # the client raises in production is the plugin's own, and only that one
        # is caught in-place. (A different class would escape to the outer
        # handler and mask the partial-failure path.)
        client = MagicMock()
        client.formalize.side_effect = plugin.ReqogniLoomError("formalize exploded")
        result, save_mock, _ = self._run("accept all", {"suggestions": [_suggestion()]}, client=client)
        self.assertIn("formalize exploded", result)
        self.assertIn("Failed, still pending", result)
        self.assertEqual(len(save_mock.call_args.args[0]["suggestions"]), 1)

    def test_accept_partial_success_keeps_only_the_failed_suggestion(self) -> None:
        # Suggestions are formalized highest-index-first (popping reindexes the
        # list, and the human's indices refer to what /reqogniloom review just
        # printed), so the first side effect belongs to index 1.
        client = MagicMock()
        client.formalize.side_effect = [
            plugin.ReqogniLoomError("server said no"),
            {"resulting_artifact_ids": ["art-2"], "status": "formalized"},
        ]
        state = {"suggestions": [_suggestion("a"), _suggestion("b", "sess-2")]}
        result, save_mock, _ = self._run("accept all", state, client=client)
        self.assertIn("Created 1 artifact(s): art-2", result)
        self.assertIn("server said no", result)
        remaining = save_mock.call_args.args[0]["suggestions"]
        self.assertEqual([entry["signature"] for entry in remaining], ["b"])

    def test_accept_and_dismiss_on_an_empty_queue(self) -> None:
        for command in ("accept all", "dismiss all"):
            with self.subTest(command=command):
                result, _, _ = self._run(command, {})
                self.assertIn("Nothing to review", result)


class PreLlmCallHookTests(unittest.TestCase):
    """The hook must be a silent side effect: it never injects context and never
    raises, whatever the state file says."""

    def _hook(self, state, user_message, **extra):
        with patch.object(plugin, "_load_state", return_value=state), patch.object(
            plugin, "_save_state"
        ), patch.object(plugin, "_spawn_capture") as spawn:
            result = plugin._on_pre_llm_call(user_message=user_message, platform="matrix", session_id="s1", **extra)
        return result, spawn

    def test_returns_none_and_spawns_nothing_while_off(self) -> None:
        result, spawn = self._hook({}, "A" * 100)
        self.assertIsNone(result)
        spawn.assert_not_called()

    def test_returns_none_but_spawns_while_on(self) -> None:
        result, spawn = self._hook({"listen": {"enabled": True, "workspace_id": "ws-1"}}, "A" * 100)
        self.assertIsNone(result)
        spawn.assert_called_once_with("A" * 100, "matrix", "s1")

    def test_throttle_blocks_a_second_capture(self) -> None:
        state = {
            "listen": {
                "enabled": True,
                "workspace_id": "ws-1",
                "min_interval_seconds": 600,
                "last_capture_at": __import__("time").time(),
            }
        }
        result, spawn = self._hook(state, "A" * 100)
        self.assertIsNone(result)
        spawn.assert_not_called()

    def test_short_message_is_not_spawned(self) -> None:
        _, spawn = self._hook({"listen": {"enabled": True, "workspace_id": "ws-1"}}, "ok")
        spawn.assert_not_called()

    def test_capture_is_stamped_before_spawning(self) -> None:
        state = {"listen": {"enabled": True, "workspace_id": "ws-1"}}
        with patch.object(plugin, "_load_state", return_value=state), patch.object(
            plugin, "_save_state"
        ) as save_mock, patch.object(plugin, "_spawn_capture"):
            plugin._on_pre_llm_call(user_message="A" * 100, platform="matrix", session_id="s1")
        self.assertGreater(save_mock.call_args.args[0]["listen"]["last_capture_at"], 0)

    def test_unexpected_errors_are_swallowed(self) -> None:
        with patch.object(plugin, "_load_state", side_effect=RuntimeError("boom")):
            self.assertIsNone(plugin._on_pre_llm_call(user_message="A" * 100))

    def test_extra_hook_kwargs_are_tolerated(self) -> None:
        # The host passes a growing set of kwargs (conversation_history, model,
        # is_first_turn, …); the callback must not choke on any of them.
        result, _ = self._hook(
            {"listen": {"enabled": True, "workspace_id": "ws-1"}},
            "A" * 100,
            conversation_history=[{"role": "user"}],
            model="deepseek",
            is_first_turn=False,
            turn_id="t-1",
        )
        self.assertIsNone(result)


class CaptureWorkerTests(unittest.TestCase):
    """The worker, end to end against a temporary HERMES_HOME: it queues a
    suggestion and it creates nothing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self._tmp.name
        self.capture = _capture_module()
        import reqogniloom_state

        self.state = reqogniloom_state

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_home
        self._tmp.cleanup()

    def test_proposal_items_normalises_the_shapes(self) -> None:
        items = [{"type": "Requirement", "fields": {"title": "x"}}]
        self.assertEqual(self.capture.proposal_items(items), items)
        self.assertEqual(self.capture.proposal_items({"items": items}), items)
        self.assertEqual(self.capture.proposal_items(None), [])
        self.assertEqual(self.capture.proposal_items({"proposal": None}), [])

    def test_capture_opens_a_multi_session_and_queues_the_proposal(self) -> None:
        client = MagicMock()
        client.start_interview.return_value = {"id": "sess-9"}
        client.proposal.return_value = {"items": [{"type": "Requirement", "fields": {"title": "Gate"}}]}

        listen = {"enabled": True, "workspace_id": "ws-1"}
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            queued = self.capture.capture("A" * 100, listen)

        self.assertEqual(queued, 1)
        client.start_interview.assert_called_once_with(None, "ws-1", session_kind="multi")
        client.chat.assert_called_once_with("sess-9", "A" * 100)
        client.formalize.assert_not_called()

        stored = self.state.load_state()
        self.assertEqual(stored["listen"]["session_id"], "sess-9")
        self.assertEqual(len(stored["suggestions"]), 1)
        self.assertEqual(stored["suggestions"][0]["items"][0]["type"], "Requirement")

    def test_capture_reuses_the_stored_session_and_dedupes(self) -> None:
        client = MagicMock()
        client.proposal.return_value = [{"type": "Requirement", "fields": {"title": "Gate"}}]
        self.state.save_state({"listen": {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-9"}})

        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            self.capture.capture("A" * 100, {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-9"})
            self.capture.capture("B" * 100, {"enabled": True, "workspace_id": "ws-1", "session_id": "sess-9"})

        client.start_interview.assert_not_called()
        self.assertEqual(len(self.state.load_state()["suggestions"]), 1, "identical proposals must not stack up")

    def test_main_skips_a_disabled_switch(self) -> None:
        payload = Path(self._tmp.name) / "payload.json"
        payload.write_text(json.dumps({"text": "A" * 100, "platform": "matrix"}), encoding="utf-8")
        self.state.save_state({"listen": {"enabled": False, "workspace_id": "ws-1"}})
        client = MagicMock()
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            exit_code = self.capture.main(["capture", str(payload)])
        self.assertEqual(exit_code, 0)
        client.chat.assert_not_called()
        self.assertFalse(payload.exists(), "the payload file is consumed even on the skip path")

    def test_main_reports_a_capture_failure_as_a_logged_nonzero(self) -> None:
        payload = Path(self._tmp.name) / "payload.json"
        payload.write_text(json.dumps({"text": "A" * 100}), encoding="utf-8")
        self.state.save_state({"listen": {"enabled": True, "workspace_id": "ws-1"}})
        with patch.object(self.capture, "ReqogniLoomClient", side_effect=RuntimeError("no network")):
            exit_code = self.capture.main(["capture", str(payload)])
        self.assertEqual(exit_code, 1)
        log = (Path(self._tmp.name) / "reqogniloom" / "capture.log").read_text(encoding="utf-8")
        self.assertIn("capture failed", log)


if __name__ == "__main__":
    unittest.main()
