"""
Dispatch-level tests for AiDerivationToolGroup (REQ-L2-AI-001..003).

Companion to ``test_ai_derivation_tool_group.py``: that module already proves
the six derivation tools against the credential-free mock provider, the
schema advertisement and most write-mode persistence. This module drives the
same PUBLIC tool-group interface (``BaseToolGroup.execute_tool``) and closes
only the dispatch-contract gaps that file leaves open:

* per-tool ``NOT_FOUND`` mapping, including the cross-tenant read fence
  (another tenant's need / requirement / architecture element / workspace),
* parameter validation for every tool's required id plus the ``n``,
  ``policy`` and ``decision_description`` value checks,
* the ``LlmResponseError`` -> ``INTERNAL_ERROR`` mapping for ALL SIX tools,
  including the hallucinated-architecture-id answer (issue #825),
* the write-mode response envelope (``is_mock_fallback`` + ``proposal``),
  the per-draft ``failed`` collection and the ``policy="auto"`` variant,
* the LLM-response cache (REQ-105) seen through the tool group,
* the unknown-tool dispatch answer of this group.

No network access: providers are faked via ``unittest.mock.patch`` on
``llm_adapter.providers.get_provider``.

leaf_id : REQ-L2-AI-002
req_id  : REQ-L2-AI-003
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.core.cache import cache

from application.architecture_service import ArchitectureService
from application.base import ValidationError
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.ai_derivation import AiDerivationToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, StakeholderNeed, Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_ai_dispatch"

# tool name -> the required UUID parameter its schema declares
_ID_PARAM_BY_TOOL = {
    "ai_derivation.derive_requirements_from_need": "need_id",
    "ai_derivation.suggest_architecture_for_requirement": "requirement_id",
    "ai_derivation.decompose_requirement_next_level": "requirement_id",
    "ai_derivation.derive_risks_from_architecture": "architecture_element_id",
    "ai_derivation.derive_glossary_from_workspace": "workspace_id",
    "ai_derivation.derive_adr_from_decision": "workspace_id",
}

# the entity each tool needs in place before it can reach the LLM
_SOURCE_KIND_BY_TOOL = {
    "ai_derivation.derive_requirements_from_need": "need",
    "ai_derivation.suggest_architecture_for_requirement": "requirement",
    "ai_derivation.decompose_requirement_next_level": "allocated_requirement",
    "ai_derivation.derive_risks_from_architecture": "architecture_element",
    "ai_derivation.derive_glossary_from_workspace": "workspace",
    "ai_derivation.derive_adr_from_decision": "workspace",
}


class _FakeProvider:
    """Minimal provider double returning a canned (non-JSON) string."""

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        return "this is not json"


class _CannedProvider:
    """Provider double returning a fixed payload and counting its calls."""

    PROVIDER_NAME = "fake-canned"

    def __init__(self, payload) -> None:
        self._payload = payload
        self.calls = 0

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls += 1
        return json.dumps(self._payload)


def _exec(group, tool, params, ctx):
    """Run *tool* through the public tool-group dispatch interface."""
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


@pytest.fixture
def caller():
    """Tenant + workspace + AuthContext, tenant scoped for the whole test.

    Mirrors ``test_ai_derivation_tool_group.py``'s ``ai_ctx`` fixture: the
    request tenant is armed for BOTH isolation layers (thread-local +
    PostgreSQL ``app.current_tenant``), so the RLS fence of the test database
    applies while the tool runs.
    """
    tenant = Tenant.objects.create(name="MCP AI dispatch", slug="mcp-ai-dispatch")
    user = User.objects.create(
        username="mcpai-dispatch-user", email="mcpai-dispatch@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="ws-dispatch")
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )
        yield tenant, workspace, ctx
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _foreign_scope(name: str, restore_tenant_id):
    """Create a second tenant + workspace, then re-arm the caller's scope.

    The RLS session variable is connection-scoped, so creating the foreign
    rows under their own tenant would otherwise leave the CALLER's fence
    disarmed for the rest of the test — the re-arm at the end is what makes
    the assertions below a real cross-tenant proof.
    """
    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(tenant=tenant, name=f"{name}-ws")
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    finally:
        set_request_tenant(restore_tenant_id)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def _make_need(tenant, workspace, title: str):
    """Create a StakeholderNeed directly via ORM (bypasses event publishing)."""
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="StakeholderNeed", tenant_id=tenant.id
    )
    return StakeholderNeed.objects.create(
        artifact=artifact, tenant_id=tenant.id, title=title, description="desc"
    )


def _make_requirement(workspace_id, ctx, title: str):
    return RequirementService().create_requirement(
        workspace_id=workspace_id, title=title, ctx=ctx
    )


def _make_architecture_element(workspace_id, ctx, title: str):
    return ArchitectureService().create_architecture_element(
        workspace_id=workspace_id, title=title, ctx=ctx
    )


def _make_source(caller_scope, tool: str):
    """Create the entity *tool* needs and return its id parameters."""
    _tenant, workspace, ctx = caller_scope
    kind = _SOURCE_KIND_BY_TOOL[tool]
    if kind == "need":
        return {"need_id": str(_make_need(_tenant, workspace, "Dispatch need").id)}
    if kind == "requirement":
        req = _make_requirement(workspace.id, ctx, "Dispatch req")
        return {"requirement_id": str(req.id)}
    if kind == "allocated_requirement":
        req = _make_requirement(workspace.id, ctx, "Dispatch parent")
        arch = _make_architecture_element(workspace.id, ctx, "Dispatch comp")
        TraceLinkService().allocate(
            requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
        )
        return {"requirement_id": str(req.id)}
    if kind == "architecture_element":
        return {
            "architecture_element_id": str(
                _make_architecture_element(workspace.id, ctx, "Dispatch gateway").id
            )
        }
    return {"workspace_id": str(workspace.id)}


# ---------------------------------------------------------------------------
# NOT_FOUND mapping — unknown and cross-tenant sources
# ---------------------------------------------------------------------------


def test_derive_requirements_unknown_need_is_not_found(caller):
    """A syntactically valid but unknown need id is NOT_FOUND, not a 500."""
    _tenant, _workspace, ctx = caller

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(uuid4())},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_suggest_architecture_unknown_requirement_is_not_found(caller):
    """Flow 2 maps an unknown requirement id to NOT_FOUND (not VALIDATION)."""
    _tenant, _workspace, ctx = caller

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(uuid4())},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_decompose_unknown_requirement_is_not_found(caller):
    """Flow 3 maps an unknown requirement id to NOT_FOUND (not VALIDATION)."""
    _tenant, _workspace, ctx = caller

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(uuid4())},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_entity_scoped_tools_fence_foreign_tenant_sources(caller):
    """Cross-tenant read fence: another tenant's entities are NOT_FOUND.

    The queries run under the CALLER's tenant (``_set_tenant_context``), so
    the foreign rows must be invisible for every entity-scoped tool — the
    response is an error, never the other tenant's drafts.
    """
    tenant_a, _workspace_a, ctx_a = caller
    tenant_b, workspace_b, ctx_b = _foreign_scope("mcp-ai-dispatch-b", tenant_a.id)

    foreign_need = _make_need(tenant_b, workspace_b, "Tenant B need")
    foreign_req = _make_requirement(workspace_b.id, ctx_b, "Tenant B req")
    foreign_arch = _make_architecture_element(
        workspace_b.id, ctx_b, "Tenant B component"
    )

    cases = [
        (
            "ai_derivation.derive_requirements_from_need",
            {"need_id": str(foreign_need.id)},
        ),
        (
            "ai_derivation.suggest_architecture_for_requirement",
            {"requirement_id": str(foreign_req.id)},
        ),
        (
            "ai_derivation.decompose_requirement_next_level",
            {"requirement_id": str(foreign_req.id)},
        ),
        (
            "ai_derivation.derive_risks_from_architecture",
            {"architecture_element_id": str(foreign_arch.id)},
        ),
    ]
    for tool_name, params in cases:
        result = _exec(AiDerivationToolGroup(), tool_name, params, ctx_a)
        assert result.success is False, tool_name
        assert result.error_code == "NOT_FOUND", tool_name


def test_workspace_scoped_tools_fence_foreign_tenant_workspace(caller):
    """Cross-tenant fence for the two workspace-scoped flows (glossary/ADR)."""
    tenant_a, _workspace_a, ctx_a = caller
    _tenant_b, workspace_b, _ctx_b = _foreign_scope("mcp-ai-dispatch-b", tenant_a.id)

    glossary = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_glossary_from_workspace",
        {"workspace_id": str(workspace_b.id)},
        ctx_a,
    )
    adr = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {
            "workspace_id": str(workspace_b.id),
            "decision_description": "Tenant B's decision.",
        },
        ctx_a,
    )

    assert glossary.success is False
    assert glossary.error_code == "NOT_FOUND"
    assert adr.success is False
    assert adr.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_missing_required_uuid_param_is_validation_error(caller, tool_name):
    """Every tool's schema-required id is enforced before any service call."""
    _tenant, _workspace, ctx = caller

    result = _exec(AiDerivationToolGroup(), tool_name, {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert _ID_PARAM_BY_TOOL[tool_name] in result.message


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_non_uuid_param_is_validation_error(caller, tool_name):
    """An unparseable id is a VALIDATION_ERROR naming the offending value."""
    _tenant, _workspace, ctx = caller
    param = _ID_PARAM_BY_TOOL[tool_name]
    params = {param: "not-a-uuid"}
    if param == "workspace_id" and tool_name.endswith("adr_from_decision"):
        params["decision_description"] = "Some decision."

    result = _exec(AiDerivationToolGroup(), tool_name, params, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "not-a-uuid" in result.message


def test_derive_requirements_non_integer_n_is_validation_error(caller):
    """A non-numeric ``n`` keeps its dedicated message (not a coerced 3)."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": "two"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "'n' must be an integer."


def test_invalid_policy_is_validation_error(caller):
    """``policy`` is validated alongside ``mode`` with a stable message."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "policy": "bogus"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "'policy' must be one of ('manual', 'auto'), got 'bogus'."


@pytest.mark.parametrize("bad_description", ["", "   ", 42, ["text"]])
def test_derive_adr_description_must_be_a_non_empty_string(caller, bad_description):
    """Empty, blank and non-string descriptions are rejected up front."""
    _tenant, workspace, ctx = caller

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_adr_from_decision",
        {"workspace_id": str(workspace.id), "decision_description": bad_description},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# LLM error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_unparseable_provider_answer_maps_to_internal_error(caller, tool_name):
    """An unusable provider answer reaches the agent as INTERNAL_ERROR.

    Companion to ``test_ai_derivation_tool_group.py``'s decompose-only proof:
    every tool's handler maps :class:`LlmResponseError` to the same stable
    error code, never to a successful empty preview and never to a 500.
    """
    params = _make_source(caller, tool_name)
    if tool_name.endswith("adr_from_decision"):
        params["decision_description"] = "We will use Postgres instead of MySQL."

    with patch("llm_adapter.providers.get_provider", return_value=_FakeProvider()):
        result = _exec(AiDerivationToolGroup(), tool_name, params, caller[2])

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"


def test_suggest_architecture_hallucinated_ids_map_to_internal_error(caller):
    """Issue #825: an answer offering no offered element is INTERNAL_ERROR."""
    _tenant, workspace, ctx = caller
    req = _make_requirement(workspace.id, ctx, "Dispatch req")
    arch = _make_architecture_element(workspace.id, ctx, "Dispatch comp")
    hallucinated = _CannedProvider([str(uuid4())])

    with patch("llm_adapter.providers.get_provider", return_value=hallucinated):
        result = _exec(
            AiDerivationToolGroup(),
            "ai_derivation.suggest_architecture_for_requirement",
            {"requirement_id": str(req.id)},
            ctx,
        )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert str(arch.id) not in result.message


# ---------------------------------------------------------------------------
# LLM happy paths through a faked (non-mock) provider + the response cache
# ---------------------------------------------------------------------------


def test_real_provider_drafts_are_forwarded_and_not_marked_as_mock(caller):
    """A genuine provider's drafts flow through verbatim, fallback flag False."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")
    provider = _CannedProvider(
        [{"title": "Real R1", "description": "Real D1", "rationale": "Real why."}]
    )

    with patch("llm_adapter.providers.get_provider", return_value=provider):
        result = _exec(
            AiDerivationToolGroup(),
            "ai_derivation.derive_requirements_from_need",
            {"need_id": str(need.id), "n": 1},
            ctx,
        )

    assert result.success is True
    assert result.data["is_mock_fallback"] is False
    assert provider.calls == 1
    assert result.data["drafts"] == [
        {
            "title": "Real R1",
            "description": "Real D1",
            "rationale": "Real why.",
            "suggested_parent_id": str(need.id),
        }
    ]


def test_provider_answer_is_served_from_cache_on_the_second_call(caller):
    """REQ-105: an identical re-derivation is answered from the cache."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")
    provider = _CannedProvider(
        [{"title": "Cached R1", "description": "Cached D1", "rationale": "Cached why."}]
    )
    cache.clear()
    params = {"need_id": str(need.id), "n": 1}

    try:
        with patch("llm_adapter.providers.get_provider", return_value=provider):
            first = _exec(
                AiDerivationToolGroup(),
                "ai_derivation.derive_requirements_from_need",
                params,
                ctx,
            )
            second = _exec(
                AiDerivationToolGroup(),
                "ai_derivation.derive_requirements_from_need",
                params,
                ctx,
            )
    finally:
        cache.clear()

    assert first.success is True and second.success is True
    assert first.data == second.data
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# Write-mode envelope
# ---------------------------------------------------------------------------


def test_write_response_carries_mock_fallback_flag_and_proposal_block(caller):
    """Systemaudit item 11 + #1089: the write envelope is self-describing."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 1, "mode": "write"},
        ctx,
    )

    assert result.success is True
    assert result.data["is_mock_fallback"] is False
    assert set(result.data["proposal"]) == {
        "state",
        "is_proposal",
        "supported",
        "proposed_by",
        "label",
        "reason",
    }
    assert "failed" not in result.data
    entry = result.data["written"][0]
    assert set(entry) >= {"id", "status", "trace_link_id", "proposal"}


def test_decompose_write_response_carries_proposal_block(caller):
    """The decompose write path reports the same envelope per written child."""
    _tenant, workspace, ctx = caller
    req = _make_requirement(workspace.id, ctx, "Dispatch parent")
    arch = _make_architecture_element(workspace.id, ctx, "Dispatch comp")
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success is True
    assert result.data["is_mock_fallback"] is False
    assert len(result.data["written"]) >= 1
    for entry in result.data["written"]:
        # The workspace decides whether "proposed" is expressible; the block
        # must always be present so the caller can see which case applies.
        assert set(entry["proposal"]) == {
            "state",
            "is_proposal",
            "supported",
            "proposed_by",
            "label",
            "reason",
        }


def test_suggest_architecture_write_without_candidates_writes_nothing(caller):
    """No offered element -> success with an empty ``written`` list."""
    _tenant, workspace, ctx = caller
    req = _make_requirement(workspace.id, ctx, "Lonely req")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success is True
    assert result.data["written"] == []
    assert result.data["is_mock_fallback"] is False


@pytest.mark.parametrize(
    "tool_name",
    [
        "ai_derivation.derive_requirements_from_need",
        "ai_derivation.decompose_requirement_next_level",
        "ai_derivation.derive_risks_from_architecture",
        "ai_derivation.derive_glossary_from_workspace",
        "ai_derivation.derive_adr_from_decision",
    ],
)
def test_policy_auto_is_accepted_by_every_write_tool(caller, tool_name):
    """``policy='auto'`` is forwarded without turning a write into a failure."""
    _tenant, _workspace, ctx = caller
    params = _make_source(caller, tool_name)
    if tool_name.endswith("adr_from_decision"):
        params["decision_description"] = "We will use Postgres instead of MySQL."
    params.update({"mode": "write", "policy": "auto"})

    result = _exec(AiDerivationToolGroup(), tool_name, params, ctx)

    assert result.success is True, result.message
    assert result.data.get("failed", []) == []
    if tool_name.endswith("adr_from_decision"):
        assert result.data["written"]["id"]
    else:
        assert result.data["written"]


def test_failed_draft_is_collected_without_discarding_written_ones(caller):
    """REQ-L3-PL003-002: one failing draft must not roll back the others."""
    _tenant, workspace, ctx = caller
    need = _make_need(_tenant, workspace, "Dispatch need")
    persisted = _make_requirement(workspace.id, ctx, "Already persisted draft")
    requirement_service = MagicMock()
    requirement_service.create_requirement.side_effect = [
        persisted,
        ValidationError("second draft rejected"),
    ]

    group = AiDerivationToolGroup(requirement_service=requirement_service)
    result = _exec(
        group,
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "write"},
        ctx,
    )

    assert result.success is True
    assert [entry["id"] for entry in result.data["written"]] == [str(persisted.id)]
    assert len(result.data["failed"]) == 1
    assert result.data["failed"][0]["error"] == "second draft rejected"


# ---------------------------------------------------------------------------
# Group dispatch contract
# ---------------------------------------------------------------------------


def test_unknown_tool_name_returns_unknown_tool(caller):
    """A tool name this group does not own is UNKNOWN_TOOL, not INTERNAL."""
    _tenant, _workspace, ctx = caller

    result = _exec(AiDerivationToolGroup(), "ai_derivation.not_a_tool", {}, ctx)

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"


def test_group_dispatch_itself_performs_no_role_check(caller):
    """The RBAC fence for these tools lives in ToolRegistry, not in the group.

    REQ-L2-MC-007: the name-based write gate in
    ``mcp_server.tool_registry._WRITE_TOOL_PREFIXES`` is what turns a
    Viewer's call into ``PERMISSION_DENIED`` (proven end-to-end against the
    real registry in ``test_ai_derivation_tool_group.py``). The group's own
    dispatch must stay a pure contract mapper, so a Viewer context that
    reaches it still gets a normal tool answer instead of a second, divergent
    permission decision — otherwise the two gates could disagree about what
    a Viewer may do.
    """
    tenant, _workspace, _ctx = caller
    viewer = AuthContext(
        user_id=uuid4(),
        tenant_id=tenant.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    service = MagicMock()
    service.derive_requirements_from_need.return_value = {
        "drafts": [],
        "is_mock_fallback": False,
    }

    result = _exec(
        AiDerivationToolGroup(service=service),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(uuid4())},
        viewer,
    )

    assert result.success is True
    assert result.data == {"drafts": [], "is_mock_fallback": False}
    assert service.derive_requirements_from_need.call_count == 1
