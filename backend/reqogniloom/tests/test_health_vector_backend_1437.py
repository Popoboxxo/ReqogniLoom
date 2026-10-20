"""Issue #1437: ``/health/`` must expose the EFFECTIVE artifact vector backend.

``ARTIFACT_VECTOR_BACKEND=qdrant`` is an explicit opt-in, but the port only
selects Qdrant when every gate condition holds (importable ``qdrant_client``,
effective ``MEMORY_BACKEND=qdrant``, configured ``QDRANT_BASE_URL``). Anything
else degrades to pgvector *by design* — but before this change an operator who
set the opt-in still read ``status: ok`` and had no way to tell that artifact
ANN search was running on pgvector.

These tests pin both halves of the fix:

* :func:`application.vector_port.vector_backend_diagnostic` names the requested
  backend, the active backend and the first failing gate — without changing the
  selection behaviour of :func:`application.vector_port.get_vector_port`;
* ``reqogniloom.health._collect_advisory`` publishes those values and raises an
  advisory warning when they diverge (HTTP 200: ``ok`` → ``warning``).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from application import vector_port


def _patch_gate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    selector: str = "qdrant",
    client_available: bool = True,
    memory_backend: str = "qdrant",
    base_url: str = "http://qdrant:6333",
    config_error: bool = False,
) -> None:
    """Drive the four Qdrant gate conditions deterministically."""
    monkeypatch.setenv(vector_port.ARTIFACT_VECTOR_BACKEND_ENV, selector)
    monkeypatch.setattr(
        vector_port, "_qdrant_client_available", lambda: client_available
    )
    monkeypatch.setattr(
        vector_port, "_effective_memory_backend_name", lambda: memory_backend
    )
    if config_error:

        def _boom() -> None:
            raise RuntimeError("unreadable qdrant config")

        monkeypatch.setattr(vector_port, "_effective_qdrant_config", _boom)
    else:

        def _config() -> SimpleNamespace:
            return SimpleNamespace(base_url=base_url)

        monkeypatch.setattr(vector_port, "_effective_qdrant_config", _config)


class TestVectorBackendDiagnostic:
    def test_pgvector_requested_is_not_a_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_gate(
            monkeypatch,
            selector="pgvector",
            client_available=False,
            memory_backend="pgvector",
            base_url="",
        )

        assert vector_port.vector_backend_diagnostic() == {
            "requested": "pgvector",
            "active": "pgvector",
            "reason": "",
        }
        assert vector_port._qdrant_selected() is False

    def test_qdrant_is_active_when_every_gate_holds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_gate(monkeypatch)

        diagnostic = vector_port.vector_backend_diagnostic()

        assert diagnostic == {
            "requested": "qdrant",
            "active": "qdrant",
            "reason": "",
        }
        # The diagnostic must agree with the real selector.
        assert vector_port._qdrant_selected() is True

    @pytest.mark.parametrize(
        ("kwargs", "expected_reason"),
        [
            ({"client_available": False}, "qdrant_client_missing"),
            ({"memory_backend": "pgvector"}, "memory_backend_not_qdrant"),
            ({"config_error": True}, "qdrant_config_error"),
            ({"base_url": ""}, "qdrant_base_url_missing"),
        ],
    )
    def test_each_failing_gate_is_named(
        self,
        monkeypatch: pytest.MonkeyPatch,
        kwargs: dict,
        expected_reason: str,
    ) -> None:
        _patch_gate(monkeypatch, **kwargs)

        diagnostic = vector_port.vector_backend_diagnostic()

        assert diagnostic["requested"] == "qdrant"
        assert diagnostic["active"] == "pgvector"
        assert diagnostic["reason"] == expected_reason
        # The fix only exposes the fallback; it must not change it.
        assert vector_port._qdrant_selected() is False

    def test_unknown_selector_is_named_and_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_gate(monkeypatch, selector="milvus")

        diagnostic = vector_port.vector_backend_diagnostic()

        assert diagnostic == {
            "requested": "milvus",
            "active": "pgvector",
            "reason": "unknown_artifact_vector_backend",
        }
        assert vector_port._qdrant_selected() is False


class TestHealthAdvisory:
    def test_pgvector_deployment_is_reported_without_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        _patch_gate(
            monkeypatch,
            selector="pgvector",
            client_available=False,
            memory_backend="pgvector",
            base_url="",
        )
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["effective_vector_backend"] == "pgvector"
        assert advisory["vector_backend_requested"] == "pgvector"
        assert advisory["vector_backend_active"] == "pgvector"
        assert "vector_backend_fallback_reason" not in advisory
        assert not any("ARTIFACT_VECTOR_BACKEND" in item for item in warnings)

    def test_qdrant_fallback_is_visible_and_warns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        _patch_gate(monkeypatch, memory_backend="pgvector")
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["effective_vector_backend"] == "pgvector"
        assert advisory["vector_backend_requested"] == "qdrant"
        assert advisory["vector_backend_active"] == "pgvector"
        assert (
            advisory["vector_backend_fallback_reason"]
            == "memory_backend_not_qdrant"
        )
        assert any("ARTIFACT_VECTOR_BACKEND=qdrant" in item for item in warnings)

    def test_active_qdrant_is_reported_without_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        _patch_gate(monkeypatch)
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["effective_vector_backend"] == "qdrant"
        assert advisory["vector_backend_requested"] == "qdrant"
        assert advisory["vector_backend_active"] == "qdrant"
        assert "vector_backend_fallback_reason" not in advisory
        assert not any("ARTIFACT_VECTOR_BACKEND" in item for item in warnings)

    def test_health_never_crashes_on_a_broken_diagnostic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from reqogniloom.health import _collect_advisory

        def _boom() -> dict[str, str]:
            raise RuntimeError("diagnostic exploded")

        monkeypatch.setattr(
            "application.vector_port.vector_backend_diagnostic", _boom
        )
        advisory: dict[str, str] = {}
        warnings: list[str] = []

        _collect_advisory(advisory, warnings, db_ok=False)

        assert "vector-backend diagnostic failed" in warnings
        assert "effective_vector_backend" not in advisory
