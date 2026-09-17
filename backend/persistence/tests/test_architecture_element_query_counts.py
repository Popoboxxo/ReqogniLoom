"""Issue #129 regression tests: ArchitectureElement level/role query counts.

``get_level()`` used to recurse in Python, issuing one query per ancestor, so
the cost of reading ``element.level`` scaled with tree depth — and with tree
size when a caller looped over elements. These tests pin the query count so the
N+1 cannot silently return.
"""

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

from persistence.models import ArchitectureElement, Artifact
from persistence.tenancy import TenantContext


def _build_chain(workspace, depth: int) -> list[ArchitectureElement]:
    """Create a linear parent->child chain of *depth* + 1 elements."""
    elements: list[ArchitectureElement] = []
    parent = None
    for index in range(depth + 1):
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="element"
        )
        parent = ArchitectureElement.objects.create(
            artifact=artifact, title=f"Node {index}", parent=parent
        )
        elements.append(parent)
    return elements


@pytest.mark.django_db(transaction=True)
class TestGetLevelQueryCount:
    """get_level() must cost exactly one query, independent of tree depth."""

    @pytest.mark.parametrize("depth", [1, 3, 6])
    def test_get_level_is_single_query_regardless_of_depth(
        self, workspace_a, tenant_a, depth
    ):
        TenantContext.set_tenant(tenant_a.id)
        elements = _build_chain(workspace_a, depth)
        leaf = elements[-1]

        with CaptureQueriesContext(connection) as captured:
            level = leaf.get_level()

        assert level == depth
        assert len(captured) == 1, (
            f"get_level() issued {len(captured)} queries for depth {depth}; "
            "expected 1 (recursive CTE, issue #129)"
        )

    def test_root_get_level_issues_no_query(self, workspace_a, tenant_a):
        TenantContext.set_tenant(tenant_a.id)
        root = _build_chain(workspace_a, 0)[0]

        with CaptureQueriesContext(connection) as captured:
            assert root.get_level() == 0

        assert len(captured) == 0


@pytest.mark.django_db(transaction=True)
class TestAnnotateLevelsQueryCount:
    """annotate_levels() must cost one query for the whole set."""

    def test_query_count_does_not_scale_with_tree_size(
        self, workspace_a, tenant_a
    ):
        TenantContext.set_tenant(tenant_a.id)
        small = _build_chain(workspace_a, 2)
        large = _build_chain(workspace_a, 8)

        with CaptureQueriesContext(connection) as small_queries:
            small_levels = ArchitectureElement.annotate_levels(small)
        with CaptureQueriesContext(connection) as large_queries:
            large_levels = ArchitectureElement.annotate_levels(large)

        assert len(small_queries) == len(large_queries) == 1
        assert [small_levels[el.id] for el in small] == [0, 1, 2]
        assert [large_levels[el.id] for el in large] == list(range(9))

    def test_annotation_is_consumed_by_the_level_property(
        self, workspace_a, tenant_a
    ):
        TenantContext.set_tenant(tenant_a.id)
        elements = _build_chain(workspace_a, 3)
        ArchitectureElement.annotate_levels(elements)

        with CaptureQueriesContext(connection) as captured:
            levels = [el.level for el in elements]

        assert levels == [0, 1, 2, 3]
        assert len(captured) == 0

    def test_empty_input_issues_no_query(self, workspace_a, tenant_a):
        TenantContext.set_tenant(tenant_a.id)
        with CaptureQueriesContext(connection) as captured:
            assert ArchitectureElement.annotate_levels([]) == {}
        assert len(captured) == 0

    def test_unsaved_element_with_parent_falls_back_to_zero(
        self, workspace_a, tenant_a
    ):
        """An element the CTE cannot resolve degrades to 0, as before.

        A truly orphaned row is unreachable in practice (``parent`` is a
        CASCADE FK), so this exercises the closest reachable case: an instance
        that is not (yet) in the table.
        """
        TenantContext.set_tenant(tenant_a.id)
        root = _build_chain(workspace_a, 0)[0]
        artifact = Artifact.objects.create(
            workspace=workspace_a, artifact_type="element"
        )
        detached = ArchitectureElement(
            artifact=artifact, title="Detached", parent=root, tenant=tenant_a
        )

        assert detached.get_level() == 0


@pytest.mark.django_db(transaction=True)
class TestAnnotateRolesQueryCount:
    """annotate_roles() resolves the children check in one query."""

    def test_roles_for_whole_set_in_constant_queries(
        self, workspace_a, tenant_a
    ):
        TenantContext.set_tenant(tenant_a.id)
        elements = _build_chain(workspace_a, 3)

        with CaptureQueriesContext(connection) as captured:
            ArchitectureElement.annotate_roles(elements)

        assert len(captured) == 1
        assert [el.role for el in elements] == [
            "system",
            "subsystem",
            "subsystem",
            "component",
        ]
