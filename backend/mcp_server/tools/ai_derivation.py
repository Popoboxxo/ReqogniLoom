"""
MCP Tool Group for AI-backed derivation flows (REQ-L2-AI-001, REQ-L2-AI-002).

Exposes the three Draft/Accept derivation flows as MCP tools. Every tool is an
explicit, user-triggered action that returns *drafts only* — nothing is
persisted. Callers accept a draft by invoking the existing create/update tools.

Tools:
  ai_derivation.derive_requirements_from_need(need_id, n=3)
      StakeholderNeed -> proposed system requirement drafts.
  ai_derivation.suggest_architecture_for_requirement(requirement_id)
      Requirement -> suggested architecture element ids (unassigned reqs only).
  ai_derivation.decompose_requirement_next_level(requirement_id)
      Requirement -> next-level requirement drafts (allocated reqs only).

The default LLM provider is ``mock`` (credential-free, deterministic), so the
tools work without external configuration (REQ-L2-AI-002).
"""
from typing import Any, Dict, Optional

from auth_tenancy.context import AuthContext

from application.ai_derivation_service import AiDerivationService, LlmResponseError
from application.base import NotFoundError, ValidationError
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    require_uuid,
)


class AiDerivationToolGroup(BaseToolGroup):
    """AI derivation tool group (draft-only, REQ-L2-AI-002)."""

    _TOOL_MAP = {
        "ai_derivation.derive_requirements_from_need": "_handle_derive_requirements",
        "ai_derivation.suggest_architecture_for_requirement": "_handle_suggest_architecture",
        "ai_derivation.decompose_requirement_next_level": "_handle_decompose_next_level",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "ai_derivation.derive_requirements_from_need",
            "description": (
                "Propose system requirement drafts for a stakeholder need. "
                "Returns drafts only; nothing is persisted."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "need_id": {
                        "type": "string",
                        "description": "UUID of the stakeholder need.",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of requirement drafts (default 3).",
                    },
                },
                "required": ["need_id"],
            },
        },
        {
            "name": "ai_derivation.suggest_architecture_for_requirement",
            "description": (
                "Suggest architecture elements that could satisfy an unassigned "
                "requirement. Returns element ids only; nothing is persisted."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the requirement.",
                    }
                },
                "required": ["requirement_id"],
            },
        },
        {
            "name": "ai_derivation.decompose_requirement_next_level",
            "description": (
                "Propose next-level requirement drafts for a requirement that is "
                "allocated to at least one architecture element. Returns drafts "
                "only; nothing is persisted."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the requirement to decompose.",
                    }
                },
                "required": ["requirement_id"],
            },
        },
    ]

    def __init__(self, service: Optional[AiDerivationService] = None) -> None:
        self._service = service or AiDerivationService()

    def _handle_derive_requirements(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "need_id")
        n_raw = params.get("n", 3)
        try:
            n = int(n_raw)
        except (TypeError, ValueError):
            return ToolResult.error("VALIDATION_ERROR", "'n' must be an integer.")
        try:
            result = self._service.derive_requirements_from_need(
                auth_context, need_id, n=n
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok(result)

    def _handle_suggest_architecture(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        requirement_id = require_uuid(params, "requirement_id")
        try:
            result = self._service.suggest_architecture_for_requirement(
                auth_context, requirement_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok(result)

    def _handle_decompose_next_level(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        requirement_id = require_uuid(params, "requirement_id")
        try:
            result = self._service.decompose_requirement_next_level(
                auth_context, requirement_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok(result)


__all__ = ["AiDerivationToolGroup"]
