"""
MCP three-level preference tool group — Q1 preference service (Plan C, T-C2-4).

leaf_id : COMP-MC-003 (RequirementsToolGroup sibling; own namespace)
req_id  : REQ-L2-MC-009 (direct ApplicationService access),
          Plan C / Q1 "generic three-level preference service"

Tools implemented:

  preference.registry    (read)  — the preference-key catalogue (type, default,
                                   allowed levels, combination mode, choices,
                                   editor hint); identical to the REST registry.
  preference.get         (read)  — the effective value plus its source, or one
                                   level's stored values; identical to the REST
                                   GETs.
  preference.set         (write) — the caller's *own* user-level values only.
  preference.set_default (write) — the workspace / tenant-wide default.

All four delegate to :class:`application.preference_service.PreferenceService`
(Layer 2, ADR-01) — the one facade that owns level resolution and the write
gates. No handler touches ``PreferenceValue`` itself. ``preference.registry``
reads the code registry (``application.preference_registry``), the same source
the REST registry view serialises; it is metadata with no DB access.

Why the write split (``set`` vs ``set_default``)
------------------------------------------------
The user level is self-service; a workspace/global default is governance
configuration (ENT-C3 = B, symmetric with the REST views). Keeping them in one
tool would leave the tier decision to the handler, which is exactly the class of
hole reported as R6 for ``tree_display_config.set``. Instead
``preference.set_default`` is named in ``_GOVERNANCE_TOOL_NAMES`` (ADMIN tier,
``Operation.WORKSPACE_CONFIG``) and the service re-asserts the RBAC rule per
level (workspace config / admin role) — the tier gate can only narrow further.

Read scoping (``mcp_server/workspace_scope.py``):

  * ``preference.registry`` is pure catalogue metadata (no workspace, no DB
    access) — ``TENANT_SCOPED_READ_TOOLS``.
  * ``preference.get`` without a ``workspace_id`` reads only the caller's own
    values (keyed by ``ctx.user_id``) and the tenant-wide default, neither of
    which is workspace data — also ``TENANT_SCOPED_READ_TOOLS``. When a
    ``workspace_id`` *is* supplied the dispatcher narrows the caller's roles to
    that workspace and runs the read gate (the parameter is the target
    workspace, so ``_TOOL_TARGETS`` needs no entry), exactly like
    ``tree_display_config.get``.
"""
from __future__ import annotations

from typing import Any

from application.preference_registry import all_preference_keys
from application.preference_service import (
    LEVEL_GLOBAL,
    LEVEL_USER,
    LEVEL_WORKSPACE,
    PreferenceService,
)
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    reject_unknown_params,
)
from persistence.errors import PermissionDeniedError, ValidationError

#: Scopes ``preference.get`` may resolve. ``effective`` walks user → workspace →
#: global → default; the other three answer one stored level. Ordered as the
#: contract documents it (highest precedence first).
_READ_SCOPES: tuple[str, ...] = (
    "effective",
    LEVEL_USER,
    LEVEL_WORKSPACE,
    LEVEL_GLOBAL,
)

#: Scopes ``preference.set_default`` may write. The user level is deliberately
#: absent: it has its own tool (``preference.set``), so its self-service gate
#: never has to share a schema with the governance one.
_DEFAULT_SCOPES: tuple[str, ...] = (LEVEL_WORKSPACE, LEVEL_GLOBAL)

#: JSON-schema fragment for the ``values`` object of both write tools. Values
#: are typed per key by the registry (the single source of truth), so the schema
#: deliberately does not enumerate them; ``null`` per key resets that level.
_VALUES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Object mapping preference keys to values (see preference.registry). "
        "A null value resets that key at this level (inherit from below)."
    ),
}


def _parse_keys(raw: Any) -> list[str] | None:
    """Normalise ``keys`` to a list of strings, or ``None`` for "all keys".

    Accepts the two shapes a client naturally sends — an array or a
    comma-separated string — like ``metrics.get`` does. An empty value means
    "no filter".
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()] or None
    if isinstance(raw, (list, tuple)):
        keys: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ParameterError("Parameter 'keys' must be an array of strings.")
            stripped = item.strip()
            if stripped:
                keys.append(stripped)
        return keys or None
    raise ParameterError(
        "Parameter 'keys' must be an array of strings or a comma-separated string."
    )


def _parse_values(raw: Any) -> dict[str, Any]:
    """Return the ``values`` payload as a dict, or raise a parameter error."""
    if raw is None:
        raise ParameterError("Parameter 'values' is required.")
    if not isinstance(raw, dict):
        raise ParameterError(
            "Parameter 'values' must be an object mapping preference keys to "
            "values."
        )
    return dict(raw)


class PreferenceToolGroup(BaseToolGroup):
    """COMP-MC-003 — Q1 three-level preference MCP tool group (2 read, 2 write)."""

    _TOOL_MAP = {
        "preference.registry": "_handle_registry",
        "preference.get": "_handle_get",
        "preference.set": "_handle_set",
        "preference.set_default": "_handle_set_default",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "preference.registry",
            "description": (
                "List every registered preference key (Plan C / Q1): for each "
                "the key, value type, default, allowed levels, combination mode "
                "(override|union), choices and the generic settings editor hint. "
                "Pure catalogue metadata — identical to the REST "
                "GET /api/v1/preference-values/registry/."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "preference.get",
            "description": (
                "Read preference values. With the default scope ``effective`` "
                "it answers each key's resolved value plus the level that "
                "supplied it (user|workspace|global|default|merged) for the "
                "caller, optionally inside one workspace. Any other scope "
                "returns that level's *stored* values only (an absent key means "
                "'inherit', never 'empty'). Identical to the REST "
                "GET .../preference-values/effective/ and level routes."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": list(_READ_SCOPES),
                        "description": (
                            "effective | user | workspace | global. "
                            "Default: effective."
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace. Required for scope "
                            "'workspace'; for scope 'effective' it includes the "
                            "workspace level. Omit for the account-wide view "
                            "(user + global only)."
                        ),
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Preference keys to answer (see preference.registry). "
                            "Omit for every registered key for the effective "
                            "scope, or every key set at that level otherwise."
                        ),
                    },
                },
            },
        },
        {
            "name": "preference.set",
            "description": (
                "Store (or reset) the caller's OWN user-level preference values. "
                "``values`` maps preference keys to values; ``null`` resets a "
                "key at that level. Self-service: no user or workspace id is "
                "accepted — the caller's credential is the whole boundary. A "
                "workspace- or tenant-wide default is a governance write and "
                "lives on preference.set_default. Identical to the REST "
                "PATCH /api/v1/users/me/preference-values/."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"values": _VALUES_SCHEMA},
                "required": ["values"],
            },
        },
        {
            "name": "preference.set_default",
            "description": (
                "Store (or reset) a workspace or tenant-wide preference default "
                "(ADMIN-tier governance write). ``scope='workspace'`` requires "
                "``workspace_id`` and write authority for the workspace's "
                "configuration; ``scope='global'`` requires the admin role. "
                "``values`` maps preference keys to values; ``null`` resets a "
                "key at that level. Identical to the REST PATCH "
                "/api/v1/workspaces/<id>/preference-values/ and "
                "/api/v1/system/preference-values/."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": list(_DEFAULT_SCOPES),
                        "description": "workspace | global.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace; required for scope "
                            "'workspace' and not accepted for scope 'global'."
                        ),
                    },
                    "values": _VALUES_SCHEMA,
                },
                "required": ["scope", "values"],
            },
        },
    ]

    def _service(self) -> PreferenceService:
        return PreferenceService()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _handle_registry(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """preference.registry — the preference-key catalogue."""
        reject_unknown_params(
            params,
            self.schema_param_names("preference.registry"),
            "preference.registry",
        )
        entries = [
            {
                "key": spec.key,
                "type": spec.value_type,
                "choices": list(spec.choices) if spec.choices is not None else None,
                "default": spec.default,
                "levels": sorted(spec.levels),
                "mode": spec.mode,
                "ui_editor": spec.ui_editor,
            }
            for spec in all_preference_keys()
        ]
        return ToolResult.ok({"keys": entries})

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """preference.get — effective resolution or one level's stored values."""
        reject_unknown_params(
            params, self.schema_param_names("preference.get"), "preference.get"
        )
        scope = str(params.get("scope") or "effective").strip().lower()
        if scope not in _READ_SCOPES:
            raise ParameterError(
                f"Parameter 'scope' must be one of {list(_READ_SCOPES)}."
            )
        workspace_id = optional_uuid(params, "workspace_id")
        keys = _parse_keys(params.get("keys"))

        if scope == LEVEL_WORKSPACE and workspace_id is None:
            raise ParameterError(
                "Parameter 'workspace_id' is required for scope 'workspace'."
            )
        if scope in (LEVEL_USER, LEVEL_GLOBAL) and workspace_id is not None:
            raise ParameterError(
                f"Scope '{scope}' must not carry a workspace_id."
            )

        service = self._service()
        try:
            if scope == "effective":
                return ToolResult.ok(
                    service.effective(
                        auth_context, workspace_id=workspace_id, keys=keys
                    )
                )
            payload = service.get_level(
                auth_context, scope=scope, workspace_id=workspace_id
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        if keys is not None:
            # The level route answers every key set there; narrow it to the
            # requested subset so ``keys`` means the same thing on both scopes.
            wanted = set(keys)
            payload = {
                **payload,
                "values": {
                    key: value
                    for key, value in payload["values"].items()
                    if key in wanted
                },
            }
        return ToolResult.ok(payload)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _handle_set(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """preference.set — the caller's own user-level values."""
        reject_unknown_params(
            params, self.schema_param_names("preference.set"), "preference.set"
        )
        values = _parse_values(params.get("values"))

        try:
            return ToolResult.ok(
                self._service().set_level(
                    auth_context, scope=LEVEL_USER, values=values
                )
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

    def _handle_set_default(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """preference.set_default — the workspace or tenant-wide default."""
        reject_unknown_params(
            params,
            self.schema_param_names("preference.set_default"),
            "preference.set_default",
        )
        scope = str(params.get("scope") or "").strip().lower()
        if scope not in _DEFAULT_SCOPES:
            raise ParameterError(
                f"Parameter 'scope' must be one of {list(_DEFAULT_SCOPES)}."
            )
        workspace_id = optional_uuid(params, "workspace_id")
        if scope == LEVEL_WORKSPACE and workspace_id is None:
            raise ParameterError(
                "Parameter 'workspace_id' is required for scope 'workspace'."
            )
        if scope == LEVEL_GLOBAL and workspace_id is not None:
            raise ParameterError("Scope 'global' must not carry a workspace_id.")
        values = _parse_values(params.get("values"))

        try:
            return ToolResult.ok(
                self._service().set_level(
                    auth_context,
                    scope=scope,
                    values=values,
                    workspace_id=workspace_id,
                )
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))


__all__ = ["PreferenceToolGroup"]
