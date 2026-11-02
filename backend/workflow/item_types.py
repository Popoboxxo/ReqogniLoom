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

``Requirement`` is deliberately **not** in the tuple: its preset is the
workspace's rigor tier (``minimal``/``standard``/``extended``), resolved at
provisioning time, not a fixed per-entity key. It is nevertheless a known
workflow item type — see :data:`KNOWN_WORKFLOW_ITEM_TYPES`.
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

#: Every item type accepted by ``workflow-defaults`` and the workflow editor.
#: Adds the tier-driven ``Requirement`` to the fixed-preset registry.
KNOWN_WORKFLOW_ITEM_TYPES: frozenset[str] = frozenset(
    {"Requirement", *WORKFLOW_ITEM_TYPE_PRESETS}
)

__all__ = [
    "COLUMNLESS_ITEM_TYPES",
    "KNOWN_WORKFLOW_ITEM_TYPES",
    "STATUS_MIRROR_ITEM_TYPES",
    "WORKFLOW_ITEM_TYPES",
    "WORKFLOW_ITEM_TYPE_PRESETS",
]
