"""Regression tests for the ADR-010 health contract (RES-03).

Findings covered: ``AUD-2026-09-031`` (false-green probe), ``-275`` (live/ready
promised but absent), ``-286`` (cache/worker/beat never probed), plus the
``checks`` → ``warnings``/``advisory`` shape change and the auth exemption.

Contract under test (ADR-010 §1–§6):

* ``/health/live`` is always 200 and never probes a dependency.
* ``/health/ready`` is fail-closed: 503 if any mandatory dependency is not ok,
  200 otherwise; ``ok``/``warning`` distinction is driven only by ``warnings``.
* ``dependencies`` is non-empty ⇔ ``status == "degraded"``; its entries carry a
  static ``detail`` marker, never a DSN/host/secret.
* Advisory signals appear only in ``warnings``/``advisory``, never in
  ``checks``/``dependencies``.
* ``/health/`` is the deprecated alias of ``/health/ready`` and carries
  ``Deprecation``/``Sunset`` headers.
* ``HEALTH_STRICT_READINESS`` defaults to strict (503); only an explicit
  ``false`` yields degraded-200.
"""
from __future__ import annotations

import pytest
from django.test import Client, override_settings

from auth_tenancy.middleware import is_exempt_path

pytestmark = pytest.mark.django_db

_REQUIRED = ("database", "memory_backend", "cache", "celery_worker", "celery_beat")


def _stub_required(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> dict[str, str]:
    """Stub the mandatory-check aggregation for HTTP-level contract tests."""
    values = {name: "ok" for name in _REQUIRED}
    values.update(overrides)
    monkeypatch.setattr("reqogniloom.health._run_required_checks", lambda: values)
    # Deterministic advisory signals (mock embedding provider, matching columns).
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    return values


def _healthy_memory_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Backend:
        @staticmethod
        def health_check():
            return True, "reachable"

    monkeypatch.setattr("memory.backends.get_memory_backend", lambda: _Backend())


# ---------------------------------------------------------------------------
# /health/live
# ---------------------------------------------------------------------------


class TestLiveness:
    def test_always_200_and_never_probes_a_dependency(self, monkeypatch) -> None:
        called: list[int] = []
        monkeypatch.setattr(
            "reqogniloom.health._run_required_checks",
            lambda: called.append(1),
        )

        response = Client().get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "checks": {}}
        assert called == [], "liveness must not touch any dependency"

    def test_trailing_slash_form_also_serves(self) -> None:
        response = Client().get("/health/live/")
        assert response.status_code == 200

    def test_stays_200_when_every_required_dependency_is_down(self, monkeypatch) -> None:
        _stub_required(
            monkeypatch,
            database="down",
            memory_backend="down",
            cache="down",
            celery_worker="down",
            celery_beat="down",
        )
        assert Client().get("/health/live").status_code == 200


# ---------------------------------------------------------------------------
# /health/ready — mandatory dependency semantics
# ---------------------------------------------------------------------------


class TestReadinessMandatoryChecks:
    def test_ok_when_all_required_are_healthy(self, monkeypatch) -> None:
        _stub_required(monkeypatch)

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["dependencies"] == []
        assert set(body["checks"]) == set(_REQUIRED)
        assert all(value == "ok" for value in body["checks"].values())
        assert body["warnings"] == []

    @pytest.mark.parametrize("failed", _REQUIRED)
    def test_503_and_lists_the_failed_required_dependency(
        self, monkeypatch, failed: str
    ) -> None:
        _stub_required(monkeypatch, **{failed: "down"})

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"
        assert body["checks"][failed] == "error"
        names = [dep["name"] for dep in body["dependencies"]]
        assert names == [failed]
        assert all(dep["detail"] == "dependency_down" for dep in body["dependencies"])

    def test_dependencies_non_empty_iff_degraded(self, monkeypatch) -> None:
        _stub_required(monkeypatch, cache="down")
        degraded = Client().get("/health/ready").json()
        assert bool(degraded["dependencies"]) is (degraded["status"] == "degraded")

        _stub_required(monkeypatch)
        healthy = Client().get("/health/ready").json()
        assert healthy["dependencies"] == []
        assert healthy["status"] != "degraded"

    def test_unknown_probe_status_is_fail_closed(self, monkeypatch) -> None:
        # `unknown` (e.g. no beat heartbeat yet) is not healthy — fail closed.
        _stub_required(monkeypatch, celery_beat="unknown")

        response = Client().get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["celery_beat"] == "error"

    def test_probe_detail_is_never_exposed(self, monkeypatch) -> None:
        """CWE-209: a probe's real cause must not reach the anonymous body."""
        sensitive = "redis://svc:supersecret@cache.internal:6379/0"
        monkeypatch.setattr(
            "admin_ops.health_rest._check_redis",
            lambda: {"name": "redis", "status": "down", "detail": sensitive},
        )
        _healthy_memory_backend(monkeypatch)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 503
        assert sensitive not in str(body)
        assert "cache.internal" not in str(body)
        assert body["dependencies"][0]["detail"] == "dependency_down"


class TestRequiredProbeMapping:
    def test_redis_row_is_mapped_to_cache_and_failures_propagate(
        self, monkeypatch
    ) -> None:
        import reqogniloom.health as health_module

        monkeypatch.setattr(health_module.connection, "ensure_connection", lambda: None)
        _healthy_memory_backend(monkeypatch)
        monkeypatch.setattr(
            "admin_ops.health_rest._check_redis",
            lambda: {"name": "redis", "status": "ok", "detail": "PING ok"},
        )
        monkeypatch.setattr(
            "admin_ops.health_rest._check_celery_worker",
            lambda: {"name": "celery_worker", "status": "ok", "detail": "1 worker"},
        )
        monkeypatch.setattr(
            "admin_ops.health_rest._check_celery_beat",
            lambda: {"name": "celery_beat", "status": "down", "detail": "stale"},
        )

        results = health_module._run_required_checks()

        assert set(results) == set(_REQUIRED), "contract names only, no `redis` key"
        assert results["cache"] == "ok"
        assert results["celery_beat"] == "down"


# ---------------------------------------------------------------------------
# Advisory signals — never degraded, never in checks/dependencies
# ---------------------------------------------------------------------------


class TestAdvisorySignals:
    def test_advisory_keys_never_appear_in_checks(self, monkeypatch) -> None:
        _stub_required(monkeypatch)
        # Force an advisory-only signal: a provider width mismatch.
        monkeypatch.setattr(
            "reqogniloom.health._embedding_dimension_mismatches",
            lambda: ["artifact.embedding"],
        )

        body = Client().get("/health/ready").json()

        assert body["advisory"]["embedding_dimensions"] == "mismatch"
        assert any("embedding columns" in w for w in body["warnings"])
        assert not set(body["advisory"]) & set(body["checks"])
        assert body["checks"]["database"] == "ok"
        assert body["dependencies"] == []

    def test_warning_status_is_200_with_all_required_healthy(self, monkeypatch) -> None:
        _stub_required(monkeypatch)
        with override_settings(AUTH_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=True):
            response = Client().get("/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "warning"
        assert body["advisory"]["csrf_cookie_secure_matches_auth"] == "mismatch"
        assert body["dependencies"] == []

    def test_advisory_does_not_mask_a_degraded_required_check(
        self, monkeypatch
    ) -> None:
        _stub_required(monkeypatch, cache="down")
        with override_settings(AUTH_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=True):
            response = Client().get("/health/ready")

        assert response.status_code == 503
        assert response.json()["status"] == "degraded"


# ---------------------------------------------------------------------------
# /health/ alias
# ---------------------------------------------------------------------------


class TestDeprecatedAlias:
    def test_alias_matches_ready_and_advertises_deprecation(self, monkeypatch) -> None:
        _stub_required(monkeypatch)

        ready = Client().get("/health/ready")
        alias = Client().get("/health/")

        assert alias.status_code == ready.status_code
        assert alias.json() == ready.json()
        assert alias["Deprecation"] == "true"
        assert alias["Sunset"].endswith("GMT")

    def test_alias_goes_red_when_a_required_dependency_fails(
        self, monkeypatch
    ) -> None:
        _stub_required(monkeypatch, cache="down")

        response = Client().get("/health/")

        assert response.status_code == 503
        assert [d["name"] for d in response.json()["dependencies"]] == ["cache"]


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


class TestStrictReadinessFlag:
    def test_default_is_strict(self, monkeypatch) -> None:
        _stub_required(monkeypatch, cache="down")
        assert Client().get("/health/ready").status_code == 503

    @override_settings(HEALTH_STRICT_READINESS=False)
    def test_explicit_false_is_degraded_200(self, monkeypatch) -> None:
        _stub_required(monkeypatch, cache="down")

        response = Client().get("/health/ready")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "degraded"
        assert [d["name"] for d in body["dependencies"]] == ["cache"]


# ---------------------------------------------------------------------------
# Auth exemption (REQ-L2-AT-007)
# ---------------------------------------------------------------------------


class TestAuthExemption:
    @pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/"])
    def test_paths_are_exempt(self, path: str) -> None:
        assert is_exempt_path(path) is True

    def test_reachable_without_any_credentials(self, monkeypatch) -> None:
        _stub_required(monkeypatch)

        live = Client().get("/health/live")
        ready = Client().get("/health/ready")

        # A plain Django test Client carries no auth; an intercepting middleware
        # would have produced 401/403.
        assert live.status_code == 200
        assert ready.status_code == 200
