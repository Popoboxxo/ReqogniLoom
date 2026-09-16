"""Runtime-configurable MCP rate limits (GitHub #944).

The transport-level throttling itself is covered by
``test_mcp_transport_throttling.py`` (the static ceilings). This module covers
the runtime layer on top of it, and in particular the one design consequence of
where MCP throttling sits in the request:

    ``mcp_server.views`` throttle **before** authentication on purpose (a
    throttle that runs after the expensive work bounds nothing), so no tenant
    is known when the rate is resolved. MCP therefore honours the *global*
    override and the settings value, and deliberately not a per-tenant one.

That is asserted explicitly below rather than left implicit, because "my tenant
override does not apply to /mcp/" is exactly the kind of behaviour an operator
would otherwise have to discover from a support ticket.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings

from admin_ops.services.rate_limit_service import RateLimitService
from mcp_server.throttling import check_mcp_rate_limit
from rest_api.throttling import DynamicRateThrottle


class DownCache:
    """Cache stand-in whose every operation fails, as Redis does when it dies."""

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")

    def set(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _request(key: str = "reqlo_key_a", ip: str = "10.0.0.1"):
    return RequestFactory().post("/mcp/", HTTP_X_API_KEY=key, REMOTE_ADDR=ip)


# ---------------------------------------------------------------------------
# The global override governs (MCP has no tenant at throttle time)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_global_override_enforces_the_limit():
    """``mcp_key`` set at runtime must refuse the second call within the window."""
    RateLimitService.set_global_overrides({"mcp_key": "1/min"})

    assert check_mcp_rate_limit(_request()) is None

    retry_after = check_mcp_rate_limit(_request())
    assert retry_after is not None
    assert retry_after >= 1.0


@pytest.mark.django_db
def test_global_override_beats_the_settings_ceiling():
    """Settings say 20000/min for ``mcp_key`` in tests; the override must win."""
    RateLimitService.set_global_overrides({"mcp_key": "1/min"})

    assert check_mcp_rate_limit(_request()) is None
    assert check_mcp_rate_limit(_request()) is not None


@pytest.mark.django_db
def test_raising_the_limit_at_runtime_takes_effect_without_a_restart():
    RateLimitService.set_global_overrides({"mcp_key": "1/min"})
    assert check_mcp_rate_limit(_request()) is None
    assert check_mcp_rate_limit(_request()) is not None

    RateLimitService.set_global_overrides({"mcp_key": "1000/min"})

    # The recorded history is unchanged; only the ceiling moved.
    assert check_mcp_rate_limit(_request()) is None


@pytest.mark.django_db
def test_tenant_override_does_not_apply_to_mcp(db):
    """Documented limitation: the transport is throttled before it has a tenant."""
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant

    tenant = Tenant.objects.create(name="MCP RL", slug="mcp-rl", is_active=True)

    set_request_tenant(tenant.id)
    try:
        RateLimitService.set_tenant_overrides(tenant.id, {"mcp_key": "1/min"})
    finally:
        clear_request_tenant()

    # Two calls that a 1/min tenant override would have refused.
    assert check_mcp_rate_limit(_request()) is None
    assert check_mcp_rate_limit(_request()) is None


@pytest.mark.django_db
def test_empty_global_override_disables_the_limit():
    RateLimitService.set_global_overrides({"mcp_key": ""})

    assert all(check_mcp_rate_limit(_request()) is None for _ in range(50))


# ---------------------------------------------------------------------------
# Fail-open policy on a counter outage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cache_outage_fails_open(monkeypatch):
    """Control first: with a healthy cache ``0/min`` refuses immediately."""
    RateLimitService.set_global_overrides({"mcp_key": "0/min"})
    assert check_mcp_rate_limit(_request()) is not None

    monkeypatch.setattr(DynamicRateThrottle, "cache", DownCache())

    assert check_mcp_rate_limit(_request()) is None


# ---------------------------------------------------------------------------
# View wiring — the runtime limit produces the JSON-RPC 429 envelope
# ---------------------------------------------------------------------------


_REFUSE_AFTER_TWO = override_settings(
    REST_FRAMEWORK={
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "mcp_key": "1000/min",
            "mcp_ip": "1000/min",
        },
    }
)


@_REFUSE_AFTER_TWO
@pytest.mark.django_db
def test_transport_returns_429_after_the_runtime_limit():
    """End-to-end: the third call over a 2/min global ceiling is a JSON-RPC 429."""
    import json

    RateLimitService.set_global_overrides({"mcp_key": "2/min", "mcp_ip": "1000/min"})

    body = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 4})

    def _call():
        return Client().post(
            "/mcp/",
            data=body,
            content_type="application/json",
            HTTP_X_API_KEY="reqlo_key_a",
            REMOTE_ADDR="10.0.0.1",
        )

    first, second, third = _call(), _call(), _call()

    assert first.status_code != 429, first.content
    assert second.status_code != 429, second.content
    assert third.status_code == 429
    assert json.loads(third.content)["error"]["error_code"] == "RATE_LIMITED"
    # The id is echoed so a client can correlate the rejection with its call.
    assert json.loads(third.content)["id"] == 4
