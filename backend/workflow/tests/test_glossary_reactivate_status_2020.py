"""Issue #2020 — ``glossary.reactivate`` must report the wire status.

GlossaryTerm is the one workflow-tracked type whose published ``status`` is
derived from the backing Artifact's soft-delete flag ("active"/"outdated")
instead of from ``WorkflowItemState.current_state``. Reactivating a term used
to report its preserved workflow state ("draft"), contradicting
``glossary.get``/``glossary.query`` ("active") for the very same term.
"""
from __future__ import annotations

import pytest

from persistence.tests.factories import active_tenant, editor_ctx, make_workspace
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow, outdate, reactivate


@pytest.mark.django_db
def test_glossary_reactivate_reports_active_and_keeps_workflow_state():
    from application.glossary_service import GlossaryService

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="GlossaryTerm",
            tenant_id=tenant.id,
        )
        dto = GlossaryService().create(
            ctx=ctx,
            workspace_id=workspace.id,
            term="Widget",
            definition="a thing",
        )

        outdate(
            item_id=dto.id,
            item_type="GlossaryTerm",
            workspace_id=workspace.id,
            ctx=ctx,
        )
        assert GlossaryService().get(ctx, dto.id).status == "outdated"

        result = reactivate(
            item_id=dto.id,
            item_type="GlossaryTerm",
            workspace_id=workspace.id,
            ctx=ctx,
        )

        # Wire status is aligned with the DTO, not with the workflow state.
        assert result.previous_state == "outdated"
        assert result.new_state == "active"
        assert GlossaryService().get(ctx, dto.id).status == "active"

        # The workflow axis and the definition are deliberately untouched.
        state = WorkflowItemState.objects.get(
            item_id=dto.id, item_type="GlossaryTerm"
        )
        assert state.current_state == "draft"
