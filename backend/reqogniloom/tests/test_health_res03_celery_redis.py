"""RES-03 x Celery x Redis — W1 cross-branch integration.

``test_health_contract_adr010.py`` pins the HTTP shape with
``_run_required_checks`` stubbed; ``test_celery_beat_heartbeat.py`` pins the
heartbeat store and ``_check_celery_beat`` in isolation. Neither ties the
*real* beat probe to the readiness contract, so a regression that disconnected
the heartbeat store from ``/health/ready`` — or that let a non-``ok`` beat
status read as healthy — would leave both files green.

These tests drive the real ``admin_ops.health_rest._check_celery_beat`` against
the real Django cache through the real ``reqogniloom.health`` aggregation, and
assert the resulting readiness status / dependency list. The worker probe is
stubbed because ``settings_test`` pins ``CELERY_BROKER_URL = "memory://"``
(there is no live worker in the unit-test process).

The Redis probe is normally stubbed too, but the container test overlay runs a
real ``redis`` service (``testing/docker-compose.test.yml`` declares it a hard
dependency and exports ``CELERY_BROKER_URL=redis://redis:6379/0``). The
``*_real_redis_*`` tests below therefore drive the *real* ``_check_redis`` PING
against that live Redis and assert the readiness contract name ``cache``, which
no stubbed test can prove. They skip when no live broker is configured (a bare
host ``pytest`` run) and run under the documented ``backend-test`` overlay.
"""
from __future__ import annotations

import os
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
    monkeypatch: pytest.MonkeyPatch,
    *,
    redis_ok: bool = True,
    stub_redis: bool = True,
) -> None:
    """Pin every readiness probe that needs live infra, except ``celery_beat``.

    ``celery_beat`` deliberately stays REAL — it is the probe under test. The
    database and memory-backend probes are health-faked so the payload's
    dependency list is decided only by the cache/celery state this test
    controls, instead of by whatever the shared test DB happens to contain.

    ``stub_redis=False`` leaves ``_check_redis`` real (it PINGs the live Redis
    named by ``settings.CELERY_BROKER_URL``); the real-Redis tests below set
    that setting themselves. ``redis_ok`` is only consulted while stubbing.
    """
    from admin_ops import health_rest

    if stub_redis:
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


# ---------------------------------------------------------------------------
# Real Redis probe (RES-03 x Redis)
#
# Every test above stubs ``_check_redis``; these drive the real PING so a
# regression in the probe itself (bad URL handling, a PING that swallows a
# refusal) or in its wiring into the readiness contract cannot stay green. They
# require the live Redis of the container test overlay and skip elsewhere.
# ---------------------------------------------------------------------------


def _live_broker_url() -> str | None:
    """Return the live broker URL from the test overlay, or ``None``.

    ``settings_test`` overrides ``CELERY_BROKER_URL`` to ``memory://``, so the
    deployment value is read from the environment the overlay exports. A bare
    host ``pytest`` run has no such value and skips these tests.
    """
    url = os.environ.get("CELERY_BROKER_URL", "")
    if not url or url.startswith("memory://"):
        return None
    return url


@pytest.mark.django_db
def test_real_redis_probe_drives_readiness_cache(monkeypatch, settings) -> None:
    """RES-03 x Redis: the real probe's ``ok`` becomes readiness ``cache: ok``."""
    from admin_ops import health_rest
    from reqogniloom import health

    broker_url = _live_broker_url()
    if broker_url is None:
        pytest.skip("requires a live Redis broker (CELERY_BROKER_URL)")

    settings.CELERY_BROKER_URL = broker_url
    _isolate_dependencies(monkeypatch, stub_redis=False)
    heartbeat.record_heartbeat()

    row = health_rest._check_redis()
    assert row == {"name": "redis", "status": "ok", "detail": "PING ok"}, row

    payload, http_status = health._readiness_payload()

    assert http_status == 200
    assert payload["checks"]["cache"] == "ok"
    assert payload["dependencies"] == []


@pytest.mark.django_db
def test_real_redis_probe_refusal_degrades_readiness(monkeypatch, settings) -> None:
    """RES-03 x Redis: a refused real PING degrades readiness through ``cache``."""
    from reqogniloom import health

    if _live_broker_url() is None:
        pytest.skip("requires the overlay's Redis configuration")

    # Port 1 on loopback refuses immediately, so the real probe's failure path
    # runs without waiting out the 1s socket timeout.
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:1/0"
    _isolate_dependencies(monkeypatch, stub_redis=False)
    heartbeat.record_heartbeat()

    payload, http_status = health._readiness_payload()

    assert http_status == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["cache"] == "error"
    assert "cache" in _dependency_names(payload)
