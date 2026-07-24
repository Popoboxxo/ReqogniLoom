"""
MCP Tool Group for LLM prompt templates (REQ-L2-PT-001).

leaf_id : COMP-MC-003..006
req_id  : REQ-L2-PT-001 (tenant-scoped editable prompt templates),
          REQ-L2-MC-009 (direct persistence access),
          REQ-L2-MC-012 (MCP audit trail for write tools)

Exposes four tools:
  prompt_template.get(slot: str, workspace_id: str | None) -> str
    Return the effective content for a template name ("slot"), most-specific
    first: active workspace override -> active tenant-global row -> factory
    default (``application.ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS``,
    the 7-entry canonical registry — see that module for why it, not
    ``persistence.models.PROMPT_TEMPLATE_DEFAULTS``, is the source used here).
    Mirrors ``AiDerivationService._get_template_content``'s fallback chain in
    every dimension that matters (same factory-default table, same
    workspace-then-tenant-global precedence), but reads the ``PromptTemplate``
    model directly rather than going through that service (this tool group
    has no dependency on the AI derivation flows).

  prompt_template.list(workspace_id: str | None) -> [templates]
    Return every currently-active ``PromptTemplate`` row for the tenant
    (optionally filtered to one workspace scope). Only real DB rows are
    returned -- factory defaults are never synthesized into this list, since
    a caller asking "what templates exist" should not be told a row exists
    when it doesn't.

  prompt_template.create(name, content, workspace_id: str | None) -> version
  prompt_template.update(name, content, workspace_id: str | None) -> version
    Publish a new active version of a template for a (tenant, workspace_id,
    name) scope: whatever row was previously active for that exact scope is
    deactivated and a new row at version = prior.version + 1 (or 1, if none
    existed) is created and marked active. Both are audited write tools
    (REQ-L2-MC-012) and are RBAC-gated as write operations
    (``tool_registry._WRITE_TOOL_PREFIXES``).

Naming-openness decision (Phase 4): the ``name`` a template is stored under
used to be a closed 3-value enum (``PROMPT_TEMPLATE_DEFAULTS.keys()``); it is
now open-ended, since ``.create()`` can introduce new names at runtime that a
fixed enum could never anticipate. Consequently:
  - The tool schema for ``slot``/``name`` no longer declares a JSON-Schema
    ``enum`` -- it is a free string.
  - ``_handle_get`` no longer treats an unrecognized name as a
    VALIDATION_ERROR (that would incorrectly imply the *name itself* is
    malformed). A name with no active DB row and no factory default now
    returns NOT_FOUND -- it may simply be a template nobody has created yet.
    VALIDATION_ERROR is reserved for genuinely malformed requests (e.g. a
    missing required parameter).

``.create()`` vs ``.update()`` decision: they are a deliberate **alias pair**,
not semantically distinct operations. Both map to the same handler
(``_handle_create_or_update``) and perform the identical "deactivate
whatever is active for this scope, create the next version" operation
regardless of whether a prior active row exists. Rationale:
  - ``PromptTemplate`` rows are documented as "effectively immutable once
    created -- a new prompt version is a new row, not an in-place update"
    (see the model's own class docstring). Under that model there is no
    real distinction between "the first version of a template" and "the
    Nth version of a template" -- both are just "publish a new active
    version for this scope."
  - Gating ``.create()`` to reject existing names (and ``.update()`` to
    reject missing ones) would add verb-based friction for no real safety
    benefit here: unlike e.g. a REST resource where PUT-vs-POST semantics
    guard against accidental overwrites of *unrelated* data, a "new version"
    here never destroys the old content -- the prior version is deactivated,
    not deleted, and remains in the table for audit/rollback purposes. So
    the failure mode a strict split would prevent (a client accidentally
    calling the "wrong" verb) has no real cost to guard against.
  - It matches this task's own reference implementation sketch, which
    performs the version bump unconditionally in a single handler.
"""
from __future__ import annotations

from typing import Any, Dict

from django.db import IntegrityError

from application.ai_derivation_service import (
    PROMPT_TEMPLATE_DEFAULTS,
)
from application.prompt_template_versioning import publish_new_version
from auth_tenancy.context import AuthContext
from persistence.models import PromptTemplate

from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    write_mcp_audit,
)


def _template_to_dict(row: PromptTemplate) -> Dict[str, Any]:
    return {
        "name": row.name,
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "version": row.version,
        "is_active": row.is_active,
        "content": row.content,
    }


class PromptTemplateToolGroup(BaseToolGroup):
    """Prompt template tool group (read + write, tenant-scoped)."""

    _TOOL_MAP = {
        "prompt_template.get": "_handle_get",
        "prompt_template.list": "_handle_list",
        "prompt_template.create": "_handle_create_or_update",
        "prompt_template.update": "_handle_create_or_update",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "prompt_template.get",
            "description": (
                "Return the effective LLM prompt content for a given template "
                "name, for the active tenant (and, if workspace_id is given, "
                "that workspace's override if one exists). Falls back to the "
                "factory default for any of the 7 known template names "
                "(need_to_sysreq | sysreq_to_arch_assign | "
                "sysreq_decompose_next_level | testcase_derive | "
                "architecture_to_risk | workspace_to_glossary | "
                "decision_to_adr) when no row has been created."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slot": {
                        "type": "string",
                        "description": (
                            "Template name (open-ended -- any name created via "
                            "prompt_template.create is valid, not just the "
                            "factory-default slots)."
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Optional workspace scope to check for an override "
                            "before falling back to the tenant-global template."
                        ),
                    },
                },
                "required": ["slot"],
            },
        },
        {
            "name": "prompt_template.list",
            "description": (
                "List all currently-active prompt templates for the tenant, "
                "optionally filtered to a single workspace scope."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope filter.",
                    },
                },
            },
        },
        {
            "name": "prompt_template.create",
            "description": (
                "Publish a new active version of a prompt template for a "
                "(tenant, workspace_id, name) scope, deactivating whatever "
                "version was previously active for that exact scope. "
                "Equivalent to prompt_template.update (alias)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Template name."},
                    "content": {"type": "string", "description": "Prompt body."},
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Optional workspace scope. Omit for a tenant-wide "
                            "default template."
                        ),
                    },
                },
                "required": ["name", "content"],
            },
        },
        {
            "name": "prompt_template.update",
            "description": (
                "Publish a new active version of a prompt template for a "
                "(tenant, workspace_id, name) scope, deactivating whatever "
                "version was previously active for that exact scope. "
                "Equivalent to prompt_template.create (alias)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Template name."},
                    "content": {"type": "string", "description": "Prompt body."},
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Optional workspace scope. Omit for a tenant-wide "
                            "default template."
                        ),
                    },
                },
                "required": ["name", "content"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # prompt_template.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        slot = require_param(params, "slot")
        workspace_id = optional_uuid(params, "workspace_id")

        if workspace_id is not None:
            row = (
                PromptTemplate.objects.filter(
                    tenant_id=auth_context.tenant_id,
                    workspace_id=workspace_id,
                    name=slot,
                    is_active=True,
                )
                .first()
            )
            if row is not None:
                return ToolResult.ok({"slot": slot, "content": row.content})

        row = (
            PromptTemplate.objects.filter(
                tenant_id=auth_context.tenant_id,
                workspace_id=None,
                name=slot,
                is_active=True,
            )
            .first()
        )
        if row is not None:
            return ToolResult.ok({"slot": slot, "content": row.content})

        if slot in PROMPT_TEMPLATE_DEFAULTS:
            return ToolResult.ok({"slot": slot, "content": PROMPT_TEMPLATE_DEFAULTS[slot]})

        return ToolResult.error(
            "NOT_FOUND",
            f"No prompt template named '{slot}' exists for this tenant, and "
            "it is not one of the factory-default slots. Known "
            f"factory-default slots: {', '.join(PROMPT_TEMPLATE_DEFAULTS)}. "
            "Use prompt_template.create to define a new one.",
        )

    # ------------------------------------------------------------------
    # prompt_template.list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        qs = PromptTemplate.objects.filter(
            tenant_id=auth_context.tenant_id, is_active=True
        )
        if workspace_id is not None:
            qs = qs.filter(workspace_id=workspace_id)

        templates = [_template_to_dict(row) for row in qs.order_by("name")]
        return ToolResult.ok({"templates": templates, "count": len(templates)})

    # ------------------------------------------------------------------
    # prompt_template.create / prompt_template.update (alias pair --
    # see module docstring for the decision and its reasoning)
    # ------------------------------------------------------------------

    def _handle_create_or_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        name = require_param(params, "name")
        content = require_param(params, "content")
        workspace_id = optional_uuid(params, "workspace_id")

        had_prior = PromptTemplate.objects.filter(
            tenant_id=auth_context.tenant_id,
            workspace_id=workspace_id,
            name=name,
            is_active=True,
        ).exists()

        try:
            new_row = publish_new_version(
                tenant_id=auth_context.tenant_id,
                name=str(name),
                content=str(content),
                workspace_id=workspace_id,
            )
        except IntegrityError as exc:
            # A concurrent writer for the same scope committed first; the
            # model's own save()-level mutex (see PromptTemplate.save)
            # rejected our attempt to activate a second row for the scope.
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Could not publish a new version for '{name}': {exc}",
            )

        # Audit operation/tool_name reflect what actually happened (a prior
        # active row existed -> "update"; none did -> "create"), independent
        # of which of the two alias tool names the caller invoked -- see the
        # module docstring's create/update alias decision.
        operation = "update" if had_prior else "create"
        write_mcp_audit(
            ctx=auth_context,
            operation=operation,
            entity_type="PromptTemplate",
            entity_id=new_row.id,
            tool_name=f"prompt_template.{operation}",
            api_key=api_key,
        )
        return ToolResult.ok(
            {
                "name": new_row.name,
                "version": new_row.version,
                "workspace_id": str(new_row.workspace_id) if new_row.workspace_id else None,
                "content": new_row.content,
            }
        )


__all__ = ["PromptTemplateToolGroup"]
