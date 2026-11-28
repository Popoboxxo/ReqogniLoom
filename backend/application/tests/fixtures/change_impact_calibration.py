"""Calibration fixtures for the deterministic change-impact severity rule (S0.6).

The fixtures are **workspace excerpts** built from the repository's own
deterministic seed definitions, because the running development stack (verified
read-only on 2026-11-28) holds no workspace data to sample. The excerpts mirror
the real chain shapes the seeds create:

* ``seed_toothbrush`` — ``Zahnbürste SysEng Demo``: an SE hierarchy with
  ``derives-from`` (requirement → parent need/requirement), ``allocated-to``
  and ``verifies`` (TestCase → Requirement) edges.
* ``seed_full_chain`` — ``SysEng Full-Chain Demo``: 3 Goals, 4 StakeholderNeeds
  (``satisfies``), 12 × L1 + 12 × L2 requirements (``derives-from``,
  ``allocated-to``), a decomposed architecture and 12 verifying TestCases; the
  fixture Change Request changes two L2 requirements.

Each excerpt lists findings as they would be produced for a change set in that
workspace: aggregated ``weight``, shortest ``hop_distance``, whether the chain
is coverage-relevant, whether it is suspect-flagged, the edge ``origin`` and the
severity the deterministic rule (``application.change_impact_severity``) must
produce. Every excerpt stays at or below the S0.6 target of 20 % blocking.

Provenance note: the development database behind ``reqogniloom-backend-1`` was
queried read-only (``pl_workspace`` / ``pl_requirement`` / ``pl_tracelink``
counts) and contained zero workspaces, requirements and trace links, so no
live aggregate counts could be sampled. The values below are therefore derived
from the seed definitions, not measured production data.
"""

from __future__ import annotations

WORKSPACE_EXCERPTS: list[dict] = [
    {
        "name": "Zahnbürste SysEng Demo — L1→L2 Verifikationskette",
        "provenance": (
            "backend/auth_tenancy/management/commands/seed_toothbrush.py "
            "(WORKSPACE_NAME 'Zahnbürste SysEng Demo': L1–L4 requirements with "
            "derives-from / allocated-to / verifies links); synthetic excerpt "
            "from seed definitions"
        ),
        "cases": [
            # Direct verifying TestCase of the changed L2 requirement.
            {
                "weight": "0.9000",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # Parent L1 requirement, flagged suspect after the change.
            {
                "weight": "0.8500",
                "hop_distance": 1,
                "coverage_relevant": False,
                "suspect": True,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # Allocated architecture component, close but not coverage-relevant.
            {
                "weight": "0.6000",
                "hop_distance": 1,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Stakeholder need reached through the L1 requirement.
            {
                "weight": "0.7000",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Goal reached through the need.
            {
                "weight": "0.4500",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Sibling L2 requirement through the shared L1 parent.
            {
                "weight": "0.3500",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Near-but-weak edge: close hop keeps it a warning.
            {
                "weight": "0.1500",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Deep chain below the warning weight: info.
            {
                "weight": "0.1800",
                "hop_distance": 4,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
            # Very deep, very weak: info.
            {
                "weight": "0.0500",
                "hop_distance": 5,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
            # Semantic edge is capped at warning even at maximal weight.
            {
                "weight": "1.0000",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "semantic",
                "expected_severity": "warning",
            },
        ],
    },
    {
        "name": "SysEng Full-Chain Demo — CR 01/02 (zwei L2-Anforderungen)",
        "provenance": (
            "backend/auth_tenancy/management/commands/seed_full_chain.py "
            "(WORKSPACE_NAME 'SysEng Full-Chain Demo': CR 'Anpassung der "
            "Subsystemanforderungen 01 und 02', 12 verifying TestCases, "
            "need→goal validation chain); synthetic excerpt from seed definitions"
        ),
        "cases": [
            # Verifying TestCase of the first changed L2 requirement.
            {
                "weight": "0.9500",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # Verifying TestCase of the second changed L2 requirement.
            {
                "weight": "0.9000",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # Shared L1 parent requirement.
            {
                "weight": "0.7000",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Allocated component of a changed L2 requirement.
            {
                "weight": "0.6500",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Root architecture element.
            {
                "weight": "0.5000",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Stakeholder need via the L1 parent.
            {
                "weight": "0.3000",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Goal behind the need.
            {
                "weight": "0.2500",
                "hop_distance": 4,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Sibling test at moderate distance but low weight: still close.
            {
                "weight": "0.1200",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Deep, weak, coverage-irrelevant: info.
            {
                "weight": "0.1000",
                "hop_distance": 4,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
            # Semantic edge to a coverage-relevant target: never blocking.
            {
                "weight": "1.0000",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "semantic",
                "expected_severity": "warning",
            },
        ],
    },
    {
        "name": "Zahnbürste SysEng Demo — Architektur-Zerlegung (L2→L3→L4)",
        "provenance": (
            "backend/auth_tenancy/management/commands/seed_toothbrush.py "
            "(architecture decomposition with derives-from / allocated-to "
            "edges across L2→L3→L4); synthetic excerpt from seed definitions"
        ),
        "cases": [
            # Directly decomposed child element, suspect-flagged.
            {
                "weight": "0.8000",
                "hop_distance": 1,
                "coverage_relevant": False,
                "suspect": True,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # Hop 2, strong but not coverage-relevant.
            {
                "weight": "0.6000",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Hop 3, strong: cannot block beyond the blocking hop limit.
            {
                "weight": "0.5500",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Hop 4, still above the warning weight.
            {
                "weight": "0.5000",
                "hop_distance": 4,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Hop 5.
            {
                "weight": "0.4000",
                "hop_distance": 5,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Hop 6.
            {
                "weight": "0.3000",
                "hop_distance": 6,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Hop 7, below the warning weight: info.
            {
                "weight": "0.1500",
                "hop_distance": 7,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
            # Hop 8, weak: info.
            {
                "weight": "0.1000",
                "hop_distance": 8,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
            # Semantic edge, near and coverage-relevant: capped at warning.
            {
                "weight": "1.0000",
                "hop_distance": 2,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "semantic",
                "expected_severity": "warning",
            },
            # High weight but far: hop limit prevents blocking.
            {
                "weight": "0.8000",
                "hop_distance": 9,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
        ],
    },
    {
        "name": "SysEng Full-Chain Demo — Need→Goal Validierungskette",
        "provenance": (
            "backend/auth_tenancy/management/commands/seed_full_chain.py "
            "(4 StakeholderNeeds 'satisfies' a Goal, L1 requirements "
            "'derives-from' a need, TestCases 'verifies' the requirement); "
            "synthetic excerpt from seed definitions"
        ),
        "cases": [
            # TestCase validating the changed need.
            {
                "weight": "0.9000",
                "hop_distance": 1,
                "coverage_relevant": True,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "blocking",
            },
            # L1 requirement deriving from the need, weak aggregate weight.
            {
                "weight": "0.4000",
                "hop_distance": 1,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Goal satisfied by the need.
            {
                "weight": "0.3500",
                "hop_distance": 2,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Sibling need through the shared goal.
            {
                "weight": "0.2500",
                "hop_distance": 3,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "warning",
            },
            # Deep requirement beyond the warning window: info.
            {
                "weight": "0.1000",
                "hop_distance": 4,
                "coverage_relevant": False,
                "suspect": False,
                "origin": "deterministic",
                "expected_severity": "info",
            },
        ],
    },
]
