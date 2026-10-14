"""#1289 — the level suggestion service + its ADR-019 accept adapter."""
from __future__ import annotations

import pytest

from application.requirement_level_service import (
    RequirementLevelService,
    suggest_level,
)
from application.suggestion_service import SuggestionService
from application.trace_link_service import AgentSelfConfirmError
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ApiKey
from persistence.models import (
    Artifact,
    Requirement,
    RequirementLevel,
    RequirementLevelSource,
    Suggestion,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext


class TestSuggestLevelPure:
    def test_architecture_wins(self):
        result = suggest_level(
            requirement_type="SyReq", architecture_level=3, parent_level=2
        )
        assert result["level"] == 3
        assert result["source"] == "architecture"

    def test_parent_wins_over_type(self):
        result = suggest_level(
            requirement_type="SyReq", architecture_level=None, parent_level=2
        )
        assert result["level"] == 3
        assert result["source"] == "trace_link_parent"

    def test_type_is_the_last_resort(self):
        result = suggest_level(
            requirement_type="FeatureReq", architecture_level=None, parent_level=None
        )
        assert result["level"] == 3
        assert result["source"] == "type"

    def test_no_source_is_not_derivable(self):
        result = suggest_level(
            requirement_type="Unknown", architecture_level=None, parent_level=None
        )
        assert result["level"] is None
        assert result["source"] is None

    def test_parent_at_the_cascade_bottom_yields_no_level(self):
        result = suggest_level(
            requirement_type="SyReq", architecture_level=None, parent_level=4
        )
        assert result["level"] is None


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t-level", slug="t-level")
    TenantContext.set_tenant(tenant.id)
    try:
        owner = User.objects.create(
            tenant=tenant, username="lvl-owner", email="lvl@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="R", type="SyReq"
        )
        api_key = ApiKey.objects.create(
            tenant=tenant,
            user=owner,
            name="level-bot",
            key_hash="sha256p1:level",
            principal_type="agent",
            agent_label="Claude Test",
        )
        agent_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
            actor_type="agent",
            agent_label="Claude Test",
        )
        human_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "requirement": requirement,
            "agent_ctx": agent_ctx,
            "human_ctx": human_ctx,
        }
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_suggest_level_uses_the_type_for_a_plain_syreq(env):
    result = RequirementLevelService().suggest_level(
        env["requirement"].id, env["human_ctx"]
    )
    assert result["level"] == RequirementLevel.L1_SYSTEM
    assert result["source"] == "type"


@pytest.mark.django_db
def test_propose_level_persists_a_requirement_level_suggestion(env):
    receipt = RequirementLevelService().propose_level(
        env["requirement"].id, env["agent_ctx"]
    )
    assert receipt["kind"] == "requirement_level"
    assert receipt["status"] == "open"
    assert receipt["payload"]["level"] == 1


@pytest.mark.django_db
def test_accepting_the_suggestion_sets_the_manual_level(env):
    service = SuggestionService()
    receipt = RequirementLevelService(suggestion_service=service).propose_level(
        env["requirement"].id, env["agent_ctx"]
    )
    result = service.accept(receipt["id"], env["human_ctx"])
    assert result["status"] == "accepted"

    requirement = Requirement.objects.get(id=env["requirement"].id)
    assert requirement.level == RequirementLevel.L1_SYSTEM
    assert requirement.level_source == RequirementLevelSource.MANUAL


@pytest.mark.django_db
def test_an_agent_cannot_accept_its_own_level_suggestion(env):
    service = SuggestionService()
    receipt = RequirementLevelService(suggestion_service=service).propose_level(
        env["requirement"].id, env["agent_ctx"]
    )
    with pytest.raises(AgentSelfConfirmError):
        service.accept(receipt["id"], env["agent_ctx"])
    # The receipt stays open — a failed accept must not stamp it.
    assert Suggestion.objects.get(id=receipt["id"]).status == Suggestion.Status.OPEN
