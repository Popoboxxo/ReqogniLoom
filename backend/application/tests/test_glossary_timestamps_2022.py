"""Issue #2022 — glossary responses must carry the AuditableModel timestamps.

``GlossaryTermDTO.from_orm`` used to drop ``created_at``/``modified_at``, so
both transports silently omitted fields they had declared: the REST serializer
(``created_at`` / ``updated_at``) and the MCP generic tool group (which
projects the DTO's ``__dict__``).
"""
from __future__ import annotations

import pytest

from application.glossary_service import GlossaryService, GlossaryTermDTO
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace
from rest_api.serializers import GlossaryTermSerializer


@pytest.mark.django_db
def test_dto_from_orm_carries_timestamps():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        created = GlossaryService().create(
            ctx=ctx,
            workspace_id=workspace.id,
            term="Widget",
            definition="a thing",
        )
        dto = GlossaryService().get(ctx, created.id)

        assert isinstance(dto, GlossaryTermDTO)
        assert dto.created_at is not None
        assert dto.modified_at is not None


@pytest.mark.django_db
def test_rest_serializer_exposes_timestamps():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        dto = GlossaryService().create(
            ctx=ctx,
            workspace_id=workspace.id,
            term="Widget",
            definition="a thing",
        )

        data = GlossaryTermSerializer(dto).data
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
        assert "modified_at" not in data  # published wire key is updated_at


@pytest.mark.django_db
def test_mcp_projection_exposes_timestamps():
    from mcp_server.tools.generic import GenericCrudToolGroup

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        dto = GlossaryService().create(
            ctx=ctx,
            workspace_id=workspace.id,
            term="Widget",
            definition="a thing",
        )

        group = GenericCrudToolGroup(
            "glossary", GlossaryService, item_type="GlossaryTerm"
        )
        projected = group._to_dict(dto)

        assert projected["created_at"] == dto.created_at.isoformat()
        assert projected["modified_at"] == dto.modified_at.isoformat()
