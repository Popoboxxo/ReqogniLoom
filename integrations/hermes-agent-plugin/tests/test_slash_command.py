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

    def test_help_example_uses_pascalcase_artifact_type(self) -> None:
        # AUD-110: the server only accepts the canonical PascalCase names
        # (IN_SCOPE_ARTIFACT_TYPES), so the help text must not advertise a
        # lowercase invocation that is rejected live with 400.
        text = plugin._handle_slash("help")
        self.assertIn('"Requirement"', text)
        self.assertNotIn('"requirement"', text)

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
            # Real server shape (interview_service._serialise_field): missing
            # fields are dicts, not bare strings. The old string fixture hid a
            # TypeError in _fmt_state (PLUG-01).
            "missing_fields": [{"name": "title", "type": "text", "choices": None}],
        }
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_save_state"
        ) as save_mock:
            result = plugin._handle_slash("start Requirement")

        fake_client.start_interview.assert_called_once_with("Requirement", "ws-1")
        save_mock.assert_called_once_with({"session_id": "sess-1", "workspace_id": "ws-1"})
        self.assertIn("Started interview sess-1", result)
        self.assertIn("phase:     collecting", result)
        self.assertIn("missing:   title", result)

    def test_start_with_explicit_workspace_id(self) -> None:
        fake_client = MagicMock()
        fake_client.start_interview.return_value = {"id": "sess-2", "phase": "collecting"}
        workspace_uuid = "11111111-1111-1111-1111-111111111111"
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_save_state"
        ):
            plugin._handle_slash(f"start StakeholderNeed {workspace_uuid}")

        fake_client.start_interview.assert_called_once_with("StakeholderNeed", workspace_uuid)
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

    def test_formalize_reports_resulting_artifact_ids(self) -> None:
        # AUD-111: the server returns {"resulting_artifact_ids": [...],
        # "status": ...}; `artifact_id` never exists, so the old code dumped
        # the raw response dict instead of reporting the created IDs.
        fake_client = MagicMock()
        fake_client.formalize.return_value = {
            "resulting_artifact_ids": ["REQ-1"],
            "status": "completed",
        }
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_load_state", return_value={"session_id": "sess-1"}
        ):
            result = plugin._handle_slash("formalize")

        fake_client.formalize.assert_called_once_with("sess-1")
        self.assertEqual(result, "Formalized. Artifact(s): REQ-1")

    def test_abandon_clears_state(self) -> None:
        fake_client = MagicMock()
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client), patch.object(
            plugin, "_load_state", return_value={"session_id": "sess-1"}
        ), patch.object(plugin, "_save_state") as save_mock:
            result = plugin._handle_slash("abandon")

        fake_client.abandon.assert_called_once_with("sess-1")
        save_mock.assert_called_once_with({})
        self.assertIn("Abandoned interview sess-1", result)

    def test_unexpected_client_error_is_reported_not_raised(self) -> None:
        # "Never raises" covers more than ReqogniLoomError: any unexpected
        # failure (e.g. a server shape change) must become a human-readable
        # string, not a traceback in the chat.
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = TypeError("bad payload shape")
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client):
            result = plugin._handle_slash("workspaces")
        self.assertIn("ReqogniLoom plugin error", result)
        self.assertIn("bad payload shape", result)

    def test_fmt_state_tolerates_string_missing_fields(self) -> None:
        # Backwards compatibility: an older server may still send bare strings.
        rendered = plugin._fmt_state(
            {"id": "sess-1", "phase": "collecting", "missing_fields": ["title"]}
        )
        self.assertIn("missing:   title", rendered)

    def test_client_error_is_reported_not_raised(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin.ReqogniLoomError("could not reach host")
        with patch.object(plugin, "ReqogniLoomClient", return_value=fake_client):
            result = plugin._handle_slash("workspaces")
        self.assertIn("ReqogniLoom error", result)
        self.assertIn("could not reach host", result)


def _slash_server_add(server_id: str, base_url: str) -> None:
    """Add one server through the real command path (no direct registry call)."""
    result = plugin._handle_slash(f"server add {server_id} {base_url}")
    assert "Added server" in result, result


class ServerGroupTests(unittest.TestCase):
    """`/reqogniloom server …` — the multi-server management group.

    The registry itself is covered in test_registry.py; here the wiring is: does
    the command reach the registry, report it readably, and never leak a key.
    """

    def test_help_mentions_the_server_group(self) -> None:
        text = plugin._handle_slash("help")
        self.assertIn("server list", text)
        self.assertIn("REQOGNILOOM_API_KEY_", text)

    def test_server_list_on_an_unconfigured_install_explains_the_setup(self) -> None:
        result = plugin._handle_slash("server list")
        self.assertIn("server add", result)

    def test_server_list_shows_a_configured_server(self) -> None:
        plugin._registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_secret")
        result = plugin._handle_slash("server list")
        self.assertIn("qs", result)
        self.assertIn("http://qs.test:8001", result)
        self.assertNotIn("reqlo_secret", result, "the listing must not print the key")

    def test_server_add_uses_env_references_and_activates(self) -> None:
        result = plugin._handle_slash("server add qs http://qs.test:8001")
        self.assertIn("Added server qs", result)
        self.assertIn("REQOGNILOOM_API_KEY_QS", result)
        self.assertEqual(plugin._registry.load_registry()["active"], "qs")

    def test_server_add_requires_both_arguments(self) -> None:
        self.assertIn("Usage:", plugin._handle_slash("server add qs"))

    def test_server_add_rejects_an_invalid_id(self) -> None:
        result = plugin._handle_slash("server add 'Bad Id' http://qs.test:8001")
        self.assertIn("Server configuration error", result)

    def test_server_use_switches_and_names_the_active_one(self) -> None:
        _slash_server_add("qs", "http://qs.test:8001")
        _slash_server_add("prod", "http://prod.test:8001")
        result = plugin._handle_slash("server use prod")
        self.assertIn("Active server is now prod", result)

    def test_server_use_without_an_id_prints_usage(self) -> None:
        self.assertIn("Usage:", plugin._handle_slash("server use"))

    def test_server_use_unknown_id_is_a_configuration_error(self) -> None:
        with self.assertRaises(plugin._registry.RegistryError):
            plugin._registry.set_active("ghost")
        result = plugin._handle_slash("server use ghost")
        self.assertIn("Server configuration error", result)
        self.assertIn("ghost", result)

    def test_server_rm_drops_the_entry(self) -> None:
        _slash_server_add("qs", "http://qs.test:8001")
        result = plugin._handle_slash("server rm qs")
        self.assertIn("Removed server qs", result)
        self.assertEqual(plugin._registry.load_registry()["servers"], [])

    def test_server_use_invalidates_the_tool_catalogue(self) -> None:
        # The catalogue belongs to a server: a stale cache would show the old
        # server's tools (and its tool count) after a switch.
        _slash_server_add("qs", "http://qs.test:8001")
        _slash_server_add("prod", "http://prod.test:8001")
        with patch.object(plugin._tools, "invalidate") as invalidate:
            plugin._handle_slash("server use qs")
        invalidate.assert_called_once_with()

    def test_server_without_action_defaults_to_list(self) -> None:
        _slash_server_add("qs", "http://qs.test:8001")
        self.assertIn("qs", plugin._handle_slash("server"))

    def test_unknown_server_action_prints_usage(self) -> None:
        self.assertIn("Usage:", plugin._handle_slash("server frobnicate"))

    def test_server_test_reports_reachability(self) -> None:
        _slash_server_add("qs", "http://qs.test:8001")

        class FakeProbeClient:
            def version(self):
                return {"version": "1.8.0-beta.21"}

            def tools_list(self, *, api_key=None):
                return [{"name": "requirement.get"}]

        with patch.object(plugin, "_server_action_client", return_value=FakeProbeClient()):
            result = plugin._handle_slash("server test qs")
        self.assertIn("reachable", result)
        self.assertIn("1.8.0-beta.21", result)
        self.assertIn("tools:      1", result)

    def test_server_test_stores_the_outcome_for_the_listing(self) -> None:
        _slash_server_add("qs", "http://qs.test:8001")

        class FakeProbeClient:
            def version(self):
                return {"version": "1.8.0-beta.21"}

            def tools_list(self, *, api_key=None):
                return [{"name": "requirement.get"}] * 3

        with patch.object(plugin, "_server_action_client", return_value=FakeProbeClient()):
            plugin._handle_slash("server test qs")
        view = plugin._registry.public_registry()["servers"][0]
        self.assertEqual(view["verify"]["tool_count"], 3)

    def test_server_test_without_a_server_points_at_the_setup(self) -> None:
        result = plugin._handle_slash("server test")
        self.assertIn("server add", result)

    def test_server_test_of_an_unknown_id_is_a_configuration_error(self) -> None:
        result = plugin._handle_slash("server test ghost")
        self.assertIn("Server configuration error", result)


if __name__ == "__main__":
    unittest.main()
