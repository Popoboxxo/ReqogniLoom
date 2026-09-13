"""AttributeCatalogService — Layer-2 facade for the central attribute catalog.

Attribut v3 WS5 (#942, spec section 8). The catalog is an item-type-independent
template library per tenant: :class:`~persistence.models.AttributeCatalogEntry`
stores one normalized ``kind="extended"`` attribute block plus display and
provenance metadata.

ADR-01: REST views and MCP handlers never touch
``persistence.models.AttributeCatalogEntry`` directly; every read and write
goes through this class. Applying an entry to a definition
(:meth:`add_to_definition`) is an explicit one-shot *copy*: the catalog is a
template, not a hard binding, so later edits to an entry never reach a
definition that already consumed it — "Re-Apply" is a separate user action.

Permission model mirrors ``AttributeDefinitionService``'s management half: the
catalog is tenant-wide configuration, so every operation requires ``admin``.

Audit: every mutation writes ``AuditEntry.OP_CREATE`` / ``AuditEntry.OP_UPDATE``
inside the same transaction (REQ-L2-AS-019).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from attribute_definitions.schema import (
    AttributeSchemaError,
    ITEM_TYPES,
    normalize_attribute,
    validate_definition_key,
)
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
)
from application.base import ServiceBase

logger = logging.getLogger(__name__)

#: Bumped only if the catalog export document's shape changes in a way
#: :meth:`AttributeCatalogService.import_catalog` cannot read compatibly.
_CATALOG_SCHEMA_VERSION = 1

_ON_COLLISION_CHOICES = frozenset({"skip", "overwrite", "rename"})


class AttributeCatalogNotFound(NotFoundError):
    """No catalog entry with the given id in the active tenant."""


class AttributeCatalogService(ServiceBase):
    """Read, manage and apply tenant attribute-catalog entries."""

    def __init__(
        self, definition_service: AttributeDefinitionService | None = None
    ) -> None:
        self._definitions = definition_service or AttributeDefinitionService()

    # ---- Normalization helpers -------------------------------------------

    @staticmethod
    def _normalize_name(name: Any) -> str:
        clean = str(name).strip() if name is not None else ""
        if not clean:
            raise AttributeSchemaError(["'name' is required"])
        if len(clean) > 64:
            raise AttributeSchemaError(["'name' must be at most 64 characters"])
        return clean

    @staticmethod
    def _normalize_definition(raw: Any) -> dict[str, Any]:
        """Validate and normalize one extended attribute block.

        The stored block is the exact shape ``normalize_attribute`` produces.
        Only ``kind="extended"`` is accepted: a catalog entry is a reusable
        template, and a ``core`` attribute's identity is fixed by the Django
        model, so it can never be introduced by a copy.
        """
        if not isinstance(raw, dict):
            raise AttributeSchemaError(["definition must be an object"])
        normalized = normalize_attribute(raw)
        if normalized["kind"] != "extended":
            raise AttributeSchemaError(
                ["definition must be a kind='extended' attribute block"]
            )
        return normalized

    @staticmethod
    def _normalize_tags(tags: Any) -> list[str]:
        if tags is None:
            return []
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise AttributeSchemaError(["'tags' must be a list of non-empty strings"])
        return [tag.strip() for tag in tags]

    @staticmethod
    def _normalize_i18n(value: Any, key: str) -> dict[str, str]:
        """Coerce ``{de, en}`` metadata to its canonical two-key shape."""
        if value is None:
            return {"de": "", "en": ""}
        if not isinstance(value, dict):
            raise AttributeSchemaError([f"'{key}' must be an object with 'de' and 'en'"])
        extra = sorted(set(value) - {"de", "en"})
        if extra:
            raise AttributeSchemaError(
                [f"'{key}' has unknown key(s): {', '.join(extra)}"]
            )
        return {
            "de": str(value.get("de") or ""),
            "en": str(value.get("en") or ""),
        }

    # ---- Payloads ---------------------------------------------------------

    @staticmethod
    def _entry_payload(entry: Any) -> dict[str, Any]:
        """Transport-safe projection of a catalog entry (MCP uses stdlib JSON)."""
        return {
            "id": str(entry.id),
            "name": entry.name,
            "definition": entry.definition,
            "category": entry.category,
            "tags": list(entry.tags or []),
            "label": dict(entry.label or {}),
            "help_text": dict(entry.help_text or {}),
            "origin": entry.origin,
            "deprecated": bool(entry.deprecated),
            "version": entry.version,
            "created_at": entry.created_at.isoformat(),
            "modified_at": entry.modified_at.isoformat(),
        }

    @staticmethod
    def _entry_document(entry: Any) -> dict[str, Any]:
        """Export/import projection — everything but storage metadata."""
        return {
            "name": entry.name,
            "definition": entry.definition,
            "category": entry.category,
            "tags": list(entry.tags or []),
            "label": dict(entry.label or {}),
            "help_text": dict(entry.help_text or {}),
            "origin": entry.origin,
            "deprecated": bool(entry.deprecated),
        }

    # ---- Read -------------------------------------------------------------

    def list_entries(
        self,
        ctx: AuthContext,
        *,
        query: str | None = None,
        category: str | None = None,
        tags: Iterable[str] | None = None,
        include_deprecated: bool = False,
    ) -> list[dict[str, Any]]:
        """List the tenant's catalog entries, optionally filtered.

        Args:
            query: Optional case-insensitive substring of ``name``.
            category: Optional exact category filter.
            tags: Optional tags; every given tag must be present (AND).
            include_deprecated: Include deprecated entries (default: no).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        return [self._entry_payload(e) for e in self._entries_queryset(
            query=query, category=category, tags=tags,
            include_deprecated=include_deprecated,
        )]

    def search_entries(
        self,
        ctx: AuthContext,
        *,
        query: str,
        category: str | None = None,
        tags: Iterable[str] | None = None,
        include_deprecated: bool = False,
    ) -> list[dict[str, Any]]:
        """Search the catalog by a required ``name`` substring (+ filters)."""
        if not query or not str(query).strip():
            raise AttributeSchemaError(["'query' is required for a catalog search"])
        return self.list_entries(
            ctx,
            query=query,
            category=category,
            tags=tags,
            include_deprecated=include_deprecated,
        )

    def get_entry(self, ctx: AuthContext, entry_id: Any) -> dict[str, Any]:
        """Return one catalog entry by id (404 as :class:`AttributeCatalogNotFound`)."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        return self._entry_payload(self._get_entry(entry_id))

    def _entries_queryset(
        self,
        *,
        query: str | None,
        category: str | None,
        tags: Iterable[str] | None,
        include_deprecated: bool,
    ) -> Any:
        from persistence.models import AttributeCatalogEntry

        qs = AttributeCatalogEntry.objects.all()
        if not include_deprecated:
            qs = qs.filter(deprecated=False)
        if category:
            qs = qs.filter(category=category)
        if query:
            qs = qs.filter(name__icontains=str(query).strip())
        for tag in tags or ():
            # JSONB array containment: the entry's tags must contain this tag.
            qs = qs.filter(tags__contains=[tag])
        return qs.order_by("name")

    def _get_entry(self, entry_id: Any) -> Any:
        from persistence.models import AttributeCatalogEntry

        try:
            identifier = UUID(str(entry_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AttributeCatalogNotFound(f"Catalog entry {entry_id!r} not found") from exc
        entry = AttributeCatalogEntry.objects.filter(id=identifier).first()
        if entry is None:
            raise AttributeCatalogNotFound(f"Catalog entry {entry_id} not found")
        return entry

    # ---- Write ------------------------------------------------------------

    def create_entry(
        self,
        ctx: AuthContext,
        *,
        name: str,
        definition: dict[str, Any],
        category: str = "",
        tags: list[str] | None = None,
        label: dict[str, str] | None = None,
        help_text: dict[str, str] | None = None,
        origin: str = "",
    ) -> dict[str, Any]:
        """Create a catalog entry.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeSchemaError: duplicate name, or a malformed definition /
                metadata block.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        clean_name = self._normalize_name(name)
        block = self._normalize_definition(definition)
        clean_tags = self._normalize_tags(tags)
        clean_label = self._normalize_i18n(label, "label")
        clean_help = self._normalize_i18n(help_text, "help_text")

        from persistence.models import AttributeCatalogEntry

        with transaction.atomic():
            if AttributeCatalogEntry.objects.filter(name=clean_name).exists():
                raise AttributeSchemaError(
                    [f"catalog entry '{clean_name}' already exists"]
                )
            try:
                with transaction.atomic():
                    entry = AttributeCatalogEntry.objects.create(
                        tenant_id=ctx.tenant_id,
                        name=clean_name,
                        definition=block,
                        category=category or "",
                        tags=clean_tags,
                        label=clean_label,
                        help_text=clean_help,
                        origin=origin or "",
                    )
            except IntegrityError as exc:
                # Concurrent create won the unique-index race.
                raise AttributeSchemaError(
                    [f"catalog entry '{clean_name}' already exists"]
                ) from exc
            self._audit(
                ctx,
                operation=AuditEntry.OP_CREATE,
                entity_type="AttributeCatalogEntry",
                entity_id=entry.id,
                details={"name": clean_name, "category": category or ""},
            )
        return self._entry_payload(entry)

    def update_entry(
        self,
        ctx: AuthContext,
        entry_id: Any,
        *,
        name: str | None = None,
        definition: dict[str, Any] | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        label: dict[str, str] | None = None,
        help_text: dict[str, str] | None = None,
        origin: str | None = None,
        deprecated: bool | None = None,
    ) -> dict[str, Any]:
        """Partially update a catalog entry.

        ``None`` means "leave unchanged" — an omitted field is never coerced to
        an empty value. Existing definitions are *not* re-applied by this:
        consumers keep the copy they already received (spec section 8).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        entry = self._get_entry(entry_id)

        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = self._normalize_name(name)
        if definition is not None:
            updates["definition"] = self._normalize_definition(definition)
        if category is not None:
            updates["category"] = category
        if tags is not None:
            updates["tags"] = self._normalize_tags(tags)
        if label is not None:
            updates["label"] = self._normalize_i18n(label, "label")
        if help_text is not None:
            updates["help_text"] = self._normalize_i18n(help_text, "help_text")
        if origin is not None:
            updates["origin"] = origin
        if deprecated is not None:
            updates["deprecated"] = bool(deprecated)

        if not updates:
            return self._entry_payload(entry)

        if "name" in updates and updates["name"] != entry.name:
            if self._qs().filter(name=updates["name"]).exclude(pk=entry.pk).exists():
                raise AttributeSchemaError(
                    [f"catalog entry '{updates['name']}' already exists"]
                )

        with transaction.atomic():
            try:
                with transaction.atomic():
                    self._qs().filter(pk=entry.pk).update(
                        **updates,
                        version=F("version") + 1,
                        modified_at=timezone.now(),
                    )
            except IntegrityError as exc:
                raise AttributeSchemaError(
                    [f"catalog entry '{updates.get('name', entry.name)}' already exists"]
                ) from exc
            entry.refresh_from_db()
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="AttributeCatalogEntry",
                entity_id=entry.id,
                details={"name": entry.name, "fields": sorted(updates)},
            )
        return self._entry_payload(entry)

    def deprecate_entry(
        self, ctx: AuthContext, entry_id: Any, *, deprecated: bool = True
    ) -> dict[str, Any]:
        """Mark a catalog entry deprecated (or lift the flag with ``False``)."""
        return self.update_entry(ctx, entry_id, deprecated=deprecated)

    @staticmethod
    def _qs() -> Any:
        from persistence.models import AttributeCatalogEntry

        return AttributeCatalogEntry.objects.all()

    # ---- Apply to a definition -------------------------------------------

    def add_to_definition(
        self,
        ctx: AuthContext,
        entry_id: Any,
        item_type: str,
        *,
        preset: str | None = None,
        workspace_id: UUID | None = None,
        on_collision: str = "skip",
    ) -> dict[str, Any]:
        """Copy an entry's attribute block into a definition (explicit one-shot).

        Exactly one of *preset* (global scope) / *workspace_id* (workspace
        scope) must be given, same contract as
        ``AttributeDefinitionService.import_definition``. Name collisions are
        resolved through that service's existing ``_merge_import`` logic
        (``skip``/``overwrite``/``rename``); everything is validated by the
        normal update path.

        Returns:
            ``{"definition": <updated payload>, "catalog_entry_id": ...,
            "on_collision": ...}``.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeCatalogNotFound: no such catalog entry.
            AttributeDefinitionNotFound: no definition exists yet to copy into.
            AttributeSchemaError: malformed parameters, an unknown item type, or
                a definition the merge rejects (e.g. a reserved name).
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        if on_collision not in _ON_COLLISION_CHOICES:
            raise AttributeSchemaError(
                [f"on_collision must be one of {sorted(_ON_COLLISION_CHOICES)}"]
            )
        if item_type not in ITEM_TYPES:
            raise AttributeSchemaError(
                [f"unknown item_type '{item_type}'; expected one of {list(ITEM_TYPES)}"]
            )
        entry = self._get_entry(entry_id)

        if workspace_id is not None:
            current = self._definitions.resolve(ctx, item_type, workspace_id)
        elif preset is not None:
            validate_definition_key(item_type, preset)
            current = self._definitions.get_global(ctx, item_type, preset)
            if not current.get("initialized", False):
                raise AttributeDefinitionNotFound(
                    f"No global attribute definition for '{item_type}/{preset}'"
                )
        else:
            raise AttributeSchemaError(
                ["add_to_definition requires either preset or workspace_id"]
            )

        merged = AttributeDefinitionService._merge_import(
            current["attributes"],
            [entry.definition],
            on_collision,
            reserved_field_names=AttributeDefinitionService._model_field_names(item_type),
        )
        if workspace_id is not None:
            updated = self._definitions.update_workspace(
                ctx, item_type, workspace_id, merged
            )
        elif preset is not None:
            updated = self._definitions.update_global(ctx, item_type, preset, merged)
        else:  # pragma: no cover - unreachable, guarded above
            raise AttributeSchemaError(
                ["add_to_definition requires either preset or workspace_id"]
            )
        return {
            "definition": updated,
            "catalog_entry_id": str(entry.id),
            "on_collision": on_collision,
        }

    # ---- Export / Import --------------------------------------------------

    def export_catalog(
        self, ctx: AuthContext, *, include_deprecated: bool = True
    ) -> dict[str, Any]:
        """Serialize the tenant's catalog for download / migration.

        ``schema_version`` lets :meth:`import_catalog` detect a future format
        change instead of silently misreading an old export.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        from persistence.models import AttributeCatalogEntry

        qs = AttributeCatalogEntry.objects.all()
        if not include_deprecated:
            qs = qs.filter(deprecated=False)
        return {
            "schema_version": _CATALOG_SCHEMA_VERSION,
            "document_type": "attribute_catalog",
            "entries": [self._entry_document(e) for e in qs.order_by("name")],
        }

    def import_catalog(
        self,
        ctx: AuthContext,
        payload: dict[str, Any],
        *,
        on_collision: str = "skip",
    ) -> dict[str, Any]:
        """Merge a previously exported catalog document into this tenant.

        Collision handling reuses ``AttributeDefinitionService._merge_import``
        on the entry documents (both carry a ``name`` key), so
        ``skip``/``overwrite``/``rename`` behave exactly like a definition
        import. Import is additive: entries absent from the document are left
        untouched (never deleted).

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeSchemaError: *on_collision* is invalid, ``schema_version``
                is missing/unrecognized, ``entries`` is not a list, or an
                entry's name/definition/tags/label/help_text is malformed.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        if on_collision not in _ON_COLLISION_CHOICES:
            raise AttributeSchemaError(
                [f"on_collision must be one of {sorted(_ON_COLLISION_CHOICES)}"]
            )
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != _CATALOG_SCHEMA_VERSION
        ):
            raise AttributeSchemaError(
                [f"unrecognized or missing schema_version (expected {_CATALOG_SCHEMA_VERSION})"]
            )
        incoming = payload.get("entries")
        if not isinstance(incoming, list):
            raise AttributeSchemaError(["payload must have an 'entries' list"])

        from persistence.models import AttributeCatalogEntry

        current_rows = list(AttributeCatalogEntry.objects.all().order_by("name"))
        current_docs = [self._entry_document(row) for row in current_rows]
        merged = AttributeDefinitionService._merge_import(
            current_docs, incoming, on_collision
        )
        # Validate every merged document before any write, so a malformed entry
        # later in the list cannot leave a half-imported catalog behind.
        normalized = [self._normalize_document(doc) for doc in merged]
        by_name = {row.name: row for row in current_rows}

        created = 0
        updated = 0
        with transaction.atomic():
            for clean in normalized:
                existing = by_name.get(clean["name"])
                if existing is None:
                    created += 1
                    entry = AttributeCatalogEntry.objects.create(
                        tenant_id=ctx.tenant_id, **clean
                    )
                    self._audit(
                        ctx,
                        operation=AuditEntry.OP_CREATE,
                        entity_type="AttributeCatalogEntry",
                        entity_id=entry.id,
                        details={"name": entry.name, "imported": True},
                    )
                    by_name[entry.name] = entry
                elif self._entry_document(existing) != clean:
                    updated += 1
                    self._qs().filter(pk=existing.pk).update(
                        **clean,
                        version=F("version") + 1,
                        modified_at=timezone.now(),
                    )
                    existing.refresh_from_db()
                    self._audit(
                        ctx,
                        operation=AuditEntry.OP_UPDATE,
                        entity_type="AttributeCatalogEntry",
                        entity_id=existing.id,
                        details={"name": existing.name, "imported": True},
                    )
        return {"created": created, "updated": updated, "total": len(merged)}

    def _normalize_document(self, doc: Any) -> dict[str, Any]:
        if not isinstance(doc, dict):
            raise AttributeSchemaError(["catalog entry must be an object"])
        return {
            "name": self._normalize_name(doc.get("name")),
            "definition": self._normalize_definition(doc.get("definition")),
            "category": str(doc.get("category") or ""),
            "tags": self._normalize_tags(doc.get("tags")),
            "label": self._normalize_i18n(doc.get("label"), "label"),
            "help_text": self._normalize_i18n(doc.get("help_text"), "help_text"),
            "origin": str(doc.get("origin") or ""),
            "deprecated": bool(doc.get("deprecated", False)),
        }


__all__ = [
    "AttributeCatalogNotFound",
    "AttributeCatalogService",
]
