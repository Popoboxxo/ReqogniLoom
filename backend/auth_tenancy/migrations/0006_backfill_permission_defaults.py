"""REQ-181/REQ-182/REQ-183 — Backfill Global + Workspace permission definitions.

Unlike workflows, there was NO prior per-workspace permissions *definition* blob
(permissions were enforced by per-user UserRole / ItemPermission rows plus a
role->capability matrix that lived in code). This migration introduces the new
governance layer for existing data:

1. One ``GlobalPermissionDefinition`` per tenant, seeded with the baseline
   role->capability matrix (``_DEFAULT_MATRIX``). This mirrors the current
   coded RBAC defaults; the exact capability keys are refined downstream.

2. One ``WorkspacePermissionDefinition`` per existing workspace, linked to its
   tenant global, ``permission_json`` copied from the global, and
   ``is_customized=False``.

All existing workspaces start "on-default": the definition concept did not
exist before, so nothing has diverged yet (contrast with the workflow backfill,
where pre-existing per-workspace definitions could already differ).

ENFORCEMENT (REQ-186/187): the new global is created with its model default
``enforcement_mode='shadow'`` (not set explicitly here). On migrate NO access
decision changes — the legacy UserRole/ItemPermission check keeps deciding while
the new model is only evaluated in the shadow phase. Flipping a tenant to
``authoritative`` is a deliberate, evidence-gated data operation performed later
(senior-developer), NOT part of this migration. This backfill still does not
mutate UserRole / ItemPermission rows, so user-visible editing capability is
preserved (REQ-182, narrowed: regression protection = editing capability, NOT
survival of the legacy enforcement path).

Reverse deletes all rows created here; no pre-existing data is affected.
"""
from __future__ import annotations

import copy

from django.db import migrations

# Baseline role->capability matrix (REQ-181), reconciled with the REAL hardcoded
# RBAC matrix so day-1 shadow decisions match legacy EXACTLY (REQ-186/187 safe
# rollout, api-specialist recommendation #3).
#
# This is a frozen, literal 1:1 lift of ``_RBAC_MATRIX`` in
# ``auth_tenancy/services/authorization.py`` (the ``Operation`` enum,
# ADR-L3-AT002-01) expressed as a closed 4-role x 6-capability boolean matrix.
# The six capability keys are the canonical set fixed by the API contract
# (docs/api/workflow-permissions-global-default.openapi.yaml, ``CapabilityKey``):
# read, write, workflow_transition, workflow_approval, workspace_config,
# assign_role.
#
# Legacy _RBAC_MATRIX (source of truth at migration authoring time):
#   admin    -> every Operation
#   editor   -> {read, write, workflow_transition}
#   viewer   -> {read}
#   approver -> {read, write, workflow_transition, workflow_approval}
#
# A migration is a point-in-time snapshot and must stay self-contained, so the
# matrix is inlined as a literal rather than imported from the service layer
# (importing live app code into a historical migration is fragile). If the coded
# RBAC matrix ever changes, this backfill is NOT retro-edited — the divergence
# would instead surface as shadow mismatches, which is the intended safety net.
_DEFAULT_MATRIX = {
    "admin": {
        "read": True,
        "write": True,
        "workflow_transition": True,
        "workflow_approval": True,
        "workspace_config": True,
        "assign_role": True,
    },
    "editor": {
        "read": True,
        "write": True,
        "workflow_transition": True,
        "workflow_approval": False,
        "workspace_config": False,
        "assign_role": False,
    },
    "approver": {
        "read": True,
        "write": True,
        "workflow_transition": True,
        "workflow_approval": True,
        "workspace_config": False,
        "assign_role": False,
    },
    "viewer": {
        "read": True,
        "write": False,
        "workflow_transition": False,
        "workflow_approval": False,
        "workspace_config": False,
        "assign_role": False,
    },
}


def backfill_permission_defaults(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    GlobalPermissionDefinition = apps.get_model(
        "auth_tenancy", "GlobalPermissionDefinition"
    )
    WorkspacePermissionDefinition = apps.get_model(
        "auth_tenancy", "WorkspacePermissionDefinition"
    )

    # Cache one global per tenant (created on first workspace encountered).
    globals_by_tenant: dict = {}

    for ws in Workspace.objects.all():
        global_def = globals_by_tenant.get(ws.tenant_id)
        if global_def is None:
            global_def, _ = GlobalPermissionDefinition.objects.get_or_create(
                tenant_id=ws.tenant_id,
                defaults={"permission_json": copy.deepcopy(_DEFAULT_MATRIX)},
            )
            globals_by_tenant[ws.tenant_id] = global_def

        WorkspacePermissionDefinition.objects.get_or_create(
            tenant_id=ws.tenant_id,
            workspace_id=ws.id,
            defaults={
                "permission_json": copy.deepcopy(global_def.permission_json),
                "source_global_id": global_def.id,
                "is_customized": False,
            },
        )


def remove_permission_defaults(apps, schema_editor):
    GlobalPermissionDefinition = apps.get_model(
        "auth_tenancy", "GlobalPermissionDefinition"
    )
    WorkspacePermissionDefinition = apps.get_model(
        "auth_tenancy", "WorkspacePermissionDefinition"
    )

    WorkspacePermissionDefinition.objects.all().delete()
    GlobalPermissionDefinition.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0005_global_default_model"),
        # Reads Workspace at its latest schema.
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.RunPython(
            backfill_permission_defaults, remove_permission_defaults
        ),
    ]
