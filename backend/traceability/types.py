"""
ARCH-L1-007 TraceabilityEngine — Shared data types and enumerations.

leaf_id: COMP-TE-001_TraceLinkManager, COMP-TE-002_QueryEngine,
         COMP-TE-003_CoverageCalculator, COMP-TE-004_VCRMReportGenerator
req_id: REQ-L2-TE-001, REQ-L2-TE-004, REQ-L2-TE-006, REQ-L2-TE-013

All dataclasses used as interface contracts between TraceabilityEngine
components are defined here (interface discipline: no circular imports).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Link-Type Enum — the eight built-in keys of ``link_types/builtin.py``.
# The ten legacy members (parent-child, satisfies, implements, refines,
# realizes, documents, traces, uses-term, copy-of) were retired by the
# link-type consolidation; ``link_types.builtin.LEGACY_LINK_TYPE_MAPPING``
# records what each one became and the data migration moved the rows.
# ---------------------------------------------------------------------------

class LinkType(str, Enum):
    """Convenience symbols for the eight built-in keys.

    **NOT the validation authority** — that is
    :func:`link_types.catalog.resolve_catalog` /
    :func:`link_types.catalog.validate_link_pair`, which is per-workspace and
    tenant-extensible. This enum survives only so code that wants a symbol
    instead of a string literal has one, and it lists the built-ins only: a
    tenant-defined key has no member here by design.

    The persistence layer stores link_type as a plain CharField.
    """

    DERIVES_FROM = "derives-from"
    # UMSETZUNGSPLAN_SYSENG_2.0.md §1.4 / link-type consolidation: the
    # Requirement/ArchitectureElement decomposition edge. Absorbed the retired
    # ``parent-child`` (same direction: source is the parent) and ``realizes``.
    DECOMPOSES = "decomposes"
    # REQ-L1-042 allocation tracking. Absorbed ``satisfies``/``implements``,
    # which ran ArchitectureElement -> Requirement; ``allocated-to`` runs
    # Requirement -> ArchitectureElement, so migrated rows had their endpoints
    # swapped (``link_types.builtin.SWAPPED_LEGACY_KEYS``).
    ALLOCATED_TO = "allocated-to"
    VERIFIES = "verifies"
    # REQ-L2-TE-020 ADR decision link (ADR -> ArchitectureElement):
    DECIDES = "decides"
    MITIGATES = "mitigates"
    # Absorbed ``documents``, ``traces`` and ``uses-term``.
    REFERENCES = "references"
    # Codeberg #353 Task 3: Reconciler-owned only (Codeberg #353) — never
    # hand-authored, never touched by manual trace-link CRUD.
    DIAGRAM_REF = "diagram-ref"

    @classmethod
    def values(cls) -> frozenset[str]:
        """Return the frozenset of valid string values."""
        return frozenset(m.value for m in cls)


#: Legacy convenience set over :class:`LinkType`. **No longer a validation
#: authority** — ``link_types.catalog.validate_link_pair`` decides what a
#: workspace accepts. Still referenced by the ReqIF importer's pre-filter and
#: the MCP tool schemas until those move to the catalog (Task 21).
VALID_LINK_TYPES: frozenset[str] = LinkType.values()

#: Every link type EXCEPT the reconciler-owned DIAGRAM_REF (Codeberg #353 I1).
#: **No longer the manual-CRUD gate** — that is now the catalog's
#: ``manual_creatable``/``system_owned`` flags, enforced for every type in
#: every workspace. Kept only as the published ``link_type`` enum of the MCP
#: tool schemas until those move to the catalog.
MANUAL_LINK_TYPES: frozenset[str] = VALID_LINK_TYPES - {LinkType.DIAGRAM_REF.value}

# ---------------------------------------------------------------------------
# The SE endpoint matrix (SE_LINK_SEMANTICS, SE_CORE_ARTIFACT_TYPES,
# SAME_TYPE, check_se_link_semantics) used to live here. It is gone: endpoint
# semantics are per-workspace catalog data now, and both of its escape hatches
# (the ``se_mode`` gate and the "non-core artifact types pass unchecked"
# allow-list, audit finding U2) were removed with it. See link_types/catalog.py.
# ``normalize_artifact_type`` moved to ``link_types.catalog`` so the catalog
# owns the whole matching vocabulary.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Direction enum for queries
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    """Query direction for graph traversal."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


# ---------------------------------------------------------------------------
# Result dataclasses (interface contracts between components)
# REQ-L2-TE-004: NeighborResult
# REQ-L2-TE-005: TransitiveResult
# REQ-L2-TE-008: TraceGraphData
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NeighborResult:
    """Direct-neighbor query result (IF-TE-EXT-IN-001, IF-TE-INT-001).

    REQ-L2-TE-004: entity_id, entity_type, link_type, direction.
    """

    entity_id: uuid.UUID
    entity_type: str          # e.g. "Artifact", "Requirement"
    link_type: str
    direction: str            # "upstream" | "downstream"
    workspace_id: Optional[uuid.UUID] = None  # populated for cross-project results


@dataclass(frozen=True)
class TransitiveResult:
    """Transitive-hull query result (REQ-L2-TE-005).

    depth=1 means directly connected.
    """

    entity_id: uuid.UUID
    entity_type: str
    link_type: str
    direction: str
    depth: int
    workspace_id: Optional[uuid.UUID] = None


@dataclass
class TraceGraphData:
    """Serializable trace graph for Baseline snapshots (REQ-L2-TE-008).

    IF-TE-EXT-IN-004: collect_trace_graph(workspace_id) return type.
    """

    links: list[dict]  # list of {id, source_id, target_id, link_type, tenant_id}

    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {"links": self.links}


# ---------------------------------------------------------------------------
# Coverage data types (COMP-TE-003 / COMP-TE-004)
# REQ-L2-TE-006: CoverageReport
# ---------------------------------------------------------------------------

@dataclass
class CoverageReport:
    """Test-coverage summary (REQ-L2-TE-006, REQ-L2-TE-007).

    IF-TE-EXT-IN-002 return type.
    """

    total: int
    covered: int
    uncovered: list[str]
    percentage: float

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "covered": self.covered,
            "uncovered": self.uncovered,
            "percentage": self.percentage,
        }


@dataclass
class RequirementCoverageEntry:
    """Per-requirement test-case assignments used by VCRM (COMP-TE-004).

    Part of CoverageData — REQ-L2-TE-013.
    """

    requirement_id: str
    test_cases: list[dict]  # [{id, result: "Passed"|"Failed"|"Not Run"}]


@dataclass
class CoverageData:
    """Detailed per-requirement coverage data (IF-TE-INT-004).

    Consumed by COMP-TE-004 VCRMReportGenerator.
    """

    entries: list[RequirementCoverageEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "requirements": {
                e.requirement_id: {"test_cases": e.test_cases}
                for e in self.entries
            }
        }


# ---------------------------------------------------------------------------
# VCRM types (COMP-TE-004)
# REQ-L2-TE-013
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VCRMRow:
    """Single row in the VCRM matrix (REQ-L2-TE-013)."""

    requirement_id: str
    component_id: str
    test_case_id: str
    test_result: str  # "Passed" | "Failed" | "Not Run"


@dataclass
class VCRMMatrix:
    """Full VCRM matrix (REQ-L2-TE-013)."""

    rows: list[VCRMRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rows": [
                {
                    "requirement_id": r.requirement_id,
                    "component_id": r.component_id,
                    "test_case_id": r.test_case_id,
                    "test_result": r.test_result,
                }
                for r in self.rows
            ]
        }


__all__ = [
    "LinkType",
    "VALID_LINK_TYPES",
    "MANUAL_LINK_TYPES",
    "Direction",
    "NeighborResult",
    "TransitiveResult",
    "TraceGraphData",
    "CoverageReport",
    "RequirementCoverageEntry",
    "CoverageData",
    "VCRMRow",
    "VCRMMatrix",
]
