"""
ARCH-L1-008 PresetConfigEngine — Django ORM models.

COMP-PC-001 PresetRegistry    (REQ-L2-PC-001, REQ-L2-PC-008)
COMP-PC-002 TerminologyProfileService (REQ-L2-PC-009, REQ-L2-PC-010)
COMP-PC-003 FeatureGateService (REQ-L2-PC-002, REQ-L2-PC-011)

leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-008, REQ-L2-PC-009, REQ-L2-PC-010,
         REQ-L2-PC-011
         REQ-L3-PC001-001, REQ-L3-PC002-003, REQ-L3-PC003-003

Design assumptions (documented per spec instruction):
-  The existing ``persistence.models.Workspace`` has a generic ``preset``
   JSONField (ADR-04, persistence/models.py line 184).  Rather than altering
   that model (which would require changing a foreign app — forbidden by the
   context_boundary constraint), this app defines ``WorkspacePresetConfig`` as
   a one-to-one companion to Workspace.  It stores the active preset tier and
   the terminology profile name as typed CharField choices, keeping the
   preset/terminology data strongly typed without DB schema changes in
   persistence/.

   Relationship: WorkspacePresetConfig.workspace_id == Workspace.id (FK).
   If no WorkspacePresetConfig row exists for a workspace the FeatureGateService
   defaults to TIER_MINIMAL / PROFILE_DEV_MODE (safe defaults, REQ-L2-PC-001).

-  IF-PC-EXT-OUT-001: Reads/writes go through Django ORM.

Migration: presets/migrations/0001_initial.py
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel

# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

PRESET_CHOICES = [
    ("minimal", "Minimal"),
    ("standard", "Standard"),
    ("extended", "Extended"),
]

TERMINOLOGY_CHOICES = [
    ("dev_mode", "Dev Mode"),
    ("se_mode", "SE Mode"),
]

DOWNGRADE_POLICY_CHOICES = [
    ("block", "Block"),
    ("warn", "Warn"),
    ("allow", "Allow"),
]


# ---------------------------------------------------------------------------
# WorkspacePresetConfig (COMP-PC-001 / COMP-PC-002 persistence)
# ---------------------------------------------------------------------------


class WorkspacePresetConfig(TenantScopedModel):
    """Persisted preset tier and terminology profile per workspace.

    One-to-one companion to ``persistence.Workspace``.  Created on demand
    by FeatureGateService.switch_preset() and
    FeatureGateService.switch_terminology_profile().

    Attributes:
        workspace_id: UUID FK to persistence.Workspace (OneToOne semantic enforced
            by unique_together).
        active_tier: Current preset tier ("minimal" | "standard" | "extended").
        terminology_profile: Active label profile ("dev_mode" | "se_mode").
        downgrade_policy: Controls behaviour on downgrade attempts
            ("block" | "warn" | "allow").

    REQ-L3-PC002-003: Profile persistence — different workspaces have
    independent active profiles, and the profile survives system restarts.
    REQ-L3-PC003-003: downgrade_policy stored here for configurable enforcement.
    """

    workspace = models.OneToOneField(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="preset_config",
    )
    active_tier = models.CharField(
        max_length=32,
        choices=PRESET_CHOICES,
        default="minimal",
    )
    terminology_profile = models.CharField(
        max_length=32,
        choices=TERMINOLOGY_CHOICES,
        default="dev_mode",
    )
    downgrade_policy = models.CharField(
        max_length=16,
        choices=DOWNGRADE_POLICY_CHOICES,
        default="block",
    )

    class Meta:
        db_table = "pc_workspace_preset_config"

    def __str__(self) -> str:
        return (
            f"WorkspacePresetConfig("
            f"workspace={self.workspace_id}, "
            f"tier={self.active_tier}, "
            f"profile={self.terminology_profile})"
        )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "WorkspacePresetConfig",
    "PRESET_CHOICES",
    "TERMINOLOGY_CHOICES",
    "DOWNGRADE_POLICY_CHOICES",
]
