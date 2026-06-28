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
# Link-Type Enum (10 types — harmonized union from COMP-TE-001 / COMP-AS-005)
# REQ-L2-TE-001: 6 base types + 2 new (documents, realizes)
# REQ-L1-030:    + traces, copy-of (harmonized with COMP-AS-005)
# ---------------------------------------------------------------------------

class LinkType(str, Enum):
    """Valid link types for TraceLink entities.

    The persistence layer stores link_type as a plain CharField; validation
    is enforced in the service layer (COMP-TE-001) against this enum to
    support the 8-type contract without modifying persistence.models.
    """

    PARENT_CHILD = "parent-child"
    DERIVES_FROM = "derives-from"
    SATISFIES = "satisfies"
    VERIFIES = "verifies"
    IMPLEMENTS = "implements"
    REFINES = "refines"
    # L1-Arch §3.4 extensions:
    DOCUMENTS = "documents"
    REALIZES = "realizes"
    # REQ-L1-030 harmonization (from COMP-AS-005):
    TRACES = "traces"
    COPY_OF = "copy-of"

    @classmethod
    def values(cls) -> frozenset[str]:
        """Return the frozenset of valid string values."""
        return frozenset(m.value for m in cls)


VALID_LINK_TYPES: frozenset[str] = LinkType.values()

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
