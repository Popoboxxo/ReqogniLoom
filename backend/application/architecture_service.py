"""
COMP-AS-003 ArchitectureService — ArchitectureElement CRUD with versioning.

leaf_id : COMP-AS-003
req_id  : REQ-L2-AS-004 (ArchitectureElement CRUD with Versioning)

Manages ArchitectureElement entities with:
  - Automatic version increment on each update
  - Optimistic locking (OptimisticLockError on stale version)
  - Cascade TraceLink deletion on delete

Interfaces consumed:
  IF-AS-INT-004     TraceLinkService.cascade_delete_trace_links (on delete)
  IF-AS-INT-010     DomainEventBus → ArchitectureElementCreated/Updated/Deleted
  IF-AS-EXT-OUT-007 persistence.models.ArchitectureElement (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-003_ArchitectureService/
      L3_COMP-AS-003_ArchitectureService_Architecture.md
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from django.db.models import F

from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    ElementType,
    Tenant,
    Workspace,
    derive_architecture_role,
)
from persistence.transactions import atomic_transaction

from application.artifact_service import _clean_custom_fields
from application.base import NotFoundError, OptimisticLockError, ServiceBase, ValidationError
from application.models import DomainEventOutbox
from application.validators import ArchitectureElementInvariantValidator

logger = logging.getLogger(__name__)

# Sentinel distinguishing "parameter omitted" from "set parent to None (root)"
_UNSET = object()


class ArchitectureService(ServiceBase):
    """COMP-AS-003 — ArchitectureElement lifecycle management."""

    # Built-in element types — used as defaults/suggestions only. REQ-006
    # (D5): element_type is a free-vocabulary field; this set no longer
    # restricts which values may be stored.
    VALID_ELEMENT_TYPES = frozenset(ElementType.values)

    def __init__(self, trace_link_service=None) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- helpers ----------

    @staticmethod
    def _validate_element_type(element_type: str) -> str:
        """Normalize *element_type* to a lowercase, trimmed string.

        REQ-006 (D5): element_type is a free-vocabulary field — any
        workspace-defined type is accepted (e.g. ``"actor"``,
        ``"boundary"``), not just the built-in ElementType enum values.
        Falls back to the default COMPONENT type when blank.
        """
        normalized = (element_type or "").strip().lower()
        return normalized or ElementType.COMPONENT

    # ---------- CRUD (REQ-L2-AS-004) ----------

    @atomic_transaction
    def create_architecture_element(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
        element_type: str = ElementType.COMPONENT,
        parent_id: Optional[UUID] = None,
        asil_level: Optional[str] = None,
        make_or_buy: Optional[str] = None,
        uid: Optional[str] = None,
        custom_fields: Optional[dict] = None,
    ) -> ArchitectureElement:
        """Create an ArchitectureElement with initial version=1.

        REQ-L2-AS-004 acceptance: create → version=1, initial WorkflowState.
        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Validate element_type against enum (rejects "banane" etc.)
        element_type = self._validate_element_type(element_type)

        # Tenant and Workspace are imported at module level to allow test mocking.
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="ArchitectureElement",
            custom_fields=_clean_custom_fields(custom_fields),
        )

        # REQ-L1-044 + SysEng 2.0 §1.2 (I5): hierarchy invariants, rigor-gated via
        # workspace preset. For a child (parent_id set) I1/I3 apply; for a root
        # (parent_id is None) I5 rejects a second root in the same workspace. The
        # validator is therefore invoked for every create, not only for children.
        # I3 also rejects cross-workspace parents (400 instead of 404 for a
        # dangling parent_id).
        validator = ArchitectureElementInvariantValidator.for_workspace(workspace_id)
        validator.validate_parent_assignment(
            parent_id=parent_id, workspace_id=workspace_id
        )

        arch_el = ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            description=description,
            element_type=element_type,
            parent_id=parent_id,
            version=1,
            asil_level=asil_level,
            make_or_buy=make_or_buy,
            uid=uid,
        )

        # Initialise workflow state
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[arch_el.id],
                item_type="ArchitectureElement",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "ArchitectureService: workflow init skipped for arch_el=%s", arch_el.id
            )

        self._audit(ctx=ctx, operation="create", entity_type="ArchitectureElement", entity_id=arch_el.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_CREATED,
                entity_id=arch_el.id,
                workspace_id=workspace_id,
                payload={"title": title, "element_type": element_type},
            )
        )
        return arch_el

    @atomic_transaction
    def update_architecture_element(
        self,
        arch_el_id: UUID,
        ctx: AuthContext,
        expected_version: int | None = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        element_type: Optional[str] = None,
        parent_id: object = _UNSET,
        asil_level: Optional[str] = _UNSET,
        make_or_buy: Optional[str] = _UNSET,
        uid: Optional[str] = _UNSET,
        custom_fields: object = _UNSET,
    ) -> ArchitectureElement:
        """Update an ArchitectureElement with optimistic locking.

        REQ-L2-AS-004: version incremented on every update; stale
        expected_version → OptimisticLockError.  When *expected_version* is
        omitted, no optimistic lock check is performed (backwards-compatible
        path for callers that do not track versions).

        REQ-L1-044: when *parent_id* is provided (UUID or None to detach),
        the hierarchy invariants I1-I3 are enforced according to the
        workspace's rigor preset before the new parent is persisted.

        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")

        # Optimistic lock check (REQ-L2-AS-004)
        if expected_version is not None and arch_el.version != expected_version:
            raise OptimisticLockError(
                f"Stale version: expected {expected_version}, "
                f"current is {arch_el.version}"
            )

        changed_fields: dict = {}
        if title is not None:
            arch_el.title = title
            changed_fields["title"] = title
        if description is not None:
            arch_el.description = description
            changed_fields["description"] = description
        if element_type is not None:
            arch_el.element_type = self._validate_element_type(element_type)
            changed_fields["element_type"] = arch_el.element_type
        if asil_level is not _UNSET:
            arch_el.asil_level = asil_level
            changed_fields["asil_level"] = asil_level
        if make_or_buy is not _UNSET:
            arch_el.make_or_buy = make_or_buy
            changed_fields["make_or_buy"] = make_or_buy
        if uid is not _UNSET:
            arch_el.uid = uid
            changed_fields["uid"] = uid

        # REQ-L2-AS-037: custom_fields lives on the backing Artifact, not on the
        # ArchitectureElement row — persist it separately from changed_fields.
        if custom_fields is not _UNSET:
            arch_el.artifact.custom_fields = _clean_custom_fields(custom_fields)
            arch_el.artifact.save(update_fields=["custom_fields", "modified_at"])

        # REQ-L1-044 + SysEng 2.0 §1.2 (I5): invariant checks before re-parenting.
        # Runs for any explicit parent_id change, including detaching to root
        # (parent_id=None) so I5 rejects creating a second root. The element
        # itself is excluded from the I5 root scan via element_id, so re-saving
        # the existing root as root stays valid.
        if parent_id is not _UNSET:
            workspace_id = arch_el.artifact.workspace_id
            validator = ArchitectureElementInvariantValidator.for_workspace(
                workspace_id
            )
            validator.validate_parent_assignment(
                parent_id=parent_id,
                element=arch_el,
                element_id=arch_el_id,
                workspace_id=workspace_id,
            )
            arch_el.parent_id = parent_id
            changed_fields["parent_id"] = parent_id

        # Atomic version increment + field persistence — guarded by
        # expected_version when provided.  Changed fields are written in the
        # same UPDATE (fix: they were previously assigned in memory only).
        current_version = expected_version if expected_version is not None else arch_el.version
        ArchitectureElement.objects.filter(id=arch_el_id, version=current_version).update(
            version=F("version") + 1, **changed_fields
        )
        arch_el.refresh_from_db(fields=["version"])

        self._audit(ctx=ctx, operation="update", entity_type="ArchitectureElement", entity_id=arch_el_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_UPDATED,
                entity_id=arch_el_id,
                workspace_id=arch_el.artifact.workspace_id,
            )
        )
        return arch_el

    @atomic_transaction
    def delete_architecture_element(self, arch_el_id: UUID, ctx: AuthContext) -> None:
        """Soft-delete ArchitectureElement by setting lifecycle_status to 'deleted' (REQ-006).

        Physical deletion is intentionally avoided for end-user operations.
        The element and its TraceLinks remain in the database for audit purposes.
        Hard-delete is available only via the Django admin panel.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")

        workspace_id = arch_el.artifact.workspace_id

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of writing lifecycle_status directly.
        from workflow.services import outdate

        outdate(
            item_id=arch_el.id,
            item_type="ArchitectureElement",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via architecture.delete",
        )

        self._audit(ctx=ctx, operation="delete", entity_type="ArchitectureElement", entity_id=arch_el_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_DELETED,
                entity_id=arch_el_id,
                workspace_id=workspace_id,
            )
        )

    def get_architecture_element(
        self, arch_el_id: UUID, ctx: AuthContext, *, include_deleted: bool = False
    ) -> ArchitectureElement:
        """Fetch a single ArchitectureElement.

        REQ-006: soft-deleted elements (outdate()'d, tracked only via
        WorkflowItemState since ArchitectureElement has no mirrored status
        column) are treated as not found by default, matching
        list_architecture_elements(). Pass include_deleted=True for flows
        that legitimately need to see an outdated item (e.g.
        architecture.reactivate).
        """
        self._set_tenant_context(ctx)
        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")
        if not include_deleted:
            from workflow.services import outdated_item_ids
            if arch_el.id in outdated_item_ids("ArchitectureElement"):
                raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")
        return arch_el

    def list_architecture_elements(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        include_deleted: bool = False,
        search: Optional[str] = None,
    ) -> List[ArchitectureElement]:
        """Return ArchitectureElements in *workspace_id*.

        REQ-006: Excludes soft-deleted elements (lifecycle_status='deleted') by default.
        Pass ``include_deleted=True`` for admin/audit access.

        Issue #267 (same root cause as RequirementService.list_requirements):
        ``search`` case-insensitively filters on title/description/uid. Applied
        *after* level/role annotation (which needs the full, unfiltered tree to
        resolve ancestors correctly) rather than as a queryset filter.
        """
        self._set_tenant_context(ctx)
        # select_related("artifact") avoids one query per element when the
        # serializer reads ``element.artifact`` (workspace_id, custom_fields).
        qs = ArchitectureElement.objects.select_related("artifact").filter(
            artifact__workspace_id=workspace_id
        )
        if not include_deleted:
            # Phase 0: delete_architecture_element() routes soft-delete through
            # workflow.services.outdate(). ArchitectureElement is NOT wired into
            # _STATUS_MIRROR_MODELS (no mirrored status column), so the
            # workflow state lives solely in WorkflowItemState — filter there
            # instead of on the now-dead `lifecycle_status` column.
            from workflow.services import outdated_item_ids

            qs = qs.exclude(id__in=outdated_item_ids("ArchitectureElement"))
        elements = list(qs)
        # REQ-L2-RA-013 / REQ-070: eliminate N+1 on tree depth. The ``level``
        # property recurses into the DB (one query per ancestor per element)
        # unless ``_level_annotated`` is pre-set. Compute all levels in a single
        # in-memory pass over the already-fetched set instead.
        self._annotate_levels(elements)
        # SysEng 2.0 §1.2: derive the structural role (system/subsystem/component)
        # from tree position in the same single-pass fashion (no per-element
        # children query).
        self._annotate_roles(elements)
        if search:
            needle = search.lower()
            elements = [
                el
                for el in elements
                if needle in (el.title or "").lower()
                or needle in (el.description or "").lower()
                or needle in (el.uid or "").lower()
            ]
        return elements

    @staticmethod
    def _annotate_levels(elements: List[ArchitectureElement]) -> None:
        """Set ``_level_annotated`` on each element via a single in-memory pass.

        REQ-070: The ArchitectureElement.level property otherwise recurses into
        the database (get_level) once per ancestor, producing N+1 queries when a
        list of elements is serialized. Since the whole workspace set is already
        loaded, tree depth can be derived without any extra query.

        Elements whose parent is not part of ``elements`` (e.g. a soft-deleted
        ancestor filtered out of the queryset) fall back to the recursive
        property so the reported depth stays correct.
        """
        parent_by_id = {el.id: el.parent_id for el in elements}
        level_cache: dict[UUID, int] = {}

        def resolve(el_id: UUID) -> int | None:
            depth = 0
            current: UUID | None = el_id
            seen: set[UUID] = set()
            while current is not None:
                if current in level_cache:
                    return depth + level_cache[current]
                if current not in parent_by_id or current in seen:
                    # Parent outside the loaded set or a cycle: cannot resolve
                    # purely in memory — signal fallback.
                    return None
                seen.add(current)
                parent = parent_by_id[current]
                if parent is None:
                    return depth
                depth += 1
                current = parent
            return depth

        for el in elements:
            resolved = resolve(el.id)
            if resolved is None:
                # Fallback: let the property compute it (recursive, rare path).
                resolved = el.get_level()
            level_cache[el.id] = resolved
            el._level_annotated = resolved

    @staticmethod
    def _annotate_roles(elements: List[ArchitectureElement]) -> None:
        """Set ``_role_annotated`` on each element via a single in-memory pass.

        SysEng 2.0 §1.2: the structural role is derived from tree position, not
        read from the stored ``element_type``. Root (no parent) → 'system',
        inner node (appears as some element's parent) → 'subsystem', leaf →
        'component'. Root precedence over leaf is handled by
        ``derive_architecture_role``.

        The children check is resolved purely from the loaded set: any id that
        appears as another element's ``parent_id`` has children. This mirrors
        ``_annotate_levels`` and avoids one EXISTS query per element. When
        ``list_architecture_elements`` excludes soft-deleted elements (the
        default), their parents correctly collapse to leaves.
        """
        parent_ids_with_children = {
            el.parent_id for el in elements if el.parent_id is not None
        }
        for el in elements:
            el._role_annotated = derive_architecture_role(
                has_parent=el.parent_id is not None,
                has_children=el.id in parent_ids_with_children,
            )


__all__ = ["ArchitectureService"]
