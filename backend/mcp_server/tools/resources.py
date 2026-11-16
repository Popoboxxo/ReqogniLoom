"""MCP ``resources/*`` capability (MCP-Modernisierung, spec section 4).

URI scheme: ``reqogniloom://artifact/{id}`` where ``{id}`` is a
``persistence.models.Artifact`` primary key.

These are internal pseudo-tools, not part of the public tool surface:
``get_tool_schemas()`` returns an empty list, so ``tools/list`` never shows
them, while ``ToolGroupRouter`` still routes ``resource.*`` here. Dispatching
through ``ToolRegistry.dispatch_request()`` is deliberate — API-key validation,
TenantContext/RLS arming, role resolution and the RBAC gate then apply to the
resource surface exactly as they do to every tool, with no second auth path to
keep in sync (ADR-011).

A workspace-fenced API key (``ApiKey.workspace_ids``) reaches this group the
same way as any other tool: ``resources/read`` carries no workspace of its own,
so the dispatcher's fence denies the workspace-less call fail-closed. A fenced
client passes ``workspace_id`` on ``resources/list`` instead.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from application.artifact_markdown import (
    ARTIFACT_MARKDOWN_MIME,
    render_artifact_markdown,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_param,
)

logger = logging.getLogger(__name__)

#: Every artifact resource URI starts with this.
ARTIFACT_URI_PREFIX = "reqogniloom://artifact/"

#: Advertised on ``resources/templates/list``.
ARTIFACT_URI_TEMPLATE = "reqogniloom://artifact/{id}"

#: Hard ceiling for one ``resources/list`` page. The MCP spec gives a client no
#: page-size parameter it can rely on, so the server owns the bound — an
#: unbounded enumeration of a large tenant would be exactly the context-cost
#: problem this spec set out to reduce.
MAX_RESOURCE_PAGE = 200
DEFAULT_RESOURCE_PAGE = 100


def parse_artifact_uri(uri: str) -> UUID:
    """Return the ``Artifact`` id encoded in *uri*.

    Raises:
        ParameterError: *uri* does not use the artifact scheme, or its id is
            not a UUID. Surfaces as ``VALIDATION_ERROR`` through
            ``BaseToolGroup.execute_tool``.
    """
    if not isinstance(uri, str) or not uri.startswith(ARTIFACT_URI_PREFIX):
        raise ParameterError(
            f"Unsupported resource URI '{uri}'. Expected '{ARTIFACT_URI_TEMPLATE}'."
        )
    raw = uri[len(ARTIFACT_URI_PREFIX) :].strip()
    try:
        return UUID(raw)
    except (ValueError, AttributeError):
        raise ParameterError(
            f"Resource URI '{uri}' does not carry a valid artifact UUID."
        ) from None


class ResourcesToolGroup(BaseToolGroup):
    """Artifact resources over MCP (``resource.*``, invisible in tools/list)."""

    capability_only = True

    _TOOL_MAP = {
        "resource.list": "_handle_list",
        "resource.read": "_handle_read",
        "resource.templates_list": "_handle_templates_list",
    }

    def __init__(self, artifact_service: Any | None = None) -> None:
        if artifact_service is None:
            from application.artifact_service import ArtifactService

            artifact_service = ArtifactService()
        self._artifact_service = artifact_service

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return no schemas — this group is a capability, not a tool group.

        ``BaseToolGroup``'s default would synthesise a fallback schema per
        ``_TOOL_MAP`` entry and leak three phantom tools into every manifest.
        """
        return []

    # ------------------------------------------------------------------
    # resources/list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.list — a bounded page of artifact resources."""
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            limit = int(params.get("limit", DEFAULT_RESOURCE_PAGE))
            offset = int(params.get("cursor", 0))
        except (TypeError, ValueError):
            raise ParameterError("'limit' and 'cursor' must be integers.") from None
        limit = max(1, min(limit, MAX_RESOURCE_PAGE))
        offset = max(0, offset)

        try:
            rows = self._artifact_service.list_artifact_resources(
                ctx=auth_context,
                workspace_id=workspace_id,
                limit=limit,
                offset=offset,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        resources = [
            {
                "uri": f"{ARTIFACT_URI_PREFIX}{row['artifact_id']}",
                "name": row.get("title")
                or f"{row['artifact_type']} {row['artifact_id']}",
                "description": f"{row['artifact_type']} artifact rendered as Markdown.",
                "mimeType": ARTIFACT_MARKDOWN_MIME,
            }
            for row in rows
        ]
        payload: dict[str, Any] = {"resources": resources}
        if len(rows) == limit:
            payload["nextCursor"] = str(offset + limit)
        return ToolResult.ok(payload)

    # ------------------------------------------------------------------
    # resources/read
    # ------------------------------------------------------------------

    def _handle_read(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.read — one artifact as Markdown.

        Authorization: the dispatcher already applied API-key validation, the
        workspace fence, RBAC and the preset gate. On top of that this handler
        narrows the read to the workspaces the caller holds a role in — the
        same set ``resources/list`` enumerates — so a Viewer in workspace A
        cannot read an artifact of workspace B by guessing its UUID. A
        foreign-tenant or unknown artifact answers NOT_FOUND (no existence
        oracle), a same-tenant artifact outside the caller's workspaces
        answers PERMISSION_DENIED.
        """
        from mcp_server.tools.prompts import accessible_workspace_ids

        uri = str(require_param(params, "uri"))
        artifact_id = parse_artifact_uri(uri)

        workspace_id = self._artifact_service.get_artifact_workspace_id(
            artifact_id, auth_context
        )
        if workspace_id is None:
            return ToolResult.error("NOT_FOUND", f"Artifact {artifact_id} not found")
        if workspace_id not in set(accessible_workspace_ids(auth_context)):
            return ToolResult.error(
                "PERMISSION_DENIED",
                f"Artifact {artifact_id} is outside the caller's workspaces.",
            )

        try:
            markdown = render_artifact_markdown(artifact_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        return ToolResult.ok(
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": ARTIFACT_MARKDOWN_MIME,
                        "text": markdown,
                    }
                ]
            }
        )

    # ------------------------------------------------------------------
    # resources/templates/list
    # ------------------------------------------------------------------

    def _handle_templates_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.templates_list — the parameterised artifact URI."""
        return ToolResult.ok(
            {
                "resourceTemplates": [
                    {
                        "uriTemplate": ARTIFACT_URI_TEMPLATE,
                        "name": "Artifact",
                        "description": (
                            "Any ReqogniLoom artifact (Requirement, "
                            "StakeholderNeed, ArchitectureElement, TestCase, "
                            "Adr, Risk, Issue, Goal, MainGoal, Document, Icd) "
                            "rendered as Markdown, addressed by its Artifact id."
                        ),
                        "mimeType": ARTIFACT_MARKDOWN_MIME,
                    }
                ]
            }
        )


__all__ = [
    "ARTIFACT_URI_PREFIX",
    "ARTIFACT_URI_TEMPLATE",
    "MAX_RESOURCE_PAGE",
    "ResourcesToolGroup",
    "parse_artifact_uri",
]
