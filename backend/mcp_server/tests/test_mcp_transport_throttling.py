"""Rate limiting on the MCP transport endpoints (SYSTEMAUDIT-2026-08-27 finding A).

Pre-fix behaviour these tests pin down: ``mcp_server.views`` are plain Django
views, so ``REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]`` never ran on ``/mcp/*``
and every endpoint answered an unbounded number of requests — unlimited SSE
session creation, unlimited tool dispatch (and therefore unlimited LLM spend on
one key), and an unlimited number of credential presentations.

No database and no live Redis are needed here:

* ``settings_test`` pins ``CACHES`` to ``LocMemCache``, which is the very
  backend the throttles count through, so the counters are real rather than
  mocked — a mocked cache would be free to disagree with the Redis semantics
  that run in production.
* The view-level tests configure a rate of ``"0/min"``, which refuses the
  *first* request. That is deliberate: it proves the throttle fires **before**
  the view touches the database (API-key validation) or Redis (SSE session
  lookup), which is the whole point of placing it first — a throttle that only
  runs after the expensive work would not bound anything.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings

from mcp_server.protocol_handler import ERROR_CODES
from mcp_server.throttling import (
    api_key_from_request,
    check_mcp_rate_limit,
    rate_limited_jsonrpc_response,
)


def _rates(**overrides: Any) -> dict:
    """Full ``REST_FRAMEWORK`` dict with only the named throttle rates changed.

    ``override_settings`` replaces a setting wholesale, so the rest of the DRF
    wiring has to be carried over. Mirrors
    ``rest_api.tests.test_security_hardening_269._rest_framework_with_rates``;
    the MCP scopes live in the same ``DEFAULT_THROTTLE_RATES`` dict precisely so
    one helper shape works for both suites.
    """
    merged = dict(settings.REST_FRAMEWORK)
    merged["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        **overrides,
    }
    return merged


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Throttle counters are cache state; isolate every test from every other."""
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


class TestApiKeyFromRequest:
    """The throttle must see the same credential the auth path sees."""

    def test_bearer_header(self):
        request = RequestFactory().post(
            "/mcp/", HTTP_AUTHORIZATION="Bearer reqlo_abc"
        )
        assert api_key_from_request(request) == "reqlo_abc"

    def test_x_api_key_header(self):
        request = RequestFactory().post("/mcp/", HTTP_X_API_KEY="reqlo_abc")
        assert api_key_from_request(request) == "reqlo_abc"

    def test_query_parameter_is_ignored(self):
        """REQ-018 / SYSTEM_AUDIT P-05: a ``?api_key=`` is never a credential.

        If the throttle honoured it, a caller could dodge their own per-key
        bucket by moving the key from the header into the URL.
        """
        request = RequestFactory().post("/mcp/?api_key=reqlo_abc")
        assert api_key_from_request(request) == ""


# ---------------------------------------------------------------------------
# Counter semantics
# ---------------------------------------------------------------------------


class TestCheckMcpRateLimit:
    def _request(self, key: str = "", ip: str = "10.0.0.1"):
        return RequestFactory().post(
            "/mcp/",
            HTTP_X_API_KEY=key,
            REMOTE_ADDR=ip,
        )

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="3/min", mcp_ip="1000/min"))
    def test_allows_up_to_the_limit_then_refuses(self):
        request = self._request("reqlo_key_a")
        assert [check_mcp_rate_limit(request) for _ in range(3)] == [None] * 3

        retry_after = check_mcp_rate_limit(request)
        assert retry_after is not None
        # Never below 1s: a client must not read "Retry-After: 0" as
        # "retry immediately" and hot-loop against the endpoint.
        assert retry_after >= 1.0

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="2/min", mcp_ip="1000/min"))
    def test_buckets_are_per_credential(self):
        """One key exhausting its budget must not refuse a different key.

        Same client IP for both, so this fails if the per-key bucket silently
        keys on something coarser.
        """
        for _ in range(2):
            assert check_mcp_rate_limit(self._request("reqlo_key_a")) is None
        assert check_mcp_rate_limit(self._request("reqlo_key_a")) is not None

        assert check_mcp_rate_limit(self._request("reqlo_key_b")) is None

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="1000/min", mcp_ip="3/min"))
    def test_ip_backstop_catches_rotating_credentials(self):
        """A caller presenting a fresh credential every time is still bounded.

        This is the vector the per-key counter structurally cannot see, and the
        reason the per-IP counter exists at all.
        """
        for i in range(3):
            assert check_mcp_rate_limit(self._request(f"reqlo_key_{i}")) is None
        assert check_mcp_rate_limit(self._request("reqlo_key_99")) is not None

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="1000/min", mcp_ip="2/min"))
    def test_ip_bucket_is_per_client_ip(self):
        for _ in range(2):
            assert check_mcp_rate_limit(self._request(ip="10.0.0.1")) is None
        assert check_mcp_rate_limit(self._request(ip="10.0.0.1")) is not None

        assert check_mcp_rate_limit(self._request(ip="10.0.0.2")) is None

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="1/min", mcp_ip="1/min"))
    def test_anonymous_request_counts_against_ip_only(self):
        """No credential → the per-key bucket is "not applicable", not "denied"."""
        assert check_mcp_rate_limit(self._request(key="")) is None
        assert check_mcp_rate_limit(self._request(key="")) is not None

    @override_settings(REST_FRAMEWORK=_rates(mcp_key=None, mcp_ip=None))
    def test_empty_rate_disables_the_throttle(self):
        """An empty env value must disable the limit, as it does for REST.

        ``settings.MCP_RATE_LIMIT_*`` map ``""`` to ``None`` exactly for the
        air-gapped / load-test deployments the #269 module docstring describes.
        """
        request = self._request("reqlo_key_a")
        assert all(check_mcp_rate_limit(request) is None for _ in range(50))

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="2/min", mcp_ip="1000/min"))
    def test_explicit_credential_overrides_headers(self):
        """``/mcp/messages/`` identifies a caller by session id, not by header.

        The key never travels on that endpoint (REQ-018 / SYSTEM_AUDIT P-02), so
        the caller must be able to name the credential the bucket keys on.
        """
        request = RequestFactory().post("/mcp/messages/?session_id=s-1")
        for _ in range(2):
            assert check_mcp_rate_limit(request, credential="s-1") is None
        assert check_mcp_rate_limit(request, credential="s-1") is not None
        assert check_mcp_rate_limit(request, credential="s-2") is None


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestRateLimitedResponse:
    def test_jsonrpc_envelope_and_retry_after_header(self):
        response = rate_limited_jsonrpc_response(4.2, request_id=17)

        assert response.status_code == 429
        # Rounded up, never down: advertising a shorter wait than the bucket
        # actually needs guarantees the retry is refused again.
        assert response["Retry-After"] == "5"

        body = json.loads(response.content)
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == 17
        # String error_code (REQ-047), matching the other transport-level
        # rejections in mcp_server.views rather than the numeric-code shape
        # ErrorFormatter emits for handler-level errors.
        assert body["error"]["error_code"] == "RATE_LIMITED"
        assert body["error"]["message"] == ERROR_CODES["RATE_LIMITED"]
        assert body["error"]["data"]["retryable"] is True
        assert body["error"]["data"]["retry_after_seconds"] == 5

    def test_missing_request_id_is_null_not_omitted(self):
        body = json.loads(rate_limited_jsonrpc_response(1.0).content)
        assert body["id"] is None


# ---------------------------------------------------------------------------
# View wiring — asserts the throttle runs before any expensive work
# ---------------------------------------------------------------------------


#: A rate that refuses the very first request. ``override_settings`` is applied
#: per method rather than to the class: Django only accepts it as a class
#: decorator on ``SimpleTestCase`` subclasses, and these are plain pytest
#: classes.
_REFUSE_EVERYTHING = override_settings(
    REST_FRAMEWORK=_rates(mcp_key="0/min", mcp_ip="0/min")
)


class TestViewsAreThrottled:
    """A ``0/min`` rate refuses the first request.

    Because no test in this class is marked ``django_db``, any endpoint that
    reached its authentication or session lookup would raise a database/Redis
    access error instead of returning 429 — so a passing test here is also
    proof that the throttle sits in front of that work.
    """

    @_REFUSE_EVERYTHING
    def test_http_transport_post(self):
        response = Client().post(
            "/mcp/",
            data=json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 4}),
            content_type="application/json",
            HTTP_X_API_KEY="reqlo_key_a",
        )
        assert response.status_code == 429
        assert response["Retry-After"]
        body = json.loads(response.content)
        assert body["error"]["error_code"] == "RATE_LIMITED"
        # The id is echoed so a client can correlate the rejection with its call.
        assert body["id"] == 4

    @override_settings(REST_FRAMEWORK=_rates(mcp_key="2/min", mcp_ip="1000/min"))
    def test_traffic_below_the_limit_still_reaches_the_handler(self, monkeypatch):
        """The throttle must *bound* the happy path, not break it.

        ``_get_handler`` is stubbed so this stays database-free: a real handler
        would only add the API-key lookup, which has nothing to do with rate
        limiting. The call-count assertion is the load-bearing one — it proves
        the refused request never reached dispatch, which is what makes the
        limit an actual cost bound rather than cosmetics.
        """
        handler = MagicMock()
        handler.handle_http_request.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }
        monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)

        client = Client()

        def _call():
            return client.post(
                "/mcp/",
                data=json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 1}),
                content_type="application/json",
                HTTP_X_API_KEY="reqlo_key_a",
            )

        assert [_call().status_code for _ in range(2)] == [200, 200]
        assert _call().status_code == 429
        assert handler.handle_http_request.call_count == 2

    @_REFUSE_EVERYTHING
    def test_http_transport_get_server_info(self):
        response = Client().get("/mcp/")
        assert response.status_code == 429
        assert json.loads(response.content)["error"]["error_code"] == "RATE_LIMITED"

    @_REFUSE_EVERYTHING
    def test_messages_endpoint(self):
        response = Client().post(
            "/mcp/messages/?session_id=some-session",
            data=json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 8}),
            content_type="application/json",
        )
        assert response.status_code == 429
        body = json.loads(response.content)
        assert body["error"]["error_code"] == "RATE_LIMITED"
        assert body["id"] == 8

    @_REFUSE_EVERYTHING
    def test_sse_handshake(self):
        """The SSE handshake is throttled *before* it is authenticated.

        Order matters here: authenticating first would spend a DB round trip per
        rejected attempt, and it is the handshake — not the message endpoint —
        that allocates the Redis binding and the held-open stream this limit is
        meant to bound.
        """
        response = Client().get("/mcp/sse/", HTTP_X_API_KEY="reqlo_key_a")
        assert response.status_code == 429
        assert response["Retry-After"]
        assert json.loads(response.content)["error"] == ERROR_CODES["RATE_LIMITED"]
