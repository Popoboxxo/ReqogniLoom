"""
REQ-L2-AI-002 — AiDerivationToolGroup MCP tool tests.

Covers the four derivation tools against the credential-free mock provider,
plus schema advertisement and the invalid-input error paths. No network access.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from application.architecture_service import ArchitectureService
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    StakeholderNeed,
    Tenant,
    User,
    Workspace as PersistenceWorkspace,
)
from persistence.tenancy import TenantContext

from mcp_server.tools.ai_derivation import AiDerivationToolGroup

_API_KEY = "reqlo_testkey_ai"


def _make_need(tenant, workspace, title, description=""):
    """Create a StakeholderNeed directly via ORM (bypasses event publishing)."""
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="StakeholderNeed", tenant_id=tenant.id
    )
    return StakeholderNeed.objects.create(
        artifact=artifact, tenant_id=tenant.id, title=title, description=description
    )


@pytest.fixture
def ai_ctx(db):
    """Tenant + workspace + AuthContext with the TenantContext activated."""
    tenant = Tenant.objects.create(name="MCP AI", slug="mcp-ai", is_active=True)
    user = User.objects.create(username="mcpaiuser", email="mcpai@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="mcp-ai-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield tenant, ctx, workspace
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _exec(group, tool, params, ctx):
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def test_derive_requirements_from_need_tool(ai_ctx):
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2},
        ctx,
    )

    assert result.success
    assert len(result.data["drafts"]) == 2
    assert result.data["drafts"][0]["suggested_parent_id"] == str(need.id)


def test_suggest_architecture_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="req", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert result.success
    assert result.data["suggested_arch_element_ids"] == [str(arch.id)]


def test_suggest_architecture_already_assigned_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="req", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_decompose_next_level_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert result.success
    assert result.data["parent_requirement_id"] == str(req.id)
    assert len(result.data["drafts"]) >= 1


def test_decompose_without_allocation_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_decompose_unusable_llm_array_is_visible_error(ai_ctx, monkeypatch):
    """Issue #311: an unusable provider answer must reach the agent as an error.

    Guards the whole boundary, not just the service: the extraction failure
    raised by ``AiDerivationService._usable_entries`` has to arrive as a failed
    ToolResult, never as a successful preview with an empty ``drafts`` list.
    """
    import json

    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", description="content", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    class _StringListProvider:
        def complete(self, prompt, *, purpose="", context=None, timeout=None):
            return json.dumps(["Sub-requirement one", "Sub-requirement two"])

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: _StringListProvider()
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "INTERNAL_ERROR"


def test_decompose_empty_llm_array_is_annotated(ai_ctx, monkeypatch):
    """Issue #311: a legitimately empty answer stays a success, but says why."""
    import json

    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", description="content", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    class _EmptyProvider:
        def complete(self, prompt, *, purpose="", context=None, timeout=None):
            return json.dumps([])

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: _EmptyProvider()
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert result.success
    assert result.data["drafts"] == []
    assert result.data["note"]


def test_missing_uuid_is_validation_error(ai_ctx):
    _tenant, ctx, _workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_schema_advertises_six_tools():
    schemas = AiDerivationToolGroup().get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == {
        "ai_derivation.derive_requirements_from_need",
        "ai_derivation.suggest_architecture_for_requirement",
        "ai_derivation.decompose_requirement_next_level",
        "ai_derivation.derive_risks_from_architecture",
        "ai_derivation.derive_glossary_from_workspace",
        "ai_derivation.derive_adr_from_decision",
    }


# ---------------------------------------------------------------------------
# Phase 3 (REQ-L2-AI-003) — mode="write" / policy, and the RBAC gate that
# comes with it.
# ---------------------------------------------------------------------------


def test_derive_requirements_preview_mode_unchanged(ai_ctx):
    """mode omitted (defaults to 'preview') returns the identical Phase-2 shape."""
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2},
        ctx,
    )
    result_explicit_preview = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "preview"},
        ctx,
    )

    assert result.success and result_explicit_preview.success
    # Systemaudit item 11: the preview forwards the service dict verbatim,
    # which now also carries the mock-fallback flag.
    assert set(result.data.keys()) == {"drafts", "is_mock_fallback"}
    assert result.data == result_explicit_preview.data


def test_derive_requirements_write_mode_persists_requirements_and_traces(ai_ctx):
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) == 2
    from persistence.models import Requirement, TraceLink

    for entry in written:
        assert entry["status"] == "draft"
        assert Requirement.objects.filter(id=entry["id"]).exists()
        assert TraceLink.objects.filter(id=entry["trace_link_id"]).exists()


def test_suggest_architecture_write_mode_allocates_top_choice(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="req", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) == 1
    assert written[0]["target_id"] == str(arch.id)
    from persistence.models import TraceLink

    assert TraceLink.objects.filter(id=written[0]["trace_link_id"]).exists()


def test_derive_risks_from_architecture_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Payment Gateway", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_risks_from_architecture",
        {"architecture_element_id": str(arch.id)},
        ctx,
    )

    assert result.success
    assert result.data["architecture_element_id"] == str(arch.id)
    assert len(result.data["drafts"]) >= 1
    for draft in result.data["drafts"]:
        assert draft["probability"] in ("low", "medium", "high")
        assert draft["impact"] in ("low", "medium", "high")


def test_derive_risks_from_architecture_missing_element_is_not_found(ai_ctx):
    import uuid

    _tenant, ctx, _workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_risks_from_architecture",
        {"architecture_element_id": str(uuid.uuid4())},
        ctx,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_derive_risks_from_architecture_write_mode_persists_risks_and_traces(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Payment Gateway", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_risks_from_architecture",
        {"architecture_element_id": str(arch.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) >= 1
    from application.models import Risk
    from persistence.models import TraceLink

    for entry in written:
        assert entry["status"] == "draft"
        assert Risk.objects.filter(id=entry["id"]).exists()
        link = TraceLink.objects.get(id=entry["trace_link_id"])
        assert link.link_type == "traces"


def test_decompose_next_level_write_mode_persists_child_requirements(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) >= 1
    from persistence.models import Requirement, TraceLink

    for entry in written:
        assert Requirement.objects.filter(id=entry["id"]).exists()
        assert TraceLink.objects.filter(id=entry["trace_link_id"]).exists()


# ---------------------------------------------------------------------------
# issue #341 — mode="write" persisted nothing in se_mode workspaces because
# the 'derives-from' link was built backwards (Need -> Requirement).
# SE_LINK_SEMANTICS only allows Requirement -> StakeholderNeed, so
# TraceLinkService raised and @atomic_transaction rolled every draft back.
#
# The pre-existing write-mode tests above run in the default dev_mode
# workspace, where _check_se_semantics returns early — which is exactly why
# they never caught this. These tests switch the workspace to se_mode.
# ---------------------------------------------------------------------------


def _enable_se_mode(tenant, workspace):
    """Activate se_mode so TraceLinkService enforces SE endpoint semantics."""
    from presets.models import WorkspacePresetConfig

    WorkspacePresetConfig.objects.create(
        workspace=workspace,
        tenant_id=tenant.id,
        active_tier="extended",
        terminology_profile="se_mode",
    )


def test_derive_requirements_write_mode_persists_in_se_mode(ai_ctx):
    """#341: every draft must persist, with a child -> parent derives-from link."""
    tenant, ctx, workspace = ai_ctx
    _enable_se_mode(tenant, workspace)
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "write"},
        ctx,
    )

    assert result.success
    # The regression: written was [] and everything landed in failed.
    assert result.data.get("failed", []) == []
    written = result.data["written"]
    assert len(written) == 2

    from persistence.models import Requirement, TraceLink

    for entry in written:
        requirement = Requirement.objects.get(id=entry["id"])
        link = TraceLink.objects.get(id=entry["trace_link_id"])
        assert link.link_type == "derives-from"
        # Direction: the new Requirement is the link SOURCE, the Need the target.
        assert link.source_id == requirement.artifact_id
        assert link.target_id == need.artifact_id


def test_decompose_next_level_write_mode_link_direction_is_child_to_parent(ai_ctx):
    """#341 sibling: decompose built 'derives-from' parent -> child (inverted)."""
    _tenant, ctx, workspace = ai_ctx
    _enable_se_mode(_tenant, workspace)
    parent = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=parent.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(parent.id), "mode": "write"},
        ctx,
    )

    assert result.success
    assert result.data.get("failed", []) == []
    written = result.data["written"]
    assert len(written) >= 1

    from persistence.models import Requirement, TraceLink

    for entry in written:
        child = Requirement.objects.get(id=entry["id"])
        link = TraceLink.objects.get(id=entry["trace_link_id"])
        assert link.link_type == "derives-from"
        assert link.source_id == child.artifact_id
        assert link.target_id == parent.artifact_id


def test_invalid_mode_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    need = _make_need(_tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "mode": "bogus"},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_ai_derivation_tool_names_registered_as_write_tools():
    """All six tools are name-gated as write tools (tool_registry._WRITE_TOOL_PREFIXES),
    complementing the real-RBAC-dispatch proof below.
    """
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "ai_derivation.derive_requirements_from_need" in _WRITE_TOOL_PREFIXES
    assert (
        "ai_derivation.suggest_architecture_for_requirement" in _WRITE_TOOL_PREFIXES
    )
    assert (
        "ai_derivation.decompose_requirement_next_level" in _WRITE_TOOL_PREFIXES
    )
    assert "ai_derivation.derive_risks_from_architecture" in _WRITE_TOOL_PREFIXES
    assert "ai_derivation.derive_glossary_from_workspace" in _WRITE_TOOL_PREFIXES
    assert "ai_derivation.derive_adr_from_decision" in _WRITE_TOOL_PREFIXES


def test_derive_glossary_from_workspace_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    RequirementService().create_requirement(
        workspace_id=workspace.id, title="Some requirement", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_glossary_from_workspace",
        {"workspace_id": str(workspace.id)},
        ctx,
    )

    assert result.success
    assert result.data["workspace_id"] == str(workspace.id)
    assert len(result.data["drafts"]) >= 1
    for draft in result.data["drafts"]:
        assert set(draft.keys()) == {"term", "definition", "synonyms", "abbreviation"}


def test_derive_glossary_from_workspace_missing_workspace_is_not_found(ai_ctx):
    import uuid

    _tenant, ctx, _workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_glossary_from_workspace",
        {"workspace_id": str(uuid.uuid4())},
        ctx,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_derive_glossary_from_workspace_write_mode_persists_terms_no_trace_link(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    RequirementService().create_requirement(
        workspace_id=workspace.id, title="Some requirement", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_glossary_from_workspace",
        {"workspace_id": str(workspace.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) >= 1
    from persistence.models import GlossaryTerm

    for entry in written:
        assert entry["status"] == "draft"
        assert "trace_link_id" not in entry
        assert GlossaryTerm.objects.filter(id=entry["id"]).exists()


def test_derive_glossary_from_workspace_write_mode_duplicate_term_is_reported_as_failed(
    ai_ctx,
):
    """A colliding (workspace, term) surfaces per-draft in 'failed', not a 500."""
    from application.glossary_service import GlossaryService

    _tenant, ctx, workspace = ai_ctx
    RequirementService().create_requirement(
        workspace_id=workspace.id, title="Some requirement", ctx=ctx
    )
    # Pre-create a term with the exact name the mock provider will emit for
    # this workspace (see llm_adapter.providers "derive_glossary_from_workspace"
    # branch: f"Term for {workspace_id}").
    GlossaryService().create(
        ctx=ctx,
        workspace_id=workspace.id,
        term=f"Term for {workspace.id}",
        definition="Pre-existing term.",
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_glossary_from_workspace",
        {"workspace_id": str(workspace.id), "mode": "write"},
        ctx,
    )

    assert result.success
    assert result.data["written"] == []
    assert len(result.data["failed"]) == 1
    assert "already exists" in result.data["failed"][0]["error"]


def test_derive_adr_from_decision_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {
            "workspace_id": str(workspace.id),
            "decision_description": "We will use Postgres instead of MySQL.",
        },
        ctx,
    )

    assert result.success
    assert result.data["workspace_id"] == str(workspace.id)
    draft = result.data["draft"]
    assert set(draft.keys()) == {"title", "description", "context", "consequences"}


def test_derive_adr_from_decision_missing_workspace_is_not_found(ai_ctx):
    import uuid

    _tenant, ctx, _workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {
            "workspace_id": str(uuid.uuid4()),
            "decision_description": "Some decision.",
        },
        ctx,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_derive_adr_from_decision_missing_description_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {"workspace_id": str(workspace.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_derive_adr_from_decision_write_mode_persists_adr_no_trace_link(ai_ctx):
    """The write path creates NO trace_link_id — analogous to the Glossary
    pair's test, but for a different reason (see
    AiDerivationService._write_adr_draft's docstring): there is no source
    entity to link from, not an unresolvable target type.
    """
    _tenant, ctx, workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {
            "workspace_id": str(workspace.id),
            "decision_description": "We will use Postgres instead of MySQL.",
            "mode": "write",
        },
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert "trace_link_id" not in written
    assert written["status"] == "draft"
    from application.models import Adr

    assert Adr.objects.filter(id=written["id"]).exists()


def test_derive_adr_from_decision_write_mode_no_trace_link_created_at_all(ai_ctx):
    """Explicit end-to-end proof: after a write, no TraceLink row references
    the new Adr's artifact at all (not just that the response omits the key).
    """
    _tenant, ctx, workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {
            "workspace_id": str(workspace.id),
            "decision_description": "We will use Postgres instead of MySQL.",
            "mode": "write",
        },
        ctx,
    )

    assert result.success
    from application.models import Adr
    from persistence.models import TraceLink

    adr = Adr.objects.get(id=result.data["written"]["id"])
    assert not TraceLink.objects.filter(
        source_id=adr.artifact_id
    ).exists() and not TraceLink.objects.filter(target_id=adr.artifact_id).exists()


@pytest.mark.django_db
def test_ai_derivation_write_tools_require_editor_role():
    """A Viewer's mode='write' call is PERMISSION_DENIED via the REAL
    ToolRegistry RBAC gate (not just the mocked ``ai_ctx`` fixture used
    elsewhere in this file) — mirrors test_mcp_rbac_role_matrix.py's pattern.

    The gate is name-based, not mode-aware: this also covers mode='preview'
    calls by the same tool name being denied (documented behaviour change,
    see mcp_server/tools/ai_derivation.py module docstring).
    """
    import uuid
    from unittest.mock import MagicMock

    from auth_tenancy.models import ROLE_VIEWER, UserRole
    from auth_tenancy.services.authentication import AuthenticationService
    from mcp_server.protocol_handler import ToolResult
    from mcp_server.tool_registry import ToolRegistry
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace as PersistenceWorkspace

    slug = f"mcp-viewer-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name="T-viewer", slug=slug, is_active=True)
    user = User.objects.create(username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="WS-viewer")
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()
    api_key = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="mcp-ai-viewer-key"
    ).plaintext

    registry = ToolRegistry()
    sink = MagicMock()
    sink.execute_tool.return_value = ToolResult.ok({"drafts": []})
    registry.register_groups({"ai_derivation": sink})

    result = registry.dispatch_request(
        tool_name="ai_derivation.derive_requirements_from_need",
        params={"need_id": str(uuid.uuid4()), "workspace_id": str(workspace.id)},
        api_key=api_key,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    sink.execute_tool.assert_not_called()
