"""Runtime resolution of the effective REST/MCP throttle ceilings (GitHub #944).

The ceilings themselves (``settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]``)
are environment-aware but read once at process start. This module adds the
runtime layer on top and is the **single** place that answers "what rate applies
to this scope right now?". Both ``rest_api.throttling`` and
``mcp_server.throttling`` resolve through it, so there is exactly one
precedence rule rather than two that can drift apart.

Precedence (first hit wins):

1. **tenant override** — :class:`~admin_ops.models.RateLimitOverride`, stored
   per ``(tenant, scope)``. Only reachable when the request already carries a
   tenant (i.e. after REST authentication).
2. **global override** — :class:`~admin_ops.models.SystemRateLimitOverride`,
   the deployment-wide default. This is the layer the MCP transport relies on:
   MCP throttling runs *before* authentication on purpose, so no tenant exists
   at that point.
3. **settings / env** — the value passed in as ``default``.
4. **disabled** — nothing configured for the scope.

A stored empty string is an explicit "unlimited" and therefore *wins* over the
settings value; an absent row falls through. See ``admin_ops.models`` for why
the two are kept distinct.

Failure policy — **fail-safe towards the last known good rate**:

* Every cache and DB access is wrapped. A failure is logged and treated as
  "no override", so resolution degrades to the settings value instead of
  raising into the request path. A throttle that can 500 the API when Redis
  hiccups would be a worse outage than the one it guards against.
* Short TTL (``_CACHE_TTL_SECONDS``) bounds staleness after an out-of-band DB
  write; the write path additionally invalidates eagerly.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional
from uuid import UUID

from django.core.cache import cache

logger = logging.getLogger(__name__)

__all__ = [
    "RATE_LIMIT_SCOPES",
    "effective_rates",
    "invalidate",
    "resolve_rate",
]

#: Every throttle scope the runtime layer can override. Kept in sync with
#: ``settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` by
#: ``admin_ops.tests.test_rate_limit_override`` — a scope added there but
#: missing here would be silently un-configurable, and vice versa.
RATE_LIMIT_SCOPES: tuple[str, ...] = (
    "user",
    "anon",
    "login",
    "login_ip",
    "refresh",
    "mcp_key",
    "mcp_ip",
)

#: Short enough that an out-of-band DB change is picked up quickly, long enough
#: that the throttles do not issue a query per request.
_CACHE_TTL_SECONDS = 30

_TENANT_CACHE_KEY = "ratelimit:overrides:tenant:{tenant_id}"
_GLOBAL_CACHE_KEY = "ratelimit:overrides:global"


def _cache_get(key: str) -> Any:
    try:
        return cache.get(key)
    except Exception:  # noqa: BLE001 - see module docstring: never raise here
        logger.warning(
            "rate_limits: cache read failed for %s; treating as no override", key,
            exc_info=True,
        )
        return None


def _cache_set(key: str, value: Any) -> None:
    try:
        cache.set(key, value, _CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - a failed cache write must not fail the request
        logger.warning(
            "rate_limits: cache write failed for %s", key, exc_info=True,
        )


def _cache_delete(key: str) -> None:
    try:
        cache.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning(
            "rate_limits: cache invalidation failed for %s", key, exc_info=True,
        )


def _tenant_overrides(tenant_id: Optional[UUID]) -> Mapping[str, str]:
    """Raw ``{scope: rate}`` overrides for *tenant_id*, or ``{}``.

    Read through the ``unscoped`` manager with an explicit ``tenant_id``
    filter: the caller may hold the tenant from its auth context while the
    thread-local tenant context is not set on this code path, and a
    manager-level filter is the deterministic half of the isolation. PostgreSQL
    RLS (migration ``0007``) remains the second layer whenever a tenant context
    *is* active, which is the normal request path.
    """
    if tenant_id is None:
        return {}

    key = _TENANT_CACHE_KEY.format(tenant_id=tenant_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        from admin_ops.models import RateLimitOverride

        data = {
            row.scope: row.rate
            for row in RateLimitOverride.unscoped.filter(tenant_id=tenant_id)
        }
    except Exception:  # noqa: BLE001 - DB outage must not break the request path
        logger.warning(
            "rate_limits: tenant override lookup failed for tenant %s", tenant_id,
            exc_info=True,
        )
        return {}

    _cache_set(key, data)
    return data


def _global_overrides() -> Mapping[str, str]:
    """Raw ``{scope: rate}`` deployment-wide overrides, or ``{}``."""
    cached = _cache_get(_GLOBAL_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        from admin_ops.models import SystemRateLimitOverride

        row = SystemRateLimitOverride.objects.first()
        scopes = getattr(row, "scopes", None)
        data = dict(scopes) if isinstance(scopes, dict) else {}
    except Exception:  # noqa: BLE001 - DB outage must not break the request path
        logger.warning(
            "rate_limits: global override lookup failed", exc_info=True,
        )
        return {}

    _cache_set(_GLOBAL_CACHE_KEY, data)
    return data


def resolve_rate(
    scope: str,
    *,
    tenant_id: Optional[UUID] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Effective rate for *scope*: tenant override > global override > default.

    Args:
        scope: Throttle scope name (``"user"``, ``"mcp_key"``, ...).
        tenant_id: Tenant of the request, when one is known. ``None`` is
            legitimate — anonymous REST requests and every MCP request reach
            this without a tenant and simply start at layer 2.
        default: The settings/env rate, already resolved by the caller.

    Returns:
        A DRF ``"<count>/<period>"`` string, or ``None`` for "unlimited"
        (either an explicit empty override or an empty/absent settings value).
    """
    if tenant_id is not None:
        override = _tenant_overrides(tenant_id).get(scope)
        if override is not None:
            # Stored "" is an explicit disable -> None (DRF: unlimited).
            return override or None

    override = _global_overrides().get(scope)
    if override is not None:
        return override or None

    return default or None


def effective_rates(
    *,
    tenant_id: Optional[UUID] = None,
    defaults: Optional[Mapping[str, Optional[str]]] = None,
) -> dict[str, dict[str, Any]]:
    """Read-only view of every scope's effective value and its origin.

    Backs the admin API: an operator needs to see not only the number that
    applies but *why* it applies, otherwise "I changed it and nothing happened"
    is undiagnosable from the outside.

    Returns a ``{scope: {...}}`` map; never raises (the underlying lookups are
    already fail-safe) so the read endpoint cannot 500 because of a cache blip.
    """
    defaults = defaults or {}
    tenant_ov = _tenant_overrides(tenant_id)
    global_ov = _global_overrides()

    result: dict[str, dict[str, Any]] = {}
    for scope in RATE_LIMIT_SCOPES:
        settings_value = defaults.get(scope) or None
        if scope in tenant_ov:
            source = "tenant"
            effective = tenant_ov[scope] or None
        elif scope in global_ov:
            source = "global"
            effective = global_ov[scope] or None
        else:
            source = "settings"
            effective = settings_value

        result[scope] = {
            "effective": effective,
            "source": source,
            "settings_value": settings_value,
            "tenant_override": tenant_ov.get(scope),
            "global_override": global_ov.get(scope),
            "disabled": effective is None,
        }
    return result


def invalidate(tenant_id: Optional[UUID] = None) -> None:
    """Drop the cached overrides for *tenant_id*, or the global layer if ``None``.

    Called by :class:`~admin_ops.services.rate_limit_service.RateLimitService`
    after every write so an operator sees the new limit on the next request
    rather than after the TTL.
    """
    if tenant_id is None:
        _cache_delete(_GLOBAL_CACHE_KEY)
    else:
        _cache_delete(_TENANT_CACHE_KEY.format(tenant_id=tenant_id))
