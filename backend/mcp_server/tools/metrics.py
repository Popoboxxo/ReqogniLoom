"""
MCP Metrics tool group — central statistics surface (Issue #1265).

leaf_id : COMP-MC-003 (RequirementsToolGroup sibling; own namespace)
req_id  : REQ-L1-031 (SE process metrics), REQ-L2-SM-001 (SeMetrics REST API),
          REQ-L2-MC-009 (direct ApplicationService access)

Tools implemented:

  metrics.catalog (read) — the available statistics: key, title, unit,
                           calculation scope (workspace/tenant/artifact_type),
                           query contract and default visibility.
  metrics.get     (read) — the *values* of the requested statistics for one
                           workspace, reusing the cached computation.

Both tools are read-only and delegate exclusively to the SeMetrics service
facade (``se_metrics.services``) — they never touch the ORM themselves, the
same ADR-01 discipline every tool group follows. The catalogue is identical to
``GET /api/v1/metrics/catalog/``; ``metrics.get`` is identical to
``GET /api/v1/metrics/?keys=…`` (Issue #1265 §2/§3, "one registry, three
transports").

Read scoping (``mcp_server/workspace_scope.py``):

  * ``metrics.catalog`` is a pure static registry read with no workspace data
    and no DB access — it is listed in ``TENANT_SCOPED_READ_TOOLS`` (it accepts
    no ``workspace_id``, so there is nothing to scope to).
  * ``metrics.get`` declares ``workspace_id`` as *required*, so the dispatcher
    narrows the caller's roles to that workspace and gates the read there.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from auth_tenancy.context import AuthContext

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    require_uuid,
)

from se_metrics.services import get_metric_catalog, get_metric_values


def _parse_keys(raw: Any) -> Optional[List[str]]:
    """Normalise the ``keys`` parameter to a list of strings, or None.

    Accepts the two shapes an MCP client naturally sends — an array of strings
    or a single comma-separated string — and normalises both. An explicitly
    empty value means "all metrics" (mirrors the REST ``?keys=`` contract).
    An unexpected shape is a caller error, not a silent no-op.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        keys: List[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ParameterError(
                    "Parameter 'keys' must be an array of strings."
                )
            stripped = item.strip()
            if stripped:
                keys.append(stripped)
        return keys
    raise ParameterError(
        "Parameter 'keys' must be an array of strings or a comma-separated string."
    )


def _parse_bool(raw: Any, name: str) -> bool:
    """Parse an opt-in boolean parameter; absent means False."""
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    lowered = str(raw).strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off", ""):
        return False
    raise ParameterError(f"Parameter '{name}' must be a boolean.")


class MetricsToolGroup(BaseToolGroup):
    """COMP-MC-003 — SeMetrics statistics MCP tool group (2 read tools)."""

    _TOOL_MAP = {
        "metrics.catalog": "_handle_catalog",
        "metrics.get": "_handle_get",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "metrics.catalog",
            "description": (
                "List the available SE statistics (Issue #1265): for each "
                "metric the key, title, unit, calculation scope "
                "(workspace|tenant|artifact_type), query contract (source + "
                "accepted parameters), cost flag and default visibility. "
                "Pure metadata — no workspace and no computation required. "
                "Identical to GET /api/v1/metrics/catalog/."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "metrics.get",
            "description": (
                "Read the values of the requested SE statistics for one "
                "workspace (Issue #1265). Reuses the cached computation; pass "
                "``refresh=true`` to force an on-demand recompute of expensive "
                "coverage metrics. Response: {workspace_id, computed_at, "
                "timeframe, metrics: {<key>: {value, unit, scope, expensive, "
                "computed_at}}, unknown_keys: [...]}. Omit ``keys`` for every "
                "registered metric. Identical to "
                "GET /api/v1/metrics/?workspace_id=…&keys=…."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to compute for.",
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Metric keys to return (see metrics.catalog). "
                            "Omitted or empty means every registered metric."
                        ),
                    },
                    "timeframe": {
                        "type": "string",
                        "description": (
                            "Optional ISO-8601 period for the volatility "
                            "window, e.g. \"P30D\" (default)."
                        ),
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": (
                            "Invalidate the cached computation before reading, "
                            "forcing an on-demand recompute."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
    ]

    def _handle_catalog(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """metrics.catalog — the available statistics (read-only)."""
        return ToolResult.ok(get_metric_catalog())

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """metrics.get — the requested statistics' values (read-only)."""
        # Required in the schema; the dispatcher has already resolved and gated
        # the workspace before this handler runs.
        workspace_id = require_uuid(params, "workspace_id")

        keys = _parse_keys(params.get("keys"))
        refresh = _parse_bool(params.get("refresh"), "refresh")

        timeframe = params.get("timeframe")
        if timeframe is not None:
            timeframe = str(timeframe).strip() or None

        payload = get_metric_values(
            workspace_id=str(workspace_id),
            keys=keys,
            timeframe=timeframe,
            refresh=refresh,
        )
        return ToolResult.ok(payload)


__all__ = ["MetricsToolGroup"]
