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
import json
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
        registered = {(sorted(route.methods)[0], route.path) for route in routes}
        self.assertEqual(
            registered,
            {
                ("GET", "/interviews"),
                ("GET", "/stats"),
                ("GET", "/version"),
                ("GET", "/workspaces"),
                ("GET", "/tools"),
                ("GET", "/tool/{tool_name:path}"),
                ("GET", "/servers"),
                ("POST", "/servers"),
                ("PATCH", "/servers/{server_id}"),
                ("DELETE", "/servers/{server_id}"),
                ("POST", "/servers/{server_id}/test"),
                ("POST", "/active"),
                ("GET", "/write-gate"),
                ("POST", "/write-gate"),
                ("POST", "/write/preview"),
                ("POST", "/write"),
            },
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


# --------------------------------------------------------------------------
# P2: servers, catalogue, write gate
# --------------------------------------------------------------------------

_WORKSPACE_UUID = "11111111-1111-1111-1111-111111111111"

_CATALOGUE = [
    {
        "name": "requirement.query",
        "description": "List requirements.",
        "inputSchema": {"type": "object", "properties": {"workspace_id": {"type": "string"}}},
    },
    {
        "name": "requirement.create",
        "description": "Create one.",
        "inputSchema": {
            "type": "object",
            "properties": {"workspace_id": {"type": "string"}, "title": {"type": "string"}},
            "required": ["workspace_id", "title"],
        },
    },
    {
        "name": "review.approve",
        "description": "Approve a proposal.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "workspace.delete",
        "description": "Delete a workspace.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
]


def _catalogue_client(*, user_key: bool = True, call_result: Any = None) -> MagicMock:
    """Client double with a tool catalogue and a recordable ``call_tool``."""
    fake = MagicMock()
    fake.base_url = "http://qs.test:8001"
    fake.server_id = "qs"
    fake.tools_list.return_value = [dict(tool) for tool in _CATALOGUE]
    fake.has_user_api_key.return_value = user_key
    fake.call_tool.return_value = {"created": "req-1"} if call_result is None else call_result
    return fake


class _CatalogueTestBase(unittest.TestCase):
    """Shared setup: isolated catalogue cache + registry + client double."""

    def setUp(self) -> None:
        plugin_api.tools.invalidate()
        self.addCleanup(plugin_api.tools.invalidate)
        self.fake_client = _catalogue_client()
        patcher = patch.object(plugin_api, "ReqogniLoomClient", return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _preview(self, tool: str, arguments: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        return plugin_api.write_preview({"tool": tool, "arguments": arguments, **extra})


class ServersApiTests(unittest.TestCase):
    def test_list_migrates_and_reports_the_registry(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_secret")
        result = plugin_api.list_servers()
        self.assertEqual(result["active"], "qs")
        self.assertEqual(result["servers"][0]["id"], "qs")
        self.assertNotIn("reqlo_secret", json.dumps(result))

    def test_add_probes_the_new_server_and_returns_health(self) -> None:
        fake = _catalogue_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake):
            result = plugin_api.add_server({"id": "qs", "base_url": "http://qs.test:8001"})
        self.assertEqual(result["server"]["id"], "qs")
        self.assertTrue(result["server"]["active"])
        self.assertIn("verify", result)

    def test_add_rejects_an_invalid_id(self) -> None:
        result = plugin_api.add_server({"id": "Bad Id", "base_url": "http://qs.test:8001"})
        self.assertIn("error", result)

    def test_patch_updates_without_echoing_a_key(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_old")
        result = plugin_api.update_server("qs", {"api_key": "reqlo_new", "name": "QS"})
        self.assertEqual(result["registry"]["servers"][0]["name"], "QS")
        self.assertNotIn("reqlo_new", json.dumps(result))
        self.assertEqual(plugin_api.registry.get_server("qs")["api_key"], "reqlo_new")

    def test_delete_removes_the_entry(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001")
        result = plugin_api.delete_server("qs")
        self.assertEqual(result["registry"]["servers"], [])

    def test_test_route_probes_one_server(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_a")
        fake = _catalogue_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake):
            result = plugin_api.test_server("qs")
        self.assertTrue(result["verify"]["reachable"])
        self.assertTrue(result["verify"]["auth_ok"])

    def test_test_route_on_an_unknown_server_is_an_error_not_a_crash(self) -> None:
        self.assertIn("error", plugin_api.test_server("ghost"))

    def test_switching_the_active_server_drops_the_catalogue_cache(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001")
        plugin_api.registry.add_server("prod", "http://prod.test:8001")
        plugin_api.tools.fetch_catalogue(_catalogue_client(), server_key="qs")
        with patch.object(plugin_api.tools, "invalidate") as invalidate:
            plugin_api.set_active_server({"server_id": "prod"})
        invalidate.assert_called_once_with()

    def test_write_gate_round_trip(self) -> None:
        self.assertTrue(plugin_api.read_write_gate()["write_gate"])
        self.assertFalse(plugin_api.set_write_gate({"enabled": False})["write_gate"])
        self.assertFalse(plugin_api.read_write_gate()["write_gate"])
        self.assertTrue(plugin_api.set_write_gate({"enabled": True})["write_gate"])


class ToolCatalogueApiTests(_CatalogueTestBase):
    def test_catalogue_is_served_with_classification(self) -> None:
        result = plugin_api.tool_catalogue()
        self.assertEqual(result["tool_count"], len(_CATALOGUE))
        by_name = {tool["name"]: tool for tool in result["tools"]}
        self.assertEqual(by_name["requirement.create"]["class"], "mutate")
        self.assertTrue(by_name["review.approve"]["requires_human"])
        self.assertTrue(by_name["workspace.delete"]["destructive"])
        self.assertEqual(by_name["requirement.query"]["class"], "read")

    def test_catalogue_second_call_is_cached(self) -> None:
        plugin_api.tool_catalogue()
        plugin_api.tool_catalogue()
        self.assertEqual(self.fake_client.tools_list.call_count, 1)

    def test_catalogue_refresh_bypasses_the_cache(self) -> None:
        plugin_api.tool_catalogue()
        plugin_api.tool_catalogue(refresh=1)
        self.assertEqual(self.fake_client.tools_list.call_count, 2)

    def test_tool_detail_serves_one_schema(self) -> None:
        result = plugin_api.tool_detail("requirement.create")
        self.assertEqual(result["tool"]["required"], ["workspace_id", "title"])

    def test_tool_detail_of_an_unknown_tool_is_an_error(self) -> None:
        self.assertIn("error", plugin_api.tool_detail("nope.nope"))

    def test_backend_failure_keeps_the_200_error_contract(self) -> None:
        self.fake_client.tools_list.side_effect = plugin_api.ReqogniLoomError("could not reach host")
        self.assertIn("error", plugin_api.tool_catalogue())


class WritePreviewTests(_CatalogueTestBase):
    def test_preview_issues_a_token_and_never_calls_the_tool(self) -> None:
        result = self._preview("requirement.create", {"workspace_id": _WORKSPACE_UUID, "title": "T"})
        self.assertEqual(result["risk"], "normal")
        self.assertEqual(len(result["confirm_token"]), 64)
        self.assertFalse(result["destructive"])
        self.assertIsNone(result["typed_confirmation"])
        self.assertEqual(result["problems"], [])
        self.fake_client.call_tool.assert_not_called()

    def test_preview_marks_destructive_calls_with_typed_confirmation(self) -> None:
        result = self._preview("workspace.delete", {"id": _WORKSPACE_UUID})
        self.assertEqual(result["risk"], "destructive")
        self.assertEqual(result["typed_confirmation"], "workspace.delete")
        self.assertTrue(result["blocked"] is False)

    def test_preview_reports_missing_required_arguments(self) -> None:
        result = self._preview("requirement.create", {"workspace_id": _WORKSPACE_UUID})
        self.assertEqual(result["problems"], ["missing required parameter 'title'"])

    def test_preview_flags_a_missing_human_key_for_approval_tools(self) -> None:
        self.fake_client.has_user_api_key.return_value = False
        result = self._preview("review.approve", {"id": "s-1"})
        self.assertTrue(result["requires_human"])
        self.assertFalse(result["human_key_available"])

    def test_preview_reports_a_closed_gate_as_blocked(self) -> None:
        plugin_api.registry.set_write_gate(False)
        result = self._preview("requirement.create", {"workspace_id": _WORKSPACE_UUID, "title": "T"})
        self.assertTrue(result["blocked"])
        self.assertFalse(result["write_gate"])

    def test_preview_without_a_tool_name_is_an_error(self) -> None:
        self.assertIn("error", plugin_api.write_preview({}))

    def test_preview_of_an_unknown_tool_is_an_error(self) -> None:
        self.assertIn("error", plugin_api.write_preview({"tool": "nope.nope", "arguments": {}}))


class WriteExecutionTests(_CatalogueTestBase):
    def _token(self, tool: str, arguments: Dict[str, Any]) -> str:
        return self._preview(tool, arguments)["confirm_token"]

    def test_write_executes_with_the_agent_principal(self) -> None:
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": "T"}
        result = plugin_api.write(
            {
                "tool": "requirement.create",
                "arguments": arguments,
                "confirm_token": self._token("requirement.create", arguments),
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["principal"], "agent")
        self.assertTrue(result["mutating"])
        self.fake_client.call_tool.assert_called_once_with(
            "requirement.create", arguments, principal="agent"
        )

    def test_write_routes_approval_tools_to_the_human_principal(self) -> None:
        arguments = {"id": "s-1"}
        result = plugin_api.write(
            {
                "tool": "review.approve",
                "arguments": arguments,
                "confirm_token": self._token("review.approve", arguments),
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["principal"], "user")
        self.fake_client.call_tool.assert_called_once_with("review.approve", arguments, principal="user")

    def test_write_refuses_when_the_human_key_is_missing(self) -> None:
        self.fake_client.has_user_api_key.return_value = False
        arguments = {"id": "s-1"}
        result = plugin_api.write(
            {
                "tool": "review.approve",
                "arguments": arguments,
                "confirm_token": self._token("review.approve", arguments),
            }
        )
        self.assertIn("human API key", result["error"])
        self.fake_client.call_tool.assert_not_called()

    def test_write_refuses_a_changed_argument_set(self) -> None:
        preview_token = self._token("requirement.create", {"workspace_id": _WORKSPACE_UUID, "title": "A"})
        result = plugin_api.write(
            {
                "tool": "requirement.create",
                "arguments": {"workspace_id": _WORKSPACE_UUID, "title": "B"},
                "confirm_token": preview_token,
            }
        )
        self.assertIn("confirmation mismatch", result["error"])
        self.fake_client.call_tool.assert_not_called()

    def test_write_refuses_a_skipped_preview(self) -> None:
        result = plugin_api.write({"tool": "requirement.create", "arguments": {}})
        self.assertIn("confirmation mismatch", result["error"])

    def test_write_refuses_while_the_gate_is_closed(self) -> None:
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": "T"}
        token = self._token("requirement.create", arguments)
        plugin_api.registry.set_write_gate(False)
        result = plugin_api.write(
            {"tool": "requirement.create", "arguments": arguments, "confirm_token": token}
        )
        self.assertIn("write gate is closed", result["error"])
        self.fake_client.call_tool.assert_not_called()

    def test_reads_are_not_gated(self) -> None:
        plugin_api.registry.set_write_gate(False)
        arguments = {"workspace_id": _WORKSPACE_UUID}
        result = plugin_api.write(
            {
                "tool": "requirement.query",
                "arguments": arguments,
                "confirm_token": self._token("requirement.query", arguments),
            }
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["mutating"])

    def test_destructive_call_requires_the_typed_name(self) -> None:
        arguments = {"id": _WORKSPACE_UUID}
        token = self._token("workspace.delete", arguments)
        result = plugin_api.write(
            {"tool": "workspace.delete", "arguments": arguments, "confirm_token": token}
        )
        self.assertIn("destructive call", result["error"])
        result_ok = plugin_api.write(
            {
                "tool": "workspace.delete",
                "arguments": arguments,
                "confirm_token": token,
                "typed": "workspace.delete",
            }
        )
        self.assertTrue(result_ok["ok"])

    def test_write_refuses_declared_validation_failures(self) -> None:
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": ""}
        result = plugin_api.write(
            {
                "tool": "requirement.create",
                "arguments": arguments,
                "confirm_token": self._token("requirement.create", arguments),
            }
        )
        self.assertIn("is empty", result["error"])

    def test_write_refuses_an_undeclared_parameter(self) -> None:
        # The backend accepts an undeclared workspace_id (finding #1376); the
        # plugin must not become the amplifier that sends it.
        arguments = {"id": "s-1", "workspace_id": _WORKSPACE_UUID}
        result = plugin_api.write(
            {
                "tool": "review.approve",
                "arguments": arguments,
                "confirm_token": self._token("review.approve", arguments),
            }
        )
        self.assertIn("unknown parameter", result["error"])

    def test_backend_failure_is_reported_as_error_not_raised(self) -> None:
        self.fake_client.call_tool.side_effect = plugin_api.ReqogniLoomError("PERMISSION_DENIED")
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": "T"}
        result = plugin_api.write(
            {
                "tool": "requirement.create",
                "arguments": arguments,
                "confirm_token": self._token("requirement.create", arguments),
            }
        )
        self.assertIn("PERMISSION_DENIED", result["error"])
        self.assertNotIn("ok", result)

    def test_write_remembers_the_workspace_per_server(self) -> None:
        plugin_api.registry.add_server("qs", "http://qs.test:8001")
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": "T"}
        plugin_api.write(
            {
                "tool": "requirement.create",
                "arguments": arguments,
                "confirm_token": self._token("requirement.create", arguments),
            }
        )
        self.assertEqual(plugin_api.registry.get_server("qs")["last_workspace_id"], _WORKSPACE_UUID)


@unittest.skipIf(TestClient is None, "fastapi.testclient is unavailable")
class WriteApiHttpTests(unittest.TestCase):
    """The write gate over real HTTP: body parsing, status codes, no 500."""

    def setUp(self) -> None:
        plugin_api.tools.invalidate()
        self.addCleanup(plugin_api.tools.invalidate)
        self.app = FastAPI()
        self.app.include_router(plugin_api.router, prefix="/api/plugins/reqogniloom")
        self.client = TestClient(self.app, base_url="http://localhost:8000")
        self.fake_client = _catalogue_client()
        patcher = patch.object(plugin_api, "ReqogniLoomClient", return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, path: str, body: Dict[str, Any]) -> Any:
        return self.client.post("/api/plugins/reqogniloom" + path, json=body)

    def test_preview_and_write_round_trip_over_http(self) -> None:
        arguments = {"workspace_id": _WORKSPACE_UUID, "title": "T"}
        preview = self._post("/write/preview", {"tool": "requirement.create", "arguments": arguments})
        self.assertEqual(preview.status_code, 200)
        token = preview.json()["confirm_token"]
        executed = self._post(
            "/write",
            {"tool": "requirement.create", "arguments": arguments, "confirm_token": token},
        )
        self.assertEqual(executed.status_code, 200)
        self.assertTrue(executed.json()["ok"])

    def test_write_without_a_body_is_an_error_not_a_500(self) -> None:
        response = self._post("/write", {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.json())

    def test_servers_and_gate_routes_answer_over_http(self) -> None:
        self.assertEqual(self.client.get("/api/plugins/reqogniloom/servers").status_code, 200)
        self.assertEqual(self.client.get("/api/plugins/reqogniloom/write-gate").status_code, 200)
        added = self._post("/servers", {"id": "qs", "base_url": "http://qs.test:8001"})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["server"]["id"], "qs")

    def test_tool_detail_with_a_dotted_name_resolves(self) -> None:
        response = self.client.get("/api/plugins/reqogniloom/tool/requirement.create")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tool"]["name"], "requirement.create")


if __name__ == "__main__":
    unittest.main()

