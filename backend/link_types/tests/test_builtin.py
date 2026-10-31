"""The built-in link types are the spec's Startbelegung, verbatim."""
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
    "refines",
    "allocated-to",
    "verifies",
    "validates",
    "performs",
    "decides",
    "mitigates",
    "satisfies",
    "realizes",
    "references",
    "diagram-ref",
}

#: Plan F F1.1-T2 (ENT-F1 = b): the Issue/Risk vocabulary as own built-ins.
ISSUE_RISK_VOCABULARY_KEYS = {"blocks", "resolves", "threatens"}

#: The pinned values of the spec table. Membership only — the catalog grows
#: with the plan series, so no test here may pin the *total* (KA-F-07).
PINNED_IMPACT_WEIGHTS = {
    "derives-from": 1.0,
    "decomposes": 1.0,
    "refines": 0.8,
    "allocated-to": 1.0,
    "verifies": 1.0,
    "validates": 1.0,
    "performs": 0.8,
    "decides": 0.3,
    "mitigates": 0.5,
    "satisfies": 1.0,
    "realizes": 0.8,
    "references": 0.2,
    "diagram-ref": 0.2,
    "blocks": 0.5,
    "resolves": 0.3,
    "threatens": 0.5,
}

PINNED_SUSPECT_RULES = {
    "derives-from": "target_change_flags_source",
    "decomposes": "parent_change_flags_children",
    "refines": "target_change_flags_source",
    "allocated-to": "source_change_flags_target",
    "verifies": "target_change_flags_source",
    "validates": "target_change_flags_source",
    "performs": "target_change_flags_source",
    "decides": "none",
    "mitigates": "none",
    "satisfies": "target_change_flags_source",
    "realizes": "target_change_flags_source",
    "references": "none",
    "diagram-ref": "none",
    "blocks": "none",
    "resolves": "none",
    "threatens": "none",
}


def test_the_expected_core_types_are_seeded():
    # Membership, not equality: later plans extend the catalog (Plan F adds
    # more built-in types), so the spec table must never pin a total count.
    assert EXPECTED_KEYS <= set(BUILTIN_LINK_TYPES)


def test_suspect_rules_are_the_four_code_anchored_values():
    assert SUSPECT_RULES == {
        "none",
        "target_change_flags_source",
        "source_change_flags_target",
        "parent_change_flags_children",
    }


def test_exactly_the_four_coverage_relevant_types_are_flagged():
    coverage = {k for k, v in BUILTIN_LINK_TYPES.items() if v["coverage_relevant"]}
    # `satisfies` is the ISO 15288/29148 validation edge (#950) — the only
    # coverage-relevant link to a Goal; `validates` (#878) is the
    # stakeholder-layer counterpart of `verifies`. Equality on purpose: an
    # accidentally flagged type would silently move the coverage KPI, so a
    # fifth edge has to be added here deliberately.
    assert coverage == {"allocated-to", "verifies", "satisfies", "validates"}


def test_impact_weights_match_the_spec_table():
    weights = {k: v["impact_weight"] for k, v in BUILTIN_LINK_TYPES.items()}
    # Membership of the pinned values, not a full map: a full map would pin the
    # catalog size, and later plans extend it (KA-F-07).
    for key, weight in PINNED_IMPACT_WEIGHTS.items():
        assert weights[key] == weight, key


def test_suspect_rules_match_the_spec_table():
    rules = {k: v["suspect_rule"] for k, v in BUILTIN_LINK_TYPES.items()}
    for key, rule in PINNED_SUSPECT_RULES.items():
        assert rules[key] == rule, key


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


def test_satisfaction_types_have_the_expected_pairs():
    """#950: `satisfies`/`realizes` are Requirement -> Goal, `refines` Req -> Req.

    #402 (cluster 5) added the direct ``StakeholderNeed -> Goal`` edge to
    `satisfies` — the validation pillar's remediation path. `realizes` stays
    Requirement -> Goal only (it is not the coverage-relevant edge).
    """
    assert BUILTIN_LINK_TYPES["satisfies"]["allowed_pairs"] == [
        {"source_type": "Requirement", "target_type": "Goal"},
        {"source_type": "StakeholderNeed", "target_type": "Goal"},
        # #877 (B3-T3): a Requirement may satisfy a *function* element.
        {"source_type": "Requirement", "target_type": "ArchitectureElement:function"},
    ]
    assert BUILTIN_LINK_TYPES["realizes"]["allowed_pairs"] == [
        {"source_type": "Requirement", "target_type": "Goal"}
    ]
    assert BUILTIN_LINK_TYPES["refines"]["allowed_pairs"] == [
        {"source_type": "Requirement", "target_type": "Requirement"}
    ]


def test_performs_links_an_element_to_a_function():
    """#877 (B3-T3): the functional architecture edge is a regular built-in.

    A component/subsystem *performs* a function. It carries no coverage
    obligation of its own — a function is justified by the Requirement that
    satisfies it (TRACE-P3), not by the performing element.
    """
    assert "performs" in BUILTIN_LINK_TYPES
    definition = BUILTIN_LINK_TYPES["performs"]
    assert definition["allowed_pairs"] == [
        {
            "source_type": "ArchitectureElement",
            "target_type": "ArchitectureElement:function",
        }
    ]
    assert definition["coverage_relevant"] is False
    assert definition["suspect_rule"] == "target_change_flags_source"
    assert definition["impact_weight"] == 0.8
    assert definition["manual_creatable"] is True
    assert definition["system_owned"] is False
    assert definition["label"]["de"] == {
        "downstream": "führt aus",
        "upstream": "wird ausgeführt von",
        "neutral": "Funktionszuordnung",
    }
    assert definition["label"]["en"] == {
        "downstream": "performs",
        "upstream": "is performed by",
        "neutral": "Function allocation",
    }


def test_issue_risk_vocabulary_is_backed_by_built_ins():
    """Plan F F1.1-T2 (ENT-F1 = b): ``blocks``/``resolves``/``threatens``.

    Pinned definitions, verbatim from the plan. ``blocked-by`` is the upstream
    label of ``blocks`` and ``mitigated-by`` the upstream label of ``mitigates``
    — neither needs an own type; ``caused-by``/``related-to`` stay aliases of
    ``references``.
    """
    assert ISSUE_RISK_VOCABULARY_KEYS <= set(BUILTIN_LINK_TYPES)

    blocks = BUILTIN_LINK_TYPES["blocks"]
    assert blocks["allowed_pairs"] == [{"source_type": "Issue", "target_type": "*"}]
    assert blocks["label"]["de"] == {
        "downstream": "blockiert",
        "upstream": "wird blockiert durch",
        "neutral": "Blockade",
    }
    assert blocks["label"]["en"] == {
        "downstream": "blocks",
        "upstream": "is blocked by",
        "neutral": "Blocker",
    }
    assert blocks["impact_weight"] == 0.5

    resolves = BUILTIN_LINK_TYPES["resolves"]
    assert resolves["allowed_pairs"] == [{"source_type": "*", "target_type": "Issue"}]
    assert resolves["label"]["de"] == {
        "downstream": "löst",
        "upstream": "wird gelöst durch",
        "neutral": "Lösung",
    }
    assert resolves["label"]["en"] == {
        "downstream": "resolves",
        "upstream": "is resolved by",
        "neutral": "Resolution",
    }
    assert resolves["impact_weight"] == 0.3

    threatens = BUILTIN_LINK_TYPES["threatens"]
    assert threatens["allowed_pairs"] == [{"source_type": "Risk", "target_type": "*"}]
    assert threatens["label"]["de"] == {
        "downstream": "bedroht",
        "upstream": "wird bedroht durch",
        "neutral": "Bedrohung",
    }
    assert threatens["label"]["en"] == {
        "downstream": "threatens",
        "upstream": "is threatened by",
        "neutral": "Threat",
    }
    assert threatens["impact_weight"] == 0.5

    for key in ISSUE_RISK_VOCABULARY_KEYS:
        definition = BUILTIN_LINK_TYPES[key]
        assert definition["coverage_relevant"] is False
        assert definition["suspect_rule"] == "none"
        assert definition["manual_creatable"] is True
        assert definition["system_owned"] is False
        assert definition["active"] is True
        assert definition["built_in"] is True


def test_legacy_mapping_covers_every_retired_key():
    # Historical, migration-only (#950): three of these keys were re-introduced
    # as built-ins with new pairs, but the pre-consolidation mapping stands.
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
