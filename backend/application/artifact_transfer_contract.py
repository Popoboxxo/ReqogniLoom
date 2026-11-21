"""Canonical artifact-transfer contract (P1 of docs/plans/2026-11-21-artifact-transfer-plan.md).

The single source of truth for *which entities exist, what they can be exported
as, which relations must be remapped and what happens to a row that is absent
from an incoming snapshot*. Import, export, workspace copy and backup/restore
will all read this module; the ratchet test in
``application/tests/test_artifact_transfer_contract.py`` fails when any of the
other registries drifts away from it.

Design decisions implemented here (see the plan, §4):

* D3b — no import ever deletes. A missing target row is moved to
  ``status_reconcile`` and flagged ``not_in_source`` instead.
* D8 — every REST/MCP-listed entity (24) has a spec, including the two
  configuration entities whose scope is *not* a workspace artifact.
* D9/D10 — new ids + ``source_id``; all relations are in scope, so every spec
  lists its relation carriers.
* D12b — tenant/workspace/artifact identity is always remapped, never taken
  from the source row (``REMAP_ALWAYS``).
* D13 — audit, secrets, global definitions and external stores are excluded
  from every snapshot.
* D14d — ReqIF stays standard-conformant and covers Need, Requirement,
  TestCase and Icd; other types use the ZIP snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass

from persistence.artifact_backing import ARTIFACT_TYPE_MODELS


#: Identity columns that are ALWAYS rebound to the target workspace, even
#: though D12 makes all other exported fields authoritative (D12b).
REMAP_ALWAYS: frozenset[str] = frozenset(
    {"tenant_id", "workspace_id", "artifact_id", "parent_id", "source_id"}
)

#: Never part of an artifact snapshot (D13).
SNAPSHOT_EXCLUSIONS: tuple[str, ...] = (
    "audit_log",
    "password_hashes",
    "totp_ciphertext",
    "memory_secrets",
    "global_attribute_definitions",
    "global_workflow_definitions",
    "external_vector_store_contents",
)

#: Relation carriers copied and remapped by snapshot/copy (D10).
ARTIFACT_RELATIONS: tuple[str, ...] = (
    "trace_links",
    "parent_hierarchy",
    "allocation",
    "group_membership",
    "comments",
    "test_runs",
)

#: Formats every artifact-scoped entity must support (D14: "alle Einzelformate").
BASE_FORMATS: tuple[str, ...] = ("json", "csv", "markdown", "pdf", "zip")

#: Standard-conformant ReqIF mapping (D14d).
REQIF_FORMATS: tuple[str, ...] = ("reqif",)


@dataclass(frozen=True)
class ArtifactTransferSpec:
    """One entity's transfer capabilities and safety rules."""

    entity_key: str
    type_name: str
    scope: str  # "artifact" | "workspace_config" | "global_config"
    formats: tuple[str, ...] = BASE_FORMATS
    relations: tuple[str, ...] = ARTIFACT_RELATIONS
    status_reconcile: str | None = "outdated"
    exclusions: tuple[str, ...] = SNAPSHOT_EXCLUSIONS
    roundtrip: bool = True
    note: str = ""

    @property
    def is_artifact(self) -> bool:
        return self.scope == "artifact"

    @property
    def is_reqif(self) -> bool:
        return "reqif" in self.formats


def _spec(
    entity_key: str,
    type_name: str,
    *,
    scope: str = "artifact",
    formats: tuple[str, ...] = BASE_FORMATS,
    relations: tuple[str, ...] = ARTIFACT_RELATIONS,
    status_reconcile: str | None = "outdated",
    roundtrip: bool = True,
    note: str = "",
) -> ArtifactTransferSpec:
    return ArtifactTransferSpec(
        entity_key=entity_key,
        type_name=type_name,
        scope=scope,
        formats=formats,
        relations=relations,
        status_reconcile=status_reconcile,
        exclusions=SNAPSHOT_EXCLUSIONS,
        roundtrip=roundtrip,
        note=note,
    )


#: All 24 entities listed by the REST/MCP entity-surface matrix. Keys are the
#: stable ids from ``mcp_server/tests/entity_surface_matrix.py``; the ratchet
#: test asserts both sets stay identical.
TRANSFER_SPECS: dict[str, ArtifactTransferSpec] = {
    "requirement": _spec("requirement", "Requirement", status_reconcile="outdated"),
    "stakeholder_need": _spec("stakeholder_need", "StakeholderNeed"),
    "architecture_element": _spec("architecture_element", "ArchitectureElement"),
    "test_case": _spec("test_case", "TestCase", status_reconcile="deprecated"),
    "test_run": _spec("test_run", "TestRun"),
    "adr": _spec("adr", "Adr"),
    "risk": _spec("risk", "Risk"),
    "issue": _spec("issue", "Issue"),
    "glossary_term": _spec("glossary_term", "GlossaryTerm"),
    "goal": _spec("goal", "Goal"),
    "main_goal": _spec("main_goal", "MainGoal"),
    "change_request": _spec("change_request", "ChangeRequest"),
    "icd": _spec("icd", "Icd"),
    "diagram": _spec("diagram", "Diagram"),
    "document": _spec("document", "Document"),
    "work_item": _spec("work_item", "WorkItem"),
    "milestone": _spec("milestone", "Milestone"),
    "artifact": _spec("artifact", "Artifact"),
    "trace_link": _spec("trace_link", "TraceLink"),
    "baseline": _spec("baseline", "Baseline"),
    "interview_session": _spec("interview_session", "InterviewSession"),
    "comment": _spec("comment", "Comment"),
    "link_type": _spec(
        "link_type",
        "WorkspaceLinkType",
        scope="workspace_config",
        formats=("json", "zip"),
        relations=(),
        status_reconcile=None,
        roundtrip=False,
        note="Workspace-scoped definitions: copied only with a new workspace (D11).",
    ),
    "workspace": _spec(
        "workspace",
        "Workspace",
        scope="global_config",
        formats=("json",),
        relations=(),
        status_reconcile=None,
        roundtrip=False,
        note="Tenant object, not an artifact: snapshot metadata only.",
    ),
}

# Standard-conformant ReqIF mapping (D14d): add the format only to the four
# entities that have a defined SpecObject mapping. Their other formats stay.
for _key in ("stakeholder_need", "requirement", "test_case", "icd"):
    _old = TRANSFER_SPECS[_key]
    TRANSFER_SPECS[_key] = ArtifactTransferSpec(
        entity_key=_old.entity_key,
        type_name=_old.type_name,
        scope=_old.scope,
        formats=_old.formats + REQIF_FORMATS,
        relations=_old.relations,
        status_reconcile=_old.status_reconcile,
        exclusions=_old.exclusions,
        roundtrip=_old.roundtrip,
        note="ReqIF 1.2 SpecObject mapping; all other formats via the ZIP snapshot.",
    )
del _key, _old


def spec_for(entity_key: str) -> ArtifactTransferSpec | None:
    """Return the contract entry for a stable entity key, or ``None``."""
    return TRANSFER_SPECS.get(entity_key)


def spec_for_type(type_name: str) -> ArtifactTransferSpec | None:
    """Return the contract entry for a model/type name, or ``None``."""
    for spec in TRANSFER_SPECS.values():
        if spec.type_name == type_name:
            return spec
    return None


def artifact_specs() -> tuple[ArtifactTransferSpec, ...]:
    """Every workspace-artifact entity (24 minus the two config entities)."""
    return tuple(s for s in TRANSFER_SPECS.values() if s.is_artifact)


def reqif_specs() -> tuple[ArtifactTransferSpec, ...]:
    """The entities with a standard-conformant ReqIF mapping."""
    return tuple(s for s in TRANSFER_SPECS.values() if s.is_reqif)


def missing_artifact_types() -> tuple[str, ...]:
    """Artifact-backed types from the canonical model registry without a spec."""
    return tuple(
        sorted(type_name for type_name in ARTIFACT_TYPE_MODELS if spec_for_type(type_name) is None)
    )


__all__ = [
    "ARTIFACT_RELATIONS",
    "BASE_FORMATS",
    "REQIF_FORMATS",
    "REMAP_ALWAYS",
    "SNAPSHOT_EXCLUSIONS",
    "TRANSFER_SPECS",
    "ArtifactTransferSpec",
    "artifact_specs",
    "missing_artifact_types",
    "reqif_specs",
    "spec_for",
    "spec_for_type",
]
