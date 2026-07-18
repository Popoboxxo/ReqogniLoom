"""REQ-165/REQ-166/REQ-178 — Provision missing per-entity WorkflowEngineDefinitions.

Idempotent maintenance command mirroring the provisioning that
``WorkspaceService.create_workspace`` performs: for every Workspace (optionally a
single one via ``--workspace-id``) it creates the fixed per-entity preset default
workflow for StakeholderNeed, Adr, Risk, Issue, TestCase and ChangeRequest when
one does not already exist. ``Requirement`` is skipped (already provisioned with
the tier-dependent preset at workspace creation).

REQ-178: ``create_default_workflow`` no longer copies ``PRESET_SCHEMAS`` straight
into the workspace row — it get-or-seeds the tenant-wide per-preset
``GlobalWorkflowDefinition`` and links the workspace row to it via
``source_global`` with ``is_customized=False``, so this command now also
backfills global defaults and inheritance links for any legacy workspace that
predates the global-default model.

REQ-181/182: the command additionally provisions the permission default
(``WorkspacePermissionDefinition`` linked to the tenant
``GlobalPermissionDefinition``) for each workspace, symmetric to workspace
creation. This never touches UserRole/ItemPermission rows.

Usage::

    python manage.py provision_workflow_definitions
    python manage.py provision_workflow_definitions --workspace-id <uuid>

Safe to run repeatedly — every provisioning path uses ``get_or_create`` so
existing (including customised) definitions are never overwritten.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from auth_tenancy.services.permission_definition import (
    PermissionDefinitionService,
)
from persistence.models import Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowEngineDefinition
from workflow.services import create_default_workflow

# (item_type, preset key). Kept in sync with
# application.workspace_service._WORKFLOW_ENTITY_TYPES.
_ENTITY_PRESETS = (
    ("StakeholderNeed", "need_default"),
    ("Adr", "adr_default"),
    ("Risk", "risk_default"),
    ("Issue", "issue_default"),
    ("TestCase", "testcase_default"),
    ("ChangeRequest", "ccb_approval"),
    ("ArchitectureElement", "architecture_default"),
    # REQ-173: Icd, Diagram, GlossaryTerm lifecycle. Diagram.workspace_id is
    # nullable (migration 0005) — pre-existing rows are backfilled separately,
    # so DiagramViewSet only exposes workflow transitions once a workspace has
    # been assigned (see application.workspace_service._WORKFLOW_ENTITY_TYPES).
    ("Icd", "icd_default"),
    ("Diagram", "diagram_default"),
    ("GlossaryTerm", "glossary_term_default"),
)


class Command(BaseCommand):
    help = "Provision missing per-entity WorkflowEngineDefinitions (REQ-165/REQ-166)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--workspace-id",
            dest="workspace_id",
            default=None,
            help="Only provision the workspace with this UUID (default: all).",
        )

    def handle(self, *args, **options) -> None:
        workspace_id = options.get("workspace_id")

        # ``unscoped`` iterates across every tenant without a request context.
        workspaces = Workspace.unscoped.all()
        if workspace_id:
            workspaces = workspaces.filter(id=workspace_id)

        total_created = 0
        total_workspaces = 0
        for ws in workspaces:
            total_workspaces += 1
            # create_default_workflow runs on the tenant-scoped manager, so a
            # tenant context is required per workspace.
            TenantContext.set_tenant(ws.tenant_id)
            try:
                for item_type, preset_key in _ENTITY_PRESETS:
                    exists = WorkflowEngineDefinition.objects.filter(
                        workspace_id=str(ws.id), item_type=item_type
                    ).exists()
                    if exists:
                        continue
                    create_default_workflow(
                        workspace_id=ws.id,
                        preset=preset_key,
                        item_type=item_type,
                        tenant_id=ws.tenant_id,
                    )
                    total_created += 1
                    self.stdout.write(
                        f"  + {item_type} ({preset_key}) for workspace {ws.id}"
                    )
                # REQ-181/182: ensure the permission default exists (idempotent).
                PermissionDefinitionService().provision_workspace(
                    tenant_id=ws.tenant_id, workspace_id=ws.id
                )
            finally:
                TenantContext.clear_tenant()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Scanned {total_workspaces} workspace(s), "
                f"created {total_created} definition(s)."
            )
        )
