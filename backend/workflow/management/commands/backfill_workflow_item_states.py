"""REQ-165/REQ-166 — Backfill missing WorkflowItemState rows for entities.

Idempotent maintenance command that seeds a WorkflowItemState for every existing
Adr / Risk / Issue / ChangeRequest / TestCase row that lacks one, at the
definition's initial state. Complements ``provision_workflow_definitions`` —
run that first so a definition exists.

Datenmodell-Konsolidierung Task 12: this command used to seed at the row's
own ``status`` column value (mapped onto the definition's valid states;
unknown values fell back to the initial state) -- that column is dropped, so
there is no legacy value left to preserve. Every row this command still finds
missing a state (no ``WorkflowEngineDefinition`` existed for its workspace at
create/backfill time) now seeds directly at the definition's initial state
instead. This is the same explicit, reviewed data-loss tradeoff as every
other seam fallback in this migration — see the Task 12 report, Finding 2.

Usage::

    python manage.py backfill_workflow_item_states
    python manage.py backfill_workflow_item_states --workspace-id <uuid>

Safe to run repeatedly — ``StateLifecycleManager.ensure_item_state`` is
idempotent and race-safe (existing rows are returned unchanged).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from persistence.models import TestCase
from persistence.tenancy import TenantContext
from application.models import Adr, ChangeRequest, Issue, Risk
from workflow.definition_store import WorkflowDefinitionError
from workflow.lifecycle_manager import StateLifecycleManager


class Command(BaseCommand):
    help = "Backfill missing WorkflowItemState rows for entities (REQ-165/REQ-166)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--workspace-id",
            dest="workspace_id",
            default=None,
            help="Only backfill entities in this workspace UUID (default: all).",
        )

    def _seed(self, lifecycle, *, item_id, item_type, workspace_id, tenant_id) -> bool:
        """Ensure a WorkflowItemState exists for one row. Returns True if created."""
        TenantContext.set_tenant(tenant_id)
        try:
            existing = lifecycle.get_item_state(item_id, item_type, workspace_id)
            if existing is not None:
                return False
            try:
                dto = lifecycle._store.get_definition(workspace_id, item_type)
            except WorkflowDefinitionError:
                return False
            lifecycle.ensure_item_state(item_id, item_type, workspace_id, dto.initial_state)
            return True
        finally:
            TenantContext.clear_tenant()

    def handle(self, *args, **options) -> None:
        workspace_id = options.get("workspace_id")
        lifecycle = StateLifecycleManager()

        created = 0
        scanned = 0

        # Application models carry workspace_id + tenant_id directly.
        for model, item_type in (
            (Adr, "Adr"),
            (Risk, "Risk"),
            (Issue, "Issue"),
            (ChangeRequest, "ChangeRequest"),
        ):
            qs = model.objects.all()
            if workspace_id:
                qs = qs.filter(workspace_id=workspace_id)
            for row in qs:
                scanned += 1
                if self._seed(
                    lifecycle,
                    item_id=row.id,
                    item_type=item_type,
                    workspace_id=row.workspace_id,
                    tenant_id=row.tenant_id,
                ):
                    created += 1

        # TestCase is scoped via its backing artifact's workspace.
        tc_qs = TestCase.unscoped.select_related("artifact").all()
        if workspace_id:
            tc_qs = tc_qs.filter(artifact__workspace_id=workspace_id)
        for tc in tc_qs:
            scanned += 1
            if self._seed(
                lifecycle,
                item_id=tc.id,
                item_type="TestCase",
                workspace_id=tc.artifact.workspace_id,
                tenant_id=tc.tenant_id,
            ):
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Scanned {scanned} entity row(s), "
                f"created {created} WorkflowItemState(s)."
            )
        )
