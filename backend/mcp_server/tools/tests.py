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
  test.derive_from_requirement — SysEng 2.0 N5: propose a TestCase draft (title,
                  description, steps) for a Requirement via the LLM adapter.
                  Draft/Accept pattern (REQ-L2-AI-001), now with mode="write"
                  support (Phase 3, REQ-L2-AI-003): mode="preview" (default)
                  returns the draft only; mode="write" persists it as a
                  TestCase and creates a 'verifies' TraceLink back to the
                  source Requirement (write, audited).

Interface contracts implemented:
  IF-MC-INT-004  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (TestService, TraceLinkService,
                       AiDerivationService)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-005_TestToolGroup/
      L3_COMP-MC-005_TestToolGroup_Architecture.md

ADR-L3-MC005-01: test.create auto-links to linked_req_id via 'verifies' TraceLink.
ADR-L3-MC005-02: Test-status written via test.update as data field.
ADR-L3-MC005-03: TraceLinks only via test.link, test.create, or (Phase 3)
  test.derive_from_requirement's mode="write" path.

REQ-L2-MC-007: because mode="write" makes test.derive_from_requirement capable
of mutation, it is registered in mcp_server.tool_registry's
_WRITE_TOOL_PREFIXES (Phase 3). That RBAC gate is name-based (not mode-aware),
so — mirroring the same deliberate restriction documented in
mcp_server/tools/ai_derivation.py — a Viewer can no longer call this tool at
all, including mode="preview".
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.ai_derivation_service import AiDerivationService, LlmResponseError
from application.services import (
    NotFoundError,
    PermissionDeniedError,
    TestRunService,
    TestService,
    TraceLinkService,
    ValidationError,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.ai_derivation import (
    _MODE_POLICY_SCHEMA_PROPERTIES,
    _parse_mode_policy,
)
from mcp_server.tools.base import (
    BaseToolGroup,
    mcp_audit_handoff,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)
from persistence.models import TestCase
from traceability.types import LinkType

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"Passed", "Failed", "Not Run"})
_VALID_RUN_RESULT_STATUSES = frozenset({"passed", "failed", "blocked", "not_run"})

#: TestCase *lifecycle* states — a different axis from the execution statuses
#: above. Derived from the model so it cannot drift from
#: ``testcase_default``'s preset states; ``"outdated"`` is the soft-delete
#: state written by ``workflow.services.outdate`` outside that list. Used only
#: to produce a better error message when a caller confuses the two (GH-453).
_LIFECYCLE_STATES = frozenset(
    {choice.value for choice in TestCase.Status} | {"outdated"}
)


def _test_case_to_dict(tc: Any) -> Dict[str, Any]:
    """Serialise a TestCase ORM object to a dict.

    GH-453: ``status`` and ``version`` are included, matching
    ``_requirement_to_dict`` (mcp_server/tools/requirements.py) and
    ``_need_to_dict`` (mcp_server/tools/needs.py). TestCase was the only
    workflow-backed entity whose MCP payload omitted the lifecycle state
    entirely, so an agent asking "list every draft item" could not evaluate
    test cases at all — the case mismatch this issue is about was only the
    second half of the problem. Additive: existing keys are unchanged.

    The value is the raw lowercase state (``"draft"``/``"ready"``/
    ``"approved"``/``"deprecated"``, or ``"outdated"`` for soft-deleted rows),
    i.e. the same vocabulary the REST ``TestCaseSerializer`` returns.
    """
    result: Dict[str, Any] = {
        "id": str(tc.id),
        "title": tc.title,
        "description": tc.description,
        "status": tc.status,
        "version": tc.version,
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
    """COMP-MC-005 — Test tool group (8 tools)."""
    __test__ = False

    _TOOL_MAP = {
        "test.get": "_handle_get",
        "test.query": "_handle_query",
        "test.create": "_handle_create",
        "test.update": "_handle_update",
        "test.link": "_handle_link",
        "test.run_create": "_handle_run_create",
        "test.run_get": "_handle_run_get",
        "test.run_report_results": "_handle_run_report_results",
        "test.derive_from_requirement": "_handle_derive_from_requirement",
        "test.outdate": "_handle_outdate",
        "test.reactivate": "_handle_reactivate",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "test.get",
            "description": (
                "Fetch a single TestCase by ID. The returned 'status' is the "
                "lifecycle state: draft|ready|approved|deprecated, or "
                "'outdated' for a soft-deleted test case. Change it via "
                "review/workflow transitions, not test.update."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the test case."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "test.query",
            "description": (
                "List TestCases in a workspace. Each entry carries 'status', "
                "the lifecycle state: draft|ready|approved|deprecated, or "
                "'outdated' for a soft-deleted test case. These values are "
                "lowercase, matching requirement and stakeholder-need status "
                "values, so one case-sensitive comparison works across "
                "entity types."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "include_outdated": {
                        "type": "boolean",
                        "description": "If true, include outdated (soft-deleted) test cases. Defaults to false.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "test.create",
            "description": "Create a TestCase, optionally auto-linked to a requirement (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "title": {"type": "string", "description": "Test case title."},
                    "description": {"type": "string", "description": "Test case description."},
                    "type": {"type": "string", "description": "Test type (default 'Unit')."},
                    "linked_req_id": {
                        "type": "string",
                        "description": "Optional requirement UUID to create a 'verifies' TraceLink.",
                    },
                },
                "required": ["workspace_id", "title"],
            },
        },
        {
            "name": "test.update",
            "description": (
                "Update TestCase fields including execution_status (write, "
                "audited). NOTE: the 'status' key here is the EXECUTION "
                "status (Passed|Failed|Not Run) — not the lifecycle status "
                "returned by test.get/test.query "
                "(draft|ready|approved|deprecated). Prefer the explicit "
                "'execution_status' key; move the lifecycle state with the "
                "review/workflow transition tools instead."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the test case."},
                    "data": {
                        "type": "object",
                        "description": (
                            "Fields to update (title, description, steps, "
                            "execution_status). 'status' is accepted as a "
                            "legacy alias for execution_status."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "test.link",
            "description": "Create a 'verifies' TraceLink between a TestCase and a Requirement (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "test_id": {"type": "string", "description": "UUID of the test case."},
                    "req_id": {"type": "string", "description": "UUID of the requirement."},
                },
                "required": ["test_id", "req_id"],
            },
        },
        {
            "name": "test.run_create",
            "description": "Create a TestRun (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "name": {"type": "string", "description": "Test run name."},
                    "ci_job_id": {"type": "string", "description": "Optional CI job identifier."},
                    "test_case_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of test case UUIDs to include.",
                    },
                },
                "required": ["workspace_id", "name"],
            },
        },
        {
            "name": "test.run_get",
            "description": "Fetch a TestRun with its results by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "UUID of the test run."},
                },
                "required": ["run_id"],
            },
        },
        {
            "name": "test.run_report_results",
            "description": "Add result(s) to a TestRun (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "UUID of the test run."},
                    "results": {
                        "type": "array",
                        "description": (
                            "List of result entries. A single result object "
                            "(not wrapped in an array) is also accepted."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "test_case_id": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "description": "One of passed|failed|blocked|not_run.",
                                },
                                "message": {"type": "string"},
                                "duration_ms": {"type": "integer"},
                            },
                            "required": ["test_case_id"],
                        },
                    },
                },
                "required": ["run_id", "results"],
            },
        },
        {
            "name": "test.derive_from_requirement",
            "description": (
                "SysEng 2.0 N5: propose a TestCase draft (title, description, "
                "steps) for a Requirement via the LLM adapter. mode='preview' "
                "(default) returns the draft only; mode='write' persists it as "
                "a TestCase and links it back to the requirement via a "
                "'verifies' trace link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the source requirement.",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["requirement_id"],
            },
        },
        {
            "name": "test.outdate",
            "description": "Soft-delete a TestCase via the workflow engine's outdate escape hatch (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the test case."},
                    "reason": {"type": "string", "description": "Optional audit reason."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "test.reactivate",
            "description": "Restore an outdated TestCase to its previous state (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the test case."},
                },
                "required": ["id"],
            },
        },
    ]

    def __init__(
        self,
        service: Optional[TestService] = None,
        trace_service: Optional[TraceLinkService] = None,
        run_service: Optional[TestRunService] = None,
        ai_derivation_service: Optional[AiDerivationService] = None,
    ) -> None:
        self._service = service or TestService()
        self._trace_service = trace_service or TraceLinkService()
        self._run_service = run_service or TestRunService()
        self._ai_derivation_service = ai_derivation_service or AiDerivationService()

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
        include_outdated = bool(params.get("include_outdated", False))
        try:
            test_cases = self._service.list_test_cases(
                workspace_id, auth_context, include_deleted=include_outdated
            )
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
            # Codeberg #313: suppress create_test_case's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
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
                # Codeberg #313: suppress create_trace_link's single
                # internal _audit() call for the same TraceLink —
                # write_mcp_audit below is the sole entry.
                with mcp_audit_handoff():
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
                # GH-453: test.get/test.query now return the *lifecycle*
                # status, so "read a test case, send it back" lands here with
                # a lifecycle value. Say so explicitly instead of only listing
                # the execution statuses, which reads like the caller invented
                # the value.
                hint = ""
                if status in _LIFECYCLE_STATES:
                    hint = (
                        f" '{status}' is the lifecycle status returned by "
                        "test.get/test.query, which test.update cannot "
                        "change — use the review/workflow transition tools "
                        "for that."
                    )
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Invalid status '{status}'. Valid: {sorted(_VALID_STATUSES)}."
                    f"{hint}",
                )
            try:
                # Codeberg #313: suppress update_test_status's single
                # internal _audit() call for the same entity —
                # write_mcp_audit below is the sole entry.
                with mcp_audit_handoff():
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
                # Codeberg #313: suppress update_test_case's single internal
                # _audit() call for the same entity — write_mcp_audit below
                # is the sole entry.
                with mcp_audit_handoff():
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
            # Codeberg #313: suppress create_trace_link's single internal
            # _audit() call for the same TraceLink — write_mcp_audit below
            # is the sole entry.
            with mcp_audit_handoff():
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


    # ------------------------------------------------------------------
    # test.run_create
    # ------------------------------------------------------------------

    def _handle_run_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.run_create — create a TestRun."""
        workspace_id = require_uuid(params, "workspace_id")
        name = require_param(params, "name")
        ci_job_id: str = params.get("ci_job_id", "")
        test_case_ids_raw = params.get("test_case_ids", [])

        try:
            test_case_ids = [UUID(str(tc)) for tc in test_case_ids_raw]
        except (ValueError, AttributeError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "test_case_ids must be a list of valid UUIDs.",
            )

        try:
            # Codeberg #313: suppress create_test_run's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
                tr = self._run_service.create_test_run(
                    workspace_id=workspace_id,
                    name=str(name),
                    ctx=auth_context,
                    ci_job_id=str(ci_job_id),
                    test_case_ids=test_case_ids,
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
            entity_type="TestRun",
            entity_id=tr.id,
            tool_name="test.run_create",
            api_key=api_key,
        )

        return ToolResult.ok({
            "test_run": {
                "id": str(tr.id),
                "workspace_id": str(tr.workspace_id),
                "name": tr.name,
                "status": tr.status,
                "ci_job_id": tr.ci_job_id,
            }
        })

    # ------------------------------------------------------------------
    # test.run_get
    # ------------------------------------------------------------------

    def _handle_run_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.run_get — fetch a TestRun by UUID."""
        run_id = require_uuid(params, "run_id")
        try:
            tr = self._run_service.get_test_run(run_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        results = [
            {
                "id": str(r.id),
                "test_case_id": str(r.test_case_id) if r.test_case_id else None,
                "test_case_title": r.test_case_title,
                "status": r.status,
                "message": r.message,
                "duration_ms": r.duration_ms,
            }
            for r in tr.results.all()
        ]

        return ToolResult.ok({
            "test_run": {
                "id": str(tr.id),
                "workspace_id": str(tr.workspace_id),
                "name": tr.name,
                "status": tr.status,
                "ci_job_id": tr.ci_job_id,
                "started_at": tr.started_at.isoformat() if tr.started_at else None,
                "finished_at": tr.finished_at.isoformat() if tr.finished_at else None,
            },
            "results": results,
            "result_count": len(results),
        })

    # ------------------------------------------------------------------
    # test.run_report_results
    # ------------------------------------------------------------------

    def _handle_run_report_results(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.run_report_results — add results to a TestRun (bulk).

        REQ-L2-MC-013: accepts run_id + list of results.
        Each result entry: {test_case_id, status, message?, duration_ms?}
        """
        run_id = require_uuid(params, "run_id")
        results_raw = params.get("results", [])

        # Accept a single result object as well as a list (REQ-L2-MC-013).
        if isinstance(results_raw, dict):
            results_raw = [results_raw]

        if not results_raw or not isinstance(results_raw, list):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'results' must be a non-empty array.",
            )

        # Validate each entry
        normalized: list[dict] = []
        for entry in results_raw:
            tc_id = entry.get("test_case_id")
            if not tc_id:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Each result entry must have a 'test_case_id'.",
                )
            status = entry.get("status", "not_run")
            if status not in _VALID_RUN_RESULT_STATUSES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Invalid status '{status}'. Valid: {sorted(_VALID_RUN_RESULT_STATUSES)}",
                )
            normalized.append({
                "test_case_id": str(tc_id),
                "status": status,
                "message": entry.get("message", ""),
                "duration_ms": entry.get("duration_ms"),
            })

        try:
            # Codeberg #313: suppress add_results_bulk's single internal
            # _audit() call (one batch-level "update"/TestRun entry, not
            # per-result) — write_mcp_audit below is the sole entry.
            with mcp_audit_handoff():
                created = self._run_service.add_results_bulk(
                    test_run_id=run_id,
                    results=normalized,
                    ctx=auth_context,
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
            entity_type="TestRun",
            entity_id=run_id,
            tool_name="test.run_report_results",
            api_key=api_key,
            details={"count": len(created)},
        )

        return ToolResult.ok({
            "recorded": len(created),
            "results": [
                {
                    "id": str(r.id),
                    "test_case_id": str(r.test_case_id) if r.test_case_id else None,
                    "test_case_title": r.test_case_title,
                    "status": r.status,
                }
                for r in created
            ],
        })

    # ------------------------------------------------------------------
    # test.derive_from_requirement (SysEng 2.0 N5)
    # ------------------------------------------------------------------

    def _handle_derive_from_requirement(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.derive_from_requirement — propose (or persist) a TestCase draft.

        Draft/Accept pattern (REQ-L2-AI-001), extended with mode/policy
        (Phase 3, REQ-L2-AI-003): mode="preview" (default, unchanged Phase-2
        behaviour) returns the draft only; mode="write" persists it as a
        TestCase via TestService.create_test_case and creates the 'verifies'
        TraceLink back to the source requirement via
        AiDerivationService._write_derived_entity.
        """
        requirement_id = require_uuid(params, "requirement_id")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._ai_derivation_service.derive_testcase_from_requirement(
                auth_context, requirement_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        try:
            req = self._ai_derivation_service._get_requirement(requirement_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        workspace_id = req.artifact.workspace_id
        draft = preview["draft"]

        # The TestCase model already has a structured JSONField `steps`
        # (list of {step, expected_result}) — see persistence.models.TestCase
        # — so the draft's steps are persisted as-is via TestService, no
        # folding into `description` needed.
        try:
            result = self._ai_derivation_service._write_derived_entity(
                ctx=auth_context,
                workspace_id=workspace_id,
                item_type="TestCase",
                create_fn=lambda: self._service.create_test_case(
                    workspace_id=workspace_id,
                    title=draft["title"],
                    ctx=auth_context,
                    description=draft["description"],
                    steps=draft["steps"],
                ),
                # SE endpoint semantics fix TestCase as the link *source* for
                # 'verifies' (traceability.types.SE_LINK_SEMANTICS), so the
                # new TestCase — not the requirement — must be the source.
                source_entity_id=requirement_id,
                source_item_type="Requirement",
                link_type=LinkType.VERIFIES.value,
                policy=policy,
                new_entity_is_link_source=True,
            )
        except (ValidationError, NotFoundError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="derive_from_requirement",
            entity_type="TestCase",
            entity_id=UUID(result["id"]),
            tool_name="test.derive_from_requirement",
            api_key=api_key,
            details={"source_requirement_id": str(requirement_id), "policy": policy},
        )
        return ToolResult.ok({"written": result})

    # ------------------------------------------------------------------
    # test.outdate
    # ------------------------------------------------------------------

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.outdate — soft-delete via the workflow engine (write, audited)."""
        tc_id = require_uuid(params, "id")
        reason: str = params.get("reason", "")

        try:
            tc = self._service.get_test_case(tc_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import outdate

        try:
            outdate(
                item_id=tc_id,
                item_type="TestCase",
                workspace_id=tc.artifact.workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="outdate",
            entity_type="TestCase",
            entity_id=tc_id,
            tool_name="test.outdate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(tc_id), "status": "outdated"})

    # ------------------------------------------------------------------
    # test.reactivate
    # ------------------------------------------------------------------

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """test.reactivate — restore a previously outdated TestCase (write, audited)."""
        tc_id = require_uuid(params, "id")

        try:
            tc = self._service.get_test_case(tc_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import reactivate

        try:
            result = reactivate(
                item_id=tc_id,
                item_type="TestCase",
                workspace_id=tc.artifact.workspace_id,
                ctx=auth_context,
            )
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="reactivate",
            entity_type="TestCase",
            entity_id=tc_id,
            tool_name="test.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(tc_id), "status": result.new_state})


# Backward-compatible alias (canonical public name)
TestToolGroup = McpTestToolGroup

__all__ = ["McpTestToolGroup", "TestToolGroup"]
