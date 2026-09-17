"""
REQ-106 — Tests for per-tenant token usage tracking, aggregation and daily limits.

Covers:
    - Persisting a TokenUsageRecord after a successful call (best-effort).
    - Aggregation over a rolling window (total + per-provider breakdown).
    - Daily-limit detection driven by ``settings.TENANT_TOKEN_LIMIT_PER_DAY``.
    - CapabilityRouter returning a structured 429 error when the limit is hit.
    - CapabilityRouter recording usage after a successful sync call.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from llm_adapter import token_tracking
from llm_adapter.interface import LlmResult
from llm_adapter.router import CapabilityRouter
from llm_adapter.token_tracking import (
    LLM_TOKEN_LIMIT_EXCEEDED,
    aggregate_usage,
    get_daily_usage,
    is_over_daily_limit,
    record_token_usage,
)
from persistence.models import Tenant, TokenUsageRecord
from persistence.tenancy import TenantContext

# Note (#360): TenantContext cleanup between tests is now handled by the
# autouse ``_clear_tenant_context`` fixture in the root ``backend/conftest.py``
# (applies to every test module in the suite, not just this file). Do not
# re-add a local duplicate here.


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant TT", slug="tenant-tt")


def _seed(tenant: Tenant, *, provider: str, total: int) -> TokenUsageRecord:
    """Create one usage record (total stored in input_tokens) for ``tenant``."""
    TenantContext.set_tenant(tenant.id)
    try:
        return TokenUsageRecord.objects.create(
            provider=provider,
            capability="validate_artifact",
            input_tokens=total,
            output_tokens=0,
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_record_token_usage_persists_row(tenant: Tenant) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        record_token_usage(
            provider="mock",
            capability="validate_artifact",
            input_tokens=42,
            output_tokens=8,
        )
        rows = list(TokenUsageRecord.objects.all())
    finally:
        TenantContext.clear_tenant()

    assert len(rows) == 1
    assert rows[0].provider == "mock"
    assert rows[0].input_tokens == 42
    assert rows[0].output_tokens == 8
    assert rows[0].total_tokens == 50


@pytest.mark.django_db
def test_record_token_usage_without_context_is_safe() -> None:
    # No tenant context set → best-effort recorder must not raise.
    record_token_usage(provider="mock", capability="validate_artifact", input_tokens=10)
    # Nothing recorded because there is no tenant to attribute it to.
    assert TokenUsageRecord.unscoped.count() == 0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_aggregate_usage_sums_by_provider(tenant: Tenant) -> None:
    _seed(tenant, provider="mock", total=100)
    _seed(tenant, provider="mock", total=50)
    _seed(tenant, provider="anthropic", total=200)

    TenantContext.set_tenant(tenant.id)
    try:
        summary = aggregate_usage(days=30)
        daily = get_daily_usage(days=1)
    finally:
        TenantContext.clear_tenant()

    assert summary["total_tokens"] == 350
    assert summary["by_provider"]["mock"] == 150
    assert summary["by_provider"]["anthropic"] == 200
    assert daily == 350


@pytest.mark.django_db
def test_get_daily_usage_excludes_old_records(tenant: Tenant) -> None:
    recent = _seed(tenant, provider="mock", total=30)
    old = _seed(tenant, provider="mock", total=999)

    # Push the "old" record outside the 24h window (auto_now_add ignores create).
    TenantContext.set_tenant(tenant.id)
    try:
        TokenUsageRecord.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        daily = get_daily_usage(days=1)
    finally:
        TenantContext.clear_tenant()

    assert recent.total_tokens == 30
    assert daily == 30


@pytest.mark.django_db
def test_aggregation_is_tenant_scoped(tenant: Tenant) -> None:
    other = Tenant.objects.create(name="Other", slug="tenant-other")
    _seed(tenant, provider="mock", total=100)
    _seed(other, provider="mock", total=777)

    TenantContext.set_tenant(tenant.id)
    try:
        daily = get_daily_usage(days=1)
    finally:
        TenantContext.clear_tenant()

    assert daily == 100  # other tenant's 777 must not leak in


# ---------------------------------------------------------------------------
# Daily limit detection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_is_over_daily_limit_false_when_unlimited(tenant: Tenant, settings) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = None
    _seed(tenant, provider="mock", total=10_000)
    TenantContext.set_tenant(tenant.id)
    try:
        assert is_over_daily_limit() is False
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_is_over_daily_limit_true_when_exceeded(tenant: Tenant, settings) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
    _seed(tenant, provider="mock", total=150)
    TenantContext.set_tenant(tenant.id)
    try:
        assert is_over_daily_limit() is True
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_is_over_daily_limit_false_when_below(tenant: Tenant, settings) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
    _seed(tenant, provider="mock", total=50)
    TenantContext.set_tenant(tenant.id)
    try:
        assert is_over_daily_limit() is False
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Router enforcement (429) and recording
# ---------------------------------------------------------------------------


def _router_with_mock_provider(monkeypatch, token_usage: int = 42) -> CapabilityRouter:
    """Build a router whose provider is a mock returning a fixed LlmResult."""
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.validate_artifact.return_value = LlmResult(
        score=0.9,
        suggestions=[],
        provider="mock",
        model="mock-model-v1",
        token_usage=token_usage,
    )
    monkeypatch.setattr("llm_adapter.router.get_provider", lambda *a, **k: provider)
    return CapabilityRouter(
        enabled_capabilities={"validate_artifact"},
        audit_logger=MagicMock(),
    )


@pytest.mark.django_db
def test_router_returns_429_when_over_limit(tenant: Tenant, settings, monkeypatch) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
    _seed(tenant, provider="mock", total=150)  # already over the limit
    router = _router_with_mock_provider(monkeypatch)

    TenantContext.set_tenant(tenant.id)
    try:
        result = router.execute_capability("validate_artifact", artifact_id="art-1")
    finally:
        TenantContext.clear_tenant()

    assert isinstance(result, dict)
    assert result["error"]["code"] == LLM_TOKEN_LIMIT_EXCEEDED
    assert result["error"]["http_status"] == 429


@pytest.mark.django_db
def test_router_records_usage_after_successful_call(
    tenant: Tenant, settings, monkeypatch
) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = None
    router = _router_with_mock_provider(monkeypatch, token_usage=42)

    TenantContext.set_tenant(tenant.id)
    try:
        result = router.execute_capability("validate_artifact", artifact_id="art-1")
        rows = list(TokenUsageRecord.objects.all())
    finally:
        TenantContext.clear_tenant()

    assert isinstance(result, LlmResult)
    assert len(rows) == 1
    assert rows[0].input_tokens == 42
    assert rows[0].capability == "validate_artifact"
    assert rows[0].provider == "mock"


@pytest.mark.django_db
def test_router_allows_call_when_under_limit(
    tenant: Tenant, settings, monkeypatch
) -> None:
    settings.TENANT_TOKEN_LIMIT_PER_DAY = 1000
    _seed(tenant, provider="mock", total=100)  # under the limit
    router = _router_with_mock_provider(monkeypatch, token_usage=10)

    TenantContext.set_tenant(tenant.id)
    try:
        result = router.execute_capability("validate_artifact", artifact_id="art-1")
    finally:
        TenantContext.clear_tenant()

    assert isinstance(result, LlmResult)
