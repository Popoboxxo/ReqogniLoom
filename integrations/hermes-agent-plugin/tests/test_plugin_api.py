"""Unit tests for the dashboard backend (dashboard/plugin_api.py).

Run: python3 -m unittest tests/test_plugin_api.py -v

The plugin runs no inbound auth of its own: the host dashboard's own auth is the
only gate. There is therefore no credential to model — these tests prove that
every route serves data with no credential at all, and that a backend
``ReqogniLoomError`` keeps the 200 + ``{"error": …}`` contract.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception:  # ASGI-level assertions are optional.
    FastAPI = None  # type: ignore[assignment,misc]
    TestClient = None  # type: ignore[assignment,misc]


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# plugin_api.py inserts _PLUGIN_ROOT onto sys.path itself on import (to reach
# reqogniloom_client.py), so no extra package-loading trick is needed here.
plugin_api = _load("reqogniloom_plugin_api_under_test", _PLUGIN_ROOT / "dashboard" / "plugin_api.py")

_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
_WORKSPACE_NAME = "Confidential Workspace"
_COUNTS = {"requirements": 42, "testcases": 7, "open_interviews": 3}


def _fake_client() -> MagicMock:
    """A client returning deterministic data; no credential gates it any more."""
    fake = MagicMock()
    fake.list_workspaces.return_value = [{"id": _WORKSPACE_ID, "name": _WORKSPACE_NAME}]
    fake.stats.return_value = dict(_COUNTS, workspace_id=_WORKSPACE_ID)
    fake.version.return_value = {"app_version": "9.9.9"}
    fake.list_interviews.return_value = []
    return fake


class DashboardApiTests(unittest.TestCase):
    def test_handlers_are_sync_so_blocking_http_leaves_the_event_loop(self) -> None:
        # The client uses blocking urllib; FastAPI only runs sync path
        # operations in a worker threadpool, async ones on the event loop.
        for handler in (plugin_api.stats, plugin_api.workspaces, plugin_api.version, plugin_api.interviews):
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

    def test_stats_endpoint_surfaces_outbound_auth_failure_as_error(self) -> None:
        # A rejected *outbound* ReqogniLoom API key must reach the caller as
        # {"error": ...}, not as a 200 with a payload of nulls.
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

    def test_client_construction_failure_is_reported_not_raised(self) -> None:
        # An invalid REQOGNILOOM_BASE_URL fails in ReqogniLoomClient.__init__
        # (issue #1202 F5). The handlers must keep their 200+error contract, so
        # construction has to live inside their try/except ReqogniLoomError.
        constructor_error = plugin_api.ReqogniLoomError(
            "invalid REQOGNILOOM_BASE_URL 'ftp://nope': expected an http:// or https:// URL"
        )
        cases = (
            (plugin_api.stats, {"workspace_id": ""}),
            (plugin_api.workspaces, {}),
            (plugin_api.version, {}),
            (plugin_api.interviews, {"workspace_id": ""}),
        )
        for handler, kwargs in cases:
            failing_constructor = MagicMock(side_effect=constructor_error)
            with self.subTest(handler=handler.__name__), patch.object(
                plugin_api, "ReqogniLoomClient", failing_constructor
            ):
                result = handler(**kwargs)
            self.assertIn("error", result)
            self.assertIn("REQOGNILOOM_BASE_URL", result["error"])

    def test_interviews_endpoint_resolves_the_workspace_and_defaults_to_open(self) -> None:
        fake_client = _fake_client()
        fake_client.list_interviews.return_value = [{"id": "sess-1", "status": "in_progress"}]
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            payload = plugin_api.interviews(workspace_id="")
        self.assertEqual(payload["workspace_id"], _WORKSPACE_ID)
        self.assertEqual(payload["interviews"][0]["id"], "sess-1")
        fake_client.list_interviews.assert_called_once_with(_WORKSPACE_ID, "in_progress")

    def test_interviews_endpoint_reports_backend_errors_as_data(self) -> None:
        # Same contract as the other handlers: a backend failure is a 200 with an
        # "error" key, not a 500 the tab cannot render.
        fake_client = _fake_client()
        fake_client.list_interviews.side_effect = plugin_api.ReqogniLoomError("backend down")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            payload = plugin_api.interviews(workspace_id="")
        self.assertEqual(payload, {"error": "backend down"})


class InboundGateRemovedTests(unittest.TestCase):
    """The inbound auth mechanism is gone, not merely disabled."""

    def test_no_inbound_auth_symbols_remain(self) -> None:
        # The removed names are assembled here so that a repository-wide grep for
        # the token strings stays clean: the point of the assertion is that the
        # source no longer mentions them, so the test must not reintroduce them.
        removed = (
            "CREDENTIAL" + "_HEADER",
            "TOKEN" + "_ENV_VAR",
            "ALLOWED_ORIGINS" + "_ENV_VAR",
            "ALLOWED_HOSTS" + "_ENV_VAR",
            "DashboardAuth" + "Error",
            "enforce_dashboard" + "_auth",
            "_author" + "ize",
            "_require_dashboard" + "_auth",
            "_ROUTE" + "_DEPENDENCIES",
        )
        for name in removed:
            with self.subTest(name=name):
                self.assertFalse(hasattr(plugin_api, name))

    def test_source_has_no_token_references(self) -> None:
        source = (_PLUGIN_ROOT / "dashboard" / "plugin_api.py").read_text(encoding="utf-8")
        self.assertNotIn("DASHBOARD" + "_TOKEN", source)
        self.assertNotIn("X-ReqogniLoom-" + "Dashboard-Token", source)

    @unittest.skipUnless(
        hasattr(plugin_api.router, "routes"),
        "fastapi APIRouter unavailable — the stub router registers no routes",
    )
    def test_every_route_is_registered_without_a_dependency(self) -> None:
        routes = [route for route in plugin_api.router.routes if getattr(route, "path", "").startswith("/")]
        self.assertEqual(
            sorted(route.path for route in routes),
            ["/interviews", "/stats", "/version", "/workspaces"],
        )
        for route in routes:
            with self.subTest(path=route.path):
                self.assertEqual(list(route.dependencies), [])


@unittest.skipIf(TestClient is None, "fastapi.testclient is unavailable")
class DashboardApiHttpTests(unittest.TestCase):
    """ASGI-level proof that the mounted router serves without any credential."""

    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(plugin_api.router, prefix="/api/plugins/reqogniloom")
        self.client = TestClient(self.app, base_url="http://localhost:8000")
        self.fake_client = _fake_client()
        patcher = patch.object(plugin_api, "ReqogniLoomClient", return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(self, path: str, **headers: str) -> Any:
        return self.client.get("/api/plugins/reqogniloom" + path, headers=headers)

    def test_every_endpoint_answers_200_without_any_credential(self) -> None:
        # No header, no cookie, no query credential: the host dashboard's own
        # auth is the only gate, so the tab's own requests are served as-is.
        expected: Dict[str, Any] = {
            "/stats": lambda body: self.assertEqual(body["requirements"], _COUNTS["requirements"]),
            "/workspaces": lambda body: self.assertEqual(body["workspaces"][0]["id"], _WORKSPACE_ID),
            "/version": lambda body: self.assertEqual(body, {"app_version": "9.9.9"}),
            "/interviews": lambda body: self.assertEqual(body["interviews"], []),
        }
        for path, check in expected.items():
            with self.subTest(path=path):
                response = self._get(path)
                self.assertEqual(response.status_code, 200)
                check(response.json())

    def test_a_legacy_header_is_ignored_not_required(self) -> None:
        # An old client could still send the removed header; it must neither be
        # required nor change the answer. The name is assembled so the grep that
        # guards against reintroducing token handling stays clean.
        legacy_header = "X-ReqogniLoom-" + "Dashboard-Token"
        response = self._get("/version", **{legacy_header: "whatever"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"app_version": "9.9.9"})

    def test_backend_failure_still_uses_the_200_error_contract(self) -> None:
        self.fake_client.version.side_effect = plugin_api.ReqogniLoomError("could not reach host")
        response = self._get("/version")
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.json())


if __name__ == "__main__":
    unittest.main()
