"""The eight built-in link types — Startbelegung of the tenant catalog.

Single source of truth for three consumers that must never drift apart:
the seed/backfill migration (``0003_seed_builtin_link_types``), workspace
provisioning (``link_types.workspace_store.provision_workspace_link_types``),
and the tests that pin the spec table.

This module is deliberately import-free (no Django, no models) so a migration
can import it without triggering app-registry side effects.

Direction conventions, authoritative for every ``allowed_pairs`` entry below
(see ``traceability/audit/hierarchy.py``)::

    decomposes     source = parent (the decomposed)   target = child
    derives-from   source = child (the derived)       target = parent
    allocated-to   source = Requirement               target = ArchitectureElement
    verifies       source = TestCase                  target = Requirement/Arch
    mitigates      source = Risk                      target = Requirement/Arch
    decides        source = Adr                       target = anything
    references     source = anything                  target = a reference entity
    diagram-ref    source = Diagram                   target = anything

``"*"`` is a wildcard on either side.
"""
from __future__ import annotations

import copy
from typing import Any

#: The four propagation behaviours the suspect engine can dispatch on. This is
#: the one part of a definition a tenant may only *choose* from, never extend:
#: ``application.trace_link_service.TraceLinkService.propagate_suspect_status``
#: branches on the value, so a new behaviour is a code change (spec section 4,
#: "Grenze — suspect_rule ist kein freier Code").
SUSPECT_RULES: frozenset[str] = frozenset(
    {
        "none",
        "target_change_flags_source",
        "source_change_flags_target",
        "parent_change_flags_children",
    }
)

#: Old link-type key -> new key. ``None`` means the type is retired without a
#: successor (``parent-child`` is deduplicated into ``decomposes`` by the data
#: migration; ``copy-of`` moves into ``Artifact.copied_from``).
LEGACY_LINK_TYPE_MAPPING: dict[str, str | None] = {
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

#: Legacy keys whose rows must have source and target swapped when migrated.
#: ``satisfies`` was ArchitectureElement -> Requirement and ``implements`` was
#: ArchitectureElement -> Requirement; ``allocated-to`` runs the other way
#: (Requirement -> ArchitectureElement), so the endpoints move with the rename.
SWAPPED_LEGACY_KEYS: frozenset[str] = frozenset({"satisfies", "implements"})


def _pairs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"source_type": s, "target_type": t} for s, t in pairs]


BUILTIN_LINK_TYPES: dict[str, dict[str, Any]] = {
    "derives-from": {
        "label": {
            "de": {
                "downstream": "leitet sich ab von",
                "upstream": "ist Grundlage für",
                "neutral": "Ableitung",
            },
            "en": {
                "downstream": "derives from",
                "upstream": "is basis for",
                "neutral": "Derivation",
            },
        },
        # Arch<->Arch is new here: it arrives from the retired `refines` type.
        "allowed_pairs": _pairs(
            ("Requirement", "Requirement"),
            ("Requirement", "StakeholderNeed"),
            ("StakeholderNeed", "StakeholderNeed"),
            ("ArchitectureElement", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "decomposes": {
        "label": {
            "de": {
                "downstream": "zerlegt sich in",
                "upstream": "ist Teil von",
                "neutral": "Zerlegung",
            },
            "en": {
                "downstream": "decomposes into",
                "upstream": "is part of",
                "neutral": "Decomposition",
            },
        },
        "allowed_pairs": _pairs(
            ("Requirement", "Requirement"),
            ("ArchitectureElement", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "parent_change_flags_children",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "allocated-to": {
        "label": {
            "de": {
                "downstream": "ist zugewiesen an",
                "upstream": "erfüllt",
                "neutral": "Zuweisung",
            },
            "en": {
                "downstream": "is allocated to",
                "upstream": "fulfils",
                "neutral": "Allocation",
            },
        },
        # Arch->Arch is deliberately gone: it duplicated `decomposes`.
        "allowed_pairs": _pairs(("Requirement", "ArchitectureElement")),
        "coverage_relevant": True,
        "suspect_rule": "source_change_flags_target",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "verifies": {
        "label": {
            "de": {
                "downstream": "verifiziert",
                "upstream": "wird verifiziert von",
                "neutral": "Verifikation",
            },
            "en": {
                "downstream": "verifies",
                "upstream": "is verified by",
                "neutral": "Verification",
            },
        },
        "allowed_pairs": _pairs(
            ("TestCase", "Requirement"),
            ("TestCase", "ArchitectureElement"),
        ),
        "coverage_relevant": True,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "decides": {
        "label": {
            "de": {
                "downstream": "entscheidet über",
                "upstream": "wird entschieden durch",
                "neutral": "Entscheidung",
            },
            "en": {
                "downstream": "decides",
                "upstream": "is decided by",
                "neutral": "Decision",
            },
        },
        "allowed_pairs": _pairs(("Adr", "*")),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.3,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "mitigates": {
        "label": {
            "de": {
                "downstream": "mindert",
                "upstream": "wird gemindert durch",
                "neutral": "Risikominderung",
            },
            "en": {
                "downstream": "mitigates",
                "upstream": "is mitigated by",
                "neutral": "Mitigation",
            },
        },
        "allowed_pairs": _pairs(
            ("Risk", "Requirement"),
            ("Risk", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "references": {
        "label": {
            "de": {
                "downstream": "verweist auf",
                "upstream": "wird referenziert von",
                "neutral": "Verweis",
            },
            "en": {
                "downstream": "references",
                "upstream": "is referenced by",
                "neutral": "Reference",
            },
        },
        # Replaces documents/traces/uses-term. The target list is data, not a
        # fixed triple: the GitHub/Jira spec appends {"*", "ExternalRef"} here
        # with a one-row data migration and no validator change. GlossaryTerm
        # and Icd only become reachable once the Datenmodell-Konsolidierung
        # spec has given them Artifact rows — until then the pair simply never
        # matches, which is inert, not an error.
        #
        # Goal / MainGoal / Interview are wildcards on *both* sides, unlike the
        # reference entities above. They are shipped, user-authored endpoints:
        # fix #237 exists solely so a Goal/MainGoal id resolves in
        # TraceLinkService._resolve_artifact_id, and no production code writes
        # these links — the user picks both endpoints through the generic
        # trace-link REST/MCP surface, in either direction (see
        # mcp_server/tests/test_traceability_link_issue264.py, which pins Goal
        # as source *and* as target). They are regular built-ins, not
        # grandfathered legacy: see link_types/grandfathered.py for the four
        # pairs that are legacy-only on purpose.
        #
        # Issue is a wildcard on both sides for the same reason, added for the
        # same reason one step later: it was the one grandfathered triple with
        # no built-in successor at all (55 rows of `Issue --traces-->
        # ArchitectureElement` in the inventory), so a fresh tenant could not
        # link an Issue to anything — including via `seed_toothbrush`, the
        # app's own seeder. Issue links are user-authored through the generic
        # trace-link surface in either direction, exactly like Goal's.
        "allowed_pairs": _pairs(
            ("*", "GlossaryTerm"),
            ("*", "Diagram"),
            ("*", "Icd"),
            ("*", "Goal"),
            ("Goal", "*"),
            ("*", "MainGoal"),
            ("MainGoal", "*"),
            ("*", "Interview"),
            ("Interview", "*"),
            ("*", "Issue"),
            ("Issue", "*"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.2,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "diagram-ref": {
        "label": {
            "de": {
                "downstream": "stellt dar",
                "upstream": "wird dargestellt in",
                "neutral": "Diagrammbezug",
            },
            "en": {
                "downstream": "depicts",
                "upstream": "is depicted in",
                "neutral": "Diagram reference",
            },
        },
        "allowed_pairs": _pairs(("Diagram", "*")),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.2,
        # Reconciler-owned (diagram.traceability_connector.sync_node_links).
        # A hand-authored one is silently deleted on the diagram's next
        # node_graph save, which looks like unexplained data loss.
        "manual_creatable": False,
        "system_owned": True,
        "active": True,
        "built_in": True,
    },
}


def builtin_definition(key: str) -> dict[str, Any]:
    """Return a deep copy of the built-in definition for *key*.

    Always a copy: the seed migration, provisioning and the reset endpoint all
    persist the result, and a shared mutable reference would let one tenant's
    edit leak into another's row.

    Raises:
        KeyError: *key* is not a built-in type.
    """
    return copy.deepcopy(BUILTIN_LINK_TYPES[key])
