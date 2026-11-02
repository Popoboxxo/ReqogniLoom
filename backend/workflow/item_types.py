"""Canonical registry of workflow-tracked item types (Plan F F2-T2).

Before this module the "which item types does the workflow engine track?"
knowledge existed in five hand-maintained copies (``workflow.state_reader``,
``workflow.services``, ``application.workspace_provisioning``, the
``provision_workflow_definitions`` management command and
``workflow/migrations/0004``). Adding a new artifact type — ``Document`` in
Plan F — meant remembering every one of them (R-F2-1).

The runtime copies now derive from :data:`WORKFLOW_ITEM_TYPES` here, and
``workflow/tests/test_item_type_registries_consistent.py`` pins the equality.
The historical migrations stay frozen (data migrations must not change once
released); their union is asserted against this registry instead.

``Requirement`` and ``WorkItem`` are deliberately **not** in the tuple: their
preset is the workspace's rigor tier (``minimal``/``standard``/``extended``),
resolved at provisioning time, not a fixed per-entity key. They are
nevertheless known workflow item types — see
:data:`KNOWN_WORKFLOW_ITEM_TYPES` and :data:`TIER_DRIVEN_ITEM_TYPES`.
"""
from __future__ import annotations

#: (item_type, fixed preset key) for every workflow-tracked type provisioned
#: with its own dedicated preset. Ordered like the provisioning loops so a
#: failure trace still reads naturally.
WORKFLOW_ITEM_TYPES: tuple[tuple[str, str], ...] = (
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
    ("Goal", "goal_default"),
    ("MainGoal", "main_goal_default"),
    ("Interview", "interview_default"),
    # Plan F F2-T2 / ADR-026: Document lifecycle.
    ("Document", "document_default"),
)

#: ``item_type -> preset key`` lookup derived from :data:`WORKFLOW_ITEM_TYPES`.
WORKFLOW_ITEM_TYPE_PRESETS: dict[str, str] = dict(WORKFLOW_ITEM_TYPES)

#: Item types whose lifecycle state is mirrored into a denormalised ``status``
#: column (Datenmodell-Konsolidierung Phase 1 / Task 12). Used by
#: :data:`workflow.state_reader.STATUS_TRACKED_ITEM_TYPES`; must stay exactly
#: the Task-12 column-drop set, so it is written out explicitly rather than
#: derived by subtraction.
STATUS_MIRROR_ITEM_TYPES: frozenset[str] = frozenset(
    {
        "StakeholderNeed",
        "TestCase",
        "Interview",
        "Adr",
        "Risk",
        "Issue",
        "ChangeRequest",
        "Goal",
        "MainGoal",
    }
)

#: Workflow-tracked types without a ``status`` column (state lives only in
#: ``WorkflowItemState``).
COLUMNLESS_ITEM_TYPES: frozenset[str] = frozenset(WORKFLOW_ITEM_TYPE_PRESETS) - (
    STATUS_MIRROR_ITEM_TYPES
)

#: Item types whose workflow preset depends on the workspace's rigor tier
#: instead of a dedicated per-entity preset key. ``Requirement`` maps 1:1 to
#: the tier (``minimal``/``standard``/``extended``); ``WorkItem`` prefixes it
#: (``work_item_<tier>``, Plan F F3-T2). Kept out of
#: :data:`WORKFLOW_ITEM_TYPES` because the fixed-preset provisioning loops must
#: not seed them with a single dedicated key.
TIER_DRIVEN_ITEM_TYPES: tuple[str, ...] = ("Requirement", "WorkItem")

#: Prefix of ``WorkItem``'s tier-dependent preset keys.
WORK_ITEM_PRESET_PREFIX = "work_item_"

#: Rigor tiers a :class:`~persistence.models.WorkItem` workflow can be
#: provisioned for, in the order the global-defaults tab lists them.
WORK_ITEM_TIERS: tuple[str, ...] = ("minimal", "standard", "extended")


def work_item_preset_key(tier: str) -> str:
    """Return the ``WorkItem`` workflow preset key for *tier*.

    >>> work_item_preset_key("extended")
    'work_item_extended'
    """
    return f"{WORK_ITEM_PRESET_PREFIX}{tier}"


#: ``tier -> preset key`` lookup for :class:`~persistence.models.WorkItem`.
WORK_ITEM_PRESET_BY_TIER: dict[str, str] = {
    tier: work_item_preset_key(tier) for tier in WORK_ITEM_TIERS
}

#: Every item type accepted by ``workflow-defaults`` and the workflow editor.
#: Adds the tier-driven ``Requirement`` and ``WorkItem`` to the fixed-preset
#: registry.
KNOWN_WORKFLOW_ITEM_TYPES: frozenset[str] = frozenset(
    {*TIER_DRIVEN_ITEM_TYPES, *WORKFLOW_ITEM_TYPE_PRESETS}
)

__all__ = [
    "COLUMNLESS_ITEM_TYPES",
    "KNOWN_WORKFLOW_ITEM_TYPES",
    "STATUS_MIRROR_ITEM_TYPES",
    "TIER_DRIVEN_ITEM_TYPES",
    "WORKFLOW_ITEM_TYPES",
    "WORKFLOW_ITEM_TYPE_PRESETS",
    "WORK_ITEM_PRESET_BY_TIER",
    "WORK_ITEM_PRESET_PREFIX",
    "WORK_ITEM_TIERS",
    "work_item_preset_key",
]
