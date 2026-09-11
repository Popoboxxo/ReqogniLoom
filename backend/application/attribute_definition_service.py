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
    stored_sections,
    validate_new_attribute_name,
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

#: Task 9 (spec section 6). Bumped only if the export document's shape ever
#: changes in a way ``import_definition`` cannot read compatibly.
_EXPORT_SCHEMA_VERSION = 1

_ON_COLLISION_CHOICES = frozenset({"skip", "overwrite", "rename"})


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

    @staticmethod
    def _source_global_names(row: Any) -> frozenset[str]:
        """Attribute names the workspace row's linked global default carries.

        ``row.source_global`` can be ``None`` (the global was deleted after
        materialization, same case :meth:`workspace_definition_store.reset`
        already guards) — an empty set then means every attribute reads as
        ``workspace_only``, which is the honest answer once there is nothing
        left to compare against.
        """
        source = row.source_global
        if source is None:
            return frozenset()
        return frozenset(a["name"] for a in stored_attributes(source.definition_json))

    def _workspace_payload(self, row: Any) -> dict[str, Any]:
        """Task 4 (spec section 4.2): a read-only ``origins`` map (name ->
        ``"global" | "global_customized" | "workspace_only"``) for the table
        view's "Herkunft" column — computed here, not stored.

        Deliberately a SEPARATE sibling key, not a per-entry ``origin`` field
        merged into ``attributes``: ``resolve()["attributes"]`` is the exact
        list ``elicit_attributes``/``export_attributes``/
        ``validate_artifact_fields`` index by known key, AND (found live by
        this addition's own regression run) ``requirement_bundle_service``'s
        schema export re-runs it through ``validate_definition_json``, which
        rejects any key outside its allow-list. A sibling map can never
        collide with that contract.

        ``is_customized`` is a per-DEFINITION flag, not per-attribute (Task 2
        finding): every attribute the workspace still inherits reads as
        ``global_customized`` once ANY local edit has landed, not just the one
        that was actually touched. Documented, not a bug — a future plan would
        need per-attribute divergence tracking to do better.
        """
        global_names = self._source_global_names(row)
        attributes = self._attributes(row)
        origins = {
            attribute["name"]: (
                "workspace_only"
                if attribute["name"] not in global_names
                else "global_customized" if row.is_customized else "global"
            )
            for attribute in attributes
        }
        return {
            "item_type": row.item_type,
            "preset": row.preset,
            "is_customized": row.is_customized,
            "version": row.version,
            "attributes": attributes,
            "origins": origins,
            # Task 7: row is materialized by resolve()/self._workspace.resolve
            # before this is ever called, so 'sections' is always present.
            "sections": stored_sections(row.definition_json),
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
            # Task 7: callers of this method must have already called
            # self._global.ensure_sections(row) first (get_global/list_global
            # do; update_global's row comes back fresh from its own write,
            # which always includes 'attributes' but not necessarily
            # 'sections' -- stored_sections tolerates that, returning []).
            "sections": stored_sections(row.definition_json) if row is not None else [],
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
        for row in rows:
            self._global.ensure_sections(row)
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
        if row is not None:
            self._global.ensure_sections(row)
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
        sections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Replace the tenant-wide default and propagate to on-default workspaces.

        *sections* (Task 8) is optional — omitted, the row's existing
        ``sections`` list is preserved unchanged; passed, it replaces it
        (validated the same way ``attributes`` is).

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
                ctx.tenant_id, item_type, preset, attributes, sections
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
        sections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Persist a workspace override (sets ``is_customized=True``).

        *sections* is optional — see :meth:`update_global`'s identical
        parameter.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row = self._workspace.update(
                ctx.tenant_id, workspace_id, item_type, attributes, sections
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

    @staticmethod
    def _model_field_names(item_type: str) -> frozenset[str]:
        """Field names already on *item_type*'s Django model.

        Reuses the bootstrap command's own model resolution (``MODEL_LOCATIONS``
        / ``_resolve_model``) instead of re-deriving it, so "which model backs
        this item type" has exactly one source. Imported inline — this module
        must not load ``django.core.management`` machinery at import time.
        """
        from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
            _resolve_model,
        )

        model = _resolve_model(item_type)
        return frozenset(f.name for f in model._meta.get_fields())

    def create_global(
        self,
        ctx: AuthContext,
        item_type: str,
        preset: str,
        attribute: dict[str, Any],
    ) -> dict[str, Any]:
        """Add one new ``kind="extended"`` attribute to the global default.

        Reuses :meth:`update_global`'s full validation (core-lock, locked-lock,
        propagation, audit log) by reading the current row, appending the new
        entry, and delegating.

        Raises:
            AttributeDefinitionNotFound: no global row for that key yet — use
                the bootstrap command / ``initialize`` first.
            AttributeSchemaError: the name collides or is malformed
                (:func:`validate_new_attribute_name`), or ``attribute["kind"]
                == "core"`` (rejected downstream by
                :func:`validate_meta_only_change`).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        row = self._global.get(ctx.tenant_id, item_type, preset)
        if row is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        current = stored_attributes(row.definition_json)
        validate_new_attribute_name(
            attribute.get("name", ""),
            current,
            reserved_field_names=self._model_field_names(item_type),
        )
        return self.update_global(ctx, item_type, preset, current + [attribute])

    def delete_global(
        self, ctx: AuthContext, item_type: str, preset: str, name: str
    ) -> dict[str, Any]:
        """Remove one ``kind="extended"`` attribute from the global default.

        Refuses (``AttributeSchemaError``) if *name* names a ``kind="core"``
        attribute — :func:`validate_meta_only_change` rejects it once the
        entry is missing from the new list. Does not check for existing
        ``CustomFieldValue`` data; this is the hard-delete primitive the
        soft-/force-delete UI flows call after their own confirmation.

        Raises:
            AttributeDefinitionNotFound: no global row for that key, or the row
                has no attribute called *name* (post-review m7: a delete of a
                name that is not there used to answer 200 + a version bump +
                an audit entry, i.e. a typo'd or already-deleted name read as
                success).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        row = self._global.get(ctx.tenant_id, item_type, preset)
        if row is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        current = stored_attributes(row.definition_json)
        remaining = [a for a in current if a["name"] != name]
        if len(remaining) == len(current):
            raise AttributeDefinitionNotFound(
                f"No attribute '{name}' in '{item_type}/{preset}'"
            )
        return self.update_global(ctx, item_type, preset, remaining)

    def create_workspace(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        attribute: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a workspace-only attribute (no ``source_global`` counterpart).

        Materializes the workspace row first (same as :meth:`resolve`) so this
        also works the first time an admin touches an item type in this
        workspace. Sets ``is_customized=True`` on the row — identical
        divergence semantics to any other workspace edit: once a workspace has
        any local addition it stops receiving global propagation until
        :meth:`reset_workspace` re-copies the global. Reuses
        :meth:`update_workspace`'s full validation the same way
        :meth:`create_global` reuses :meth:`update_global`'s.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        preset = self._workspace_preset(workspace_id)
        row = self._workspace.resolve(ctx.tenant_id, workspace_id, item_type, preset)
        current = stored_attributes(row.definition_json)
        validate_new_attribute_name(
            attribute.get("name", ""),
            current,
            reserved_field_names=self._model_field_names(item_type),
        )
        return self.update_workspace(ctx, item_type, workspace_id, current + [attribute])

    def delete_workspace(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID, name: str
    ) -> dict[str, Any]:
        """Remove one attribute from the workspace's resolved definition.

        Works identically whether *name* is a workspace-only attribute or one
        the workspace currently only inherits from global (no prior local
        override): either way the row is materialized if needed, the entry is
        dropped, and the result is saved through :meth:`update_workspace` —
        which sets ``is_customized=True`` like any other workspace edit. An
        inherited attribute removed this way therefore does NOT come back on
        the next global propagation (propagation only ever touches
        ``is_customized=False`` rows, see
        ``GlobalAttributeDefinitionStore._derived_row_filter``); it stays gone
        until :meth:`reset_workspace` explicitly discards the override. A
        ``kind="core"`` name is refused the same way :meth:`delete_global`
        refuses one.

        Raises:
            AttributeDefinitionNotFound: the workspace/global row does not
                exist, or the resolved definition has no attribute called
                *name* (post-review m7, see :meth:`delete_global`).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        preset = self._workspace_preset(workspace_id)
        row = self._workspace.resolve(ctx.tenant_id, workspace_id, item_type, preset)
        current = stored_attributes(row.definition_json)
        remaining = [a for a in current if a["name"] != name]
        if len(remaining) == len(current):
            raise AttributeDefinitionNotFound(
                f"No attribute '{name}' in '{item_type}' of workspace {workspace_id}"
            )
        return self.update_workspace(ctx, item_type, workspace_id, remaining)

    def count_usages(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        attribute_name: str,
        option_value: str | None = None,
    ) -> int:
        """Count artifacts of *item_type* in this workspace referencing *attribute_name*.

        Only meaningful for a ``kind="extended"`` attribute: its value lives
        in ``Artifact.custom_fields`` (REQ-L2-AS-037, the single JSONB store
        every artifact type's extended field folds into since the
        Datenmodell-Konsolidierung, indexed by
        ``pl_artifact_custom_fields_gin``). A ``kind="core"`` name has no
        live caller: ``delete_global``/``delete_workspace`` already refuse to
        remove a core attribute, and the delete- and option-removal
        confirmation flows are this method's only two callers — so this
        deliberately does not also branch into per-model-field counting for
        that case (YAGNI: nothing would ever reach it).

        Uses ``KeyTextTransform``/``KeyTransform`` rather than a
        ``custom_fields__{name}`` keyword lookup: the latter splits on every
        ``__`` in *attribute_name* as a JSON path segment, which is wrong for
        a (valid, snake_case) name that happens to contain a double
        underscore.

        Post-review M4: *option_value* matches BOTH storage shapes an option
        can have, because an ``enum`` stores the bare string while a
        ``multi-enum`` stores a JSON list (``field_validation._check_type``).
        The old ``KeyTextTransform == option_value`` comparison saw a
        multi-enum's serialized array text, never the bare option, so removing
        a multi-enum option always reported 0 affected artifacts and the
        safety check of spec section 4.3 was dead for exactly the type that
        needs it most. The list arm is a JSONB containment test
        (``(custom_fields -> name) @> '["value"]'``), which the
        ``pl_artifact_custom_fields_gin`` index serves.

        Both arms are ORed instead of branching on the attribute's declared
        ``type``: reading the type would mean resolving the whole definition,
        which 404s when the item type has no global default yet — a probe that
        legitimately answers 0 today would start raising. The two predicates
        are mutually exclusive on real data anyway (a JSON string is never
        contained in an array test, an array never equals a bare string).

        Raises:
            PermissionDeniedError: caller is not an admin.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        from django.db.models import Q
        from django.db.models.fields.json import KeyTextTransform, KeyTransform

        from persistence.models import Artifact

        qs = Artifact.objects.filter(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            artifact_type=item_type,
            custom_fields__has_key=attribute_name,
        )
        if option_value is not None:
            qs = qs.annotate(
                _attr_text=KeyTextTransform(attribute_name, "custom_fields"),
                _attr_json=KeyTransform(attribute_name, "custom_fields"),
            ).filter(
                Q(_attr_text=option_value) | Q(_attr_json__contains=[option_value])
            )
        return qs.count()

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
        ``WorkflowTransitionsMixin`` (Task 11), as well as MCP artifact-write
        tools (``mcp_server/tools/base.py::validate_artifact_write``) and the
        CSV bulk importer (``ImportService._validate_attribute_definitions``).
        `attribute_definition.py`'s own MCP tool group only manages
        definitions, it does not validate other artifacts' writes.
        ``existing is None`` means create (all required attributes
        are demanded); otherwise only the fields the request carries are
        checked, so a save that never touches a required field is not blocked.

        The resolved ``sections`` travel with the attributes (post-review M5):
        a ``required`` attribute sitting in a ``visible=false`` section is not
        demanded, exactly as the form renderer already treats it — otherwise
        hiding such a section made every create fail server-side for a field
        the UI no longer draws, with no way out from the UI.

        Raises:
            FieldValidationError: ``.errors`` maps attribute name -> messages.
        """
        definition = self.resolve(ctx, item_type, workspace_id)
        validate_values(
            definition["attributes"],
            changed_fields,
            existing,
            definition["sections"],
        )

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

    # ---- Export / Import (Task 9, spec section 6) --------------------------

    def export_definition(
        self,
        ctx: AuthContext,
        item_type: str,
        *,
        preset: str | None = None,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Serialize a whole definition (attributes + sections) for download.

        Exactly one of *preset* (global scope) / *workspace_id* (workspace
        scope, resolved from the workspace's own tier) must be given.

        ``schema_version`` lets :meth:`import_definition` detect a future
        format change instead of silently misreading an old export.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeDefinitionNotFound: the global row does not exist yet
                (global scope), or no global default exists for the
                workspace's preset (workspace scope).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        if workspace_id is not None:
            row = self._workspace.resolve(
                ctx.tenant_id, workspace_id, item_type, self._workspace_preset(workspace_id)
            )
        elif preset is not None:
            row = self._global.get(ctx.tenant_id, item_type, preset)
            if row is None:
                raise AttributeDefinitionNotFound(
                    f"No global attribute definition for '{item_type}/{preset}'"
                )
            self._global.ensure_sections(row)
        else:
            # AttributeSchemaError, not a bare ValueError: every caller of this
            # module catches the module's own taxonomy (the REST views'
            # ``except AttributeSchemaError`` clauses, the MCP tool group's
            # error mapping). A bare ValueError matches none of them and would
            # surface as a 500 for what is a malformed request.
            raise AttributeSchemaError(
                ["export_definition requires either preset or workspace_id"]
            )
        return {
            "schema_version": _EXPORT_SCHEMA_VERSION,
            "item_type": item_type,
            "attributes": stored_attributes(row.definition_json),
            "sections": stored_sections(row.definition_json),
        }

    def import_definition(
        self,
        ctx: AuthContext,
        item_type: str,
        payload: dict[str, Any],
        *,
        preset: str | None = None,
        workspace_id: UUID | None = None,
        on_collision: str = "skip",
    ) -> dict[str, Any]:
        """Import a previously-exported document into a definition.

        Exactly one of *preset* / *workspace_id* must be given, same contract
        as :meth:`export_definition`. On global scope this is "like an edit"
        (spec section 6): it goes through :meth:`update_global`, so
        propagation to non-customized workspaces applies exactly as any
        other global edit would — no special-cased write path.

        Structural validation, the core-lock and the final duplicate-name
        check all happen downstream in ``update_global``/``update_workspace``;
        :meth:`_merge_import` decides WHICH entries survive the merge per
        *on_collision* and runs the new-name gate
        (:func:`validate_new_attribute_name`) on every entry it ADDS, which is
        the same single validation path ``create_global``/``create_workspace``
        rely on (spec section 6: "validated against the same logic as
        creating one").

        ``payload["sections"]`` is merged by the identical rules and applied
        alongside the attributes; a document without a ``sections`` key leaves
        the target's own sections untouched.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeSchemaError: *on_collision* is not one of "skip"/
                "overwrite"/"rename", the payload's ``schema_version`` is
                missing or unrecognized, ``attributes`` is not a list,
                ``sections`` is present but not a list, an added attribute
                name is invalid or shadows a model field, or the merged result
                fails the normal update validation (e.g. an incoming
                ``kind="core"`` entry — rejected the same way a fresh core
                create is).
            AttributeDefinitionNotFound: no definition exists yet to import into.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        if on_collision not in _ON_COLLISION_CHOICES:
            raise AttributeSchemaError(
                [f"on_collision must be one of {sorted(_ON_COLLISION_CHOICES)}"]
            )
        if not isinstance(payload, dict) or payload.get("schema_version") != _EXPORT_SCHEMA_VERSION:
            raise AttributeSchemaError(
                [f"unrecognized or missing schema_version (expected {_EXPORT_SCHEMA_VERSION})"]
            )
        incoming = payload.get("attributes")
        if not isinstance(incoming, list):
            raise AttributeSchemaError(["payload must have an 'attributes' list"])
        incoming_sections = payload.get("sections")
        if incoming_sections is not None and not isinstance(incoming_sections, list):
            raise AttributeSchemaError(["'sections', if present, must be a list"])

        if workspace_id is not None:
            current_row = self._workspace.resolve(
                ctx.tenant_id, workspace_id, item_type, self._workspace_preset(workspace_id)
            )
        elif preset is not None:
            current_row = self._global.get(ctx.tenant_id, item_type, preset)
            if current_row is None:
                raise AttributeDefinitionNotFound(
                    f"No global attribute definition for '{item_type}/{preset}'"
                )
        else:
            raise AttributeSchemaError(
                ["import_definition requires either preset or workspace_id"]
            )

        merged = self._merge_import(
            stored_attributes(current_row.definition_json),
            incoming,
            on_collision,
            reserved_field_names=self._model_field_names(item_type),
        )
        # Post-review M1: ``export_definition`` emits 'sections' too, and
        # dropping it here silently discarded every imported section's
        # visibility/layout while the target's own sections survived — i.e. an
        # import of a document whose sections are hidden produced a definition
        # whose sections are visible. ``None`` (document carries no 'sections'
        # key at all — a hand-written or pre-Task-7 document) keeps meaning
        # "leave the row's sections alone", the same contract the PUT views'
        # ``_read_sections`` already has. Section names carry no snake_case /
        # reserved-name rules (they are free-text display groups), hence no
        # ``reserved_field_names`` on this call.
        merged_sections = (
            None
            if incoming_sections is None
            else self._merge_import(
                stored_sections(current_row.definition_json),
                incoming_sections,
                on_collision,
            )
        )
        if workspace_id is not None:
            return self.update_workspace(
                ctx, item_type, workspace_id, merged, merged_sections
            )
        return self.update_global(ctx, item_type, preset, merged, merged_sections)

    @staticmethod
    def _merge_import(
        current: list[dict[str, Any]],
        incoming: list[Any],
        on_collision: str,
        *,
        reserved_field_names: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge *incoming* (raw, un-normalized entries from an import file)
        into *current* per *on_collision*: ``"skip"`` leaves the existing
        entry, ``"overwrite"`` replaces it, ``"rename"`` suffixes the
        incoming entry's name (``name_2``, ``name_3``, ... — the first free
        suffix). A malformed entry (not a dict, or no ``name``) is passed
        through unchanged; ``update_global``/``update_workspace``'s own
        validation rejects it with a proper error naming the problem.

        Post-review M2: *reserved_field_names* (``None`` disables the check,
        which is what the sections merge wants) turns on the SAME
        :func:`validate_new_attribute_name` gate ``create_global``/
        ``create_workspace`` run — spec section 6 requires an import to
        validate a new name "against the same logic as creating one". It runs
        for every entry this merge ADDS under a name the definition does not
        have yet, including the ``name_2`` candidate the rename path
        fabricates. It deliberately does NOT run for ``skip``/``overwrite``
        collisions: those names are already stored, i.e. already validated,
        and re-validating them would fail on "already exists".

        Raises:
            AttributeSchemaError: an added name is not snake_case or collides
                with a Django model field of the item type.
        """
        existing_names = {a["name"] for a in current}
        result = list(current)

        def _admit(name: str) -> None:
            """Validate a name this merge is about to introduce, then claim it."""
            if reserved_field_names is not None:
                validate_new_attribute_name(
                    name,
                    [{"name": n} for n in existing_names],
                    reserved_field_names=reserved_field_names,
                )
            existing_names.add(name)

        for entry in incoming:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str) or name not in existing_names:
                if isinstance(name, str):
                    _admit(name)
                result.append(entry)
                continue
            if on_collision == "skip":
                continue
            if on_collision == "overwrite":
                result = [
                    entry if (isinstance(a, dict) and a.get("name") == name) else a
                    for a in result
                ]
                continue
            # "rename"
            suffix = 2
            candidate = f"{name}_{suffix}"
            while candidate in existing_names:
                suffix += 1
                candidate = f"{name}_{suffix}"
            _admit(candidate)
            result.append({**entry, "name": candidate})
        return result


__all__ = [
    "AttributeDefinitionConflictError",
    "AttributeDefinitionNotFound",
    "AttributeDefinitionService",
    "AttributeSchemaError",
    "FieldValidationError",
]
