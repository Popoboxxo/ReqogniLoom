"""Milestone M3 gate — all 10 artifact types are Artifact-backed.

Datenmodell-Konsolidierung Phase 3. The observable payoff (spec section 4.4) is
that multi-artifact interviews can finally create GlossaryTerms.
"""
from __future__ import annotations

import inspect

import pytest

from application import interview_artifact_adapters


def test_glossary_adapter_no_longer_refuses():
    source = inspect.getsource(interview_artifact_adapters)
    assert "GlossaryTerm is not Artifact-backed yet" not in source


@pytest.mark.django_db
def test_interview_can_create_a_glossary_term(interview_env):
    from persistence.models import GlossaryTerm

    ctx, workspace_id = interview_env

    ref = interview_artifact_adapters.ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"](
        {"term": "Widget", "definition": "a thing"}, ctx, workspace_id
    )

    # The adapter contract (module docstring) says artifact_id is ALWAYS the
    # persistence.Artifact PK, not the GlossaryTerm row id -- look the row up
    # via that FK.
    row = GlossaryTerm.objects.get(artifact_id=ref.artifact_id)
    assert row.term == "Widget"
    assert row.artifact_id is not None


@pytest.mark.django_db
def test_every_backed_type_reports_clean(interview_env):
    import io

    from django.core.management import call_command

    out = io.StringIO()
    call_command("check_artifact_backing", stdout=out)

    assert "All artifact types are consistently backed." in out.getvalue()


@pytest.fixture
def interview_env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-m3", slug="t-m3")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="ws-m3")
        # GlossaryTerm.created_by/modified_by are FKs to pl_user -- a random
        # uuid here would fail with an IntegrityError, unlike the sibling
        # adapters' create_X() calls, which don't all write those columns.
        user = User.objects.create(username="t-m3-user", email="t-m3@example.com", tenant=tenant)
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
            workspace_id=workspace.id,
        )
        yield ctx, workspace.id
    finally:
        TenantContext.clear_tenant()
