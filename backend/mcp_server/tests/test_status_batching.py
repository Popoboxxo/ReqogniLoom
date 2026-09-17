"""Regression guard: MCP list handlers batch ``status`` resolution (no N+1).

``architecture.query`` and ``icd.query`` resolve each row's wire ``status``
through the workflow engine. Both used to call ``resolve_engine_status`` once
per element inside their row helper, i.e. one engine lookup per row. They now
compute a single ``resolve_status_map`` for the whole page and hand it into the
helper.

These tests drive the real ``ToolRegistry.dispatch_request`` stack (API-key auth
-> RBAC -> workspace gate -> tool group -> application/icd service -> DB) and spy
on ``workflow.state_reader.current_states`` -- the same batching idiom pinned for
REST in ``rest_api/tests/test_status_from_engine.py``. They assert *batch*
semantics (one call), not a fragile raw query count.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

from mcp_server.tool_registry import ToolRegistry

pytestmark = pytest.mark.django_db


def _dispatch(tool_name: str, params: Dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create_element(
    workspace_id: str,
    api_key: str,
    title: str,
    parent_id: str | None = None,
) -> str:
    params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "title": title,
        "element_type": "component",
    }
    if parent_id is not None:
        params["parent_id"] = parent_id
    result = _dispatch("architecture.create", params, api_key)
    assert result.success is True, result.message
    return result.data["architecture_element"]["id"]


def _current_states_spy():
    """Patch ``workflow.state_reader.current_states`` with a call-counting spy."""
    from workflow import state_reader

    return patch(
        "workflow.state_reader.current_states",
        wraps=state_reader.current_states,
    )


def test_architecture_query_resolves_status_in_one_engine_call(
    e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    # I5 allows exactly one root per workspace, so build a chain.
    root = _create_element(workspace_id, e2e_api_key_member, "root")
    child = _create_element(workspace_id, e2e_api_key_member, "child", parent_id=root)
    _create_element(workspace_id, e2e_api_key_member, "grandchild", parent_id=child)

    with _current_states_spy() as spy:
        result = _dispatch(
            "architecture.query",
            {"workspace_id": workspace_id},
            e2e_api_key_member,
        )

    assert result.success is True, result.message
    assert len(result.data["architecture_elements"]) >= 3
    assert spy.call_count == 1, "status resolution must batch, not N+1"


def test_icd_query_resolves_status_in_one_engine_call(
    e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    source = _create_element(workspace_id, e2e_api_key_member, "icd-source")
    # Every ICD creates a 'decomposes' TraceLink between its endpoints and the
    # uq_tracelink_edge constraint forbids duplicate (source, target, type)
    # edges — so each ICD needs its own target element.
    targets = [
        _create_element(
            workspace_id, e2e_api_key_member, f"icd-target-{index}", parent_id=source
        )
        for index in range(3)
    ]
    for index, target in enumerate(targets):
        created = _dispatch(
            "icd.create",
            {
                "workspace_id": workspace_id,
                "name": f"batch-icd-{index}",
                "source_element_id": source,
                "target_element_id": target,
            },
            e2e_api_key_member,
        )
        assert created.success is True, created.message

    with _current_states_spy() as spy:
        result = _dispatch(
            "icd.query", {"workspace_id": workspace_id}, e2e_api_key_member
        )

    assert result.success is True, result.message
    assert len(result.data["icds"]) >= 3
    assert spy.call_count == 1, "status resolution must batch, not N+1"
