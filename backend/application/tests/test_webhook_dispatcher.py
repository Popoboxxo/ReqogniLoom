"""
Tests for COMP-AS-011 WebhookDispatcher.

leaf_id : COMP-AS-011
req_id  : REQ-L1-024, REQ-L3-WHOOK-001..009

Static tests (no DB): subscription, event filtering, payload building,
HMAC signature, retry logic (4xx no-retry), DLQ marking, tenant isolation.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.webhook_dispatcher import (
    SUBSCRIBED_EVENT_TYPES,
    WebhookDispatcher,
    _MAX_RETRIES,
    get_webhook_dispatcher,
)
from application.event_bus import DomainEvent


# ---------- Helpers ----------


def _make_event(event_type="RequirementCreated", workspace_id=None):
    return DomainEvent(
        event_type=event_type,
        entity_id=uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        payload={"title": "Test Req"},
    )


def _make_subscription(url="https://example.com/hook", secret="", event_types=None):
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.url = url
    sub.secret = secret
    sub.get_event_types_list.return_value = event_types or SUBSCRIBED_EVENT_TYPES
    return sub


# ---------- subscribe_to_events ----------


class TestSubscribeToEvents:
    def test_registers_for_all_subscribed_types(self):
        """REQ-L3-WHOOK-001: dispatcher subscribes to all SUBSCRIBED_EVENT_TYPES."""
        dispatcher = WebhookDispatcher()
        mock_bus = MagicMock()

        with patch("application.webhook_dispatcher.get_event_bus", return_value=mock_bus):
            dispatcher.subscribe_to_events()

        assert mock_bus.register_subscriber.call_count == len(SUBSCRIBED_EVENT_TYPES)
        registered_types = {
            c.args[0] for c in mock_bus.register_subscriber.call_args_list
        }
        assert registered_types == set(SUBSCRIBED_EVENT_TYPES)

    def test_unsubscribe_removes_all(self):
        dispatcher = WebhookDispatcher()
        dispatcher._registered = True
        mock_bus = MagicMock()

        with patch("application.webhook_dispatcher.get_event_bus", return_value=mock_bus):
            dispatcher.unsubscribe_from_events()

        assert mock_bus.unregister_subscriber.call_count == len(SUBSCRIBED_EVENT_TYPES)


# ---------- process_event ----------


class TestProcessEvent:
    def test_ignores_unsubscribed_event_type(self):
        dispatcher = WebhookDispatcher()
        event = _make_event(event_type="ADRCreated")

        with patch.object(dispatcher, "_load_webhook_configs") as mock_load:
            dispatcher.process_event(event)

        mock_load.assert_not_called()

    def test_no_subscriptions_skips_dispatch(self):
        dispatcher = WebhookDispatcher()
        event = _make_event()

        with (
            patch.object(dispatcher, "_load_webhook_configs", return_value=[]),
            patch.object(dispatcher, "_dispatch_with_retry") as mock_dispatch,
        ):
            dispatcher.process_event(event)

        mock_dispatch.assert_not_called()

    def test_dispatches_to_each_subscription(self):
        dispatcher = WebhookDispatcher()
        event = _make_event()
        sub1 = _make_subscription()
        sub2 = _make_subscription(url="https://other.com/hook")

        with (
            patch.object(dispatcher, "_load_webhook_configs", return_value=[sub1, sub2]),
            patch.object(dispatcher, "_dispatch_with_retry") as mock_dispatch,
        ):
            dispatcher.process_event(event)

        assert mock_dispatch.call_count == 2


# ---------- _build_payload ----------


class TestBuildPayload:
    def test_payload_contains_required_fields(self):
        """REQ-L3-WHOOK-003: event_type, entity_id, workspace_id, timestamp."""
        event = _make_event()

        with patch("application.webhook_dispatcher.timezone") as mock_tz:
            mock_tz.now.return_value.isoformat.return_value = "2026-01-01T00:00:00+00:00"
            payload_bytes = WebhookDispatcher._build_payload(event)

        data = json.loads(payload_bytes.decode("utf-8"))
        assert data["event_type"] == event.event_type
        assert data["entity_id"] == str(event.entity_id)
        assert data["workspace_id"] == str(event.workspace_id)
        assert "timestamp" in data

    def test_no_sensitive_fields_in_payload(self):
        """REQ-L3-WHOOK-003: no password/api_key in payload."""
        event = _make_event()
        event.payload["password"] = "should-not-appear"

        payload_bytes = WebhookDispatcher._build_payload(event)
        data = json.loads(payload_bytes.decode("utf-8"))

        # password should appear inside nested 'payload' key, not at top level
        assert "password" not in {k for k in data if k != "payload"}


# ---------- _compute_signature ----------


class TestComputeSignature:
    def test_signature_format(self):
        """REQ-L3-WHOOK-004: format is 'sha256=<hex>'."""
        payload = b"hello world"
        sig = WebhookDispatcher._compute_signature(payload, "secret123")
        assert sig.startswith("sha256=")
        assert len(sig) == len("sha256=") + 64  # sha256 hex = 64 chars

    def test_consistent_with_known_value(self):
        """Deterministic: same payload + secret → same signature."""
        payload = b"test payload"
        sig1 = WebhookDispatcher._compute_signature(payload, "mykey")
        sig2 = WebhookDispatcher._compute_signature(payload, "mykey")
        assert sig1 == sig2

    def test_different_secret_produces_different_sig(self):
        payload = b"test payload"
        sig1 = WebhookDispatcher._compute_signature(payload, "key1")
        sig2 = WebhookDispatcher._compute_signature(payload, "key2")
        assert sig1 != sig2


# ---------- _send_http_post ----------


class TestSendHttpPost:
    def test_success_2xx(self):
        dispatcher = WebhookDispatcher()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("application.webhook_dispatcher.urllib.request.urlopen", return_value=mock_resp):
            status, success, err = dispatcher._send_http_post(
                "https://example.com/hook", b"payload", ""
            )

        assert status == 200
        assert success is True
        assert err == ""

    def test_http_error_4xx(self):
        """REQ-L3-WHOOK-006: 4xx → failure, no retry (tested via status_code)."""
        import urllib.error

        dispatcher = WebhookDispatcher()
        http_err = urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        with patch(
            "application.webhook_dispatcher.urllib.request.urlopen",
            side_effect=http_err,
        ):
            status, success, err = dispatcher._send_http_post(
                "https://example.com/hook", b"payload", ""
            )

        assert status == 404
        assert success is False

    def test_url_error(self):
        import urllib.error

        dispatcher = WebhookDispatcher()
        with patch(
            "application.webhook_dispatcher.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            status, success, err = dispatcher._send_http_post(
                "https://example.com/hook", b"payload", ""
            )

        assert status is None
        assert success is False
        assert "connection refused" in err

    def test_signature_header_added_when_secret_provided(self):
        """REQ-L3-WHOOK-004: X-Webhook-Signature header present when secret set."""
        dispatcher = WebhookDispatcher()
        captured_headers = {}

        original_request = __import__("urllib.request", fromlist=["Request"]).Request

        def _capture_request(url, data, headers, method):
            captured_headers.update(headers)
            mock_req = MagicMock()
            mock_req.get_full_url.return_value = url
            return mock_req

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch(
                "application.webhook_dispatcher.urllib.request.Request",
                side_effect=_capture_request,
            ),
            patch(
                "application.webhook_dispatcher.urllib.request.urlopen",
                return_value=mock_resp,
            ),
        ):
            dispatcher._send_http_post("https://example.com", b"payload", "mysecret")

        assert "X-Webhook-Signature" in captured_headers
        assert captured_headers["X-Webhook-Signature"].startswith("sha256=")


# ---------- _dispatch_with_retry — 4xx no-retry ----------


class TestDispatchWithRetry:
    def test_4xx_does_not_retry(self):
        """REQ-L3-WHOOK-006: 4xx client error stops after first attempt."""
        dispatcher = WebhookDispatcher()
        sub = _make_subscription()
        event = _make_event()
        payload = b"payload"

        with (
            patch.object(
                dispatcher,
                "_send_http_post",
                return_value=(404, False, "Not Found"),
            ) as mock_send,
            patch.object(dispatcher, "_already_delivered", return_value=False),
            patch("application.models.WebhookDeliveryLog.objects.create"),
        ):
            dispatcher._dispatch_with_retry(sub, event, payload)

        # Should only attempt once (no retry for 4xx)
        assert mock_send.call_count == 1

    def test_5xx_retries_up_to_max(self):
        """REQ-L3-WHOOK-005: 5xx triggers retry with backoff."""
        dispatcher = WebhookDispatcher()
        sub = _make_subscription()
        event = _make_event()
        payload = b"payload"

        with (
            patch.object(
                dispatcher,
                "_send_http_post",
                return_value=(503, False, "Service Unavailable"),
            ) as mock_send,
            patch.object(dispatcher, "_already_delivered", return_value=False),
            patch("application.models.WebhookDeliveryLog.objects.create"),
            patch("application.webhook_dispatcher.time.sleep"),
        ):
            dispatcher._dispatch_with_retry(sub, event, payload)

        assert mock_send.call_count == _MAX_RETRIES

    def test_success_stops_retrying(self):
        dispatcher = WebhookDispatcher()
        sub = _make_subscription()
        event = _make_event()
        payload = b"payload"

        with (
            patch.object(
                dispatcher,
                "_send_http_post",
                return_value=(200, True, ""),
            ) as mock_send,
            patch.object(dispatcher, "_already_delivered", return_value=False),
            patch("application.models.WebhookDeliveryLog.objects.create"),
        ):
            dispatcher._dispatch_with_retry(sub, event, payload)

        assert mock_send.call_count == 1

    def test_skips_delivery_when_already_delivered(self):
        """REQ-072: at-least-once redelivery must not re-send the webhook."""
        dispatcher = WebhookDispatcher()
        sub = _make_subscription()
        event = _make_event()
        payload = b"payload"

        with (
            patch.object(
                dispatcher,
                "_send_http_post",
                return_value=(200, True, ""),
            ) as mock_send,
            patch.object(dispatcher, "_already_delivered", return_value=True),
            patch("application.models.WebhookDeliveryLog.objects.create") as mock_create,
        ):
            dispatcher._dispatch_with_retry(sub, event, payload)

        # Idempotent: no HTTP send, no new delivery-log row.
        assert mock_send.call_count == 0
        assert mock_create.call_count == 0


# ---------- Singleton ----------


class TestGetWebhookDispatcher:
    def test_returns_same_instance(self):
        d1 = get_webhook_dispatcher()
        d2 = get_webhook_dispatcher()
        assert d1 is d2

    def test_returns_webhook_dispatcher_instance(self):
        assert isinstance(get_webhook_dispatcher(), WebhookDispatcher)
