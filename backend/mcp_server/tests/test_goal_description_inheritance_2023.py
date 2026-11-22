"""Issue #2023 — MCP ``goal.create_version`` must forward an omitted description.

The handler used to pass ``params.get("description", "")``, which turned an
omitted argument into an explicit empty string and defeated the service's
description inheritance.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.goal_service import GoalService
from mcp_server.tools.goals import GoalToolGroup
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace


@pytest.mark.django_db
def test_goal_create_version_mcp_inherits_omitted_description():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant, goals_enabled=True)
        ctx = editor_ctx(tenant, workspace)
        first = GoalService().create_version(
            workspace_id=workspace.id,
            title="Original",
            description="Inherited text.",
            lineage_id=None,
            ctx=ctx,
        )

        with patch(
            "mcp_server.tools.goals.validate_artifact_write", return_value=None
        ):
            result = GoalToolGroup()._handle_create_version(
                params={
                    "workspace_id": str(workspace.id),
                    "lineage_id": first["lineage_id"],
                    "title": "Revised",
                },
                auth_context=ctx,
                api_key="reqlo_test",
            )

        assert result.success, result.message
        assert result.data["description"] == "Inherited text."


@pytest.mark.django_db
def test_goal_create_version_mcp_keeps_explicit_empty_description():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant, goals_enabled=True)
        ctx = editor_ctx(tenant, workspace)
        first = GoalService().create_version(
            workspace_id=workspace.id,
            title="Original",
            description="Inherited text.",
            lineage_id=None,
            ctx=ctx,
        )

        with patch(
            "mcp_server.tools.goals.validate_artifact_write", return_value=None
        ):
            result = GoalToolGroup()._handle_create_version(
                params={
                    "workspace_id": str(workspace.id),
                    "lineage_id": first["lineage_id"],
                    "title": "Cleared",
                    "description": "",
                },
                auth_context=ctx,
                api_key="reqlo_test",
            )

        assert result.success, result.message
        assert result.data["description"] == ""
