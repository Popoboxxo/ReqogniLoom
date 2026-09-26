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

CR-10 (inheritance-link repair): a pre-REQ-178 workspace row that predates the
global-default model carries ``source_global_id=None``. Previously such a row
made this command ``continue`` (it exists) AND made
``create_workspace_default_workflow`` a no-op (its ``get_or_create`` discards
``defaults`` on the Existing branch) — so the row stayed unlinked forever and,
because ``_propagate`` selects on ``source_global_id``, received no global edit
ever again: a silent, permanent inheritance gap. This command now REPAIRS
exactly that case (``is_customized=False`` and ``source_global_id is None``) by
linking the row to the tenant global and re-syncing its graph, and reports the
repair. Rows with ``is_customized=True`` are individualized workspaces and are
never touched; the report names what was NOT repaired, per reason.

The re-sync overwrite is additionally fail-safe in two ways, because
``is_customized=False`` on a legacy row does NOT prove "mirrors the global" —
the flag was introduced *after* those rows existed, so it only means "never
set". The CR-09b stranding is therefore possible right here and is refused
before the ``.update(...)``:

* ``empty-global`` — the tenant global carries no states at all; linking would
  re-sync the row to an EMPTY graph.
* ``would-orphan-live-item`` — the row declares state names the tenant global
  does not, and a live ``WorkflowItemState`` in this workspace sits in one of
  them. Re-syncing would strand that item in a state its own definition no
  longer declares.

Usage::

    python manage.py provision_workflow_definitions
    python manage.py provision_workflow_definitions --workspace-id <uuid>

Safe to run repeatedly — every provisioning path uses ``get_or_create`` so
existing (including customised) definitions are never overwritten, and the
repair is a no-op once ``source_global_id`` is set (idempotent).
"""
from __future__ import annotations

import copy

from django.core.management.base import BaseCommand

from auth_tenancy.services.permission_definition import (
    PermissionDefinitionService,
)
from persistence.models import Workspace
from persistence.tenancy import TenantContext
from workflow.global_definition_store import GlobalWorkflowDefinitionStore
from workflow.models import WorkflowEngineDefinition, WorkflowItemState
from workflow.services import create_default_workflow

# (item_type, preset key). Kept in sync with the canonical
# application.workspace_provisioning.WORKFLOW_ENTITY_TYPES. This Layer 1 command
# keeps its own copy on purpose: it must not import upward from the Layer 2
# application package.
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
    ("Goal", "goal_default"),
    ("MainGoal", "main_goal_default"),
    ("Interview", "interview_default"),
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
        total_repaired = 0
        total_workspaces = 0
        # (reason, item_type, preset, workspace_id) — the audit trail of rows
        # this command deliberately did NOT touch. ``preset`` is always read
        # from the ROW (``existing.preset``), never from the loop variable: the
        # repair/skip lookup is keyed on ``(workspace_id, item_type)`` alone, so
        # with more than one row per pair the loop's ``preset_key`` could name a
        # preset the reported row does not actually carry.
        not_repaired: list[tuple[str, str, str, str]] = []
        for ws in workspaces:
            total_workspaces += 1
            # create_default_workflow runs on the tenant-scoped manager, so a
            # tenant context is required per workspace.
            TenantContext.set_tenant(ws.tenant_id)
            try:
                for item_type, preset_key in _ENTITY_PRESETS:
                    existing = WorkflowEngineDefinition.objects.filter(
                        workspace_id=str(ws.id), item_type=item_type
                    ).first()
                    if existing is None:
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
                        continue
                    # CR-10: the row exists. Repair only the legacy shape that
                    # is verifiably on-default-but-unlinked; everything else is
                    # left exactly as found and reported.
                    if existing.is_customized:
                        not_repaired.append(
                            ("customized", item_type, existing.preset, str(ws.id))
                        )
                        continue
                    if existing.source_global_id is not None:
                        # Already linked — nothing to repair, not worth reporting.
                        continue
                    # is_customized=False and source_global_id is None: the row
                    # claims to mirror a global it is not linked to, so it can
                    # never receive a propagation. Get-or-seed the tenant global
                    # and re-assert the on-default invariant in one write.
                    global_def = (
                        GlobalWorkflowDefinitionStore().get_or_seed_from_preset(
                            tenant_id=ws.tenant_id,
                            item_type=item_type,
                            preset=preset_key,
                        )
                    )
                    if not (global_def.workflow_json or {}).get("states"):
                        # Fail safe: linking would otherwise re-sync the row to an
                        # EMPTY graph and destroy live state names. Report instead.
                        not_repaired.append(
                            ("empty-global", item_type, existing.preset, str(ws.id))
                        )
                        continue
                    # B1 / CR-09b parity: the re-sync below overwrites
                    # ``workflow_json`` unconditionally. On a legacy row
                    # ``is_customized=False`` only means "the flag was never
                    # set" — the flag was introduced AFTER these rows existed —
                    # so it does NOT prove the row mirrors a global. A legacy row
                    # with an EDITED graph can hold state names the tenant global
                    # never declared, and live WorkflowItemState rows can sit in
                    # exactly those names. Re-syncing would silently strand them
                    # (a state their own definition no longer declares, with no
                    # transition out of it) and the row would then be linked as
                    # ``is_customized=False``, so every future global edit
                    # propagates into it too. Refuse, and report.
                    existing_states = set((existing.workflow_json or {}).get("states") or [])
                    global_states = set((global_def.workflow_json or {}).get("states") or [])
                    orphaned = existing_states - global_states
                    if orphaned and WorkflowItemState.objects.filter(
                        workspace_id=str(ws.id),
                        item_type=item_type,
                        current_state__in=orphaned,
                    ).exists():
                        not_repaired.append(
                            (
                                "would-orphan-live-item",
                                item_type,
                                existing.preset,
                                str(ws.id),
                            )
                        )
                        continue
                    updated = WorkflowEngineDefinition.objects.filter(
                        pk=existing.pk
                    ).update(
                        source_global_id=global_def.id,
                        workflow_json=copy.deepcopy(global_def.workflow_json),
                        is_customized=False,
                    )
                    if updated:
                        total_repaired += 1
                        self.stdout.write(
                            f"  ~ repaired {item_type} ({preset_key}) for "
                            f"workspace {ws.id}: linked source_global "
                            f"{global_def.id}, re-synced workflow_json"
                        )
                    else:
                        not_repaired.append(
                            ("vanished", item_type, existing.preset, str(ws.id))
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
                f"created {total_created} definition(s), "
                f"repaired {total_repaired} unlinked definition(s)."
            )
        )
        if not_repaired:
            # The audit requires the negative space to be explicit, not just a
            # count: name every row that was skipped and why.
            self.stdout.write(
                self.style.WARNING(
                    f"Not repaired ({len(not_repaired)} definition(s)) — "
                    "left untouched by design:"
                )
            )
            for reason, item_type, preset, ws_id in not_repaired[:50]:
                self.stdout.write(
                    f"    - [{reason}] {item_type} ({preset}) @ workspace {ws_id}"
                )
            if len(not_repaired) > 50:
                self.stdout.write(
                    f"    ... and {len(not_repaired) - 50} more "
                    "(raise this cap in the command to list them all)"
                )
        else:
            self.stdout.write("Not repaired: none.")
