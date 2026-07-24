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
from llm_adapter.providers import MAX_PROMPT_CONTENT_CHARS
from persistence.models import (
    Artifact,
    PromptTemplate,
    StakeholderNeed,
    Tenant,
    TraceLink,
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


# ---------------------------------------------------------------------------
# REQ-046 — long descriptions are truncated before being embedded in a prompt
# ---------------------------------------------------------------------------


def test_derive_requirements_truncates_long_need_description(
    auth_context, workspace, monkeypatch
):
    """An oversized need description is bounded, not embedded verbatim."""
    long_description = "d" * (MAX_PROMPT_CONTENT_CHARS + 500)
    need = _make_need(auth_context, workspace, "N", long_description)
    provider = _CaptureProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().derive_requirements_from_need(auth_context, need.id, n=1)

    prompt = provider.calls[0]["prompt"]
    assert long_description not in prompt
    assert "[truncated]" in prompt


def test_suggest_architecture_truncates_long_requirement_description(
    auth_context, workspace, monkeypatch
):
    """An oversized requirement description is bounded before prompt embedding."""
    long_description = "r" * (MAX_PROMPT_CONTENT_CHARS + 500)
    req = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Some requirement",
        description=long_description,
        ctx=auth_context,
    )
    provider = _CaptureProvider(json.dumps([]))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().suggest_architecture_for_requirement(auth_context, req.id)

    prompt = provider.calls[0]["prompt"]
    assert long_description not in prompt
    assert "[truncated]" in prompt


# ---------------------------------------------------------------------------
# REQ-046 — backward compatibility with pre-existing user-defined templates
# ---------------------------------------------------------------------------


def test_old_template_with_only_req_title_still_renders(
    auth_context, workspace, monkeypatch
):
    """A tenant template written before REQ-046 (no {req_description}/
    {arch_elements_json} placeholders) must still render without error —
    `_render` substitutes known placeholders individually instead of using
    `str.format`, so extra values that have no matching placeholder are
    simply not inserted, and missing placeholders never raise KeyError.
    """
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        PromptTemplate.objects.create(
            tenant_id=auth_context.tenant_id,
            sysreq_to_arch_assign="Legacy prompt for {req_title} only.",
        )
    finally:
        TenantContext.clear_tenant()

    req = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Legacy Requirement Title",
        description="Some description that the old template ignores.",
        ctx=auth_context,
    )
    provider = _CaptureProvider(json.dumps([]))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    # Must not raise despite the template lacking {req_description} /
    # {arch_elements_json} placeholders that the service always supplies.
    result = AiDerivationService().suggest_architecture_for_requirement(
        auth_context, req.id
    )

    assert result == {"suggested_arch_element_ids": []}
    prompt = provider.calls[0]["prompt"]
    assert prompt == "Legacy prompt for Legacy Requirement Title only."


# ---------------------------------------------------------------------------
# Flow 4 (SysEng 2.0 N5) — derive a TestCase draft from a requirement
# ---------------------------------------------------------------------------


def test_derive_testcase_returns_draft(auth_context, workspace):
    """Mock provider yields a single TestCase draft with title/description/steps."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="The system shall log in users", ctx=auth_context
    )

    result = AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)

    assert result["requirement_id"] == str(req.id)
    draft = result["draft"]
    assert set(draft.keys()) == {"title", "description", "steps"}
    assert draft["title"]
    assert draft["description"]
    assert len(draft["steps"]) >= 1
    for step in draft["steps"]:
        assert set(step.keys()) == {"step", "expected_result"}


def test_derive_testcase_no_preset_gate(auth_context, workspace):
    """Unlike decompose_requirement_next_level, no allocation is required."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Unallocated requirement", ctx=auth_context
    )

    # Must not raise ValidationError despite having no allocated-to link.
    result = AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)
    assert result["draft"]["title"]


def test_derive_testcase_formats_prompt(auth_context, workspace, monkeypatch):
    """The rendered prompt substitutes requirement title/description."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Distinctive Requirement Title",
        description="Distinctive Requirement Description",
        ctx=auth_context,
    )
    provider = _CaptureProvider(
        json.dumps({"title": "t", "description": "d", "steps": []})
    )
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)

    prompt = provider.calls[0]["prompt"]
    assert "Distinctive Requirement Title" in prompt
    assert "Distinctive Requirement Description" in prompt
    assert "{req_title}" not in prompt and "{req_description}" not in prompt
    assert provider.calls[0]["purpose"] == "test_derive_from_requirement"


def test_derive_testcase_invalid_json_raises(auth_context, workspace, monkeypatch):
    """A non-JSON provider response surfaces as LlmResponseError."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="R", ctx=auth_context
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider",
        lambda *a, **k: _CaptureProvider("this is not json"),
    )

    with pytest.raises(LlmResponseError):
        AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)


def test_derive_testcase_json_array_raises(auth_context, workspace, monkeypatch):
    """A JSON array (not object) response is rejected — draft must be an object."""
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="R", ctx=auth_context
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider",
        lambda *a, **k: _CaptureProvider(json.dumps([{"title": "t"}])),
    )

    with pytest.raises(LlmResponseError):
        AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)


def test_derive_testcase_missing_requirement_raises(auth_context):
    import uuid

    with pytest.raises(NotFoundError):
        AiDerivationService().derive_testcase_from_requirement(auth_context, uuid.uuid4())


def test_derive_testcase_truncates_long_requirement_description(
    auth_context, workspace, monkeypatch
):
    """An oversized requirement description is bounded before prompt embedding."""
    long_description = "r" * (MAX_PROMPT_CONTENT_CHARS + 500)
    req = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Some requirement",
        description=long_description,
        ctx=auth_context,
    )
    provider = _CaptureProvider(json.dumps({"title": "t", "description": "d", "steps": []}))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().derive_testcase_from_requirement(auth_context, req.id)

    prompt = provider.calls[0]["prompt"]
    assert long_description not in prompt


# ---------------------------------------------------------------------------
# Flow 5 (Phase 3) — derive risk drafts from an architecture element
# ---------------------------------------------------------------------------


def test_derive_risks_from_architecture_returns_drafts_with_valid_probability_impact(
    auth_context, workspace
):
    """Mock provider yields a risk draft with valid enum probability/impact."""
    ae = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Payment Gateway", ctx=auth_context
    )

    result = AiDerivationService().derive_risks_from_architecture(auth_context, ae.id)

    assert result["architecture_element_id"] == str(ae.id)
    assert len(result["drafts"]) >= 1
    for draft in result["drafts"]:
        assert set(draft.keys()) == {
            "title",
            "description",
            "probability",
            "impact",
            "category",
        }
        assert draft["probability"] in ("low", "medium", "high")
        assert draft["impact"] in ("low", "medium", "high")
        assert draft["category"] in (
            "technical",
            "operational",
            "organizational",
            "business",
        )


def test_derive_risks_from_architecture_formats_prompt(auth_context, workspace, monkeypatch):
    """The rendered prompt substitutes the architecture element title/description."""
    ae = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id,
        title="Distinctive Element Title",
        description="Distinctive Element Description",
        ctx=auth_context,
    )
    provider = _CaptureProvider(json.dumps([]))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().derive_risks_from_architecture(auth_context, ae.id)

    prompt = provider.calls[0]["prompt"]
    assert "Distinctive Element Title" in prompt
    assert "Distinctive Element Description" in prompt
    assert "{ae_title}" not in prompt and "{ae_description}" not in prompt
    assert provider.calls[0]["purpose"] == "derive_risks_from_architecture"


def test_derive_risks_from_architecture_clamps_invalid_enum_values(
    auth_context, workspace, monkeypatch
):
    """An invalid/missing probability, impact or category is clamped, not raised."""
    ae = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Element", ctx=auth_context
    )
    provider = _CaptureProvider(
        json.dumps(
            [
                {
                    "title": "Hallucinated risk",
                    "description": "d",
                    "probability": "extreme",
                    "impact": None,
                    "category": "not-a-category",
                },
                {"title": "Sparse risk"},
            ]
        )
    )
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    result = AiDerivationService().derive_risks_from_architecture(auth_context, ae.id)

    assert result["drafts"][0]["probability"] == "medium"
    assert result["drafts"][0]["impact"] == "medium"
    assert result["drafts"][0]["category"] == "technical"
    assert result["drafts"][1]["probability"] == "medium"
    assert result["drafts"][1]["impact"] == "medium"
    assert result["drafts"][1]["category"] == "technical"


def test_derive_risks_from_architecture_invalid_json_raises(
    auth_context, workspace, monkeypatch
):
    """A non-JSON provider response surfaces as LlmResponseError."""
    ae = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Element", ctx=auth_context
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider",
        lambda *a, **k: _CaptureProvider("this is not json"),
    )

    with pytest.raises(LlmResponseError):
        AiDerivationService().derive_risks_from_architecture(auth_context, ae.id)


def test_derive_risks_from_architecture_missing_element_raises(auth_context):
    import uuid

    with pytest.raises(NotFoundError):
        AiDerivationService().derive_risks_from_architecture(auth_context, uuid.uuid4())


def test_derive_risks_from_architecture_truncates_long_description(
    auth_context, workspace, monkeypatch
):
    """An oversized element description is bounded before prompt embedding."""
    long_description = "d" * (MAX_PROMPT_CONTENT_CHARS + 500)
    ae = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id,
        title="Element",
        description=long_description,
        ctx=auth_context,
    )
    provider = _CaptureProvider(json.dumps([]))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)

    AiDerivationService().derive_risks_from_architecture(auth_context, ae.id)

    prompt = provider.calls[0]["prompt"]
    assert long_description not in prompt
    assert "[truncated]" in prompt


# ---------------------------------------------------------------------------
# Phase 3 — write-mode helpers (_write_derived_entity / _auto_approve)
# ---------------------------------------------------------------------------


@pytest.fixture
def need_with_workflow(auth_context, workspace):
    """A StakeholderNeed's Artifact id + a Requirement workflow definition.

    Uses the "extended" preset: its draft->in_review transition is reachable
    by the shared ``auth_context`` fixture's "editor" role (unlike the
    "standard" preset, whose only exits from draft require "approver"/"admin"
    — see ``_standard_transitions``), so ``policy="auto"`` tests are
    meaningful against the shared fixture.

    Returns ``(need_artifact_id, workspace_id)`` rather than the
    StakeholderNeed's own PK: ``TraceLinkService._resolve_artifact_id`` only
    resolves Artifact/Requirement/ArchitectureElement/Adr ids, not
    StakeholderNeed ids (confirmed by reading trace_link_service.py before
    writing this fixture) — so a trace link sourced from a need must be
    built from ``need.artifact_id``, exactly like ``mcp_server/tools/
    ai_derivation.py``'s write-mode handler does.
    """
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=auth_context.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()
    need = _make_need(auth_context, workspace, "Users need workflow-aware derivation")
    return need.artifact_id, workspace.id


def test_write_derived_entity_creates_entity_and_trace_link(
    need_with_workflow, auth_context
):
    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    result = svc._write_derived_entity(
        ctx=auth_context,
        workspace_id=workspace_id,
        item_type="Requirement",
        create_fn=lambda: RequirementService().create_requirement(
            workspace_id=workspace_id,
            title="Derived Req",
            ctx=auth_context,
            description="from need",
        ),
        source_entity_id=need_id,
        source_item_type="StakeholderNeed",
        link_type="derives-from",
        policy="manual",
    )

    assert result["status"] == "draft"
    from persistence.models import Requirement

    assert Requirement.objects.filter(id=result["id"]).exists()
    # TraceLink lives in persistence.models (already imported at module top) —
    # confirmed against persistence/models.py before writing this test.
    assert TraceLink.objects.filter(id=result["trace_link_id"]).exists()


def test_write_derived_entity_rolls_back_entity_on_trace_link_failure(
    need_with_workflow, auth_context
):
    """REQ-L3-PL003-002: a failing trace-link creation must not leave an
    orphaned, un-linked entity behind.

    ``create_trace_link`` raises ``ValidationError`` for an invalid
    ``link_type`` *before* touching the database (confirmed by reading
    ``TraceLinkService.create_trace_link`` before writing this test — the
    ``link_type not in VALID_LINK_TYPES`` check runs first). Since
    ``_write_derived_entity`` is wrapped in ``@atomic_transaction``, the
    ``Requirement`` created moments earlier by ``create_fn()`` must be rolled
    back together with the failed trace link — no partially-written entity
    may survive in the database.
    """
    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    from persistence.models import Requirement

    before_count = Requirement.objects.count()

    with pytest.raises(ValidationError):
        svc._write_derived_entity(
            ctx=auth_context,
            workspace_id=workspace_id,
            item_type="Requirement",
            create_fn=lambda: RequirementService().create_requirement(
                workspace_id=workspace_id,
                title="Should Be Rolled Back",
                ctx=auth_context,
                description="orphan candidate",
            ),
            source_entity_id=need_id,
            source_item_type="StakeholderNeed",
            link_type="not-a-real-link-type",
            policy="manual",
        )

    assert Requirement.objects.count() == before_count
    assert not Requirement.objects.filter(title="Should Be Rolled Back").exists()


def test_write_derived_entity_policy_auto_advances_state(
    need_with_workflow, auth_context
):
    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    result = svc._write_derived_entity(
        ctx=auth_context,
        workspace_id=workspace_id,
        item_type="Requirement",
        create_fn=lambda: RequirementService().create_requirement(
            workspace_id=workspace_id, title="Derived Req 2", ctx=auth_context,
        ),
        source_entity_id=need_id,
        source_item_type="StakeholderNeed",
        link_type="derives-from",
        policy="auto",
    )

    # "extended" preset's draft->in_review transition is allowed for the
    # "editor" role held by auth_context, so the walk must advance past draft.
    assert result["status"] != "draft"


def test_write_derived_entity_policy_manual_stays_draft(
    need_with_workflow, auth_context
):
    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    result = svc._write_derived_entity(
        ctx=auth_context,
        workspace_id=workspace_id,
        item_type="Requirement",
        create_fn=lambda: RequirementService().create_requirement(
            workspace_id=workspace_id, title="Derived Req 3", ctx=auth_context,
        ),
        source_entity_id=need_id,
        source_item_type="StakeholderNeed",
        link_type="derives-from",
        policy="manual",
    )

    assert result["status"] == "draft"


def test_auto_approve_never_raises_when_role_lacks_permission(
    need_with_workflow, workspace, auth_context
):
    """A ctx without a role that can perform the next transition stops the
    walk at the current state instead of propagating WorkflowTransitionError.
    """
    need_id, workspace_id = need_with_workflow
    viewer_ctx = AuthContext(
        user_id=auth_context.user_id,
        tenant_id=auth_context.tenant_id,
        active_roles=("viewer",),
        auth_method="test",
        api_key_id=None,
        tenant_name="ai-tenant",
    )
    svc = AiDerivationService()
    created = RequirementService().create_requirement(
        workspace_id=workspace_id, title="Derived Req 4", ctx=auth_context,
    )

    status = svc._auto_approve("Requirement", created.id, workspace_id, viewer_ctx)

    assert status == "draft"
