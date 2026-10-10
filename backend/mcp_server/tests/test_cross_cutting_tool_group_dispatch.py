"""
Dispatch-level tests for CrossCuttingToolGroup (COMP-MC-006, REQ-L2-MC-004).

Companion to ``test_cross_cutting_tool_group.py`` (which starts from real-DB
fixtures): this module drives every covered tool through the PUBLIC tool-group
interface ``BaseToolGroup.execute_tool`` and locks the contract that the
refactoring work on ``cross_cutting.py`` must preserve byte-for-byte:

* ``workspace.get_context`` — happy path without a workspace, empty-workspace
  counts, unknown/degraded workspace ids, and the cross-tenant read fence.
* ``context.change_impact`` — the no-candidate path, the LLM annotation path
  with a fake provider, the degraded-annotation fallback, and the cross-tenant
  anchor fence.
* ``traceability.create_link`` — the NOT_FOUND endpoint path.
* ``traceability.suggest_links`` — result payload shape, empty findings,
  scope validation, the document-scope translation, the producer-context
  fail-closed gate and the service error mapping.

For LLM paths the provider is faked (``unittest.mock.patch`` on
``llm_adapter.providers.get_provider``) — no network, mirroring the mock-only
default of the test settings.

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from application.traceability_suggest_service import (
    LinkCandidate,
    LinkSuggestion,
    SuggestLinksResult,
)
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
        # Link validation is always-on: an unprovisioned workspace has an
        # empty link-type catalog and rejects every trace link.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


def _ensure_workflow(tenant, workspace, preset: str, item_type: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


def _make_requirement(workspace_id, ctx: AuthContext, title: str):
    from application.requirement_service import RequirementService

    return RequirementService().create_requirement(
        workspace_id=workspace_id, title=title, ctx=ctx
    )


@pytest.fixture
def tenant_workspace_ctx():
    return _make_tenant_workspace_ctx("cc-dispatch")


@pytest.fixture
def auth_ctx(tenant_workspace_ctx):
    _, _, ctx = tenant_workspace_ctx
    return ctx


class _FakeLlmProvider:
    """Minimal provider double returning a canned completion string."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context=None,
        timeout=None,
    ) -> str:
        return self._response


# ---------------------------------------------------------------------------
# workspace.get_context
# ---------------------------------------------------------------------------


def test_get_context_without_workspace_id_returns_base_context(auth_ctx):
    """workspace_id is optional: without it only the caller identity is echoed."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context", params={}, auth_context=auth_ctx, api_key=""
    )

    assert result.success is True
    context = result.data["workspace_context"]
    assert context["tenant_id"] == str(auth_ctx.tenant_id)
    assert context["user_id"] == str(auth_ctx.user_id)
    assert context["active_roles"] == ["editor"]
    assert context["workspace_id"] is None
    assert "requirements" not in context
    assert "preset" not in context


def test_get_context_empty_workspace_returns_zero_counts(tenant_workspace_ctx, auth_ctx):
    """An empty workspace yields zeroed counts, not a partial/error response."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _tenant, workspace, _ctx = tenant_workspace_ctx
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace.id), "depth": "summary"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is True
    context = result.data["workspace_context"]
    assert context["requirements"] == {"active": 0, "outdated": 0, "total": 0}
    assert context["architecture"] == {"active": 0, "outdated": 0, "total": 0}
    assert context["tests"]["pass"] == 0
    assert context["tests"]["fail"] == 0
    assert context["risks"] == {"open": 0, "mitigated": 0, "accepted": 0}
    assert context["workspace_id"] == str(workspace.id)


def test_get_context_unknown_workspace_id_degrades_to_empty_counts(auth_ctx):
    """A syntactically valid but unknown workspace id must not raise."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(uuid4()), "depth": "normal"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is True
    context = result.data["workspace_context"]
    assert context["requirements"]["total"] == 0
    assert context["requirements_list"] == []
    assert context["workspace_id"] is not None


def test_get_context_non_uuid_workspace_id_degrades_gracefully(auth_ctx):
    """An unparseable workspace id never reaches the caller as an exception."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": "not-a-uuid", "depth": "summary"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is True
    context = result.data["workspace_context"]
    assert context["workspace_id"] == "not-a-uuid"
    assert "requirements" not in context


def test_get_context_invalid_depth_message_is_stable(tenant_workspace_ctx, auth_ctx):
    """The validation error message is part of the tool contract."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _tenant, workspace, _ctx = tenant_workspace_ctx
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace.id), "depth": "invalid"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Parameter 'depth' must be one of ['full', 'normal', 'summary']."


def test_get_context_foreign_tenant_workspace_returns_no_data(tenant_workspace_ctx, auth_ctx):
    """Cross-tenant read fence: another tenant's workspace id yields zero counts.

    The queries run under the CALLER's tenant context
    (``tenant_id=auth_context.tenant_id``), so the foreign workspace's rows must
    be invisible — the response succeeds with zeroed counts rather than
    leaking the other tenant's data.
    """
    from application.requirement_service import RequirementService
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _tenant_a, _workspace_a, ctx_a = tenant_workspace_ctx
    _tenant_b, workspace_b, ctx_b = _make_tenant_workspace_ctx("cc-dispatch-b")

    _ensure_workflow(_tenant_b, workspace_b, "standard", "Requirement")
    RequirementService().create_requirement(
        workspace_id=workspace_b.id, title="Tenant B Req", ctx=ctx_b
    )

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_b.id), "depth": "normal"},
        auth_context=ctx_a,
        api_key="",
    )

    assert result.success is True
    context = result.data["workspace_context"]
    assert context["requirements"]["total"] == 0
    assert context["open_requirements_count"] == 0
    assert context["requirements_list"] == []


# ---------------------------------------------------------------------------
# context.change_impact
# ---------------------------------------------------------------------------


@pytest.fixture
def requirement_without_links(tenant_workspace_ctx, auth_ctx):
    """A workspace with one Requirement that has no TraceLinks at all."""
    tenant, workspace, _ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")
    requirement = _make_requirement(workspace.id, auth_ctx, "Lonely Req")
    return requirement.id, "Requirement", workspace.id


@pytest.fixture
def requirement_with_traces_fixture(tenant_workspace_ctx, auth_ctx):
    """A Requirement anchor with one verifying TestCase (VERIFIES TraceLink).

    Returns ``(entity_id, entity_type, workspace_id)`` — the verify link makes
    the TestCase a single change_impact candidate.
    """
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from traceability.types import LinkType

    tenant, workspace, _ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")
    _ensure_workflow(tenant, workspace, "standard", "TestCase")

    requirement = _make_requirement(workspace.id, auth_ctx, "Anchor Req")
    test_case = TestService().create_test_case(
        workspace_id=workspace.id, title="Verifying Test", ctx=auth_ctx
    )
    TraceLinkService().create_trace_link(
        source_id=test_case.artifact_id,
        target_id=requirement.artifact_id,
        link_type=LinkType.VERIFIES.value,
        ctx=auth_ctx,
    )
    return requirement.id, "Requirement", workspace.id


def test_change_impact_without_candidates_returns_empty_list(
    requirement_without_links, auth_ctx
):
    """No TraceLinks and no children -> empty affected list, description echoed."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    entity_id, entity_type, _workspace_id = requirement_without_links
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.change_impact",
        params={
            "entity_id": str(entity_id),
            "entity_type": entity_type,
            "change_description": "Split this requirement in two",
        },
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is True
    assert result.data["affected_entities"] == []
    assert result.data["change_description"] == "Split this requirement in two"


def test_change_impact_applies_llm_annotations(requirement_with_traces_fixture, auth_ctx):
    """A fake provider's JSON annotations flow into the response entries."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    entity_id, entity_type, _workspace_id = requirement_with_traces_fixture
    group = CrossCuttingToolGroup()

    baseline = group.execute_tool(
        "context.change_impact",
        params={"entity_id": str(entity_id), "entity_type": entity_type},
        auth_context=auth_ctx,
        api_key="",
    )
    assert baseline.success is True
    candidate_id = baseline.data["affected_entities"][0]["id"]

    annotations = [
        {"id": candidate_id, "likely_affected": False, "rationale": "renamed only"}
    ]
    with patch(
        "llm_adapter.providers.get_provider",
        return_value=_FakeLlmProvider(json.dumps(annotations)),
    ):
        result = group.execute_tool(
            "context.change_impact",
            params={
                "entity_id": str(entity_id),
                "entity_type": entity_type,
                "change_description": "Rename a field",
            },
            auth_context=auth_ctx,
            api_key="",
        )

    assert result.success is True
    entry = result.data["affected_entities"][0]
    assert entry["id"] == candidate_id
    assert entry["likely_affected"] is False
    assert entry["rationale"] == "renamed only"


def test_change_impact_unconfigured_provider_degrades_to_mock_annotation(
    requirement_with_traces_fixture, auth_ctx
):
    """Provider misconfiguration must not raise: the deterministic mock
    annotation is applied via the fallback branch (never an exception)."""
    from llm_adapter.providers import LlmNotConfiguredError
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    entity_id, entity_type, _workspace_id = requirement_with_traces_fixture
    group = CrossCuttingToolGroup()

    with patch(
        "llm_adapter.providers.get_provider",
        side_effect=LlmNotConfiguredError("no key"),
    ):
        result = group.execute_tool(
            "context.change_impact",
            params={"entity_id": str(entity_id), "entity_type": entity_type},
            auth_context=auth_ctx,
            api_key="",
        )

    assert result.success is True
    entry = result.data["affected_entities"][0]
    assert entry["likely_affected"] is True
    assert entry["rationale"].startswith("Directly linked to the changed entity")


def test_change_impact_invalid_uuid_message_is_stable(auth_ctx):
    """An unparseable entity_id is a VALIDATION_ERROR naming the value."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.change_impact",
        params={"entity_id": "not-a-uuid", "entity_type": "Requirement"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "'not-a-uuid' is not a valid UUID"


def test_change_impact_foreign_tenant_entity_returns_not_found(tenant_workspace_ctx, auth_ctx):
    """Cross-tenant anchor fence: another tenant's entity id is NOT_FOUND."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _tenant_a, _workspace_a, ctx_a = tenant_workspace_ctx
    _tenant_b, workspace_b, ctx_b = _make_tenant_workspace_ctx("cc-dispatch-b")
    _ensure_workflow(_tenant_b, workspace_b, "standard", "Requirement")
    foreign_req = _make_requirement(workspace_b.id, ctx_b, "Tenant B Req")

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.change_impact",
        params={"entity_id": str(foreign_req.id), "entity_type": "Requirement"},
        auth_context=ctx_a,
        api_key="",
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# traceability.create_link
# ---------------------------------------------------------------------------


def test_create_link_unknown_source_returns_not_found(auth_ctx):
    """An unresolvable endpoint is NOT_FOUND, not an INTERNAL_ERROR."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    from traceability.types import LinkType

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "traceability.create_link",
        params={
            "source_id": str(uuid4()),
            "target_id": str(uuid4()),
            "link_type": LinkType.DERIVES_FROM.value,
        },
        auth_context=auth_ctx,
        api_key="x",
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# traceability.suggest_links
# ---------------------------------------------------------------------------


def _producer_ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method="api_key",
        api_key_id=uuid4(),
        actor_type="agent",
    )


def _suggest_result(*, empty: bool = False) -> SuggestLinksResult:
    if empty:
        return SuggestLinksResult(
            tier="standard", provider="mock", degraded=False, total_findings=0
        )
    return SuggestLinksResult(
        tier="standard",
        provider="mock",
        degraded=False,
        total_findings=2,
        eligible_findings=1,
        truncated=False,
        total_findings_available=2,
        suggestions=[
            LinkSuggestion(
                finding_index=0,
                rule_id="TRACE-P1",
                source_artifact_id=str(uuid4()),
                ranked_candidates=[
                    LinkCandidate(
                        artifact_id=str(uuid4()),
                        title="Need candidate",
                        artifact_type="StakeholderNeed",
                        score=3,
                    )
                ],
                rationale="keyword overlap",
            )
        ],
    )


def test_suggest_links_happy_path_returns_result_payload():
    """The dispatch forwards to the service and serialises its result payload."""
    service = MagicMock()
    service.suggest_links.return_value = _suggest_result()
    group = CrossCuttingToolGroup(trace_suggest_service=service)
    workspace_id = uuid4()

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(workspace_id)},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data["tier"] == "standard"
    assert result.data["degraded"] is False
    assert result.data["counts"] == {
        "total_findings": 2,
        "eligible_findings": 1,
        "suggestions": 1,
    }
    suggestion = result.data["suggestions"][0]
    assert suggestion["rule_id"] == "TRACE-P1"
    assert suggestion["ranked_candidates"][0]["artifact_type"] == "StakeholderNeed"
    assert service.suggest_links.call_count == 1
    assert service.suggest_links_async.call_count == 0
    call_args = service.suggest_links.call_args
    assert call_args.args[0] == workspace_id
    assert call_args.kwargs["scopes"] is None


def test_suggest_links_without_eligible_findings_returns_empty_suggestions():
    """An audit run without missing-link findings is a zero-suggestion payload."""
    service = MagicMock()
    service.suggest_links.return_value = _suggest_result(empty=True)
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4())},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data["suggestions"] == []
    assert result.data["counts"] == {
        "total_findings": 0,
        "eligible_findings": 0,
        "suggestions": 0,
    }


def test_suggest_links_scope_document_requires_scope_artifact_id():
    service = MagicMock()
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4()), "scope": "document"},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    service.suggest_links.assert_not_called()


def test_suggest_links_rejects_unknown_scope():
    service = MagicMock()
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4()), "scope": "galaxy"},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    service.suggest_links.assert_not_called()


def test_suggest_links_document_scope_is_forwarded_as_audit_scope():
    """scope=document + scope_artifact_id translates into one AuditScope."""
    from traceability.audit import AuditScope

    service = MagicMock()
    service.suggest_links.return_value = _suggest_result(empty=True)
    group = CrossCuttingToolGroup(trace_suggest_service=service)
    artifact_id = uuid4()

    result = group.execute_tool(
        "traceability.suggest_links",
        params={
            "workspace_id": str(uuid4()),
            "scope": "document",
            "scope_artifact_id": str(artifact_id),
        },
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    call_args = service.suggest_links.call_args
    expected = [AuditScope("document", artifact_id=str(artifact_id))]
    assert call_args.kwargs["scopes"] == expected


def test_suggest_links_missing_workspace_id_returns_validation_error():
    service = MagicMock()
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    service.suggest_links.assert_not_called()


def test_suggest_links_human_bearer_context_fails_closed_with_conflict():
    """ADR-019 7(f): a human trigger maps the producer gate to CONFLICT."""
    from application.base import ProducerContextRequiredError

    service = MagicMock()
    service.suggest_links.side_effect = ProducerContextRequiredError(
        "agent/API-key context required"
    )
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4())},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "CONFLICT"


def test_suggest_links_unknown_workspace_returns_not_found():
    from application.base import NotFoundError

    service = MagicMock()
    service.suggest_links.side_effect = NotFoundError("Workspace not found")
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4())},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_suggest_links_service_error_returns_internal_error():
    from application.traceability_suggest_service import SuggestLinksResponseError

    service = MagicMock()
    service.suggest_links.side_effect = SuggestLinksResponseError("unparseable")
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group.execute_tool(
        "traceability.suggest_links",
        params={"workspace_id": str(uuid4())},
        auth_context=_producer_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
