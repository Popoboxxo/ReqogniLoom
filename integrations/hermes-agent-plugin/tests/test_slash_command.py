"""Unit tests for the /reqogniloom slash command handler.

Run: python3 -m unittest tests/test_slash_command.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from _loader import load_plugin

plugin = load_plugin()


class HandleSlashTests(unittest.TestCase):
    def test_help_with_no_args(self) -> None:
        self.assertIn("/reqogniloom", plugin._handle_slash(""))

    def test_help_subcommand(self) -> None:
        self.assertIn("Subcommands", plugin._handle_slash("help"))

    def test_unknown_subcommand(self) -> None:
        self.assertIn("Unknown subcommand", plugin._handle_slash("bogus"))

    def test_status_without_active_session(self) -> None:
        with patch.object(plugin, "_load_state", return_value={}):
            result = plugin._handle_slash("status")
        self.assertIn("No active interview", result)

    def test_start_missing_artifact_type(self) -> None:
        result = plugin._handle_slash("start")
        self.assertIn("Usage:", result)

    def test_start_success_resolves_first_workspace(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = [{"id": "ws-1", "name": "Demo"}]
        fake_client.start_interview.return_value = {
            "id": "sess-1",
            "phase": "collecting",
            "missing_fields": ["title"],
        }
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_save_state"
        ) as save_mock:
            result = plugin._handle_slash("start requirement")

        fake_client.start_interview.assert_called_once_with("requirement", "ws-1")
        save_mock.assert_called_once_with({"session_id": "sess-1", "workspace_id": "ws-1"})
        self.assertIn("Started interview sess-1", result)
        self.assertIn("phase:     collecting", result)

    def test_start_with_explicit_workspace_id(self) -> None:
        fake_client = MagicMock()
        fake_client.start_interview.return_value = {"id": "sess-2", "phase": "collecting"}
        workspace_uuid = "11111111-1111-1111-1111-111111111111"
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_save_state"
        ):
            plugin._handle_slash(f"start need {workspace_uuid}")

        fake_client.start_interview.assert_called_once_with("need", workspace_uuid)
        fake_client.list_workspaces.assert_not_called()

    def test_answer_requires_active_session(self) -> None:
        with patch.object(plugin, "_load_state", return_value={}):
            result = plugin._handle_slash("answer title Foo")
        self.assertIn("No active interview", result)

    def test_answer_forwards_to_client(self) -> None:
        fake_client = MagicMock()
        fake_client.answer.return_value = {"id": "sess-1", "phase": "collecting", "missing_fields": []}
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_load_state", return_value={"session_id": "sess-1"}
        ):
            result = plugin._handle_slash("answer title My Requirement")

        fake_client.answer.assert_called_once_with("sess-1", "title", "My Requirement")
        self.assertIn("phase:     collecting", result)

    def test_abandon_clears_state(self) -> None:
        fake_client = MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_load_state", return_value={"session_id": "sess-1"}
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash("abandon")

        fake_client.abandon.assert_called_once_with("sess-1")
        save_mock.assert_called_once_with({})
        self.assertIn("Abandoned interview sess-1", result)

    def test_client_error_is_reported_not_raised(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin.ReqogniLoomError("could not reach host")
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client):
            result = plugin._handle_slash("workspaces")
        self.assertIn("ReqogniLoom error", result)
        self.assertIn("could not reach host", result)


if __name__ == "__main__":
    unittest.main()
