"""
COMP-AS-011 WebhookDispatcher — Event-driven outbound webhook delivery.

leaf_id : COMP-AS-011
req_id  : REQ-L1-024, REQ-L3-WHOOK-001 through REQ-L3-WHOOK-009

Subscribes to DomainEventBus events and dispatches HTTP POST webhooks to
configured external URLs (WebhookSubscription). Implements HMAC-SHA256 signing
(REQ-L3-WHOOK-004), exponential back-off retry (REQ-L3-WHOOK-005), dead-letter
marking (REQ-L3-WHOOK-008), and tenant isolation (REQ-L3-WHOOK-009).

TODO-ASYNC: Outbound HTTP calls are currently synchronous (direct send).
Future integration with ResilienceOrchestrator (ARCH-L1-016 / A016) will wrap
dispatch in a Celery/Django-Q task for true async delivery.
See: COMP-AS-011 Architecture, REQ-L3-WHOOK-007.

Interface contracts implemented:
  IF-AS-INT-013     — inbound: DomainEventBus subscriber registration
  IF-AS-EXT-OUT-007 — outbound: WebhookSubscription reads from persistence
  (external)        — outbound: HTTP POST to configured webhook URLs

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-011_WebhookDispatcher/
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.utils import timezone

from application.event_bus import DomainEvent, get_event_bus

logger = logging.getLogger(__name__)

# ---------- Constants ----------

# Event types this dispatcher subscribes to (REQ-L3-WHOOK-001)
SUBSCRIBED_EVENT_TYPES: List[str] = [
    "RequirementCreated",
    "RequirementUpdated",
    "RequirementDeleted",
    "WorkflowTransitioned",
    "BaselineCreated",
]

_MAX_RETRIES = 5
_BACKOFF_SECONDS = [1, 2, 4, 8, 16]  # exponential backoff per retry
_HTTP_TIMEOUT = 10  # seconds per request (REQ-L3-WHOOK-005)


# ---------- WebhookDispatcher ----------


class WebhookDispatcher:
    """Event-driven webhook dispatcher.

    COMP-AS-011. Registers itself as a subscriber for predefined event types
    on the DomainEventBus. On receipt, fetches matching WebhookSubscriptions
    from the DB and sends HTTP POST requests.

    Usage::

        dispatcher = WebhookDispatcher()
        dispatcher.subscribe_to_events()  # call once at startup

    The dispatcher then runs synchronously inside the DomainEventBus subscriber
    callback.

    TODO-ASYNC: Replace synchronous HTTP call with Celery/Django-Q task
    (REQ-L3-WHOOK-007, ResilienceOrchestrator A016).
    """

    def __init__(self) -> None:
        self._registered = False

    def subscribe_to_events(self) -> None:
        """Register as a subscriber for all SUBSCRIBED_EVENT_TYPES.

        REQ-L3-WHOOK-001. Safe to call multiple times (idempotent).
        """
        bus = get_event_bus()
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.register_subscriber(event_type, self.process_event)
        self._registered = True
        logger.info(
            "WebhookDispatcher: subscribed to %d event types",
            len(SUBSCRIBED_EVENT_TYPES),
        )

    def unsubscribe_from_events(self) -> None:
        """Deregister from all subscribed event types."""
        bus = get_event_bus()
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.unregister_subscriber(event_type, self.process_event)
        self._registered = False

    def process_event(self, event: DomainEvent) -> None:
        """Handle an incoming domain event — main subscriber callback.

        REQ-L3-WHOOK-002 (load configs), REQ-L3-WHOOK-003 (payload),
        REQ-L3-WHOOK-005 (retry). Tenant isolation via workspace_id matching.

        Args:
            event: The domain event from the DomainEventBus.
        """
        if event.event_type not in SUBSCRIBED_EVENT_TYPES:
            return  # ignore unsubscribed types

        subscriptions = self._load_webhook_configs(
            workspace_id=event.workspace_id,
            event_type=event.event_type,
        )

        if not subscriptions:
            return  # no webhooks configured → nothing to do

        payload_bytes = self._build_payload(event)

        for subscription in subscriptions:
            self._dispatch_with_retry(
                subscription=subscription,
                event=event,
                payload_bytes=payload_bytes,
            )

    # ---------- Private: config loading ----------

    @staticmethod
    def _load_webhook_configs(workspace_id: UUID, event_type: str) -> List[Any]:
        """Fetch enabled WebhookSubscriptions matching workspace + event_type.

        IF-AS-EXT-OUT-007. REQ-L3-WHOOK-002, REQ-L3-WHOOK-009 (tenant isolation).
        """
        from application.models import WebhookSubscription

        all_subs = WebhookSubscription.objects.filter(
            workspace_id=workspace_id,
            enabled=True,
        )
        matching = []
        for sub in all_subs:
            if event_type in sub.get_event_types_list():
                matching.append(sub)
        return matching

    # ---------- Private: payload construction ----------

    @staticmethod
    def _build_payload(event: DomainEvent) -> bytes:
        """Construct the JSON webhook payload.

        REQ-L3-WHOOK-003: event_type, entity_id, workspace_id, timestamp.
        """
        # timezone is imported at module level to allow test mocking.
        data = {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "entity_id": str(event.entity_id),
            "workspace_id": str(event.workspace_id),
            "timestamp": timezone.now().isoformat(),
            "payload": event.payload,
        }
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _compute_signature(payload_bytes: bytes, secret: str) -> str:
        """Compute HMAC-SHA256 signature for the payload.

        REQ-L3-WHOOK-004. Format: "sha256=<hex_digest>".
        """
        mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
        return f"sha256={mac.hexdigest()}"

    # ---------- Private: HTTP dispatch ----------

    @staticmethod
    def _already_delivered(subscription: Any, event: DomainEvent) -> bool:
        """Return True if this (subscription, event) was already delivered (REQ-072).

        Idempotency guard for at-least-once outbox dispatch: a prior successful
        WebhookDeliveryLog for the same event means the webhook must not be
        re-sent on redelivery.
        """
        from application.models import WebhookDeliveryLog

        return WebhookDeliveryLog.objects.filter(
            subscription=subscription,
            event_id=event.event_id,
            success=True,
        ).exists()

    def _dispatch_with_retry(
        self,
        subscription: Any,
        event: DomainEvent,
        payload_bytes: bytes,
    ) -> None:
        """Send HTTP POST with exponential back-off retry.

        REQ-L3-WHOOK-005 (retry), REQ-L3-WHOOK-006 (status semantics),
        REQ-L3-WHOOK-008 (DLQ on exhaustion).

        TODO-ASYNC: This runs synchronously. Future: enqueue as Celery task.
        """
        from application.models import WebhookDeliveryLog

        # REQ-072: outbox dispatch is at-least-once, so process_event may run
        # again for the same event (e.g. worker crash after HTTP send but before
        # the outbox row is marked published). Skip re-delivery when this exact
        # (subscription, event) was already delivered successfully — makes the
        # handler idempotent and prevents duplicate webhook calls.
        if self._already_delivered(subscription, event):
            logger.info(
                "WebhookDispatcher: skip re-delivery of event=%s to url=%s "
                "(already delivered — idempotent)",
                event.event_type,
                subscription.url,
            )
            return

        last_error = ""
        for attempt in range(1, _MAX_RETRIES + 1):
            status_code, success, error_msg = self._send_http_post(
                url=subscription.url,
                payload_bytes=payload_bytes,
                secret=subscription.secret,
            )

            # Log attempt
            is_final = attempt == _MAX_RETRIES
            is_dead = not success and is_final

            try:
                WebhookDeliveryLog.objects.create(
                    subscription=subscription,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    attempt=attempt,
                    status_code=status_code,
                    success=success,
                    error_message=error_msg,
                    is_dead_letter=is_dead,
                )
            except Exception:
                logger.exception(
                    "WebhookDispatcher: failed to write delivery log "
                    "subscription=%s attempt=%d",
                    subscription.id,
                    attempt,
                )

            if success:
                logger.info(
                    "WebhookDispatcher: delivered event=%s to url=%s attempt=%d",
                    event.event_type,
                    subscription.url,
                    attempt,
                )
                return

            last_error = error_msg
            logger.warning(
                "WebhookDispatcher: attempt %d/%d failed for event=%s url=%s: %s",
                attempt,
                _MAX_RETRIES,
                event.event_type,
                subscription.url,
                error_msg,
            )

            # REQ-L3-WHOOK-006: 4xx → permanent failure, no retry
            if status_code is not None and 400 <= status_code < 500:
                logger.error(
                    "WebhookDispatcher: permanent client error %d for url=%s "
                    "event=%s — no retry",
                    status_code,
                    subscription.url,
                    event.event_type,
                )
                return

            if not is_final:
                sleep_sec = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
                time.sleep(sleep_sec)

        logger.error(
            "WebhookDispatcher: exhausted retries for event=%s url=%s: %s — "
            "marked as dead letter",
            event.event_type,
            subscription.url,
            last_error,
        )

    def _send_http_post(
        self,
        url: str,
        payload_bytes: bytes,
        secret: str,
    ) -> tuple[Optional[int], bool, str]:
        """Perform a single HTTP POST.

        Returns:
            (status_code, success, error_message)
            success=True iff status_code is 2xx.
        """
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ReqogniLoom-WebhookDispatcher/1.0",
        }

        if secret:
            headers["X-Webhook-Signature"] = self._compute_signature(payload_bytes, secret)

        req = urllib.request.Request(
            url=url,
            data=payload_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                status_code = resp.status
                success = 200 <= status_code < 300
                return status_code, success, ""
        except urllib.error.HTTPError as exc:
            return exc.code, False, f"HTTP {exc.code}: {exc.reason}"
        except urllib.error.URLError as exc:
            return None, False, f"URLError: {exc.reason}"
        except Exception as exc:
            return None, False, str(exc)


# ---------- Module-level singleton ----------

_dispatcher_instance: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Return the process-singleton WebhookDispatcher instance."""
    global _dispatcher_instance
    if _dispatcher_instance is None:
        _dispatcher_instance = WebhookDispatcher()
    return _dispatcher_instance


__all__ = [
    "WebhookDispatcher",
    "SUBSCRIBED_EVENT_TYPES",
    "get_webhook_dispatcher",
]
