"""REST provenance lookup -- GET /api/v1/interviews/by-artifact/{artifact_id}/.

Covers the multi-artifact provenance endpoint (multi-artifact plan): given
an Artifact created by a multi-mode interview, the endpoint resolves the
owning InterviewSession via the InterviewSessionArtifact join row; an
artifact without a provenance row answers ``{"session_id": null}`` instead.

Uses the shared ``tenant``/``workspace``/``authed_client`` fixtures from
rest_api/tests/conftest.py -- same real-Bearer-login pattern as
test_interview_views_multi.py (``force_authenticate`` never populates
``request.auth_context`` with this codebase's AuthTenancyAuthentication,
so it would silently 401 every call). ORM seeding mirrors the
set_request_tenant/clear_request_tenant bracket used by every conftest
fixture (TenantScopedModel's default manager filters by thread-local
tenant).
"""
from __future__ import annotations

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    InterviewSession,
    InterviewSessionArtifact,
)

pytestmark = pytest.mark.django_db


def _seed_artifact(tenant, workspace) -> Artifact:
    """A bare in-scope Artifact in *workspace* (no provenance row yet)."""
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()


def _seed_multi_session_with_provenance(
    tenant, workspace
) -> "tuple[InterviewSession, Artifact]":
    """A multi-mode session plus one provenance row pointing at a new
    Artifact -- the exact row shape ``_formalize_multi`` writes."""
    set_request_tenant(tenant.id)
    try:
        session = InterviewSession.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            status=InterviewSession.STATUS_IN_PROGRESS,
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        InterviewSessionArtifact.objects.create(
            tenant=tenant,
            session=session,
            artifact=artifact,
            artifact_type=artifact.artifact_type,
        )
        return session, artifact
    finally:
        clear_request_tenant()


class TestInterviewProvenanceLookup:
    def test_returns_session_id_when_provenance_row_exists(
        self, authed_client, tenant, workspace
    ):
        session, artifact = _seed_multi_session_with_provenance(tenant, workspace)

        response = authed_client.get(f"/api/v1/interviews/by-artifact/{artifact.id}/")

        assert response.status_code == 200, response.content
        assert response.data == {"session_id": str(session.id)}

    def test_returns_null_without_provenance_row(self, authed_client, tenant, workspace):
        artifact = _seed_artifact(tenant, workspace)

        response = authed_client.get(f"/api/v1/interviews/by-artifact/{artifact.id}/")

        assert response.status_code == 200, response.content
        assert response.data["session_id"] is None
