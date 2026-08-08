"""Tests for RequirementBundleQueryService (Requirement Bundle Export, Plan 1 Task 1)."""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

import pytest

from application.base import NotFoundError
from application.requirement_bundle_service import (
    BundleDepthExceededError,
    RequirementBundleQueryService,
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
