"""AttributeMigrationToolGroup — MCP surface for AWMS value migrations (WS7 #940).

Spec §7's MCP contract: ``attribute_migration.plan`` is a *reading* operation
(schema validation + hash, no DB write) and therefore available to every
authenticated caller; ``apply`` / ``rollback`` / ``dry_run`` mutate (they write
the run row and, for apply/rollback, artifacts) and are fail-closed
write-gated by the registry. ``list_runs`` / ``get_run`` are plain reads of the
run history.

Tools:

  attribute_migration.plan       — validate a plan doc + return its hash (read)
  attribute_migration.dry_run    — full preview, no artifact writes (write)
  attribute_migration.apply      — execute a plan (write, admin)
  attribute_migration.rollback   — restore a run's snapshots (write, admin)
  attribute_migration.list_runs  — run history (read, admin)
  attribute_migration.get_run    — one run incl. report (read, admin)

The service additionally asserts ``admin`` on every data-touching operation, so
a non-admin gets ``PERMISSION_DENIED`` and never a silent success.

No ORM in this module (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_tools``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from auth_tenancy.context import AuthContext

from application.attribute_migration_service import (
    AttributeMigrationConflict,
    AttributeMigrationNotFound,
    AttributeMigrationService,
)
from application.base import PermissionDeniedError
from attribute_definitions.migration_plan import MigrationPlanError
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_param, require_uuid

logger = logging.getLogger(__name__)

_READ_TOOLS = {
    "attribute_migration.plan",
    "attribute_migration.list_runs",
    "attribute_migration.get_run",
}
_WRITE_TOOLS = {
    "attribute_migration.dry_run",
    "attribute_migration.apply",
    "attribute_migration.rollback",
}

_PLAN_PROPERTY = {
    "type": "object",
    "description": (
        "Declarative AWMS plan: {id, description, scope{item_type, preset, "
        "workspace}, mode, options, steps:[{op, ...}]}."
    ),
}


class AttributeMigrationToolGroup(BaseToolGroup):
    """AWMS migration tool group (3 read + 3 write tools)."""

    _TOOL_MAP = {
        "attribute_migration.plan": "_handle_plan",
        "attribute_migration.dry_run": "_handle_dry_run",
        "attribute_migration.apply": "_handle_apply",
        "attribute_migration.rollback": "_handle_rollback",
        "attribute_migration.list_runs": "_handle_list_runs",
        "attribute_migration.get_run": "_handle_get_run",
    }

    @staticmethod
    def _get_service() -> AttributeMigrationService:
        return AttributeMigrationService()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "attribute_migration.plan",
                "description": (
                    "Validate an AWMS plan document and return its normalized "
                    "form + SHA-256 hash. No database write."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"plan": _PLAN_PROPERTY},
                    "required": ["plan"],
                },
            },
            {
                "name": "attribute_migration.dry_run",
                "description": (
                    "Plan a migration against real data and return the full "
                    "change report without modifying artifacts (admin-only)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"plan": _PLAN_PROPERTY},
                    "required": ["plan"],
                },
            },
            {
                "name": "attribute_migration.apply",
                "description": (
                    "Execute an AWMS plan: snapshot, migrate values, audit "
                    "(admin-only)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"plan": _PLAN_PROPERTY},
                    "required": ["plan"],
                },
            },
            {
                "name": "attribute_migration.rollback",
                "description": "Restore every artifact of a previous apply run (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "Run UUID."},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "attribute_migration.list_runs",
                "description": "List AWMS runs of the tenant, newest first (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "plan_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["dry_run", "apply"]},
                        "status": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                    "required": [],
                },
            },
            {
                "name": "attribute_migration.get_run",
                "description": "Return one AWMS run including its stored report (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "Run UUID."},
                    },
                    "required": ["run_id"],
                },
            },
        ]

    # ---- Handlers ---------------------------------------------------------

    @staticmethod
    def _plan_param(params: Dict[str, Any]) -> Dict[str, Any]:
        plan = params.get("plan")
        if not isinstance(plan, dict):
            raise MigrationPlanError(["Parameter 'plan' must be an object."])
        return plan

    def _handle_plan(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            result = self._get_service().validate_plan(self._plan_param(params))
        except MigrationPlanError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok(result)

    def _handle_dry_run(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            report = self._get_service().dry_run(auth_context, self._plan_param(params))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except MigrationPlanError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except AttributeMigrationConflict as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok({"report": report})

    def _handle_apply(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            report = self._get_service().apply(auth_context, self._plan_param(params))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except MigrationPlanError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except AttributeMigrationConflict as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok({"report": report})

    def _handle_rollback(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        run_id = require_uuid(params, "run_id")
        try:
            result = self._get_service().rollback(auth_context, run_id)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeMigrationNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except MigrationPlanError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok(result)

    def _handle_list_runs(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            runs = self._get_service().list_runs(
                auth_context,
                plan_id=params.get("plan_id") or None,
                mode=params.get("mode") or None,
                status=params.get("status") or None,
                limit=int(params.get("limit", 50)),
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (TypeError, ValueError):
            return ToolResult.error("VALIDATION_ERROR", "'limit' must be an integer.")
        return ToolResult.ok({"runs": runs, "count": len(runs)})

    def _handle_get_run(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        run_id = require_param(params, "run_id")
        try:
            run = self._get_service().get_run(auth_context, run_id)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeMigrationNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"run": run})


__all__ = ["AttributeMigrationToolGroup"]
