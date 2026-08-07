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
    # REQ-L1-042 allocation tracking:
    ALLOCATED_TO = "allocated-to"
    # REQ-L1-044 Semantic Glossary Link
    USES_TERM = "uses-term"
    # REQ-L2-TE-020 ADR decision link (ADR -> ArchitectureElement):
    DECIDES = "decides"
    # UMSETZUNGSPLAN_SYSENG_2.0.md §1.4: additive Requirement/Need hierarchy
    # link type — the hardcoded output of RequirementService.decompose() /
    # derive_requirement(), replacing the workspace-configurable link type
    # (formerly read from Workspace.decomposition_link_type). Not a rename of
    # PARENT_CHILD: existing parent-child TraceLinks/baselines are untouched.
    DECOMPOSES = "decomposes"
    # Codeberg #353 Task 3: Reconciler-owned only (Codeberg #353) — never
    # hand-authored, never touched by manual trace-link CRUD.
    DIAGRAM_REF = "diagram-ref"

    @classmethod
    def values(cls) -> frozenset[str]:
        """Return the frozenset of valid string values."""
        return frozenset(m.value for m in cls)


VALID_LINK_TYPES: frozenset[str] = LinkType.values()

#: Codeberg #353 final review (I1): every link type EXCEPT the
#: reconciler-owned DIAGRAM_REF, which must never be created/updated through
#: manual TraceLink CRUD (REST ``trace-links`` endpoints, MCP
#: ``traceability.create_link`` / ``architecture.link``). Manual creation of a
#: ``diagram-ref`` link would silently be deleted on the next node_graph save
#: (``diagram.traceability_connector.sync_node_links``'s ``current - desired``
#: reconciliation), which looks like unexplained data loss to the caller who
#: just created it. Single source of truth for both the manual-CRUD rejection
#: (application.trace_link_service.TraceLinkService.create_trace_link) and the
#: MCP tool schemas' published ``link_type`` enum.
MANUAL_LINK_TYPES: frozenset[str] = VALID_LINK_TYPES - {LinkType.DIAGRAM_REF.value}

# ---------------------------------------------------------------------------
# SE endpoint semantics (SE-mode rigor, see docs/se/workspace_modes_er_model.md)
#
# In se_mode workspaces the link_type string alone is not enough: SE discipline
# constrains WHICH artifact types a link may connect (e.g. "verifies" is only
# valid from a TestCase towards a Requirement/ArchitectureElement).
#
# Matrix values:
#   set of (source_type, target_type) pairs — "*" is a wildcard side.
#   SAME_TYPE sentinel — both endpoints must share the same artifact type.
#   Link types absent from the matrix are unrestricted (traces, realizes,
#   uses-term — deliberately generic).
#
# Artifact types outside the core set (e.g. ICD or import artifacts) are NOT
# constrained: enforcement is permissive by design so that existing data and
# seeds keep working.
# ---------------------------------------------------------------------------

_REQ = "Requirement"
_ARCH = "ArchitectureElement"
_TC = "TestCase"
_SN = "StakeholderNeed"
_DIAG = "Diagram"

#: Core artifact types the SE matrix constrains. Anything else passes.
SE_CORE_ARTIFACT_TYPES: frozenset[str] = frozenset(
    {_REQ, _ARCH, _TC, _SN, _DIAG}
)

#: Sentinel: both endpoints must have the same artifact type.
SAME_TYPE = "same-type"

SE_LINK_SEMANTICS: dict[str, object] = {
    LinkType.DERIVES_FROM.value: {(_REQ, _REQ), (_REQ, _SN), (_SN, _SN)},
    LinkType.SATISFIES.value: {(_ARCH, _REQ), (_REQ, _SN)},
    LinkType.VERIFIES.value: {(_TC, _REQ), (_TC, _ARCH)},
    LinkType.IMPLEMENTS.value: {(_ARCH, _REQ)},
    LinkType.REFINES.value: {(_REQ, _REQ), (_ARCH, _ARCH)},
    LinkType.ALLOCATED_TO.value: {(_REQ, _ARCH), (_ARCH, _ARCH)},
    LinkType.DOCUMENTS.value: {(_DIAG, "*")},
    LinkType.PARENT_CHILD.value: SAME_TYPE,
    LinkType.COPY_OF.value: SAME_TYPE,
}


def normalize_artifact_type(artifact_type: str | None) -> str:
    """Strip sub-type tags: ``"TestCase:unit"`` → ``"TestCase"``."""
    if not artifact_type:
        return ""
    return artifact_type.split(":", 1)[0]


def check_se_link_semantics(
    link_type: str, source_type: str | None, target_type: str | None
) -> Optional[str]:
    """Validate SE endpoint semantics for a link (se_mode rigor).

    Args:
        link_type: One of VALID_LINK_TYPES.
        source_type: Artifact.artifact_type of the source endpoint.
        target_type: Artifact.artifact_type of the target endpoint.

    Returns:
        None if the combination is SE-conform (or unconstrained),
        otherwise a human-readable error message.
    """
    rule = SE_LINK_SEMANTICS.get(link_type)
    if rule is None:
        return None  # unrestricted link type

    src = normalize_artifact_type(source_type)
    tgt = normalize_artifact_type(target_type)

    # Permissive default: non-core artifact types are never constrained.
    if src not in SE_CORE_ARTIFACT_TYPES or tgt not in SE_CORE_ARTIFACT_TYPES:
        return None

    if rule == SAME_TYPE:
        if src == tgt:
            return None
        return (
            f"SE mode: '{link_type}' links require both endpoints to be the "
            f"same artifact type (got {src} -> {tgt})."
        )

    pairs = rule  # set of (source, target) pairs, "*" = wildcard
    for pair_src, pair_tgt in pairs:  # type: ignore[union-attr]
        if pair_src in ("*", src) and pair_tgt in ("*", tgt):
            return None

    allowed = ", ".join(
        sorted(f"{s}->{t}" for s, t in pairs)  # type: ignore[union-attr]
    )
    return (
        f"SE mode: '{link_type}' is not valid from {src} to {tgt}. "
        f"Allowed: {allowed}."
    )

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
    "SE_LINK_SEMANTICS",
    "SE_CORE_ARTIFACT_TYPES",
    "SAME_TYPE",
    "check_se_link_semantics",
    "normalize_artifact_type",
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
