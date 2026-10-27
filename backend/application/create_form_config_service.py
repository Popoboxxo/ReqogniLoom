"""Create-dialog form-definition service (Issue #1263).

The "new artifact" dialog is definition-driven: the shared ``ArtifactForm``
renders the resolved attribute definition. Issue #1263 makes that *dialog*
configurable on its own — which fields are visible, in what order, which are
required and which have a default — on three levels with precedence
``user > workspace > global`` and per artifact type, exactly like the
Attribute-v3 inheritance (issue #1263 point 1).

Storage deliberately reuses the tables the #1257 navigation-tree configuration
already established (``application.tree_display_config_service``):

* **user** — ``UserDisplayPreference.create_form_fields`` (self-service,
  RLS-covered; ``ctx.user_id`` is the whole boundary),
* **workspace** — ``TreeDisplayConfig(scope="workspace").create_form_json``
  (one row per workspace, workspace-admin-gated: ``Operation.WORKSPACE_CONFIG``,
  ENT-C3 = B),
* **global** — ``TreeDisplayConfig(scope="global").create_form_json`` (one row
  per tenant, admin-only).

At every level the JSON document is a map
``{item_type: [{"field_key", "visible", "required", "order", "default"}, …]}``,
so one document carries every artifact type and resolution stays a plain dict
lookup per level. Reusing the #1257 tables (rather than adding a second entity)
keeps the row count flat and the RLS policy identical.

The **base** the configuration customizes is the workspace's resolved attribute
definition (Attribute-v3, via ``AttributeDefinitionService``): the selectable
fields ARE the definition's attributes, so "vom Vorgehen genau wie die
Attribute". A missing row is **not** an error and never read as "empty":
resolution falls through and finally to the definition-derived base, which is
exactly the pre-#1263 rendering (issue #1263 point 3).

Server-side ``required`` enforcement (issue #1263 point 4) reads the *same*
resolved definition through :meth:`required_field_keys`, so a create that omits
a field the form marks required is refused on REST and MCP alike — not only in
the UI.

Layer 2 placement mirrors ``application.tree_display_config_service``: the
``rest_api/*_views.py`` modules keep their no-direct-ORM ratchet
(``rest_api/tests/test_architecture.py``). The direction
``application -> auth_tenancy.models`` is an established import.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction

from application.base import ServiceBase
from application.permissions import assert_workspace_config_permission
from attribute_definitions.create_form_fields import (
    CreateFormError,
    catalog_field_entries,
    merge_create_form_entries,
    normalize_create_form_entries,
    required_field_keys,
)
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    ROLE_ADMIN,
    TREE_DISPLAY_SCOPE_GLOBAL,
    TREE_DISPLAY_SCOPE_WORKSPACE,
    TreeDisplayConfig,
    UserDisplayPreference,
)
from persistence.errors import ValidationError

#: Task 9 (spec section 6 precedent): bumped only if the export document's
#: shape ever changes in a way ``import_config`` cannot read compatibly.
_EXPORT_SCHEMA_VERSION = 1

SCOPE_USER = "user"
SCOPE_WORKSPACE = "workspace"
SCOPE_GLOBAL = "global"
SCOPE_DEFAULT = "default"

#: The scopes a caller may read/write. ``default`` is a resolution outcome only,
#: never a target store.
WRITABLE_SCOPES: tuple[str, ...] = (SCOPE_USER, SCOPE_WORKSPACE, SCOPE_GLOBAL)


class CreateFormConfigService(ServiceBase):
    """Read/write the three-level create-dialog form definition (Issue #1263)."""

    # ------------------------------------------------------------------
    # Catalogue / base
    # ------------------------------------------------------------------

    def catalog(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Return the base entries for ``(item_type, workspace)``.

        The base is the workspace's resolved attribute definition projected to
        create-form entries (issue #1263 point 1: "keys from the Attribute-v3
        catalogue, do not reinvent"). Any failure to resolve — no bootstrapped
        definition, unknown item type, missing workspace — degrades to an empty
        base rather than failing the read: the stored configuration is still
        readable and writable, it simply has nothing to overlay yet.
        """
        definition = self._definition(ctx, item_type, workspace_id)
        return catalog_field_entries(
            definition["attributes"], definition["sections"]
        )

    # ------------------------------------------------------------------
    # Effective resolution
    # ------------------------------------------------------------------

    def get_config(
        self,
        ctx: AuthContext,
        *,
        item_type: str,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return the *effective* form definition for ``(item_type, workspace)``.

        Resolution order is ``user > workspace > global > definition default``.
        The returned ``scope`` names which level supplied the value, so a UI can
        show "inherited" vs "set here".
        """
        self._set_tenant_context(ctx)
        base = self.catalog(ctx, item_type, workspace_id)
        levels: tuple[tuple[str, dict[str, Any]], ...] = (
            (SCOPE_USER, self._user_map(ctx)),
            (SCOPE_WORKSPACE, self._workspace_map(workspace_id)),
            (SCOPE_GLOBAL, self._global_map()),
        )
        for scope, mapping in levels:
            if item_type in mapping:
                return self._payload(
                    item_type=item_type,
                    scope=scope,
                    fields=merge_create_form_entries(mapping[item_type], base=base),
                    base=base,
                )
        return self._payload(
            item_type=item_type,
            scope=SCOPE_DEFAULT,
            fields=base,
            base=base,
        )

    def get_scope(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        item_type: str | None = None,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return one level's stored configuration (not the resolved value).

        ``item_type`` omitted returns the whole ``{item_type: [...]}`` map, which
        is what an editor needs to render every type's row.
        """
        self._assert_writable_scope(scope)
        self._set_tenant_context(ctx)
        mapping = {
            SCOPE_USER: lambda: self._user_map(ctx),
            SCOPE_WORKSPACE: lambda: self._workspace_map(workspace_id),
            SCOPE_GLOBAL: self._global_map,
        }[scope]()

        if item_type is None:
            return {
                "scope": scope,
                "config": mapping,
                "catalog": [],
            }
        base = self.catalog(ctx, item_type, workspace_id)
        fields = (
            merge_create_form_entries(mapping[item_type], base=base)
            if item_type in mapping
            else None
        )
        return {
            "scope": scope,
            "item_type": item_type,
            "fields": fields,
            "catalog": base,
        }

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def set_config(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        item_type: str,
        fields: list[Any] | None,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Store (or reset) one level's form definition for one item type.

        ``fields`` is the ordered list of ``{field_key, visible, required, order,
        default}`` entries; ``None`` *resets* the level for that item type
        (removing the entry, so resolution falls back to the next level) — the
        user-facing "auf Standard zurücksetzen".

        The response is the **level that was written**, in the same shape
        :meth:`get_scope` returns — never the resolved value. An editor that
        edits the global default must not be shown its own personal override as
        if it were the tenant default; the resolved value is :meth:`get_config`
        (REST: ``?resolve=effective``).

        Raises:
            ValidationError: unknown scope, invalid ``fields`` payload, or a
                workspace scope without a ``workspace_id``.
            PermissionDeniedError: the caller lacks the privilege of the
                target level — ``Operation.WORKSPACE_CONFIG`` (workspace
                admin) for the workspace level, the ``admin`` role for the
                tenant-wide default.
        """
        self._assert_writable_scope(scope)
        self._set_tenant_context(ctx)

        normalized: list[dict[str, Any]] | None = None
        if fields is not None:
            valid_keys = [
                entry["field_key"]
                for entry in self.catalog(ctx, item_type, workspace_id)
            ]
            try:
                normalized = normalize_create_form_entries(
                    fields, valid_keys=valid_keys
                )
            except CreateFormError as exc:
                raise ValidationError(str(exc)) from exc

        if scope == SCOPE_USER:
            self._set_user(ctx, item_type, normalized)
        elif scope == SCOPE_WORKSPACE:
            if workspace_id is None:
                raise ValidationError("scope 'workspace' requires a workspace_id")
            self._set_workspace(ctx, workspace_id, item_type, normalized)
        else:
            self._set_global(ctx, item_type, normalized)

        return self.get_scope(
            ctx, scope=scope, item_type=item_type, workspace_id=workspace_id
        )

    # ------------------------------------------------------------------
    # Export / import (issue #1263 point 4 — "wie beim Attribut-Katalog")
    # ------------------------------------------------------------------

    def export_config(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        item_type: str,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Serialize one level's form definition for download.

        The document carries a ``schema_version`` so a future format change is
        detectable instead of silently misread. ``fields`` is the level's stored
        entry list, or ``null`` when that level inherits — the document
        round-trips through :meth:`import_config` either way.
        """
        header = self.get_scope(
            ctx, scope=scope, item_type=item_type, workspace_id=workspace_id
        )
        return {
            "schema_version": _EXPORT_SCHEMA_VERSION,
            "item_type": item_type,
            "scope": scope,
            "fields": header["fields"],
        }

    def import_config(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        item_type: str,
        payload: Any,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Import a previously-exported document into one level.

        Structural validation and normalization are :meth:`set_config`'s
        (the single write path), so an imported document is validated exactly
        like an edited one.

        Raises:
            ValidationError: the payload is not an object, its ``schema_version``
                is unrecognized, ``fields`` is neither a list nor ``null``, or
                :meth:`set_config` rejects an entry.
        """
        if not isinstance(payload, dict) or payload.get(
            "schema_version"
        ) != _EXPORT_SCHEMA_VERSION:
            raise ValidationError(
                f"unrecognized or missing schema_version "
                f"(expected {_EXPORT_SCHEMA_VERSION})"
            )
        fields = payload.get("fields")
        if fields is not None and not isinstance(fields, list):
            raise ValidationError("'fields', if present, must be a list or null")
        return self.set_config(
            ctx,
            scope=scope,
            item_type=item_type,
            fields=fields,
            workspace_id=workspace_id,
        )

    # ------------------------------------------------------------------
    # Server-side required enforcement (issue #1263 point 4)
    # ------------------------------------------------------------------

    def required_field_keys(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
    ) -> list[str]:
        """Field keys a create payload must carry, from the effective form.

        Reads the *same* resolved definition the dialog renders, so the server
        demands exactly the fields the form marks required — on REST and MCP
        creates alike, not only in the UI.
        """
        resolved = self.get_config(
            ctx, item_type=item_type, workspace_id=workspace_id
        )
        return required_field_keys(resolved["fields"])

    # ------------------------------------------------------------------
    # Level readers
    # ------------------------------------------------------------------

    def _user_map(self, ctx: AuthContext) -> dict[str, Any]:
        row = UserDisplayPreference.objects.filter(user_id=ctx.user_id).first()
        return self._as_map(row.create_form_fields if row is not None else None)

    def _workspace_map(self, workspace_id: UUID | None) -> dict[str, Any]:
        if workspace_id is None:
            return {}
        row = (
            TreeDisplayConfig.objects.filter(
                scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=workspace_id
            )
            .only("create_form_json")
            .first()
        )
        return self._as_map(row.create_form_json if row is not None else None)

    def _global_map(self) -> dict[str, Any]:
        row = (
            TreeDisplayConfig.objects.filter(scope=TREE_DISPLAY_SCOPE_GLOBAL)
            .only("create_form_json")
            .first()
        )
        return self._as_map(row.create_form_json if row is not None else None)

    # ------------------------------------------------------------------
    # Level writers
    # ------------------------------------------------------------------

    def _set_user(
        self,
        ctx: AuthContext,
        item_type: str,
        fields: list[dict[str, Any]] | None,
    ) -> None:
        row, _created = UserDisplayPreference.objects.get_or_create(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            defaults={},
        )
        mapping = self._as_map(row.create_form_fields)
        self._apply(mapping, item_type, fields)
        row.create_form_fields = mapping or None
        row.save(update_fields=["create_form_fields", "modified_at"])

    def _set_workspace(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        fields: list[dict[str, Any]] | None,
    ) -> None:
        # A workspace-level default governs every member, so it is workspace
        # *configuration* (Operation.WORKSPACE_CONFIG, admin tier) — an
        # editor's WRITE is not enough (ENT-C3 = B, Plan C T-C2-10).
        assert_workspace_config_permission(
            ctx, what="workspace-wide create-form definition"
        )
        # R7: ``create_form_json`` is ONE document per level, so this is a
        # read-modify-write. Two writers of different item types must not
        # overwrite each other: the row is re-read under ``SELECT ... FOR
        # UPDATE`` inside the transaction that commits the change.
        with transaction.atomic():
            row, _created = TreeDisplayConfig.objects.get_or_create(
                scope=TREE_DISPLAY_SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                defaults={},
            )
            row = TreeDisplayConfig.objects.select_for_update().get(pk=row.pk)
            mapping = self._as_map(row.create_form_json)
            self._apply(mapping, item_type, fields)
            row.create_form_json = mapping
            row.save(update_fields=["create_form_json", "modified_at"])

    def _set_global(
        self,
        ctx: AuthContext,
        item_type: str,
        fields: list[dict[str, Any]] | None,
    ) -> None:
        if not ctx.has_role(ROLE_ADMIN):
            from persistence.errors import PermissionDeniedError

            raise PermissionDeniedError(
                "Permission denied: the tenant-wide create-form definition "
                "requires the 'admin' role"
            )
        # Same lost-update shape as the workspace level (R7): one JSON document
        # per tenant, re-read under row lock before mutating.
        with transaction.atomic():
            row, _created = TreeDisplayConfig.objects.get_or_create(
                scope=TREE_DISPLAY_SCOPE_GLOBAL,
                tenant_id=ctx.tenant_id,
                defaults={},
            )
            row = TreeDisplayConfig.objects.select_for_update().get(pk=row.pk)
            mapping = self._as_map(row.create_form_json)
            self._apply(mapping, item_type, fields)
            row.create_form_json = mapping
            row.save(update_fields=["create_form_json", "modified_at"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(
        mapping: dict[str, Any],
        item_type: str,
        fields: list[dict[str, Any]] | None,
    ) -> None:
        """Set or drop one item type's entry in *mapping* (in place)."""
        if fields is None:
            mapping.pop(item_type, None)
        else:
            mapping[item_type] = fields

    @staticmethod
    def _as_map(raw: Any) -> dict[str, Any]:
        """Coerce a stored JSON value to a plain ``{item_type: [...]}`` dict.

        A hand-edited or legacy row is never allowed to raise on a *read* path:
        anything that is not a dict reads as "no configuration at this level".
        """
        return dict(raw) if isinstance(raw, dict) else {}

    def _definition(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID | None,
    ) -> dict[str, Any]:
        """Best-effort resolved attribute definition of ``(item_type, workspace)``.

        Returns empty ``attributes``/``sections`` whenever the definition cannot
        be resolved — no bootstrapped definition, unknown item type, missing
        workspace — so the catalogue (and validation) never fail because the
        attribute engine is not ready. The import is lazy to avoid a module-load
        cycle with ``application.attribute_definition_service``.
        """
        empty: dict[str, Any] = {"attributes": [], "sections": []}
        if not item_type or workspace_id is None:
            return empty
        try:
            from application.attribute_definition_service import (
                AttributeDefinitionService,
            )

            definition = AttributeDefinitionService().resolve(
                ctx, item_type, workspace_id
            )
            return {
                "attributes": [
                    a for a in definition.get("attributes", []) if isinstance(a, dict)
                ],
                "sections": [
                    s for s in definition.get("sections", []) if isinstance(s, dict)
                ],
            }
        except Exception:  # noqa: BLE001 — catalogue/validation must not fail
            return empty

    @staticmethod
    def _payload(
        *,
        item_type: str,
        scope: str,
        fields: list[dict[str, Any]],
        base: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "item_type": item_type,
            "scope": scope,
            "fields": fields,
            # The base doubles as the catalogue an editor renders: every
            # configurable field with the definition's own default entry.
            "catalog": base,
        }

    @staticmethod
    def _assert_writable_scope(scope: str) -> None:
        if scope not in WRITABLE_SCOPES:
            raise ValidationError(
                f"Unknown create-form scope {scope!r}; expected one of "
                f"{list(WRITABLE_SCOPES)}"
            )


__all__ = [
    "SCOPE_DEFAULT",
    "SCOPE_GLOBAL",
    "SCOPE_USER",
    "SCOPE_WORKSPACE",
    "WRITABLE_SCOPES",
    "CreateFormConfigService",
]
