"""CR-08 — MCP surface: a lost transition race answers a *caller* error.

DoD gap: the ``expected_version`` threading and the ``OptimisticLockError``
mapping were code changes in ``mcp_server/tools/review.py`` (two handlers) and
``mcp_server/tools/goals.py`` (one handler) with no test at all. That is the
worst place for an untested mapping: the engine raises ``WorkflowConflictError``,
``WorkflowFacade`` remaps it to ``OptimisticLockError``, and each tool group has
to catch it itself. A missing ``except`` clause does not crash — it falls
through to the generic handler and the caller gets a *validation* error, so the
race looks like bad input instead of "retry after re-reading".

Staleness setup, and why it is shaped this way: both review handlers resolve
the target transition from ``get_available_transitions`` BEFORE calling the
facade, so an item parked in a state with no outgoing approval edge would be
rejected by that earlier check and the conflict would never be reached. The
stale revision is therefore created by reading the version in a state that HAS
the needed edge, then performing one real transition into the target state — the
revision is now genuinely stale and the tool's own availability check still
passes. Nothing is stubbed and no version is written behind the engine's back.

What is pinned per tool:

* a stale ``expected_version`` produces ``success=False`` with a message naming
  the version conflict — never ``success=True``, never a leak of internals;
* the *current* ``expected_version`` still succeeds (the guard is a compare,
  not a blanket rejection);
* omitting ``expected_version`` still succeeds (unchanged back-compat).

The REST half of the same mapping is pinned in
``rest_api/tests/test_transition_expected_version_cr08.py``.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from mcp_server.tools.goals import GoalToolGroup
from mcp_server.tools.review import ReviewToolGroup
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow, transition

pytestmark = pytest.mark.django_db

# Fixture-only key: no real credential, just a shape the auth stub accepts. The
# ``placeholder`` marker is the W1 secret scanner's documented allowlist token
# (``_SAFE_PATTERNS``) — the scanner pattern still matches, the allowlist is
# what clears it, exactly as in
# rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py.
_API_KEY = "reqlo_placeholder_testkey_cr08"


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="cr08-mcp-tenant", slug="cr08-mcp-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="cr08-mcp-ws")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant, workspace):
    return User.objects.create(
        username="cr08mcpuser",
        email="cr08mcp@example.com",
        tenant=tenant,
        is_active=True,
    )


@pytest.fixture
def auth_context(user, workspace):
    """Approver+admin: crosses the real "In Review -> Approved" approval gate.

    The conflict is raised BEFORE the graph is consulted, so the gate is
    irrelevant for the stale case — but the *positive* control on the same
    fixture does cross it, which is exactly why the two must be asserted
    separately: a suite that only checked the conflict would pass even if the
    happy path had broken.
    """
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("approver", "admin", "editor"),
        auth_method="test",
        api_key_id=None,
        tenant_name="cr08-mcp-tenant",
        workspace_id=workspace.id,
    )


@pytest.fixture
def api_key():
    return _API_KEY


def _workflow_version(tenant_id, item_id, item_type, workspace_id) -> int:
    TenantContext.set_tenant(tenant_id)
    try:
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type=item_type, workspace_id=workspace_id
        ).version
    finally:
        TenantContext.clear_tenant()


def _engine_transition(tenant_id, ctx, item_id, item_type, workspace_id, target, reason):
    TenantContext.set_tenant(tenant_id)
    try:
        transition(
            item_id=item_id,
            target_state=target,
            change_reason=reason,
            ctx=ctx,
            item_type=item_type,
            workspace_id=workspace_id,
        )
    finally:
        TenantContext.clear_tenant()


def _assert_is_a_retryable_conflict(result) -> None:
    """The one contract every handler must honour, asserted once.

    Deliberately does NOT pin the concrete error_code string: the tools report
    conflicts under the generic ``VALIDATION_ERROR`` code with a
    "Version conflict" message, and hard-coding the code here would make a
    future, better code (a dedicated CONFLICT code) look like a regression.
    What must not change is: not a success, and a message that names the
    conflict so the caller can tell "retry" from "your request is wrong".
    """
    assert result.success is False, result.data
    assert "Version conflict" in (result.message or ""), result.message


@pytest.fixture
def adr_in_draft(auth_context, workspace):
    """A real Adr in "Draft", with its definition already provisioned.

    Definition FIRST: an Adr created before its ``WorkflowItemState`` exists
    has no state row and every later transition on it fails with "No
    WorkflowItemState found" — which would mask the conflict under test.
    """
    from application.adr_service import AdrService

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="adr_default",
            item_type="Adr",
            tenant_id=auth_context.tenant_id,
        )
        return AdrService().create_adr(
            workspace_id=workspace.id,
            title="ADR for the CR-08 MCP mapping",
            description="submitted for review",
            ctx=auth_context,
            context="ctx",
            consequences="consequences",
        )
    finally:
        TenantContext.clear_tenant()


def _stale_adr_revision(auth_context, workspace, adr_in_draft) -> int:
    """Version read in "Draft", then moved to "In Review" — now genuinely stale.

    ``adr_default`` declares ``In Review -> [Approved, Rejected, Draft]``, so
    "In Review" is exactly the state the review handlers need in order to
    resolve a target at all.
    """
    stale = _workflow_version(
        auth_context.tenant_id, adr_in_draft.id, "Adr", workspace.id
    )
    _engine_transition(
        auth_context.tenant_id,
        auth_context,
        adr_in_draft.id,
        "Adr",
        workspace.id,
        "In Review",
        "moved on by another session",
    )
    return stale


# ---------------------------------------------------------------------------
# review.approve
# ---------------------------------------------------------------------------


def test_review_approve_stale_expected_version_is_a_retryable_conflict(
    auth_context, api_key, workspace, adr_in_draft
):
    stale = _stale_adr_revision(auth_context, workspace, adr_in_draft)

    result = ReviewToolGroup().execute_tool(
        "review.approve",
        {
            "item_id": str(adr_in_draft.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "change_reason": "approve please",
            "expected_version": stale,
        },
        auth_context,
        api_key,
    )

    _assert_is_a_retryable_conflict(result)


def test_review_approve_with_the_current_expected_version_succeeds(
    auth_context, api_key, workspace, adr_in_draft
):
    _stale_adr_revision(auth_context, workspace, adr_in_draft)
    current = _workflow_version(
        auth_context.tenant_id, adr_in_draft.id, "Adr", workspace.id
    )

    result = ReviewToolGroup().execute_tool(
        "review.approve",
        {
            "item_id": str(adr_in_draft.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "change_reason": "approve please",
            "expected_version": current,
        },
        auth_context,
        api_key,
    )

    assert result.success is True, result.message
    assert result.data["new_state"] == "Approved"


def test_review_approve_without_expected_version_still_succeeds(
    auth_context, api_key, workspace, adr_in_draft
):
    """Back-compat: an MCP client that pins no revision is not newly rejected."""
    _stale_adr_revision(auth_context, workspace, adr_in_draft)

    result = ReviewToolGroup().execute_tool(
        "review.approve",
        {
            "item_id": str(adr_in_draft.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "change_reason": "approve please",
        },
        auth_context,
        api_key,
    )

    assert result.success is True, result.message
    assert result.data["new_state"] == "Approved"


# ---------------------------------------------------------------------------
# review.request_changes (the second handler in review.py)
# ---------------------------------------------------------------------------


def test_review_request_changes_stale_expected_version_is_a_retryable_conflict(
    auth_context, api_key, workspace, adr_in_draft
):
    """The ``_handle_request_changes`` twin — a separate ``except`` chain, so a
    mapping added to one handler proves nothing about the other."""
    stale = _stale_adr_revision(auth_context, workspace, adr_in_draft)

    result = ReviewToolGroup().execute_tool(
        "review.request_changes",
        {
            "item_id": str(adr_in_draft.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "reason": "please revise",
            "expected_version": stale,
        },
        auth_context,
        api_key,
    )

    _assert_is_a_retryable_conflict(result)


def test_review_request_changes_with_the_current_expected_version_succeeds(
    auth_context, api_key, workspace, adr_in_draft
):
    _stale_adr_revision(auth_context, workspace, adr_in_draft)
    current = _workflow_version(
        auth_context.tenant_id, adr_in_draft.id, "Adr", workspace.id
    )

    result = ReviewToolGroup().execute_tool(
        "review.request_changes",
        {
            "item_id": str(adr_in_draft.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "reason": "please revise",
            "expected_version": current,
        },
        auth_context,
        api_key,
    )

    assert result.success is True, result.message
    assert result.data["new_state"] == "Draft"


# ---------------------------------------------------------------------------
# goal.transition (the third site, in goals.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def goal_in_draft(auth_context, workspace):
    """A real Goal version in "Entwurf", definition provisioned first."""
    from application.goal_service import GoalService

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="goal_default",
            item_type="Goal",
            tenant_id=auth_context.tenant_id,
        )
        return GoalService().create_version(
            workspace_id=workspace.id,
            title="Goal for the CR-08 MCP mapping",
            description="a goal to transition",
            lineage_id=None,
            ctx=auth_context,
        )
    finally:
        TenantContext.clear_tenant()


def test_goal_transition_stale_expected_version_is_a_retryable_conflict(
    auth_context, api_key, workspace, goal_in_draft
):
    """``goal.transition`` has its own handler and its own except chain."""
    goal_id = goal_in_draft["id"]
    stale = _workflow_version(auth_context.tenant_id, goal_id, "Goal", workspace.id)
    # goal_default declares Entwurf -> [Freigegeben, Archiviert] and
    # Freigegeben -> [Archiviert, Entwurf]: one real transition leaves the goal
    # in a state with a valid outgoing edge AND bumps the revision.
    _engine_transition(
        auth_context.tenant_id,
        auth_context,
        goal_id,
        "Goal",
        workspace.id,
        "Freigegeben",
        "first session wins",
    )

    result = GoalToolGroup().execute_tool(
        "goal.transition",
        {
            "goal_id": str(goal_id),
            "workspace_id": str(workspace.id),
            "target_state": "Archiviert",
            "change_reason": "second session is stale",
            "expected_version": stale,
        },
        auth_context,
        api_key,
    )

    _assert_is_a_retryable_conflict(result)


def test_goal_transition_with_the_current_expected_version_succeeds(
    auth_context, api_key, workspace, goal_in_draft
):
    goal_id = goal_in_draft["id"]
    _workflow_version(auth_context.tenant_id, goal_id, "Goal", workspace.id)
    _engine_transition(
        auth_context.tenant_id,
        auth_context,
        goal_id,
        "Goal",
        workspace.id,
        "Freigegeben",
        "first session wins",
    )
    current = _workflow_version(auth_context.tenant_id, goal_id, "Goal", workspace.id)

    result = GoalToolGroup().execute_tool(
        "goal.transition",
        {
            "goal_id": str(goal_id),
            "workspace_id": str(workspace.id),
            "target_state": "Archiviert",
            "change_reason": "second session is current",
            "expected_version": current,
        },
        auth_context,
        api_key,
    )

    assert result.success is True, result.message
