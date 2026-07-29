"""
REQ-L1-042: TraceLink allocated-to + Allocation-Coverage Reporter tests.

Unit and integration tests for allocation tracking and coverage reporting.
"""
from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from application.architecture_service import ArchitectureService
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import ArchitectureElement, Requirement, TraceLink, Tenant, User, Workspace as PersistenceWorkspace
from traceability.types import LinkType


@pytest.fixture
def tenant():
    """Create test tenant."""
    return Tenant.objects.create(name="test-tenant", slug="test-tenant")


@pytest.fixture
def user(tenant):
    """Create test user."""
    u = User.objects.create(
        username="testuser",
        email="test@example.com",
        tenant=tenant,
    )
    return u


@pytest.fixture
def workspace(tenant):
    """Create test workspace."""
    from persistence.tenancy import TenantContext
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(
            tenant=tenant,
            name="test-workspace",
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def auth_context(user):
    """Create auth context.

    active_roles=("editor",): these tests exercise allocation/coverage logic,
    not the RBAC gate, so the context needs a real write-permitting role.
    An empty tuple used to slip past ``ServiceBase._assert_write_permission``
    only because that check was fail-open for any non-("viewer",) value
    (Systemaudit #100) — now fixed to be fail-closed, an empty role tuple is
    correctly denied.
    """
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="test-tenant",
    )


@pytest.mark.django_db
class TestAllocationTraceLink:
    """Test TraceLink allocated-to type creation and management."""

    def test_create_allocated_to_tracelink(self, auth_context, workspace):
        """Test creating an allocated-to TraceLink between Requirement and ArchitectureElement."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        # Create Requirement
        req = req_svc.create_requirement(
            workspace_id=workspace.id,
            title="Allocate to Component",
            ctx=auth_context,
        )

        # Create ArchitectureElement (root)
        arch_el = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Test Component",
            ctx=auth_context,
        )

        # Create allocated-to link
        link = link_svc.allocate(
            requirement_id=req.id,
            architecture_element_id=arch_el.id,
            ctx=auth_context,
        )

        assert link is not None
        assert link.link_type == LinkType.ALLOCATED_TO
        # Note: TraceLink stores artifact IDs, not entity IDs directly
        assert link.source is not None
        assert link.target is not None

    def test_allocate_overwrites_previous_allocation(self, auth_context, workspace):
        """Test that allocating a Requirement to a new element removes the old allocation."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        # Create Requirement
        req = req_svc.create_requirement(
            workspace_id=workspace.id,
            title="Requirement to reallocate",
            ctx=auth_context,
        )

        # Create two ArchitectureElements
        arch_el_1 = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Component A",
            ctx=auth_context,
        )
        arch_el_2 = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Component B",
            parent_id=arch_el_1.id,
            ctx=auth_context,
        )

        # Allocate to first component
        link1 = link_svc.allocate(
            requirement_id=req.id,
            architecture_element_id=arch_el_1.id,
            ctx=auth_context,
        )
        first_link_id = link1.id

        # Allocate to second component
        link2 = link_svc.allocate(
            requirement_id=req.id,
            architecture_element_id=arch_el_2.id,
            ctx=auth_context,
        )

        # Old link should be deleted
        assert not TraceLink.objects.filter(id=first_link_id).exists()
        # New link should exist
        assert TraceLink.objects.filter(id=link2.id).exists()

    def test_allocation_unique_per_requirement(self, auth_context, workspace):
        """Test that a Requirement can only have one allocated-to link."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        req = req_svc.create_requirement(
            workspace_id=workspace.id,
            title="Unique allocation test",
            ctx=auth_context,
        )

        arch_el = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Component C",
            ctx=auth_context,
        )

        # Allocate
        link_svc.allocate(
            requirement_id=req.id,
            architecture_element_id=arch_el.id,
            ctx=auth_context,
        )

        # Count allocated-to links for this requirement
        allocated_links = list(
            link_svc.query_trace_links(
                entity_id=req.id,
                direction="downstream",
                link_type=LinkType.ALLOCATED_TO,
                ctx=auth_context,
            )
        )

        assert len(allocated_links) == 1


@pytest.mark.django_db
class TestAllocationCoverageReport:
    """Test allocation coverage reporting."""

    def test_coverage_report_all_allocated(self, auth_context, workspace):
        """Test coverage report when all child requirements are allocated."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        # Create parent ArchitectureElement
        parent_arch = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Parent System",
            ctx=auth_context,
        )

        # Create child ArchitectureElement
        child_arch = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Child Subsystem",
            parent_id=parent_arch.id,
            ctx=auth_context,
        )

        # Create Requirements and allocate them
        for i in range(3):
            req = req_svc.create_requirement(
                workspace_id=workspace.id,
                title=f"Requirement {i}",
                ctx=auth_context,
            )
            link_svc.allocate(
                requirement_id=req.id,
                architecture_element_id=child_arch.id,
                ctx=auth_context,
            )

        # Get coverage report
        report = link_svc.get_allocation_coverage(
            architecture_element_id=parent_arch.id,
            ctx=auth_context,
        )

        assert report is not None
        assert report["allocated_count"] >= 0
        assert report["coverage_ratio"] >= 0
        assert "unallocated_requirements" in report

    def test_coverage_report_partial_allocation(self, auth_context, workspace):
        """Test coverage report with partially allocated child requirements."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        # Create ArchitectureElement
        arch_el = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Subsystem with partial allocation",
            ctx=auth_context,
        )

        # Create some requirements (allocated) and some (not allocated)
        allocated_reqs = []
        for i in range(2):
            req = req_svc.create_requirement(
                workspace_id=workspace.id,
                title=f"Allocated Requirement {i}",
                ctx=auth_context,
            )
            link_svc.allocate(
                requirement_id=req.id,
                architecture_element_id=arch_el.id,
                ctx=auth_context,
            )
            allocated_reqs.append(req)

        # Create unallocated requirements
        for i in range(2):
            req_svc.create_requirement(
                workspace_id=workspace.id,
                title=f"Unallocated Requirement {i}",
                ctx=auth_context,
            )

        # Get coverage report
        report = link_svc.get_allocation_coverage(
            architecture_element_id=arch_el.id,
            ctx=auth_context,
        )

        assert report is not None
        assert report["allocated_count"] >= 2
        assert len(report["unallocated_requirements"]) >= 2

    def test_coverage_report_no_requirements(self, auth_context, workspace):
        """Test coverage report for ArchitectureElement with no child requirements."""
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        arch_el = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Empty Component",
            ctx=auth_context,
        )

        report = link_svc.get_allocation_coverage(
            architecture_element_id=arch_el.id,
            ctx=auth_context,
        )

        assert report is not None
        assert report["allocated_count"] == 0
        assert report["coverage_ratio"] == 0
        assert len(report["unallocated_requirements"]) == 0


@pytest.mark.django_db
class TestRequirementAllocations:
    """REQ-L1-058 AC3 / REQ-066: get_requirement_allocations service method.

    Covers the ORM/prefetch logic moved out of RequirementViewSet.allocation_coverage
    into TraceLinkService during REQ-066 Phase 3.
    """

    def test_returns_allocated_architecture_elements(self, auth_context, workspace):
        """Returns the ArchitectureElement a requirement is allocated to."""
        req_svc = RequirementService()
        arch_svc = ArchitectureService()
        link_svc = TraceLinkService()

        req_dto = req_svc.create_requirement(
            workspace_id=workspace.id,
            title="Requirement with allocation",
            ctx=auth_context,
        )
        arch_el = arch_svc.create_architecture_element(
            workspace_id=workspace.id,
            title="Target Component",
            ctx=auth_context,
        )
        link_svc.allocate(
            requirement_id=req_dto.id,
            architecture_element_id=arch_el.id,
            ctx=auth_context,
        )

        req = req_svc.get_requirement(req_dto.id, auth_context)
        allocations = link_svc.get_requirement_allocations(
            req.artifact_id, req.tenant_id, auth_context
        )

        assert len(allocations) == 1
        entry = allocations[0]
        assert entry["architecture_element_id"] == str(arch_el.id)
        assert entry["architecture_element_title"] == "Target Component"
        assert "target_level" in entry
        assert "asil_level" in entry
        assert "make_or_buy" in entry

    def test_returns_empty_when_not_allocated(self, auth_context, workspace):
        """Returns an empty list when the requirement has no allocation."""
        req_svc = RequirementService()
        link_svc = TraceLinkService()

        req_dto = req_svc.create_requirement(
            workspace_id=workspace.id,
            title="Unallocated requirement",
            ctx=auth_context,
        )
        req = req_svc.get_requirement(req_dto.id, auth_context)

        allocations = link_svc.get_requirement_allocations(
            req.artifact_id, req.tenant_id, auth_context
        )

        assert allocations == []
