"""Throttle-rate configuration checks (#1738, C1-T4).

A malformed rate setting must be reported by ``rest_api.E001`` at startup and
must never surface as an HTTP 500 on the request path.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.core.exceptions import ImproperlyConfigured

from mcp_server.throttling import (
    McpApiKeyRateThrottle,
    service_unavailable_jsonrpc_response,
)
from rest_api.checks import check_throttle_rates


def _error_ids() -> list[str]:
    return [error.id for error in check_throttle_rates()]


@override_settings(MCP_RATE_LIMIT_KEY="not-a-rate")
def test_system_check_reports_invalid_key_rate() -> None:
    assert "rest_api.E001" in _error_ids()


@override_settings(MCP_RATE_LIMIT_IP="")
def test_empty_optional_rate_is_ignored() -> None:
    assert "rest_api.E001" not in _error_ids()


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {"user": "600/min", "anon": "120/min"}
    }
)
def test_valid_rates_produce_no_errors() -> None:
    assert "rest_api.E001" not in _error_ids()


@override_settings(
    REST_FRAMEWORK={"DEFAULT_THROTTLE_RATES": {"user": "600"}}
)
def test_system_check_reports_invalid_framework_rate() -> None:
    errors = [e for e in check_throttle_rates() if e.id == "rest_api.E001"]
    assert len(errors) == 1
    assert "600" in errors[0].msg


@override_settings(
    REST_FRAMEWORK={"DEFAULT_THROTTLE_RATES": {"mcp_key": "not-a-rate"}}
)
def test_key_throttle_translates_value_error_to_config_error() -> None:
    with pytest.raises(ImproperlyConfigured):
        McpApiKeyRateThrottle("credential")


def test_service_unavailable_response_is_503_with_retry_after() -> None:
    response = service_unavailable_jsonrpc_response(request_id=1)
    assert response.status_code == 503
    assert response["Retry-After"] == "60"
    assert b"SERVICE_UNAVAILABLE" in response.content
