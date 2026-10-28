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


_QDRANT_ACTIVE = {"requested": "qdrant", "active": "qdrant", "reason": ""}
_PGVECTOR_ACTIVE = {"requested": "pgvector", "active": "pgvector", "reason": ""}


def _patch_artifact_backend(monkeypatch: pytest.MonkeyPatch, diagnostic: dict) -> None:
    """Pin what the artifact port reports as its ACTIVE backend."""
    monkeypatch.setattr(
        "application.vector_port.vector_backend_diagnostic", lambda: dict(diagnostic)
    )


def _patch_index_stats(monkeypatch: pytest.MonkeyPatch, stats: dict) -> None:
    monkeypatch.setattr(
        "reqogniloom.health._qdrant_artifact_index_stats", lambda: dict(stats)
    )


class TestQdrantArtifactIndexAdvisories:
    """T-A2-9: ``qdrant_artifact_points`` / ``qdrant_sparse_ready``.

    The ``..._artifacts_v2`` collections are the semantic-search corpus once the
    artifact port runs on Qdrant, and an empty one answers "no results" instead
    of erroring — so the documented rollout rule (backfill with ``failed: 0``
    BEFORE the switch) needs to be readable from the probe. Both advisories are
    published ONLY while the artifact backend actually is Qdrant: the default
    pgvector payload must stay byte-identical.
    """

    @staticmethod
    def _collect(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, list[str]]:
        from reqogniloom.health import _collect_advisory

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        advisory: dict[str, str] = {}
        warnings: list[str] = []
        _collect_advisory(advisory, warnings, db_ok=False)
        return advisory, warnings

    def test_default_pgvector_payload_has_no_qdrant_index_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No Qdrant selected => the probe must not even run."""

        def _must_not_run() -> dict:
            raise AssertionError("the Qdrant index probe ran on a pgvector deployment")

        _patch_artifact_backend(monkeypatch, _PGVECTOR_ACTIVE)
        monkeypatch.setattr(
            "reqogniloom.health._qdrant_artifact_index_stats", _must_not_run
        )

        advisory, _warnings = self._collect(monkeypatch)

        assert "qdrant_artifact_points" not in advisory
        assert "qdrant_sparse_ready" not in advisory

    def test_qdrant_active_publishes_counts_and_sparse_readiness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_artifact_backend(monkeypatch, _QDRANT_ACTIVE)
        _patch_index_stats(
            monkeypatch,
            {"collections": "2", "points": "2338", "sparse_ready": "true"},
        )

        advisory, warnings = self._collect(monkeypatch)

        assert advisory["qdrant_artifact_points"] == "collections=2,points=2338"
        assert advisory["qdrant_sparse_ready"] == "true"
        # Two aggregate counts are not a defect signal.
        assert not any("artifact index" in warning for warning in warnings)

    def test_missing_sparse_config_is_reported_false_not_hidden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_artifact_backend(monkeypatch, _QDRANT_ACTIVE)
        _patch_index_stats(
            monkeypatch,
            {"collections": "1", "points": "10", "sparse_ready": "false"},
        )

        advisory, _warnings = self._collect(monkeypatch)

        assert advisory["qdrant_sparse_ready"] == "false"

    def test_probe_failure_is_a_warning_and_never_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreachable Qdrant is an operator signal, not a 503."""

        def _boom() -> dict:
            raise RuntimeError("qdrant unreachable: ConnectionError")

        _patch_artifact_backend(monkeypatch, _QDRANT_ACTIVE)
        monkeypatch.setattr("reqogniloom.health._qdrant_artifact_index_stats", _boom)

        advisory, warnings = self._collect(monkeypatch)

        assert "qdrant_artifact_points" not in advisory
        assert "qdrant_sparse_ready" not in advisory
        assert any("artifact index probe failed" in warning for warning in warnings)
        # CWE-209: the raw client error never reaches the anonymous body.
        assert not any("ConnectionError" in warning for warning in warnings)


class TestQdrantAdvisoryHttpVerboseGate:
    """HTTP level: the key advisories are ``?verbose=1`` only (T-A2-9/#1437).

    The warning TEXT is deliberately unconditional (the operator signal), so the
    gate is asserted on the advisory keys, not on the headings a monitor needs.
    """

    @staticmethod
    def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
        from reqogniloom import health

        monkeypatch.setattr(
            health,
            "_run_required_checks",
            lambda: {name: "ok" for name in health._REQUIRED_CHECK_NAMES},
        )
        # Unrelated DB-backed advisories: keep the payload deterministic and the
        # test independent of the migrated corpus.
        monkeypatch.setattr(health, "_embedding_dimension_mismatches", lambda: [])
        monkeypatch.setattr(
            "application.vector_port.vector_backend_diagnostic",
            lambda: dict(_QDRANT_ACTIVE),
        )
        monkeypatch.setattr(
            health,
            "_qdrant_artifact_index_stats",
            lambda: {"collections": "1", "points": "7", "sparse_ready": "true"},
        )
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        # Qdrant is the configured artifact store in production, with no key.
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", "qdrant")
        monkeypatch.setattr("memory.checks._django_env", lambda: "production")
        monkeypatch.delenv("QDRANT_API_KEY", raising=False)

    def test_keys_are_absent_without_verbose(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._configure(monkeypatch)

        response = Client().get("/health/")
        advisory = response.json()["advisory"]

        assert response.status_code == 200
        assert "qdrant_api_key" not in advisory
        assert "qdrant_api_key_missing" not in advisory
        # The aggregate index counts are NOT gated: they name no tenant/workspace.
        assert advisory["qdrant_artifact_points"] == "collections=1,points=7"

    def test_keys_are_present_with_verbose(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._configure(monkeypatch)

        response = Client().get("/health/?verbose=1")
        advisory = response.json()["advisory"]

        assert response.status_code == 200
        assert advisory["qdrant_api_key"] == "missing"
        assert advisory["qdrant_api_key_missing"] == "true"
