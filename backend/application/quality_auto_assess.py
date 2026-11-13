"""Automatic quality assessment behind a feature flag (Issue #1578).

Wiring only — the assessment itself stays in :class:`QualityService`. This
module decides **whether** a run may happen and under whose identity.

Gates, in order (first hit wins, result is a ``skipped:<reason>`` string):

1. ``QUALITY_AUTO_ASSESS_ENABLED`` is off (default)          -> ``flag_off``
2. entity type is not assessable                             -> ``type_not_assessable``
3. workspace preset is not ``extended``                      -> ``tier_not_extended``
4. no active agent API key configured for the tenant         -> ``no_agent_key``
5. the same artefact was assessed within the interval        -> ``throttled``

The run itself uses the configured **agent** key (one per tenant), because an
automatic assessment has no human actor. Without that key nothing runs: the
feature must never silently write under a real user's identity.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache

from application.quality_service import ASSESSABLE_TYPES, QualityService
from auth_tenancy.context import AuthContext, AuthMethod
from application.models import DomainEventOutbox
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)

TRIGGER_TRANSITION = "auto_transition"
TRIGGER_CREATE = "auto_create"
TRIGGER_PERIODIC = "auto_periodic"

_CREATED_EVENT = "{entity_type}Created"
_TRANSITION_EVENT = DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED.value


def _setting(name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def auto_assess_enabled() -> bool:
    return bool(_setting("QUALITY_AUTO_ASSESS_ENABLED", False))


def agent_key_id() -> UUID | None:
    raw = str(_setting("QUALITY_AUTO_ASSESS_AGENT_KEY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        logger.warning(
            "QUALITY_AUTO_ASSESS_AGENT_KEY_ID is not a UUID; auto-assessment stays off."
        )
        return None


def min_interval_seconds() -> int:
    return int(_setting("QUALITY_AUTO_ASSESS_MIN_INTERVAL_SECONDS", 3600))


def _throttle_key(entity_type: str, entity_id: UUID) -> str:
    return f"quality:auto-assess:{entity_type}:{entity_id}"


class QualityAutoAssessor:
    """Decides and executes one automatic assessment run."""

    def __init__(self, service: QualityService | None = None) -> None:
        self._service = service or QualityService()

    # ------------------------------------------------------------------
    # Event entry point
    # ------------------------------------------------------------------

    def handle_event(self, event: Any) -> None:
        """Bus subscriber: dispatch a Celery task, never call the LLM here."""
        if event.event_type == _TRANSITION_EVENT:
            entity_type = str((event.payload or {}).get("item_type") or "")
            trigger = TRIGGER_TRANSITION
        else:
            entity_type = _entity_type_for_created_event(event.event_type)
            trigger = TRIGGER_CREATE
        if entity_type not in ASSESSABLE_TYPES:
            return
        if not auto_assess_enabled():
            return

        from application.tasks import quality_auto_assess_entity

        quality_auto_assess_entity.delay(
            tenant_id=str(event.tenant_id or ""),
            workspace_id=str(event.workspace_id),
            entity_type=entity_type,
            entity_id=str(event.entity_id),
            trigger=trigger,
        )

    # ------------------------------------------------------------------
    # Task entry point
    # ------------------------------------------------------------------

    def run_for(
        self,
        *,
        tenant_id: UUID | str | None,
        workspace_id: UUID | str,
        entity_type: str,
        entity_id: UUID | str,
        trigger: str,
    ) -> str:
        """Run the gates, then assess. Returns ``assessed|skipped:<r>|failed``."""
        if not auto_assess_enabled():
            return "skipped:flag_off"
        if entity_type not in ASSESSABLE_TYPES:
            return "skipped:type_not_assessable"
        if not tenant_id:
            # Fail closed: the outbox row is the tenant authority, and a row
            # without one would make the key lookup cross-tenant.
            logger.warning("quality auto-assess skipped: event carries no tenant anchor.")
            return "skipped:no_agent_key"

        workspace_uuid = UUID(str(workspace_id))
        entity_uuid = UUID(str(entity_id))
        tenant_uuid = UUID(str(tenant_id))

        previous = TenantContext.get_tenant() if TenantContext.is_set() else None
        TenantContext.set_tenant(tenant_uuid)
        try:
            if not self._is_extended(workspace_uuid):
                return "skipped:tier_not_extended"

            ctx = self._agent_context(tenant_uuid, workspace_uuid)
            if ctx is None:
                return "skipped:no_agent_key"

            cache_key = _throttle_key(entity_type, entity_uuid)
            if cache.get(cache_key):
                return "skipped:throttled"
            # Set before the call: a provider hang must not allow a second run
            # to start in parallel and pay twice.
            cache.set(cache_key, 1, timeout=min_interval_seconds())

            try:
                _row, cached = self._service.assess(
                    ctx,
                    workspace_uuid,
                    entity_type,
                    entity_uuid,
                    trigger=trigger,
                )
            except Exception:  # noqa: BLE001 - provider faults must not retry-storm
                logger.warning(
                    "quality auto-assess failed for %s %s",
                    entity_type,
                    entity_uuid,
                    exc_info=True,
                )
                cache.delete(cache_key)
                return "failed"

            if cached:
                return "skipped:unchanged_hash"
            return "assessed"
        finally:
            if previous is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_extended(workspace_id: UUID) -> bool:
        from presets.services import get_preset

        return get_preset(str(workspace_id)).preset == "extended"

    @staticmethod
    def _agent_context(tenant_id: UUID, workspace_id: UUID) -> AuthContext | None:
        from auth_tenancy.models import ApiKey
        from auth_tenancy.services.authorization import AuthorizationService

        key_id = agent_key_id()
        if key_id is None:
            logger.warning(
                "quality auto-assess skipped: QUALITY_AUTO_ASSESS_AGENT_KEY_ID is unset."
            )
            return None
        key = (
            ApiKey.objects.filter(
                id=key_id, principal_type="agent", revoked_at__isnull=True
            )
            .select_related("user")
            .first()
        )
        if key is None:
            logger.warning(
                "quality auto-assess skipped: configured agent key is missing or revoked."
            )
            return None

        roles = AuthorizationService().active_roles_for(
            user_id=key.user_id, workspace_id=workspace_id
        )
        return AuthContext(
            user_id=key.user_id,
            tenant_id=tenant_id,
            active_roles=roles,
            auth_method=AuthMethod.API_KEY,
            api_key_id=key.id,
            workspace_id=workspace_id,
            actor_type="agent",
            agent_label=key.agent_label or "",
            scope=key.scope,
            api_key_workspace_ids=tuple(key.workspace_ids or ()),
        )


def _entity_type_for_created_event(event_type: str) -> str:
    for entity_type in ASSESSABLE_TYPES:
        if event_type == _CREATED_EVENT.format(entity_type=entity_type):
            return entity_type
    return ""


def subscribed_event_types() -> tuple[str, ...]:
    """Event types the auto-assessor listens to (declared, not derived)."""
    return (_TRANSITION_EVENT,) + tuple(
        _CREATED_EVENT.format(entity_type=entity_type)
        for entity_type in ASSESSABLE_TYPES
    )


def register_auto_assessor_on_event_bus() -> int:
    """Subscribe the assessor. The handler itself is a no-op while the flag is off."""
    from application.event_bus import get_event_bus

    assessor = QualityAutoAssessor()
    bus = get_event_bus()
    event_types = subscribed_event_types()
    for event_type in event_types:
        bus.register_subscriber(event_type, assessor.handle_event)
    logger.info(
        "QualityAutoAssessor registered on DomainEventBus for %d event type(s).",
        len(event_types),
    )
    return len(event_types)


__all__ = [
    "QualityAutoAssessor",
    "TRIGGER_CREATE",
    "TRIGGER_PERIODIC",
    "TRIGGER_TRANSITION",
    "auto_assess_enabled",
    "register_auto_assessor_on_event_bus",
    "subscribed_event_types",
]
