"""Tests for the Phase 4 PromptTemplate model shape (REQ-L2-PT-001).

Covers the new named, versioned, workspace-overridable model: multiple
templates per tenant (open-ended ``name``), tenant-global vs. per-workspace
override scoping (``workspace_id``), and the "at most one active row per
(tenant, workspace_id, name)" invariant, enforced at the application level in
``PromptTemplate.save()`` (see backend/persistence/models.py docstring for the
DB-level-vs-application-level decision).

Tests activate the tenant context via ``active_tenant`` (persistence/tests/
conftest.py) before touching ``PromptTemplate.objects`` because it is a
``TenantScopedModel`` whose default manager requires an active
``TenantContext`` (ARCH-L1-011), same convention as
``persistence/tests/test_entity_schema.py``.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from persistence.tests.conftest import active_tenant


@pytest.mark.django_db
def test_create_tenant_global_template(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        tpl = PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="Derive from {need_title}",
            version=1, is_active=True, workspace_id=None,
        )
    assert tpl.workspace_id is None
    assert tpl.is_active is True


@pytest.mark.django_db
def test_only_one_active_version_per_name_and_scope(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v1", version=1, is_active=True
        )
        # Application-level enforcement (see PromptTemplate.save()): a second
        # active=True row for the same (tenant, workspace_id=None, name) scope
        # raises IntegrityError, mirroring the codebase's existing idiom of
        # raising/catching IntegrityError around uniqueness violations (e.g.
        # CustomFieldDefinitionService).
        with pytest.raises(IntegrityError):
            PromptTemplate.objects.create(
                tenant=tenant, name="need_to_sysreq", content="v2", version=2, is_active=True
            )


@pytest.mark.django_db
def test_inactive_version_can_coexist_with_active_version(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v1", version=1, is_active=True
        )
        # A second, inactive version in the same scope is allowed - only
        # is_active=True rows are constrained to at most one per scope.
        inactive = PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v2 draft", version=2, is_active=False
        )
        assert inactive.pk is not None
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=None
        ).count() == 2


@pytest.mark.django_db
def test_workspace_override_and_tenant_global_coexist(tenant, workspace):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="global v1", version=1,
            is_active=True, workspace_id=None,
        )
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="workspace override v1", version=1,
            is_active=True, workspace_id=workspace.id,
        )
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=None, is_active=True
        ).count() == 1
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=workspace.id, is_active=True
        ).count() == 1
