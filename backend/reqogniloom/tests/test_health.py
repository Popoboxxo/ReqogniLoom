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
    def test_no_warning_when_all_definitions_have_states(self) -> None:
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
