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
from django.conf import settings
from django.test import Client

from memory import checks
from memory.checks import (
    EMBEDDING_DIMENSION_MISMATCH,
    EMBEDDING_MODEL_MISMATCH,
    QDRANT_API_KEY_MISSING,
    check_honcho_embedding_consistency,
    check_qdrant_api_key,
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


class TestQdrantApiKeyCheck:
    """QR-S23: Qdrant is an unauthenticated store without ``QDRANT_API_KEY``.

    Once ``ARTIFACT_VECTOR_BACKEND=qdrant`` makes Qdrant a *productive* artifact
    store holding tenant content, a production deployment without an API key
    lets every container on the network read and delete all collections. It is
    reported as a ``Warning`` (``memory.W003``), not an ``Error``: the
    deployment still serves, it is merely not authenticated (ENT-A8 = A,
    provisionally a warning).
    """

    @staticmethod
    def _configure(
        monkeypatch: pytest.MonkeyPatch,
        *,
        backend: str = "qdrant",
        django_env: str = "production",
        api_key: str = "",
    ) -> None:
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", backend)
        monkeypatch.setattr(settings, "DJANGO_ENV", django_env)
        if api_key:
            monkeypatch.setenv("QDRANT_API_KEY", api_key)
        else:
            monkeypatch.delenv("QDRANT_API_KEY", raising=False)

    def test_qdrant_without_api_key_warns_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._configure(monkeypatch)

        warnings = check_qdrant_api_key()

        assert [warning.id for warning in warnings] == [QDRANT_API_KEY_MISSING]
        assert QDRANT_API_KEY_MISSING == "memory.W003"
        assert "QDRANT_API_KEY" in warnings[0].msg
        assert warnings[0].hint, "a warning without a remediation hint is not loud"

    def test_api_key_set_reports_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._configure(monkeypatch, api_key="sk-qdrant")

        assert check_qdrant_api_key() == []

    @pytest.mark.parametrize(
        "django_env", ["prod", "staging", "Production", "sandbox", "typo-env"]
    )
    def test_any_env_outside_the_non_production_set_is_production(
        self, monkeypatch: pytest.MonkeyPatch, django_env: str
    ) -> None:
        """Settings treat everything but four values as production (REQ-115).

        ``settings.DEBUG`` is ``DEBUG and DJANGO_ENV in _NON_PROD_ENVS``, so
        ``prod``/``staging``/a typo are production there. A literal
        ``== "production"`` comparison here made exactly those values a silent
        no-warning zone — production reality, no finding, no log.
        """
        self._configure(monkeypatch, django_env=django_env)

        warnings = check_qdrant_api_key()

        assert [warning.id for warning in warnings] == [QDRANT_API_KEY_MISSING]

    @pytest.mark.parametrize(
        "django_env", ["development", "dev", "local", "test", "  DEV  "]
    )
    def test_declared_non_production_envs_report_nothing(
        self, monkeypatch: pytest.MonkeyPatch, django_env: str
    ) -> None:
        """A dev/test stack on an isolated network is the accepted case."""
        self._configure(monkeypatch, django_env=django_env)

        assert check_qdrant_api_key() == []

    def test_db_configured_key_counts_as_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The port resolves the key through SystemMemorySettings, not the env.

        A key configured only in the DB never appears in ``os.environ``; reading
        the env alone reported a false ``memory.W003`` on every probe.
        """
        from memory.models import SystemMemorySettings

        self._configure(monkeypatch)
        row = SystemMemorySettings()
        row.qdrant_api_key = "db-configured-key"
        row.save()

        assert check_qdrant_api_key() == []

    def test_pgvector_backend_reports_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default deployment must stay byte-identical — no new warning."""
        self._configure(monkeypatch, backend="pgvector")

        assert check_qdrant_api_key() == []


class TestCheckRegistration:
    def test_run_checks_reports_memory_w003(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check must be *registered*, not merely importable.

        Without ``memory.apps``'s ``register(check_qdrant_api_key)`` the
        function still passes its own tests while ``manage.py check`` and
        ``migrate`` stay silent — the whole point of a system check.
        """
        from django.core.checks import run_checks

        TestQdrantApiKeyCheck._configure(monkeypatch)

        reported = [
            result for result in run_checks() if result.id == QDRANT_API_KEY_MISSING
        ]

        assert len(reported) == 1


class TestHealthQdrantApiKeyAdvisory:
    def test_missing_key_is_advisory_on_health(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        TestQdrantApiKeyCheck._configure(monkeypatch)
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False, verbose=True)

        assert advisory["qdrant_api_key"] == "missing"
        assert advisory["qdrant_api_key_missing"] == "true"
        assert any("qdrant_api_key_missing" in warning for warning in warnings)

    def test_present_key_is_advisory_ok_on_health(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        TestQdrantApiKeyCheck._configure(monkeypatch, api_key="sk-qdrant")
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False, verbose=True)

        assert advisory["qdrant_api_key"] == "ok"
        assert advisory["qdrant_api_key_missing"] == "false"
        assert not any("qdrant_api_key_missing" in warning for warning in warnings)

    def test_key_advisory_is_verbose_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``/health/`` is unauthenticated: the posture is not published by default.

        The warning stays (it is the operator signal); only the advisory keys
        that would name the soft target are gated behind ``?verbose=1``.
        """
        from reqogniloom.health import _collect_advisory

        TestQdrantApiKeyCheck._configure(monkeypatch)
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False)

        assert "qdrant_api_key" not in advisory
        assert "qdrant_api_key_missing" not in advisory
        assert any("qdrant_api_key_missing" in warning for warning in warnings)


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
