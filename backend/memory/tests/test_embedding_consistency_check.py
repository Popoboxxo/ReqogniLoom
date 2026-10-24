"""T-A0-4: the app <-> Honcho embedding coupling must be loud, never blocking.

Two embedding configurations exist by design (``EMBEDDING_*`` for the app,
``HONCHO_EMBEDDING_*`` for the Honcho memory backend) and T-A0-3 makes the
second inherit the first by default. An explicit override re-opens the gap, and
nothing else notices: both write paths are best-effort, so the only symptom is a
memory vector space that is not comparable to the artifact one.

These tests pin both surfaces of the check:

* :func:`memory.checks.check_honcho_embedding_consistency` — ``manage.py check``
  ids ``memory.W001`` (model) / ``memory.W002`` (width), only when Honcho is the
  effective backend and only for *configured* values;
* ``/health/`` — a single advisory signal, HTTP 200, never ``degraded``.
"""
from __future__ import annotations

import pytest
from django.test import Client

from memory import checks
from memory.checks import (
    EMBEDDING_DIMENSION_MISMATCH,
    EMBEDDING_MODEL_MISMATCH,
    check_honcho_embedding_consistency,
    honcho_embedding_mismatches,
)

pytestmark = pytest.mark.django_db

_REQUIRED_CHECKS = (
    "database",
    "memory_backend",
    "cache",
    "celery_worker",
    "celery_beat",
)


def _configure_honcho(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_model: str = "",
    honcho_model: str = "",
    honcho_dimensions: str | None = None,
) -> None:
    """Set the embedding variables both sides resolve, without inherited noise.

    ``env_file: .env`` in the test stack leaks the deployment's
    ``EMBEDDING_*`` values into the container, so every variable this check reads
    is set explicitly (or deleted) here instead of relying on a default.
    """
    monkeypatch.setenv("MEMORY_BACKEND", "honcho")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", app_model)
    monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", honcho_model)
    if honcho_dimensions is None:
        monkeypatch.delenv("HONCHO_EMBEDDING_VECTOR_DIMENSIONS", raising=False)
    else:
        monkeypatch.setenv("HONCHO_EMBEDDING_VECTOR_DIMENSIONS", honcho_dimensions)


class TestHonchoEmbeddingConsistencyCheck:
    def test_different_model_reports_memory_w001(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(a) A divergent model is the silent-recall-loss case -> memory.W001."""
        _configure_honcho(
            monkeypatch,
            app_model="nomic-embed-text",
            honcho_model="mxbai-embed-large",
        )

        warnings = check_honcho_embedding_consistency()

        assert [warning.id for warning in warnings] == [EMBEDDING_MODEL_MISMATCH]
        assert "nomic-embed-text" in warnings[0].msg
        assert "mxbai-embed-large" in warnings[0].msg
        assert warnings[0].hint, "a warning without a remediation hint is not loud"

    def test_same_model_reports_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) The single-source default (T-A0-3) must stay quiet."""
        _configure_honcho(
            monkeypatch,
            app_model="nomic-embed-text",
            honcho_model="nomic-embed-text",
        )

        assert check_honcho_embedding_consistency() == []

    def test_other_memory_backend_reports_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(c) pgvector runs no Honcho embedding service -> nothing to compare."""
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "nomic-embed-text")
        monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", "mxbai-embed-large")
        monkeypatch.setenv("HONCHO_EMBEDDING_VECTOR_DIMENSIONS", "1536")

        assert check_honcho_embedding_consistency() == []

    def test_different_dimensions_report_memory_w002(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A width divergence is its own id, independent of the model check."""
        _configure_honcho(
            monkeypatch,
            app_model="nomic-embed-text",
            honcho_model="nomic-embed-text",
            honcho_dimensions="1536",
        )
        monkeypatch.setattr(checks, "EMBEDDING_VECTOR_DIMENSIONS", 384)

        warnings = check_honcho_embedding_consistency()

        assert [warning.id for warning in warnings] == [
            EMBEDDING_DIMENSION_MISMATCH
        ]
        assert "384" in warnings[0].msg
        assert "1536" in warnings[0].msg

    def test_unconfigured_values_are_not_a_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Blank means "not configured": no warning, not a false alarm."""
        _configure_honcho(monkeypatch, app_model="", honcho_model="")

        assert honcho_embedding_mismatches() == []
        assert check_honcho_embedding_consistency() == []


class TestHealthEmbeddingModelConsistencyAdvisory:
    def test_mismatch_is_advisory_and_keeps_readiness_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(d) Reported on /health/ as advisory, never as a degraded dependency."""
        monkeypatch.setattr(
            "reqogniloom.health._run_required_checks",
            lambda: {name: "ok" for name in _REQUIRED_CHECKS},
        )
        # Unrelated advisory probe: the physical column width is not what this
        # test is about, and its result depends on the migrated test database.
        monkeypatch.setattr(
            "reqogniloom.health._embedding_dimension_mismatches", lambda: []
        )
        _configure_honcho(
            monkeypatch,
            app_model="nomic-embed-text",
            honcho_model="mxbai-embed-large",
        )

        response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "warning", "advisory only, never degraded"
        assert body["dependencies"] == []
        assert body["checks"]["memory_backend"] == "ok"
        assert body["advisory"]["embedding_model_consistency"].startswith("mismatch:")
        assert any("Honcho" in warning for warning in body["warnings"])
