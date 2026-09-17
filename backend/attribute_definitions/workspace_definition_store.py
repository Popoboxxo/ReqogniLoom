"""Store for the per-workspace materialized attribute definitions.

Materialize-on-first-read: a workspace that has never been resolved gets a full
deep copy of its preset's global default, linked back via ``source_global`` with
``is_customized=False``. Every later global edit then reaches it through
``GlobalAttributeDefinitionStore._propagate`` — no merge-on-read on the form
load path.

Preset changes re-materialize inherited definitions. Customized definitions keep
their complete payload if all referenced attributes exist in the target preset
(spec section 9); otherwise resolution raises an explicit conflict without
changing the row. This supersedes section 3's creation-time preset freeze: a
resolved definition must never silently claim a different tier (#960).
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from .models import WorkspaceAttributeDefinition
from .schema import (
    AttributeDefinitionConflictError,
    materialize_sections,
    stored_attributes,
    validate_definition_json,
    validate_meta_only_change,
)


class WorkspaceAttributeDefinitionStore:
    """Resolve / override / reset per-workspace attribute definitions."""

    def __init__(self, global_store: GlobalAttributeDefinitionStore | None = None) -> None:
        self._global_store = global_store or GlobalAttributeDefinitionStore()

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, workspace_id: UUID | str, item_type: str
    ) -> WorkspaceAttributeDefinition | None:
        """Return the workspace row or None (no materialization).

        Deliberately NOT sections-materializing here — same reasoning as
        ``GlobalAttributeDefinitionStore.get()``: ``update()`` calls this
        internally as a plain lookup, and a hidden version bump inside it
        would land an untracked extra increment on every write. ``resolve()``
        below calls :meth:`ensure_sections` explicitly on the row it returns.
        """
        return WorkspaceAttributeDefinition.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id, item_type=item_type
        ).first()

    @staticmethod
    def ensure_sections(obj: WorkspaceAttributeDefinition) -> None:
        """Backfill ``definition_json['sections']`` in place if missing (Task 7).

        Same reasoning as ``GlobalAttributeDefinitionStore.ensure_sections``
        (see its docstring).
        """
        if isinstance(obj.definition_json, dict) and "sections" in obj.definition_json:
            return
        attributes = stored_attributes(obj.definition_json)
        base = obj.definition_json if isinstance(obj.definition_json, dict) else {"attributes": []}
        obj.definition_json = {**base, "sections": materialize_sections(attributes)}
        obj.version = F("version") + 1
        obj.save(update_fields=["definition_json", "version", "modified_at"])
        obj.refresh_from_db(fields=["version"])

    def resolve(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        preset: str,
    ) -> WorkspaceAttributeDefinition:
        """Resolve the requested preset, preserving compatible customizations.

        Uncustomized rows are re-copied on a preset change. Customized rows
        retain their payload and adopt the target source only if its attribute
        names cover the override (the same rule as the downgrade probe).

        Raises:
            AttributeDefinitionNotFound: no global default exists for
                ``(item_type, preset)`` — run the bootstrap command first.
            AttributeDefinitionConflictError: the target preset lacks attributes
                used by a customization; the existing row is left untouched.
        """
        existing = self.get(tenant_id, workspace_id, item_type)
        if existing is not None and existing.preset == preset:
            self.ensure_sections(existing)
            return existing

        source = self._global_store.get(tenant_id, item_type, preset)
        if source is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}' — "
                f"run 'manage.py bootstrap_attribute_definitions' first"
            )
        self._global_store.ensure_sections(source)
        with transaction.atomic():
            # Also lock a get_or_create race winner: another reader may have
            # materialized a different preset, or an admin may have customized
            # the row after our first lookup. Never overwrite that work.
            obj, _created = (
                WorkspaceAttributeDefinition.unscoped.select_for_update().get_or_create(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    item_type=item_type,
                    defaults={
                        "preset": preset,
                        "definition_json": copy.deepcopy(source.definition_json),
                        "source_global": source,
                        "is_customized": False,
                    },
                )
            )
            if obj.preset != preset:
                if obj.is_customized:
                    missing = self._missing_attribute_names(
                        obj.definition_json, source.definition_json
                    )
                    if missing:
                        raise AttributeDefinitionConflictError([
                            f"Customized definition '{item_type}' uses preset "
                            f"'{obj.preset}', but workspace requests '{preset}'; "
                            f"target preset lacks: {', '.join(missing)}. "
                            "Reconcile the customization or explicitly reset it."
                        ])
                    # Section 9 preserves the whole override, not a guessed
                    # per-field diff (there is no historical base snapshot).
                    definition = obj.definition_json
                else:
                    definition = copy.deepcopy(source.definition_json)
                WorkspaceAttributeDefinition.unscoped.filter(pk=obj.pk).update(
                    preset=preset,
                    source_global=source,
                    definition_json=definition,
                    version=F("version") + 1,
                    modified_at=timezone.now(),
                )
                obj.refresh_from_db()
            self.ensure_sections(obj)
            return obj

    # ---------- Write ----------

    def update(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        attributes: list[dict[str, Any]],
        sections: list[dict[str, Any]] | None = None,
        section_flow: list[dict[str, Any]] | None = None,
    ) -> WorkspaceAttributeDefinition:
        """Persist a workspace override and flip ``is_customized`` to True.

        *sections*/*section_flow* are optional — see
        ``GlobalAttributeDefinitionStore.update()``'s identical parameters.

        Raises:
            AttributeDefinitionNotFound: the workspace has never been resolved.
            AttributeSchemaError: malformed payload or a forbidden core/locked
                change.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No attribute definition resolved for '{item_type}' in "
                f"workspace {workspace_id}"
            )
        raw_payload: dict[str, Any] = {"attributes": attributes}
        if sections is not None:
            raw_payload["sections"] = sections
        if section_flow is not None:
            raw_payload["section_flow"] = section_flow
        payload = validate_definition_json(raw_payload)
        # Ledger item (e): normalize the stored row before it is indexed as a
        # dict of required keys — see global_definition_store.update() for the
        # KeyError→500 this replaces with a 400.
        old = stored_attributes(obj.definition_json)
        validate_meta_only_change(old, payload["attributes"])

        # Task 7/8 + WS4: carry the existing 'sections'/'section_flow' lists
        # over when the caller didn't send one — see
        # GlobalAttributeDefinitionStore.update()'s identical comment for why
        # (definition_json is replaced wholesale).
        if (
            "sections" not in payload
            and isinstance(obj.definition_json, dict)
            and "sections" in obj.definition_json
        ):
            payload["sections"] = obj.definition_json["sections"]
        if (
            "section_flow" not in payload
            and isinstance(obj.definition_json, dict)
            and "section_flow" in obj.definition_json
        ):
            payload["section_flow"] = obj.definition_json["section_flow"]

        obj.definition_json = payload
        obj.is_customized = True
        # Ledger binding (j): F() expression, not a read-modify-write — see
        # global_definition_store.update() for the concurrent-writer race this
        # avoids. refresh_from_db is load-bearing: the caller (the REST PUT
        # response, via AttributeDefinitionService._workspace_payload) reads
        # obj.version right after this call.
        obj.version = F("version") + 1
        obj.save(
            update_fields=["definition_json", "is_customized", "version", "modified_at"]
        )
        obj.refresh_from_db(fields=["version"])
        return obj

    def reset(
        self, tenant_id: UUID | str, workspace_id: UUID | str, item_type: str
    ) -> WorkspaceAttributeDefinition:
        """Discard the override and re-copy the global default.

        Raises:
            AttributeDefinitionNotFound: the workspace has no row, or its
                ``source_global`` link is gone (the global was deleted), in
                which case there is nothing to reset TO.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No attribute definition resolved for '{item_type}' in "
                f"workspace {workspace_id}"
            )
        source = obj.source_global
        if source is None:
            raise AttributeDefinitionNotFound(
                f"Attribute definition for '{item_type}' in workspace "
                f"{workspace_id} has no global source to reset to"
            )
        self._global_store.ensure_sections(source)
        obj.definition_json = copy.deepcopy(source.definition_json)
        obj.is_customized = False
        # Ledger binding (j): see update() above for why this is F(), not
        # read-modify-write, and why refresh_from_db follows it.
        obj.version = F("version") + 1
        obj.save(
            update_fields=["definition_json", "is_customized", "version", "modified_at"]
        )
        obj.refresh_from_db(fields=["version"])
        return obj

    # ---------- Preset downgrade probe ----------

    def missing_attributes_for_preset(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        target_preset: str,
    ) -> list[str]:
        """Return the attribute names the workspace uses that *target_preset* lacks.

        Feeds the warning list of ``presets.services.validate_downgrade`` — the
        spec (section 9) explicitly reuses that check rather than inventing a
        second one. An empty list means the override survives the switch.

        Raises:
            AttributeDefinitionNotFound: *target_preset* has never been
                bootstrapped for *item_type* — same condition, same exception
                as ``resolve()``. Ledger binding (i), Task 5 review I-2: this
                used to silently degrade to the empty set, which reported
                every current attribute as "will be lost" — the maximally
                alarming wrong answer for what is actually "nobody has
                configured the target preset yet", a caller-fixable setup
                gap rather than data loss.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            return []
        target = self._global_store.get(tenant_id, item_type, target_preset)
        if target is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{target_preset}' — "
                f"run 'manage.py bootstrap_attribute_definitions' first"
            )
        # Ledger item (e), third site in this file: both rows are stored rows
        # being indexed by a required key, so both go through the same
        # normalization as update() above.
        return self._missing_attribute_names(obj.definition_json, target.definition_json)

    @staticmethod
    def _missing_attribute_names(current: Any, target: Any) -> list[str]:
        """Use the same compatibility rule for the warning and resolution."""
        target_names = {a["name"] for a in stored_attributes(target)}
        current_names = {a["name"] for a in stored_attributes(current)}
        return sorted(current_names - target_names)

    def resolved_item_types(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> list[str]:
        """Item types this workspace has already materialized a definition for."""
        return sorted(
            WorkspaceAttributeDefinition.unscoped.filter(
                tenant_id=tenant_id, workspace_id=workspace_id
            ).values_list("item_type", flat=True)
        )


__all__ = ["WorkspaceAttributeDefinitionStore"]
