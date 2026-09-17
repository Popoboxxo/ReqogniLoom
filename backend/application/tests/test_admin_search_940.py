"""Admin search smoke test for the renamed Risk owner column (WS7 #940 review).

Migration ``0092_rename_risk_owner_to_owner_name`` renamed the free-text
``Risk.owner`` field to ``owner_name`` (same DB column). ``RiskAdmin.search_fields``
kept the old name, so any admin search raised ``FieldError`` — a failure
``manage.py check`` does not catch because it never exercises
``get_search_results``. This test drives the real search path.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from application.admin import RiskAdmin
from persistence.models import Artifact, Risk, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def test_risk_admin_search_uses_owner_name_column() -> None:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"adm-{suffix}", slug=f"adm-{suffix}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant_id=tenant.id, workspace=workspace, artifact_type="Risk"
        )
        risk = Risk.objects.create(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact=artifact,
            title="Admin search target",
            owner_name="Ada Lovelace",
        )

        model_admin = RiskAdmin(Risk, AdminSite())
        request = RequestFactory().get("/admin/application/risk/", {"q": "Ada"})

        # A stale ``owner`` in search_fields raises FieldError here.
        queryset, _ = model_admin.get_search_results(
            request, Risk.objects.all(), "Ada"
        )

        assert list(queryset) == [risk]
    finally:
        TenantContext.clear_tenant()
