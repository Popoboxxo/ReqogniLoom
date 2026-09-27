"""ADR-005 / #1086 — ``Requirement.level`` and ``parent_id`` over MCP.

MCP is the transport where the wave had the most room to lie. The create path
accepted a ``level`` in its input schema and forwarded it straight into
``create_requirement(level=...)``; the update path already did *not* forward it
— an asymmetry the ADR turns into consistency. Neither half said so out loud, and
"not forwarded" is still a silent accept, which is the failure class this wave
closes.

The property under test: an agent gets an **error**, not a stored value it
cannot influence, and the field it *is* allowed to send (``parent_id``) is
actually applied.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod

from mcp_server.tools.requirements import RequirementsToolGroup

#: ``list_tools()`` resolves the workspace preset and ``_requirement_to_dict``
#: resolves the workflow state, so even the pure schema assertions touch the DB.
pytestmark = pytest.mark.django_db

EDITOR_CTX = AuthContext(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
)
VALID_API_KEY = "reqlo_testkey1234"
WORKSPACE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000010")


def _mock_requirement(id_val=None, level=1):
    req = MagicMock()
    req.id = id_val or uuid.UUID("00000000-0000-0000-0000-000000000020")
    req.artifact_id = uuid.UUID("00000000-0000-0000-0000-000000000021")
    req.title = "Test Req"
    req.description = ""
    req.category = ""
    req.status = "draft"
    req.version = 1
    req.level = level
    req.artifact = MagicMock()
    req.artifact.workspace_id = WORKSPACE_UUID
    return req


def _group():
    svc = MagicMock()
    return RequirementsToolGroup(service=svc), svc


def _tools(group) -> dict:
    return {tool["name"]: tool for tool in group.get_tool_schemas()}


# ---------------------------------------------------------------------------
# The advertised schema must be honest
# ---------------------------------------------------------------------------


class TestAdvertisedSchema:
    def test_create_does_not_advertise_level_as_settable(self):
        group, _ = _group()
        level = _tools(group)["requirement.create"]["inputSchema"]["properties"]["level"]
        assert "enum" not in level, (
            "an enum invites the client to pick a value; ADR-005 removed the "
            "choice"
        )
        assert "READ-ONLY" in level["description"]
        assert "derived" in level["description"].lower()

    def test_update_advertises_level_as_read_only(self):
        group, _ = _group()
        data = _tools(group)["requirement.update"]["inputSchema"]["properties"]["data"]
        assert "READ-ONLY" in data["properties"]["level"]["description"]

    def test_update_advertises_parent_id(self):
        """The field the client *is* allowed to send must be in the schema —
        otherwise the honest ``level`` contract has no usable replacement."""
        group, _ = _group()
        data = _tools(group)["requirement.update"]["inputSchema"]["properties"]["data"]
        assert "parent_id" in data["properties"]

    def test_update_tool_description_names_both(self):
        group, _ = _group()
        description = _tools(group)["requirement.update"]["description"]
        assert "level" in description
        assert "parent_id" in description


# ---------------------------------------------------------------------------
# level is refused, not silently dropped
# ---------------------------------------------------------------------------


@patch("mcp_server.tools.requirements.write_mcp_audit")
class TestLevelIsRefused:
    def test_create_with_a_level_is_a_validation_error(self, mock_audit):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="requirement.create",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "title": "Req",
                "level": 3,
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "derived" in result.message.lower()
        # Nothing was written — the service is not even reached.
        svc.create_requirement.assert_not_called()
        mock_audit.assert_not_called()

    def test_create_without_a_level_still_works(self, mock_audit):
        group, svc = _group()
        svc.create_requirement.return_value = _mock_requirement()
        result = group.execute_tool(
            tool_name="requirement.create",
            params={"workspace_id": str(WORKSPACE_UUID), "title": "Req"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert "level" not in svc.create_requirement.call_args.kwargs

    def test_update_with_a_different_level_is_a_validation_error(self, mock_audit):
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement(level=1)
        result = group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"level": 4}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.update_requirement.assert_not_called()

    def test_update_with_an_unchanged_level_echo_is_accepted(self, mock_audit):
        """#263's contract, reused: an echoed read-only field must not cost the
        agent the rest of its edit."""
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement(level=2)
        svc.update_requirement.return_value = _mock_requirement(level=2)
        result = group.execute_tool(
            tool_name="requirement.update",
            params={
                "id": str(uuid.uuid4()),
                "data": {"title": "renamed", "level": 2},
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.update_requirement.assert_called_once()

    def test_update_flat_top_level_level_is_refused_too(self, mock_audit):
        """``_field()`` falls back to top-level params for every field, so the
        guard has to read the same fallback or an agent can route around it by
        flattening the payload (the #601 shape)."""
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement(level=1)
        result = group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "level": 3},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.update_requirement.assert_not_called()


# ---------------------------------------------------------------------------
# parent_id is forwarded, so the re-parent is reachable at all
# ---------------------------------------------------------------------------


@patch("mcp_server.tools.requirements.write_mcp_audit")
class TestParentIdIsForwarded:
    def test_parent_id_under_data_is_forwarded(self, mock_audit):
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement()
        svc.update_requirement.return_value = _mock_requirement(level=2)
        new_parent = str(uuid.uuid4())
        result = group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"parent_id": new_parent}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert svc.update_requirement.call_args.kwargs["parent_id"] == new_parent

    def test_parent_id_flat_top_level_is_forwarded(self, mock_audit):
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement()
        svc.update_requirement.return_value = _mock_requirement()
        new_parent = str(uuid.uuid4())
        group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "parent_id": new_parent},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert svc.update_requirement.call_args.kwargs["parent_id"] == new_parent

    def test_explicit_null_parent_id_detaches(self, mock_audit):
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement(level=2)
        svc.update_requirement.return_value = _mock_requirement(level=1)
        group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"parent_id": None}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert svc.update_requirement.call_args.kwargs["parent_id"] is None

    def test_an_omitted_parent_id_is_not_forwarded(self, mock_audit):
        """Absent must not be conflated with "detach to the top" — the service
        uses an ``_UNSET`` sentinel for exactly that distinction."""
        group, svc = _group()
        svc.get_requirement.return_value = _mock_requirement()
        svc.update_requirement.return_value = _mock_requirement()
        group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"title": "renamed"}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert "parent_id" not in svc.update_requirement.call_args.kwargs
