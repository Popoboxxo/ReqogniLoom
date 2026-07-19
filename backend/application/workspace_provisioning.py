"""Shared workspace default-provisioning (REQ-165/REQ-166/REQ-181/REQ-188).

Single source of truth for the workflow- and permission-default seeding that a
newly provisioned workspace needs before it is usable. Both
``WorkspaceService.create_workspace`` / ``clone_workspace`` (the API/MCP write
path) and the first-start self-init receiver (``application.self_init``, REQ-188)
call :func:`provision_workspace_defaults`, so the demo/base workspace created at
bootstrap ends up with exactly the same workflow and permission defaults as any
workspace created later through the API.

Layering: this module lives in ``application`` (Layer 2) precisely because it
depends on ``workflow`` (Layer 1, ``create_default_workflow``) and
``auth_tenancy`` (Layer 0, ``PermissionDefinitionService``); putting the seeding
in either lower layer would invert the dependency direction.
"""
from __future__ import annotations

import logging
from uuid import UUID

from auth_tenancy.services.permission_definition import (
    PermissionDefinitionService,
)
from persistence.tenancy import TenantContext
from workflow.global_definition_store import GlobalWorkflowDefinitionStore
from workflow.services import create_default_workflow

logger = logging.getLogger(__name__)

# REQ-178: the three rigor presets the "Global Workflow Defaults" tab
# (System Settings) lets an admin browse/edit for ANY entity type, independent
# of which fixed preset key (e.g. "need_default") that entity type's own
# workspace-level workflow actually uses.
_GLOBAL_TAB_PRESETS: tuple[str, ...] = ("minimal", "standard", "extended")

# REQ-165/REQ-166/REQ-171/REQ-173: entity types that receive a fixed-preset
# default workflow on workspace provisioning. ``Requirement`` is provisioned
# separately with the workspace's tier-dependent preset (minimal/standard/
# extended); the types below always use their dedicated per-entity preset key.
# ``ChangeRequest`` reuses the existing ``ccb_approval`` preset.
#
# Canonical list — ``application.workspace_service`` imports it from here. The
# ``workflow.provision_workflow_definitions`` management command keeps its own
# copy on purpose: as a Layer 1 command it must not import upward from Layer 2.
WORKFLOW_ENTITY_TYPES: tuple[tuple[str, str], ...] = (
    ("StakeholderNeed", "need_default"),
    ("Adr", "adr_default"),
    ("Risk", "risk_default"),
    ("Issue", "issue_default"),
    ("TestCase", "testcase_default"),
    ("ChangeRequest", "ccb_approval"),
    ("ArchitectureElement", "architecture_default"),
    ("Icd", "icd_default"),
    ("Diagram", "diagram_default"),
    ("GlossaryTerm", "glossary_term_default"),
)


def provision_workspace_defaults(
    *,
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    requirement_preset: str,
) -> None:
    """Seed the default workflow + permission definitions for a workspace.

    Idempotent — every underlying provisioning call uses ``get_or_create``, so a
    repeat run never overwrites an existing (possibly customised) definition.

    Args:
        workspace_id: Target workspace UUID.
        tenant_id: Owning tenant UUID. Passed explicitly because
            ``create_default_workflow`` runs ``get_or_create`` on the plain
            QuerySet, bypassing the tenant manager's auto-inject on create.
        requirement_preset: Tier for the ``Requirement`` workflow — one of
            ``minimal`` / ``standard`` / ``extended``. The per-entity workflows
            use their own fixed presets regardless of this tier.
    """
    # Requirement workflow (tier-dependent). Without it a requirement's status
    # stays stuck at "draft" because no WorkflowEngineDefinition exists to
    # initialise a WorkflowItemState against.
    create_default_workflow(
        workspace_id=workspace_id,
        preset=requirement_preset,
        item_type="Requirement",
        tenant_id=tenant_id,
    )

    # Fixed-preset per-entity workflows (ADR, Risk, Issue, TestCase, ...).
    for item_type, preset_key in WORKFLOW_ENTITY_TYPES:
        create_default_workflow(
            workspace_id=workspace_id,
            preset=preset_key,
            item_type=item_type,
            tenant_id=tenant_id,
        )

    # REQ-178 bugfix: pre-seed ALL THREE rigor presets (minimal/standard/
    # extended) as GlobalWorkflowDefinition rows for every entity type the
    # "Global Workflow Defaults" tab can display — not just whichever preset
    # this workspace's own tier happens to be. Placed here (rather than only in
    # self-init) so the guarantee applies uniformly to every workspace creation
    # path — self-init AND the WorkspaceService API/MCP write path this module's
    # docstring already promises parity for. Without this, a fresh deployment
    # only had "extended" global rows (self-init's base workspace tier), and an
    # admin opening the tab — which defaults to "standard" — saw an empty
    # canvas even though workflow inheritance itself worked correctly.
    global_store = GlobalWorkflowDefinitionStore()
    global_tab_item_types = tuple(
        dict.fromkeys(
            [item_type for item_type, _preset_key in WORKFLOW_ENTITY_TYPES]
            + ["Requirement"]
        )
    )
    for item_type in global_tab_item_types:
        for preset in _GLOBAL_TAB_PRESETS:
            global_store.get_or_seed_from_preset(tenant_id, item_type, preset)

    # REQ-181/182: link the workspace to the tenant-wide permission global with
    # is_customized=False ("on-default"). Does not touch UserRole/ItemPermission
    # rows, so real access control is unchanged (shadow phase).
    PermissionDefinitionService().provision_workspace(
        tenant_id=tenant_id, workspace_id=workspace_id
    )


def provision_workspace_defaults_scoped(
    *,
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    requirement_preset: str,
) -> None:
    """:func:`provision_workspace_defaults` wrapped in an explicit tenant scope.

    ``create_default_workflow`` reads/writes through the tenant-scoped manager,
    so a ``TenantContext`` must be active. Callers already inside a request or
    service tenant scope (e.g. ``WorkspaceService``) should call
    :func:`provision_workspace_defaults` directly; bootstrap/self-init callers,
    which run without a request context, use this variant.
    """
    TenantContext.set_tenant(tenant_id)
    try:
        provision_workspace_defaults(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            requirement_preset=requirement_preset,
        )
    finally:
        TenantContext.clear_tenant()


__all__ = [
    "WORKFLOW_ENTITY_TYPES",
    "provision_workspace_defaults",
    "provision_workspace_defaults_scoped",
]
