"""WorkflowDefaultToolGroup — MCP access to the tenant-wide workflow defaults.

Nine tools over :class:`application.workflow_facade.WorkflowFacade`, the same
Layer-2 facade the REST surface (``rest_api.global_default_views``) calls
(ADR-01, P1.8/M-11). Every tool is **tenant-wide admin configuration**: the
global workflow default is the template a workspace's non-customized
definition inherits, so a mutation reaches every workspace still on the default
— not one workspace's resource. Each handler therefore re-asserts
``auth_context.has_role("admin")``, mirroring the REST ``_require_admin`` gate;
no ``workspace_id`` exists or is accepted.

Reads:

  workflow_default.list             — every global definition of the tenant
                                      (``GET /api/v1/workflow-defaults/``)
  workflow_default.get              — one ``(item_type, preset)`` graph, or the
                                      empty graph for an uninitialised pair
                                      (``GET /api/v1/workflow-defaults/{item_type}/{preset}/``)

Writes:

  workflow_default.initialize       — create the empty global graph
                                      (``POST …/initialize/``)
  workflow_default.add_state        — append a state (``POST …/states/``)
  workflow_default.update_state     — rename and/or toggle ``freeze_on_enter``
                                      (``PATCH …/states/{state}/``)
  workflow_default.delete_state     — remove a state (``DELETE …/states/{state}/``)
  workflow_default.add_transition   — append a transition
                                      (``POST …/transitions/``)
  workflow_default.update_transition — update role/gate flags of one transition
                                      (``PATCH …/transitions/{from}__{to}/``)
  workflow_default.delete_transition — remove a transition
                                      (``DELETE …/transitions/{from}__{to}/``)

The graph payload is built by the *same* module-level helper the REST view
delegates to (:func:`application.workflow_facade.global_graph_payload`), so the
two transports cannot drift into two graph shapes. The helper returns the row's
``modified_at`` datetime, which stdlib ``json.dumps`` cannot encode — the shared
transport-boundary helper :func:`mcp_server.tools.base.transport_safe` renders it
as an ISO string exactly as DRF's JSONRenderer does for REST.

Every tool requires an **unfenced** ADMIN-tier API key: the call names no
workspace, and an API key fenced to specific workspaces is denied (the same
fail-closed rule REST applies to its workspace fence). The role gate is the
handler's own ``has_role("admin")`` check, mirrored from REST's
``_require_admin``.

No ORM in this module (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_tools``).
"""
from __future__ import annotations

import logging
from typing import Any

from application.base import OptimisticLockError
from application.workflow_facade import WorkflowFacade, global_graph_payload
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_ADMIN
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, transport_safe
from persistence.errors import NotFoundError, PermissionDeniedError
from workflow.services import (
    OrphanedStateError,
    StateReferencedError,
    WorkflowDefinitionError,
)

logger = logging.getLogger(__name__)

#: ``workflow.models.GlobalWorkflowDefinition.preset`` is ``max_length=32``. A
#: longer value used to reach the column and surface as a masked
#: ``INTERNAL_ERROR``; it is a caller error, so it is answered as one here.
_MAX_PRESET_LENGTH = 32

#: Appended to every tool description: whose key may call these tools at all.
_ADMIN_TIER_NOTE = (
    " Requires an unfenced ADMIN-tier API key: a key fenced to specific "
    "workspaces is denied because this call names no workspace (the same "
    "fail-closed rule as REST's workspace fence)."
)

_ITEM_TYPE_PROP = {
    "item_type": {
        "type": "string",
        "description": (
            "Workflow item type, e.g. 'Document', 'Requirement' or 'Adr' "
            "(the canonical registry is workflow.item_types."
            "KNOWN_WORKFLOW_ITEM_TYPES)."
        ),
    }
}
_PRESET_PROP = {
    "preset": {
        "type": "string",
        "description": (
            "Preset key the definition is keyed by, e.g. 'ccb_approval', "
            "'extended' or 'document_default' (at most 32 characters — the "
            "store's column width)."
        ),
    }
}
_STATE_PROP = {
    "state": {
        "type": "string",
        "description": "Name of the state the call acts on.",
    }
}
_TRANSITION_PROPS = {
    "from_state": {"type": "string", "description": "Source state of the transition."},
    "to_state": {"type": "string", "description": "Target state of the transition."},
}
_TRANSITION_WRITE_PROPS = {
    "allowed_roles": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Roles allowed to take the transition. The store always keeps "
            "'admin'; an empty list therefore stores ['admin']."
        ),
    },
    "requires_change_reason": {
        "type": "boolean",
        "description": "Require a change reason on this transition.",
    },
    "signature_gate": {
        "type": "boolean",
        "description": "Require a signature credential on this transition.",
    },
}


class WorkflowDefaultToolGroup(BaseToolGroup):
    """Nine tools over the tenant-wide global workflow defaults (2 read, 7 write)."""

    _TOOL_MAP = {
        "workflow_default.list": "_handle_list",
        "workflow_default.get": "_handle_get",
        "workflow_default.initialize": "_handle_initialize",
        "workflow_default.add_state": "_handle_add_state",
        "workflow_default.update_state": "_handle_update_state",
        "workflow_default.delete_state": "_handle_delete_state",
        "workflow_default.add_transition": "_handle_add_transition",
        "workflow_default.update_transition": "_handle_update_transition",
        "workflow_default.delete_transition": "_handle_delete_transition",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "workflow_default.list",
            "description": (
                "List the tenant-wide global workflow defaults (read-only, "
                "admin only). This is tenant-wide admin configuration, not a "
                "workspace resource: each row is the template non-customized "
                "workspace definitions inherit. Mirrors "
                "GET /api/v1/workflow-defaults/. Both filters are optional "
                "exact matches."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_type": _ITEM_TYPE_PROP["item_type"],
                    "preset": _PRESET_PROP["preset"],
                },
            },
        },
        {
            "name": "workflow_default.get",
            "description": (
                "Read one tenant-wide global workflow default (read-only, admin "
                "only). Tenant-wide admin configuration, not a workspace "
                "resource. Mirrors "
                "GET /api/v1/workflow-defaults/{item_type}/{preset}/. An "
                "uninitialised pair answers the empty graph with "
                "initialized=false — that is not an error; an unknown "
                "item_type is NOT_FOUND."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_ITEM_TYPE_PROP, **_PRESET_PROP},
                "required": ["item_type", "preset"],
            },
        },
        {
            "name": "workflow_default.initialize",
            "description": (
                "Create the empty global workflow default for one "
                "(item_type, preset) pair (write, admin only). Tenant-wide "
                "admin configuration: the row is the template every "
                "non-customized workspace definition of that preset inherits. "
                "Mirrors POST /api/v1/workflow-defaults/{item_type}/{preset}/"
                "initialize/. A pair that already has a definition answers "
                "CONFLICT."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_ITEM_TYPE_PROP, **_PRESET_PROP},
                "required": ["item_type", "preset"],
            },
        },
        {
            "name": "workflow_default.add_state",
            "description": (
                "Append a state to the global workflow default (write, admin "
                "only). Tenant-wide admin configuration: the change propagates "
                "into every workspace definition still on the default. Mirrors "
                "POST /api/v1/workflow-defaults/{item_type}/{preset}/states/. "
                "A duplicate state name is VALIDATION_ERROR."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **_ITEM_TYPE_PROP,
                    **_PRESET_PROP,
                    "name": {"type": "string", "description": "New state name."},
                },
                "required": ["item_type", "preset", "name"],
            },
        },
        {
            "name": "workflow_default.update_state",
            "description": (
                "Rename a state and/or toggle its freeze_on_enter flag on the "
                "global workflow default (write, admin only). Tenant-wide admin "
                "configuration, propagated to every workspace on the default. "
                "Mirrors PATCH "
                "/api/v1/workflow-defaults/{item_type}/{preset}/states/{state}/ "
                "— at least one of new_name / freeze_on_enter is required, and "
                "both may be sent in one call."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **_ITEM_TYPE_PROP,
                    **_PRESET_PROP,
                    **_STATE_PROP,
                    "new_name": {
                        "type": "string",
                        "description": "Rename the state to this name.",
                    },
                    "freeze_on_enter": {
                        "type": ["boolean", "null"],
                        "description": (
                            "Set or clear the freeze-on-enter flag of the "
                            "state (a rename applies first)."
                        ),
                    },
                },
                "required": ["item_type", "preset", "state"],
            },
        },
        {
            "name": "workflow_default.delete_state",
            "description": (
                "Remove a state from the global workflow default (write, admin "
                "only). Tenant-wide admin configuration, propagated to every "
                "workspace on the default. Mirrors DELETE "
                "/api/v1/workflow-defaults/{item_type}/{preset}/states/{state}/. "
                "A state a transition references, or one a live item still "
                "occupies in an inheriting workspace, answers CONFLICT."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_ITEM_TYPE_PROP, **_PRESET_PROP, **_STATE_PROP},
                "required": ["item_type", "preset", "state"],
            },
        },
        {
            "name": "workflow_default.add_transition",
            "description": (
                "Append a transition to the global workflow default (write, "
                "admin only). Tenant-wide admin configuration, propagated to "
                "every workspace on the default. Mirrors POST "
                "/api/v1/workflow-defaults/{item_type}/{preset}/transitions/. "
                "'admin' is always kept in allowed_roles; an unknown state or a "
                "duplicate edge is VALIDATION_ERROR."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **_ITEM_TYPE_PROP,
                    **_PRESET_PROP,
                    **_TRANSITION_PROPS,
                    **_TRANSITION_WRITE_PROPS,
                },
                "required": ["item_type", "preset", "from_state", "to_state"],
            },
        },
        {
            "name": "workflow_default.update_transition",
            "description": (
                "Update the role/gate flags of one transition of the global "
                "workflow default (write, admin only). Tenant-wide admin "
                "configuration, propagated to every workspace on the default. "
                "Mirrors PATCH "
                "/api/v1/workflow-defaults/{item_type}/{preset}/transitions/"
                "{from_state}__{to_state}/. Omitted keys keep their stored "
                "value (the REST handler passes them through unchanged)."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **_ITEM_TYPE_PROP,
                    **_PRESET_PROP,
                    **_TRANSITION_PROPS,
                    "allowed_roles": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "New allowed-role list; 'admin' is always kept. "
                            "Omit to keep the stored roles."
                        ),
                    },
                    "requires_change_reason": {
                        "type": ["boolean", "null"],
                        "description": "New change-reason flag; omit to keep it.",
                    },
                    "signature_gate": {
                        "type": ["boolean", "null"],
                        "description": "New signature-gate flag; omit to keep it.",
                    },
                },
                "required": ["item_type", "preset", "from_state", "to_state"],
            },
        },
        {
            "name": "workflow_default.delete_transition",
            "description": (
                "Remove a transition from the global workflow default (write, "
                "admin only). Tenant-wide admin configuration, propagated to "
                "every workspace on the default. Mirrors DELETE "
                "/api/v1/workflow-defaults/{item_type}/{preset}/transitions/"
                "{from_state}__{to_state}/. An unknown edge is "
                "VALIDATION_ERROR."
                + _ADMIN_TIER_NOTE
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **_ITEM_TYPE_PROP,
                    **_PRESET_PROP,
                    **_TRANSITION_PROPS,
                },
                "required": ["item_type", "preset", "from_state", "to_state"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _facade() -> WorkflowFacade:
        return WorkflowFacade()

    @staticmethod
    def _admin_denied(auth_context: AuthContext) -> ToolResult | None:
        """Return a ``PERMISSION_DENIED`` result unless the caller is admin.

        Mirrors ``rest_api.global_default_views._require_admin``: the global
        default is tenant-wide configuration, so the role gate is explicit in
        the handler (the dispatcher's RBAC matrix cannot express it for a call
        that names no workspace).
        """
        if auth_context.has_role(ROLE_ADMIN):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED", "Admin role required for global workflow defaults."
        )

    @staticmethod
    def _unknown_item_type(item_type: str) -> ToolResult | None:
        """R-F2-2: an unknown ``item_type`` is NOT_FOUND, not an empty graph.

        Same rule and same known set as REST's ``_unknown_item_type``
        (``workflow.item_types.KNOWN_WORKFLOW_ITEM_TYPES``).
        """
        from workflow.item_types import KNOWN_WORKFLOW_ITEM_TYPES

        if item_type in KNOWN_WORKFLOW_ITEM_TYPES:
            return None
        return ToolResult.error(
            "NOT_FOUND", f"Unknown workflow item type: {item_type!r}"
        )

    @staticmethod
    def _preset_too_long(preset: str) -> ToolResult | None:
        """Reject a preset key wider than the store's column before any query."""
        if len(preset) <= _MAX_PRESET_LENGTH:
            return None
        return ToolResult.error(
            "VALIDATION_ERROR",
            f"preset must be at most {_MAX_PRESET_LENGTH} characters (the "
            f"store's column width); got {len(preset)}.",
        )

    @staticmethod
    def _roles_error(value: Any) -> ToolResult | None:
        """Validate a caller-supplied ``allowed_roles`` value before the facade.

        The store iterates the list as strings; a non-string item used to raise
        ``AttributeError`` there and surface as a masked ``INTERNAL_ERROR``. A
        wrongly shaped value is a caller error, so it is answered as one.
        """
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(role, str) for role in value
        ):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "allowed_roles must be a list of role strings.",
            )
        return None

    def _scope(
        self,
        params: dict[str, Any],
        auth_context: AuthContext,
        tool_name: str,
        *,
        require_item_type: bool = True,
    ) -> tuple[str | None, str | None] | ToolResult:
        """Run the prelude every handler shares.

        Admin gate -> ``item_type``/``preset`` presence -> known ``item_type``
        -> preset width. Returns ``(item_type, preset)`` on success, or the
        ``ToolResult`` to return verbatim. The per-tool name stays in the
        validation message so a caller can tell which tool rejected the call.

        ``require_item_type=False`` is for ``workflow_default.list``, whose two
        parameters are optional exact-match filters rather than a scope — its
        behaviour is exactly the admin gate plus the two text lookups.
        """
        denied = self._admin_denied(auth_context)
        if denied is not None:
            return denied
        item_type = self._text(params, "item_type")
        preset = self._text(params, "preset")
        if require_item_type:
            if not item_type or not preset:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameters 'item_type' and 'preset' are required for "
                    f"{tool_name}.",
                )
            unknown = self._unknown_item_type(item_type)
            if unknown is not None:
                return unknown
            too_long = self._preset_too_long(preset)
            if too_long is not None:
                return too_long
        return item_type, preset

    @staticmethod
    def _guard(func) -> ToolResult:
        """Run a facade call, mapping workflow/domain errors onto ToolResult codes.

        Deliberately local (no import of ``rest_api._map_workflow_error``):
        ``mcp_server`` must not depend on the REST layer. The mapping itself is
        the same one REST publishes:

        * ``OrphanedStateError`` / ``StateReferencedError`` -> ``CONFLICT``
          (both subclass ``WorkflowDefinitionError``, so they are matched first);
        * any other ``WorkflowDefinitionError`` -> ``CONFLICT`` for "already
          initialized", else ``VALIDATION_ERROR``;
        * ``PermissionDeniedError`` -> ``PERMISSION_DENIED``,
          ``NotFoundError`` -> ``NOT_FOUND``, ``OptimisticLockError`` ->
          ``CONFLICT``;
        * anything else is logged and masked (CWE-209). Parameters and values
          are never logged — the message names only the failure class.
        """
        try:
            return ToolResult.ok(func())
        except (OrphanedStateError, StateReferencedError) as exc:
            return ToolResult.error("CONFLICT", str(exc))
        except WorkflowDefinitionError as exc:
            message = str(exc)
            if "already initialized" in message:
                return ToolResult.error("CONFLICT", message)
            return ToolResult.error("VALIDATION_ERROR", message)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except Exception:  # noqa: BLE001 — transport boundary
            logger.exception("workflow_default tool failed")
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

    @staticmethod
    def _text(params: dict[str, Any], name: str) -> str | None:
        """Return a stripped string parameter, or ``None`` when absent/empty."""
        value = (params or {}).get(name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _payload(
        obj: Any,
        *,
        auth_context: AuthContext,
        item_type: str,
        preset: str,
        propagated: int | None = None,
    ) -> dict[str, Any]:
        """Render one definition through the shared helper, transport-safe."""
        return transport_safe(
            global_graph_payload(
                obj,
                tenant_id=auth_context.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=propagated,
            )
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(
            params, auth_context, "workflow_default.list", require_item_type=False
        )
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope

        def _run():
            rows = self._facade().list_global_definitions(
                auth_context, item_type=item_type, preset=preset
            )
            return {
                "workflow_defaults": [
                    self._payload(
                        row,
                        auth_context=auth_context,
                        item_type=row.item_type,
                        preset=row.preset,
                    )
                    for row in rows
                ]
            }

        return self._guard(_run)

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.get")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope

        def _run():
            obj = self._facade().get_global_definition(
                auth_context, item_type=item_type, preset=preset
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                )
            }

        return self._guard(_run)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _handle_initialize(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.initialize")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope

        def _run():
            obj = self._facade().initialize_global_definition(
                auth_context, item_type=item_type, preset=preset
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                )
            }

        return self._guard(_run)

    def _handle_add_state(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.add_state")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        name = self._text(params, "name")
        if not name:
            return ToolResult.error("VALIDATION_ERROR", "name is required")

        def _run():
            obj, count = self._facade().add_global_state(
                auth_context, item_type=item_type, preset=preset, name=name
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)

    def _handle_update_state(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.update_state")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        state = self._text(params, "state")
        if not state:
            return ToolResult.error("VALIDATION_ERROR", "state is required")
        new_name = self._text(params, "new_name")
        # Mirrors REST: presence of the key (even null) means "set the flag";
        # the stored flag is boolean, so a null reads as False (clear).
        freeze_given = "freeze_on_enter" in (params or {})
        if not new_name and not freeze_given:
            return ToolResult.error(
                "VALIDATION_ERROR", "new_name or freeze_on_enter is required"
            )

        def _run():
            target = state
            obj = None
            count = None
            if new_name:
                obj, count = self._facade().rename_global_state(
                    auth_context,
                    item_type=item_type,
                    preset=preset,
                    old_name=state,
                    new_name=new_name,
                )
                target = new_name
            if freeze_given:
                obj, count = self._facade().set_global_state_freeze(
                    auth_context,
                    item_type=item_type,
                    preset=preset,
                    state=target,
                    freeze=bool((params or {}).get("freeze_on_enter")),
                )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)

    def _handle_delete_state(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.delete_state")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        state = self._text(params, "state")
        if not state:
            return ToolResult.error("VALIDATION_ERROR", "state is required")

        def _run():
            obj, count = self._facade().delete_global_state(
                auth_context, item_type=item_type, preset=preset, name=state
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)

    def _handle_add_transition(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.add_transition")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        from_state = self._text(params, "from_state")
        to_state = self._text(params, "to_state")
        if not from_state or not to_state:
            return ToolResult.error(
                "VALIDATION_ERROR", "from_state and to_state are required"
            )
        allowed_roles = (params or {}).get("allowed_roles")
        roles_error = self._roles_error(allowed_roles)
        if roles_error is not None:
            return roles_error

        def _run():
            obj, count = self._facade().add_global_transition(
                auth_context,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
                allowed_roles=allowed_roles,
                requires_change_reason=bool(
                    (params or {}).get("requires_change_reason", False)
                ),
                signature_gate=bool((params or {}).get("signature_gate", False)),
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)

    def _handle_update_transition(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.update_transition")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        from_state = self._text(params, "from_state")
        to_state = self._text(params, "to_state")
        if not from_state or not to_state:
            return ToolResult.error(
                "VALIDATION_ERROR", "from_state and to_state are required"
            )
        allowed_roles = (params or {}).get("allowed_roles")
        roles_error = self._roles_error(allowed_roles)
        if roles_error is not None:
            return roles_error

        def _run():
            # Same pass-through shape as the REST PATCH handler: a key the
            # caller omitted arrives as ``None`` and the store leaves the
            # stored value alone. Both transports therefore behave identically
            # (verified against rest_api.global_default_views).
            obj, count = self._facade().update_global_transition(
                auth_context,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
                allowed_roles=allowed_roles,
                requires_change_reason=(params or {}).get("requires_change_reason"),
                signature_gate=(params or {}).get("signature_gate"),
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)

    def _handle_delete_transition(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        scope = self._scope(params, auth_context, "workflow_default.delete_transition")
        if isinstance(scope, ToolResult):
            return scope
        item_type, preset = scope
        from_state = self._text(params, "from_state")
        to_state = self._text(params, "to_state")
        if not from_state or not to_state:
            return ToolResult.error(
                "VALIDATION_ERROR", "from_state and to_state are required"
            )

        def _run():
            obj, count = self._facade().delete_global_transition(
                auth_context,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
            )
            return {
                "workflow_default": self._payload(
                    obj,
                    auth_context=auth_context,
                    item_type=item_type,
                    preset=preset,
                    propagated=count,
                )
            }

        return self._guard(_run)


__all__ = ["WorkflowDefaultToolGroup"]
