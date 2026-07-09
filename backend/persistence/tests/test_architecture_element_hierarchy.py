"""Unit tests for ArchitectureElement.parent_id and get_level() — REQ-L1-041."""

import pytest
from persistence.models import ArchitectureElement, Artifact
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
