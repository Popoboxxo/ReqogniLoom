"""Tests for rebuild_workspace_graph (Issue #377, Task 8)."""
from __future__ import annotations

import pytest

from context_graph.tests.conftest import (
    seed_context_settings,
    seed_glossary_term,
    seed_requirement,
    seed_workspace,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _clear():
    from persistence.tenancy import TenantContext

    TenantContext.clear_tenant()


def test_rebuild_without_settings_row_errors_without_creating_one():
    from context_graph.admin_ops import rebuild_workspace_graph
    from context_graph.models import WorkspaceContextSettings

    tenant, workspace, ctx = seed_workspace("cg-rebuild-nosettings")
    _clear()

    result = rebuild_workspace_graph(workspace.id)

    assert result.error != ""
    assert not WorkspaceContextSettings.unscoped.filter(workspace_id=workspace.id).exists()


def test_rebuild_with_empty_generators_produces_zero_edges():
    from context_graph.admin_ops import rebuild_workspace_graph
    from context_graph.models import ContextEdge

    tenant, workspace, ctx = seed_workspace("cg-rebuild-empty")
    seed_context_settings(tenant, workspace, enabled_generators=[])
    seed_requirement(tenant, workspace, title="Req", uid="REQ-A")
    _clear()

    result = rebuild_workspace_graph(workspace.id)

    assert result.error == ""
    assert result.edge_count == 0
    assert not ContextEdge.unscoped.filter(source__workspace_id=workspace.id).exists()


def test_rebuild_produces_correct_edge_count_and_is_idempotent():
    from context_graph.admin_ops import rebuild_workspace_graph

    tenant, workspace, ctx = seed_workspace("cg-rebuild-count")
    settings_row = seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
    seed_glossary_term(tenant, workspace, term="Autopilot")
    seed_glossary_term(tenant, workspace, term="Sensor")
    # 3 requirements share "Autopilot" (3 pairs: AB, AC, BC); one more shares
    # "Sensor" with none of them.
    seed_requirement(tenant, workspace, title="Autopilot A", uid="REQ-A")
    seed_requirement(tenant, workspace, title="Autopilot B", uid="REQ-B")
    seed_requirement(tenant, workspace, title="Autopilot C", uid="REQ-C")
    seed_requirement(tenant, workspace, title="Sensor only", uid="REQ-D")
    _clear()

    first = rebuild_workspace_graph(workspace.id)
    assert first.error == ""
    assert first.artifacts_processed == 4
    assert first.edge_count == 3, "expected exactly 3 shares-term pairs (AB, AC, BC)"

    second = rebuild_workspace_graph(workspace.id)
    assert second.edge_count == first.edge_count, "rebuild must be idempotent"

    settings_row.refresh_from_db()
    assert settings_row.edge_count == 3
    assert settings_row.node_count == 4
    assert settings_row.last_error == ""


def test_unknown_workspace_returns_error():
    import uuid as uuid_mod

    from context_graph.admin_ops import rebuild_workspace_graph

    result = rebuild_workspace_graph(uuid_mod.uuid4())
    assert "not found" in result.error
