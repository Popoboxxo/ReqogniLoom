"""InterviewSession model — REQ (Interview-Management-Engine spec §3.2)."""
from __future__ import annotations

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from persistence.models import Artifact, InterviewSession, Tenant, Workspace
from persistence.tenancy import TenantContext

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Interview Tenant", slug="interview-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


class TestInterviewSessionDefaults:
    def test_creates_with_defaults(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            session = InterviewSession.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
        finally:
            TenantContext.clear_tenant()

        # Task 12: the `status` column is dropped -- this raw create bypasses
        # InterviewService.start() (no WorkflowItemState either), so the
        # "default" is now the interview_default preset's initial state.
        from workflow import state_reader

        assert state_reader.initial_state("Interview") == "in_progress"
        assert session.collected_fields == {}
        assert session.grounding_snapshot == {}
        assert session.resulting_artifact_ids == []
        assert session.transcript == []
        assert session.target_artifact is None

    def test_target_artifact_survives_artifact_deletion_as_null(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
            session = InterviewSession.objects.create(
                workspace=workspace,
                artifact_type="Requirement",
                target_artifact=artifact,
            )
            artifact.delete()
            session.refresh_from_db()
        finally:
            TenantContext.clear_tenant()

        assert session.target_artifact_id is None


@_pg_only
class TestInterviewSessionRls:
    def test_direct_sql_without_tenant_context_sees_no_rows(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            InterviewSession.objects.create(workspace=workspace, artifact_type="Requirement")
        finally:
            TenantContext.clear_tenant()

        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pl_interview_session")
                count = cursor.fetchone()[0]
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

        assert count == 0, "RLS failed to block direct SQL access without app.current_tenant"
