"""COMP-AS-050 SavedViewService / TableViewStateService — table views (slice 3).

leaf_id : COMP-AS-050
req_id  : REQ-L2-PL-004, REQ-L2-AS-001, REQ-L2-AS-021

The single write entry point (ADR-01) for the two table-view tables of
``docs/superpowers/plans/2026-11-04-tabellenansicht-neu.md`` slice 3:

* :class:`SavedViewService` — a named, shareable view of one artifact type
  (columns, filters, sort) plus :meth:`apply`, which runs the stored documents
  through the slice-1 table query service
  (:mod:`application.table_query_service` / :mod:`application.table_filter_dsl`).
* :class:`TableViewStateService` — the per-user "where I was last" state, one
  row per ``(user, workspace, item_type)``, upserted.

Validation split (deliberate, spec §4.1 + plan Task 3.2):

* A **saved view** is validated when written: ``filters`` and ``sort`` go
  through the DSL, so an unknown field is refused with ``ValidationError``
  instead of producing an empty table weeks later.
* The **per-user state** is *not* validated against the attribute definition.
  It is layout memory; a column whose attribute disappeared must still load.
  Only shape and size caps apply (:data:`MAX_STATE_BYTES`,
  :data:`MAX_COLUMNS`).

``apply`` is fail-soft (plan Review Focus 4): a stored filter that no longer
compiles — an attribute removed from the definition, an enum value that no
longer exists — answers an **empty result plus a warning naming the field**,
never a 500. That is the difference between "your view is stale" and "the
server is broken".

Permission model:
  * list/read: any role (the workspace fence already ran in the transport).
  * create/update/delete: write role *and* — for update/delete — owner or
    workspace admin (``ROLE_ADMIN`` in the request-scoped role set).
  * a ``private`` view of another user is answered as ``NotFoundError`` (404),
    not 403: whether it exists is not the caller's business.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import IntegrityError
from django.db.models import F, Q

from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from application.table_filter_dsl import TABLE_ITEM_TYPES, compile_filters, compile_sort
from application.table_query_service import TableQueryService
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_ADMIN
from persistence.models import SavedView, Tenant, UserTableViewState, Workspace
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

#: Entity names used in audit entries.
SAVED_VIEW_ITEM_TYPE = "SavedView"
TABLE_VIEW_STATE_ITEM_TYPE = "UserTableViewState"

#: Visibility values a client may send.
VISIBILITIES: frozenset[str] = frozenset({"private", "workspace"})

#: Size cap for one stored layout document set, in bytes (plan Task 3.2).
MAX_STATE_BYTES: int = 32 * 1024

#: Column cap for both tables.
MAX_COLUMNS: int = 200

#: Default layout for a user without stored state.
EMPTY_STATE: dict[str, Any] = {"columns": [], "filters": {}, "sort": []}


class _Unset:
    """Sentinel for "argument not given" on the partial update path."""

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<unset>"


_UNSET = _Unset()


@dataclass(frozen=True)
class SavedViewDTO:
    """Wire/DTO form of one saved view (REST and MCP share it)."""

    id: UUID
    workspace_id: UUID
    item_type: str
    owner_id: UUID
    name: str
    columns: list[Any]
    filters: dict[str, Any]
    sort: list[Any]
    visibility: str
    version: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "item_type": self.item_type,
            "owner_id": str(self.owner_id),
            "name": self.name,
            "columns": self.columns,
            "filters": self.filters,
            "sort": self.sort,
            "visibility": self.visibility,
            "version": self.version,
        }


@dataclass(frozen=True)
class SavedViewApplyResult:
    """Outcome of :meth:`SavedViewService.apply`.

    ``rows`` are the table rows
    (:meth:`application.table_query_service.TableQueryService.serialize_rows`);
    ``warnings`` names every reason the stored documents could not be honoured.
    A stale view is therefore a 200 with an empty result *and* an explanation,
    never an error.
    """

    rows: list[dict[str, Any]]
    warnings: list[str]
    view: SavedViewDTO


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------


def _clean_name(name: Any) -> str:
    if not isinstance(name, str):
        raise ValidationError("Saved view name must be a string")
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Saved view name is required")
    if len(cleaned) > 255:
        raise ValidationError("Saved view name must be at most 255 characters")
    return cleaned


def _clean_visibility(visibility: Any) -> str:
    if visibility not in VISIBILITIES:
        allowed = ", ".join(sorted(VISIBILITIES))
        raise ValidationError(
            f"Unknown visibility {visibility!r}; expected one of {allowed}"
        )
    return str(visibility)


def _clean_columns(columns: Any) -> list[Any]:
    """Validate the *shape* of a column list (never its field names).

    A column whose attribute has since been removed must stay loadable — the
    same reason the per-user state is unvalidated. Reordering and order numbers
    are the client's business; only the container shape and the cap are ours.
    """
    if columns is None:
        return []
    if not isinstance(columns, list):
        raise ValidationError("'columns' must be a list")
    if len(columns) > MAX_COLUMNS:
        raise ValidationError(f"'columns' accepts at most {MAX_COLUMNS} entries")
    for entry in columns:
        if not isinstance(entry, dict) or not isinstance(entry.get("field"), str):
            raise ValidationError(
                "Each column must be an object with a string 'field'"
            )
    return columns


def _clean_filters(
    ctx: AuthContext,
    workspace_id: UUID,
    item_type: str,
    filters: Any,
    attributes: list[dict[str, Any]],
) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValidationError("'filters' must be an object")
    # Compiling validates without executing: unknown field/operator/type raise.
    compile_filters(
        item_type,
        attributes,
        filters,
        tenant_id=ctx.tenant_id,
        workspace_id=workspace_id,
    )
    return filters


def _clean_sort(
    item_type: str,
    sort: Any,
    attributes: list[dict[str, Any]],
) -> list[Any]:
    if sort is None:
        return []
    if not isinstance(sort, list):
        raise ValidationError("'sort' must be a list")
    compile_sort(item_type, attributes, sort)
    return sort


def _warning_for(exc: Exception) -> str:
    """Render a DSL ``ValidationError`` as the warning an apply returns."""
    message = getattr(exc, "message", None) or str(exc)
    return f"Saved view could not be applied: {message}"


def _clean_item_type(item_type: Any) -> str:
    if not isinstance(item_type, str) or not item_type.strip():
        raise ValidationError("'item_type' is required")
    if item_type not in TABLE_ITEM_TYPES:
        raise ValidationError(
            f"Unknown item_type {item_type!r}: the table covers the eight "
            "artifact types Requirement, StakeholderNeed, ArchitectureElement, "
            "TestCase, Adr, Risk, Issue and GlossaryTerm"
        )
    return item_type


def _dto(row: SavedView) -> SavedViewDTO:
    return SavedViewDTO(
        id=row.id,
        workspace_id=row.workspace_id,
        item_type=row.item_type,
        owner_id=row.owner_id,
        name=row.name,
        columns=list(row.columns or []),
        filters=dict(row.filters or {}),
        sort=list(row.sort or []),
        visibility=row.visibility,
        version=row.version,
    )


def _state_payload(row: UserTableViewState | None) -> dict[str, Any]:
    if row is None:
        return {**EMPTY_STATE}
    return {
        "columns": list(row.columns or []),
        "filters": dict(row.filters or {}),
        "sort": list(row.sort or []),
    }


def _payload_size(columns: Any, filters: Any, sort: Any) -> int:
    return len(
        json.dumps(
            {"columns": columns, "filters": filters, "sort": sort},
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


class _TableViewBase(ServiceBase):
    """Shared workspace/tenant lookups for both services."""

    @staticmethod
    def _workspace(ctx: AuthContext, workspace_id: UUID | str) -> Workspace:
        workspace = Workspace.objects.filter(
            id=workspace_id, tenant_id=ctx.tenant_id, is_active=True
        ).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace


class SavedViewService(_TableViewBase):
    """CRUD plus :meth:`apply` for ``SavedView`` rows."""

    # ---------- Lookups ----------

    def _get(self, ctx: AuthContext, view_id: UUID | str) -> SavedView:
        row = SavedView.objects.filter(
            id=view_id, tenant_id=ctx.tenant_id
        ).first()
        if row is None:
            raise NotFoundError(f"Saved view {view_id} not found")
        return row

    @staticmethod
    def _assert_readable(ctx: AuthContext, row: SavedView) -> None:
        """A private view is readable by its owner only (404 otherwise)."""
        if row.visibility == "private" and row.owner_id != ctx.user_id:
            raise NotFoundError(f"Saved view {row.id} not found")

    @staticmethod
    def _assert_mutable(ctx: AuthContext, row: SavedView) -> None:
        """Owner or workspace admin may change/delete; everybody else 403."""
        if row.owner_id == ctx.user_id:
            return
        if ctx.has_role(ROLE_ADMIN):
            return
        raise PermissionDeniedError(
            "Only the owner or a workspace admin may change a saved view"
        )

    def _guard_unique_name(
        self,
        workspace_id: UUID,
        item_type: str,
        owner_id: UUID,
        name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        qs = SavedView.objects.filter(
            workspace_id=workspace_id,
            item_type=item_type,
            owner_id=owner_id,
            name=name,
        )
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        if qs.exists():
            raise ValidationError(
                f"A saved view named {name!r} already exists for {item_type} "
                "in this workspace"
            )

    # ---------- Read ----------

    def list(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        item_type: str | None = None,
    ) -> list[SavedViewDTO]:
        """Own views plus the workspace-wide views of others.

        A ``private`` view of another user is filtered out here (no existence
        hint); an unknown/malformed ``item_type`` is a 400, not an empty list.
        """
        self._set_tenant_context(ctx)
        workspace = self._workspace(ctx, workspace_id)
        cleaned_type = _clean_item_type(item_type) if item_type else None

        qs = SavedView.objects.filter(
            workspace_id=workspace.id, tenant_id=ctx.tenant_id
        ).filter(Q(owner_id=ctx.user_id) | Q(visibility="workspace"))
        if cleaned_type is not None:
            qs = qs.filter(item_type=cleaned_type)
        return [_dto(row) for row in qs.order_by("item_type", "name", "id")]

    def get(self, ctx: AuthContext, view_id: UUID | str) -> SavedViewDTO:
        """Return one readable saved view, or 404 (missing/foreign/private)."""
        self._set_tenant_context(ctx)
        row = self._get(ctx, view_id)
        self._assert_readable(ctx, row)
        return _dto(row)

    # ---------- Create ----------

    @atomic_transaction
    def create(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID | str,
        item_type: str,
        name: str,
        columns: Any = None,
        filters: Any = None,
        sort: Any = None,
        visibility: str = "private",
    ) -> SavedViewDTO:
        """Create a saved view owned by the caller (``version == 1``).

        Raises:
            PermissionDeniedError: No write role.
            NotFoundError: Tenant or workspace not in the caller's tenant.
            ValidationError: Unknown item type/field, bad visibility or a
                duplicate name for this owner.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cleaned_type = _clean_item_type(item_type)
        cleaned_name = _clean_name(name)
        cleaned_visibility = _clean_visibility(visibility)
        cleaned_columns = _clean_columns(columns)

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")
        workspace = self._workspace(ctx, workspace_id)
        attributes = TableQueryService().attributes(
            ctx, workspace.id, cleaned_type
        )
        cleaned_filters = _clean_filters(
            ctx, workspace.id, cleaned_type, filters, attributes
        )
        cleaned_sort = _clean_sort(cleaned_type, sort, attributes)

        self._guard_unique_name(
            workspace.id, cleaned_type, ctx.user_id, cleaned_name
        )
        try:
            row = SavedView.objects.create(
                tenant=tenant,
                workspace=workspace,
                owner_id=ctx.user_id,
                item_type=cleaned_type,
                name=cleaned_name,
                columns=cleaned_columns,
                filters=cleaned_filters,
                sort=cleaned_sort,
                visibility=cleaned_visibility,
            )
        except IntegrityError as exc:  # concurrent create of the same name
            raise ValidationError(
                f"A saved view named {cleaned_name!r} already exists for "
                f"{cleaned_type} in this workspace"
            ) from exc

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type=SAVED_VIEW_ITEM_TYPE,
            entity_id=row.id,
        )
        return _dto(row)

    # ---------- Update / delete ----------

    @atomic_transaction
    def update(
        self,
        ctx: AuthContext,
        view_id: UUID | str,
        *,
        name: Any = _UNSET,
        columns: Any = _UNSET,
        filters: Any = _UNSET,
        sort: Any = _UNSET,
        visibility: Any = _UNSET,
        expected_version: int | None = None,
    ) -> SavedViewDTO:
        """Partially update a saved view (owner or workspace admin only).

        Omitted fields keep their value (the :data:`_UNSET` sentinel — a
        ``None`` passed explicitly still means "clear"). A stale
        ``expected_version`` raises :class:`OptimisticLockError` (409).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        qs = lock_for_version_check(
            SavedView.objects.filter(id=view_id, tenant_id=ctx.tenant_id),
            expected_version,
        )
        row = qs.first()
        if row is None:
            raise NotFoundError(f"Saved view {view_id} not found")
        self._assert_mutable(ctx, row)
        assert_expected_version(row, expected_version, entity_type="SavedView")

        # Only a filter/sort change needs the attribute list (one definition
        # resolve, cached per workspace); a rename must not touch it.
        attributes: list[dict[str, Any]] | None = None
        if filters is not _UNSET or sort is not _UNSET:
            attributes = TableQueryService().attributes(
                ctx, row.workspace_id, row.item_type
            )
        updates: dict[str, Any] = {}
        if name is not _UNSET:
            cleaned_name = _clean_name(name)
            self._guard_unique_name(
                row.workspace_id,
                row.item_type,
                row.owner_id,
                cleaned_name,
                exclude_id=row.id,
            )
            updates["name"] = cleaned_name
        if columns is not _UNSET:
            updates["columns"] = _clean_columns(columns)
        if filters is not _UNSET:
            updates["filters"] = _clean_filters(
                ctx, row.workspace_id, row.item_type, filters, attributes or []
            )
        if sort is not _UNSET:
            updates["sort"] = _clean_sort(row.item_type, sort, attributes or [])
        if visibility is not _UNSET:
            updates["visibility"] = _clean_visibility(visibility)

        if updates:
            try:
                SavedView.objects.filter(id=row.id).update(
                    version=F("version") + 1, **updates
                )
            except IntegrityError as exc:  # unique name race
                raise ValidationError(
                    f"A saved view named {updates.get('name')!r} already exists "
                    f"for {row.item_type} in this workspace"
                ) from exc

        row.refresh_from_db()
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=SAVED_VIEW_ITEM_TYPE,
            entity_id=row.id,
            details={"fields": sorted(updates)} if updates else None,
        )
        return _dto(row)

    @atomic_transaction
    def delete(self, ctx: AuthContext, view_id: UUID | str) -> None:
        """Hard-delete a saved view (owner or workspace admin only)."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        row = self._get(ctx, view_id)
        self._assert_mutable(ctx, row)
        row_id = row.id
        row.delete()
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type=SAVED_VIEW_ITEM_TYPE,
            entity_id=row_id,
        )

    # ---------- Apply ----------

    def apply(
        self,
        ctx: AuthContext,
        view_id: UUID | str,
        *,
        workspace_id: UUID | str | None = None,
    ) -> SavedViewApplyResult:
        """Run a stored view and return its rows plus warnings.

        Fail-soft by contract: an unreadable stored document (removed
        attribute, removed enum value, unknown item type) yields **no rows**
        and one warning naming the problem instead of raising. A caller who
        may not read the view still gets the normal 404.
        """
        self._set_tenant_context(ctx)
        row = self._get(ctx, view_id)
        self._assert_readable(ctx, row)
        if workspace_id is not None and str(row.workspace_id) != str(workspace_id):
            # Fence, mirroring the MCP tool: a view of another workspace is not
            # applied by accident, and the caller learns nothing about it.
            raise NotFoundError("SavedView", view_id)
        dto = _dto(row)

        service = TableQueryService()
        try:
            attributes = service.attributes(ctx, row.workspace_id, row.item_type)
            queryset = service.query(
                ctx,
                row.workspace_id,
                row.item_type,
                row.filters,
                row.sort,
            )
            rows = service.serialize_rows(
                ctx, list(queryset), attributes, workspace_id=row.workspace_id
            )
        except ValidationError as exc:
            logger.info("Saved view %s no longer applies: %s", row.id, exc)
            return SavedViewApplyResult(
                rows=[], warnings=[_warning_for(exc)], view=dto
            )
        return SavedViewApplyResult(rows=rows, warnings=[], view=dto)


class TableViewStateService(_TableViewBase):
    """Upsert the per-user "where I was last" layout of one table."""

    def get(
        self, ctx: AuthContext, workspace_id: UUID | str, item_type: str
    ) -> dict[str, Any] | None:
        """Return the caller's stored state, or ``None`` when none exists.

        The transport answers ``200`` with :data:`EMPTY_STATE` in that case;
        ``None`` is kept distinct so the caller can tell "never saved" from
        "saved as empty".
        """
        self._set_tenant_context(ctx)
        workspace = self._workspace(ctx, workspace_id)
        cleaned_type = _clean_item_type(item_type)
        row = UserTableViewState.objects.filter(
            user_id=ctx.user_id,
            workspace_id=workspace.id,
            item_type=cleaned_type,
        ).first()
        return None if row is None else _state_payload(row)

    @atomic_transaction
    def save(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        item_type: str,
        *,
        columns: Any = None,
        filters: Any = None,
        sort: Any = None,
    ) -> dict[str, Any]:
        """Upsert the caller's layout state (one row per user/workspace/type).

        Deliberately **not** validated against the attribute definition: this
        is "where I was last", and a column whose attribute disappeared must
        still load. Only the JSON shape and the caps apply.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cleaned_type = _clean_item_type(item_type)
        cleaned_columns = _clean_columns(columns)
        if filters is not None and not isinstance(filters, dict):
            raise ValidationError("'filters' must be an object")
        if sort is not None and not isinstance(sort, list):
            raise ValidationError("'sort' must be a list")
        cleaned_filters = filters if filters is not None else {}
        cleaned_sort = sort if sort is not None else []

        size = _payload_size(cleaned_columns, cleaned_filters, cleaned_sort)
        if size > MAX_STATE_BYTES:
            raise ValidationError(
                f"Table view state is {size} bytes; the limit is "
                f"{MAX_STATE_BYTES} bytes"
            )

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")
        workspace = self._workspace(ctx, workspace_id)

        row = UserTableViewState.objects.filter(
            user_id=ctx.user_id,
            workspace_id=workspace.id,
            item_type=cleaned_type,
        ).first()
        if row is None:
            row = UserTableViewState.objects.create(
                tenant=tenant,
                workspace=workspace,
                user_id=ctx.user_id,
                item_type=cleaned_type,
                columns=cleaned_columns,
                filters=cleaned_filters,
                sort=cleaned_sort,
            )
        else:
            UserTableViewState.objects.filter(id=row.id).update(
                version=F("version") + 1,
                columns=cleaned_columns,
                filters=cleaned_filters,
                sort=cleaned_sort,
            )
            row.refresh_from_db()
        # Layout state is not an audited domain write (it is a UI bookmark and
        # would flood the trail); the tenant-scoped row itself is the record.
        return _state_payload(row)
