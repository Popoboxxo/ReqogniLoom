"""
REQ-L2-AI-001 / REQ-L2-AI-002 — AiDerivationService tests.

Covers the three Draft/Accept derivation flows end-to-end against the
credential-free mock provider (no network access), plus prompt formatting and
error handling via a capturing fake provider.
"""
from __future__ import annotations

import json

import pytest

from application.ai_derivation_service import AiDerivationService, LlmResponseError
from application.architecture_service import ArchitectureService
from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import (
    Artifact,
    StakeholderNeed,
    Tenant,
    User,
    Workspace as PersistenceWorkspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _make_need(ctx, workspace, title, description=""):
    """Create a StakeholderNeed directly via ORM (bypasses event publishing)."""
    TenantContext.set_tenant(ctx.tenant_id)
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="StakeholderNeed", tenant_id=ctx.tenant_id
    )
    return StakeholderNeed.objects.create(
        artifact=artifact, tenant_id=ctx.tenant_id, title=title, description=description
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="ai-tenant", slug="ai-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(username="aiuser", email="ai@example.com", tenant=tenant)


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="ai-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="ai-ws")
    finally:
        TenantContext.clear_tenant()


class _CaptureProvider:
    """Fake provider recording the prompt and returning a canned response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict] = []

    def complete(self, prompt, *, purpose="", context=None):
        self.calls.append({"prompt": prompt, "purpose": purpose, "context": context})
        return self.response


# ---------------------------------------------------------------------------
# Flow 1 — derive requirements from a stakeholder need
# ---------------------------------------------------------------------------


def test_derive_requirements_from_need_returns_drafts(auth_context, workspace):
    """Mock provider yields n structured drafts referencing the parent need."""
    need = _make_need(
        auth_context, workspace, "Users need fast search", "Search must feel instant."
    )

    result = AiDerivationService().derive_requirements_from_need(
        auth_context, need.id, n=2
    )

    assert list(result.keys()) == ["drafts"]
    assert len(result["drafts"]) == 2
    for draft in result["drafts"]:
        assert set(draft.keys()) == {
            "title",
            "description",
            "rationale",
            "suggested_parent_id",
        }
        assert draft["suggested_parent_id"] == str(need.id)


def test_derive_requirements_formats_prompt(auth_context, workspace, monkeypatch):
    """The rendered prompt substitutes need title/description and n."""
    need = _make_need(
        auth_context, workspace, "Distinctive Need Title", "Distinctive Need Description"
    )
    provider = _CaptureProvider(json.dumps([{"title": "t", "description": "d", "rationale": "r"}]))
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    AiDerivationService().derive_requirements_from_need(auth_context, need.id, n=5)

    prompt = provider.calls[0]["prompt"]
    assert "Distinctive Need Title" in prompt
    assert "Distinctive Need Description" in prompt
    assert "5" in prompt
    assert "{need_title}" not in prompt and "{n}" not in prompt


def test_derive_requirements_invalid_json_raises(auth_context, workspace, monkeypatch):
    """A non-JSON provider response surfaces as LlmResponseError."""
    need = _make_need(auth_context, workspace, "N", "")
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider",
        lambda *a, **k: _CaptureProvider("this is not json"),
    )

    with pytest.raises(LlmResponseError):
        AiDerivationService().derive_requirements_from_need(auth_context, need.id)


def test_derive_requirements_missing_need_raises(auth_context):
    import uuid

    with pytest.raises(NotFoundError):
        AiDerivationService().derive_requirements_from_need(auth_context, uuid.uuid4())


# ---------------------------------------------------------------------------
# Flow 2 — suggest architecture for an unassigned requirement
# ---------------------------------------------------------------------------


def test_suggest_architecture_returns_ids(auth_context, workspace):
    """Mock suggests the first available architecture element for an unassigned req."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Some requirement", ctx=auth_context
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Component A", ctx=auth_context
    )

    result = AiDerivationService().suggest_architecture_for_requirement(
        auth_context, req.id
    )

    assert result["suggested_arch_element_ids"] == [str(arch.id)]


def test_suggest_architecture_already_assigned_is_validation_error(
    auth_context, workspace
):
    """A requirement with an existing allocation cannot be re-suggested (400)."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Assigned req", ctx=auth_context
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Component B", ctx=auth_context
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=auth_context
    )

    with pytest.raises(ValidationError):
        AiDerivationService().suggest_architecture_for_requirement(auth_context, req.id)


# ---------------------------------------------------------------------------
# Flow 3 — decompose a requirement to the next level
# ---------------------------------------------------------------------------


def test_decompose_next_level_returns_drafts(auth_context, workspace):
    """An allocated requirement yields decomposition drafts + parent reference."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Parent req", ctx=auth_context
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Component C", ctx=auth_context
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=auth_context
    )

    result = AiDerivationService().decompose_requirement_next_level(
        auth_context, req.id
    )

    assert result["parent_requirement_id"] == str(req.id)
    assert len(result["drafts"]) >= 1
    for draft in result["drafts"]:
        assert set(draft.keys()) == {
            "title",
            "description",
            "rationale",
            "suggested_arch_element_id",
        }
    # The mock tags the first draft with an available architecture element id.
    assert result["drafts"][0]["suggested_arch_element_id"] == str(arch.id)


def test_decompose_without_allocation_is_validation_error(auth_context, workspace):
    """Decomposing an unallocated requirement is rejected (400)."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Unallocated req", ctx=auth_context
    )

    with pytest.raises(ValidationError):
        AiDerivationService().decompose_requirement_next_level(auth_context, req.id)
