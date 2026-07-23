"""Unit tests for ArchitectureElement.parent_id and get_level() — REQ-L1-041."""

import pytest
from persistence.models import ArchitectureElement, ArchitectureRole, Artifact
from persistence.tenancy import TenantContext


@pytest.mark.django_db(transaction=True)
class TestArchitectureElementGetLevel:
    """REQ-L1-041: parent_id FK and get_level() derivation."""

    def test_root_element_get_level_returns_0(self, workspace_a, tenant_a):
        """Root element (parent_id=None) returns level=0."""
        TenantContext.set_tenant(tenant_a.id)
        art1 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        el = ArchitectureElement.objects.create(artifact=art1, title="Root")
        assert el.get_level() == 0

    def test_child_element_get_level_returns_1(self, workspace_a, tenant_a):
        """Child element (direct child of root) returns level=1."""
        TenantContext.set_tenant(tenant_a.id)
        art1 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        root = ArchitectureElement.objects.create(artifact=art1, title="Root")
        
        art2 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        child = ArchitectureElement.objects.create(artifact=art2, title="Child", parent=root)
        assert child.get_level() == 1

    def test_nested_child_element_get_level_returns_2(self, workspace_a, tenant_a):
        """Nested child (grandchild) returns level=2."""
        TenantContext.set_tenant(tenant_a.id)
        art1 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        root = ArchitectureElement.objects.create(artifact=art1, title="Root")
        
        art2 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        child = ArchitectureElement.objects.create(artifact=art2, title="Child", parent=root)
        
        art3 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        grandchild = ArchitectureElement.objects.create(artifact=art3, title="Grandchild", parent=child)
        assert grandchild.get_level() == 2

    def test_three_level_hierarchy_returns_3(self, workspace_a, tenant_a):
        """Three-level hierarchy returns level=3 for deepest."""
        TenantContext.set_tenant(tenant_a.id)
        art1 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        root = ArchitectureElement.objects.create(artifact=art1, title="Root")
        
        art2 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        child = ArchitectureElement.objects.create(artifact=art2, title="Child", parent=root)
        
        art3 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        grandchild = ArchitectureElement.objects.create(artifact=art3, title="Grandchild", parent=child)
        
        art4 = Artifact.objects.create(workspace=workspace_a, artifact_type="element")
        great_grandchild = ArchitectureElement.objects.create(artifact=art4, title="GreatGrandchild", parent=grandchild)
        assert great_grandchild.get_level() == 3


class TestArchitectureElementModel:
    """Test ArchitectureElement model structure (REQ-L1-041)."""

    def test_parent_field_exists(self):
        """ArchitectureElement model has 'parent' ForeignKey field."""
        assert hasattr(ArchitectureElement, "parent")
        field = ArchitectureElement._meta.get_field("parent")
        assert field.null is True
        assert field.blank is True
        # Self-referencing FK
        assert field.related_model == ArchitectureElement

    def test_get_level_method_exists(self):
        """ArchitectureElement has get_level() method."""
        assert hasattr(ArchitectureElement, "get_level")
        assert callable(getattr(ArchitectureElement, "get_level"))


# ---------------------------------------------------------------------------
# Regression (Phase 0 final review, Fund 1 #2): get_role() must exclude
# children soft-deleted via workflow.services.outdate() — ArchitectureElement
# has no status mirror, so outdate() writes only WorkflowItemState, never the
# dead `lifecycle_status` column.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestArchitectureElementGetRoleExcludesOutdatedChildren:
    def test_parent_collapses_to_component_when_only_child_is_outdated(
        self, workspace_a, tenant_a
    ):
        """A parent whose only child was outdate()'d must report role
        'component' (leaf), not 'subsystem'."""
        import uuid

        from auth_tenancy.context import AuthContext
        from workflow.services import (
            create_default_workflow,
            initialize_workflow_states,
            outdate,
        )

        TenantContext.set_tenant(tenant_a.id)
        try:
            create_default_workflow(
                workspace_id=workspace_a.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=tenant_a.id,
            )

            # Three-level hierarchy: get_role() returns 'system' unconditionally
            # for parent_id IS NULL — the children-exclusion logic under test
            # only kicks in for a non-root element (subsystem <-> component).
            art_root = Artifact.objects.create(
                workspace=workspace_a, artifact_type="element"
            )
            root = ArchitectureElement.objects.create(artifact=art_root, title="Root")
            art_parent = Artifact.objects.create(
                workspace=workspace_a, artifact_type="element"
            )
            parent = ArchitectureElement.objects.create(
                artifact=art_parent, title="Parent", parent=root
            )
            art_child = Artifact.objects.create(
                workspace=workspace_a, artifact_type="element"
            )
            child = ArchitectureElement.objects.create(
                artifact=art_child, title="Child", parent=parent
            )

            ctx = AuthContext(
                user_id=uuid.uuid4(),
                tenant_id=tenant_a.id,
                active_roles=("editor",),
                auth_method="test",
                api_key_id=None,
                tenant_name=tenant_a.name,
            )
            initialize_workflow_states(
                item_ids=[child.id],
                item_type="ArchitectureElement",
                workspace_id=workspace_a.id,
                ctx=ctx,
            )

            # Before outdate(): parent has an active child -> subsystem.
            assert parent.get_role() == ArchitectureRole.SUBSYSTEM

            outdate(
                item_id=child.id,
                item_type="ArchitectureElement",
                workspace_id=workspace_a.id,
                ctx=ctx,
                reason="test soft-delete",
            )

            # get_role() must re-query — the in-memory `parent` instance has no
            # cached children count, so a fresh call reflects the outdate().
            assert parent.get_role() == ArchitectureRole.COMPONENT
        finally:
            TenantContext.clear_tenant()
