"""
MCP Summary tool group — the persisted per-scope AI summaries (issue #1793 / S6).

leaf_id : COMP-MC-006 sibling (own namespace)
req_id  : REQ-L2-AI-002 (LLM provider abstraction), REQ-L2-MC-009
          (direct ApplicationService access), REQ-L2-MC-012 (reads do not audit)

Tools implemented:

  summary.get      (read)  — the last stored ``ArtifactSummary`` state of a
                             workspace: every type roster, one type roster, or
                             one artifact scope.
  summary.refresh  (write) — run one scope *now*: the workspace cadence is
                             bypassed, every spend brake (switch, day budget,
                             agent key, throttle) stays in force.

Both tools delegate exclusively to the Layer-2 facade
(``application.artifact_summary_service.ArtifactSummaryService`` and, for the
manual run, ``ArtifactSummarySweeper.run_for_scope(manual=True)``). This module
performs no ORM access of its own (ADR-01,
``rest_api/tests/test_architecture.py``).

Read scoping (``mcp_server/workspace_scope.py``): both tools declare
``workspace_id`` as **required**, so the dispatcher narrows the caller's roles to
that workspace and gates there — a foreign workspace is ``PERMISSION_DENIED``
before a handler runs, and no ``_TOOL_TARGETS`` entry is needed. The optional
``artifact_type``/``artifact_id`` narrow *within* that workspace; both at once is
a caller error, because the two name different summary scopes.

The field set of every answer is the same dict builder REST uses
(``stored_summary_payload``), so the two transports cannot drift apart.
"""
from __future__ import annotations

from typing import Any

from application.artifact_summary_service import ArtifactSummaryService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_uuid,
)
from mcp_server.tools.cross_cutting import artifact_summary_rate_limited


def _optional_type(params: dict[str, Any]) -> str:
    """Return the optional ``artifact_type`` or ``""`` (never ``None``)."""
    raw = params.get("artifact_type")
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ParameterError("Parameter 'artifact_type' must be a string.")
    return raw.strip()


class SummaryToolGroup(BaseToolGroup):
    """Persisted AI summaries — one read tool, one manual-refresh tool."""

    _TOOL_MAP = {
        "summary.get": "_handle_get",
        "summary.refresh": "_handle_refresh",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "summary.get",
            "description": (
                "Read the last STORED AI summary state of one workspace (issue "
                "#1793), one payload per scope: {workspace_id, summary_kind, "
                "artifact_type, artifact_id, text, reason, stale, item_count, "
                "status, provider, model, token_usage, trigger, generated_at, "
                "updated_at}. Read-only and free — no provider call, ever. "
                "Without 'artifact_type'/'artifact_id' it returns every type "
                "roster the workspace has (result.summaries, result.count, "
                "result.truncated, result.limit); with 'artifact_type' it "
                "returns that type's state; with 'artifact_id' the stored "
                "artifact scope. Passing both is a VALIDATION_ERROR. A scope "
                "never summarised answers text=null, item_count=0, reason=null; "
                "'stale' is true when the stored text is older than twice the "
                "workspace cadence (or the sweep is off), and 'reason' then "
                "reads 'stale'. The four values of 'reason' are "
                "'budget_exhausted', 'provider_unavailable', 'stale' and "
                "'disabled' — a degradation is NOT an error."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to read.",
                    },
                    "artifact_type": {
                        "type": "string",
                        "description": (
                            "Optional artifact type (e.g. 'Requirement'). Omit "
                            "for every stored type roster of the workspace."
                        ),
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": (
                            "Optional UUID of one artifact whose stored "
                            "'artifact' scope to read. Mutually exclusive with "
                            "'artifact_type'."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "summary.refresh",
            "description": (
                "Run one summary scope NOW (write, issue #1793). Pass exactly "
                "one of 'artifact_type' (type roster) or 'artifact_id' (that "
                "artifact's on-demand summary). A manual run bypasses the "
                "workspace cadence but keeps every spend brake: "
                "ARTIFACT_SUMMARY_ENABLED, the summary-only day budget, the "
                "configured agent key and the min-interval throttle — a refused "
                "run answers 'outcome'='skipped:<reason>' with the stored state "
                "instead of an error. A type roster answers the same payload as "
                "summary.get plus 'outcome' (summarized|skipped:<reason>|"
                "failed); 'artifact_id' answers the artifact.summary payload "
                "(cache-backed, nothing persisted). Costs at most one LLM call, "
                "and the shared 'artifact_summary' rate scope applies to both "
                "transports."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to refresh in.",
                    },
                    "artifact_type": {
                        "type": "string",
                        "description": (
                            "Artifact type whose roster to re-summarise "
                            "(e.g. 'Requirement')."
                        ),
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": (
                            "UUID of one artifact to summarise on demand. "
                            "Mutually exclusive with 'artifact_type'."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
    ]

    def __init__(self, service: ArtifactSummaryService | None = None) -> None:
        self._service = service or ArtifactSummaryService()

    # -- scopes ---------------------------------------------------------

    @staticmethod
    def _resolve_scope(params: dict[str, Any]) -> tuple[str, Any]:
        """Return ``("all"|"type"|"artifact", value)`` from the two optional ids.

        Exactly one scope may be named; two would be two questions in one call,
        and a refresh in particular must never mean "all of them".
        """
        artifact_type = _optional_type(params)
        artifact_id = optional_uuid(params, "artifact_id")
        if artifact_type and artifact_id is not None:
            raise ParameterError(
                "Pass at most one of 'artifact_type' and 'artifact_id' — they "
                "name different summary scopes."
            )
        if artifact_type:
            return "type", artifact_type
        if artifact_id is not None:
            return "artifact", artifact_id
        return "all", None

    # -- handlers -------------------------------------------------------

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """summary.get — the stored state(s) of one workspace (read-only)."""
        workspace_id = require_uuid(params, "workspace_id")
        scope, value = self._resolve_scope(params)

        if scope == "type":
            payload = self._service.get_type_summary(
                auth_context, workspace_id, value
            )
        elif scope == "artifact":
            payload = self._service.get_artifact_scope_summary(
                auth_context, workspace_id, value
            )
        else:
            payload = self._service.list_type_summaries(auth_context, workspace_id)
        return ToolResult.ok(payload)

    def _handle_refresh(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """summary.refresh — run one scope now (write, one paid call at most)."""
        workspace_id = require_uuid(params, "workspace_id")
        scope, value = self._resolve_scope(params)
        if scope == "all":
            raise ParameterError(
                "Name the scope to refresh: pass 'artifact_type' (type roster) "
                "or 'artifact_id' (one artifact)."
            )

        if artifact_summary_rate_limited(auth_context):
            return ToolResult.error(
                "RATE_LIMITED",
                "artifact_summary rate limit exceeded — retry later.",
            )

        if scope == "artifact":
            # Validate that the artifact actually lives in the workspace the
            # dispatcher gated on before spending a provider call: the on-demand
            # service resolves the artifact on its own, so without this check
            # ``workspace_id`` would be decorative for this branch.
            self._service.get_artifact_scope_summary(auth_context, workspace_id, value)
            result = self._service.summarize_artifact(
                value, auth_context, refresh=True
            )
            return ToolResult.ok(result.as_payload())

        payload = self._service.refresh_type_summary(
            auth_context, workspace_id, value
        )
        return ToolResult.ok(payload)


__all__ = ["SummaryToolGroup"]
