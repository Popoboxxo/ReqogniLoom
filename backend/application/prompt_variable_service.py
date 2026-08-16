"""COMP-AS-PV PromptVariableService — prompt variable catalog (spec §3.1).

Single entry point (ADR-01) for everything REST, MCP and the admin UI need
from the catalog: listing every variable with its per-scope state, publishing
a tenant-wide or workspace-scoped override, and dropping an override again.

The wire dict this service returns is deliberately shaped like
``SettingsService._build_slot_state``'s prompt-slot dict — same
``*_value``/``*_version``/``has_workspace_override``/``effective_*``
vocabulary — so the frontend can reuse the origin-badge pattern it already
renders for prompt slots.

``kind="data"`` rows are catalog documentation only: they list read-only and
every write path rejects them, because their values are computed by the code
that builds the render call and nothing an admin types could reach them.

req_id: REQ-L2-PT-001
leaf_id: COMP-AS-PV
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db import IntegrityError

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PROMPT_VARIABLE_KIND_DATA,
    PROMPT_VARIABLE_TYPES,
    PromptVariable,
)

from application.base import NotFoundError, ServiceBase, ValidationError
from application.prompt_variable_versioning import (
    deactivate_variable_scope,
    get_active_variable,
    list_active_variables,
    publish_new_variable_version,
)
from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    PromptVariableSpec,
    VariableTypeError,
    deserialize_variable_value,
    serialize_variable_value,
)


def _row_value(row: PromptVariable) -> Any:
    """Deserialise a row's stored value, tolerating a malformed body."""
    try:
        return deserialize_variable_value(row.var_type, row.default_value)
    except VariableTypeError:
        return row.default_value


class PromptVariableService(ServiceBase):
    """Layer-2 facade over the ``PromptVariable`` catalog."""

    @staticmethod
    def _build_state(
        name: str,
        *,
        spec: Optional[PromptVariableSpec],
        global_row: Optional[PromptVariable],
        workspace_row: Optional[PromptVariable],
    ) -> Dict[str, Any]:
        """Resolve one variable's per-scope rows into the wire representation.

        Precedence mirrors ``application.prompt_resolver.resolve_config_values``
        exactly: workspace row > tenant row > factory registry.
        """
        reference = workspace_row or global_row
        if spec is not None:
            kind = spec.kind
            var_type = spec.var_type
            description = spec.description
            factory_default = spec.default_value
        elif reference is not None:
            kind = reference.kind
            var_type = reference.var_type
            description = reference.description
            factory_default = None
        else:  # pragma: no cover — callers never build a state from nothing
            kind = PROMPT_VARIABLE_KIND_CONFIG
            var_type = "str"
            description = ""
            factory_default = None

        if workspace_row is not None:
            effective, scope = _row_value(workspace_row), "workspace"
        elif global_row is not None:
            effective, scope = _row_value(global_row), "global"
        else:
            effective, scope = factory_default, "factory"

        return {
            "name": name,
            "kind": kind,
            "var_type": var_type,
            "description": description,
            "factory_default": factory_default,
            "global_value": _row_value(global_row) if global_row else None,
            "global_version": global_row.version if global_row else None,
            "workspace_value": _row_value(workspace_row) if workspace_row else None,
            "workspace_version": workspace_row.version if workspace_row else None,
            "has_workspace_override": workspace_row is not None,
            "effective_value": effective,
            "effective_scope": scope,
            "is_editable": kind == PROMPT_VARIABLE_KIND_CONFIG,
        }

    def list_variables(
        self, ctx: AuthContext, *, workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """Return every catalog variable with its per-scope state, name-sorted.

        The result is the union of the factory registry and every name that
        already has an active row for this tenant — a ``config`` variable
        invented at runtime would otherwise be invisible to the UI that
        created it.
        """
        self._set_tenant_context(ctx)
        # One query for all active rows, resolved in memory: per-name lookups
        # would be 2 queries x variable count for a page rendering all of them.
        rows = list_active_variables(tenant_id=ctx.tenant_id)
        global_rows = {r.name: r for r in rows if r.workspace_id is None}
        workspace_rows = (
            {r.name: r for r in rows if r.workspace_id == workspace_id}
            if workspace_id is not None
            else {}
        )
        names = set(PROMPT_VARIABLE_DEFAULTS) | {r.name for r in rows}
        return [
            self._build_state(
                name,
                spec=PROMPT_VARIABLE_DEFAULTS.get(name),
                global_row=global_rows.get(name),
                workspace_row=workspace_rows.get(name),
            )
            for name in sorted(names)
        ]

    def _state(
        self, ctx: AuthContext, name: str, *, workspace_id: Optional[UUID]
    ) -> Dict[str, Any]:
        """Fetch one variable's rows and resolve them (single-name read path)."""
        return self._build_state(
            name,
            spec=PROMPT_VARIABLE_DEFAULTS.get(name),
            global_row=get_active_variable(
                tenant_id=ctx.tenant_id, name=name, workspace_id=None
            ),
            workspace_row=(
                get_active_variable(
                    tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
                )
                if workspace_id is not None
                else None
            ),
        )

    def get_variable(
        self, ctx: AuthContext, name: str, *, workspace_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Return one variable's state.

        Raises:
            NotFoundError: The name is neither factory-registered nor backed
                by an active row — a clear error instead of a silent empty
                value (spec §8).
        """
        self._set_tenant_context(ctx)
        state = self._state(ctx, name, workspace_id=workspace_id)
        if (
            name not in PROMPT_VARIABLE_DEFAULTS
            and state["global_value"] is None
            and state["workspace_value"] is None
        ):
            raise NotFoundError(f"PromptVariable {name!r} not found for this tenant.")
        return state

    def set_variable(
        self,
        ctx: AuthContext,
        *,
        name: str,
        value: Any,
        workspace_id: Optional[UUID] = None,
        var_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish a new active version of *name* for the given scope.

        Args:
            ctx:          Caller's auth context.
            name:         Variable name (open-ended — a name with no factory
                          entry creates a brand-new ``config`` variable).
            value:        Typed value; validated against the effective
                          ``var_type``.
            workspace_id: Workspace to override for, or ``None`` for the
                          tenant-wide default.
            var_type:     Type for a name that has no factory entry yet
                          (defaults to ``"str"``); ignored for known names,
                          whose type is owned by the registry.
            description:  Documentation for a new variable.

        Raises:
            ValidationError: The name is a ``data`` variable, the declared
                type is unknown, the value does not match the type, or a
                concurrent writer published for the same scope first.
        """
        self._set_tenant_context(ctx)
        spec = PROMPT_VARIABLE_DEFAULTS.get(name)
        existing = get_active_variable(
            tenant_id=ctx.tenant_id, name=name, workspace_id=None
        ) or get_active_variable(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )

        if spec is not None:
            kind = spec.kind
            effective_type = spec.var_type
            effective_description = description or spec.description
        elif existing is not None:
            kind = existing.kind
            effective_type = existing.var_type
            effective_description = (
                description if description is not None else existing.description
            )
        else:
            kind = PROMPT_VARIABLE_KIND_CONFIG
            effective_type = var_type or "str"
            effective_description = description or ""

        if kind == PROMPT_VARIABLE_KIND_DATA:
            raise ValidationError(
                f"PromptVariable {name!r} is code-bound (kind='data'); its value "
                "is computed by the system and cannot be set."
            )
        if effective_type not in PROMPT_VARIABLE_TYPES:
            raise ValidationError(
                f"Unknown var_type {effective_type!r}; expected one of "
                f"{', '.join(PROMPT_VARIABLE_TYPES)}."
            )

        serialized = serialize_variable_value(value)
        try:
            deserialize_variable_value(effective_type, serialized)
        except VariableTypeError as exc:
            raise ValidationError(str(exc)) from exc

        try:
            publish_new_variable_version(
                tenant_id=ctx.tenant_id,
                name=name,
                kind=PROMPT_VARIABLE_KIND_CONFIG,
                var_type=effective_type,
                description=effective_description,
                default_value=serialized,
                workspace_id=workspace_id,
            )
        except IntegrityError as exc:
            raise ValidationError(
                f"Could not publish a new version for {name!r}: {exc}"
            ) from exc
        return self._state(ctx, name, workspace_id=workspace_id)

    def clear_variable(
        self, ctx: AuthContext, *, name: str, workspace_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Drop *name*'s active row at the given scope (idempotent).

        Clearing a workspace scope restores the tenant default; clearing the
        tenant scope restores the factory value. Rows are deactivated, never
        deleted, so the version history stays auditable.
        """
        self._set_tenant_context(ctx)
        deactivate_variable_scope(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )
        return self._state(ctx, name, workspace_id=workspace_id)


__all__ = ["PromptVariableService"]
