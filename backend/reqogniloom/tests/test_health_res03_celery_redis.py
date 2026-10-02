"""RES-03 x Celery x Redis — W1 cross-branch integration.

``test_health_contract_adr010.py`` pins the HTTP shape with
``_run_required_checks`` stubbed; ``test_celery_beat_heartbeat.py`` pins the
heartbeat store and ``_check_celery_beat`` in isolation. Neither ties the
*real* beat probe to the readiness contract, so a regression that disconnected
the heartbeat store from ``/health/ready`` — or that let a non-``ok`` beat
status read as healthy — would leave both files green.

These tests drive the real ``admin_ops.health_rest._check_celery_beat`` against
the real Django cache through the real ``reqogniloom.health`` aggregation, and
assert the resulting readiness status / dependency list. The Redis and worker
probes are stubbed because ``settings_test`` pins
``CELERY_BROKER_URL = "memory://"`` (there is no live Redis in the unit-test
process); the live Redis/beat path is verified against the running stack
separately.
"""
from __future__ import annotations

import time

import pytest
from django.core.cache import cache

from admin_ops import celery_beat_heartbeat as heartbeat


@pytest.fixture(autouse=True)
def _healthy_required_infra() -> None:
    """Neutralise the package conftest's blanket celery-beat stub.

    ``reqogniloom/tests/conftest.py`` pins ``_check_celery_beat`` to ``ok`` for
    every HTTP test in this package. These tests are the deliberate exception:
    they drive the *real* beat probe, so that stub is disabled here and the
    Redis/worker probes are pinned explicitly per test instead.
    """
    yield


@pytest.fixture(autouse=True)
def _clear_heartbeat() -> None:
    """Isolate every test from heartbeat state written by another test."""
    cache.delete(heartbeat.HEARTBEAT_CACHE_KEY)
    yield
    cache.delete(heartbeat.HEARTBEAT_CACHE_KEY)


def _isolate_dependencies(
    monkeypatch: pytest.MonkeyPatch, *, redis_ok: bool = True
) -> None:
    """Pin every readiness probe that needs live infra, except ``celery_beat``.

    ``celery_beat`` deliberately stays REAL — it is the probe under test. The
    database and memory-backend probes are health-faked so the payload's
    dependency list is decided only by the cache/celery state this test
    controls, instead of by whatever the shared test DB happens to contain.
    """
    from admin_ops import health_rest

    monkeypatch.setattr(
        health_rest,
        "_check_redis",
        lambda: {
            "name": "redis",
            "status": "ok" if redis_ok else "down",
            "detail": "PING ok" if redis_ok else "connection refused",
        },
    )
    monkeypatch.setattr(
        health_rest,
        "_check_celery_worker",
        lambda: {"name": "celery_worker", "status": "ok", "detail": "1 worker"},
    )

    class _MemoryBackend:
        @staticmethod
        def health_check():
            return True, "reachable"

    monkeypatch.setattr(
        "memory.backends.get_memory_backend", lambda: _MemoryBackend()
    )
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")


def _dependency_names(payload: dict) -> set[str]:
    return {dep["name"] for dep in payload["dependencies"]}


@pytest.mark.django_db
def test_real_beat_probe_is_wired_into_required_checks(monkeypatch) -> None:
    from reqogniloom import health

    _isolate_dependencies(monkeypatch)

    # No heartbeat recorded yet: the real probe reports "unknown" ...
    assert health._run_required_checks()["celery_beat"] == "unknown"

    # ... and a fresh heartbeat flips it to "ok" through the same cache path.
    heartbeat.record_heartbeat()
    assert health._run_required_checks()["celery_beat"] == "ok"


@pytest.mark.django_db
def test_readiness_degrades_when_beat_heartbeat_is_absent(monkeypatch) -> None:
    from reqogniloom import health

    _isolate_dependencies(monkeypatch)

    payload, http_status = health._readiness_payload()

    assert http_status == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["celery_beat"] == "error"
    assert "celery_beat" in _dependency_names(payload)


@pytest.mark.django_db
def test_readiness_degrades_when_beat_heartbeat_is_stale(monkeypatch) -> None:
    from reqogniloom import health

    _isolate_dependencies(monkeypatch)
    stale = time.time() - (heartbeat.HEARTBEAT_STALE_AFTER_SECONDS + 60)
    cache.set(heartbeat.HEARTBEAT_CACHE_KEY, stale, timeout=3600)

    payload, http_status = health._readiness_payload()

    assert http_status == 503
    assert payload["checks"]["celery_beat"] == "error"
    assert "celery_beat" in _dependency_names(payload)


@pytest.mark.django_db
def test_readiness_is_healthy_when_redis_and_beat_are_ok(monkeypatch) -> None:
    from reqogniloom import health

    _isolate_dependencies(monkeypatch, redis_ok=True)
    heartbeat.record_heartbeat()

    payload, http_status = health._readiness_payload()

    assert http_status == 200
    assert payload["status"] != "degraded"
    assert payload["checks"]["cache"] == "ok"
    assert payload["checks"]["celery_beat"] == "ok"
    assert payload["dependencies"] == []


@pytest.mark.django_db
def test_readiness_degrades_when_the_redis_probe_is_down(monkeypatch) -> None:
    from reqogniloom import health

    _isolate_dependencies(monkeypatch, redis_ok=False)
    heartbeat.record_heartbeat()

    payload, http_status = health._readiness_payload()

    assert http_status == 503
    assert payload["checks"]["cache"] == "error"
    assert "cache" in _dependency_names(payload)
