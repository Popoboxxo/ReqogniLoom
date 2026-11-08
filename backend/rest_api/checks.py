"""Startup system checks for the REST/MCP throttle configuration (#1738).

A malformed rate (for example ``MCP_RATE_LIMIT_KEY=<random token>``) used to
surface as ``ValueError: not enough values to unpack`` inside
``SimpleRateThrottle.__init__`` — i.e. as an HTTP 500 on every MCP request.
The settings layer stays tolerant on purpose (an import-time ``raise`` makes
``manage.py check`` crash with a traceback instead of reporting a check), so
this check is the fail-fast gate: ``manage.py check``, ``runserver`` and
``migrate`` report ``rest_api.E001`` before the first request.

The request path additionally translates a rate that appears after startup
(runtime override, hot reload) into ``503`` — see
``DynamicRateThrottle.__init__`` and ``McpApiKeyRateThrottle.__init__``.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings
from django.core.checks import Error, register
from rest_framework.throttling import SimpleRateThrottle

#: Settings that carry a rate but are not part of ``DEFAULT_THROTTLE_RATES``.
_EXTRA_RATE_SETTINGS = ("MCP_RATE_LIMIT_KEY", "MCP_RATE_LIMIT_IP")


def _iter_rates() -> list[tuple[str, Any]]:
    """Return ``(setting_name, rate)`` for every configured throttle rate."""
    rates: list[tuple[str, Any]] = []
    rest_framework = getattr(django_settings, "REST_FRAMEWORK", {}) or {}
    default_rates = rest_framework.get("DEFAULT_THROTTLE_RATES", {}) or {}
    for scope, rate in default_rates.items():
        rates.append((f"REST_FRAMEWORK.DEFAULT_THROTTLE_RATES[{scope!r}]", rate))
    for name in _EXTRA_RATE_SETTINGS:
        rates.append((name, getattr(django_settings, name, None)))
    return rates


def check_throttle_rates(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    """Return one ``rest_api.E001`` error per malformed throttle rate.

    ``SimpleRateThrottle.parse_rate`` does not use ``self``; calling it
    unbound avoids constructing a throttle whose scope/rate would immediately
    re-trigger the very lookup this check is validating.
    """
    errors: list[Error] = []
    for name, rate in _iter_rates():
        if rate in (None, ""):
            continue
        try:
            SimpleRateThrottle.parse_rate(None, rate)
        except (ValueError, TypeError, KeyError):
            errors.append(
                Error(
                    f"{name} is not a valid throttle rate: {rate!r}.",
                    hint=(
                        "Use '<count>/<period>' with period s, m, h or d — "
                        "e.g. '240/min'. A token or other non-rate value in a "
                        "rate setting makes every request to that endpoint fail."
                    ),
                    id="rest_api.E001",
                )
            )
    return errors


def register_checks() -> None:
    """Register the checks; called from ``RestApiConfig.ready``."""
    register(check_throttle_rates)
