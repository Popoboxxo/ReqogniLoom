"""Regression: the optional Qdrant backend must never turn readiness red.

ADR-020 §4 makes Qdrant an OPT-IN second vector backend: pgvector stays the
source of truth, and a configured-but-unreachable Qdrant is *degraded* — visible
in the health payload, but never fatal. Before this fix
``reqogniloom.health._run_required_checks`` called the active backend's
``health_check()`` directly and reported *any* failure as ``memory_backend:
"down"``, so ``MEMORY_BACKEND=qdrant`` plus a stopped qdrant container made
``GET /health/ready`` (and the ``/health/`` compose probe) return 503 — the
container healthcheck then marked a perfectly working backend unhealthy
(``admin_ops.health_rest._check_memory_backend`` already mapped this to
``degraded``; only the public readiness path did not).

These tests pin both halves of the contract:

* an optional Qdrant failure => HTTP 200, ``status: degraded``;
* a genuine mandatory failure => HTTP 503, even alongside a degraded Qdrant.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _qdrant_backend(healthy: bool) -> MagicMock:
    """Return a mock that ``isinstance(..., QdrantMemoryBackend)``-passes.

    ``MagicMock(spec=QdrantMemoryBackend)`` mirrors the exact pattern the
    ``admin_ops`` health tests use for the same discrimination.
    """
    from memory.qdrant_backend import QdrantMemoryBackend

    backend = MagicMock(spec=QdrantMemoryBackend)
    backend.health_check.return_value = (
        (True, "qdrant reachable")
        if healthy
        else (False, "qdrant unreachable: ConnectionError")
    )
    return backend


def _patch_memory_backend(monkeypatch: pytest.MonkeyPatch, backend: object) -> None:
    monkeypatch.setattr("memory.backends.get_memory_backend", lambda: backend)
    # Deterministic advisory signals (mock embedding provider, matching columns).
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")


class TestQdrantIsNotAReadinessFailure:
    def test_configured_but_unreachable_qdrant_is_degraded_not_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_memory_backend(monkeypatch, _qdrant_backend(healthy=False))

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 200, (
            "ADR-020 §4: an unreachable optional Qdrant backend must never "
            "fail readiness"
        )
        assert body["status"] == "degraded"
        assert body["checks"]["memory_backend"] == "degraded"
        dependency = next(
            dep for dep in body["dependencies"] if dep["name"] == "memory_backend"
        )
        assert dependency["status"] == "degraded"
        assert dependency["detail"] == "optional_dependency_degraded"
        # CWE-209: the raw probe cause never reaches the anonymous body.
        assert "ConnectionError" not in str(body)

    def test_deprecated_health_alias_is_also_not_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The compose probe hits ``/health/`` — it must stay green too."""
        _patch_memory_backend(monkeypatch, _qdrant_backend(healthy=False))

        response = Client().get("/health/")

        assert response.status_code == 200
        assert response.json()["checks"]["memory_backend"] == "degraded"
        assert response["Deprecation"] == "true"

    def test_run_required_checks_maps_qdrant_failure_to_degraded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import reqogniloom.health as health_module

        _patch_memory_backend(monkeypatch, _qdrant_backend(healthy=False))

        results = health_module._run_required_checks()

        assert results["memory_backend"] == "degraded"
        assert results["database"] == "ok"


class TestGenuineMandatoryFailureStillFailsClosed:
    def test_required_dependency_down_still_503_with_degraded_qdrant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_memory_backend(monkeypatch, _qdrant_backend(healthy=False))
        # A genuinely mandatory dependency is down alongside the degraded
        # optional one: readiness must still fail closed.
        monkeypatch.setattr(
            "admin_ops.health_rest._check_redis",
            lambda: {"name": "redis", "status": "down", "detail": "unreachable"},
        )

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"
        assert body["checks"]["cache"] == "error"
        names = {dep["name"] for dep in body["dependencies"]}
        assert "cache" in names

    def test_non_optional_memory_backend_failure_still_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exception is scoped to Qdrant; pgvector/other stays mandatory."""

        class _RequiredBackend:
            @staticmethod
            def health_check():
                return False, "embed.invalid unreachable"

        _patch_memory_backend(monkeypatch, _RequiredBackend())

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 503
        assert body["checks"]["memory_backend"] == "error"
        dependency = next(
            dep for dep in body["dependencies"] if dep["name"] == "memory_backend"
        )
        assert dependency["detail"] == "dependency_down"

    def test_healthy_qdrant_reports_ok_and_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_memory_backend(monkeypatch, _qdrant_backend(healthy=True))

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["memory_backend"] == "ok"
        assert body["dependencies"] == []
