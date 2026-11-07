"""P1 Task 1.5: importers and decompose preserve their source order."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.db.models import F

from application.import_service import ImportService
from application.reqif_import_service import ReqifImportService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _workspace(slug: str):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
        from link_types.workspace_store import provision_workspace_link_types

        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )
    return tenant, workspace, ctx


def _root_artifact(workspace, name: str) -> Artifact:
    return Artifact.unscoped.create(
        tenant=workspace.tenant,
        workspace=workspace,
        artifact_type="Requirement",
        reqif_identifier=name,
    )


def test_reqif_import_keeps_document_order():
    _tenant, workspace, _ctx = _workspace("reqif-order")
    first = _root_artifact(workspace, "first")
    second = _root_artifact(workspace, "second")
    third = _root_artifact(workspace, "third")

    mapping = {"S1": first, "S2": second, "S3": third}
    specification = SimpleNamespace(
        children=[
            SimpleNamespace(spec_object="S3", children=[]),
            SimpleNamespace(spec_object="S1", children=[]),
            SimpleNamespace(spec_object="S2", children=[]),
        ]
    )

    ReqifImportService._apply_hierarchy([specification], mapping)

    roots = list(
        Artifact.unscoped.filter(
            workspace_id=workspace.id, parent_id__isnull=True
        ).order_by(F("sort_key").asc(nulls_last=True), "created_at", "id")
    )
    assert [row.id for row in roots] == [third.id, first.id, second.id]


def test_csv_import_keeps_row_order():
    _tenant, workspace, ctx = _workspace("csv-order")
    csv_text = (
        "title,description\n"
        "Alpha,first\n"
        "Beta,second\n"
        "Gamma,third\n"
    )

    result = ImportService().import_csv(csv_text, "Requirement", workspace.id, ctx)
    assert result.success is True
    assert result.imported_count == 3

    rows = (
        RequirementService()
        .list_requirements(workspace_id=workspace.id, ctx=ctx)
        .order_by(F("artifact__sort_key").asc(nulls_last=True), "created_at", "id")
    )
    assert [row.title for row in rows] == ["Alpha", "Beta", "Gamma"]


def test_decompose_keeps_llm_order():
    _tenant, workspace, ctx = _workspace("decompose-order")
    parent = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Parent", ctx=ctx
    )

    RequirementService().decompose(
        requirement_id=parent.id,
        ctx=ctx,
        children=[
            {"title": "Third", "description": ""},
            {"title": "First", "description": ""},
            {"title": "Second", "description": ""},
        ],
    )

    children = list(
        Artifact.unscoped.filter(parent_id=parent.artifact_id).order_by(
            F("sort_key").asc(nulls_last=True), "created_at", "id"
        )
    )
    from persistence.models import Requirement

    titles = [
        Requirement.unscoped.get(artifact_id=row.id).title for row in children
    ]
    assert titles == ["Third", "First", "Second"]
