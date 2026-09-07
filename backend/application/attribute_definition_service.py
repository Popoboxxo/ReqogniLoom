"""COMP-AS-ATD AttributeDefinitionService — the single facade for attribute
definitions (spec sections 5, 7 and 9).

ADR-01: REST views, MCP tools, the interview protocol and the export service all
go through this class; none of them touches ``attribute_definitions.models``.

Permission model, deliberately asymmetric:
  * **reads of the resolved definition** (``resolve``, ``elicit_attributes``,
    ``export_attributes``, ``validate_artifact_fields``) are open to any
    authenticated tenant member — applying a configuration to your own data is
    exactly what a non-admin needs it for. Gating them on ``admin`` would make
    the configured form unusable by the users it constrains (the same reasoning
    the removed ``AttributeVisibilityConfigService.hidden_attribute_names``
    carried).
  * **management** (``list_global``, ``get_global``, ``update_global``,
    ``update_workspace``, ``reset_workspace``) requires ``admin``.

Audit: every mutation writes ``AuditEntry.OP_UPDATE``. No new ``op`` choice is
introduced on purpose — an undeclared ``operation=`` string fails ``full_clean``
and 500s the whole transaction *after* the mutation succeeded (issue #265).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db import transaction

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.schema import (
    AttributeDefinitionConflictError,
    AttributeSchemaError,
    stored_attributes,
)
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext

from application.base import ServiceBase
from application.cache_invalidation import (
    attribute_def_cache_key,
    invalidate_workspace_caches,
)

#: Resolved definitions are read on every form load; 10 minutes is long enough
#: to matter and short enough that a missed invalidation self-heals.
_CACHE_TTL_SECONDS = 600


class AttributeDefinitionService(ServiceBase):
    """Read, manage and apply attribute definitions."""

    def __init__(
        self,
        global_store: GlobalAttributeDefinitionStore | None = None,
        workspace_store: WorkspaceAttributeDefinitionStore | None = None,
    ) -> None:
        self._global = global_store or GlobalAttributeDefinitionStore()
        self._workspace = workspace_store or WorkspaceAttributeDefinitionStore()

    # ---- Helpers ----------------------------------------------------------

    @staticmethod
    def _workspace_preset(workspace_id: UUID) -> str:
        """Resolve the workspace's rigor tier through the preset gate.

        Raises:
            AttributeDefinitionNotFound: *workspace_id* names no workspace at
                all, or is not a well-formed workspace id.
                ``presets.gate._resolve_workspace_tenant`` deliberately lets
                ``Workspace.DoesNotExist`` propagate as a documented,
                pre-existing contract ("callers must let this propagate") —
                but ``resolve()`` below is reachable from a REST GET carrying
                a raw, caller-supplied workspace id in the URL path (Task 10),
                so this is the one call site that must translate it into the
                error the view already maps to 404, instead of a 500. Same
                trap as issue #398 (``BaselineViewSet`` / preset gate).

                A *malformed* id is folded into the same answer on purpose: the
                lookup raises Django's ``ValidationError`` rather than
                ``DoesNotExist`` for it, which is in neither ``_EXC_TO_HTTP``
                nor any handler's except-list, so it surfaced as a 500 for what
                is simply "no such workspace" (issue #271's error-asymmetry
                class). Every caller of ``resolve()`` — including the artifact
                ViewSets since Task 11, whose workspace id comes straight off a
                request body — is guarded by this one translation.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        from persistence.models import Workspace
        from presets.services import get_preset

        try:
            return get_preset(str(workspace_id)).preset
        except (Workspace.DoesNotExist, DjangoValidationError, ValueError) as exc:
            raise AttributeDefinitionNotFound(
                f"No workspace '{workspace_id}' in the active tenant"
            ) from exc

    @staticmethod
    def _attributes(row: Any) -> list[dict[str, Any]]:
        """Normalized attribute list of a stored row.

        Ledger item (e): this is the single seam BOTH facade read paths go
        through — ``_workspace_payload`` (``resolve`` → ``elicit_attributes``
        indexes ``a["ai_elicit"]``/``a["visible"]``, ``export_attributes``
        indexes ``a["export"]``, ``validate_artifact_fields`` indexes
        ``a["kind"]``/``a["required"]``/``a["options"]``/``a["validation"]``)
        and ``_global_payload`` (the admin list/detail responses, and the
        preset-downgrade comparison). A row missing any of those keys — written
        before the key existed, restored from an older backup, hand-edited —
        used to surface as a bare ``KeyError`` 500 far from its cause; it now
        raises ``AttributeSchemaError``, which every caller maps to a 400
        naming the offending attribute.
        """
        return stored_attributes(row.definition_json)

    def _workspace_payload(self, row: Any) -> dict[str, Any]:
        return {
            "item_type": row.item_type,
            "preset": row.preset,
            "is_customized": row.is_customized,
            "version": row.version,
            "attributes": self._attributes(row),
        }

    def _global_payload(
        self, item_type: str, preset: str, row: Any, *, propagated: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "item_type": item_type,
            "preset": preset,
            "initialized": row is not None,
            "version": row.version if row is not None else 0,
            "attributes": self._attributes(row) if row is not None else [],
        }
        if propagated is not None:
            payload["propagated_workspace_count"] = propagated
        return payload

    # ---- Read -------------------------------------------------------------

    def resolve(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Return the resolved (materialized) definition for the workspace.

        Cached per workspace under ``reqogniloom:attribute-def:{workspace_id}``;
        the entry is dropped by ``invalidate_workspace_caches`` on every write.

        Raises:
            AttributeDefinitionNotFound: no global default for the workspace's
                preset — the bootstrap command has not been run.
        """
        self._set_tenant_context(ctx)
        # SA-15: the workspace-ownership guard must run *before* the cache
        # read. ``attribute_def_cache_key`` is keyed by workspace alone, so a
        # warm entry would otherwise serve a cross-tenant caller a 200 with
        # another tenant's definition, without ever touching a guarded path —
        # the exact trap ``presets.gate.FeatureGateService.get_preset`` already
        # documents and avoids for its own ``_tier_cache``. Costs nothing on a
        # warm process: ``get_preset`` is itself in-process cached, and the
        # ownership lookup is memoised in ``gate._workspace_tenant_cache``.
        preset = self._workspace_preset(workspace_id)
        cache_key = attribute_def_cache_key(str(workspace_id))
        cached = cache.get(cache_key) or {}
        if item_type in cached:
            return cached[item_type]

        row = self._workspace.resolve(ctx.tenant_id, workspace_id, item_type, preset)
        payload = self._workspace_payload(row)
        cached[item_type] = payload
        cache.set(cache_key, cached, _CACHE_TTL_SECONDS)
        return payload

    def list_global(
        self,
        ctx: AuthContext,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return every tenant-wide global default, optionally filtered."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        rows = self._global.list(ctx.tenant_id, item_type=item_type, preset=preset)
        return [self._global_payload(r.item_type, r.preset, r) for r in rows]

    def get_global(
        self, ctx: AuthContext, item_type: str, preset: str
    ) -> dict[str, Any]:
        """Return one global default, or an ``initialized: False`` stub.

        Never 404s on a missing row so the UI can offer an "Initialize"
        affordance — same contract as ``workflow-defaults/``.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        row = self._global.get(ctx.tenant_id, item_type, preset)
        return self._global_payload(item_type, preset, row)

    def elicit_attributes(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Attributes the interview must ask for (``ai_elicit=true``).

        Order is the resolved definition's order, i.e. section order first —
        which is what the interview protocol uses as its phase order
        (spec section 7).
        """
        return [
            a
            for a in self.resolve(ctx, item_type, workspace_id)["attributes"]
            if a["ai_elicit"] and a["visible"]
        ]

    def export_attributes(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Attributes ReqIF / CSV / Bundle export must carry (``export=true``)."""
        return [
            a
            for a in self.resolve(ctx, item_type, workspace_id)["attributes"]
            if a["export"]
        ]

    # ---- Write ------------------------------------------------------------

    def update_global(
        self,
        ctx: AuthContext,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Replace the tenant-wide default and propagate to on-default workspaces.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeDefinitionNotFound: the global row does not exist yet.
            AttributeSchemaError: malformed payload or a forbidden core/locked
                change.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row, propagated = self._global.update(
                ctx.tenant_id, item_type, preset, attributes
            )
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="GlobalAttributeDefinition",
                entity_id=row.id,
                details={
                    "item_type": item_type,
                    "preset": preset,
                    "propagated_workspace_count": propagated,
                },
            )
        for workspace_id in self._global.list_derived_workspace_ids(row):
            invalidate_workspace_caches(str(workspace_id))
        return self._global_payload(item_type, preset, row, propagated=propagated)

    def update_workspace(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist a workspace override (sets ``is_customized=True``)."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row = self._workspace.update(
                ctx.tenant_id, workspace_id, item_type, attributes
            )
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="WorkspaceAttributeDefinition",
                entity_id=row.id,
                details={"item_type": item_type, "workspace_id": str(workspace_id)},
            )
        invalidate_workspace_caches(str(workspace_id))
        return self._workspace_payload(row)

    def reset_workspace(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Discard the override and re-copy the global default."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row = self._workspace.reset(ctx.tenant_id, workspace_id, item_type)
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="WorkspaceAttributeDefinition",
                entity_id=row.id,
                details={
                    "item_type": item_type,
                    "workspace_id": str(workspace_id),
                    "reset": True,
                },
            )
        invalidate_workspace_caches(str(workspace_id))
        return self._workspace_payload(row)

    # ---- Apply ------------------------------------------------------------

    def validate_artifact_fields(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        """Validate a create/update payload against the resolved definition.

        Wired live into the 9 workflow-backed REST ViewSets via
        ``WorkflowTransitionsMixin`` (Task 11). NOT yet called by the MCP
        artifact-write tools or by the CSV bulk importer — those paths still
        bypass this gate (tracked in the SDD ledger, tracker item I-2;
        `attribute_definition.py`'s own MCP tool group only manages
        definitions, it does not validate other artifacts' writes).
        ``existing is None`` means create (all required attributes
        are demanded); otherwise only the fields the request carries are
        checked, so a save that never touches a required field is not blocked.

        Raises:
            FieldValidationError: ``.errors`` maps attribute name -> messages.
        """
        attributes = self.resolve(ctx, item_type, workspace_id)["attributes"]
        validate_values(attributes, changed_fields, existing)

    def downgrade_warnings(
        self, ctx: AuthContext, workspace_id: UUID, target_preset: str
    ) -> list[str]:
        """Preset-downgrade warnings, reusing the existing preset check.

        Spec section 9: the same ``validate_downgrade`` as workflow, reused —
        this method only appends the attribute-specific findings for every item
        type the workspace has resolved.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        from presets.services import validate_downgrade

        warnings = list(validate_downgrade(str(workspace_id), target_preset))
        for item_type in self._workspace.resolved_item_types(
            ctx.tenant_id, workspace_id
        ):
            try:
                missing = self._workspace.missing_attributes_for_preset(
                    ctx.tenant_id, workspace_id, item_type, target_preset
                )
            except AttributeDefinitionNotFound:
                # Ledger binding (i), Task 5 review I-2: the target preset has
                # never been bootstrapped for this item type. That is a setup
                # gap for the admin to fix, not "every current attribute is
                # lost" — surface it as its own warning instead of either
                # crashing the whole downgrade check or silently treating an
                # unconfigured preset as an empty (i.e. compatible) one.
                warnings.append(
                    f"{item_type}: preset '{target_preset}' has not been "
                    f"initialized yet — run the bootstrap command before downgrading"
                )
                continue
            if missing:
                warnings.append(
                    f"{item_type}: attribute(s) {', '.join(missing)} do not exist "
                    f"in preset '{target_preset}'"
                )
        return warnings


__all__ = [
    "AttributeDefinitionConflictError",
    "AttributeDefinitionNotFound",
    "AttributeDefinitionService",
    "AttributeSchemaError",
    "FieldValidationError",
]
