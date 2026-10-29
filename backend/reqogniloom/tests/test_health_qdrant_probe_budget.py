"""Regression: the unauthenticated Qdrant artifact probe must stay bounded.

``GET /health/`` is the compose healthcheck (``interval: 30s``) and is
reachable without authentication; the backend port is published. The
artifact-index probe used to issue ``1 + 2N`` authenticated Qdrant calls *per
request* (``get_collections`` plus a ``count`` and a ``get_collection`` per
collection), each with the 5 s ``DEFAULT_QDRANT_TIMEOUT`` and no cache. That
turned an anonymous HTTP request into a fan-out against the shared store and
could hang a worker past Gunicorn's ``--timeout``; a slow or partitioned Qdrant
could also make the container unhealthy although the service itself works.

These tests pin the three properties of the fix:

* a second request inside the TTL performs **no** additional Qdrant calls,
* a slow Qdrant degrades to an advisory warning (HTTP 200, never ``degraded``),
* the "holds no points" log line waits for the second consecutive zero.
"""
from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

_COLLECTION = (
    "reqlo_00000000-0000-0000-0000-000000000001_"
    "11111111-1111-1111-1111-111111111111_artifacts_v2"
)


def _collection_response() -> SimpleNamespace:
    return SimpleNamespace(collections=[SimpleNamespace(name=_COLLECTION)])


def _collection_info() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(sparse_vectors={"bm25": SimpleNamespace()})
        )
    )


class _FakeQdrantClient:
    """Minimal Qdrant double that counts the calls it receives."""

    def __init__(self, *, points: int = 42, delay: float = 0.0) -> None:
        self.points = points
        self.delay = delay
        self.calls = 0

    def get_collections(self, **_kwargs) -> SimpleNamespace:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return _collection_response()

    def count(self, **_kwargs) -> SimpleNamespace:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return SimpleNamespace(count=self.points)

    def get_collection(self, **_kwargs) -> SimpleNamespace:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return _collection_info()

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clean_probe_cache() -> None:
    """Keep the module-level TTL cache from leaking across tests."""
    from reqogniloom import health

    health._reset_artifact_probe_cache()
    yield
    health._reset_artifact_probe_cache()


def _configure(monkeypatch: pytest.MonkeyPatch, client: _FakeQdrantClient) -> None:
    """Pin the read-only advisory signals and point the probe at *client*."""
    from reqogniloom import health

    monkeypatch.setattr(
        health,
        "_run_required_checks",
        lambda: {name: "ok" for name in health._REQUIRED_CHECK_NAMES},
    )
    monkeypatch.setattr(health, "_embedding_dimension_mismatches", lambda: [])
    monkeypatch.setattr(health, "_artifact_probe_client", lambda _config: client)
    monkeypatch.setattr(
        "application.vector_port.vector_backend_diagnostic",
        lambda: {"requested": "qdrant", "active": "qdrant", "reason": ""},
    )
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    # The config resolver needs an address; the client seam never dials it.
    monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid:6333")
    monkeypatch.delenv("ARTIFACT_VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)


class TestProbeResultIsCached:
    def test_second_request_inside_the_ttl_makes_no_new_qdrant_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeQdrantClient()
        _configure(monkeypatch, fake)

        first = Client().get("/health/")
        second = Client().get("/health/")

        assert first.status_code == 200
        assert second.status_code == 200
        # get_collections + one count + one get_collection: exactly one round
        # trip, in spite of two anonymous requests.
        assert fake.calls == 3
        assert (
            first.json()["advisory"]["qdrant_artifact_points"]
            == second.json()["advisory"]["qdrant_artifact_points"]
            == "collections=1,points=42"
        )

    def test_cache_is_shared_by_the_ready_and_the_alias_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeQdrantClient()
        _configure(monkeypatch, fake)

        Client().get("/health/ready")
        Client().get("/health/")

        assert fake.calls == 3


class TestSlowQdrantIsAdvisoryOnly:
    def test_deadline_turns_a_slow_store_into_a_warning_not_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom import health

        # A 10 ms budget against a client that takes 50 ms per call: the first
        # step consumes the budget, so the probe aborts before the next call.
        monkeypatch.setattr(health, "QDRANT_ARTIFACT_PROBE_DEADLINE_SECONDS", 0.01)
        fake = _FakeQdrantClient(delay=0.05)
        _configure(monkeypatch, fake)

        started = time.monotonic()
        response = Client().get("/health/")
        elapsed = time.monotonic() - started
        body = response.json()

        # An optional dependency must never become a readiness criterion.
        assert response.status_code == 200
        assert body["status"] != "degraded"
        assert "qdrant_artifact_points" not in body["advisory"]
        assert any("artifact index probe failed" in w for w in body["warnings"])
        # One bounded client call, not a 5 s-per-collection fan-out.
        assert fake.calls == 1
        assert elapsed < 2.0

    def test_failure_is_cached_so_a_flapping_store_is_not_hammered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom import health

        monkeypatch.setattr(health, "QDRANT_ARTIFACT_PROBE_DEADLINE_SECONDS", 0.01)
        fake = _FakeQdrantClient(delay=0.05)
        _configure(monkeypatch, fake)

        Client().get("/health/")
        Client().get("/health/")

        # The second request replays the cached failure instead of probing again.
        assert fake.calls == 1


class TestZeroPointsWarningIsTwoStrike:
    def test_first_zero_is_silent_second_zero_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from reqogniloom import health

        fake = _FakeQdrantClient(points=0)
        _configure(monkeypatch, fake)

        with caplog.at_level(logging.WARNING, logger="reqogniloom.health"):
            Client().get("/health/")
            assert "holds no points" not in caplog.text

            # Expire only the TTL entry: the streak is the state under test.
            health._artifact_probe_cache = None
            Client().get("/health/")

        assert "holds no points" in caplog.text
