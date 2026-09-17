"""CommentToolGroup — comment.* MCP tools (Menschen-im-System spec §4).

Tools implemented:
  comment.create   — add a comment to an artifact
  comment.list     — list an artifact's comments
  comment.resolve  — mark a comment resolved

Deliberately NOT implemented:
  comment.delete   — spec §4 restricts deletion to the author or an admin; that
                     is a human decision, not an agent capability.

Every value in a returned payload is stringified: the MCP transport serialises
with stdlib ``json.dumps``, which cannot encode ``UUID`` or ``datetime`` (see
issue #441 — an unencodable frame used to escape as a Django HTML 500).

Plan-deviation note: the plan block for this module is written against a
``group.dispatch(...)`` / ``ToolResult(payload=...)`` API that does not exist
here. This implementation uses the real seam — handlers are called as
``handler(params=..., auth_context=..., api_key=...)`` by
``BaseToolGroup.execute_tool`` and return ``ToolResult.ok(dict)``. The tool
names, schemas, service delegation and stringification contract are unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.comment_service import CommentService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid

logger = logging.getLogger(__name__)


def _comment_to_dict(comment: Any) -> Dict[str, Any]:
    """Serialise a Comment for MCP responses (all values JSON-native)."""
    return {
        "id": str(comment.id),
        "artifact_id": str(comment.artifact_id),
        "text": comment.text,
        "author_id": str(comment.author_id) if comment.author_id else None,
        "resolved": bool(comment.resolved),
        "resolved_by_id": str(comment.resolved_by_id) if comment.resolved_by_id else None,
        "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


class CommentToolGroup(BaseToolGroup):
    """Comment tool group (3 tools) — wraps ``CommentService``."""

    _TOOL_MAP = {
        "comment.create": "_handle_create",
        "comment.list": "_handle_list",
        "comment.resolve": "_handle_resolve",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "comment.create",
            "description": "Add a comment to an artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "text": {"type": "string", "description": "Comment body."},
                },
                "required": ["artifact_id", "text"],
            },
        },
        {
            "name": "comment.list",
            "description": "List the comments on an artifact, oldest first.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "include_resolved": {
                        "type": "boolean",
                        "description": "Include resolved comments (default true).",
                    },
                },
                "required": ["artifact_id"],
            },
        },
        {
            "name": "comment.resolve",
            "description": "Mark a comment as resolved.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the comment."},
                },
                "required": ["id"],
            },
        },
    ]

    @staticmethod
    def _get_service() -> CommentService:
        """Return a CommentService instance."""
        return CommentService()

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Handle ``comment.create``."""
        artifact_id: UUID = require_uuid(params, "artifact_id")
        comment = self._get_service().create_comment(
            artifact_id=artifact_id, text=params.get("text", ""), ctx=auth_context
        )
        return ToolResult.ok(_comment_to_dict(comment))

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Handle ``comment.list``."""
        artifact_id: UUID = require_uuid(params, "artifact_id")
        rows = self._get_service().list_for_artifact(
            artifact_id,
            auth_context,
            include_resolved=bool(params.get("include_resolved", True)),
        )
        return ToolResult.ok({"comments": [_comment_to_dict(row) for row in rows]})

    def _handle_resolve(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Handle ``comment.resolve``."""
        comment_id: UUID = require_uuid(params, "id")
        comment = self._get_service().resolve_comment(comment_id, auth_context)
        return ToolResult.ok(_comment_to_dict(comment))


__all__ = ["CommentToolGroup"]
