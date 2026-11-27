"""Tests for the Hermes listen mode: the shared switch, the write-ahead queue,
the ``pre_llm_call`` hook and the detached drain worker.

The contract is documented in ``docs/clients/listen-mode-contract.md`` and is
identical for every client. What these tests pin down:

* the hook does no network work and never raises into the turn;
* messages inside a window are queued, not dropped (H3);
* the switch and the queue live in ``~/.reqogniloom/listen`` (override
  ``REQNILOOM_LISTEN_DIR``), so all clients share them;
* ``off`` deletes anything unsent (privacy action);
* a failed delivery stays queued; a permanent 400/409 does not.

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
WORKSPACE = "11111111-1111-1111-1111-111111111111"


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


class _StateDirMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("REQNILOOM_LISTEN_DIR")
        self.state_dir = Path(self._tmp.name) / "listen"
        os.environ["REQNILOOM_LISTEN_DIR"] = str(self.state_dir)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("REQNILOOM_LISTEN_DIR", None)
        else:
            os.environ["REQNILOOM_LISTEN_DIR"] = self._old
        self._tmp.cleanup()

    def write_switch(self, enabled: bool, workspace: str = WORKSPACE) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "listen.json").write_text(
            json.dumps({"enabled": enabled, "workspace_id": workspace}), encoding="utf-8"
        )

    def queue(self) -> list[dict]:
        path = self.state_dir / "capture-queue.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class WorthCapturingTests(unittest.TestCase):
    def test_short_messages_are_not_captured(self) -> None:
        for text in ("ok", "danke!", "", "   "):
            with self.subTest(text=text):
                self.assertFalse(plugin._worth_capturing(text))

    def test_commands_are_never_captured(self) -> None:
        self.assertFalse(plugin._worth_capturing("/reqogniloom start Requirement with a fairly long tail of words"))
        self.assertFalse(plugin._worth_capturing("!ls -la /opt/data and then some more text here"))

    def test_a_pasted_log_is_not_captured(self) -> None:
        self.assertFalse(plugin._worth_capturing("\n".join(["line"] * 301)))

    def test_substantial_statement_is_captured(self) -> None:
        self.assertTrue(plugin._worth_capturing("A" * plugin.MIN_CAPTURE_CHARS))


class ListenToggleTests(_StateDirMixin):
    def _run(self, command: str, state=None, client=None):
        client = client or MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=client), patch.object(
            plugin, "_load_state", return_value=dict(state or {})
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash(command)
        return result, save_mock, client

    def test_listen_on_writes_the_shared_switch(self) -> None:
        result, save_mock, client = self._run(f"listen on {WORKSPACE}")
        switch = json.loads((self.state_dir / "listen.json").read_text())
        self.assertTrue(switch["enabled"])
        self.assertEqual(switch["workspace_id"], WORKSPACE)
        self.assertIn("Listen mode: on", result)
        self.assertIn("Privacy", result)
        # The compatibility mirror keeps the review commands working.
        self.assertTrue(save_mock.call_args.args[0]["listen"]["enabled"])
        client.formalize.assert_not_called()

    def test_listen_on_without_workspace_is_refused(self) -> None:
        """H6: capture never guesses the first visible workspace."""
        result, save_mock, client = self._run("listen on")
        self.assertIn("Usage:", result)
        self.assertIn("explicit", result)
        self.assertFalse((self.state_dir / "listen.json").exists())
        save_mock.assert_not_called()
        client.list_workspaces.assert_not_called()

    def test_listen_off_deletes_unsent_and_keeps_counters(self) -> None:
        self.write_switch(True)
        (self.state_dir / "capture-queue.jsonl").write_text(
            json.dumps({"workspace_id": WORKSPACE, "text": "A" * 100}) + "\n", encoding="utf-8"
        )
        (self.state_dir / "listen-status.json").write_text(
            json.dumps({"captured": 3, "failed": 1, "queued": 1}), encoding="utf-8"
        )
        result, save_mock, _ = self._run(
            "listen off", {"suggestions": [{"id": "legacy"}]}
        )
        switch = json.loads((self.state_dir / "listen.json").read_text())
        self.assertFalse(switch["enabled"])
        self.assertIn("deleted", result)
        self.assertFalse((self.state_dir / "capture-queue.jsonl").exists())
        status = json.loads((self.state_dir / "listen-status.json").read_text())
        self.assertEqual(status["queued"], 0)
        self.assertEqual(status["captured"], 3)
        self.assertEqual(len(save_mock.call_args.args[0]["suggestions"]), 1)

    def test_listen_status_reports_the_contract_keys(self) -> None:
        self.write_switch(True)
        (self.state_dir / "listen-status.json").write_text(
            json.dumps(
                {
                    "captured": 2,
                    "failed": 1,
                    "queued": 0,
                    "last_success_at": "2026-11-27T10:00:00Z",
                    "last_error": "timeout",
                    "last_error_at": "2026-11-27T09:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        result, save_mock, _ = self._run("listen status")
        self.assertIn("Listen mode: on", result)
        self.assertIn(WORKSPACE, result)
        self.assertIn("captured:         2", result)
        self.assertIn("failed:           1", result)
        self.assertIn("last error:       timeout", result)
        save_mock.assert_not_called()

    def test_listen_status_when_never_configured(self) -> None:
        result, _, _ = self._run("listen")
        self.assertIn("Listen mode: off", result)

    def test_unknown_listen_action_is_a_usage_error(self) -> None:
        result, save_mock, _ = self._run("listen maybe")
        self.assertIn("Usage:", result)
        save_mock.assert_not_called()


class PreLlmCallHookTests(_StateDirMixin):
    """The hook must be a silent side effect: it never injects context, never
    raises and never sends inline."""

    def _hook(self, user_message, **extra):
        with patch.object(plugin, "_spawn_worker") as spawn:
            result = plugin._on_pre_llm_call(
                user_message=user_message, platform="matrix", session_id="s1", **extra
            )
        return result, spawn

    def test_returns_none_and_queues_nothing_while_off(self) -> None:
        result, spawn = self._hook("A" * 100)
        self.assertIsNone(result)
        spawn.assert_not_called()
        self.assertEqual(self.queue(), [])

    def test_queues_while_on_without_sending_inline(self) -> None:
        self.write_switch(True)
        result, spawn = self._hook("A" * 100, turn_id="turn-1")
        self.assertIsNone(result)
        spawn.assert_called_once()
        entries = self.queue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["client"], "hermes")
        self.assertEqual(entries[0]["workspace_id"], WORKSPACE)
        self.assertEqual(entries[0]["source_session"], "s1")
        self.assertEqual(entries[0]["message_id"], "turn-1")
        self.assertEqual(len(entries[0]["idempotency_key"]), 64)

    def test_messages_inside_a_window_are_queued_not_dropped(self) -> None:
        """H3: no throttle that silently discards the second message."""
        self.write_switch(True)
        self._hook("A" * 100)
        self._hook("B" * 100)
        self.assertEqual([entry["text"][0] for entry in self.queue()], ["A", "B"])

    def test_short_message_is_not_queued(self) -> None:
        self.write_switch(True)
        _, spawn = self._hook("ok")
        spawn.assert_not_called()
        self.assertEqual(self.queue(), [])

    def test_missing_workspace_is_a_logged_skip(self) -> None:
        self.write_switch(True, workspace="")
        _, spawn = self._hook("A" * 100)
        self.assertEqual(self.queue(), [])
        # The worker still runs so the status can report the missing config.
        spawn.assert_called_once()

    def test_unexpected_errors_are_swallowed(self) -> None:
        with patch.object(plugin._listen, "load_switch", side_effect=RuntimeError("boom")):
            self.assertIsNone(plugin._on_pre_llm_call(user_message="A" * 100))

    def test_extra_hook_kwargs_are_tolerated(self) -> None:
        self.write_switch(True)
        result, _ = self._hook(
            "A" * 100,
            conversation_history=[{"role": "user"}],
            model="deepseek",
            is_first_turn=False,
        )
        self.assertIsNone(result)


class CaptureWorkerTests(_StateDirMixin):
    """The worker, end to end against the shared state directory."""

    def setUp(self) -> None:
        super().setUp()
        self.capture = _capture_module()

    def _enqueue(self, text: str) -> int:
        payload = Path(self._tmp.name) / "payload.json"
        payload.write_text(
            json.dumps(
                {
                    "text": text,
                    "workspace_id": WORKSPACE,
                    "client": "hermes",
                    "source_session": "s1",
                }
            ),
            encoding="utf-8",
        )
        return self.capture.main(["capture", "--enqueue", str(payload)])

    def test_enqueue_filters_and_writes_the_entry(self) -> None:
        self.write_switch(True)
        self.assertEqual(self._enqueue("ok"), 0)
        self.assertEqual(self.queue(), [])
        self.assertEqual(self._enqueue("A" * 100), 0)
        entries = self.queue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "A" * 100)

    def test_enqueue_respects_the_switch(self) -> None:
        self.assertEqual(self._enqueue("A" * 100), 0)
        self.assertEqual(self.queue(), [])

    def test_drain_posts_once_and_writes_the_status(self) -> None:
        self.write_switch(True)
        self._enqueue("A" * 100)
        client = MagicMock()
        client.base_url = "http://example.invalid"
        client.api_key = "reqlo_test_key"
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            self.assertEqual(self.capture.main(["capture", "--drain"]), 0)
        client.capture_suggestion.assert_called_once()
        kwargs = client.capture_suggestion.call_args.kwargs
        self.assertEqual(kwargs["workspace_id"], WORKSPACE)
        self.assertEqual(kwargs["client"], "hermes")
        self.assertEqual(kwargs["source_session"], "s1")
        self.assertAlmostEqual(kwargs["timeout_seconds"], 60.0, places=1)
        self.assertEqual(self.queue(), [])
        status = json.loads((self.state_dir / "listen-status.json").read_text())
        self.assertEqual(status["captured"], 1)
        self.assertEqual(status["queued"], 0)
        self.assertIsNone(status["last_error"])

    def test_failed_delivery_stays_queued_and_a_later_run_sends_it(self) -> None:
        self.write_switch(True)
        self._enqueue("A" * 100)
        failing = MagicMock()
        failing.base_url = "http://example.invalid"
        failing.api_key = "reqlo_test_key"
        error = plugin.ReqogniLoomError("server down", status=500)
        failing.capture_suggestion.side_effect = error
        with patch.object(self.capture, "ReqogniLoomClient", return_value=failing):
            self.assertEqual(self.capture.main(["capture", "--drain"]), 0)
        queued = self.queue()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["attempts"], 1)
        status = json.loads((self.state_dir / "listen-status.json").read_text())
        self.assertEqual(status["last_error"], "HTTP 500")
        # The log and the status never carry message text or the key.
        log = (self.state_dir / "capture.log").read_text(encoding="utf-8")
        for raw in (log, json.dumps(status)):
            self.assertNotIn("A" * 100, raw)
            self.assertNotIn("reqlo_test_key", raw)

        healthy = MagicMock()
        healthy.base_url = "http://example.invalid"
        healthy.api_key = "reqlo_test_key"
        with patch.object(self.capture, "ReqogniLoomClient", return_value=healthy):
            self.assertEqual(self.capture.main(["capture", "--drain"]), 0)
        self.assertEqual(self.queue(), [])
        status = json.loads((self.state_dir / "listen-status.json").read_text())
        self.assertIsNone(status["last_error"])

    def test_drain_is_a_no_op_while_off(self) -> None:
        self.write_switch(True)
        self._enqueue("A" * 100)
        self.write_switch(False)
        client = MagicMock()
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            self.assertEqual(self.capture.main(["capture", "--drain"]), 0)
        client.capture_suggestion.assert_not_called()
        self.assertEqual(len(self.queue()), 1)

    def test_missing_config_is_reported_not_raised(self) -> None:
        self.write_switch(True)
        self._enqueue("A" * 100)
        client = MagicMock()
        client.base_url = ""
        client.api_key = ""
        with patch.object(self.capture, "ReqogniLoomClient", return_value=client):
            self.assertEqual(self.capture.main(["capture", "--drain"]), 0)
        status = json.loads((self.state_dir / "listen-status.json").read_text())
        self.assertTrue(status["last_error"].startswith("missing_config"))
        client.capture_suggestion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
