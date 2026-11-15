"""P3 Task 3.1: the flat allocation-view read object."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.allocation_view_service import AllocationViewService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    AllocationIntent,
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)

pytestmark = pytest.mark.django_db


def _env(slug="alloc-view"):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("editor",), auth_method="test"
    )
    return tenant, workspace, ctx


def _element(tenant, workspace, title, parent=None, sort_key="a0"):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="ArchitectureElement",
        sort_key=sort_key,
    )
    return ArchitectureElement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"E-{title}",
        parent=parent,
    )


def _requirement(tenant, workspace, title, intent="unassigned", sort_key="a0"):
    artifact = Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", sort_key=sort_key
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
        allocation_intent=intent,
    )


def _fixture(slug="alloc-view-fixture"):
    tenant, workspace, ctx = _env(slug)
    root = _element(tenant, workspace, "Root")
    child = _element(tenant, workspace, "Child", parent=root)
    allocated = _requirement(tenant, workspace, "Allocated", AllocationIntent.ALLOCATED)
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=allocated.artifact_id,
        target_id=child.artifact_id,
        link_type="allocated-to",
    )
    excluded = _requirement(
        tenant, workspace, "Excluded", AllocationIntent.NOT_ALLOCATABLE
    )
    return tenant, workspace, ctx, root, child, allocated, excluded


def test_rows_and_counters():
    _tenant, workspace, ctx, _root, _child, _allocated, _excluded = _fixture()

    payload = AllocationViewService().list(workspace.id, ctx)

    assert payload["meta"]["total"] == 4  # 2 requirements + 2 elements
    assert payload["meta"]["unallocated"] == 1
    assert payload["meta"]["findings"] == 0


def test_allocated_and_intent_filters():
    _tenant, workspace, ctx, _root, _child, allocated, excluded = _fixture("alloc-filters")
    service = AllocationViewService()

    only_allocated = service.list(workspace.id, ctx, allocated=True)
    assert [row["title"] for row in only_allocated["results"]] == ["Allocated"]

    excluded_rows = service.list(workspace.id, ctx, intent="not_allocatable")
    assert [row["title"] for row in excluded_rows["results"]] == ["Excluded"]
    assert excluded_rows["results"][0]["id"] == str(excluded.id)


def test_element_subtree_filter():
    _tenant, workspace, ctx, root, child, _allocated, _excluded = _fixture("alloc-subtree")

    payload = AllocationViewService().list(
        workspace.id, ctx, element_subtree=root.id
    )

    ids = {row["id"] for row in payload["results"]}
    assert str(child.id) in ids
    assert any(row["title"] == "Allocated" for row in payload["results"])


def test_page_size_cap_is_rejected():
    _tenant, workspace, ctx, *_ = _fixture("alloc-cap")
    with pytest.raises(ValidationError):
        AllocationViewService().list(workspace.id, ctx, page_size=501)


# ---------------------------------------------------------------------------
# V2.1 (B-1): the `kind` filter narrows the page, never the counters.
# ---------------------------------------------------------------------------


def test_kind_requirement_returns_only_requirements():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-req")

    payload = AllocationViewService().list(workspace.id, ctx, kind="requirement")

    assert {row["kind"] for row in payload["results"]} == {"requirement"}
    assert [row["title"] for row in payload["results"]] == ["Allocated", "Excluded"]


def test_kind_element_returns_only_elements():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-el")

    payload = AllocationViewService().list(workspace.id, ctx, kind="element")

    assert {row["kind"] for row in payload["results"]} == {"element"}
    assert [row["title"] for row in payload["results"]] == ["Root", "Child"]


def test_meta_is_independent_of_kind():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-meta")
    service = AllocationViewService()

    unchecked = service.list(workspace.id, ctx)
    requirements = service.list(workspace.id, ctx, kind="requirement")
    elements = service.list(workspace.id, ctx, kind="element")

    assert requirements["meta"] == unchecked["meta"]
    assert elements["meta"] == unchecked["meta"]
    # the counter covers all four filtered rows (2 requirements + 2 elements)
    assert unchecked["meta"]["total"] == 4


def test_kind_only_narrows_the_page_not_the_slice_window():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-paging")
    service = AllocationViewService()

    # The second element is at index 1 of the element-only set; a filter applied
    # *after* the slice would return nothing here.
    second_element_page = service.list(
        workspace.id, ctx, kind="element", page_size=1, offset=1
    )

    assert second_element_page["meta"]["total"] == 4
    assert [row["title"] for row in second_element_page["results"]] == ["Child"]


def test_unknown_kind_is_400():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-bad")

    with pytest.raises(ValidationError):
        AllocationViewService().list(workspace.id, ctx, kind="requirementz")


def test_kind_none_is_unchanged():
    _tenant, workspace, ctx, *_ = _fixture("alloc-kind-none")
    service = AllocationViewService()

    default = service.list(workspace.id, ctx)
    explicit_none = service.list(workspace.id, ctx, kind=None)

    assert explicit_none == default
    assert {row["kind"] for row in default["results"]} == {"requirement", "element"}


# ---------------------------------------------------------------------------
# V2.2 (B-2): element rows carry the sort key of their backing artifact.
# ---------------------------------------------------------------------------


def test_element_row_carries_artifact_sort_key():
    tenant, workspace, ctx = _env("alloc-el-sortkey")
    element = _element(tenant, workspace, "Sorted", sort_key="a5")

    payload = AllocationViewService().list(workspace.id, ctx, kind="element")

    assert [row["id"] for row in payload["results"]] == [str(element.id)]
    assert payload["results"][0]["sort_key"] == "a5"


class _FakeValuesQuery:
    """Minimal stand-in for ``Artifact.unscoped.filter(...).values(...)``."""

    def __init__(self, rows):
        self._rows = rows

    def values(self, *_fields):
        return self._rows


def test_element_without_artifact_row_has_none():
    tenant, workspace, ctx = _env("alloc-el-noartifact")
    requirement = _requirement(tenant, workspace, "Kept")
    _element(tenant, workspace, "Orphan")

    requirement_artifact = {
        "id": requirement.artifact_id,
        "parent_id": None,
        "sort_key": "a0",
    }
    fake_artifact = type(
        "FakeArtifact",
        (),
        {
            "unscoped": type(
                "FakeUnscoped",
                (),
                {"filter": staticmethod(lambda **_kw: _FakeValuesQuery([requirement_artifact]))},
            )()
        },
    )
    with patch("application.allocation_view_service.Artifact", fake_artifact):
        payload = AllocationViewService().list(workspace.id, ctx)

    by_title = {row["title"]: row for row in payload["results"]}
    assert by_title["Orphan"]["sort_key"] is None
    assert by_title["Kept"]["sort_key"] == "a0"


# ---------------------------------------------------------------------------
# V2 acceptance: the 500 cap applies per kind, not to the combined set.
# ---------------------------------------------------------------------------


def test_600_requirements_and_20_elements_yield_all_elements():
    tenant, workspace, ctx = _env("alloc-500-cap")

    requirement_artifacts = Artifact.unscoped.bulk_create(
        [
            Artifact(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                sort_key="a0",
            )
            for _ in range(600)
        ]
    )
    Requirement.unscoped.bulk_create(
        [
            Requirement(
                tenant=tenant,
                workspace=workspace,
                artifact=artifact,
                title=f"R{index}",
                uid=f"R-{index}",
            )
            for index, artifact in enumerate(requirement_artifacts)
        ]
    )
    element_artifacts = Artifact.unscoped.bulk_create(
        [
            Artifact(
                tenant=tenant,
                workspace=workspace,
                artifact_type="ArchitectureElement",
                sort_key="a0",
            )
            for _ in range(20)
        ]
    )
    ArchitectureElement.unscoped.bulk_create(
        [
            ArchitectureElement(
                tenant=tenant,
                workspace=workspace,
                artifact=artifact,
                title=f"E{index}",
                uid=f"E-{index}",
            )
            for index, artifact in enumerate(element_artifacts)
        ]
    )

    payload = AllocationViewService().list(workspace.id, ctx, kind="element")

    # Before V2.1 the combined page (capped at 500) returned zero elements.
    assert len(payload["results"]) == 20
    assert {row["kind"] for row in payload["results"]} == {"element"}
    assert payload["meta"]["total"] == 620


def test_no_additional_query_for_elements():
    tenant, workspace, ctx = _env("alloc-el-queries")
    _element(tenant, workspace, "First")
    service = AllocationViewService()
    # warm-up: the tier ladder / workflow definitions are cached after this call
    service.list(workspace.id, ctx)

    with CaptureQueriesContext(connection) as before:
        service.list(workspace.id, ctx)

    for index in range(5):
        _element(tenant, workspace, f"Extra {index}")

    with CaptureQueriesContext(connection) as after:
        service.list(workspace.id, ctx)

    assert len(after) == len(before)
    # one lookup for both row kinds: exactly one artifact query, no second one
    artifact_queries = [
        query
        for query in after.captured_queries
        if '"pl_artifact"' in query["sql"] and "sort_key" in query["sql"]
    ]
    assert len(artifact_queries) == 1
