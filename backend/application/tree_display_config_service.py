"""Tree-display configuration service (Issue #1257).

Server-side home of the navigation tree's configurable field selection. The
tree (``shared/WorkspaceTree``) used to render one fixed field combination per
artifact type; issue #1257 makes it configurable on three levels with precedence
``user > workspace > global`` and per artifact type.

Storage (mirrors the #1096/#1265 display-preference precedent):

* **personal** — ``UserDisplayPreference.tree_display_fields`` (self-service,
  RLS-covered; ``ctx.user_id`` is the whole authorization boundary),
* **workspace** — ``TreeDisplayConfig(scope="workspace")`` (one row per
  workspace, workspace-admin-gated: ``Operation.WORKSPACE_CONFIG``, ENT-C3 = B),
* **global** — ``TreeDisplayConfig(scope="global")`` (one row per tenant,
  admin-only).

At every level ``fields_json`` / ``tree_display_fields`` is a map
``{item_type: [{"key": …, "width": …}, …]}``. Because a *single* JSON document
carries every artifact type, the row count stays flat (one global row, one row
per workspace, one per user) no matter how many artifact types are configured,
and resolution is a plain dict lookup per level.

Field keys come from ``attribute_definitions.tree_fields`` (issue #1257 point 2
— "keys from the Attribute-v3 catalogue, do not reinvent"). The catalogue is
extended, best-effort, with the workspace's custom attribute names so a custom
attribute is configurable too; when no definition is resolvable the built-in
catalogue still answers.

A missing row is **not** an error and never read as "empty": resolution falls
through to the next level and finally to
:data:`attribute_definitions.tree_fields.DEFAULT_TREE_DISPLAY_FIELDS`, which is
the pre-#1257 rendering (issue #1257 point 5).

Placement mirrors ``application.display_preference_service``: Layer 2, so the
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
from attribute_definitions.tree_fields import (
    DEFAULT_TREE_DISPLAY_FIELDS,
    TreeFieldError,
    field_catalog,
    merge_tree_fields,
    normalize_tree_fields,
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

SCOPE_USER = "user"
SCOPE_WORKSPACE = "workspace"
SCOPE_GLOBAL = "global"
SCOPE_DEFAULT = "default"

#: The scopes a caller may read/write. ``default`` is a resolution outcome only,
#: never a target store.
WRITABLE_SCOPES: tuple[str, ...] = (SCOPE_USER, SCOPE_WORKSPACE, SCOPE_GLOBAL)


class TreeDisplayConfigService(ServiceBase):
    """Read/write the three-level tree-display configuration (Issue #1257)."""

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------

    def catalog(
        self,
        ctx: AuthContext,
        *,
        item_type: str | None = None,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Return the selectable fields for *item_type* (built-in + custom).

        Custom attribute names are merged in best-effort from the workspace's
        resolved attribute definition; any failure (no bootstrapped definition,
        unknown item type) degrades to the built-in catalogue rather than
        failing the read — the configuration is usable either way.
        """
        return field_catalog(self._custom_attribute_keys(ctx, item_type, workspace_id))

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
        """Return the *effective* field selection for ``(item_type, workspace)``.

        Resolution order is ``user > workspace > global > default``. The
        returned ``scope`` names which level supplied the value, so a UI can
        show "inherited" vs "set here".
        """
        self._set_tenant_context(ctx)
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
                    fields=merge_tree_fields(
                        mapping[item_type],
                        base=self._default_fields(),
                    ),
                    ctx=ctx,
                    workspace_id=workspace_id,
                )
        return self._payload(
            item_type=item_type,
            scope=SCOPE_DEFAULT,
            fields=self._default_fields(),
            ctx=ctx,
            workspace_id=workspace_id,
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
                "catalog": self.catalog(ctx, workspace_id=workspace_id),
            }
        fields = (
            merge_tree_fields(mapping[item_type], base=self._default_fields())
            if item_type in mapping
            else None
        )
        return {
            "scope": scope,
            "item_type": item_type,
            "fields": fields,
            "catalog": self.catalog(
                ctx, item_type=item_type, workspace_id=workspace_id
            ),
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
        """Store (or reset) one level's selection for one item type.

        ``fields`` is the ordered list of ``{"key", "width"}`` entries; ``None``
        *resets* the level for that item type (removing the entry, so resolution
        falls back to the next level) — the user-facing "auf Standard
        zurücksetzen".

        The response is the **level that was written**, in the same shape
        :meth:`get_scope` returns (``scope``/``item_type``/``fields``/
        ``catalog``) — never the resolved value. An editor that edits the global
        default must not be shown its own personal override as if it were the
        tenant default; the resolved value is :meth:`get_config` (REST:
        ``?resolve=effective``).

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
            try:
                normalized = normalize_tree_fields(
                    fields,
                    extra_keys=self._custom_attribute_keys(
                        ctx, item_type, workspace_id
                    ),
                )
            except TreeFieldError as exc:
                raise ValidationError(str(exc)) from exc

        if scope == SCOPE_USER:
            self._set_user(ctx, item_type, normalized)
        elif scope == SCOPE_WORKSPACE:
            if workspace_id is None:
                raise ValidationError(
                    "scope 'workspace' requires a workspace_id"
                )
            self._set_workspace(ctx, workspace_id, item_type, normalized)
        else:
            self._set_global(ctx, item_type, normalized)

        return self.get_scope(
            ctx, scope=scope, item_type=item_type, workspace_id=workspace_id
        )

    # ------------------------------------------------------------------
    # Level readers
    # ------------------------------------------------------------------

    def _user_map(self, ctx: AuthContext) -> dict[str, Any]:
        row = UserDisplayPreference.objects.filter(user_id=ctx.user_id).first()
        return self._as_map(row.tree_display_fields if row is not None else None)

    def _workspace_map(self, workspace_id: UUID | None) -> dict[str, Any]:
        if workspace_id is None:
            return {}
        row = (
            TreeDisplayConfig.objects.filter(
                scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=workspace_id
            )
            .only("fields_json")
            .first()
        )
        return self._as_map(row.fields_json if row is not None else None)

    def _global_map(self) -> dict[str, Any]:
        row = (
            TreeDisplayConfig.objects.filter(scope=TREE_DISPLAY_SCOPE_GLOBAL)
            .only("fields_json")
            .first()
        )
        return self._as_map(row.fields_json if row is not None else None)

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
        mapping = self._as_map(row.tree_display_fields)
        self._apply(mapping, item_type, fields)
        row.tree_display_fields = mapping or None
        row.save(update_fields=["tree_display_fields", "modified_at"])

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
            ctx, what="workspace-wide tree display configuration"
        )
        # R7: ``fields_json`` is ONE document per level, so this is a
        # read-modify-write. Two writers of different item types must not
        # overwrite each other: the row is re-read under ``SELECT ... FOR
        # UPDATE`` inside the transaction that commits the change.
        with transaction.atomic():
            row, _created = TreeDisplayConfig.objects.get_or_create(
                scope=TREE_DISPLAY_SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                defaults={"fields_json": {}},
            )
            row = TreeDisplayConfig.objects.select_for_update().get(pk=row.pk)
            mapping = self._as_map(row.fields_json)
            self._apply(mapping, item_type, fields)
            row.fields_json = mapping
            row.save(update_fields=["fields_json", "modified_at"])

    def _set_global(
        self,
        ctx: AuthContext,
        item_type: str,
        fields: list[dict[str, Any]] | None,
    ) -> None:
        if not ctx.has_role(ROLE_ADMIN):
            from persistence.errors import PermissionDeniedError

            raise PermissionDeniedError(
                "Permission denied: the tenant-wide tree display configuration "
                "requires the 'admin' role"
            )
        # Same lost-update shape as the workspace level (R7): one JSON document
        # per tenant, re-read under row lock before mutating.
        with transaction.atomic():
            row, _created = TreeDisplayConfig.objects.get_or_create(
                scope=TREE_DISPLAY_SCOPE_GLOBAL,
                tenant_id=ctx.tenant_id,
                defaults={"fields_json": {}},
            )
            row = TreeDisplayConfig.objects.select_for_update().get(pk=row.pk)
            mapping = self._as_map(row.fields_json)
            self._apply(mapping, item_type, fields)
            row.fields_json = mapping
            row.save(update_fields=["fields_json", "modified_at"])

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

    @staticmethod
    def _default_fields() -> list[dict[str, Any]]:
        """The pre-#1257 combination as full ``{"key", "width"}`` entries."""
        return merge_tree_fields(
            list(DEFAULT_TREE_DISPLAY_FIELDS),
            base=[
                {"key": key, "width": "full"} for key in DEFAULT_TREE_DISPLAY_FIELDS
            ],
        )

    def _payload(
        self,
        *,
        item_type: str,
        scope: str,
        fields: list[dict[str, Any]],
        ctx: AuthContext,
        workspace_id: UUID | None,
    ) -> dict[str, Any]:
        return {
            "item_type": item_type,
            "scope": scope,
            "fields": fields,
            "catalog": self.catalog(
                ctx, item_type=item_type, workspace_id=workspace_id
            ),
        }

    @staticmethod
    def _assert_writable_scope(scope: str) -> None:
        if scope not in WRITABLE_SCOPES:
            raise ValidationError(
                f"Unknown tree display scope {scope!r}; expected one of "
                f"{list(WRITABLE_SCOPES)}"
            )

    @staticmethod
    def _custom_attribute_keys(
        ctx: AuthContext,
        item_type: str | None,
        workspace_id: UUID | None,
    ) -> list[str]:
        """Best-effort custom attribute names of ``(item_type, workspace)``.

        Returns ``[]`` whenever the definition cannot be resolved — no
        bootstrapped definition, unknown item type, missing workspace — so the
        catalogue (and validation) never fail because the attribute engine is
        not ready. The import is lazy to avoid a module-load cycle with
        ``attribute_definitions``.
        """
        if not item_type or workspace_id is None:
            return []
        try:
            from application.attribute_definition_service import (
                AttributeDefinitionService,
            )

            definition = AttributeDefinitionService().resolve(
                ctx, item_type, workspace_id
            )
            # Only extended attributes are relevant: a ``core`` attribute is a
            # model field (``id``/``status``/…) that the built-in catalogue
            # already covers under its own key. ``field_catalog`` de-duplicates
            # the overlap, so returning a name twice is harmless.
            return [
                str(attr["name"])
                for attr in definition.get("attributes", [])
                if attr.get("kind") == "extended" and attr.get("name")
            ]
        except Exception:  # noqa: BLE001 — catalogue/validation must not fail
            return []


__all__ = [
    "SCOPE_DEFAULT",
    "SCOPE_GLOBAL",
    "SCOPE_USER",
    "SCOPE_WORKSPACE",
    "WRITABLE_SCOPES",
    "TreeDisplayConfigService",
]
