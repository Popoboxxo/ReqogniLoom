"""
COMP-MC-005 TestToolGroup — 5 test.* MCP tools.

leaf_id : COMP-MC-005
req_id  : REQ-L2-MC-003 (5 Test Tools),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  test.get      — fetch single TestCase by ID
  test.query    — list TestCases with optional workspace filter
  test.create   — create a new TestCase, optionally with TraceLink (write, audited)
  test.update   — update TestCase fields including execution_status (write, audited)
  test.link     — create a 'verifies' TraceLink between TestCase and Requirement (write, audited)

Interface contracts implemented:
  IF-MC-INT-004  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (TestService, TraceLinkService)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-005_TestToolGroup/
      L3_COMP-MC-005_TestToolGroup_Architecture.md

ADR-L3-MC005-01: test.create auto-links to linked_req_id via 'verifies' TraceLink.
ADR-L3-MC005-02: Test-status written via test.update as data field.
ADR-L3-MC005-03: TraceLinks only via test.link or test.create.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.services import (
    NotFoundError,
    PermissionDeniedError,
    TestService,
    TraceLinkService,
    ValidationError,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"Passed", "Failed", "Not Run"})


def _test_case_to_dict(tc: Any) -> Dict[str, Any]:
    """Serialise a TestCase ORM object to a dict."""
    result: Dict[str, Any] = {
        "id": str(tc.id),
        "title": tc.title,
        "description": tc.description,
        "steps": tc.steps if hasattr(tc, "steps") else [],
    }
    if hasattr(tc, "artifact") and tc.artifact:
        result["workspace_id"] = str(tc.artifact.workspace_id)
        # Decode test_type from artifact_type tag (e.g. "TestCase:Unit")
        artifact_type = tc.artifact.artifact_type or ""
        if ":" in artifact_type:
            result["test_type"] = artifact_type.split(":", 1)[1]
    return result


class McpTestToolGroup(BaseToolGroup):
    """COMP-MC-005 — Test tool group (5 tools)."""

    _TOOL_MAP = {
        "test.get": "_handle_get",
        "test.query": "_handle_query",
        "test.create": "_handle_create",
        "test.update": "_handle_update",
        "test.link": "_handle_link",
    }

    def __init__(
        self,
        service: Optional[TestService] = None,
        trace_service: Optional[TraceLinkService] = None,
    ) -> None:
        self._service = service or TestService()
        self._trace_service = trace_service or TraceLinkService()

    # ------------------------------------------------------------------
    # test.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.get — fetch a single TestCase by UUID."""
        tc_id = require_uuid(params, "id")
        try:
            tc = self._service.get_test_case(tc_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"test_case": _test_case_to_dict(tc)})

    # ------------------------------------------------------------------
    # test.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.query — list TestCases by workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for test.query.",
            )
        try:
            test_cases = self._service.list_test_cases(workspace_id, auth_context)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({
            "test_cases": [_test_case_to_dict(tc) for tc in test_cases],
            "count": len(test_cases),
        })

    # ------------------------------------------------------------------
    # test.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.create — create a TestCase, optionally with 'verifies' TraceLink.

        ADR-L3-MC005-01: If linked_req_id is provided, automatically creates
        a 'verifies' TraceLink in the same logical operation.
        """
        title = require_param(params, "title")
        workspace_id = require_uuid(params, "workspace_id")
        test_type: str = params.get("type") or params.get("test_type") or "Unit"
        description: str = params.get("description", "")
        linked_req_id = optional_uuid(params, "linked_req_id")

        try:
            tc = self._service.create_test_case(
                workspace_id=workspace_id,
                title=str(title),
                ctx=auth_context,
                description=description,
                test_type=test_type,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="TestCase",
            entity_id=tc.id,
            tool_name="test.create",
            api_key=api_key,
        )

        trace_link_id: Optional[str] = None
        if linked_req_id:
            try:
                tl = self._trace_service.create_trace_link(
                    source_id=tc.artifact_id,
                    target_id=linked_req_id,
                    link_type="verifies",
                    ctx=auth_context,
                )
                trace_link_id = str(tl.id) if hasattr(tl, "id") else None
                write_mcp_audit(
                    ctx=auth_context,
                    operation="create",
                    entity_type="TraceLink",
                    entity_id=UUID(trace_link_id) if trace_link_id else tc.id,
                    tool_name="test.create",
                    api_key=api_key,
                    details={
                        "source_id": str(tc.artifact_id),
                        "target_id": str(linked_req_id),
                        "link_type": "verifies",
                    },
                )
            except Exception as exc:
                logger.warning("TraceLink creation failed in test.create: %s", exc)

        response_data: Dict[str, Any] = {"test_case": _test_case_to_dict(tc)}
        if trace_link_id:
            response_data["trace_link_id"] = trace_link_id
        return ToolResult.ok(response_data)

    # ------------------------------------------------------------------
    # test.update
    # ------------------------------------------------------------------

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.update — update TestCase fields including execution_status.

        ADR-L3-MC005-02: status written as 'status' field in data dict.
        """
        tc_id = require_uuid(params, "id")
        data: Dict[str, Any] = params.get("data") or {}

        # Handle execution_status update path
        status = data.get("status") or data.get("execution_status")
        if status:
            if status not in _VALID_STATUSES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Invalid status '{status}'. Valid: {sorted(_VALID_STATUSES)}",
                )
            try:
                tc = self._service.update_test_status(
                    test_case_id=tc_id,
                    execution_status=status,
                    ctx=auth_context,
                )
            except NotFoundError as exc:
                return ToolResult.error("NOT_FOUND", str(exc))
            except ValidationError as exc:
                return ToolResult.error("VALIDATION_ERROR", str(exc))
            except PermissionDeniedError as exc:
                return ToolResult.error("PERMISSION_DENIED", str(exc))
        else:
            # General field update
            try:
                tc = self._service.update_test_case(
                    test_case_id=tc_id,
                    ctx=auth_context,
                    title=data.get("title"),
                    description=data.get("description"),
                    steps=data.get("steps"),
                )
            except NotFoundError as exc:
                return ToolResult.error("NOT_FOUND", str(exc))
            except ValidationError as exc:
                return ToolResult.error("VALIDATION_ERROR", str(exc))
            except PermissionDeniedError as exc:
                return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="TestCase",
            entity_id=tc.id,
            tool_name="test.update",
            api_key=api_key,
        )
        return ToolResult.ok({"test_case": _test_case_to_dict(tc)})

    # ------------------------------------------------------------------
    # test.link
    # ------------------------------------------------------------------

    def _handle_link(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.link — create a 'verifies' TraceLink between TestCase and Requirement.

        ADR-L3-MC005-03: Link type is always 'verifies' for test→requirement links.
        """
        test_id = require_uuid(params, "test_id")
        req_id = require_uuid(params, "req_id")

        # Fetch the TestCase to get its artifact_id
        try:
            tc = self._service.get_test_case(test_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        try:
            tl = self._trace_service.create_trace_link(
                source_id=UUID(str(tc.artifact_id)),
                target_id=req_id,
                link_type="verifies",
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        trace_link_id = str(tl.id) if hasattr(tl, "id") else str(test_id)

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="TraceLink",
            entity_id=UUID(trace_link_id),
            tool_name="test.link",
            api_key=api_key,
            details={
                "source_id": str(tc.artifact_id),
                "target_id": str(req_id),
                "link_type": "verifies",
            },
        )
        return ToolResult.ok({
            "trace_link": {
                "id": trace_link_id,
                "test_case_id": str(test_id),
                "requirement_id": str(req_id),
                "link_type": "verifies",
            }
        })


# Backward-compatible alias (canonical public name)
TestToolGroup = McpTestToolGroup

__all__ = ["McpTestToolGroup", "TestToolGroup"]
