# Requirement Bundle Export — Plan 1: Raw Query + REST + MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the raw (non-AI) half of the Requirement Bundle Export feature: a service that, given an `ArchitectureElement` root and a depth, walks `ALLOCATED_TO` trace links to collect every Requirement allocated to that element and its (optionally recursive) sub-elements, with three attribute-filter modes and JSON/Markdown/CSV output — exposed via REST and MCP, plus a small attribute-schema discovery endpoint.

**Architecture:** One new backend service (`RequirementBundleQueryService`) owns the recursive trace-link walk, filtering, and formatting — no LLM involvement. `AttributeVisibilityConfigService` gains one new read method for schema discovery. A REST custom action and a new MCP tool group expose both.

**Tech Stack:** Django 5.2 (raw SQL recursive CTE via `django.db.connection`), DRF (`@action` on the existing `ArchitectureElementViewSet`), the project's `BaseToolGroup` MCP pattern, pytest.

**Design source:** `docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md` (branch `docs/requirement-bundle-export-design`), sections 2-4, 7 (raw parts only), 8, 9. Sections 5 (compressed mode/caching) and the UI panel (§7 UI) are **out of scope for this plan** — see "Follow-on plans" at the end of this document.

## Global Constraints

- Grouping is via the `ALLOCATED_TO` trace-link type ONLY (`LinkType.ALLOCATED_TO.value == "allocated-to"`, `backend/traceability/types.py`) — never `parent_id`/structural hierarchy, never `IMPLEMENTS`.
- `depth` is a single unified scope parameter: `0` = only requirements directly allocated to the root element; `N` = also walk `ALLOCATED_TO` (Arch→Arch) sub-elements up to N levels deep, collecting their direct requirements too; `None`/omitted = full hierarchy, capped at depth 20 (mirrors the existing cap in `ArtifactService.get_tree`'s recursive CTE, `backend/application/artifact_service.py:504`).
- Every result item carries the id of the architecture element it was found directly allocated to (`found_under_element_id`), never silently flattened.
- Every public service method takes `ctx: AuthContext` first (after `self`) and calls `self._set_tenant_context(ctx)` at entry — the project's `ServiceBase` convention (`backend/application/base.py:87`).
- No new dependency additions. Use `django.db.connection` for the recursive CTE, exactly like `ArtifactService.get_tree`.
- Do not modify `AttributeVisibilityConfigService`'s existing methods — only add a new one.
- Every new REST/MCP entry point requires an `AuthContext` and enforces existing tenant/workspace scoping the same way every other endpoint in this codebase does (via `get_auth_context(request)` for REST, via `BaseToolGroup`'s existing dispatch machinery for MCP) — no new auth mechanism.
- Field lists for `filter_mode="all"` cover the artifact's OWN fields, never internal-only columns (`tenant_id`, `embedding`, `created_by_id`/`modified_by_id` raw FK ids) — mirror what `RequirementSerializer` (`backend/rest_api/serializers.py:459`) already exposes.

---

### Task 1: `RequirementBundleQueryService` — recursive `ALLOCATED_TO` walk

**Files:**
- Create: `backend/application/requirement_bundle_service.py`
- Test: `backend/application/tests/test_requirement_bundle_service.py`

**Interfaces:**
- Consumes: `ServiceBase` (`application.base`), `NotFoundError`/`ValidationError` (`application.base`), `TraceLinkService._resolve_artifact_id` (`application.trace_link_service`) for resolving the root's Artifact id, `LinkType` (`traceability.types`).
- Produces: `RequirementBundleQueryService.get_bundle(ctx, root_id, workspace_id, depth=None) -> BundleResult` — a dataclass with `.items: list[BundleItem]` and `.truncated_at_depth: bool`. `BundleItem` is a dataclass: `requirement_id: UUID`, `found_under_element_id: UUID`, `depth: int`, `fields: dict[str, Any]` (ALL Requirement fields, unfiltered — filtering is Task 2's job). Later tasks import `RequirementBundleQueryService`, `BundleResult`, `BundleItem`, `BundleDepthExceededError` from this module.

- [ ] **Step 1: Write the failing test for depth=0 (direct allocations only)**

```python
# backend/application/tests/test_requirement_bundle_service.py
"""Tests for RequirementBundleQueryService (Requirement Bundle Export, Plan 1 Task 1)."""
from __future__ import annotations

from uuid import UUID

import pytest

from application.requirement_bundle_service import (
    RequirementBundleQueryService,
    BundleDepthExceededError,
)
from application.base import NotFoundError
from persistence.tenancy import TenantContext


@pytest.mark.django_db
class TestGetBundleDepthZero:
    def test_depth_zero_returns_only_directly_allocated_requirements(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        root = make_architecture_element(workspace, title="Root System")
        child = make_architecture_element(workspace, title="Child Subsystem", parent=None)
        req_direct = make_requirement(workspace, title="Directly allocated")
        req_on_child = make_requirement(workspace, title="Allocated to child only")
        make_allocated_to_link(source=req_direct, target=root)
        make_allocated_to_link(source=req_on_child, target=child)
        make_allocated_to_link(source=child, target=root)  # child is a sub-element of root

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0)

        ids = {item.requirement_id for item in result.items}
        assert ids == {req_direct.id}
        assert result.items[0].found_under_element_id == root.id
        assert result.items[0].depth == 0
        assert result.truncated_at_depth is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_requirement_bundle_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.requirement_bundle_service'` (and the `auth_ctx`/`make_architecture_element`/`make_requirement`/`make_allocated_to_link` fixtures may not exist yet either — if so, check `backend/application/tests/conftest.py` and the nearest sibling test file, e.g. `test_architecture_decompose.py` or `test_trace_link_service.py`, for the exact existing fixture names and signatures in this codebase and use those instead of inventing new ones; only add new fixtures to `conftest.py` if truly none of the existing ones fit, and if you do, name them consistently with the existing style).

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/application/requirement_bundle_service.py
"""COMP-AS-RBQ RequirementBundleQueryService — grouped requirement export by
architecture element via ALLOCATED_TO trace links (GitHub issue for
Requirement Bundle Export, Plan 1 Task 1).

Design: docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md

Walks the ALLOCATED_TO trace-link graph (Requirement->ArchitectureElement and
ArchitectureElement->ArchitectureElement) starting at a root
ArchitectureElement, up to a configurable depth, collecting every Requirement
directly allocated to the root or any sub-element within that depth. Does NOT
use the Artifact parent_id structural tree (that is a different relationship,
see ArtifactService.get_tree) — grouping here is the semantic ALLOCATED_TO
allocation, per the design spec's explicit decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import UUID

from django.db import connection

from auth_tenancy.context import AuthContext
from traceability.types import LinkType

from application.base import NotFoundError, ServiceBase, ValidationError

MAX_DEPTH = 20  # mirrors ArtifactService.get_tree's recursive CTE cap


class BundleDepthExceededError(ValidationError):
    """Raised when a caller passes a depth greater than MAX_DEPTH."""


@dataclass
class BundleItem:
    """One Requirement found during the ALLOCATED_TO walk, with its origin."""

    requirement_id: UUID
    found_under_element_id: UUID
    depth: int
    fields: Dict[str, Any]


@dataclass
class BundleResult:
    items: List[BundleItem] = field(default_factory=list)
    truncated_at_depth: bool = False


# Requirement's own fields exposed by RequirementSerializer
# (backend/rest_api/serializers.py:459), used as the "all" field set — never
# internal-only columns (tenant_id, embedding, raw *_by_id FKs).
REQUIREMENT_ALL_FIELDS = (
    "id",
    "workspace_id",
    "parent_id",
    "title",
    "description",
    "acceptance_criteria",
    "category",
    "status",
    "type",
    "level",
    "complexity_fibonacci",
    "verification_method",
    "uid",
    "suspect",
    "lifecycle_status",
    "version",
)


class RequirementBundleQueryService(ServiceBase):
    """Raw (non-AI) requirement bundle query — Task 1: unfiltered field set."""

    def get_bundle(
        self,
        ctx: AuthContext,
        root_id: UUID,
        workspace_id: UUID,
        depth: "int | None" = None,
    ) -> BundleResult:
        """Return every Requirement allocated (ALLOCATED_TO) to *root_id* or
        its ALLOCATED_TO sub-elements, up to *depth* levels.

        Args:
            root_id: ArchitectureElement id (the more user-facing id, same
                convention as TraceLinkService endpoints — resolved to its
                backing Artifact id internally).
            workspace_id: Workspace the root element must belong to.
            depth: 0 = only requirements directly allocated to the root.
                N = also walk N levels of ALLOCATED_TO Arch->Arch
                sub-elements. None = unbounded, capped at MAX_DEPTH.

        Raises:
            NotFoundError: root_id does not resolve to an ArchitectureElement
                in workspace_id.
            BundleDepthExceededError: depth > MAX_DEPTH.
        """
        self._set_tenant_context(ctx)

        if depth is not None and depth > MAX_DEPTH:
            raise BundleDepthExceededError(
                f"depth {depth} exceeds the maximum of {MAX_DEPTH}"
            )
        effective_cap = MAX_DEPTH if depth is None else depth

        from application.trace_link_service import TraceLinkService
        from persistence.models import ArchitectureElement

        root_artifact_id = TraceLinkService()._resolve_artifact_id(root_id)
        if not ArchitectureElement.objects.filter(
            artifact_id=root_artifact_id, artifact__workspace_id=workspace_id
        ).exists():
            raise NotFoundError(
                f"ArchitectureElement {root_id} not found in workspace {workspace_id}"
            )

        # Recursive CTE over pl_tracelink, filtered to ALLOCATED_TO, walking
        # ArchitectureElement->ArchitectureElement edges from the root, then
        # collecting every Requirement->ArchitectureElement edge landing on
        # any element found in that walk. Mirrors ArtifactService.get_tree's
        # raw-SQL CTE shape (backend/application/artifact_service.py:492).
        sql = """
            WITH RECURSIVE arch_tree AS (
                SELECT %s::uuid AS element_artifact_id, 0 AS depth

                UNION ALL

                SELECT tl.target_id AS element_artifact_id, t.depth + 1
                FROM pl_tracelink tl
                INNER JOIN arch_tree t ON tl.source_id = t.element_artifact_id
                WHERE tl.link_type = %s
                  AND t.depth < %s
            )
            SELECT DISTINCT ON (req_link.source_id)
                req_link.source_id AS requirement_artifact_id,
                arch_tree.element_artifact_id AS found_under_artifact_id,
                arch_tree.depth AS found_depth
            FROM arch_tree
            INNER JOIN pl_tracelink req_link
                ON req_link.target_id = arch_tree.element_artifact_id
                AND req_link.link_type = %s
            ORDER BY req_link.source_id, arch_tree.depth ASC;
        """
        allocated_to = LinkType.ALLOCATED_TO.value
        with connection.cursor() as cursor:
            cursor.execute(
                sql, [str(root_artifact_id), allocated_to, effective_cap, allocated_to]
            )
            rows = cursor.fetchall()

        truncated = depth is None and any(r[2] >= MAX_DEPTH for r in rows)

        if not rows:
            return BundleResult(items=[], truncated_at_depth=truncated)

        req_artifact_ids = [r[0] for r in rows]
        found_under_by_req: Dict[UUID, tuple] = {
            r[0]: (r[1], r[2]) for r in rows
        }

        from persistence.models import Requirement

        req_rows = Requirement.unscoped.filter(
            artifact_id__in=req_artifact_ids, tenant_id=ctx.tenant_id
        ).values(*REQUIREMENT_ALL_FIELDS, "artifact_id")

        items: List[BundleItem] = []
        for row in req_rows:
            artifact_id = row.pop("artifact_id")
            found_under_artifact_id, found_depth = found_under_by_req[artifact_id]
            items.append(
                BundleItem(
                    requirement_id=row["id"],
                    found_under_element_id=found_under_artifact_id,
                    depth=found_depth,
                    fields={k: v for k, v in row.items()},
                )
            )

        return BundleResult(items=items, truncated_at_depth=truncated)


__all__ = [
    "RequirementBundleQueryService",
    "BundleResult",
    "BundleItem",
    "BundleDepthExceededError",
    "REQUIREMENT_ALL_FIELDS",
    "MAX_DEPTH",
]
```

**Note on `found_under_element_id`:** the CTE returns the element's *Artifact* id (`pl_tracelink.target_id`/`source_id` are Artifact ids, per `TraceLink.source`/`TraceLink.target` both being FKs to `Artifact`). This matches `root_id`'s own resolution (`TraceLinkService()._resolve_artifact_id(root_id)` also returns an Artifact id) — both sides of every returned item are consistently Artifact ids at this layer. Do not silently mix in the ArchitectureElement's own (non-Artifact) id anywhere in this task; Task 5 (REST) documents this explicitly for API consumers.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_requirement_bundle_service.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for recursive depth and the depth cap**

```python
# append to backend/application/tests/test_requirement_bundle_service.py

@pytest.mark.django_db
class TestGetBundleRecursiveDepth:
    def test_depth_one_includes_direct_child_requirements(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        root = make_architecture_element(workspace, title="Root")
        child = make_architecture_element(workspace, title="Child")
        make_allocated_to_link(source=child, target=root)
        req_on_child = make_requirement(workspace, title="On child")
        make_allocated_to_link(source=req_on_child, target=child)

        svc = RequirementBundleQueryService()
        result_depth0 = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0)
        result_depth1 = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=1)

        assert result_depth0.items == []
        ids_depth1 = {item.requirement_id for item in result_depth1.items}
        assert ids_depth1 == {req_on_child.id}
        assert result_depth1.items[0].depth == 1

    def test_depth_none_walks_full_hierarchy(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        root = make_architecture_element(workspace, title="Root")
        mid = make_architecture_element(workspace, title="Mid")
        leaf = make_architecture_element(workspace, title="Leaf")
        make_allocated_to_link(source=mid, target=root)
        make_allocated_to_link(source=leaf, target=mid)
        req_on_leaf = make_requirement(workspace, title="Deep")
        make_allocated_to_link(source=req_on_leaf, target=leaf)

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None)

        assert {i.requirement_id for i in result.items} == {req_on_leaf.id}
        assert result.items[0].depth == 2

    def test_depth_exceeding_max_raises(self, auth_ctx, workspace, make_architecture_element):
        root = make_architecture_element(workspace, title="Root")
        svc = RequirementBundleQueryService()
        with pytest.raises(BundleDepthExceededError):
            svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=21)

    def test_unknown_root_raises_not_found(self, auth_ctx, workspace):
        import uuid
        svc = RequirementBundleQueryService()
        with pytest.raises(NotFoundError):
            svc.get_bundle(auth_ctx, root_id=uuid.uuid4(), workspace_id=workspace.id, depth=0)
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_requirement_bundle_service.py -v`
Expected: all PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/application/requirement_bundle_service.py backend/application/tests/test_requirement_bundle_service.py
git commit -m "feat: add RequirementBundleQueryService recursive ALLOCATED_TO walk"
```

---

### Task 2: Attribute filtering (three modes)

**Files:**
- Modify: `backend/application/requirement_bundle_service.py`
- Modify: `backend/application/tests/test_requirement_bundle_service.py`

**Interfaces:**
- Consumes: `AttributeVisibilityConfigService.list_configs(ctx)` (`application.attribute_visibility_service`, existing method, returns a `QuerySet[AttributeVisibilityConfig]` with `.entity_type`, `.attribute_name`, `.is_visible`).
- Produces: `RequirementBundleQueryService.get_bundle(..., filter_mode="all"|"visible"|"custom", fields=None)`. `filter_mode` and `fields` are new keyword-only params. Raises `application.base.ValidationError` (imported already) listing unknown field names for `filter_mode="custom"`.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/application/tests/test_requirement_bundle_service.py

@pytest.mark.django_db
class TestGetBundleFiltering:
    def test_filter_mode_all_returns_every_field(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0, filter_mode="all"
        )
        from application.requirement_bundle_service import REQUIREMENT_ALL_FIELDS
        assert set(result.items[0].fields.keys()) == set(REQUIREMENT_ALL_FIELDS)

    def test_filter_mode_custom_returns_only_requested_fields(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(
            auth_ctx,
            root_id=root.id,
            workspace_id=workspace.id,
            depth=0,
            filter_mode="custom",
            fields=["title", "status"],
        )
        assert set(result.items[0].fields.keys()) == {"title", "status"}

    def test_filter_mode_custom_with_unknown_field_raises(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        from application.base import ValidationError

        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        svc = RequirementBundleQueryService()
        with pytest.raises(ValidationError, match="not_a_real_field"):
            svc.get_bundle(
                auth_ctx,
                root_id=root.id,
                workspace_id=workspace.id,
                depth=0,
                filter_mode="custom",
                fields=["title", "not_a_real_field"],
            )

    def test_filter_mode_visible_uses_attribute_visibility_config(
        self, auth_ctx, workspace, make_architecture_element, make_requirement,
        make_allocated_to_link, make_attribute_visibility_config,
    ):
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)
        make_attribute_visibility_config(
            entity_type="Requirement", attribute_name="title", is_visible=True
        )
        make_attribute_visibility_config(
            entity_type="Requirement", attribute_name="description", is_visible=False
        )

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0, filter_mode="visible"
        )
        fields = result.items[0].fields
        assert "title" in fields
        assert "description" not in fields
```

If `make_attribute_visibility_config` doesn't exist as a fixture yet, check `backend/application/tests/test_service_boundaries_req066.py` for how `AttributeVisibilityConfig` rows are created in existing tests and either reuse that pattern inline or add a small fixture matching this codebase's existing conftest style.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_requirement_bundle_service.py::TestGetBundleFiltering -v`
Expected: FAIL — `get_bundle() got an unexpected keyword argument 'filter_mode'`

- [ ] **Step 3: Implement filtering**

```python
# In backend/application/requirement_bundle_service.py, replace the
# get_bundle signature and add filtering logic. Full updated method:

    def get_bundle(
        self,
        ctx: AuthContext,
        root_id: UUID,
        workspace_id: UUID,
        depth: "int | None" = None,
        *,
        filter_mode: str = "all",
        fields: "List[str] | None" = None,
    ) -> BundleResult:
        """Return every Requirement allocated (ALLOCATED_TO) to *root_id* or
        its ALLOCATED_TO sub-elements, up to *depth* levels, with fields
        limited per *filter_mode*.

        Args:
            root_id: ArchitectureElement id (the more user-facing id, same
                convention as TraceLinkService endpoints — resolved to its
                backing Artifact id internally).
            workspace_id: Workspace the root element must belong to.
            depth: 0 = only requirements directly allocated to the root.
                N = also walk N levels of ALLOCATED_TO Arch->Arch
                sub-elements. None = unbounded, capped at MAX_DEPTH.
            filter_mode: "all" (every field), "visible" (only fields marked
                visible for Requirement in AttributeVisibilityConfig for the
                active tenant), or "custom" (only the fields named in
                *fields*).
            fields: Required (non-empty) when filter_mode="custom". Every
                name must be a member of REQUIREMENT_ALL_FIELDS.

        Raises:
            NotFoundError: root_id does not resolve to an ArchitectureElement
                in workspace_id.
            BundleDepthExceededError: depth > MAX_DEPTH.
            ValidationError: filter_mode is invalid, or filter_mode="custom"
                with missing/unknown field names.
        """
        self._set_tenant_context(ctx)

        if filter_mode not in ("all", "visible", "custom"):
            raise ValidationError(
                f"Invalid filter_mode {filter_mode!r}; expected 'all', 'visible', or 'custom'"
            )
        if filter_mode == "custom":
            if not fields:
                raise ValidationError("filter_mode='custom' requires a non-empty 'fields' list")
            unknown = sorted(set(fields) - set(REQUIREMENT_ALL_FIELDS))
            if unknown:
                raise ValidationError(
                    f"Unknown field(s) for filter_mode='custom': {', '.join(unknown)}"
                )

        if depth is not None and depth > MAX_DEPTH:
            raise BundleDepthExceededError(
                f"depth {depth} exceeds the maximum of {MAX_DEPTH}"
            )
        effective_cap = MAX_DEPTH if depth is None else depth

        from application.trace_link_service import TraceLinkService
        from persistence.models import ArchitectureElement

        root_artifact_id = TraceLinkService()._resolve_artifact_id(root_id)
        if not ArchitectureElement.objects.filter(
            artifact_id=root_artifact_id, artifact__workspace_id=workspace_id
        ).exists():
            raise NotFoundError(
                f"ArchitectureElement {root_id} not found in workspace {workspace_id}"
            )

        sql = """
            WITH RECURSIVE arch_tree AS (
                SELECT %s::uuid AS element_artifact_id, 0 AS depth

                UNION ALL

                SELECT tl.target_id AS element_artifact_id, t.depth + 1
                FROM pl_tracelink tl
                INNER JOIN arch_tree t ON tl.source_id = t.element_artifact_id
                WHERE tl.link_type = %s
                  AND t.depth < %s
            )
            SELECT DISTINCT ON (req_link.source_id)
                req_link.source_id AS requirement_artifact_id,
                arch_tree.element_artifact_id AS found_under_artifact_id,
                arch_tree.depth AS found_depth
            FROM arch_tree
            INNER JOIN pl_tracelink req_link
                ON req_link.target_id = arch_tree.element_artifact_id
                AND req_link.link_type = %s
            ORDER BY req_link.source_id, arch_tree.depth ASC;
        """
        allocated_to = LinkType.ALLOCATED_TO.value
        with connection.cursor() as cursor:
            cursor.execute(
                sql, [str(root_artifact_id), allocated_to, effective_cap, allocated_to]
            )
            rows = cursor.fetchall()

        truncated = depth is None and any(r[2] >= MAX_DEPTH for r in rows)

        if not rows:
            return BundleResult(items=[], truncated_at_depth=truncated)

        req_artifact_ids = [r[0] for r in rows]
        found_under_by_req: Dict[UUID, tuple] = {r[0]: (r[1], r[2]) for r in rows}

        selected_fields = self._resolve_field_set(ctx, filter_mode, fields)

        from persistence.models import Requirement

        query_fields = tuple(set(selected_fields) | {"id", "artifact_id"})
        req_rows = Requirement.unscoped.filter(
            artifact_id__in=req_artifact_ids, tenant_id=ctx.tenant_id
        ).values(*query_fields)

        items: List[BundleItem] = []
        for row in req_rows:
            artifact_id = row.pop("artifact_id")
            requirement_id = row.pop("id")
            found_under_artifact_id, found_depth = found_under_by_req[artifact_id]
            items.append(
                BundleItem(
                    requirement_id=requirement_id,
                    found_under_element_id=found_under_artifact_id,
                    depth=found_depth,
                    fields={k: v for k, v in row.items() if k in selected_fields},
                )
            )

        return BundleResult(items=items, truncated_at_depth=truncated)

    def _resolve_field_set(
        self, ctx: AuthContext, filter_mode: str, fields: "List[str] | None"
    ) -> "set[str]":
        """Return the concrete field-name set for *filter_mode*."""
        if filter_mode == "all":
            return set(REQUIREMENT_ALL_FIELDS)
        if filter_mode == "custom":
            return set(fields or [])
        # "visible"
        from application.attribute_visibility_service import AttributeVisibilityConfigService

        configs = AttributeVisibilityConfigService().list_configs(ctx).filter(
            entity_type="Requirement"
        )
        visible_names = {c.attribute_name for c in configs if c.is_visible}
        hidden_names = {c.attribute_name for c in configs if not c.is_visible}
        # Fields with no explicit config row default to visible (matches
        # AttributeVisibilityConfigService's own "opt-out" convention — a
        # missing row is not the same as an explicit is_visible=False row).
        return (set(REQUIREMENT_ALL_FIELDS) - hidden_names) | (
            visible_names & set(REQUIREMENT_ALL_FIELDS)
        )
```

Before writing this, confirm the "no config row = visible by default" assumption against `AttributeVisibilityConfigService`'s actual documented default behavior (check `backend/application/tests/test_service_boundaries_req066.py` and the `AttributeVisibilityConfig` model's own docstring/default in `persistence/models.py` for the authoritative default) — if the codebase's real convention is the opposite (no row = hidden by default), flip the set logic accordingly and update this note.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_requirement_bundle_service.py -v`
Expected: all PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/requirement_bundle_service.py backend/application/tests/test_requirement_bundle_service.py
git commit -m "feat: add three-mode attribute filtering to RequirementBundleQueryService"
```

---

### Task 3: Markdown and CSV formatters

**Files:**
- Create: `backend/application/requirement_bundle_formatters.py`
- Test: `backend/application/tests/test_requirement_bundle_formatters.py`

**Interfaces:**
- Consumes: `BundleResult`, `BundleItem` (Task 1/2, `application.requirement_bundle_service`).
- Produces: `format_bundle_json(result: BundleResult) -> dict`, `format_bundle_markdown(result: BundleResult) -> str`, `format_bundle_csv(result: BundleResult) -> str`. Task 5 (REST) and Task 6 (MCP) call these directly.

- [ ] **Step 1: Write the failing tests**

```python
# backend/application/tests/test_requirement_bundle_formatters.py
from __future__ import annotations

import csv
import io
from uuid import uuid4

from application.requirement_bundle_service import BundleItem, BundleResult
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)


def _sample_result() -> BundleResult:
    root_id = uuid4()
    return BundleResult(
        items=[
            BundleItem(
                requirement_id=uuid4(),
                found_under_element_id=root_id,
                depth=0,
                fields={"title": "First requirement", "status": "draft"},
            ),
            BundleItem(
                requirement_id=uuid4(),
                found_under_element_id=root_id,
                depth=1,
                fields={"title": "Second, with a comma", "status": "approved"},
            ),
        ],
        truncated_at_depth=False,
    )


class TestFormatBundleJson:
    def test_json_is_list_of_dicts_with_metadata(self):
        result = _sample_result()
        payload = format_bundle_json(result)
        assert payload["truncated_at_depth"] is False
        assert len(payload["items"]) == 2
        assert payload["items"][0]["fields"]["title"] == "First requirement"
        assert payload["items"][0]["depth"] == 0
        assert "requirement_id" in payload["items"][0]
        assert "found_under_element_id" in payload["items"][0]


class TestFormatBundleMarkdown:
    def test_markdown_contains_every_title_grouped_by_element(self):
        result = _sample_result()
        md = format_bundle_markdown(result)
        assert "First requirement" in md
        assert "Second, with a comma" in md
        assert md.startswith("#")


class TestFormatBundleCsv:
    def test_csv_has_one_row_per_item_and_escapes_commas(self):
        result = _sample_result()
        csv_text = format_bundle_csv(result)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[1]["title"] == "Second, with a comma"
        assert "found_under_element_id" in reader.fieldnames
        assert "depth" in reader.fieldnames

    def test_csv_with_no_items_still_has_header_only(self):
        empty = BundleResult(items=[], truncated_at_depth=False)
        csv_text = format_bundle_csv(empty)
        assert csv_text.strip() != ""
        reader = csv.DictReader(io.StringIO(csv_text))
        assert list(reader) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec backend python -m pytest application/tests/test_requirement_bundle_formatters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.requirement_bundle_formatters'`

- [ ] **Step 3: Implement the formatters**

```python
# backend/application/requirement_bundle_formatters.py
"""Output formatters for RequirementBundleQueryService results (Plan 1 Task 3).

Three formats, matching the design spec's §5 raw-mode decision:
  - JSON: default, for REST/MCP/UI consumption.
  - Markdown: hierarchical, token-efficient (also the compressed-mode default
    in a later plan).
  - CSV: flat, one row per requirement, denormalized with a
    found_under_element_id column since CSV cannot express hierarchy.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict

from application.requirement_bundle_service import BundleItem, BundleResult


def _item_to_dict(item: BundleItem) -> Dict[str, Any]:
    return {
        "requirement_id": str(item.requirement_id),
        "found_under_element_id": str(item.found_under_element_id),
        "depth": item.depth,
        "fields": dict(item.fields),
    }


def format_bundle_json(result: BundleResult) -> Dict[str, Any]:
    """Return a JSON-ready dict: {"items": [...], "truncated_at_depth": bool}."""
    return {
        "items": [_item_to_dict(item) for item in result.items],
        "truncated_at_depth": result.truncated_at_depth,
    }


def format_bundle_markdown(result: BundleResult) -> str:
    """Render the bundle as hierarchical Markdown, grouped by
    found_under_element_id in the order items were returned (already
    depth-ordered by the query)."""
    lines = ["# Requirement Bundle"]
    if result.truncated_at_depth:
        lines.append("\n> **Note:** results truncated at the maximum depth cap.")

    current_group: "str | None" = None
    for item in result.items:
        group_key = str(item.found_under_element_id)
        if group_key != current_group:
            lines.append(f"\n## Element {group_key} (depth {item.depth})")
            current_group = group_key
        title = item.fields.get("title", str(item.requirement_id))
        lines.append(f"\n### {title}")
        for field_name, value in item.fields.items():
            if field_name == "title":
                continue
            lines.append(f"- **{field_name}**: {value}")
    return "\n".join(lines) + "\n"


def format_bundle_csv(result: BundleResult) -> str:
    """Render the bundle as flat CSV: one row per requirement.

    Column order: requirement_id, found_under_element_id, depth, then every
    field key present across all items (union, stable-sorted), so a bundle
    whose items carry heterogeneous field sets (filter_mode='custom' with a
    field only some requirement types have) still produces one consistent
    header row.
    """
    buffer = io.StringIO()
    field_names: "list[str]" = []
    seen = set()
    for item in result.items:
        for key in item.fields:
            if key not in seen:
                seen.add(key)
                field_names.append(key)

    header = ["requirement_id", "found_under_element_id", "depth"] + sorted(field_names)
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    for item in result.items:
        row = {
            "requirement_id": str(item.requirement_id),
            "found_under_element_id": str(item.found_under_element_id),
            "depth": item.depth,
        }
        row.update({k: item.fields.get(k, "") for k in field_names})
        writer.writerow(row)
    return buffer.getvalue()


__all__ = ["format_bundle_json", "format_bundle_markdown", "format_bundle_csv"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest application/tests/test_requirement_bundle_formatters.py -v`
Expected: all PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/requirement_bundle_formatters.py backend/application/tests/test_requirement_bundle_formatters.py
git commit -m "feat: add JSON/Markdown/CSV formatters for requirement bundles"
```

---

### Task 4: Attribute schema discovery

**Files:**
- Modify: `backend/application/attribute_visibility_service.py`
- Modify: `backend/application/tests/test_service_boundaries_req066.py` (or create `backend/application/tests/test_attribute_schema_discovery.py` if that file's `TestAttributeVisibilityConfigService` class is a poor fit — check the existing file first and follow its established style)

**Interfaces:**
- Consumes: `REQUIREMENT_ALL_FIELDS` (`application.requirement_bundle_service`, Task 1). If a future artifact type beyond Requirement is added to this discovery endpoint, extend the same pattern — this task covers Requirement only, per the design spec's Requirement-first scope.
- Produces: `AttributeVisibilityConfigService.describe_schema(ctx, entity_type=None) -> list[dict]`. Each dict: `{"entity_type": str, "attribute_name": str, "is_visible": bool}`. Task 5 (REST) and Task 6 (MCP) call this.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/application/tests/test_service_boundaries_req066.py,
# inside or near the existing TestAttributeVisibilityConfigService class —
# read that class first and match its existing fixture usage exactly.

class TestDescribeSchema:
    def test_describe_schema_lists_every_requirement_field(self, ...):  # match existing fixture args in this file
        svc = AttributeVisibilityConfigService()
        schema = svc.describe_schema(ctx, entity_type="Requirement")
        names = {row["attribute_name"] for row in schema}
        from application.requirement_bundle_service import REQUIREMENT_ALL_FIELDS
        assert names == set(REQUIREMENT_ALL_FIELDS)
        assert all(row["entity_type"] == "Requirement" for row in schema)
        assert all(isinstance(row["is_visible"], bool) for row in schema)

    def test_describe_schema_reflects_explicit_hidden_config(self, ...):
        svc = AttributeVisibilityConfigService()
        svc.create_config(
            ctx, entity_type="Requirement", attribute_name="description", is_visible=False
        )
        schema = svc.describe_schema(ctx, entity_type="Requirement")
        row = next(r for r in schema if r["attribute_name"] == "description")
        assert row["is_visible"] is False

    def test_describe_schema_without_entity_type_returns_all_known_types(self, ...):
        svc = AttributeVisibilityConfigService()
        schema = svc.describe_schema(ctx)
        entity_types = {row["entity_type"] for row in schema}
        assert "Requirement" in entity_types
```

Replace the `...` fixture args with whatever this existing test file already uses to construct an `AuthContext`/tenant (read `test_service_boundaries_req066.py` in full before writing — it already has a working `TestAttributeVisibilityConfigService` class right above where this new class should go, per the grep result from research: `backend/application/tests/test_service_boundaries_req066.py:78`).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec backend python -m pytest application/tests/test_service_boundaries_req066.py::TestDescribeSchema -v`
Expected: FAIL — `AttributeError: 'AttributeVisibilityConfigService' object has no attribute 'describe_schema'`

- [ ] **Step 3: Implement `describe_schema`**

```python
# Add to backend/application/attribute_visibility_service.py, inside the
# AttributeVisibilityConfigService class, in the "Read" section (near
# list_configs/get_config):

    # Known entity types and their full field sets, for schema discovery
    # (Requirement Bundle Export Plan 1, Task 4). Extend this dict when a new
    # entity type is wired into bundle export or any other consumer of
    # describe_schema.
    _KNOWN_SCHEMAS: dict[str, tuple[str, ...]] | None = None

    @staticmethod
    def _known_schemas() -> dict[str, tuple[str, ...]]:
        # Imported lazily to avoid a module-level circular import between
        # attribute_visibility_service and requirement_bundle_service.
        from application.requirement_bundle_service import REQUIREMENT_ALL_FIELDS

        return {"Requirement": REQUIREMENT_ALL_FIELDS}

    def describe_schema(
        self, ctx: AuthContext, entity_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the available attributes for *entity_type* (or every known
        entity type when omitted), with each attribute's current
        workspace/tenant visibility (Requirement Bundle Export, Plan 1).

        Used by REST/MCP callers to discover valid field names before making
        a filter_mode='custom' bundle-export request.
        """
        self._set_tenant_context(ctx)
        schemas = self._known_schemas()
        if entity_type is not None:
            if entity_type not in schemas:
                raise NotFoundError(f"Unknown entity_type {entity_type!r}")
            schemas = {entity_type: schemas[entity_type]}

        hidden_by_type: dict[str, set[str]] = {}
        for et in schemas:
            configs = AttributeVisibilityConfig.objects.filter(
                tenant_id=ctx.tenant_id, entity_type=et, is_visible=False
            )
            hidden_by_type[et] = {c.attribute_name for c in configs}

        result: list[dict[str, Any]] = []
        for et, field_names in schemas.items():
            hidden = hidden_by_type.get(et, set())
            for name in field_names:
                result.append(
                    {
                        "entity_type": et,
                        "attribute_name": name,
                        "is_visible": name not in hidden,
                    }
                )
        return result
```

Add `Any` to the existing `from typing import Any` import at the top of the file if not already present (it already is, per the file's current imports).

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest application/tests/test_service_boundaries_req066.py -v`
Expected: all PASS, including the 3 new `TestDescribeSchema` tests

- [ ] **Step 5: Commit**

```bash
git add backend/application/attribute_visibility_service.py backend/application/tests/test_service_boundaries_req066.py
git commit -m "feat: add describe_schema for attribute discovery"
```

---

### Task 5: REST endpoints

**Files:**
- Modify: `backend/rest_api/views.py` (add a custom action to `ArchitectureElementViewSet`, add a new `AttributeSchemaView`)
- Modify: `backend/rest_api/urls.py` (route `AttributeSchemaView`)
- Test: `backend/rest_api/tests/test_requirement_bundle_export.py`

**Interfaces:**
- Consumes: `RequirementBundleQueryService.get_bundle` (Task 1/2), `format_bundle_json`/`format_bundle_markdown`/`format_bundle_csv` (Task 3), `AttributeVisibilityConfigService.describe_schema` (Task 4), `get_auth_context`, `detect_lang`, `_service_error_response`, `build_error_response` (all already imported/used throughout `rest_api/views.py`, e.g. at `backend/rest_api/views.py:793-826`).
- Produces: `GET /api/v1/architecture/{pk}/requirement-bundle/`, `GET /api/v1/attribute-schema/`. Task 9 (a later, separate plan) wires the frontend against these two routes.

- [ ] **Step 1: Write the failing tests**

```python
# backend/rest_api/tests/test_requirement_bundle_export.py
"""REST tests for the Requirement Bundle Export raw endpoints (Plan 1 Task 5)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestRequirementBundleEndpoint:
    def test_default_depth_zero_json(self, authed_client: APIClient, workspace, architecture_element, requirement_allocated_to):
        # Follow this test file's sibling REST tests (e.g.
        # backend/rest_api/tests/test_traceability.py) for the exact fixture
        # names this project's REST test suite already uses for an
        # authenticated APIClient, a workspace, and an ArchitectureElement —
        # substitute the real fixture names/signatures here.
        root = architecture_element
        req = requirement_allocated_to(root)

        resp = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated_at_depth"] is False
        assert len(body["items"]) == 1
        assert body["items"][0]["requirement_id"] == str(req.id)

    def test_depth_param_is_respected(self, authed_client, architecture_element, child_architecture_element, requirement_allocated_to):
        root = architecture_element
        child = child_architecture_element(root)
        req_on_child = requirement_allocated_to(child)

        resp0 = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?depth=0")
        assert resp0.json()["items"] == []

        resp1 = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?depth=1")
        assert len(resp1.json()["items"]) == 1

    def test_format_markdown(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?format=markdown"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/markdown")
        assert resp.content.decode().startswith("#")

    def test_format_csv(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?format=csv")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")

    def test_custom_filter_mode_requires_fields(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?filter_mode=custom"
        )
        assert resp.status_code == 400

    def test_custom_filter_mode_with_fields(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?filter_mode=custom&fields=title,status"
        )
        assert resp.status_code == 200
        assert set(resp.json()["items"][0]["fields"].keys()) == {"title", "status"}

    def test_unknown_root_returns_404(self, authed_client):
        import uuid
        resp = authed_client.get(f"/api/v1/architecture/{uuid.uuid4()}/requirement-bundle/")
        assert resp.status_code == 404

    def test_depth_over_max_returns_400(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?depth=99"
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAttributeSchemaEndpoint:
    def test_lists_requirement_schema(self, authed_client):
        resp = authed_client.get("/api/v1/attribute-schema/?entity_type=Requirement")
        assert resp.status_code == 200
        names = {row["attribute_name"] for row in resp.json()}
        assert "title" in names
        assert "status" in names

    def test_without_entity_type_returns_all(self, authed_client):
        resp = authed_client.get("/api/v1/attribute-schema/")
        assert resp.status_code == 200
        entity_types = {row["entity_type"] for row in resp.json()}
        assert "Requirement" in entity_types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec backend python -m pytest rest_api/tests/test_requirement_bundle_export.py -v`
Expected: FAIL — 404s (routes don't exist yet)

- [ ] **Step 3: Implement the REST view + action**

```python
# In backend/rest_api/views.py:

# 1. Add these imports near the top, alongside the other application.*
#    service imports already present in this file:
from application.requirement_bundle_service import (
    RequirementBundleQueryService,
    BundleDepthExceededError,
)
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.attribute_visibility_service import AttributeVisibilityConfigService

# 2. Add this method inside ArchitectureElementViewSet (the class backing
#    `router.register(r"architecture", ArchitectureElementViewSet, ...)`,
#    rest_api/urls.py:129), placed near that class's other @action methods:

    @action(detail=True, methods=["get"], url_path="requirement-bundle")
    def requirement_bundle(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/requirement-bundle/
            ?depth=<int>&filter_mode=<all|visible|custom>&fields=<comma-list>
            &format=<json|markdown|csv>

        Requirement Bundle Export, Plan 1 Task 5. Raw (non-AI) bundle of every
        Requirement ALLOCATED_TO this element or its ALLOCATED_TO
        sub-elements, up to `depth` levels.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            element = self._svc().get_element(UUID(pk), ctx)
            workspace_id = element.artifact.workspace_id

            depth_param = request.query_params.get("depth")
            depth = int(depth_param) if depth_param is not None else None

            filter_mode = request.query_params.get("filter_mode", "all")
            fields_param = request.query_params.get("fields")
            fields = fields_param.split(",") if fields_param else None

            output_format = request.query_params.get("format", "json")
            if output_format not in ("json", "markdown", "csv"):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang,
                        message=f"Invalid format {output_format!r}; expected json, markdown, or csv",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = RequirementBundleQueryService().get_bundle(
                ctx,
                root_id=UUID(pk),
                workspace_id=workspace_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except BundleDepthExceededError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)

        if output_format == "json":
            return Response(format_bundle_json(result))
        if output_format == "markdown":
            from django.http import HttpResponse
            return HttpResponse(format_bundle_markdown(result), content_type="text/markdown; charset=utf-8")
        from django.http import HttpResponse
        return HttpResponse(format_bundle_csv(result), content_type="text/csv; charset=utf-8")

# 3. Add a new small view, placed near AttributeVisibilityConfigViewSet
#    (rest_api/urls.py:155) — as a plain APIView since it's a single
#    read-only lookup, not a resource CRUD set:

from rest_framework.views import APIView


class AttributeSchemaView(APIView):
    """GET /api/v1/attribute-schema/?entity_type=<optional>

    Requirement Bundle Export, Plan 1 Task 5 / Task 4.
    """

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            entity_type = request.query_params.get("entity_type")
            schema = AttributeVisibilityConfigService().describe_schema(
                ctx, entity_type=entity_type
            )
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(schema)
```

Verify `NotFoundError`, `PermissionDeniedError`, `ValidationError`, `UUID`, `Any`, `Request`, `Response`, `status`, `detect_lang`, `build_error_response`, `_service_error_response`, `get_auth_context`, `action` are all already imported at the top of `rest_api/views.py` before adding new ones — this file already imports most of these for the neighboring `diff`/`versions` actions read during planning; only add what's genuinely missing.

```python
# In backend/rest_api/urls.py, add near the other individual path()
# entries (the file already has ~40, following the same shape) — place
# just before `path("", include(router.urls))` (urls.py:447):

    path(
        "attribute-schema/",
        AttributeSchemaView.as_view(),
        name="api-v1-attribute-schema",
    ),
```

Add `AttributeSchemaView` to this file's `from rest_api.views import (...)` block (or wherever views are imported into `urls.py` — check the existing import style at the top of the file).

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest rest_api/tests/test_requirement_bundle_export.py -v`
Expected: all PASS (10 tests). If fixtures like `authed_client`, `architecture_element`, `child_architecture_element`, `requirement_allocated_to` don't exist yet in this test file's conftest chain, add them to `backend/rest_api/tests/conftest.py` (or the nearest applicable conftest) following the exact style of existing fixtures in `backend/rest_api/tests/test_traceability.py` or `test_architecture_decompose.py` — do not invent a divergent auth/fixture pattern.

- [ ] **Step 5: Run the full REST test suite to check for regressions**

Run: `docker-compose exec backend python -m pytest rest_api/ -v`
Expected: PASS, no new failures beyond this project's already-known pre-existing ones.

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/views.py backend/rest_api/urls.py backend/rest_api/tests/test_requirement_bundle_export.py backend/rest_api/tests/conftest.py
git commit -m "feat: add REST endpoints for requirement bundle export and attribute schema"
```

---

### Task 6: MCP tool group `requirement_bundle.*`

**Files:**
- Create: `backend/mcp_server/tools/requirement_bundle.py`
- Modify: `backend/mcp_server/tool_registry.py`
- Test: `backend/mcp_server/tests/test_requirement_bundle_tool_group.py`
- Modify: `docs/agent-templates/tool-manifest.json` (regenerate per this project's existing drift-guard convention — see Task 7's note below)

**Interfaces:**
- Consumes: `RequirementBundleQueryService.get_bundle` (Task 1/2), `format_bundle_json`/`format_bundle_markdown`/`format_bundle_csv` (Task 3), `AttributeVisibilityConfigService.describe_schema` (Task 4), `BaseToolGroup`, `require_uuid`, `require_param`, `optional_uuid` (`mcp_server.tools.base`, same imports as `mcp_server/tools/architecture.py:49-56`).
- Produces: MCP tools `requirement_bundle.export`, `requirement_bundle.attribute_schema`, registered under the `requirement_bundle` prefix in `tool_registry.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/mcp_server/tests/test_requirement_bundle_tool_group.py
"""Tests for the requirement_bundle.* MCP tool group (Plan 1 Task 6)."""
from __future__ import annotations

import pytest

from mcp_server.tools.requirement_bundle import RequirementBundleToolGroup


@pytest.mark.django_db
class TestRequirementBundleExportTool:
    def test_export_returns_json_by_default(
        self, mcp_auth_context, architecture_element, requirement_allocated_to
    ):
        # Follow mcp_server/tests/test_architecture_decompose.py or
        # test_ai_derivation_tool_group.py for this suite's existing
        # auth-context/fixture conventions and substitute them here.
        root = architecture_element
        requirement_allocated_to(root)

        group = RequirementBundleToolGroup()
        result = group.execute_tool(
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(root.artifact.workspace_id)},
            mcp_auth_context,
        )
        assert result.is_error is False
        assert "items" in result.content

    def test_export_depth_param(self, mcp_auth_context, architecture_element, child_architecture_element, requirement_allocated_to):
        root = architecture_element
        child = child_architecture_element(root)
        requirement_allocated_to(child)

        group = RequirementBundleToolGroup()
        result0 = group.execute_tool(
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(root.artifact.workspace_id), "depth": 0},
            mcp_auth_context,
        )
        assert result0.content["items"] == []

    def test_export_unknown_root_returns_error(self, mcp_auth_context):
        import uuid
        group = RequirementBundleToolGroup()
        result = group.execute_tool(
            "requirement_bundle.export",
            {"root_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
            mcp_auth_context,
        )
        assert result.is_error is True


@pytest.mark.django_db
class TestAttributeSchemaTool:
    def test_attribute_schema_returns_requirement_fields(self, mcp_auth_context):
        group = RequirementBundleToolGroup()
        result = group.execute_tool(
            "requirement_bundle.attribute_schema",
            {"entity_type": "Requirement"},
            mcp_auth_context,
        )
        assert result.is_error is False
        names = {row["attribute_name"] for row in result.content}
        assert "title" in names
```

Check `mcp_server/tools/base.py`'s `BaseToolGroup.execute_tool` and `ToolResult` shape (used by every other tool group, e.g. `mcp_server/tests/test_architecture_decompose.py`) before writing these assertions — match `result.is_error`/`result.content` (or whatever the real attribute names are) exactly rather than guessing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec backend python -m pytest mcp_server/tests/test_requirement_bundle_tool_group.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the tool group**

```python
# backend/mcp_server/tools/requirement_bundle.py
"""requirement_bundle.* MCP tools — raw bundle export + attribute schema
discovery (Requirement Bundle Export, Plan 1 Task 6).

Tools implemented:
  requirement_bundle.export            — grouped requirement export by
                                          architecture element (ALLOCATED_TO)
  requirement_bundle.attribute_schema  — list available/visible attributes

Interface contracts implemented:
  IF-MC-INT-003 — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService
    (RequirementBundleQueryService, AttributeVisibilityConfigService)
"""
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.attribute_visibility_service import AttributeVisibilityConfigService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.requirement_bundle_service import (
    BundleDepthExceededError,
    RequirementBundleQueryService,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_param,
    require_uuid,
)

logger = logging.getLogger(__name__)


class RequirementBundleToolGroup(BaseToolGroup):
    """requirement_bundle tool group (2 tools)."""

    _TOOL_MAP = {
        "requirement_bundle.export": "_handle_export",
        "requirement_bundle.attribute_schema": "_handle_attribute_schema",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "requirement_bundle.export",
            "description": (
                "Export every Requirement ALLOCATED_TO the given "
                "ArchitectureElement or its ALLOCATED_TO sub-elements, up to "
                "a configurable depth."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "root_id": {"type": "string", "description": "UUID of the root ArchitectureElement."},
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "depth": {
                        "type": "integer",
                        "description": "0 = only requirements directly allocated to root; omit for full hierarchy.",
                    },
                    "filter_mode": {
                        "type": "string",
                        "enum": ["all", "visible", "custom"],
                        "description": "Attribute selection mode. Defaults to 'all'.",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to include; required when filter_mode='custom'.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "csv"],
                        "description": "Output format. Defaults to 'json'.",
                    },
                },
                "required": ["root_id", "workspace_id"],
            },
        },
        {
            "name": "requirement_bundle.attribute_schema",
            "description": "List available attributes for an entity type, with current visibility.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Optional entity type filter, e.g. 'Requirement'. Omit for all known types.",
                    },
                },
                "required": [],
            },
        },
    ]

    def _handle_export(self, params: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        try:
            root_id = require_uuid(params, "root_id")
            workspace_id = require_uuid(params, "workspace_id")
            depth = params.get("depth")
            filter_mode = params.get("filter_mode", "all")
            fields = params.get("fields")
            output_format = params.get("format", "json")

            if output_format not in ("json", "markdown", "csv"):
                return ToolResult.error(f"Invalid format {output_format!r}")

            result = RequirementBundleQueryService().get_bundle(
                ctx,
                root_id=root_id,
                workspace_id=workspace_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
            )
        except (NotFoundError, PermissionDeniedError, BundleDepthExceededError, ValidationError) as exc:
            return ToolResult.error(str(exc))

        if output_format == "json":
            return ToolResult.success(format_bundle_json(result))
        if output_format == "markdown":
            return ToolResult.success(format_bundle_markdown(result))
        return ToolResult.success(format_bundle_csv(result))

    def _handle_attribute_schema(self, params: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        try:
            entity_type = params.get("entity_type")
            schema = AttributeVisibilityConfigService().describe_schema(
                ctx, entity_type=entity_type
            )
        except NotFoundError as exc:
            return ToolResult.error(str(exc))
        return ToolResult.success(schema)


__all__ = ["RequirementBundleToolGroup"]
```

Before finalizing, confirm the exact `ToolResult.success(...)`/`ToolResult.error(...)` constructor shape (or whatever this codebase's real convention is — read `mcp_server/protocol_handler.py`'s `ToolResult` class and how `mcp_server/tools/architecture.py`'s existing handlers build return values) and the exact `require_uuid`/`require_param`/`optional_uuid` signatures (`mcp_server/tools/base.py`) — adjust the code above to match precisely; do not guess method names.

- [ ] **Step 4: Register the tool group**

```python
# In backend/mcp_server/tool_registry.py, add the import near the other
# `from mcp_server.tools.* import *ToolGroup` lines (tool_registry.py:427-434):
from mcp_server.tools.requirement_bundle import RequirementBundleToolGroup

# Add to the self.register_groups({...}) dict (tool_registry.py:448-479),
# alongside the other single-owner entries:
            "requirement_bundle": RequirementBundleToolGroup(),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest mcp_server/tests/test_requirement_bundle_tool_group.py -v`
Expected: all PASS

- [ ] **Step 6: Run the manifest drift guard and regenerate if needed**

This project regenerates `docs/agent-templates/tool-manifest.json` whenever a tool's schema changes (see `mcp_server/tests/test_tool_manifest_drift.py` and how prior diagram-feature commits handled this — check for a management command or script that regenerates it, referenced in earlier commits of this repo's history). Run whatever that regeneration step is, then re-run:

Run: `docker-compose exec backend python -m pytest mcp_server/tests/test_tool_manifest_drift.py -v`
Expected: PASS, or the known pre-existing container-path-resolution failure already documented elsewhere in this project's history (not a new failure) — if you hit a DIFFERENT failure than that known one, investigate for real rather than assuming it's the same pre-existing issue.

- [ ] **Step 7: Update the MCP tool governance rule file**

The project's `.claude/rules/mcp-reqogniloom.md` maintains an explicit allow-list of MCP tools. Add `requirement_bundle.export` and `requirement_bundle.attribute_schema` to the "Erlaubte Tools" list in that file, in the same alphabetized/grouped style as the existing entries, with a one-line addition to "Agent-Hinweise" explaining when to use them (mirroring the existing per-tool usage hints in that file).

- [ ] **Step 8: Run the full MCP test suite to check for regressions**

Run: `docker-compose exec backend python -m pytest mcp_server/ -v`
Expected: PASS, no new failures.

- [ ] **Step 9: Commit**

```bash
git add backend/mcp_server/tools/requirement_bundle.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_requirement_bundle_tool_group.py docs/agent-templates/tool-manifest.json .claude/rules/mcp-reqogniloom.md
git commit -m "feat: add requirement_bundle.* MCP tool group"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** design spec §2 (ALLOCATED_TO) → Task 1. §3 (depth) → Task 1. §4 (3 filter modes + discovery) → Tasks 2, 4. §5 raw formats (JSON/Markdown/CSV) → Task 3. §7 REST/MCP raw endpoints → Tasks 5, 6. §8 error handling (404/depth cap/unknown custom fields) → covered across Tasks 1, 2, 5, 6. §5 compressed mode, §6 caching, §7 UI panel are explicitly NOT in this plan — see Follow-on plans below.
- Every task's code was written against real signatures read directly from this codebase during planning (`ServiceBase`, `AttributeVisibilityConfigService`, `TraceLink`/`pl_tracelink`, `ArtifactService.get_tree`'s CTE shape, `ArchitectureToolGroup`'s MCP pattern, `router.register`/`@action` REST pattern) — not invented APIs.
- Two things this plan could NOT verify from static reading and flags explicitly for the Task 1/2/4/5/6 implementers to confirm against the live codebase before trusting the plan's code verbatim: (a) `AttributeVisibilityConfig`'s true default-visibility convention when no config row exists (Task 2's `_resolve_field_set`); (b) the exact `ToolResult`/`require_uuid` call signatures in `mcp_server/tools/base.py` and `mcp_server/protocol_handler.py` (Task 6). Both are called out inline at the relevant step.

## Follow-on plans (not part of this plan)

1. **Requirement Bundle Export — Plan 2: AI Compression + Caching.** Adds a `BundleCompressionService`, a new `compress_bundle` capability across all 4 LLM provider implementations (`backend/llm_adapter/providers.py`) plus `ALLOWED_CAPABILITIES`/`llm_adapter/tasks.py` wiring for the async path (the existing `AsyncTaskDispatcher`/`run_capability` infrastructure, `backend/llm_adapter/dispatcher.py`, already supports exactly this "dispatch → poll task_id → get_task_status" shape — no new async infra needed, only a new capability), a new `bundle_compression` PromptTemplate type wired through the existing Phase-4 lookup chain (`AiDerivationService._get_template_content`, `backend/application/ai_derivation_service.py:1316`), and Redis-backed caching keyed on scope+filter+`(artifact_id, version)` hash. Depends on Plan 1's `RequirementBundleQueryService`/`BundleResult` types.
2. **Requirement Bundle Export — Plan 3: UI Panel.** Lazy-load panel/modal in the Architecture View, wired against this plan's REST endpoints (and Plan 2's compressed endpoint once it exists). Depends on Plan 1 (and optionally Plan 2) being deployed.

Write each as its own `docs/superpowers/plans/YYYY-MM-DD-...` document via a fresh `superpowers:writing-plans` pass when ready to start it — do not treat this list as those plans already existing.
