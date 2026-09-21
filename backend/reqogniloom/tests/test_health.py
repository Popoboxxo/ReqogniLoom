"""
Health-check tests — workflow-definition sanity check (#40).

Verifies the ``/health/`` endpoint surfaces a warning when a workflow
definition (global or per-workspace) exists but carries no ``states``, which
otherwise silently breaks all lifecycle transitions for that item type until
someone notices manually (as happened after commit 9e7ae79, see #40).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client, override_settings

from persistence.models import Tenant
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition


def _make_tenant() -> Tenant:
    return Tenant.objects.create(name="Health-Check Tenant", slug=f"health-{uuid.uuid4().hex[:12]}")


@pytest.mark.django_db
class TestHealthWorkflowWarning:
    def test_no_warning_when_all_definitions_have_states(self, monkeypatch) -> None:
        # Do not depend on the ambient EMBEDDING_PROVIDER: pin a known 384-dim
        # provider (matching the migrated vector(384) columns) so the only
        # source of a warning could be the workflow check under test.
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        class _Provider:
            dimensions = 384

        monkeypatch.setattr(
            "llm_adapter.embedding_service.get_embedding_provider",
            lambda config=None: _Provider(),
        )

        client = Client()
        response = client.get("/health/")
        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["warnings"] == []

    def test_warning_when_global_definition_has_empty_states(self) -> None:
        tenant = _make_tenant()
        GlobalWorkflowDefinition.unscoped.create(
            tenant_id=tenant.id,
            item_type="Requirement",
            preset="standard",
            workflow_json={"states": [], "transitions": []},
        )

        client = Client()
        response = client.get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "warning"
        assert any("global workflow definition" in w for w in body["warnings"])

    def test_warning_when_workspace_definition_has_empty_states(self) -> None:
        tenant = _make_tenant()
        workspace_id = uuid.uuid4()
        WorkflowEngineDefinition.unscoped.create(
            tenant_id=tenant.id,
            workspace_id=workspace_id,
            item_type="Requirement",
            preset="standard",
            workflow_json={"states": [], "transitions": []},
        )

        client = Client()
        response = client.get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "warning"
        assert any("workspace workflow definition" in w for w in body["warnings"])

    def test_warning_when_states_key_missing_entirely(self) -> None:
        tenant = _make_tenant()
        GlobalWorkflowDefinition.unscoped.create(
            tenant_id=tenant.id,
            item_type="Requirement",
            preset="standard",
            workflow_json={},
        )

        client = Client()
        response = client.get("/health/")
        body = response.json()

        assert body["status"] == "warning"
        assert any("global workflow definition" in w for w in body["warnings"])

    def test_database_error_still_yields_503_and_no_workflow_check_crash(
        self, monkeypatch
    ) -> None:
        # A degraded DB check must short-circuit before the workflow check
        # even runs (it needs the DB) and must not itself raise.
        import reqogniloom.health as health_module

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(health_module.connection, "ensure_connection", _boom)

        client = Client()
        response = client.get("/health/")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"

    def test_database_error_detail_is_static_and_the_cause_is_logged(
        self, monkeypatch, caplog
    ) -> None:
        """#697 (CWE-209): ``/health/`` is reachable without authentication.

        A psycopg error's ``str()`` carries host, port, user and DSN fragments,
        so the probe's ``checks.database`` must be a static marker — the real
        cause belongs in the log. The probe decision (503 / degraded) is
        unchanged.
        """
        import reqogniloom.health as health_module

        sensitive = (
            "OperationalError: could not connect to server: "
            "host=db.internal user=reqogniloom_app password=***"
        )

        def _boom():
            raise RuntimeError(sensitive)

        monkeypatch.setattr(health_module.connection, "ensure_connection", _boom)

        client = Client()
        with caplog.at_level("WARNING"):
            response = client.get("/health/")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"
        assert body["checks"]["database"] == "error"
        assert sensitive not in str(body)
        assert sensitive in caplog.text


@pytest.mark.django_db
class TestHealthMemoryProbe:
    """``/health/`` surfaces a broken memory/embedding backend (#911).

    The shipped defect: Honcho's embedding base URL pointed at an unreachable
    host, every memory write failed, and ``/health/`` still reported ``ok``.
    The public endpoint now runs the active backend's bounded ``health_check()``
    (the real embedding probe) and degrades on failure.
    """

    def _patch_backend(self, monkeypatch, backend) -> None:
        monkeypatch.setattr("memory.backends.get_memory_backend", lambda: backend)

    def test_healthy_memory_backend_reports_ok(self, monkeypatch) -> None:
        class _Backend:
            @staticmethod
            def health_check():
                return True, "reachable"

        self._patch_backend(monkeypatch, _Backend())

        response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["memory_backend"] == "ok"

    def test_broken_memory_backend_degrades_without_leaking_detail(
        self, monkeypatch, caplog
    ) -> None:
        sensitive = (
            "HTTPConnectionPool(host=embed.invalid, port=11434): "
            "Max retries exceeded with url: /embeddings"
        )

        class _Backend:
            @staticmethod
            def health_check():
                return False, sensitive

        self._patch_backend(monkeypatch, _Backend())

        with caplog.at_level("WARNING"):
            response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"
        assert body["checks"]["memory_backend"] == "error"
        assert sensitive not in str(body)
        assert sensitive in caplog.text

    def test_memory_probe_exception_degrades_without_leaking_detail(
        self, monkeypatch, caplog
    ) -> None:
        sensitive = "OperationalError: host=embed.invalid user=mem"

        class _Backend:
            @staticmethod
            def health_check():
                raise RuntimeError(sensitive)

        self._patch_backend(monkeypatch, _Backend())

        with caplog.at_level("WARNING"):
            response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "degraded"
        assert body["checks"]["memory_backend"] == "error"
        assert sensitive not in str(body)
        assert sensitive in caplog.text


@pytest.mark.django_db
def test_health_reports_csrf_cookie_configuration():
    client = Client()
    with override_settings(AUTH_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
        resp = client.get("/health/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["csrf_cookie_secure_matches_auth"] == "ok"
    # The "ok" case must not escalate the top-level status.
    assert body["status"] == "ok"
    assert not any("CSRF_COOKIE_SECURE" in w for w in body["warnings"])


@pytest.mark.django_db
def test_health_flags_csrf_cookie_mismatch():
    client = Client()
    with override_settings(AUTH_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=True):
        resp = client.get("/health/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["csrf_cookie_secure_matches_auth"] == "mismatch"
    # Final review: a mismatch must escalate via the same `warnings`
    # mechanism the workflow check uses, so monitoring that only watches the
    # top-level `status` sees it. http_status must stay 200 (warning, not
    # failure) so container/k8s probes are unaffected.
    assert body["status"] == "warning"
    assert any("CSRF_COOKIE_SECURE" in w for w in body["warnings"])


@pytest.mark.django_db
class TestHealthEmbeddingDimensions:
    """``/health/`` surfaces a pgvector/provider dimension mismatch (#1018/#1019).

    The physical ``vector(N)`` columns are fixed by the last migration that
    ran; the configured embedding provider's width is fixed at container start.
    When they disagree, embedding writes and semantic search are skipped
    *silently* (the write guard is best-effort by design) — the one symptom is
    an ``artifact.search`` that never returns semantic hits. The endpoint must
    surface that where a deployment is watched, without turning it into a
    ``503`` that would restart-loop an otherwise healthy stack.
    """

    @staticmethod
    def _healthy_memory_backend(monkeypatch) -> None:
        """Isolate this class from the independent ``memory_backend`` probe."""

        class _Backend:
            @staticmethod
            def health_check():
                return True, "reachable"

        monkeypatch.setattr("memory.backends.get_memory_backend", lambda: _Backend())

    def test_aligned_columns_report_ok_without_a_warning(self, monkeypatch) -> None:
        self._healthy_memory_backend(monkeypatch)
        # 384-dim mock, matching the migrated vector(384) columns.
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["checks"]["embedding_dimensions"] == "ok"
        assert body["status"] != "degraded"
        assert not any("embedding" in w.lower() for w in body["warnings"])

    def test_provider_width_mismatch_is_a_warning_not_503(self, monkeypatch) -> None:
        self._healthy_memory_backend(monkeypatch)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        class _WideProvider:
            dimensions = 768

        monkeypatch.setattr(
            "llm_adapter.embedding_service.get_embedding_provider",
            lambda config=None: _WideProvider(),
        )

        response = Client().get("/health/")
        body = response.json()

        # Visible, but NOT degraded: a width mismatch disables semantic search
        # without making the service unhealthy, so probes must stay green.
        assert response.status_code == 200
        assert body["status"] == "warning"
        assert body["checks"]["embedding_dimensions"] == "mismatch"
        assert any("embedding columns" in w for w in body["warnings"])
        # CWE-209: reachable without authentication — no DB detail leaks.
        assert "host=" not in str(body)

    def test_unknown_provider_skips_the_check_without_a_second_alarm(
        self, monkeypatch
    ) -> None:
        """An unknown provider has no width to compare against.

        ``llm_adapter.W002`` already reports the bad provider from
        ``manage.py check``; this endpoint must not raise a second, misleading
        embedding-dimension warning.
        """
        from llm_adapter.embedding_service import EmbeddingProviderConfig

        self._healthy_memory_backend(monkeypatch)
        monkeypatch.setattr(
            "llm_adapter.embedding_service._read_config",
            lambda: EmbeddingProviderConfig(provider_name="not-a-real-provider"),
        )

        response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 200
        assert body["checks"]["embedding_dimensions"] == "ok"
        assert not any("embedding columns" in w for w in body["warnings"])
        assert body["status"] != "degraded"

    def test_check_is_skipped_when_the_database_is_down(self, monkeypatch) -> None:
        import reqogniloom.health as health_module

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(health_module.connection, "ensure_connection", _boom)

        response = Client().get("/health/")
        body = response.json()

        assert response.status_code == 503
        assert "embedding_dimensions" not in body["checks"]
