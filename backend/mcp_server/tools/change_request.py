"""MCP tool group for Change Requests, including the CCB submit step (REQ-157).

The generic CRUD surface (``change_request.read/query/create/update/delete/
outdate/reactivate``) comes from :class:`GenericCrudToolGroup`. This subclass
adds the one workflow move that used to have no discoverable MCP entry point
(issue #2016): ``draft -> submitted``, the editor-gated CCB submission step of
the ``ccb_approval`` graph in ``workflow/definition_store.py``.

``change_request.update`` deliberately rejects a ``status`` kwarg (see
``generic.py``), so without this tool an agent could only reach ``submitted``
through the undiscoverable ``artifact.bulk_transition`` workaround. The
handler goes through ``ChangeRequestService.transition_status`` (ADR-01 single
entry point), which itself delegates to ``WorkflowFacade.transition`` and keeps
all CCB governance gates -- role checks, change_reason requirement, separation
of duties -- intact.
"""
from __future__ import annotations

from typing import Any

from auth_tenancy.context import AuthContext
from mcp_server.tools.base import (
    ToolResult,
    mcp_audit_handoff,
    reject_unknown_params,
    require_param,
    require_uuid,
    write_mcp_audit,
)
from mcp_server.tools.generic import GenericCrudToolGroup

#: The editor/admin-gated first hop of the CCB graph: ``draft -> submitted``.
SUBMIT_TARGET_STATE = "submitted"


class ChangeRequestToolGroup(GenericCrudToolGroup):
    """Change Request CRUD plus the ``change_request.submit_for_review`` step."""

    def __init__(self) -> None:
        from application.change_request_service import ChangeRequestService

        super().__init__(
            "change_request", ChangeRequestService, item_type="ChangeRequest"
        )
        self._TOOL_MAP = {
            **self._TOOL_MAP,
            "change_request.submit_for_review": "_handle_submit_for_review",
        }
        self._TOOL_SCHEMAS = [
            *self._TOOL_SCHEMAS,
            {
                "name": "change_request.submit_for_review",
                "description": (
                    "Submit a Change Request for CCB review (write): performs "
                    "the editor-gated 'draft -> submitted' transition of the "
                    "ccb_approval workflow. Requires a change_reason. Further "
                    "decisions (under_review/approved/rejected) stay behind "
                    "their approver gates; use review.approve/reject for those."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "UUID of the Change Request to submit.",
                        },
                        "workspace_id": {
                            "type": "string",
                            "description": "UUID of the owning workspace.",
                        },
                        "change_reason": {
                            "type": "string",
                            "description": (
                                "Required rationale for the submission; the "
                                "CCB 'draft -> submitted' transition demands "
                                "a non-empty reason."
                            ),
                        },
                        "expected_version": {
                            "type": "integer",
                            "description": (
                                "Optional last-seen workflow revision (CR-08). "
                                "A stale value is refused as a version "
                                "conflict instead of overwriting the winner."
                            ),
                        },
                    },
                    "required": ["id", "workspace_id", "change_reason"],
                },
            },
        ]

    def _handle_submit_for_review(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Move a draft Change Request to ``submitted`` via the CCB service.

        Domain errors (not found, wrong state, missing reason, denied roles,
        version conflict) propagate to ``BaseToolGroup.execute_tool``, which
        maps them to the canonical MCP error codes. Only a successful move is
        audited here.
        """
        # ``change_request`` is a strict prefix: reject undeclared kwargs so a
        # typo cannot silently become a no-op (#1376 / API-008).
        allowed = self.schema_param_names("change_request.submit_for_review")
        if allowed:
            reject_unknown_params(
                params, allowed, "change_request.submit_for_review"
            )

        cr_id = require_uuid(params, "id")
        workspace_id = require_uuid(params, "workspace_id")
        change_reason = require_param(params, "change_reason")
        expected_version = params.get("expected_version")

        # Codeberg #313: suppress the service/facade's own audit entry so this
        # MCP entry is the single audit trail for the operation.
        with mcp_audit_handoff():
            cr = self._service.transition_status(
                cr_id=cr_id,
                target_status=SUBMIT_TARGET_STATE,
                ctx=auth_context,
                change_reason=change_reason,
                expected_version=expected_version,
            )

        write_mcp_audit(
            ctx=auth_context,
            operation="transition",
            entity_type="ChangeRequest",
            entity_id=cr_id,
            tool_name="change_request.submit_for_review",
            api_key=api_key,
            details={"change_reason": change_reason, "workspace_id": str(workspace_id)},
        )
        return ToolResult.ok(
            {"item_id": str(cr_id), "new_state": SUBMIT_TARGET_STATE, "version": cr.version}
        )


__all__ = ["ChangeRequestToolGroup", "SUBMIT_TARGET_STATE"]
