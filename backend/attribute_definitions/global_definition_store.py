"""Store for the tenant-wide ``GlobalAttributeDefinition`` rows.

Structurally symmetric to ``workflow.global_definition_store``: every mutation
persists the global row and PROPAGATES ``definition_json`` into every
``is_customized=False`` derived definition of the SAME preset, returning the
propagated workspace count so the UI can surface it.

Uses ``unscoped`` on purpose: the tenant is passed explicitly by the caller
(the service already asserted the admin role for that tenant), which mirrors
``GlobalWorkflowDefinitionStore``. ``unscoped`` only bypasses Django's
``TenantManager`` filtering, not the Postgres RLS policies (see
``migrations/0002_attribute_definition_rls_policies.py``, ENABLE + FORCE ROW
LEVEL SECURITY). It works from data migrations because those run as the
Postgres superuser, which RLS never restricts. It does NOT unlock all-tenant
visibility from management commands: those run as the ``reqogniloom_app``
role, which is subject to RLS, so with no thread-local tenant armed the
policy predicate is false for every row and the query returns nothing.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import GlobalAttributeDefinition, WorkspaceAttributeDefinition
from .schema import (
    AttributeDefinitionConflictError,
    stored_attributes,
    validate_definition_json,
    validate_definition_key,
    validate_meta_only_change,
)


class AttributeDefinitionNotFound(LookupError):
    """No definition row exists for the requested key."""


class GlobalAttributeDefinitionStore:
    """CRUD + propagation for tenant-wide global attribute defaults."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalAttributeDefinition | None:
        """Return the global row for ``(tenant, item_type, preset)`` or None."""
        return GlobalAttributeDefinition.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, preset=preset
        ).first()

    def list(
        self,
        tenant_id: UUID | str,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[GlobalAttributeDefinition]:
        """Return all global rows for the tenant, optionally filtered."""
        qs = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        if preset:
            qs = qs.filter(preset=preset)
        return list(qs.order_by("item_type", "preset"))

    # ---------- Write ----------

    def initialize(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> GlobalAttributeDefinition:
        """Create the global definition for ``(item_type, preset)``.

        This is the **only** path that may write ``kind="core"`` /
        ``locked=True`` entries: ``validate_meta_only_change`` (which forbids
        both) guards updates, not creation. That is deliberate — the bootstrap
        introspector has to be able to seed them — but it also means a bad
        initial payload is not repairable through ``update()``, since the very
        rules that protect core/locked attributes then make them permanent.
        :meth:`reinitialize` is the recovery path for that case.

        Raises:
            AttributeDefinitionConflictError: a row already exists (409). A
                dedicated subclass so a REST/MCP handler can map it without
                substring-matching this message.
            AttributeSchemaError: unknown *item_type*/*preset*, or *attributes*
                is malformed.
        """
        validate_definition_key(item_type, preset)
        if self.get(tenant_id, item_type, preset) is not None:
            raise AttributeDefinitionConflictError(
                [
                    f"Global attribute definition for '{item_type}/{preset}' "
                    f"is already initialized"
                ]
            )
        payload = validate_definition_json({"attributes": attributes})
        return GlobalAttributeDefinition.unscoped.create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            definition_json=payload,
        )

    def reinitialize(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> tuple[GlobalAttributeDefinition, int]:
        """Overwrite an existing global definition wholesale, then propagate.

        The escape hatch for a row :meth:`initialize` got wrong. ``update()``
        cannot repair such a row: dropping a bogus ``kind="core"`` attribute is
        "a core attribute may not be removed", and relaxing a bogus
        ``locked=True`` one is "not changeable on a locked attribute" — correct
        rules that, applied to a bad seed, lock the mistake in forever with no
        API path back.

        Skips ``validate_meta_only_change`` on purpose (that is the whole
        point) but still runs the full structural validation, so the
        replacement itself cannot be malformed. Exposed to operators through
        ``manage.py bootstrap_attribute_definitions --reset``, not through
        REST/MCP: it is a recovery tool, not a normal edit.

        Returns:
            ``(row, propagated_workspace_count)``.

        Raises:
            AttributeDefinitionNotFound: no row for that key — use
                :meth:`initialize`.
            AttributeSchemaError: unknown key or malformed *attributes*.
        """
        validate_definition_key(item_type, preset)
        obj = self.get(tenant_id, item_type, preset)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        payload = validate_definition_json({"attributes": attributes})
        with transaction.atomic():
            obj.definition_json = payload
            obj.version = F("version") + 1
            obj.save(update_fields=["definition_json", "version", "modified_at"])
            obj.refresh_from_db(fields=["version"])
            propagated = self._propagate(obj)
        return obj, propagated

    def update(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> tuple[GlobalAttributeDefinition, int]:
        """Replace the attribute list, bump ``version``, propagate.

        Returns:
            ``(row, propagated_workspace_count)``.

        Raises:
            AttributeDefinitionNotFound: no global row for that key.
            AttributeSchemaError: malformed payload, or a change that the
                core-lock / ``locked`` rules forbid.
        """
        obj = self.get(tenant_id, item_type, preset)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        payload = validate_definition_json({"attributes": attributes})
        # Ledger item (e): the STORED row is normalized before it is used as a
        # dict of required keys. ``validate_meta_only_change`` indexes
        # ``old["kind"]``/``old["locked"]``/``old[prop]``, so a row predating a
        # key (or restored from an older backup) raised a bare KeyError → 500
        # on an admin PUT. Now it degrades to the 400 the view already renders.
        old = stored_attributes(obj.definition_json)
        validate_meta_only_change(old, payload["attributes"])

        with transaction.atomic():
            obj.definition_json = payload
            # Ledger binding (j): bump the optimistic-lock counter with an
            # atomic F() expression, not a read-modify-write on the in-memory
            # value — two concurrent PUTs (Task 10 wires the REST layer that
            # makes this reachable from two clients at once) would otherwise
            # both compute the same "old + 1" and one increment is lost.
            # ``refresh_from_db`` is load-bearing: without it ``obj.version``
            # stays the unresolved ``F()`` expression object, and every
            # caller of ``update()`` reads ``row.version`` off the returned
            # object (``_global_payload`` on the REST response).
            obj.version = F("version") + 1
            obj.save(update_fields=["definition_json", "version", "modified_at"])
            obj.refresh_from_db(fields=["version"])
            propagated = self._propagate(obj)
        return obj, propagated

    # ---------- Propagation ----------

    def _propagate(self, obj: GlobalAttributeDefinition) -> int:
        """Copy ``definition_json`` into every non-customized derived row.

        ``copy.deepcopy`` is load-bearing: without it every derived row would
        share one mutable dict with the global, so an in-place edit on one row
        would silently rewrite the tenant default and all of its siblings.

        The bulk ``.update()`` also bumps ``version``/``modified_at`` itself
        (it bypasses ``Model.save()``, so ``auto_now`` never fires and nothing
        else would bump the optimistic-lock counter for these rows).

        The row filter comes from :meth:`_derived_row_filter`, shared with
        :meth:`list_derived_workspace_ids`: both must describe the exact same
        row set (the cache-invalidation targets have to match what actually
        got rewritten), so the predicate lives in one place instead of two
        copies that can silently drift (code review Task 7 I-1/I-3).
        """
        return WorkspaceAttributeDefinition.unscoped.filter(
            **self._derived_row_filter(obj)
        ).update(
            definition_json=copy.deepcopy(obj.definition_json),
            version=F("version") + 1,
            modified_at=timezone.now(),
        )

    @staticmethod
    def _derived_row_filter(obj: GlobalAttributeDefinition) -> dict[str, Any]:
        """Filter kwargs for every non-customized workspace row derived from *obj*.

        ``tenant_id`` is filtered explicitly (not just implied by
        ``source_global_id``): without it a workspace row belonging to a
        different tenant than ``obj`` could be matched if it ever pointed at
        this global row's id.

        ``preset`` is part of the derived row's identity, so the filter narrows
        on it too: a standard-preset edit must never match a minimal-preset
        workspace that happens to point at a stale ``source_global``.
        """
        return dict(
            tenant_id=obj.tenant_id,
            source_global_id=obj.id,
            preset=obj.preset,
            is_customized=False,
        )

    def list_derived_workspace_ids(
        self, obj: GlobalAttributeDefinition
    ) -> list[str]:
        """Workspace ids whose definition mirrors *obj* — the cache-drop targets.

        A bulk ``QuerySet.update()`` bypasses ``save()``/signals, so the shared
        cache is not invalidated by the propagation itself; callers walk this
        list explicitly (the same lesson as
        ``GlobalWorkflowDefinitionStore._propagate``).
        """
        return [
            str(ws_id)
            for ws_id in WorkspaceAttributeDefinition.unscoped.filter(
                **self._derived_row_filter(obj)
            ).values_list("workspace_id", flat=True)
        ]


__all__ = [
    "AttributeDefinitionConflictError",
    "AttributeDefinitionNotFound",
    "GlobalAttributeDefinitionStore",
]
