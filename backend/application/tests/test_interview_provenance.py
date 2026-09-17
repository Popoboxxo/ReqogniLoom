"""L2.3: interview provenance is recorded and resolvable for BOTH session kinds."""
from __future__ import annotations

import uuid

import pytest

from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSessionArtifact, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IP Tenant", slug="ip-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _formalized_requirement(ctx, workspace):
    svc = InterviewService()
    session = svc.start(ctx, "Requirement", workspace.id)
    svc.answer(ctx, session.id, "title", "Provenance probe")
    svc.answer(ctx, session.id, "rationale", "so the badge has something to find")
    result = svc.formalize(ctx, session.id)
    return session, result


class TestSingleModeProvenance:
    def test_single_mode_formalize_writes_a_provenance_row(self, ctx, workspace):
        session, _ = _formalized_requirement(ctx, workspace)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            rows = list(InterviewSessionArtifact.objects.filter(session_id=session.id))
        finally:
            TenantContext.clear_tenant()

        assert len(rows) == 1
        assert rows[0].artifact_type == "Requirement"

    def test_provenance_row_references_the_artifact_pk_not_the_subtype_id(
        self, ctx, workspace
    ):
        """InterviewSessionArtifact.artifact is an Artifact FK. The subtype id
        returned in resulting_artifact_ids is a DIFFERENT UUID -- storing it
        here would write an unresolvable FK."""
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            row = InterviewSessionArtifact.objects.get(session_id=session.id)
        finally:
            TenantContext.clear_tenant()

        assert row.artifact_id == requirement.artifact_id
        assert row.artifact_id != requirement.id

    def test_update_branch_writes_no_provenance_row(self, ctx, workspace):
        """A grounded update did not CREATE the artifact, so claiming the
        interview produced it would be wrong."""
        from application.requirement_service import RequirementService
        from persistence.models import InterviewSession

        existing = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Pre-existing", ctx=ctx, description=""
        )
        svc = InterviewService()
        session = svc.start(ctx, "Requirement", workspace.id)
        svc.answer(ctx, session.id, "title", "Updated title")
        svc.answer(ctx, session.id, "rationale", "why")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
        finally:
            TenantContext.clear_tenant()

        svc.formalize(ctx, session.id)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            assert not InterviewSessionArtifact.objects.filter(
                session_id=session.id
            ).exists()
        finally:
            TenantContext.clear_tenant()


class TestProvenanceLookupIdSpaces:
    def test_resolves_by_artifact_pk(self, ctx, workspace):
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )

        found = InterviewService().provenance_session_id(ctx, requirement.artifact_id)

        assert found == str(session.id)

    def test_resolves_by_subtype_id(self, ctx, workspace):
        """Every artifact detail view passes the subtype id (e.g.
        RequirementEditors passes `requirement.id`), so the badge lookup must
        accept it -- otherwise it never matches anything."""
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )
        assert requirement.id != requirement.artifact_id  # guard: really two spaces

        found = InterviewService().provenance_session_id(ctx, requirement.id)

        assert found == str(session.id)

    def test_unknown_id_returns_none_not_an_error(self, ctx, workspace):
        """A plain (non-interview) artifact and a wholly unknown UUID are both
        the normal answer 'not created by an interview', never an exception --
        the badge is informational and must not surface an error."""
        assert InterviewService().provenance_session_id(ctx, uuid.uuid4()) is None

    def test_non_interview_artifact_returns_none(self, ctx, workspace):
        from application.requirement_service import RequirementService

        plain = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Hand-written", ctx=ctx, description=""
        )
        assert InterviewService().provenance_session_id(ctx, plain.id) is None
