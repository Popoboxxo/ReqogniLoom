"""The eight built-in link types are the spec's Startbelegung, verbatim."""
from __future__ import annotations

from link_types.builtin import (
    BUILTIN_LINK_TYPES,
    LEGACY_LINK_TYPE_MAPPING,
    SUSPECT_RULES,
    SWAPPED_LEGACY_KEYS,
    builtin_definition,
)

EXPECTED_KEYS = {
    "derives-from",
    "decomposes",
    "allocated-to",
    "verifies",
    "decides",
    "mitigates",
    "references",
    "diagram-ref",
}


def test_exactly_the_eight_core_types_are_seeded():
    assert set(BUILTIN_LINK_TYPES) == EXPECTED_KEYS


def test_suspect_rules_are_the_four_code_anchored_values():
    assert SUSPECT_RULES == {
        "none",
        "target_change_flags_source",
        "source_change_flags_target",
        "parent_change_flags_children",
    }


def test_only_allocated_to_and_verifies_are_coverage_relevant():
    coverage = {k for k, v in BUILTIN_LINK_TYPES.items() if v["coverage_relevant"]}
    assert coverage == {"allocated-to", "verifies"}


def test_impact_weights_match_the_spec_table():
    weights = {k: v["impact_weight"] for k, v in BUILTIN_LINK_TYPES.items()}
    assert weights == {
        "derives-from": 1.0,
        "decomposes": 1.0,
        "allocated-to": 1.0,
        "verifies": 1.0,
        "decides": 0.3,
        "mitigates": 0.5,
        "references": 0.2,
        "diagram-ref": 0.2,
    }


def test_suspect_rules_match_the_spec_table():
    rules = {k: v["suspect_rule"] for k, v in BUILTIN_LINK_TYPES.items()}
    assert rules == {
        "derives-from": "target_change_flags_source",
        "decomposes": "parent_change_flags_children",
        "allocated-to": "source_change_flags_target",
        "verifies": "target_change_flags_source",
        "decides": "none",
        "mitigates": "none",
        "references": "none",
        "diagram-ref": "none",
    }


def test_diagram_ref_is_the_only_system_owned_and_non_manual_type():
    system_owned = {k for k, v in BUILTIN_LINK_TYPES.items() if v["system_owned"]}
    non_manual = {k for k, v in BUILTIN_LINK_TYPES.items() if not v["manual_creatable"]}
    assert system_owned == {"diagram-ref"}
    assert non_manual == {"diagram-ref"}


def test_allocated_to_is_requirement_to_architecture_only():
    pairs = BUILTIN_LINK_TYPES["allocated-to"]["allowed_pairs"]
    assert pairs == [{"source_type": "Requirement", "target_type": "ArchitectureElement"}]


def test_derives_from_gained_the_architecture_pair_from_refines():
    pairs = BUILTIN_LINK_TYPES["derives-from"]["allowed_pairs"]
    assert {"source_type": "ArchitectureElement", "target_type": "ArchitectureElement"} in pairs


def test_references_targets_are_a_list_not_a_fixed_triple():
    pairs = BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    reference_entities = [
        p["target_type"] for p in pairs if p["source_type"] == "*"
    ]
    # The reference-entity half is append-only and keeps its original order:
    # the GitHub/Jira spec adds {"*", "ExternalRef"} here with a one-row data
    # migration and no validator change.
    assert reference_entities[:3] == ["GlossaryTerm", "Diagram", "Icd"]


def test_goal_main_goal_and_interview_are_reference_endpoints_in_both_directions():
    """fix #237's Goal/MainGoal links are regular built-ins, not grandfathered.

    They are user-authored through the generic trace-link surface, so both
    directions must be creatable in every tenant — including a brand-new one,
    which never sees link_types/grandfathered.py.
    """
    pairs = {
        (p["source_type"], p["target_type"])
        for p in BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    }
    for artifact_type in ("Goal", "MainGoal", "Interview"):
        assert ("*", artifact_type) in pairs
        assert (artifact_type, "*") in pairs


def test_issue_is_a_reference_endpoint_in_both_directions():
    """Issue is a regular built-in too, for the same reason Goal is.

    It was the one grandfathered triple with no built-in successor, so a
    freshly provisioned workspace could not link an Issue to anything —
    including through ``seed_toothbrush``, the app's own seeder.
    """
    pairs = {
        (p["source_type"], p["target_type"])
        for p in BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    }
    assert ("*", "Issue") in pairs
    assert ("Issue", "*") in pairs


def test_every_definition_carries_tri_labels_in_both_languages():
    for key, definition in BUILTIN_LINK_TYPES.items():
        for lang in ("de", "en"):
            assert set(definition["label"][lang]) == {
                "downstream",
                "upstream",
                "neutral",
            }, f"{key}/{lang} is missing a tri-label perspective"


def test_every_definition_is_active_and_flagged_built_in():
    assert all(v["active"] for v in BUILTIN_LINK_TYPES.values())
    assert all(v["built_in"] for v in BUILTIN_LINK_TYPES.values())


def test_legacy_mapping_covers_every_retired_key():
    assert LEGACY_LINK_TYPE_MAPPING == {
        "parent-child": None,
        "satisfies": "allocated-to",
        "implements": "allocated-to",
        "refines": "derives-from",
        "realizes": "decomposes",
        "documents": "references",
        "traces": "references",
        "uses-term": "references",
        "copy-of": None,
    }
    assert SWAPPED_LEGACY_KEYS == {"satisfies", "implements"}


def test_builtin_definition_returns_an_isolated_copy():
    first = builtin_definition("verifies")
    first["impact_weight"] = 99.0
    assert BUILTIN_LINK_TYPES["verifies"]["impact_weight"] == 1.0
    assert builtin_definition("verifies")["impact_weight"] == 1.0
