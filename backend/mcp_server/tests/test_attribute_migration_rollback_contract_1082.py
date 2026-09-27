"""The MCP attribute tools must report a no-op reset as CONFLICT (issue #1082).

``attribute_definition.reset`` goes through the same
``WorkspaceAttributeDefinitionStore.reset`` as the REST endpoint, so it hits the
same refusal — ``AttributeDefinitionConflictError``, a plain ``ValueError``. With
no handler the base dispatcher's blanket ``except Exception`` turned it into
INTERNAL_ERROR: the tool group *crashed* on a condition that has a perfectly
good error code.

Also pinned here: the ``attribute_migration.rollback`` description has to state
the rollback contract (#1082 made it partial-able), because the description is
the only output contract this tool surface publishes — the JSON schemas carry
``inputSchema`` only, no ``outputSchema``.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from attribute_definitions.global_definition_store import AttributeDefinitionNotFound
from attribute_definitions.schema import AttributeDefinitionConflictError
from mcp_server.tools.attribute_definition import AttributeDefinitionToolGroup
from mcp_server.tools.attribute_migration import AttributeMigrationToolGroup

pytestmark = pytest.mark.django_db

VALID_API_KEY = "reqlo_test_key"


def _descriptions(group) -> dict[str, str]:
    return {tool["name"]: tool["description"] for tool in group.get_tool_schemas()}


def _input_schemas(group) -> dict[str, dict]:
    return {tool["name"]: tool["inputSchema"] for tool in group.get_tool_schemas()}


def _reset(params: dict) -> object:
    return AttributeDefinitionToolGroup().execute_tool(
        tool_name="attribute_definition.reset",
        params=params,
        auth_context=MagicMock(),
        api_key=VALID_API_KEY,
    )


def test_reset_maps_the_conflict_to_a_conflict_error() -> None:
    """#1082: CONFLICT, not INTERNAL_ERROR and not a crash."""
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.reset_workspace.side_effect = (
            AttributeDefinitionConflictError(["nothing to reset"])
        )
        result = _reset({"item_type": "Risk", "workspace_id": str(uuid.uuid4())})

    assert result.success is False
    assert result.error_code == "CONFLICT"
    assert "nothing to reset" in result.message


def test_reset_still_maps_a_missing_definition_to_not_found() -> None:
    """The conflict handler must not swallow the NOT_FOUND branch."""
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.reset_workspace.side_effect = AttributeDefinitionNotFound(
            "no definition resolved"
        )
        result = _reset({"item_type": "Goal", "workspace_id": str(uuid.uuid4())})

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_the_reset_tool_input_contract_is_unchanged() -> None:
    """The option that carries the reset semantics lives in the plan doc."""
    schema = _input_schemas(AttributeDefinitionToolGroup())[
        "attribute_definition.reset"
    ]

    assert schema["required"] == ["item_type", "workspace_id"]


def test_rollback_description_states_the_partial_contract() -> None:
    """#1082: the split counters, the outstanding list, and the new status."""
    description = _descriptions(AttributeMigrationToolGroup())[
        "attribute_migration.rollback"
    ]

    assert "partially_rolled_back" in description
    assert "not_reverted" in description
    # The two split counters plus the total they add up to.
    for field in ("restored_artifacts", "restored_definitions", "restored"):
        assert field in description, field


def test_rollback_declares_no_status_enum_that_would_exclude_the_new_value() -> None:
    """A closed enum on the output would be a contract break; there is none."""
    schema = _input_schemas(AttributeMigrationToolGroup())[
        "attribute_migration.rollback"
    ]

    assert set(schema["properties"]) == {"run_id"}


@pytest.mark.parametrize(
    "tool_name",
    ["attribute_migration.dry_run", "attribute_migration.apply"],
)
def test_dry_run_and_apply_mention_target_scope(tool_name: str) -> None:
    """#1083: the reach disclosure is useless if the tool never names it."""
    description = _descriptions(AttributeMigrationToolGroup())[tool_name]

    assert "target_scope" in description
