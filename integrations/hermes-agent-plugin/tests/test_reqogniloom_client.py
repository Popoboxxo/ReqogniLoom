"""Unit tests for reqogniloom_client.py.

Run: python3 -m unittest tests/test_reqogniloom_client.py -v
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


client_mod = _load("reqogniloom_client_under_test", _PLUGIN_ROOT / "reqogniloom_client.py")


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
        result = client_mod.resolve_workspace_id(client, None)
        self.assertEqual(result, "ws-1")

    def test_raises_when_no_workspaces_visible(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = []
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, None)


class ConfigResolutionTests(unittest.TestCase):
    def test_defaults_when_env_unset(self) -> None:
        import os

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
        self.assertEqual(client.base_url, "http://example.test")  # trailing slash stripped
        self.assertEqual(client.api_key, "reqlo_abc")


if __name__ == "__main__":
    unittest.main()
