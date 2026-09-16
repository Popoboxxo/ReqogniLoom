"""RateLimitService — admin read/write of the runtime throttle overrides (#944).

Thin write layer over the two override models, kept out of the views so the
REST adapter stays a pure transport (REQ-L3-RA001-004). The read path used by
the throttles themselves lives in :mod:`admin_ops.rate_limits`; this module is
the *operator-facing* half and is the only place that validates a rate string
or writes an audit entry.

Every mutation invalidates the resolution cache
(:func:`admin_ops.rate_limits.invalidate`) inside the same transaction, so an
operator sees the new ceiling on the next request instead of after the TTL.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional
from uuid import UUID

from django.conf import settings
from django.db import transaction

from admin_ops.models import (
    SYSTEM_RATE_LIMIT_ID,
    RateLimitOverride,
    SystemRateLimitOverride,
)
from admin_ops.rate_limits import RATE_LIMIT_SCOPES, effective_rates, invalidate
from application.base import ValidationError
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

__all__ = ["RateLimitService"]

#: DRF's own ``"<count>/<period>"`` syntax. The period check mirrors
#: ``SimpleRateThrottle.parse_rate`` exactly: it only ever looks at the *first*
#: character (``{'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period[0]]``), so
#: ``min``, ``minute`` and ``min``-anything are all accepted there. Validating
#: anything stricter would reject values the throttle happily runs with;
#: validating anything looser would let ``5/fortnight`` through to fail on the
#: next request instead of in the admin API.
_RATE_PATTERN = re.compile(r"^(?P<count>\d+)/(?P<period>[A-Za-z]+)$")


def _validate_rate(value: Any) -> str:
    """Validate a single rate value; return it normalised.

    An empty string is valid and means "unlimited" (see
    :class:`~admin_ops.models.RateLimitOverride`).
    """
    if not isinstance(value, str):
        raise ValidationError("Rate must be a string like '600/min' (or '' to disable).")
    rate = value.strip()
    if not rate:
        return rate
    match = _RATE_PATTERN.match(rate)
    if match is None or match.group("period")[0].lower() not in "smhd":
        raise ValidationError(
            f"Invalid rate {value!r}: expected '<count>/<period>' with period "
            "one of s, m, h, d (e.g. '600/min')."
        )
    return rate


def _defaults() -> Mapping[str, Optional[str]]:
    """The settings/env layer, i.e. precedence layer 3."""
    return settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})


def _audit(user_id: Optional[UUID], entity_id: UUID, reason: str) -> None:
    """Best-effort audit entry for a rate-limit change.

    Not fatal, mirroring ``MemorySettingsService._audit_config_write``: an
    audit row is tenant-scoped while the global override is deployment-wide, so
    a missing tenant context must not roll back a legitimate config change. The
    nested ``atomic()`` is what makes swallowing safe — a DB error inside
    ``log_write`` would otherwise poison the caller's outer transaction.
    """
    if user_id is None:
        return
    try:
        with transaction.atomic():
            from audit.services import log_write

            log_write(
                actor=str(user_id),
                actor_type="user",
                operation="update",
                entity_type="RateLimitOverride",
                entity_id=entity_id,
                change_reason=reason,
            )
    except Exception:  # noqa: BLE001 - see docstring: attribution is best-effort
        logger.warning(
            "RateLimitService: audit entry for %s could not be written",
            reason, exc_info=True,
        )


class RateLimitService:
    """Read and mutate the runtime throttle overrides."""

    # -- read ---------------------------------------------------------------

    @staticmethod
    def get_effective(tenant_id: Optional[UUID] = None) -> dict[str, dict[str, Any]]:
        """Effective value, origin and raw overrides for every scope."""
        return effective_rates(tenant_id=tenant_id, defaults=_defaults())

    # -- write --------------------------------------------------------------

    @staticmethod
    @atomic_transaction
    def set_tenant_overrides(
        tenant_id: UUID,
        overrides: Mapping[str, Any],
        *,
        user_id: Optional[UUID] = None,
    ) -> dict[str, dict[str, Any]]:
        """Set or clear overrides for *tenant_id*.

        ``overrides`` maps a scope to either a rate string (written, ``""``
        allowed for "unlimited") or ``None`` (the row is deleted, so the global
        override / settings value applies again). Unknown scopes are rejected
        rather than silently dropped.
        """
        for scope, value in overrides.items():
            if scope not in RATE_LIMIT_SCOPES:
                raise ValidationError(
                    f"Unknown rate-limit scope {scope!r}. "
                    f"Valid scopes: {', '.join(RATE_LIMIT_SCOPES)}."
                )
            if value is None:
                RateLimitOverride.unscoped.filter(
                    tenant_id=tenant_id, scope=scope
                ).delete()
            else:
                row, created = RateLimitOverride.unscoped.update_or_create(
                    tenant_id=tenant_id,
                    scope=scope,
                    defaults={
                        "rate": _validate_rate(value),
                        "modified_by_id": user_id,
                    },
                )
                if created and user_id is not None:
                    # ``created_by`` is attribution, not content: it must be set
                    # once and never rewritten by a later edit, so it cannot live
                    # in ``defaults`` (which is applied on every save).
                    RateLimitOverride.unscoped.filter(pk=row.pk).update(
                        created_by_id=user_id
                    )

        invalidate(tenant_id)
        _audit(user_id, tenant_id, f"tenant overrides={sorted(overrides)}")
        return RateLimitService.get_effective(tenant_id)

    @staticmethod
    @atomic_transaction
    def clear_tenant_overrides(
        tenant_id: UUID, *, user_id: Optional[UUID] = None
    ) -> dict[str, dict[str, Any]]:
        """Delete every tenant-scoped override (falls back to global/settings)."""
        RateLimitOverride.unscoped.filter(tenant_id=tenant_id).delete()
        invalidate(tenant_id)
        _audit(user_id, tenant_id, "tenant overrides=reset")
        return RateLimitService.get_effective(tenant_id)

    @staticmethod
    @atomic_transaction
    def set_global_overrides(
        overrides: Mapping[str, Any],
        *,
        user_id: Optional[UUID] = None,
    ) -> dict[str, dict[str, Any]]:
        """Set or clear deployment-wide overrides (same value semantics)."""
        row, created = SystemRateLimitOverride.objects.get_or_create(
            pk=SYSTEM_RATE_LIMIT_ID
        )
        scopes = dict(row.scopes) if isinstance(row.scopes, dict) else {}

        for scope, value in overrides.items():
            if scope not in RATE_LIMIT_SCOPES:
                raise ValidationError(
                    f"Unknown rate-limit scope {scope!r}. "
                    f"Valid scopes: {', '.join(RATE_LIMIT_SCOPES)}."
                )
            if value is None:
                scopes.pop(scope, None)
            else:
                scopes[scope] = _validate_rate(value)

        row.scopes = scopes
        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()

        invalidate(None)
        _audit(user_id, SYSTEM_RATE_LIMIT_ID, f"global overrides={sorted(overrides)}")
        return RateLimitService.get_effective()

    @staticmethod
    @atomic_transaction
    def clear_global_overrides(
        *, user_id: Optional[UUID] = None
    ) -> dict[str, dict[str, Any]]:
        """Delete the deployment-wide override row entirely."""
        SystemRateLimitOverride.objects.all().delete()
        invalidate(None)
        _audit(user_id, SYSTEM_RATE_LIMIT_ID, "global overrides=reset")
        return RateLimitService.get_effective()
