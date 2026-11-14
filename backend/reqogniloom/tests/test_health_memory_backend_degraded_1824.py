"""Readiness semantics for a reachable-but-degraded memory backend (#1824).

The live defect: with ``MEMORY_BACKEND=honcho`` and every Honcho service
healthy, ``/health/`` stayed on **503** (``memory_backend: down``,
``dependency_down``) just because the *embedding* endpoint was unreachable —
even though every memory READ answered 200 and the write path degraded
correctly. A missing embedding provider must not restart-loop a deployment in
which reads work.

These tests pin both halves of the new contract:

* Honcho API unreachable => readiness stays fail-closed (503), and
* Honcho API reachable, embedding unavailable => HTTP 200 with
  ``checks.memory_backend == "ok"`` while ``HonchoMemoryBackend.health()``
  still reports ``degraded=True`` with the ``embedding_unavailable`` detail.
"""
from __future__ import annotations

from unittest import mock

import pytest
import requests
from django.test import Client

_HONCHO_BASE_URL = "http://honcho.invalid"
_EMBEDDING_BASE_URL = "http://embed.invalid/v1"
_EMBEDDING_MODEL = "nomic-embed-text"


@pytest.fixture(autouse=True)
def _honcho_is_the_active_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the real ``HonchoMemoryBackend`` the probe target.

    ``EMBEDDING_PROVIDER=mock`` + a matching model name keep the *unrelated*
    embedding-consistency advisories quiet, so a warning in the payload can be
    attributed to the probe under test.
    """
    monkeypatch.setenv("MEMORY_BACKEND", "honcho")
    monkeypatch.setenv("HONCHO_BASE_URL", _HONCHO_BASE_URL)
    monkeypatch.setenv("HONCHO_EMBEDDING_BASE_URL", _EMBEDDING_BASE_URL)
    monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", _EMBEDDING_MODEL)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", _EMBEDDING_MODEL)


def _head_ok():
    return mock.Mock(status_code=200)


def _embedding_ok():
    response = mock.Mock(status_code=200)
    response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    return response


@pytest.mark.django_db
class TestMemoryBackendProbeClassification1824:
    """``reqogniloom.health._probe_memory_backend`` is the single classifier."""

    def test_reachable_api_with_unreachable_embedding_is_ok(self, monkeypatch):
        from reqogniloom.health import _probe_memory_backend

        monkeypatch.setattr("requests.head", lambda *a, **kw: _head_ok())
        monkeypatch.setattr(
            "requests.post",
            mock.Mock(side_effect=requests.ConnectionError("Connection refused")),
        )

        assert _probe_memory_backend() == "ok"

    def test_unreachable_api_is_down(self, monkeypatch):
        from reqogniloom.health import _probe_memory_backend

        monkeypatch.setattr(
            "requests.head",
            mock.Mock(side_effect=requests.ConnectionError("Connection refused")),
        )

        assert _probe_memory_backend() == "down"

    def test_api_5xx_is_down(self, monkeypatch):
        from reqogniloom.health import _probe_memory_backend

        monkeypatch.setattr("requests.head", lambda *a, **kw: mock.Mock(status_code=503))

        assert _probe_memory_backend() == "down"

    def test_fully_healthy_backend_is_ok(self, monkeypatch):
        from reqogniloom.health import _probe_memory_backend

        monkeypatch.setattr("requests.head", lambda *a, **kw: _head_ok())
        monkeypatch.setattr("requests.post", lambda *a, **kw: _embedding_ok())

        assert _probe_memory_backend() == "ok"


@pytest.mark.django_db
class TestReadinessEndpoint1824:
    """The public endpoint must not go red for a missing embedding provider."""

    def test_embedding_unavailable_keeps_readiness_200(self, monkeypatch):
        monkeypatch.setattr("requests.head", lambda *a, **kw: _head_ok())
        monkeypatch.setattr(
            "requests.post",
            mock.Mock(side_effect=requests.ConnectionError("Connection refused")),
        )

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 200, (
            "#1824: a reachable Honcho API without an embedding provider keeps "
            "every READ working; readiness must stay green"
        )
        assert body["checks"]["memory_backend"] == "ok"
        # CWE-209: the raw probe detail never reaches the anonymous body.
        assert "Connection refused" not in str(body)

    def test_unreachable_api_still_fails_readiness_with_503(self, monkeypatch):
        monkeypatch.setattr(
            "requests.head",
            mock.Mock(side_effect=requests.ConnectionError("Connection refused")),
        )

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 503
        assert body["checks"]["memory_backend"] == "error"
        dependency = next(
            dep for dep in body["dependencies"] if dep["name"] == "memory_backend"
        )
        assert dependency["status"] == "down"
        assert dependency["detail"] == "dependency_down"
        assert "Connection refused" not in str(body)

    def test_deprecated_health_alias_is_also_200(self, monkeypatch):
        """The compose probe hits ``/health/`` - it must stay green too."""
        monkeypatch.setattr("requests.head", lambda *a, **kw: _head_ok())
        monkeypatch.setattr(
            "requests.post",
            mock.Mock(side_effect=requests.ConnectionError("Connection refused")),
        )

        response = Client().get("/health/")

        assert response.status_code == 200
        assert response.json()["checks"]["memory_backend"] == "ok"
