"""Tests for RequirementBundleQueryService (Requirement Bundle Export, Plan 1 Task 1)."""
from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

import pytest

from application.base import NotFoundError
from application.requirement_bundle_service import (
    MAX_DEPTH,
    BundleDepthExceededError,
    RequirementBundleQueryService,
    describe_attribute_schema,
)
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
#
# Elements/requirements/links are created directly against the ORM rather
# than via ArchitectureService/RequirementService/TraceLinkService, mirroring
# the established pattern in application/tests/test_architecture_decompose.py
# (`_artifact`/`_arch`/`_requirement`/`_allocate`). This is a deliberate
# deviation from the plan brief's assumption that the fixtures could go
# through ArchitectureService.create_architecture_element: invariant I5
# ("at most one root ArchitectureElement per workspace", enforced on *every*
# rigor tier — see application/validators.py) would reject the second,
# third, ... independent ArchitectureElement each test creates with
# parent_id=None, since these tests deliberately link elements only via
# ALLOCATED_TO TraceLinks, never via the structural parent_id tree that I5
# guards. Direct ORM creation bypasses that service-layer invariant, which
# is correct here: the invariant governs the structural tree, not the
# ALLOCATED_TO allocation graph this service walks.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Bundle Tenant", slug="bundle-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="bundle-user", email="bundle@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Bundle-WS")


@pytest.fixture
def auth_ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Bundle Tenant",
    )


@pytest.fixture
def make_architecture_element(tenant: Tenant):
    def _make(ws: Workspace, title: str = "AE", parent=None) -> ArchitectureElement:
        with _active(tenant):
            art = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="ArchitectureElement"
            )
            return ArchitectureElement.objects.create(
                tenant=tenant, artifact=art, title=title, parent=parent
            )

    return _make


@pytest.fixture
def make_requirement(tenant: Tenant):
    def _make(ws: Workspace, title: str = "Requirement") -> Requirement:
        with _active(tenant):
            art = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement"
            )
            return Requirement.objects.create(tenant=tenant, artifact=art, title=title)

    return _make


@pytest.fixture
def make_allocated_to_link(tenant: Tenant):
    def _make(source, target) -> TraceLink:
        with _active(tenant):
            return TraceLink.objects.create(
                tenant=tenant,
                source=source.artifact,
                target=target.artifact,
                link_type=LinkType.ALLOCATED_TO.value,
            )

    return _make


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
        # found_under_element_id is the *Artifact* id (see the plan's "Note
        # on found_under_element_id"), not the ArchitectureElement's own
        # business id — the brief's draft assertion compared against
        # root.id, which is a different UUID from root.artifact_id and
        # would never match; fixed here to compare against root.artifact_id.
        assert result.items[0].found_under_element_id == root.artifact_id
        assert result.items[0].depth == 0
        assert result.truncated_at_depth is False


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
        svc = RequirementBundleQueryService()
        with pytest.raises(NotFoundError):
            svc.get_bundle(auth_ctx, root_id=uuid.uuid4(), workspace_id=workspace.id, depth=0)


@pytest.mark.django_db
class TestGetBundleTruncationAndDedup:
    """Regression tests added after code review round 1 (CHANGES_REQUESTED)."""

    def test_truncation_flag_reflects_full_walk_not_just_rows_with_requirements(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """truncated_at_depth must be derived from the full arch_tree walk,
        not from the subset of elements that happen to have a
        directly-allocated Requirement (the plan's Global Constraint "never
        silently flattened").

        Builds an ALLOCATED_TO chain deeper than MAX_DEPTH (20) with no
        Requirement allocated anywhere within the visited depth range
        (0..20) — only at the unreachable tail (depth 24). Pre-fix, the flag
        was computed as ``any(r[2] >= MAX_DEPTH for r in rows)`` over the
        post-JOIN `rows`, which are empty here (no Requirement in range), so
        it silently reported False even though req_deep exists but is
        missing from the result because its element sits beyond the depth
        cap.
        """
        root = make_architecture_element(workspace, title="Chain root")
        current = root
        for level in range(1, 25):
            nxt = make_architecture_element(workspace, title=f"Chain L{level}")
            make_allocated_to_link(source=nxt, target=current)
            current = nxt
        # `current` is now the deepest element (depth 24), well past MAX_DEPTH=20.
        req_deep = make_requirement(workspace, title="Unreachably deep")
        make_allocated_to_link(source=req_deep, target=current)

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None)

        assert result.items == []  # req_deep exists but its element is unreachable
        assert result.truncated_at_depth is True

    def test_allocated_requirement_is_reported_once_at_its_own_depth(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """N:1 rewrite of the former "diamond dedups to shallowest path" test.

        Before P2 the same element could carry ALLOCATED_TO edges to two
        parents, so one Requirement was reachable from the root at two
        different depths; ``DISTINCT ON (req_link.source_id) ... ORDER BY
        req_link.source_id, arch_tree.depth ASC`` then had to keep the
        shallower row. P2's partial unique index
        (``uniq_tracelink_allocated_to_source``, spec E4/B6) makes that state
        unrepresentable: every element has at most one parent edge, so the
        allocation graph is a forest and each Requirement is reachable along
        exactly one path.

        The observable property this test still pins is the one the guard
        existed to produce: every Requirement surfaces exactly once, at the
        depth of the element it is actually allocated to.
        """
        root = make_architecture_element(workspace, title="Root")
        child = make_architecture_element(workspace, title="Child")
        make_allocated_to_link(source=child, target=root)
        grandchild = make_architecture_element(workspace, title="Grandchild")
        make_allocated_to_link(source=grandchild, target=child)

        req_root = make_requirement(workspace, title="Allocated to root")
        make_allocated_to_link(source=req_root, target=root)
        req_deep = make_requirement(workspace, title="Allocated to grandchild")
        make_allocated_to_link(source=req_deep, target=grandchild)

        # ADR-028 D9 moved the N:1 rule out of the database (the cardinality is
        # a per-workspace setting now, see application/tests/
        # test_multi_allocation_config.py). The bundle assertion below is not
        # about that rule: it pins that every requirement surfaces once at the
        # depth of the element it is allocated to.

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None)

        assert sorted((i.requirement_id, i.depth) for i in result.items) == sorted(
            [(req_root.id, 0), (req_deep.id, 2)]
        )
        assert len({i.requirement_id for i in result.items}) == len(result.items)

    def test_truncation_flag_false_for_natural_boundary_at_exactly_max_depth(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """Regression test for the code-review round-2 finding: a hierarchy
        that is exactly MAX_DEPTH (20) levels deep and terminates naturally
        (no further children beyond the boundary, no Requirement near it)
        must NOT be reported as truncated — nothing was actually cut off.

        The round-1 fix computed truncation as ``EXISTS (SELECT 1 FROM
        arch_tree WHERE depth >= effective_cap)``, which only proves a node
        exists at the cap depth, not that anything was cut off there. Since
        the recursive walk always visits (and includes) the boundary node
        itself before checking whether to recurse further, that check
        false-positived on exactly this natural-termination case.
        """
        root = make_architecture_element(workspace, title="Boundary root")
        current = root
        for level in range(1, MAX_DEPTH + 1):  # exactly MAX_DEPTH hops: L1..L20
            nxt = make_architecture_element(workspace, title=f"Boundary L{level}")
            make_allocated_to_link(source=nxt, target=current)
            current = nxt
        # `current` is now L20 (depth == MAX_DEPTH), with no further children
        # and no Requirement anywhere near the boundary.
        req_shallow = make_requirement(workspace, title="Shallow, unrelated")
        make_allocated_to_link(source=req_shallow, target=root)

        svc = RequirementBundleQueryService()
        result = svc.get_bundle(auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None)

        assert {i.requirement_id for i in result.items} == {req_shallow.id}
        assert result.truncated_at_depth is False


@pytest.mark.django_db
class TestArchTreeWalkConstraints:
    """Regression tests for the recursive CTE's two under-constraints
    (final whole-branch review, Fix 4)."""

    def test_requirement_to_requirement_edge_is_not_walked_as_an_element(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """A Requirement --allocated-to--> Requirement edge must never put a
        Requirement artifact into arch_tree.

        SE_LINK_SEMANTICS constrains ALLOCATED_TO endpoints to
        {(Requirement, ArchitectureElement), (ArchitectureElement,
        ArchitectureElement)}, but TraceLinkService._check_se_semantics
        returns early unless the workspace has se_mode configured — so in an
        ordinary dev-mode workspace this edge is creatable. Without the
        artifact_type join on the recursive term, req_a's artifact would be
        walked as if it were an architecture element and req_b would surface
        with found_under_element_id pointing at a Requirement.
        """
        root = make_architecture_element(workspace, title="Root")
        req_a = make_requirement(workspace, title="Allocated to root")
        make_allocated_to_link(source=req_a, target=root)
        req_b = make_requirement(workspace, title="Allocated to a Requirement")
        make_allocated_to_link(source=req_b, target=req_a)

        result = RequirementBundleQueryService().get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None
        )

        assert {i.requirement_id for i in result.items} == {req_a.id}
        assert all(
            i.found_under_element_id != req_a.artifact_id for i in result.items
        )

    def test_shared_ancestor_returns_one_row_per_requirement(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """N:1 rewrite of the former equal-depth diamond test.

        The old fixture allocated one shared child to two parents, which P2's
        partial unique index now rejects. The property that fixture was there
        to protect is unchanged: two branches under the same ancestor must not
        multiply or merge the rows of the Requirements attached to them —
        every Requirement is reported exactly once, at its branch's depth.
        """
        root = make_architecture_element(workspace, title="Root")
        p1 = make_architecture_element(workspace, title="P1")
        p2 = make_architecture_element(workspace, title="P2")
        make_allocated_to_link(source=p1, target=root)
        make_allocated_to_link(source=p2, target=root)
        req_p1 = make_requirement(workspace, title="Under P1")
        make_allocated_to_link(source=req_p1, target=p1)
        req_p2 = make_requirement(workspace, title="Under P2")
        make_allocated_to_link(source=req_p2, target=p2)

        result = RequirementBundleQueryService().get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=None
        )

        assert len(result.items) == 2
        assert sorted((i.requirement_id, i.depth) for i in result.items) == sorted(
            [(req_p1.id, 1), (req_p2.id, 1)]
        )

    def test_shared_cte_yields_each_element_once_under_n_to_one(
        self, auth_ctx, workspace, make_architecture_element, make_allocated_to_link
    ):
        """White-box guard on the shared CTE itself (N:1 rewrite).

        The former version asserted that ``UNION`` (not ``UNION ALL``) collapses
        a diamond: without it the walk would grow per path instead of per
        node. P2's partial unique index makes a diamond unrepresentable
        (an element has exactly one parent edge), so no data can trigger the
        difference any more. Two guards remain here:

        * structural: the query text must keep ``UNION`` — switching to
          ``UNION ALL`` would silently remove the only path-multiplication
          guard should the cardinality rule ever be relaxed again;
        * behavioural: on the legal forest shape the walk returns each element
          exactly once, at its real depth, with no duplicate rows.
        """
        from django.db import connection

        from application.requirement_bundle_service import (
            _ARCH_TREE_CTE,
            MAX_DEPTH,
        )

        assert "UNION ALL" not in _ARCH_TREE_CTE
        assert "UNION" in _ARCH_TREE_CTE

        root = make_architecture_element(workspace, title="Root")
        p1 = make_architecture_element(workspace, title="P1")
        p2 = make_architecture_element(workspace, title="P2")
        make_allocated_to_link(source=p1, target=root)
        make_allocated_to_link(source=p2, target=root)
        child = make_architecture_element(workspace, title="Child of P1")
        make_allocated_to_link(source=child, target=p1)

        svc = RequirementBundleQueryService()
        svc._set_tenant_context(auth_ctx)  # RLS GUC + thread-local tenant
        with connection.cursor() as cursor:
            cursor.execute(
                _ARCH_TREE_CTE + " SELECT element_artifact_id, depth FROM arch_tree;",
                [
                    str(root.artifact_id),
                    LinkType.ALLOCATED_TO.value,
                    str(auth_ctx.tenant_id),
                    MAX_DEPTH,
                ],
            )
            rows = cursor.fetchall()

        assert sorted(rows, key=lambda r: (r[1], str(r[0]))) == sorted(
            [
                (root.artifact_id, 0),
                (p1.artifact_id, 1),
                (p2.artifact_id, 1),
                (child.artifact_id, 2),
            ],
            key=lambda r: (r[1], str(r[0])),
        )
        assert len(rows) == len({row[0] for row in rows})


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

    def test_invalid_filter_mode_raises_validation_error(
        self, auth_ctx, workspace, make_architecture_element
    ):
        """An unrecognised filter_mode is rejected before any query runs."""
        from application.base import ValidationError

        root = make_architecture_element(workspace, title="Root")
        with pytest.raises(ValidationError, match="bogus"):
            RequirementBundleQueryService().get_bundle(
                auth_ctx,
                root_id=root.id,
                workspace_id=workspace.id,
                depth=0,
                filter_mode="bogus",
            )

    def test_all_fields_includes_audit_timestamps(
        self, auth_ctx, workspace, make_architecture_element, make_requirement, make_allocated_to_link
    ):
        """created_at/modified_at are ordinary user-visible Requirement
        columns (RequirementSerializer publishes them as
        created_at/updated_at) and must be part of the "all" field set —
        they were previously missing, so filter_mode='all' never returned
        them and filter_mode='custom' rejected them as unknown fields.
        """
        from application.requirement_bundle_service import REQUIREMENT_ALL_FIELDS

        assert "created_at" in REQUIREMENT_ALL_FIELDS
        assert "modified_at" in REQUIREMENT_ALL_FIELDS

        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        result = RequirementBundleQueryService().get_bundle(
            auth_ctx,
            root_id=root.id,
            workspace_id=workspace.id,
            depth=0,
            filter_mode="custom",
            fields=["created_at", "modified_at"],
        )
        assert set(result.items[0].fields.keys()) == {"created_at", "modified_at"}
        assert result.items[0].fields["created_at"] is not None

    def test_filter_mode_visible_degrades_to_all_fields(
        self, auth_ctx, workspace, make_architecture_element, make_requirement,
        make_allocated_to_link,
    ):
        """AttributeVisibilityConfig (and the per-tenant hide toggle it drove)
        was retired in Task 9 (spec section 4). filter_mode='visible' is kept
        as a valid, still-accepted request value (REST/MCP contract), but
        currently degrades to the same result as filter_mode='all' rather
        than crashing or silently dropping fields — see
        RequirementBundleQueryService._resolve_field_set /
        application.requirement_bundle_service.describe_attribute_schema.
        Real per-attribute visibility (sourced from
        WorkspaceAttributeDefinition) is future work, not part of this task.
        """
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        svc = RequirementBundleQueryService()
        visible_result = svc.get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0, filter_mode="visible"
        )
        all_result = svc.get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0, filter_mode="all"
        )
        assert set(visible_result.items[0].fields) == set(all_result.items[0].fields)
        assert "title" in visible_result.items[0].fields

    def test_filter_mode_visible_is_not_admin_only(
        self, auth_ctx, workspace, make_architecture_element, make_requirement,
        make_allocated_to_link,
    ):
        """Regression guard (#470): filter_mode='visible' must stay usable by
        non-admin roles. auth_ctx here holds only ('editor',)."""
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="R1")
        make_allocated_to_link(source=req, target=root)

        assert "admin" not in auth_ctx.active_roles
        result = RequirementBundleQueryService().get_bundle(
            auth_ctx, root_id=root.id, workspace_id=workspace.id, depth=0,
            filter_mode="visible",
        )
        assert "title" in result.items[0].fields


# ---------------------------------------------------------------------------
# GitHub #1192 — effective required-field flag on the attribute schema
# ---------------------------------------------------------------------------


class TestDescribeAttributeSchemaRequired:
    """``describe_attribute_schema`` rows carry the effective approval-gate
    ``is_required`` flag and the active ``tier`` (GitHub #1192).

    ``is_required`` names the set ``workflow.precondition_rules`` Rule 5
    demands on approval — the definition ``required`` flags (visibility-aware)
    UNION the legacy preset ``mandatory_fields`` for Requirement — not the
    ``AttributeDescriptor.required`` create-payload flag alone. The keys are
    additive: an existing consumer reading ``entity_type`` / ``attribute_name``
    / ``is_visible`` by key stays compatible.
    """

    _ROW_KEYS = frozenset(
        {"entity_type", "attribute_name", "is_visible", "is_required", "tier"}
    )

    @staticmethod
    def _rows(auth_ctx, workspace, entity_type: str = "Requirement") -> dict:
        rows = describe_attribute_schema(auth_ctx, workspace.id, entity_type)
        return {row["attribute_name"]: row for row in rows}

    def test_row_shape_is_additive(self, auth_ctx, workspace):
        """Every row keeps the three legacy keys and adds exactly two."""
        rows = self._rows(auth_ctx, workspace)
        assert rows
        for row in rows.values():
            assert set(row) == self._ROW_KEYS

    def test_minimal_preset_requires_only_title(self, auth_ctx, workspace):
        """The default (minimal) workspace gate demands ``title`` only."""
        rows = self._rows(auth_ctx, workspace)
        assert {row["tier"] for row in rows.values()} == {"minimal"}
        assert rows["title"]["is_required"] is True
        assert rows["acceptance_criteria"]["is_required"] is False

    def test_standard_preset_requires_acceptance_criteria(self, auth_ctx, workspace):
        """Standard/extended add ``acceptance_criteria`` to the gate."""
        from presets.services import switch_preset

        switch_preset(str(workspace.id), "standard")
        rows = self._rows(auth_ctx, workspace)
        assert {row["tier"] for row in rows.values()} == {"standard"}
        assert rows["title"]["is_required"] is True
        assert rows["acceptance_criteria"]["is_required"] is True

    def test_required_flag_is_the_gate_set_not_the_descriptor_flag(
        self, auth_ctx, workspace, tenant
    ):
        """After bootstrapping, ``acceptance_criteria`` carries
        ``required=False`` (the model column is ``blank=True``) yet the
        standard preset's approval gate demands it. The row must follow
        ``scoped_mandatory_fields`` — the same resolver Rule 5 uses — not
        ``AttributeDescriptor.required``.
        """
        from django.core.management import call_command

        from application.artifact_attribute_gateway import ArtifactAttributeGateway
        from presets.services import switch_preset

        with _active(tenant):
            switch_preset(str(workspace.id), "standard")
            call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

        descriptors = {
            descriptor.name: descriptor
            for descriptor in ArtifactAttributeGateway().discover(
                auth_ctx, "Requirement", workspace.id
            )
        }
        assert descriptors["acceptance_criteria"].required is False

        rows = self._rows(auth_ctx, workspace)
        assert rows["acceptance_criteria"]["is_required"] is True
        assert rows["title"]["is_required"] is True


@pytest.mark.django_db
class TestBundleExposesRequirementTier:
    """P2/V4/V5: a bundle export publishes the stable ladder key and the
    ladder's display name next to the permanent integer alias ``level``."""

    def test_all_mode_exposes_tier_key_name_and_level(
        self,
        auth_ctx,
        workspace,
        tenant,
        make_architecture_element,
        make_requirement,
        make_allocated_to_link,
    ):
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="Tiered")
        with _active(tenant):
            req.tier_key = "dazwischen"
            req.level = 2
            req.save(update_fields=["tier_key", "level"])
        make_allocated_to_link(source=req, target=root)

        result = RequirementBundleQueryService().get_bundle(
            auth_ctx,
            root_id=root.id,
            workspace_id=workspace.id,
            depth=0,
            filter_mode="all",
        )

        fields = result.items[0].fields
        assert fields["level"] == 2
        assert fields["tier_key"] == "dazwischen"
        assert fields["tier_name"] == "Middle"

    def test_custom_mode_can_request_tier_name_only(
        self,
        auth_ctx,
        workspace,
        tenant,
        make_architecture_element,
        make_requirement,
        make_allocated_to_link,
    ):
        root = make_architecture_element(workspace, title="Root")
        req = make_requirement(workspace, title="Tiered")
        with _active(tenant):
            req.tier_key = "letzte"
            req.save(update_fields=["tier_key"])
        make_allocated_to_link(source=req, target=root)

        result = RequirementBundleQueryService().get_bundle(
            auth_ctx,
            root_id=root.id,
            workspace_id=workspace.id,
            depth=0,
            filter_mode="custom",
            fields=["tier_name"],
        )

        assert result.items[0].fields == {"tier_name": "Last"}
