"""Issue #2023 — Goal version creation must inherit an omitted description.

``create_version`` used to default ``description=""`` and write that literal,
so appending a version without a description silently cleared the lineage's
text. ``GoalService.update`` already inherited via ``None``; direct service
callers (and the MCP ``goal.create_version`` tool) did not.
"""
from __future__ import annotations

import uuid

import pytest

from application.goal_service import GoalService
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace


@pytest.fixture
def goal_env():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant, goals_enabled=True)
        ctx = editor_ctx(tenant, workspace)
        yield tenant, workspace, ctx


@pytest.mark.django_db
def test_create_version_inherits_description_when_omitted(goal_env):
    _tenant, workspace, ctx = goal_env
    svc = GoalService()
    first = svc.create_version(
        workspace_id=workspace.id,
        title="Reduce onboarding",
        description="From 5 days to 2 days.",
        lineage_id=None,
        ctx=ctx,
    )

    second = svc.create_version(
        workspace_id=workspace.id,
        title="Reduce onboarding (revised)",
        lineage_id=uuid.UUID(first["lineage_id"]),
        ctx=ctx,
    )

    assert second["description"] == "From 5 days to 2 days."
    assert svc.get(uuid.UUID(second["id"]), ctx).description == (
        "From 5 days to 2 days."
    )


@pytest.mark.django_db
def test_create_version_keeps_explicit_empty_description(goal_env):
    _tenant, workspace, ctx = goal_env
    svc = GoalService()
    first = svc.create_version(
        workspace_id=workspace.id,
        title="Goal",
        description="Original text.",
        lineage_id=None,
        ctx=ctx,
    )

    cleared = svc.create_version(
        workspace_id=workspace.id,
        title="Goal",
        description="",
        lineage_id=uuid.UUID(first["lineage_id"]),
        ctx=ctx,
    )
    assert cleared["description"] == ""


@pytest.mark.django_db
def test_first_version_without_description_defaults_to_empty(goal_env):
    _tenant, workspace, ctx = goal_env
    created = GoalService().create_version(
        workspace_id=workspace.id,
        title="Goal without description",
        lineage_id=None,
        ctx=ctx,
    )
    assert created["description"] == ""
