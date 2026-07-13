"""
MCP Tool Group for LLM prompt templates (REQ-L2-PT-001).

leaf_id : COMP-MC-003..006
req_id  : REQ-L2-PT-001 (tenant-scoped editable prompt templates),
          REQ-L2-MC-009 (direct persistence access)

Exposes a single read tool:
  prompt_template.get(slot: str) -> str
    Return the current content of a prompt slot for the active tenant. If no
    PromptTemplate row exists yet, the factory default for that slot is
    returned, so callers always receive usable prompt content.

Valid slots: need_to_sysreq | sysreq_to_arch_assign | sysreq_decompose_next_level
"""
from typing import Any, Dict

from auth_tenancy.context import AuthContext
from persistence.models import PROMPT_TEMPLATE_DEFAULTS, PromptTemplate

from mcp_server.tools.base import BaseToolGroup, ToolResult, require_param


class PromptTemplateToolGroup(BaseToolGroup):
    """Prompt template tool group (read-only slot retrieval)."""

    _TOOL_MAP = {
        "prompt_template.get": "_handle_get",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "prompt_template.get",
            "description": (
                "Return the current LLM prompt content for a given slot "
                "(need_to_sysreq | sysreq_to_arch_assign | "
                "sysreq_decompose_next_level) for the active tenant."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slot": {
                        "type": "string",
                        "enum": list(PROMPT_TEMPLATE_DEFAULTS.keys()),
                        "description": "Prompt slot name.",
                    }
                },
                "required": ["slot"],
            },
        }
    ]

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        slot = require_param(params, "slot")
        if slot not in PROMPT_TEMPLATE_DEFAULTS:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Unknown prompt slot: '{slot}'. Valid slots: "
                f"{', '.join(PROMPT_TEMPLATE_DEFAULTS)}.",
            )

        # TenantContext is active during dispatch, so the default manager is
        # already tenant-scoped. Fall back to the factory default when no row
        # has been created for this tenant yet.
        row = PromptTemplate.objects.filter(
            tenant_id=auth_context.tenant_id
        ).first()
        content = (
            getattr(row, slot) if row is not None else PROMPT_TEMPLATE_DEFAULTS[slot]
        )
        return ToolResult.ok({"slot": slot, "content": content})


__all__ = ["PromptTemplateToolGroup"]
