"""Unit tests for reqogniloom_client.py.

Run: python3 -m unittest tests/test_reqogniloom_client.py -v
"""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from typing import Self

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


client_mod = _load("reqogniloom_client_under_test", _PLUGIN_ROOT / "reqogniloom_client.py")

_API_KEY = "reqlo_test_key"
_BASE_URL = "http://api.test"

#: The three endpoints ``stats()`` hits, in call order.
_STATS_PATHS = ("/api/v1/interviews/", "/api/v1/requirements/", "/api/v1/testcases/")


class _FakeResponse:
    """Stand-in for the response object ``urlopen`` returns."""

    def __init__(self, body: bytes = b"", read_error: Optional[BaseException] = None) -> None:
        self._body = body
        self._read_error = read_error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body


class _Routes:
    """Answers requests from a path -> payload map, recording every request.

    ``errors`` maps a path to an exception raised instead of a response, so a
    test can make one endpoint fail while the others succeed.
    """

    def __init__(self, routes: Dict[str, Any], errors: Optional[Dict[str, BaseException]] = None) -> None:
        self.routes = routes
        self.errors = errors or {}
        self.requests: List[urllib.request.Request] = []
        self.timeouts: List[Optional[float]] = []

    def __call__(self, req: urllib.request.Request, timeout: Optional[float] = None) -> _FakeResponse:
        self.requests.append(req)
        self.timeouts.append(timeout)
        parts = urllib.parse.urlsplit(req.full_url)
        path = parts.path
        # Exact query-inclusive key wins (needed to serve page=2 differently
        # from page=1); a bare path key still matches, so existing fixtures
        # that ignore the query string keep working.
        key = f"{path}?{parts.query}" if parts.query else path
        for candidate in (key, path):
            if candidate in self.errors:
                raise self.errors[candidate]
        if key in self.routes:
            route = self.routes[key]
        elif path in self.routes:
            route = self.routes[path]
        else:
            raise AssertionError(f"unexpected request path: {key}")
        return _FakeResponse(json.dumps(route).encode("utf-8"))


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=f"{_BASE_URL}/whatever/",
        code=code,
        msg="boom",
        hdrs=email.message.Message(),
        fp=io.BytesIO(body.encode("utf-8")),
    )


def _client(**kwargs: Any) -> Any:
    kwargs.setdefault("api_key", _API_KEY)
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL, **kwargs)


def _page(count: Optional[int], items: int) -> Dict[str, Any]:
    """A DRF page envelope: ``count`` total, ``items`` results on this page."""
    page: Dict[str, Any] = {"results": [{"id": f"row-{i}"} for i in range(items)]}
    if count is not None:
        page["count"] = count
    return page


class _NoApiKeyEnv:
    """Clears REQOGNILOOM_API_KEY for the duration of a test."""

    def __enter__(self) -> None:
        self._backup = os.environ.pop("REQOGNILOOM_API_KEY", None)

    def __exit__(self, *exc_info: object) -> None:
        if self._backup is not None:
            os.environ["REQOGNILOOM_API_KEY"] = self._backup


class _BaseUrlEnv:
    """Sets ``REQOGNILOOM_BASE_URL`` for a test; passing ``None`` unsets it."""

    def __init__(self, value: str | None) -> None:
        self._value = value

    def __enter__(self) -> None:
        self._backup = os.environ.pop("REQOGNILOOM_BASE_URL", None)
        if self._value is not None:
            os.environ["REQOGNILOOM_BASE_URL"] = self._value

    def __exit__(self, *exc_info: object) -> None:
        if self._backup is None:
            os.environ.pop("REQOGNILOOM_BASE_URL", None)
        else:
            os.environ["REQOGNILOOM_BASE_URL"] = self._backup


def _keyless_client() -> Any:
    return client_mod.ReqogniLoomClient(base_url=_BASE_URL)


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

    def test_workspace_entry_without_id_raises_reqogniloom_error(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = [{"name": "Demo"}]
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.resolve_workspace_id(client, None)
        self.assertIn("malformed", str(ctx.exception).lower())

    def test_workspace_entry_with_empty_id_raises_reqogniloom_error(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = [{"id": ""}]
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, None)

    def test_non_dict_workspace_entry_raises_reqogniloom_error(self) -> None:
        client = MagicMock()
        client.list_workspaces.return_value = ["ws-1"]
        with self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.resolve_workspace_id(client, None)


class ConfigResolutionTests(unittest.TestCase):
    def test_defaults_when_env_unset(self) -> None:
        # The default is intentionally unchanged (issue #1202 F5): local dev and
        # existing configs keep working. Only the failure path became loud.
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

    def test_empty_base_url_env_is_rejected(self) -> None:
        with _BaseUrlEnv(""), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.ReqogniLoomClient()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("''", message)  # names the offending (empty) value

    def test_whitespace_base_url_env_is_rejected(self) -> None:
        with _BaseUrlEnv("   "), self.assertRaises(client_mod.ReqogniLoomError):
            client_mod.ReqogniLoomClient()

    def test_non_http_base_url_env_is_rejected(self) -> None:
        with _BaseUrlEnv("ftp://example.test"), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client_mod.ReqogniLoomClient()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("ftp://example.test", message)

    def test_explicit_non_http_base_url_is_rejected(self) -> None:
        with self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.ReqogniLoomClient(base_url="localhost:8001")
        self.assertIn("localhost:8001", str(ctx.exception))


class TransportFailureTests(unittest.TestCase):
    def test_read_timeout_becomes_reqogniloom_error(self) -> None:
        # A socket timeout while reading the body is a bare TimeoutError/
        # OSError: urlopen only wraps send-side failures in URLError.
        response = _FakeResponse(read_error=TimeoutError("timed out"))
        with patch("urllib.request.urlopen", return_value=response), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("timed out", str(ctx.exception))
        self.assertIn("/api/v1/workspaces/", str(ctx.exception))

    def test_connection_reset_while_reading_becomes_reqogniloom_error(self) -> None:
        response = _FakeResponse(read_error=ConnectionResetError("connection reset by peer"))
        with patch("urllib.request.urlopen", return_value=response), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("connection reset by peer", str(ctx.exception))

    def test_timeout_comes_from_module_constant(self) -> None:
        routes = _Routes({"/api/v1/version/": {"app_version": "1.7.0"}})
        with patch("urllib.request.urlopen", routes):
            _client().version()
        self.assertEqual(routes.timeouts, [client_mod.REQUEST_TIMEOUT_SECONDS])

    def test_http_error_still_reports_code_and_body(self) -> None:
        error = _http_error(404, '{"detail":"Not found."}')
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertEqual(str(ctx.exception), '404: {"detail":"Not found."}')

    def test_server_error_still_reports_code_and_body(self) -> None:
        error = _http_error(500, "upstream exploded")
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertEqual(str(ctx.exception), "500: upstream exploded")

    def test_unreachable_host_reports_reason(self) -> None:
        error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        self.assertIn("could not reach", str(ctx.exception))

    def test_default_target_failure_names_env_var_and_default(self) -> None:
        # No REQOGNILOOM_BASE_URL and no explicit base_url: the request silently
        # went to the local default, so the error must say exactly that.
        error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with _BaseUrlEnv(None), patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client_mod.ReqogniLoomClient(api_key=_API_KEY).list_workspaces()
        message = str(ctx.exception)
        self.assertIn("could not reach", message)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("http://localhost:8001", message)
        self.assertIn("default", message)

    def test_default_target_read_failure_names_env_var_too(self) -> None:
        # The read-side OSError branch gets the same hint as the send-side one.
        response = _FakeResponse(read_error=TimeoutError("timed out"))
        with _BaseUrlEnv(None), patch("urllib.request.urlopen", return_value=response), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            client_mod.ReqogniLoomClient(api_key=_API_KEY).list_workspaces()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_BASE_URL", message)
        self.assertIn("http://localhost:8001", message)

    def test_configured_target_failure_has_no_default_hint(self) -> None:
        # A reachable-but-misconfigured instance must not get the misleading
        # "you forgot REQOGNILOOM_BASE_URL" hint.
        error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with _BaseUrlEnv(None), patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().list_workspaces()
        message = str(ctx.exception)
        self.assertIn("could not reach", message)
        self.assertNotIn("REQOGNILOOM_BASE_URL", message)
        self.assertNotIn("default", message)

    def test_non_json_body_becomes_reqogniloom_error(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse(b"<html>nope</html>")), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _client().version()
        self.assertIn("non-JSON", str(ctx.exception))


class ResponseShapeTests(unittest.TestCase):
    def test_list_workspaces_accepts_bare_array(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": [{"id": "ws-1"}]})
        with patch("urllib.request.urlopen", routes):
            self.assertEqual(_client().list_workspaces(), [{"id": "ws-1"}])

    def test_list_workspaces_accepts_paginated_object(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": _page(2, 2)})
        with patch("urllib.request.urlopen", routes):
            self.assertEqual(len(_client().list_workspaces()), 2)

    def test_dict_without_results_raises_instead_of_returning_empty(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": {"detail": "Invalid token."}})
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().list_workspaces()
        self.assertIn("unexpected list response", str(ctx.exception))

    def test_json_null_body_raises(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": None})
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError):
            _client().list_workspaces()

    def test_empty_body_raises(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse(b"")), self.assertRaises(
            client_mod.ReqogniLoomError
        ):
            _client().list_workspaces()

    def test_list_interviews_rejects_dict_without_results(self) -> None:
        routes = _Routes({"/api/v1/interviews/": {"detail": "Invalid token."}})
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError):
            _client().list_interviews("ws-1", status="in_progress")

    def test_list_interviews_accepts_bare_array(self) -> None:
        routes = _Routes({"/api/v1/interviews/": [{"id": "sess-1"}]})
        with patch("urllib.request.urlopen", routes):
            self.assertEqual(_client().list_interviews("ws-1", status="in_progress"), [{"id": "sess-1"}])

    def test_shaped_failure_surfaces_through_resolve_workspace_id(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": {"detail": "Invalid token."}})
        client = _client()
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            client_mod.resolve_workspace_id(client, None)
        self.assertIn("unexpected list response", str(ctx.exception))


class PaginationTests(unittest.TestCase):
    def test_list_workspaces_follows_next_across_pages(self) -> None:
        routes = _Routes(
            {
                "/api/v1/workspaces/": {
                    "count": 3,
                    "next": f"{_BASE_URL}/api/v1/workspaces/?page=2",
                    "previous": None,
                    "results": [{"id": "ws-1"}, {"id": "ws-2"}],
                },
                "/api/v1/workspaces/?page=2": {
                    "count": 3,
                    "next": None,
                    "previous": None,
                    "results": [{"id": "ws-3"}],
                },
            }
        )
        with patch("urllib.request.urlopen", routes):
            workspaces = _client().list_workspaces()
        self.assertEqual([w["id"] for w in workspaces], ["ws-1", "ws-2", "ws-3"])
        self.assertEqual(len(routes.requests), 2)

    def test_list_interviews_follows_next_across_pages(self) -> None:
        first = "/api/v1/interviews/?workspace_id=ws-1&status=in_progress"
        second = "/api/v1/interviews/?workspace_id=ws-1&status=in_progress&page=2"
        routes = _Routes(
            {
                first: {
                    "count": 2,
                    "next": f"{_BASE_URL}{second}",
                    "previous": None,
                    "results": [{"id": "sess-1"}],
                },
                second: {
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [{"id": "sess-2"}],
                },
            }
        )
        with patch("urllib.request.urlopen", routes):
            sessions = _client().list_interviews("ws-1", status="in_progress")
        self.assertEqual([s["id"] for s in sessions], ["sess-1", "sess-2"])

    def test_list_workspaces_stops_on_repeated_next(self) -> None:
        loop_url = f"{_BASE_URL}/api/v1/workspaces/?page=2"
        routes = _Routes(
            {
                "/api/v1/workspaces/": {
                    "count": 2,
                    "next": loop_url,
                    "previous": None,
                    "results": [{"id": "ws-1"}],
                },
                "/api/v1/workspaces/?page=2": {
                    "count": 2,
                    "next": loop_url,
                    "previous": None,
                    "results": [{"id": "ws-2"}],
                },
            }
        )
        with patch("urllib.request.urlopen", routes):
            workspaces = _client().list_workspaces()
        self.assertEqual([w["id"] for w in workspaces], ["ws-1", "ws-2"])
        self.assertEqual(len(routes.requests), 2)


class ApiKeyTests(unittest.TestCase):
    def test_missing_key_fails_before_any_request_is_sent(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": _page(0, 0)})
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", routes), self.assertRaises(
            client_mod.ReqogniLoomError
        ) as ctx:
            _keyless_client().list_workspaces()
        message = str(ctx.exception)
        self.assertIn("REQOGNILOOM_API_KEY", message)
        self.assertIn("reqlo_", message)
        self.assertEqual(routes.requests, [])

    def test_missing_key_does_not_degrade_stats_to_nulls(self) -> None:
        routes = _Routes({path: _page(1, 1) for path in _STATS_PATHS})
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", routes), self.assertRaises(
            client_mod.ReqogniLoomError
        ):
            _keyless_client().stats("ws-1")
        self.assertEqual(routes.requests, [])

    def test_version_still_works_without_a_key_and_sends_no_authorization(self) -> None:
        routes = _Routes({"/api/v1/version/": {"app_version": "1.7.0"}})
        with _NoApiKeyEnv(), patch("urllib.request.urlopen", routes):
            self.assertEqual(_keyless_client().version(), {"app_version": "1.7.0"})
        self.assertIsNone(routes.requests[0].get_header("Authorization"))

    def test_rejected_key_propagates_from_list_workspaces(self) -> None:
        routes = _Routes({}, errors={"/api/v1/workspaces/": _http_error(401, "Invalid API key.")})
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().list_workspaces()
        self.assertEqual(str(ctx.exception), "401: Invalid API key.")

    def test_rejected_key_propagates_from_stats_instead_of_null_payload(self) -> None:
        denied = {path: _http_error(401, "Invalid API key.") for path in _STATS_PATHS}
        routes = _Routes({}, errors=denied)
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError) as ctx:
            _client().stats("ws-1")
        self.assertIn("401", str(ctx.exception))

    def test_forbidden_key_propagates_from_stats(self) -> None:
        denied = {path: _http_error(403, "Forbidden.") for path in _STATS_PATHS}
        routes = _Routes({}, errors=denied)
        with patch("urllib.request.urlopen", routes), self.assertRaises(client_mod.ReqogniLoomError):
            _client().stats("ws-1")

    def test_authorized_request_sends_bearer_token(self) -> None:
        routes = _Routes({"/api/v1/workspaces/": _page(0, 0)})
        with patch("urllib.request.urlopen", routes):
            _client().list_workspaces()
        self.assertEqual(routes.requests[0].get_header("Authorization"), f"Bearer {_API_KEY}")


class StatsTests(unittest.TestCase):
    def test_count_comes_from_drf_count_not_page_length(self) -> None:
        routes = _Routes(
            {
                "/api/v1/requirements/": _page(500, 25),
                "/api/v1/testcases/": _page(120, 25),
                "/api/v1/interviews/": _page(7, 3),
            }
        )
        with patch("urllib.request.urlopen", routes):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 500)
        self.assertEqual(stats["testcases"], 120)
        self.assertEqual(stats["open_interviews"], 7)

    def test_missing_count_yields_none_not_page_length(self) -> None:
        routes = _Routes(
            {
                "/api/v1/requirements/": _page(None, 25),
                "/api/v1/testcases/": {"results": []},
                "/api/v1/interviews/": {"results": [{"id": "sess-1"}]},
            }
        )
        with patch("urllib.request.urlopen", routes):
            stats = _client().stats("ws-1")
        self.assertIsNone(stats["requirements"])
        self.assertIsNone(stats["testcases"])
        self.assertIsNone(stats["open_interviews"])

    def test_bare_list_response_yields_none_count(self) -> None:
        routes = _Routes(
            {
                "/api/v1/requirements/": [{"id": "r-1"}],
                "/api/v1/testcases/": _page(0, 0),
                "/api/v1/interviews/": _page(0, 0),
            }
        )
        with patch("urllib.request.urlopen", routes):
            stats = _client().stats("ws-1")
        self.assertIsNone(stats["requirements"])

    def test_incidental_count_failure_degrades_only_that_number(self) -> None:
        routes = _Routes(
            {
                "/api/v1/requirements/": _page(3, 3),
                "/api/v1/testcases/": _page(0, 0),
                "/api/v1/interviews/": _page(2, 2),
            },
            errors={"/api/v1/testcases/": _http_error(500, "boom")},
        )
        with patch("urllib.request.urlopen", routes):
            stats = _client().stats("ws-1")
        self.assertEqual(stats["requirements"], 3)
        self.assertIsNone(stats["testcases"])
        self.assertEqual(stats["open_interviews"], 2)
        self.assertEqual(stats["workspace_id"], "ws-1")

    def test_interviews_request_filters_by_status(self) -> None:
        routes = _Routes({path: _page(0, 0) for path in _STATS_PATHS})
        with patch("urllib.request.urlopen", routes):
            _client().stats("ws-1")
        interview_urls = [r.full_url for r in routes.requests if "interviews" in r.full_url]
        self.assertEqual(len(interview_urls), 1)
        self.assertIn("workspace_id=ws-1", interview_urls[0])
        self.assertIn("status=in_progress", interview_urls[0])


if __name__ == "__main__":
    unittest.main()
