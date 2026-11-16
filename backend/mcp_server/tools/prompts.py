"""MCP ``prompts/*`` capability (MCP-Modernisierung, spec section 4).

Exposes the existing, versioned ``PromptTemplate`` system as MCP prompts — the
natural path for a client that wants to offer a human a menu of ready-made
prompts instead of iterating the ``prompt_template.*`` tools. Those tools stay
in place for management (create/update, admin-gated); this capability is the
read/use path only.

Like ``mcp_server.tools.resources``, this group returns an empty
``get_tool_schemas()`` so it is routable but invisible in ``tools/list``.

Placeholder substitution is deliberately not duplicated here: it stays in
``application.prompt_resolver`` / ``prompt_variables``, and ``prompts/get``
therefore advertises ``arguments: []`` and returns the template body verbatim.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from application.prompt_resolver import try_resolve_template_content
from application.prompt_template_versioning import list_active_templates
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, optional_uuid, require_param

logger = logging.getLogger(__name__)


def accessible_workspace_ids(ctx: AuthContext) -> list[UUID]:
    """Return the workspaces *ctx* holds an active role in.

    A module-level function so the visibility filter below has one obvious seam
    to patch in tests. It applies the same narrowing
    ``PromptTemplateToolGroup._handle_list`` applies for the same reason
    (Systemaudit 2026-08-29 section 6.5: an omitted workspace_id must not mean
    "every workspace in the tenant").
    """
    from auth_tenancy.services.authorization import AuthorizationService

    return list(
        AuthorizationService().accessible_workspace_ids(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )
    )


class PromptsToolGroup(BaseToolGroup):
    """Prompt templates over MCP (``prompt.*``, invisible in tools/list)."""

    capability_only = True

    _TOOL_MAP = {
        "prompt.list": "_handle_list",
        "prompt.get": "_handle_get",
    }

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return no schemas — capability, not tool group (see resources.py)."""
        return []

    # ------------------------------------------------------------------
    # prompts/list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """prompt.list — active templates visible to the caller."""
        workspace_id: UUID | None = optional_uuid(params, "workspace_id")
        rows = list_active_templates(
            tenant_id=auth_context.tenant_id, workspace_id=workspace_id
        )

        if workspace_id is None:
            accessible = set(accessible_workspace_ids(auth_context))
            rows = [
                row
                for row in rows
                if row.workspace_id is None or row.workspace_id in accessible
            ]

        prompts = [
            {
                "name": row.name,
                "description": (
                    f"ReqogniLoom prompt template '{row.name}' (version "
                    f"{row.version}"
                    + (
                        f", workspace {row.workspace_id}"
                        if row.workspace_id
                        else ", tenant-wide"
                    )
                    + ")."
                ),
                # Placeholder substitution stays in application.prompt_resolver
                # / prompt_variables. Declaring arguments here would duplicate
                # that catalog into a second, silently diverging place.
                "arguments": [],
            }
            for row in rows
        ]
        return ToolResult.ok({"prompts": prompts})

    # ------------------------------------------------------------------
    # prompts/get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """prompt.get — the effective body of one template as one message."""
        name = str(require_param(params, "name"))
        workspace_id = optional_uuid(params, "workspace_id")

        content = try_resolve_template_content(name, auth_context, workspace_id)
        if content is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"No prompt template named '{name}' is available to this tenant.",
            )

        return ToolResult.ok(
            {
                "description": f"ReqogniLoom prompt template '{name}'.",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": content}}
                ],
            }
        )


__all__ = ["PromptsToolGroup", "accessible_workspace_ids"]
