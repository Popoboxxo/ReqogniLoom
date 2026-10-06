"""Unit tests for the dashboard backend (dashboard/plugin_api.py).

Run: python3 -m unittest tests/test_plugin_api.py -v
"""
from __future__ import annotations

import inspect
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
except Exception:  # ASGI-level assertions are optional; see DashboardAuthHttpTests.
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    TestClient = None  # type: ignore[assignment,misc]


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

# Not a credential: a fixed, obviously-fake value so the tests are deterministic.
_TEST_TOKEN = "test-dashboard-token"

# Sentinel data a leaking response would carry; the rejection tests assert it
# appears nowhere in the result.
_SECRET_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
_SECRET_WORKSPACE_NAME = "Confidential Workspace"
_SECRET_COUNTS = {"requirements": 42, "testcases": 7, "open_interviews": 3}


def _headers(**headers: str) -> Dict[str, str]:
    """Header mapping for the framework-free guard, valid credential included."""
    return {plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN, **headers}


def _request(**headers: str) -> SimpleNamespace:
    """A framework-free stand-in for the FastAPI ``Request`` the handlers read
    their headers from — anything exposing ``.headers`` behaves identically."""
    return SimpleNamespace(headers=_headers(**headers))


# The loopback authority the dashboard tab addresses. It is both the ``Host`` a
# browser always sends and the ``base_url`` the ASGI test client has to use, so
# the DNS-rebinding guard cannot reject the modelled request before the
# credential check gets its say.
_TAB_HOST = "localhost:8000"
_TAB_BASE_URL = "http://" + _TAB_HOST


def _tab_headers(token: Optional[str] = _TEST_TOKEN) -> Dict[str, str]:
    """The complete header set a same-origin GET from the dashboard tab sends.

    Mirrors the rewritten ``dist/index.js``, which calls
    ``window.fetch("/api/plugins/reqogniloom/<path>", { headers, credentials:
    "same-origin" })``, and deliberately nothing more:

    * ``Host`` — the loopback authority, always sent by the browser;
    * ``X-ReqogniLoom-Dashboard-Token`` — the shared secret the tab read from
      ``sessionStorage``, present only once the operator connected. ``token=None``
      models the not-yet-connected tab, which sends no credential header at all;
    * no ``Origin`` — browsers omit it on a same-origin GET, and
      ``_check_allowed_origin`` reads an absent one as a non-browser caller that
      the credential check alone has to hold in line;
    * no cookie — the host hands this plugin no credential, so
      ``credentials: "same-origin"`` has nothing of its own to attach and the
      header is the only credential the request carries.
    """
    headers: Dict[str, str] = {"Host": _TAB_HOST}
    if token is not None:
        headers[plugin_api.CREDENTIAL_HEADER] = token
    return headers


def _leaky_client() -> MagicMock:
    """A client that would hand over tenant data if it were ever reached."""
    fake = MagicMock()
    fake.list_workspaces.return_value = [{"id": _SECRET_WORKSPACE_ID, "name": _SECRET_WORKSPACE_NAME}]
    fake.stats.return_value = dict(_SECRET_COUNTS, workspace_id=_SECRET_WORKSPACE_ID)
    fake.version.return_value = {"app_version": "9.9.9"}
    fake.list_interviews.return_value = []
    return fake


def _assert_no_tenant_data(case: unittest.TestCase, exc: BaseException) -> None:
    """The rejection must expose no part of the tenant payload or the secret."""
    rendered = f"{exc} {exc!r} {getattr(exc, 'detail', '')}"
    for needle in (
        _SECRET_WORKSPACE_ID,
        _SECRET_WORKSPACE_NAME,
        _TEST_TOKEN,
        "requirements",
        "testcases",
        "workspaces",
    ):
        case.assertNotIn(needle, rendered)


class DashboardAuthTestCase(unittest.TestCase):
    """Base class: a valid token configured, allowlists cleared from the
    ambient environment, everything restored on teardown."""

    def setUp(self) -> None:
        self._env_patcher = patch.dict(os.environ, {plugin_api.TOKEN_ENV_VAR: _TEST_TOKEN}, clear=False)
        self._env_patcher.start()
        for name in (plugin_api.ALLOWED_ORIGINS_ENV_VAR, plugin_api.ALLOWED_HOSTS_ENV_VAR):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def assertAuthRejected(self, call: Any, status_code: int) -> str:
        """Assert ``call()`` is refused with ``status_code`` and that the refusal
        leaks neither tenant data nor the configured token.

        The framework-free guard raises :class:`DashboardAuthError`; where
        FastAPI is importable the handlers translate it into an ``HTTPException``
        carrying the same status, so both are accepted here.
        """
        rejections = (plugin_api.DashboardAuthError,) + (
            (HTTPException,) if HTTPException is not None else ()
        )
        try:
            result = call()
        except rejections as exc:
            self.assertEqual(getattr(exc, "status_code", None), status_code)
            _assert_no_tenant_data(self, exc)
            return str(getattr(exc, "detail", exc))
        self.fail(f"expected an auth rejection, got {result!r}")


class DashboardApiTests(DashboardAuthTestCase):
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
            result = plugin_api.stats(workspace_id="", request=_request())
        fake_client.stats.assert_called_once_with("ws-1")
        self.assertEqual(result["requirements"], 12)

    def test_stats_endpoint_reports_error_without_raising(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = []
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.stats(workspace_id="", request=_request())
        self.assertIn("error", result)

    def test_stats_endpoint_surfaces_auth_failure_as_error(self) -> None:
        # A rejected *outbound* ReqogniLoom API key must reach the caller as
        # {"error": ...}, not as a 200 with a payload of nulls. That is the
        # tenant-auth layer and is deliberately separate from the inbound gate.
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin_api.ReqogniLoomError("401: Invalid API key.")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.stats(workspace_id="", request=_request())
        self.assertIn("error", result)
        self.assertIn("401", result["error"])

    def test_stats_endpoint_uses_explicit_workspace_id(self) -> None:
        fake_client = MagicMock()
        fake_client.stats.return_value = {"workspace_id": "ws-explicit"}
        workspace_uuid = "22222222-2222-2222-2222-222222222222"
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            plugin_api.stats(workspace_id=workspace_uuid, request=_request())
        fake_client.stats.assert_called_once_with(workspace_uuid)
        fake_client.list_workspaces.assert_not_called()

    def test_workspaces_endpoint(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.return_value = [{"id": "ws-1", "name": "Demo"}]
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.workspaces(request=_request())
        self.assertEqual(result["workspaces"], [{"id": "ws-1", "name": "Demo"}])

    def test_workspaces_endpoint_reports_shape_failure_as_error(self) -> None:
        fake_client = MagicMock()
        fake_client.list_workspaces.side_effect = plugin_api.ReqogniLoomError("unexpected list response")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.workspaces(request=_request())
        self.assertIn("error", result)

    def test_version_endpoint(self) -> None:
        fake_client = MagicMock()
        fake_client.version.return_value = {"app_version": "1.7.0", "commit_short": "abc1234"}
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.version(request=_request())
        self.assertEqual(result["app_version"], "1.7.0")

    def test_version_endpoint_reports_error_without_raising(self) -> None:
        fake_client = MagicMock()
        fake_client.version.side_effect = plugin_api.ReqogniLoomError("could not reach host")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.version(request=_request())
        self.assertIn("error", result)


class InboundAuthGuardTests(DashboardAuthTestCase):
    """The framework-free guard: enforce_dashboard_auth(headers) -> None."""

    def test_valid_credential_is_accepted(self) -> None:
        self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers()))

    def test_credential_header_name_is_the_documented_one(self) -> None:
        self.assertEqual(plugin_api.CREDENTIAL_HEADER, "X-ReqogniLoom-Dashboard-Token")

    def test_credential_header_lookup_is_case_insensitive(self) -> None:
        headers = {plugin_api.CREDENTIAL_HEADER.lower(): _TEST_TOKEN}
        self.assertIsNone(plugin_api.enforce_dashboard_auth(headers))

    def test_missing_credential_is_rejected(self) -> None:
        with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
            plugin_api.enforce_dashboard_auth({"Origin": "http://localhost:3000"})
        self.assertEqual(ctx.exception.status_code, 401)
        _assert_no_tenant_data(self, ctx.exception)

    def test_empty_credential_is_rejected(self) -> None:
        for headers in (
            {plugin_api.CREDENTIAL_HEADER: ""},
            {plugin_api.CREDENTIAL_HEADER: "   "},
        ):
            with self.subTest(headers=headers), self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                plugin_api.enforce_dashboard_auth(headers)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_credential_is_rejected(self) -> None:
        with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
            plugin_api.enforce_dashboard_auth({plugin_api.CREDENTIAL_HEADER: "not-the-token"})
        self.assertEqual(ctx.exception.status_code, 401)
        _assert_no_tenant_data(self, ctx.exception)

    def test_credential_sharing_the_prefix_is_rejected(self) -> None:
        with self.assertRaises(plugin_api.DashboardAuthError):
            plugin_api.enforce_dashboard_auth({plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN + "x"})

    def test_unset_token_env_var_makes_the_gate_inert(self) -> None:
        # PLUG-12: the token is an OPT-IN second factor. Unset means the host
        # dashboard's own auth is the only gate, so a request with no credential
        # at all is let through — and nothing is inspected, not even the
        # allowlists (a foreign origin included).
        os.environ.pop(plugin_api.TOKEN_ENV_VAR, None)
        for headers in (
            None,
            {},
            _request().headers,
            {plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN},
            {"Origin": "http://evil.example", "Host": "evil.example"},
        ):
            with self.subTest(headers=headers):
                self.assertIsNone(plugin_api.enforce_dashboard_auth(headers))

    def test_blank_token_env_var_makes_the_gate_inert(self) -> None:
        # "" and "   " read exactly like unset: a whitespace value is a
        # configuration typo, not a credential.
        for value in ("", "   "):
            with self.subTest(value=value):
                os.environ[plugin_api.TOKEN_ENV_VAR] = value
                self.assertIsNone(plugin_api.enforce_dashboard_auth({}))

    def test_a_configured_token_restores_the_full_gate(self) -> None:
        # The opt-in must not weaken the configured case: with a token set, the
        # allowlists are consulted again and a credential is required.
        os.environ[plugin_api.TOKEN_ENV_VAR] = _TEST_TOKEN
        self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers()))
        with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
            plugin_api.enforce_dashboard_auth(_headers(Origin="http://evil.example"))
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
            plugin_api.enforce_dashboard_auth({})
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_mapping_header_source_is_rejected_not_raises(self) -> None:
        for headers in (None, "X-ReqogniLoom-Dashboard-Token: " + _TEST_TOKEN, object(), 42):
            with self.subTest(headers=headers), self.assertRaises(plugin_api.DashboardAuthError):
                plugin_api.enforce_dashboard_auth(headers)  # type: ignore[arg-type]

    def test_absent_origin_is_allowed_for_non_browser_callers(self) -> None:
        # The dashboard's own same-origin GET and curl both send no Origin;
        # the credential check alone holds those in line.
        self.assertIsNone(plugin_api.enforce_dashboard_auth({plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN}))

    def test_loopback_origins_are_allowed_by_default(self) -> None:
        for origin in (
            "http://localhost",
            "http://localhost:3000",
            "http://127.0.0.1:8001",
            "http://[::1]:8001",
        ):
            with self.subTest(origin=origin):
                self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers(Origin=origin)))

    def test_disallowed_origin_is_rejected(self) -> None:
        for origin in (
            "http://evil.example",
            "https://evil.example",
            "https://localhost:3000",
            "http://127.0.0.1.evil.example",
            "http://localhost.evil.example:3000",
        ):
            with self.subTest(origin=origin), self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                plugin_api.enforce_dashboard_auth(_headers(Origin=origin))
            self.assertEqual(ctx.exception.status_code, 403)

    def test_wildcard_and_null_origin_are_never_accepted(self) -> None:
        for origin in ("*", "null", ""):
            with self.subTest(origin=origin):
                if origin:
                    with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                        plugin_api.enforce_dashboard_auth(_headers(Origin=origin))
                    self.assertEqual(ctx.exception.status_code, 403)

    def test_configured_allowlist_is_honoured_and_narrows_the_default(self) -> None:
        os.environ[plugin_api.ALLOWED_ORIGINS_ENV_VAR] = "https://dashboard.example"
        self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers(Origin="https://dashboard.example")))
        with self.assertRaises(plugin_api.DashboardAuthError):
            plugin_api.enforce_dashboard_auth(_headers(Origin="http://localhost:3000"))

    def test_configured_allowlist_supports_a_port_wildcard(self) -> None:
        os.environ[plugin_api.ALLOWED_ORIGINS_ENV_VAR] = "http://localhost:*,https://dashboard.example:8443"
        allowed = (
            "http://localhost:1",
            "http://localhost:65535",
            "http://localhost",  # a "*" port covers the scheme's default port too
            "https://dashboard.example:8443",
        )
        for origin in allowed:
            with self.subTest(origin=origin):
                self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers(Origin=origin)))
        # An entry naming a port matches that port only — no implicit widening.
        for origin in ("https://dashboard.example", "https://dashboard.example:9999"):
            with self.subTest(origin=origin), self.assertRaises(plugin_api.DashboardAuthError):
                plugin_api.enforce_dashboard_auth(_headers(Origin=origin))

    def test_allowlist_cannot_be_widened_to_a_wildcard_host(self) -> None:
        for configured in ("*", "http://*", "http://*:*", ",,", "https://*"):
            with self.subTest(configured=configured):
                os.environ[plugin_api.ALLOWED_ORIGINS_ENV_VAR] = configured
                with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                    plugin_api.enforce_dashboard_auth(_headers(Origin="http://evil.example"))
                self.assertEqual(ctx.exception.status_code, 403)

    def test_userinfo_in_origin_is_rejected(self) -> None:
        for origin in ("http://localhost@evil.example", "http://user:pass@localhost:3000"):
            with self.subTest(origin=origin), self.assertRaises(plugin_api.DashboardAuthError):
                plugin_api.enforce_dashboard_auth(_headers(Origin=origin))

    def test_rebinding_host_header_is_rejected(self) -> None:
        for host in ("evil.example", "evil.example:8001", "localhost.evil.example", "10.0.0.5:8001"):
            with self.subTest(host=host), self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                plugin_api.enforce_dashboard_auth(_headers(Host=host))
            self.assertEqual(ctx.exception.status_code, 403)

    def test_loopback_hosts_are_allowed_by_default(self) -> None:
        for host in ("localhost", "localhost:8001", "127.0.0.1:8001", "[::1]:8001"):
            with self.subTest(host=host):
                self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers(Host=host)))

    def test_configured_host_allowlist_is_honoured(self) -> None:
        os.environ[plugin_api.ALLOWED_HOSTS_ENV_VAR] = "dashboard.example:8443"
        self.assertIsNone(plugin_api.enforce_dashboard_auth(_headers(Host="dashboard.example:8443")))
        with self.assertRaises(plugin_api.DashboardAuthError):
            plugin_api.enforce_dashboard_auth(_headers(Host="localhost:8001"))

    def test_non_ascii_credential_is_rejected_not_raising(self) -> None:
        # compare_digest raises TypeError on non-ASCII str operands, which
        # would surface as 500 instead of a 401 rejection.
        with self.assertRaises(plugin_api.DashboardAuthError) as ctx:
            plugin_api.enforce_dashboard_auth({plugin_api.CREDENTIAL_HEADER: "tökén-Ünicode"})
        self.assertEqual(ctx.exception.status_code, 401)

    def test_configured_token_is_never_echoed(self) -> None:
        for headers in ({}, {plugin_api.CREDENTIAL_HEADER: "wrong"}):
            with self.subTest(headers=headers), self.assertRaises(plugin_api.DashboardAuthError) as ctx:
                plugin_api.enforce_dashboard_auth(headers)
            self.assertNotIn(_TEST_TOKEN, str(ctx.exception))
            self.assertNotIn(_TEST_TOKEN, repr(ctx.exception))
            self.assertNotIn(_TEST_TOKEN, ctx.exception.detail)


class HandlerGuardTests(DashboardAuthTestCase):
    """The gate as seen by the handlers, which is what a direct call exercises."""

    def test_every_endpoint_rejects_a_request_without_a_credential(self) -> None:
        fake_client = _leaky_client()
        bare = SimpleNamespace(headers={})
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            for call in (
                lambda: plugin_api.stats(workspace_id="", request=bare),
                lambda: plugin_api.workspaces(request=bare),
                lambda: plugin_api.version(request=bare),
            ):
                self.assertAuthRejected(call, 401)
        # Nothing reached ReqogniLoom, so no tenant data can have leaked.
        fake_client.assert_not_called()
        fake_client.stats.assert_not_called()
        fake_client.list_workspaces.assert_not_called()
        fake_client.version.assert_not_called()

    def test_every_endpoint_rejects_an_omitted_request(self) -> None:
        fake_client = _leaky_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            for call in (
                lambda: plugin_api.stats(workspace_id=""),
                lambda: plugin_api.workspaces(),
                lambda: plugin_api.version(),
            ):
                self.assertAuthRejected(call, 401)
        fake_client.assert_not_called()

    def test_every_endpoint_rejects_a_wrong_credential(self) -> None:
        fake_client = _leaky_client()
        wrong = _request()
        wrong.headers[plugin_api.CREDENTIAL_HEADER] = "not-the-token"
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            self.assertAuthRejected(lambda: plugin_api.workspaces(request=wrong), 401)
        fake_client.assert_not_called()

    def test_every_endpoint_rejects_an_empty_credential(self) -> None:
        fake_client = _leaky_client()
        empty = _request()
        empty.headers[plugin_api.CREDENTIAL_HEADER] = ""
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            self.assertAuthRejected(lambda: plugin_api.version(request=empty), 401)
        fake_client.assert_not_called()

    def test_every_endpoint_serves_data_when_no_token_is_configured(self) -> None:
        # The opt-in case, end to end through the handlers: with no token in the
        # process environment the tab works out of the box (PLUG-12) instead of
        # answering 403 to its own requests.
        fake_client = _leaky_client()
        os.environ.pop(plugin_api.TOKEN_ENV_VAR, None)
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            self.assertEqual(
                plugin_api.stats(workspace_id="", request=_request())["requirements"],
                _SECRET_COUNTS["requirements"],
            )
            self.assertEqual(
                plugin_api.workspaces(request=_request())["workspaces"][0]["id"], _SECRET_WORKSPACE_ID
            )
            self.assertEqual(plugin_api.version(request=_request())["app_version"], "9.9.9")
            self.assertEqual(plugin_api.interviews(workspace_id="", request=_request())["interviews"], [])

    def test_interviews_endpoint_resolves_the_workspace_and_defaults_to_open(self) -> None:
        fake_client = _leaky_client()
        fake_client.list_interviews.return_value = [{"id": "sess-1", "status": "in_progress"}]
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            payload = plugin_api.interviews(workspace_id="", request=_request())
        self.assertEqual(payload["workspace_id"], _SECRET_WORKSPACE_ID)
        self.assertEqual(payload["interviews"][0]["id"], "sess-1")
        fake_client.list_interviews.assert_called_once_with(_SECRET_WORKSPACE_ID, "in_progress")

    def test_interviews_endpoint_reports_backend_errors_as_data(self) -> None:
        # Same contract as the other handlers: a backend failure is a 200 with an
        # "error" key, not a 500 the tab cannot render.
        fake_client = _leaky_client()
        fake_client.list_interviews.side_effect = plugin_api.ReqogniLoomError("backend down")
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            payload = plugin_api.interviews(workspace_id="", request=_request())
        self.assertEqual(payload, {"error": "backend down"})

    def test_every_endpoint_rejects_a_disallowed_origin(self) -> None:
        fake_client = _leaky_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            for call in (
                lambda: plugin_api.stats(workspace_id="", request=_request(Origin="http://evil.example")),
                lambda: plugin_api.workspaces(request=_request(Origin="*")),
                lambda: plugin_api.version(request=_request(Origin="null")),
            ):
                self.assertAuthRejected(call, 403)
        fake_client.assert_not_called()

    def test_valid_credential_returns_the_endpoints_normal_data(self) -> None:
        fake_client = _leaky_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            stats_result = plugin_api.stats(workspace_id="", request=_request())
            workspaces_result = plugin_api.workspaces(request=_request())
            version_result = plugin_api.version(request=_request())
        self.assertEqual(stats_result["requirements"], _SECRET_COUNTS["requirements"])
        self.assertEqual(
            workspaces_result["workspaces"],
            [{"id": _SECRET_WORKSPACE_ID, "name": _SECRET_WORKSPACE_NAME}],
        )
        self.assertEqual(version_result["app_version"], "9.9.9")

    def test_valid_credential_with_a_loopback_origin_is_accepted(self) -> None:
        fake_client = _leaky_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            result = plugin_api.workspaces(request=_request(Origin="http://localhost:3000", Host="localhost:3000"))
        self.assertEqual(result["workspaces"][0]["id"], _SECRET_WORKSPACE_ID)

    def test_auth_failure_is_not_degraded_to_a_200_error_body(self) -> None:
        # The 200+{"error": …} contract belongs to ReqogniLoomError, the
        # tenant-auth layer; an inbound auth failure must never use it.
        fake_client = _leaky_client()
        with patch.object(plugin_api, "ReqogniLoomClient", return_value=fake_client):
            for call in (
                lambda: plugin_api.stats(workspace_id="", request=SimpleNamespace(headers={})),
                lambda: plugin_api.workspaces(request=SimpleNamespace(headers={})),
                lambda: plugin_api.version(request=SimpleNamespace(headers={})),
            ):
                detail = self.assertAuthRejected(call, 401)
                self.assertNotIn("error", detail)

    @unittest.skipUnless(
        hasattr(plugin_api.router, "routes"),
        "fastapi APIRouter unavailable — the stub router registers no routes",
    )
    def test_every_route_is_registered_with_the_auth_dependency(self) -> None:
        routes = [route for route in plugin_api.router.routes if getattr(route, "path", "").startswith("/")]
        self.assertEqual(
            sorted(route.path for route in routes),
            ["/interviews", "/stats", "/version", "/workspaces"],
        )
        for route in routes:
            with self.subTest(path=route.path):
                calls = [dep.dependency for dep in route.dependencies]
                self.assertIn(plugin_api._require_dashboard_auth, calls)


@unittest.skipIf(TestClient is None, "fastapi.testclient is unavailable")
class DashboardAuthHttpTests(DashboardAuthTestCase):
    """ASGI-level proof that the mounted router answers 401/403, not 200."""

    def setUp(self) -> None:
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(plugin_api.router, prefix="/api/plugins/reqogniloom")
        # base_url fixes the Host header to loopback so the DNS-rebinding
        # guard does not reject the test client before the credential check.
        self.client = TestClient(self.app, base_url="http://localhost:8000")
        self.fake_client = _leaky_client()
        patcher = patch.object(plugin_api, "ReqogniLoomClient", return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(self, path: str, **headers: str) -> Any:
        return self.client.get("/api/plugins/reqogniloom" + path, headers=headers)

    def test_all_three_endpoints_answer_401_without_a_credential(self) -> None:
        for path in ("/stats", "/workspaces", "/version"):
            with self.subTest(path=path):
                response = self._get(path)
                self.assertEqual(response.status_code, 401)

    def test_all_three_endpoints_answer_401_for_a_wrong_credential(self) -> None:
        for path in ("/stats", "/workspaces", "/version"):
            with self.subTest(path=path):
                response = self._get(path, **{plugin_api.CREDENTIAL_HEADER: "not-the-token"})
                self.assertEqual(response.status_code, 401)

    def test_all_endpoints_answer_200_when_the_token_env_var_is_unset(self) -> None:
        # PLUG-12: no configured token ⇒ no second factor, so the tab gets its
        # data instead of a 403 it cannot fix from the browser.
        os.environ.pop(plugin_api.TOKEN_ENV_VAR, None)
        for path in ("/stats", "/workspaces", "/version", "/interviews"):
            with self.subTest(path=path):
                response = self._get(path, **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN})
                self.assertEqual(response.status_code, 200)

    def test_rejection_response_carries_no_tenant_data(self) -> None:
        for headers in ({}, {plugin_api.CREDENTIAL_HEADER: "not-the-token"}):
            with self.subTest(headers=headers):
                response = self._get("/workspaces", **headers)
                self.assertEqual(response.status_code, 401)
                body = response.text
                for needle in (_SECRET_WORKSPACE_ID, _SECRET_WORKSPACE_NAME, _TEST_TOKEN):
                    self.assertNotIn(needle, body)
        self.fake_client.assert_not_called()

    def test_rejection_is_not_a_200_error_body(self) -> None:
        response = self._get("/stats")
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("error", response.json())

    def test_valid_credential_returns_200_with_data(self) -> None:
        response = self._get("/version", **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"app_version": "9.9.9"})

    def test_valid_credential_with_a_loopback_origin_returns_200(self) -> None:
        response = self._get(
            "/stats",
            **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN, "Origin": "http://localhost:3000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requirements"], _SECRET_COUNTS["requirements"])

    def test_disallowed_origin_answers_403(self) -> None:
        for origin in ("http://evil.example", "*", "null", "https://localhost:3000"):
            with self.subTest(origin=origin):
                response = self._get(
                    "/version",
                    **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN, "Origin": origin},
                )
                self.assertEqual(response.status_code, 403)

    def test_rebinding_host_answers_403(self) -> None:
        response = self._get(
            "/version",
            **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN, "Host": "evil.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_backend_failure_still_uses_the_200_error_contract(self) -> None:
        # ReqogniLoomError keeps its original contract; only the inbound gate
        # was changed to 401/403 semantics.
        self.fake_client.version.side_effect = plugin_api.ReqogniLoomError("could not reach host")
        response = self._get("/version", **{plugin_api.CREDENTIAL_HEADER: _TEST_TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.json())


@unittest.skipIf(TestClient is None, "fastapi.testclient is unavailable")
class DashboardTabRequestShapeTests(DashboardAuthTestCase):
    """The request the rewritten dashboard tab actually sends, end to end.

    The two paths under test are ``/stats`` and ``/version`` — the pair
    ``dist/index.js`` fetches in parallel from its ``load()``.

    LIMIT, stated rather than worked around: this harness is handed a header
    mapping and nothing else. It can prove the SERVER contract for the shape the
    tab sends (loopback ``Host``, credential header, no ``Origin``, no cookie)
    and that the server keeps the tab's failure modes distinguishable — it
    cannot observe a browser, so it proves nothing about whether the tab really
    attaches that header on a live request. No JS harness in this repo reaches
    that bundle (``node --check`` is the only check that does), and standing one
    up here would test a stub of the tab rather than the tab. The tab side stays
    a browser check; what is pinned below is that the server answers the tab's
    shape with 200/401/403 and says which of the three happened.
    """

    def setUp(self) -> None:
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(plugin_api.router, prefix="/api/plugins/reqogniloom")
        # The tab addresses the dashboard by loopback, so base_url pins Host the
        # same way the tab's own request does.
        self.client = TestClient(self.app, base_url=_TAB_BASE_URL)
        self.fake_client = _leaky_client()
        patcher = patch.object(plugin_api, "ReqogniLoomClient", return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        # A deliberately gate-free diagnostic route, registered outside the
        # plugin prefix: it has to report the headers the ASGI server actually
        # received, including for a request the gate would reject.
        self.app.add_api_route("/_probe", self._echo_headers, methods=["GET"])

    def _echo_headers(self, request: plugin_api.Request) -> Dict[str, str]:
        """Report the received headers verbatim (names arrive lowercased).

        ``plugin_api.Request`` is ``fastapi.Request`` whenever the TestClient is
        importable, which is exactly when this class runs — reusing it avoids a
        second import of the same class.
        """
        return {name: value for name, value in request.headers.items()}

    def _get(self, path: str, headers: Dict[str, str]) -> Any:
        """One GET in the tab's shape, against the mounted plugin prefix."""
        return self.client.get("/api/plugins/reqogniloom" + path, headers=headers)

    def _seen_headers(self) -> Dict[str, str]:
        """What the diagnostic route reports for one tab-shaped request."""
        return self.client.get("/_probe", headers=_tab_headers()).json()

    def test_tab_shape_reaches_the_gate_as_modelled(self) -> None:
        # Measured, not assumed: if the harness did not really deliver the tab's
        # shape, every other assertion in this class would be about a fiction.
        seen = self._seen_headers()
        self.assertEqual(seen.get("host"), _TAB_HOST)
        self.assertNotIn("origin", seen)
        self.assertNotIn("cookie", seen)
        self.assertEqual(seen.get(plugin_api.CREDENTIAL_HEADER.lower()), _TEST_TOKEN)

    def test_tab_shape_answers_200_with_data(self) -> None:
        stats = self._get("/stats", _tab_headers())
        version = self._get("/version", _tab_headers())
        self.assertEqual((stats.status_code, version.status_code), (200, 200))
        self.assertEqual(stats.json()["requirements"], _SECRET_COUNTS["requirements"])
        self.assertEqual(version.json(), {"app_version": "9.9.9"})

    def test_tab_shape_without_the_credential_header_answers_401_missing(self) -> None:
        # The regression that shipped: the tab reached the API carrying no header
        # at all. It has to stay a 401 that NAMES the header — dist/index.js
        # branches on the literal "missing" and echoes the header name back to
        # the operator, so a generic "unauthorized" would misdirect the fix at
        # the token instead of at the host that dropped it.
        for path in ("/stats", "/version"):
            with self.subTest(path=path):
                response = self._get(path, _tab_headers(token=None))
                self.assertEqual(response.status_code, 401)
                detail = response.json()["detail"]
                self.assertIn("missing", detail)
                self.assertIn(plugin_api.CREDENTIAL_HEADER, detail)
                _assert_no_tenant_data(self, SimpleNamespace(detail=detail))
        self.fake_client.assert_not_called()

    def test_tab_shape_with_a_wrong_credential_answers_401_invalid(self) -> None:
        # The other 401. The tab's describeFailure() falls through to
        # "disconnect and re-enter the token" here, so this detail must not
        # claim the header is missing.
        for path in ("/stats", "/version"):
            with self.subTest(path=path):
                response = self._get(path, _tab_headers(token="not-the-token"))
                self.assertEqual(response.status_code, 401)
                detail = response.json()["detail"]
                self.assertNotIn(plugin_api.CREDENTIAL_HEADER, detail)
                self.assertNotIn("missing", detail)
                _assert_no_tenant_data(self, SimpleNamespace(detail=detail))
        self.fake_client.assert_not_called()

    def test_a_dropped_header_is_told_apart_from_a_wrong_credential(self) -> None:
        # What the tab has to be able to say: "the host never forwarded the
        # header" vs "that token is wrong". Both are 401, so the status alone
        # cannot carry the difference — only a detail naming the header can.
        missing = self._get("/stats", _tab_headers(token=None)).json()["detail"]
        wrong = self._get("/stats", _tab_headers(token="not-the-token")).json()["detail"]
        self.assertNotEqual(missing, wrong)
        self.assertIn(plugin_api.CREDENTIAL_HEADER, missing)
        self.assertNotIn(plugin_api.CREDENTIAL_HEADER, wrong)

    def test_tab_shape_answers_200_when_no_token_is_configured(self) -> None:
        # The regression that made the tab unusable: an unset token used to be a
        # 403 for every request the tab made, with no way for the operator to fix
        # it from the browser. With the gate opt-in (PLUG-12) the tab loads.
        os.environ.pop(plugin_api.TOKEN_ENV_VAR, None)
        for path in ("/stats", "/version"):
            with self.subTest(path=path):
                response = self._get(path, _tab_headers())
                self.assertEqual(response.status_code, 200)

    def test_a_cookie_does_not_authenticate_the_tab_shape(self) -> None:
        # credentials: "same-origin" would attach a cookie if the host set one.
        # This host sets none, and a cookie must never become an alternative way
        # in: without the header the request is rejected whatever the jar holds.
        response = self._get(
            "/stats",
            {"Host": _TAB_HOST, "Cookie": "hermes_dashboard_session=8f14e45fceea167a5a36dedd4bea2543"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(plugin_api.CREDENTIAL_HEADER, response.json()["detail"])
        self.fake_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
