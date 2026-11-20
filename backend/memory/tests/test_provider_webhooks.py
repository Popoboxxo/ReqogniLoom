"""Generic provider webhook receiver (P3).

The dedicated Honcho route keeps its contract (covered by
``test_memory_webhooks.py``); this pins the provider-neutral route: an unknown
provider or one that does not declare ``capabilities.webhooks`` is a 404, and
the receiver is unauthenticated because the provider credential lives inside
``verify_webhook``.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_unknown_provider_is_404() -> None:
    response = APIClient().post(
        "/api/v1/memory/webhooks/does-not-exist/",
        data=b"{}",
        content_type="application/json",
    )

    assert response.status_code == 404


def test_provider_without_webhook_capability_is_404() -> None:
    # pgvector is registered but declares webhooks=False.
    response = APIClient().post(
        "/api/v1/memory/webhooks/pgvector/",
        data=b"{}",
        content_type="application/json",
    )

    assert response.status_code == 404


def test_generic_receiver_is_unauthenticated_and_throttled() -> None:
    from memory.memory_rest import MemoryProviderWebhookView

    assert MemoryProviderWebhookView.authentication_classes == []
    assert MemoryProviderWebhookView.throttle_classes, (
        "the generic receiver must be rate-limited like the Honcho one"
    )


def test_honcho_declares_its_webhook_route_and_capability() -> None:
    from memory.backends import MEMORY_BACKEND_REGISTRY

    honcho = MEMORY_BACKEND_REGISTRY["honcho"]

    assert honcho.capabilities.webhooks is True
    assert honcho.webhook_route.__qualname__.endswith("HonchoMemoryBackend.webhook_route")
