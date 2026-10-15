"""ReqIF export keeps glossary reference tokens as stable IDs (#1266).

Requirement 6 of #1266: references leave the system as their stable
``[[glossary:<global_uuid>@<revision>]]`` token, never as the resolved term
text — a foreign tool must be able to round-trip the identity, and the meaning
must not be frozen into an export.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.reqif_export_service import ReqifExportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db

TOKEN = "[[glossary:11111111-1111-1111-1111-111111111111@2]]"


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def test_reference_token_is_exported_verbatim_not_resolved():
    tenant = Tenant.objects.create(
        name="Ref-Export", slug=f"ref-export-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Ref WS", preset={"name": "standard"}
        )
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=art,
            title="Uses a term",
            description=f"This requirement references {TOKEN}.",
        )
    finally:
        clear_request_tenant()

    result = ReqifExportService().export_reqif(
        workspace_id=workspace.id, ctx=_ctx(tenant.id)
    )

    assert TOKEN in result.content
