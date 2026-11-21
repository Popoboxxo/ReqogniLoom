"""P2: every transfer-contract entity must export in every declared format."""
from __future__ import annotations

import json

import pytest

from application.generic_export_service import GenericArtifactExportService
from application.artifact_transfer_contract import TRANSFER_SPECS
from persistence.tests.factories import active_tenant, editor_ctx, make_requirement, make_workspace

FORMATS = ("json", "csv", "markdown", "pdf")


@pytest.mark.django_db
@pytest.mark.parametrize("entity_key", sorted(TRANSFER_SPECS))
def test_every_entity_exports_in_every_declared_format(entity_key: str) -> None:
    spec = TRANSFER_SPECS[entity_key]
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        for fmt in FORMATS:
            if fmt not in spec.formats:
                continue
            result = GenericArtifactExportService().export(
                ctx=ctx,
                workspace_id=workspace.id,
                entity_key=entity_key,
                format=fmt,
            )
            assert result.content
            assert result.media_type
            assert result.filename == f"export_{entity_key}.{fmt}"
            # Config entities legitimately have rows (the workspace itself and
            # provisioned link types), so only artifact entities must be empty.
            if spec.is_artifact:
                assert result.record_count == 0
            assert result.truncated is False


@pytest.mark.django_db
def test_requirement_json_export_contains_row_and_no_secret_columns() -> None:
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        make_requirement(workspace, title="Export fixture")
        result = GenericArtifactExportService().export(
            ctx=ctx, workspace_id=workspace.id, entity_key="requirement", format="json"
        )
        payload = json.loads(result.content)
        assert result.record_count == 1
        assert payload["metadata"]["entity"] == "requirement"
        assert any(row.get("title") == "Export fixture" for row in payload["data"])
        assert all(
            "password" not in key and "secret" not in key and "embedding" not in key
            for row in payload["data"]
            for key in row
        )


@pytest.mark.django_db
def test_csv_export_neutralises_formula_cells() -> None:
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        make_requirement(workspace, title="=cmd|'/c calc'!A1")
        result = GenericArtifactExportService().export(
            ctx=ctx, workspace_id=workspace.id, entity_key="requirement", format="csv"
        )
        assert "'=cmd" in result.content


@pytest.mark.django_db
def test_unknown_entity_and_format_are_rejected() -> None:
    from application.base import ValidationError

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        service = GenericArtifactExportService()
        with pytest.raises(ValidationError):
            service.export(ctx=ctx, workspace_id=workspace.id, entity_key="nope")
        with pytest.raises(ValidationError):
            service.export(
                ctx=ctx, workspace_id=workspace.id, entity_key="requirement", format="reqif"
            )


@pytest.mark.django_db
def test_row_cap_reports_truncation() -> None:
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        make_requirement(workspace, title="First")
        make_requirement(workspace, title="Second")
        result = GenericArtifactExportService().export(
            ctx=ctx,
            workspace_id=workspace.id,
            entity_key="requirement",
            format="json",
            max_rows=1,
        )
        assert result.record_count == 1
        assert result.truncated is True
