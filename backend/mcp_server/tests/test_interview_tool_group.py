"""
Tests for the interview.* MCP tool group (Interview-Management-Engine spec §4).

leaf_id : Task 4 of feat/interview-management-engine
req_id  : spec §4 (interview.start / get_state / answer / list / get)

Pattern matches mcp_server/tests/test_tool_groups.py (see
TestStakeholderNeedsToolGroup): a mocked InterviewService is injected into
the tool group, and every call goes through ``group.execute_tool(...)`` —
the real dispatcher (routing + ParameterError -> VALIDATION_ERROR mapping),
not the private ``_handle_*`` methods directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from application.base import NotFoundError, ValidationError

from mcp_server.tools.interview import InterviewToolGroup


EDITOR_CTX_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_UUID = UUID("00000000-0000-0000-0000-000000000002")
API_KEY_UUID = UUID("00000000-0000-0000-0000-000000000003")
VALID_API_KEY = "reqlo_testkey1234"
WORKSPACE_UUID = UUID("00000000-0000-0000-0000-000000000010")
SESSION_UUID = UUID("00000000-0000-0000-0000-000000000080")


def _make_ctx(role="editor"):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=EDITOR_CTX_ID,
        tenant_id=TENANT_UUID,
        active_roles=(role,),
        auth_method=AuthMethod.API_KEY,
        api_key_id=API_KEY_UUID,
    )


EDITOR_CTX = _make_ctx("editor")


def _mock_session(
    id_val=None,
    workspace_id=WORKSPACE_UUID,
    artifact_type="Requirement",
    status="in_progress",
):
    session = MagicMock()
    session.id = id_val or SESSION_UUID
    session.workspace_id = workspace_id
    session.artifact_type = artifact_type
    session.status = status
    return session


def _mock_state(session, missing_fields=None, collected_fields=None):
    return {
        "session_id": str(session.id),
        "status": session.status,
        "phase": "elicitation",
        "collected_fields": collected_fields or {},
        "missing_fields": missing_fields
        if missing_fields is not None
        else [{"name": "title", "type": "text", "choices": None}],
        "grounding_snapshot": {},
    }


class TestInterviewToolGroup:
    def _group(self, service=None):
        if service is None:
            service = MagicMock()
        return InterviewToolGroup(service=service), service

    # ------------------------------------------------------------------
    # interview.start
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.interview.write_mcp_audit")
    def test_start_returns_session_id_and_missing_fields(self, mock_audit):
        group, svc = self._group()
        session = _mock_session()
        svc.start.return_value = session
        svc.get_state.return_value = _mock_state(session)

        result = group.execute_tool(
            tool_name="interview.start",
            params={"artifact_type": "Requirement", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["session_id"] == str(session.id)
        assert "title" in [f["name"] for f in result.data["missing_fields"]]
        svc.start.assert_called_once_with(
            EDITOR_CTX, "Requirement", WORKSPACE_UUID, seed_context=None
        )
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tool_name"] == "interview.start"
        # AuditLog.op is a fixed vocabulary (audit/models.py OP_CHOICES) --
        # a new InterviewSession row maps to "create", not a literal "start".
        assert call_kwargs["operation"] == "create"

    @patch("mcp_server.tools.interview.write_mcp_audit")
    def test_start_passes_seed_context_through_to_the_service(self, mock_audit):
        """seed_context is part of InterviewService.start()'s interface but
        was never read/forwarded by the MCP layer -- confirm it now is."""
        group, svc = self._group()
        session = _mock_session()
        svc.start.return_value = session
        svc.get_state.return_value = _mock_state(session)

        result = group.execute_tool(
            tool_name="interview.start",
            params={
                "artifact_type": "Requirement",
                "workspace_id": str(WORKSPACE_UUID),
                "seed_context": {"title": "Pre-known title"},
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        svc.start.assert_called_once_with(
            EDITOR_CTX,
            "Requirement",
            WORKSPACE_UUID,
            seed_context={"title": "Pre-known title"},
        )

    def test_start_validation_error_returns_validation_error(self):
        group, svc = self._group()
        svc.start.side_effect = ValidationError("Interviews are not available for artifact_type='Bogus'")

        result = group.execute_tool(
            tool_name="interview.start",
            params={"artifact_type": "Bogus", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_start_requires_workspace_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="interview.start",
            params={"artifact_type": "Requirement"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.start.assert_not_called()

    def test_start_unknown_workspace_returns_not_found(self):
        """An unknown workspace_id must surface as a clean NOT_FOUND, not a
        raw INTERNAL_ERROR from an unhandled exception."""
        group, svc = self._group()
        svc.start.side_effect = NotFoundError("Workspace not found")

        result = group.execute_tool(
            tool_name="interview.start",
            params={"artifact_type": "Requirement", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    # ------------------------------------------------------------------
    # interview.answer + interview.get_state
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.interview.write_mcp_audit")
    def test_answer_then_get_state_reflects_it(self, mock_audit):
        group, svc = self._group()
        session = _mock_session()
        svc.answer.return_value = session
        svc.get_state.return_value = _mock_state(
            session, missing_fields=[], collected_fields={"title": "SSO login"}
        )

        answer_result = group.execute_tool(
            tool_name="interview.answer",
            params={"session_id": str(session.id), "field": "title", "value": "SSO login"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert answer_result.success is True
        svc.answer.assert_called_once_with(EDITOR_CTX, session.id, "title", "SSO login")
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tool_name"] == "interview.answer"
        # AuditLog.op is a fixed vocabulary (audit/models.py OP_CHOICES) --
        # updating an existing InterviewSession row maps to "update", not a literal "answer".
        assert call_kwargs["operation"] == "update"

        state_result = group.execute_tool(
            tool_name="interview.get_state",
            params={"session_id": str(session.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert state_result.success is True
        assert state_result.data["collected_fields"]["title"] == "SSO login"

    def test_answer_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.answer.side_effect = NotFoundError("InterviewSession not found")

        result = group.execute_tool(
            tool_name="interview.answer",
            params={"session_id": str(SESSION_UUID), "field": "title", "value": "x"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_answer_validation_error_returns_validation_error(self):
        group, svc = self._group()
        svc.answer.side_effect = ValidationError("InterviewSession is completed, cannot answer.")

        result = group.execute_tool(
            tool_name="interview.answer",
            params={"session_id": str(SESSION_UUID), "field": "title", "value": "x"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_answer_missing_value_param_returns_validation_error(self):
        """value is schema-required; an omitted value must not silently
        record None as the answer."""
        group, svc = self._group()

        result = group.execute_tool(
            tool_name="interview.answer",
            params={"session_id": str(SESSION_UUID), "field": "title"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.answer.assert_not_called()

    def test_get_state_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.get_state.side_effect = NotFoundError("InterviewSession not found")

        result = group.execute_tool(
            tool_name="interview.get_state",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    # ------------------------------------------------------------------
    # interview.list
    # ------------------------------------------------------------------

    def test_list_returns_started_session(self):
        group, svc = self._group()
        session = _mock_session()
        svc.list_sessions.return_value = [session]

        result = group.execute_tool(
            tool_name="interview.list",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert str(session.id) in [s["id"] for s in result.data["sessions"]]
        svc.list_sessions.assert_called_once_with(EDITOR_CTX, WORKSPACE_UUID, status=None)

    def test_list_passes_status_filter(self):
        group, svc = self._group()
        svc.list_sessions.return_value = []

        result = group.execute_tool(
            tool_name="interview.list",
            params={"workspace_id": str(WORKSPACE_UUID), "status": "completed"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        svc.list_sessions.assert_called_once_with(EDITOR_CTX, WORKSPACE_UUID, status="completed")

    def test_list_requires_workspace_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="interview.list",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.list_sessions.assert_not_called()

    # ------------------------------------------------------------------
    # interview.get
    # ------------------------------------------------------------------

    def test_get_calls_service(self):
        group, svc = self._group()
        session = _mock_session()
        svc.get.return_value = session

        result = group.execute_tool(
            tool_name="interview.get",
            params={"session_id": str(session.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["id"] == str(session.id)
        svc.get.assert_called_once_with(EDITOR_CTX, session.id)

    def test_get_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.get.side_effect = NotFoundError("InterviewSession not found")

        result = group.execute_tool(
            tool_name="interview.get",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_unknown_tool_returns_error(self):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="interview.nonexistent",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    # ------------------------------------------------------------------
    # interview.grounding_context
    # ------------------------------------------------------------------

    def test_grounding_context_calls_service_and_returns_snapshot(self):
        group, svc = self._group()
        svc.grounding_context.return_value = {
            "candidates": [
                {"artifact_id": str(WORKSPACE_UUID), "title": "SSO login support", "score": None}
            ]
        }

        result = group.execute_tool(
            tool_name="interview.grounding_context",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data == svc.grounding_context.return_value
        svc.grounding_context.assert_called_once_with(EDITOR_CTX, SESSION_UUID)

    def test_grounding_context_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.grounding_context.side_effect = NotFoundError("InterviewSession not found")

        result = group.execute_tool(
            tool_name="interview.grounding_context",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    # ------------------------------------------------------------------
    # interview.formalize
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.interview.write_mcp_audit")
    def test_formalize_calls_service_and_returns_result(self, mock_audit):
        group, svc = self._group()
        svc.formalize.return_value = {
            "resulting_artifact_ids": ["11111111-1111-1111-1111-111111111111"],
            "status": "completed",
        }

        result = group.execute_tool(
            tool_name="interview.formalize",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data == svc.formalize.return_value
        svc.formalize.assert_called_once_with(EDITOR_CTX, SESSION_UUID)
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tool_name"] == "interview.formalize"
        assert call_kwargs["operation"] == "update"

    def test_formalize_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.formalize.side_effect = NotFoundError(
            "Target artifact no longer exists; cannot formalize an update against it."
        )

        result = group.execute_tool(
            tool_name="interview.formalize",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_formalize_validation_error_returns_validation_error(self):
        group, svc = self._group()
        svc.formalize.side_effect = ValidationError(
            "formalize() for artifact_type='Risk' is not implemented yet"
        )

        result = group.execute_tool(
            tool_name="interview.formalize",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_formalize_requires_session_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="interview.formalize",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.formalize.assert_not_called()

    # ------------------------------------------------------------------
    # interview.set_target
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.interview.write_mcp_audit")
    def test_set_target_calls_service_and_returns_state(self, mock_audit):
        group, svc = self._group()
        session = _mock_session()
        artifact_id = "22222222-2222-2222-2222-222222222222"
        svc.set_target.return_value = _mock_state(session, missing_fields=[])

        result = group.execute_tool(
            tool_name="interview.set_target",
            params={"session_id": str(session.id), "artifact_id": artifact_id},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data == svc.set_target.return_value
        svc.set_target.assert_called_once_with(
            EDITOR_CTX, session.id, UUID(artifact_id)
        )
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tool_name"] == "interview.set_target"
        assert call_kwargs["operation"] == "update"

    def test_set_target_not_found_returns_not_found(self):
        group, svc = self._group()
        svc.set_target.side_effect = NotFoundError(
            "Requirement with artifact_id=... not found"
        )

        result = group.execute_tool(
            tool_name="interview.set_target",
            params={
                "session_id": str(SESSION_UUID),
                "artifact_id": "22222222-2222-2222-2222-222222222222",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_set_target_validation_error_returns_validation_error(self):
        group, svc = self._group()
        svc.set_target.side_effect = ValidationError(
            "set_target() for artifact_type='Risk' is not supported"
        )

        result = group.execute_tool(
            tool_name="interview.set_target",
            params={
                "session_id": str(SESSION_UUID),
                "artifact_id": "22222222-2222-2222-2222-222222222222",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_set_target_requires_artifact_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="interview.set_target",
            params={"session_id": str(SESSION_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.set_target.assert_not_called()


# ---------------------------------------------------------------------------
# Registration / RBAC classification structural checks
# ---------------------------------------------------------------------------


class TestInterviewToolGroupRegistration:
    def test_group_is_registered_under_interview_prefix(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()
        assert "interview" in registry._groups
        assert isinstance(registry._groups["interview"], InterviewToolGroup)

    def test_write_tools_are_registered_as_write_tools(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        for tool_name in (
            "interview.start",
            "interview.answer",
            "interview.formalize",
            "interview.grounding_context",
            "interview.set_target",
        ):
            assert any(
                tool_name == wt or tool_name.startswith(wt) for wt in _WRITE_TOOL_PREFIXES
            ), f"{tool_name} missing from _WRITE_TOOL_PREFIXES"

    def test_read_tools_are_not_rbac_gated(self):
        """interview.get_state/list/get are reads: under the fail-closed RBAC
        gate (_is_write_tool in tool_registry.py) any tool name not
        explicitly listed as read-only defaults to write-protected, so a
        Viewer would wrongly be denied a plain read unless these are added
        to _READ_ONLY_TOOL_NAMES.
        interview.grounding_context is deliberately NOT in this list: it now
        makes a real LLM provider call (Task 6), so it is write-gated like
        every other LLM-invoking MCP tool (e.g. ai_derivation.*) -- a
        Viewer-role API key must not be able to drive LLM spend.
        """
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        for tool_name in (
            "interview.get_state",
            "interview.list",
            "interview.get",
        ):
            assert registry._is_write_tool(tool_name) is False, (
                f"{tool_name} is wrongly RBAC-gated as a write tool"
            )
        assert registry._is_write_tool("interview.grounding_context") is True, (
            "interview.grounding_context makes a real LLM call and must be "
            "write-gated"
        )
