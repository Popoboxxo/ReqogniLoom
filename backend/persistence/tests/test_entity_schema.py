"""
COMP-PL-001 EntitySchemaManager — schema + audit + referential-integrity tests.

Covers REQ-L2-PL-004 (13 entities), REQ-L2-PL-005 (audit fields),
REQ-L2-PL-009 (on_delete rules).
"""
from __future__ import annotations

import uuid
import time

import pytest
from django.db.models import ProtectedError

from baseline.models import BaselineSnapshot
from persistence import models as m
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)


EXPECTED_ENTITIES = [
    m.Tenant,
    m.User,
    m.Role,
    m.Workspace,
    m.Artifact,
    m.Requirement,
    m.ArchitectureElement,
    m.TraceLink,
    m.TestCase,
    BaselineSnapshot,
    m.WorkflowDefinition,
    m.WorkflowState,
    m.AuditLogEntry,
]


def test_all_13_entities_exist():
    """REQ-L2-PL-004: exactly the 13 domain entities are defined."""
    assert len(EXPECTED_ENTITIES) == 13
    for model in EXPECTED_ENTITIES:
        assert hasattr(model, "_meta")
        if issubclass(model, m.TenantScopedModel):
            field = model._meta.get_field("tenant")
            assert field.related_model == m.Tenant
            assert not field.null


def test_uuid_primary_key(tenant_a, workspace_a):
    """REQ-L3-PL001-002: tenant-scoped entities use a UUID primary key."""
    with active_tenant(tenant_a):
        artifact = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )
    assert isinstance(artifact.id, uuid.UUID)


def test_audit_fields_on_create(tenant_a, workspace_a):
    """REQ-L2-PL-005: create sets created_at and version == 1."""
    with active_tenant(tenant_a):
        artifact = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )
    assert artifact.created_at is not None
    assert artifact.version == 1


def test_audit_modified_at_updates(tenant_a, workspace_a):
    """REQ-L2-PL-005: update refreshes modified_at, created_at stays, version increments."""
    with active_tenant(tenant_a):
        artifact = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )
        created_at = artifact.created_at
        old_modified_at = artifact.modified_at
        old_version = artifact.version
        
        time.sleep(0.01) # Ensure modified_at has a chance to change
        
        artifact.artifact_type = "y"
        # The app should ideally use F('version') + 1 but for the sake of triggering update
        # if the framework doesn't do it automatically, the test will correctly fail here
        artifact.save()
        artifact.refresh_from_db()
        
    assert artifact.created_at == created_at
    assert artifact.modified_at > old_modified_at
    assert artifact.version == old_version + 1


def test_set_null_on_user_deletion_for_audit_fields(tenant_a, workspace_a):
    """REQ-L2-PL-009: deleting a User sets audit fields to NULL."""
    user = m.User.objects.create(username="testuser", email="test@example.com")
    with active_tenant(tenant_a):
        artifact = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x", created_by=user
        )
        assert artifact.created_by == user
        
    user.delete()
    
    with active_tenant(tenant_a):
        artifact.refresh_from_db()
        assert artifact.created_by is None


def test_protect_blocks_tenant_deletion(tenant_a, workspace_a):
    """REQ-L2-PL-009: deleting a tenant that still owns rows is blocked (PROTECT)."""
    with active_tenant(tenant_a):
        m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )
    with pytest.raises(ProtectedError):
        tenant_a.delete()


def test_cascade_deletes_children_and_links(tenant_a, workspace_a):
    """REQ-L2-PL-009: deleting a parent artifact cascades to children + links."""
    with active_tenant(tenant_a):
        parent = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="parent"
        )
        child = m.Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="child", parent=parent
        )
        m.TraceLink.objects.create(
            tenant=tenant_a, source=parent, target=child, link_type="contains"
        )
        parent.delete()
        assert m.Artifact.objects.filter(pk=child.pk).count() == 0
        assert m.TraceLink.objects.count() == 0
