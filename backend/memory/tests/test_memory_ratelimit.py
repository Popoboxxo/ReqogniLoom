"""Tests for the configurable memory.write ratelimit (RFC #1002 PR B §5)."""
from uuid import uuid4

import pytest
from django.core.cache import cache

from auth_tenancy.context import AuthContext, AuthMethod
from memory.models import SystemMemorySettings
from memory.ratelimit import (
    DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR,
    RATE_LIMIT_ENV_VAR,
    MemoryWriteRateLimitExceeded,
    check_write_rate_limit,
    resolve_write_rate_limit,
)


def _ctx():
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestResolveWriteRateLimit:
    def test_defaults_to_60_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv(RATE_LIMIT_ENV_VAR, raising=False)
        assert resolve_write_rate_limit() == DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR
        assert DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR == 60

    def test_env_value_is_honoured(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "5")
        assert resolve_write_rate_limit() == 5

    def test_env_zero_means_unlimited(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "0")
        assert resolve_write_rate_limit() is None

    def test_unparsable_env_falls_back_to_default_not_unlimited(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "not-a-number")
        assert resolve_write_rate_limit() == DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR

    def test_db_override_wins_over_env(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "5")
        SystemMemorySettings.objects.create(memory_write_rate_limit_per_hour=7)
        assert resolve_write_rate_limit() == 7

    def test_db_zero_override_means_unlimited(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "5")
        SystemMemorySettings.objects.create(memory_write_rate_limit_per_hour=0)
        assert resolve_write_rate_limit() is None


@pytest.mark.django_db
class TestCheckWriteRateLimit:
    def test_unlimited_does_not_increment(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "0")
        ctx = _ctx()
        assert check_write_rate_limit(ctx) == 0

    def test_limit_is_enforced_after_the_configured_count(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "2")
        ctx = _ctx()

        assert check_write_rate_limit(ctx) == 1
        assert check_write_rate_limit(ctx) == 2
        with pytest.raises(MemoryWriteRateLimitExceeded) as excinfo:
            check_write_rate_limit(ctx)

        assert excinfo.value.limit == 2
        assert 0 < excinfo.value.retry_after <= 3600

    def test_counter_is_per_user(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "1")
        first = _ctx()
        second = _ctx()

        check_write_rate_limit(first)
        with pytest.raises(MemoryWriteRateLimitExceeded):
            check_write_rate_limit(first)
        # A different user has their own, fresh counter.
        assert check_write_rate_limit(second) == 1

    def test_cache_failure_is_fail_open(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV_VAR, "1")

        def _boom(*args, **kwargs):
            raise RuntimeError("redis is down")

        monkeypatch.setattr("memory.ratelimit.cache.add", _boom)
        ctx = _ctx()
        # No exception: a cache outage must not block a legitimate write.
        assert check_write_rate_limit(ctx) == 0
