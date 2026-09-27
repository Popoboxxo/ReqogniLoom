"""Issue #1089 — an AI derivation must produce REVIEWABLE proposals, not drafts.

The defect this file pins: ``workflow.services.initial_state_for`` seeds
``"proposed"`` only when ``ctx.actor_type == "agent"``, which is decided at the
auth layer. An agent calling over MCP got a proposal; a **human** pressing
"KI-Ableitung" in the UI (Bearer token, ``actor_type="user"``) got ``draft``.
The derivation reported success either way, so the AI-authored Requirements
existed but were never presented to anyone for approval.

What is asserted here:

1. the human-triggered write path lands in ``"proposed"`` and carries a
   ``-> "proposed"`` history entry naming the derivation (the ``proposed_by``
   provenance ``resolve_proposed_by`` reads back on the REST transitions route);
2. the write response carries a ``proposal`` block, so a client can tell a
   proposal from a plain draft without a second request;
3. a workspace whose graph has no ``"proposed"`` state is **reported**, never
   silently downgraded — the state is the graph's initial state, ``supported``
   is False and ``reason`` says why;
4. ``require_proposal_support`` turns that reportable gap into a hard failure
   for the callers whose contract *is* the proposal.
"""
from __future__ import annotations

import json

import pytest

from application.ai_derivation_service import AiDerivationService
from application.ai_proposal_service import (
    AI_DERIVATION_LABEL,
    require_proposal_support,
    resolve_proposal_authoring,
)
from application.base import ValidationError
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, StakeholderNeed, Tenant, TraceLink, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_ITEM_TYPE = "Requirement"


def _make_need(ctx, workspace, title, description=""):
    """Create a StakeholderNeed directly via ORM (mirrors the sibling suite's
    helper — the service path publishes domain events this test does not need)."""
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="StakeholderNeed", tenant_id=ctx.tenant_id
        )
        return StakeholderNeed.objects.create(
            artifact=artifact, tenant_id=ctx.tenant_id, title=title, description=description
        )
    finally:
        TenantContext.clear_tenant()


def _provision(workspace_id, tenant_id, preset: str = "extended") -> None:
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace_id,
            preset=preset,
            item_type=_ITEM_TYPE,
            tenant_id=tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="prop-tenant", slug="prop-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="propuser", email="prop@example.com", tenant=tenant
    )


@pytest.fixture
def auth_context(user):
    """A plain Bearer-token editor — ``actor_type="user"``, the shape the UI
    derivation actually runs under. This is the whole point of the fixture: the
    defect only reproduces for a non-agent principal."""
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("editor",),
        auth_method="test",
        tenant_name="prop-tenant",
    )


@pytest.fixture
def workspace(tenant):
    from link_types.workspace_store import provision_workspace_link_types

    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(
            tenant=tenant, name="prop-ws", preset={"name": "extended"}
        )
        # The derivation links every derived Requirement back to its source with
        # a 'derives-from' TraceLink, and link-pair validation is always on.
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def need(auth_context, workspace):
    return _make_need(
        auth_context,
        workspace,
        "The operator needs a dashboard",
        "so they can see throughput",
    )


@pytest.fixture
def proposal_ready(workspace, auth_context):
    """A workspace whose Requirement graph really does contain ``"proposed"``."""
    _provision(workspace.id, auth_context.tenant_id, preset="extended")
    return workspace


@pytest.fixture
def capture_provider(monkeypatch):
    """Install a deterministic LLM provider returning *payload*."""

    class _Provider:
        def __init__(self, payload):
            self._payload = payload
            self.calls: list[dict] = []

        def complete(self, prompt, *, purpose="", context=None, timeout=None):
            # Keyword-only signature mirrors ``LlmCapabilityInterface``;
            # ``_complete()`` always passes purpose/context/timeout.
            self.calls.append({"prompt": prompt, "purpose": purpose, "context": context})
            return self._payload

    def _install(payload: str):
        provider = _Provider(payload)
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: provider
        )
        return provider

    return _install


# ---------------------------------------------------------------------------
# 1. the human-triggered derivation creates a proposal
# ---------------------------------------------------------------------------


def test_human_triggered_derivation_creates_a_proposal_not_a_draft(
    proposal_ready, auth_context, need, capture_provider
):
    """DoD #1: the write path lands in "proposed" for a *user* principal."""
    capture_provider(json.dumps([{"title": "System shall show throughput"}]))
    svc = AiDerivationService()
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        preview = svc.derive_requirements_from_need(auth_context, need.id, n=1)
        authoring = svc.proposal_authoring(
            auth_context, item_type=_ITEM_TYPE, workspace_id=need.artifact.workspace_id
        )
        result = svc._write_derived_entity(
            ctx=auth_context,
            workspace_id=need.artifact.workspace_id,
            item_type=_ITEM_TYPE,
            create_fn=lambda: RequirementService().create_requirement(
                workspace_id=need.artifact.workspace_id,
                title=preview["drafts"][0]["title"],
                ctx=authoring.create_context,
            ),
            source_entity_id=need.artifact_id,
            source_item_type="StakeholderNeed",
            link_type="derives-from",
            new_entity_is_link_source=True,
        )
        # Read back inside the tenant context: `state_reader` and the tenant-scoped
        # `TraceLink` manager both require it, exactly as the service does.
        state = _current_state(result["id"], _ITEM_TYPE)
        link_exists = TraceLink.objects.filter(
            id=result["trace_link_id"]
        ).exists()
    finally:
        TenantContext.clear_tenant()

    assert preview["drafts"], "the fake provider must have produced a draft"

    assert state == "proposed", (
        "an AI derivation triggered by a human must land in 'proposed', not "
        "'draft' — otherwise nobody is ever shown the proposal (#1089)"
    )
    assert result["status"] == "proposed"
    assert result["proposal"]["is_proposal"] is True
    assert result["proposal"]["supported"] is True
    assert result["proposal"]["reason"] == ""
    # The origin marker: the proposal's `proposed_by` provenance, which the REST
    # `transitions/` route surfaces as `proposed_by` and the artefact header
    # renders as "Vorschlag von ...".
    assert result["proposal"]["proposed_by"] == AI_DERIVATION_LABEL
    assert link_exists


def test_proposal_carries_a_proposal_history_entry(
    proposal_ready, auth_context, need
):
    """The `from_state="" -> "proposed"` entry is the only provenance the
    artefact has — without it `resolve_proposed_by` answers None and the UI has
    no "who proposed this" to show."""
    svc = AiDerivationService()
    workspace_id = need.artifact.workspace_id
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        authoring = svc.proposal_authoring(
            auth_context, item_type=_ITEM_TYPE, workspace_id=workspace_id
        )
        result = svc._write_derived_entity(
            ctx=auth_context,
            workspace_id=workspace_id,
            item_type=_ITEM_TYPE,
            create_fn=lambda: RequirementService().create_requirement(
                workspace_id=workspace_id,
                title="Proposed Req",
                ctx=authoring.create_context,
            ),
            source_entity_id=need.artifact_id,
            source_item_type="StakeholderNeed",
            link_type="derives-from",
            new_entity_is_link_source=True,
        )
        actors = _proposal_history_actors(result["id"], _ITEM_TYPE)
    finally:
        TenantContext.clear_tenant()

    assert AI_DERIVATION_LABEL in actors, (
        "the proposal history entry must name the derivation, not be blank"
    )


# ---------------------------------------------------------------------------
# 2. a graph without a proposal state is REPORTED, not downgraded silently
# ---------------------------------------------------------------------------


def test_minimal_preset_workspace_reports_instead_of_downgrading(
    workspace, auth_context, need
):
    """DoD #4: a value that cannot enter `proposed` is reported.

    The ``minimal`` preset is in ``SCHEMAS_WITHOUT_PROPOSED``, so the graph
    genuinely cannot express a proposal. The write must still succeed (the
    derivation did happen) but the response must say the artefact is NOT a
    reviewable proposal and why.
    """
    _provision(workspace.id, auth_context.tenant_id, preset="minimal")
    svc = AiDerivationService()
    workspace_id = need.artifact.workspace_id
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        authoring = svc.proposal_authoring(
            auth_context, item_type=_ITEM_TYPE, workspace_id=workspace_id
        )
        result = svc._write_derived_entity(
            ctx=auth_context,
            workspace_id=workspace_id,
            item_type=_ITEM_TYPE,
            create_fn=lambda: RequirementService().create_requirement(
                workspace_id=workspace_id, title="Minimal Req", ctx=auth_context
            ),
            source_entity_id=need.artifact_id,
            source_item_type="StakeholderNeed",
            link_type="derives-from",
            new_entity_is_link_source=True,
        )
    finally:
        TenantContext.clear_tenant()

    assert authoring.supported is False
    assert "proposed" in authoring.reason
    assert result["proposal"]["is_proposal"] is False
    assert result["proposal"]["supported"] is False
    # The actionable part: the caller learns WHICH state it got and why.
    assert result["proposal"]["state"] == "draft"
    assert "NOT a reviewable proposal" in result["proposal"]["reason"]


def test_resolve_proposal_authoring_marks_a_human_derivation_as_agent_authored(
    proposal_ready, auth_context
):
    """The rewrite is about authorship, not identity: the caller's identity,
    tenant, roles and workspace survive verbatim."""
    authoring = resolve_proposal_authoring(
        auth_context, item_type=_ITEM_TYPE, workspace_id=proposal_ready.id
    )
    ctx = authoring.create_context
    assert ctx.actor_type == "agent"
    assert ctx.agent_label == AI_DERIVATION_LABEL
    assert ctx.user_id == auth_context.user_id
    assert ctx.tenant_id == auth_context.tenant_id
    assert ctx.active_roles == auth_context.active_roles
    assert ctx.auth_method == auth_context.auth_method


def test_unsupported_graph_keeps_the_honest_actor_type(
    workspace, auth_context
):
    """No proposal state -> the audit log must keep recording the human."""
    _provision(workspace.id, auth_context.tenant_id, preset="minimal")
    authoring = resolve_proposal_authoring(
        auth_context, item_type=_ITEM_TYPE, workspace_id=workspace.id
    )
    assert authoring.supported is False
    assert authoring.create_context.actor_type == "user"


def test_require_proposal_support_raises_on_a_graph_without_proposals(
    workspace, auth_context
):
    """The REST persist path cannot accept the downgrade: its whole contract is
    "create a reviewable proposal", so a 4xx is the honest answer."""
    _provision(workspace.id, auth_context.tenant_id, preset="minimal")
    authoring = resolve_proposal_authoring(
        auth_context, item_type=_ITEM_TYPE, workspace_id=workspace.id
    )
    with pytest.raises(ValidationError) as exc:
        require_proposal_support(authoring, item_type=_ITEM_TYPE)
    assert "reviewable AI proposals" in str(exc.value)


def test_require_proposal_support_is_a_no_op_when_supported(
    proposal_ready, auth_context
):
    authoring = resolve_proposal_authoring(
        auth_context, item_type=_ITEM_TYPE, workspace_id=proposal_ready.id
    )
    assert require_proposal_support(authoring, item_type=_ITEM_TYPE) is authoring


def test_definition_less_workspace_is_reported_not_raised(workspace, auth_context):
    """No workflow at all is also unsupportable — and also only reported."""
    authoring = resolve_proposal_authoring(
        auth_context, item_type=_ITEM_TYPE, workspace_id=workspace.id
    )
    assert authoring.supported is False
    assert "No workflow is configured" in authoring.reason
    assert authoring.state == "draft"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _current_state(item_id: str, item_type: str) -> str | None:
    from workflow import state_reader

    import uuid as _uuid

    return state_reader.current_state(item_type, _uuid.UUID(item_id))


def _proposal_history_actors(item_id: str, item_type: str) -> list[str]:
    from workflow.models import WorkflowHistoryEntry, WorkflowItemState

    import uuid as _uuid

    state = WorkflowItemState.objects.filter(
        item_id=_uuid.UUID(item_id), item_type=item_type
    ).first()
    if state is None:
        return []
    return list(
        WorkflowHistoryEntry.objects.filter(
            item_state=state, to_state="proposed"
        ).values_list("transitioned_by", flat=True)
    )
