"""Unit tests for the dashboard backend (dashboard/plugin_api.py).

Run: python3 -m unittest tests/test_plugin_api.py -v
"""
from __future__ import annotations

import inspect
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# plugin_api.py inserts _PLUGIN_ROOT onto sys.path itself on import (to reach
# reqogniloom_client.py), so no extra package-loading trick is needed here —
# unlike __init__.py it uses a plain (non-relative) import.
plugin_api = _load("reqogniloom_plugin_api_under_test", _PLUGIN_ROOT / "dashboard" / "plugin_api.py")


class DashboardApiTests(unittest.TestCase):
    def test_handlers_are_sync_so_blocking_http_leaves_the_event_loop(self) -> None:
        # The client uses blocking urllib; FastAPI only runs sync path
        # operations in a worker threadpool, async ones on the event loop.
        for handler in (plugin_api.stats, plugin_api.workspaces, plugin_api.version):
            self.assertFalse(inspect.iscoroutinefunction(handler))

    def test_stats_endpoint_returns_client_stats(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = [{"id": "ws-1", "name": "Demo"}]
        fake_client.stats.return_value = {
            "workspace_id": "ws-1",
            "requirements": 12,
            "testcases": 4,
            "open_interviews": 1,
        }
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.stats(workspace_id="")
        fake_client.stats.assert_called_once_with("ws-1")
        self.assertEqual(result["requirements"], 12)

    def test_stats_endpoint_reports_error_without_raising(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = []
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.stats(workspace_id="")
        self.assertIn("error", result)

    def test_stats_endpoint_surfaces_auth_failure_as_error(self) -> None:
        # A missing/rejected API key must reach the caller as {"error": ...},
        # not as a 200 with a payload of nulls.
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin_api.ReqogniLoomError("401: Invalid API key.")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.stats(workspace_id="")
        self.assertIn("error", result)
        self.assertIn("401", result["error"])

    def test_stats_endpoint_uses_explicit_workspace_id(self) -> None:
        fake_client = MagicMock()
        fake_client.stats.return_value = {"workspace_id": "ws-explicit"}
        workspace_uuid = "22222222-2222-2222-2222-222222222222"
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            plugin_api.stats(workspace_id=workspace_uuid)
        fake_client.stats.assert_called_once_with(workspace_uuid)
        fake_client.list_workspaces.assert_not_called()

    def test_workspaces_endpoint(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = [{"id": "ws-1", "name": "Demo"}]
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.workspaces()
        self.assertEqual(result["workspaces"], [{"id": "ws-1", "name": "Demo"}])

    def test_workspaces_endpoint_reports_shape_failure_as_error(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin_api.ReqogniLoomError("unexpected list response")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.workspaces()
        self.assertIn("error", result)

    def test_version_endpoint(self) -> None:
        fake_client = MagicMock()
        fake_client.version.return_value = {"app_version": "1.7.0", "commit_short": "abc1234"}
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.version()
        self.assertEqual(result["app_version"], "1.7.0")

    def test_version_endpoint_reports_error_without_raising(self) -> None:
        fake_client = MagicMock()
        fake_client.version.side_effect = plugin_api.ReqogniLoomError("could not reach host")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.version()
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
