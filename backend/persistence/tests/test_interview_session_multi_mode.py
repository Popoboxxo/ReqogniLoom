"""InterviewSession multi-mode axis + InterviewSessionArtifact provenance join.

Task 1 of the multi-artifact discovery interview plan:
``session_kind`` ("single" default / "multi"), nullable ``artifact_type``
for type-free multi sessions, and the provenance join table linking a
session to every artifact it created.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from persistence.models import Artifact, InterviewSession, InterviewSessionArtifact
from persistence.tests.conftest import active_tenant


@pytest.mark.django_db
class TestInterviewSessionMultiMode:
    def test_session_kind_defaults_to_single(self, tenant, workspace):
        with active_tenant(tenant):
            session = InterviewSession.objects.create(
                workspace=workspace,
                artifact_type="Requirement",
            )
            assert session.session_kind == "single"

    def test_artifact_type_can_be_null_for_multi_sessions(self, tenant, workspace):
        with active_tenant(tenant):
            session = InterviewSession.objects.create(
                workspace=workspace,
                artifact_type=None,
                session_kind="multi",
            )
            assert session.artifact_type is None
            assert session.session_kind == "multi"

    def test_interview_session_artifact_links_session_to_artifact(
        self, tenant, workspace
    ):
        with active_tenant(tenant):
            session = InterviewSession.objects.create(
                workspace=workspace,
                artifact_type=None,
                session_kind="multi",
            )
            artifact = Artifact.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
            row = InterviewSessionArtifact.objects.create(
                session=session, artifact=artifact, artifact_type="Requirement"
            )
            assert row.session_id == session.id
            assert row.artifact_id == artifact.id
            assert row.created_at is not None

    def test_interview_session_artifact_requires_session(self, tenant, workspace):
        with active_tenant(tenant), pytest.raises(IntegrityError):
            artifact = Artifact.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
            InterviewSessionArtifact.objects.create(
                session=None, artifact=artifact, artifact_type="Requirement"
            )
