"""
ARCH-L1-006 BaselineService — Full-State-Snapshot capture (REQ-L2-BL-012).

leaf_id: COMP-BL-001 (DeltaIndexBuilder) / COMP-BL-003 (BaselineStore)
req_id:  REQ-L2-BL-012 (Baseline Full-State-Snapshot)

Given the delta index tuples resolved for a Baseline, this module produces a
``{item_id: state_dict}`` mapping that captures the *complete* field-level
state of every referenced entity at Baseline creation time. Storing this state
alongside the version number enables:

  - Reconstructing "what did entity X look like in this baseline" without the
    audit log (REQ-L2-BL-012).
  - Field-level Baseline diffs (COMP-BL-002, DiffEngine).

Performance (ADR-L3-BL001-01 spirit, N+1 avoidance):
  Entities are grouped by ``entity_type`` and each type is fetched in a *single*
  batched query using ``id__in`` / ``artifact_id__in``. No per-item DB round
  trips are issued. For the "item" entity_type — where ``item_id`` is an
  Artifact UUID that may back a Requirement, ArchitectureElement,
  StakeholderNeed or TestCase — one query per candidate domain table is issued
  (4 queries total, independent of item count) plus one for the Artifact
  headers.

Tenant isolation:
  All queries go through the ``unscoped`` manager with an explicit
  ``tenant_id`` filter, mirroring ``BaselineStore`` and ``ScopeResolver``.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from baseline.types import DeltaIndexTuple


def capture_states(
    delta_index: Iterable[DeltaIndexTuple],
    tenant_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    """Return a ``{item_id: state_dict}`` map for the given delta index.

    REQ-L2-BL-012. Only entities that are found are included; missing rows are
    silently skipped (their entry simply gets a ``None`` state at persist time).

    Args:
        delta_index: The resolved (item_id, version, entity_type) tuples.
        tenant_id: Active tenant UUID for row-level isolation.

    Returns:
        Mapping from ``item_id`` (str) to a JSON-serializable state dict.
    """
    # Group item_ids by entity_type so each kind can be batch-fetched.
    by_type: dict[str, list[str]] = {}
    for t in delta_index:
        by_type.setdefault(t.entity_type, []).append(t.item_id)

    states: dict[str, dict[str, Any]] = {}

    if "item" in by_type:
        states.update(_capture_items(by_type["item"], tenant_id))
    if "trace_link" in by_type:
        states.update(_capture_trace_links(by_type["trace_link"], tenant_id))
    if "glossary_term" in by_type:
        states.update(_capture_glossary_terms(by_type["glossary_term"], tenant_id))
    if "icd" in by_type:
        states.update(_capture_icd_versions(by_type["icd"], tenant_id))

    return states


# ---------------------------------------------------------------------------
# entity_type = "item" (Artifact-backed domain entities)
# ---------------------------------------------------------------------------


def _capture_items(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for Artifact-backed items via batched queries.

    ``item_id`` is the Artifact UUID. The concrete domain entity is discovered
    by batch-querying each candidate table on ``artifact_id__in``. This is a
    fixed number of queries (5) regardless of how many items are captured.
    """
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        StakeholderNeed,
        TestCase,
    )

    # Artifact headers — provides artifact_type as a fallback discriminator.
    artifact_type_by_id: dict[str, str] = {}
    for art_id, art_type in (
        Artifact.unscoped.filter(id__in=uuids, tenant_id=tenant_id)
        .values_list("id", "artifact_type")
    ):
        artifact_type_by_id[str(art_id)] = art_type

    states: dict[str, dict[str, Any]] = {}

    # Requirement
    for req in Requirement.unscoped.filter(
        artifact_id__in=uuids, tenant_id=tenant_id
    ):
        states[str(req.artifact_id)] = {
            "artifact_type": "requirement",
            "uid": req.uid,
            "title": req.title,
            "description": req.description,
            "category": req.category,
            "status": req.status,
            "type": req.type,
            "complexity_fibonacci": req.complexity_fibonacci,
            "verification_method": req.verification_method,
            "suspect": req.suspect,
            "version": req.version,
        }

    # ArchitectureElement
    for ae in ArchitectureElement.unscoped.filter(
        artifact_id__in=uuids, tenant_id=tenant_id
    ):
        states[str(ae.artifact_id)] = {
            "artifact_type": "architecture_element",
            "uid": ae.uid,
            "title": ae.title,
            "description": ae.description,
            "element_type": ae.element_type,
            "asil_level": ae.asil_level,
            "make_or_buy": ae.make_or_buy,
            "suspect": ae.suspect,
            "version": ae.version,
        }

    # StakeholderNeed
    for sn in StakeholderNeed.unscoped.filter(
        artifact_id__in=uuids, tenant_id=tenant_id
    ):
        states[str(sn.artifact_id)] = {
            "artifact_type": "stakeholder_need",
            "uid": sn.uid,
            "title": sn.title,
            "description": sn.description,
            "category": sn.category,
            "status": sn.status,
            "moscow_priority": sn.moscow_priority,
            "suspect": sn.suspect,
            "version": sn.version,
        }

    # TestCase
    for tc in TestCase.unscoped.filter(
        artifact_id__in=uuids, tenant_id=tenant_id
    ):
        states[str(tc.artifact_id)] = {
            "artifact_type": "test_case",
            "uid": tc.uid,
            "title": tc.title,
            "description": tc.description,
            "steps": tc.steps,
            "suspect": tc.suspect,
            "version": tc.version,
        }

    # Bare artifacts (no domain entity found) — capture the type + version so
    # the entry is not left stateless.
    for item_id in item_ids:
        if item_id in states:
            continue
        art_type = artifact_type_by_id.get(item_id)
        if art_type is not None:
            states[item_id] = {
                "artifact_type": art_type,
            }

    return states


# ---------------------------------------------------------------------------
# entity_type = "trace_link"
# ---------------------------------------------------------------------------


def _capture_trace_links(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for TraceLink entries in one batched query."""
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    from persistence.models import TraceLink

    states: dict[str, dict[str, Any]] = {}
    for tl in TraceLink.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(tl.id)] = {
            "artifact_type": "trace_link",
            "source_id": str(tl.source_id),
            "target_id": str(tl.target_id),
            "link_type": tl.link_type,
            "version": tl.version,
        }
    return states


# ---------------------------------------------------------------------------
# entity_type = "glossary_term"
# ---------------------------------------------------------------------------


def _capture_glossary_terms(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for GlossaryTerm entries in one batched query."""
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    from persistence.models import GlossaryTerm

    states: dict[str, dict[str, Any]] = {}
    for gt in GlossaryTerm.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(gt.id)] = {
            "artifact_type": "glossary_term",
            "term": gt.term,
            "definition": gt.definition,
            "synonyms": gt.synonyms,
            "abbreviation": gt.abbreviation,
            "version": gt.version,
        }
    return states


# ---------------------------------------------------------------------------
# entity_type = "icd" (defensive; not currently produced by ScopeResolver)
# ---------------------------------------------------------------------------


def _capture_icd_versions(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for IcdVersion entries in one batched query.

    ``item_id`` is expected to be an IcdVersion UUID. This handler is included
    for completeness — the current ScopeResolver does not emit ``icd`` entries,
    but keeping the capture logic here means the feature works the moment they
    are added, without touching this module again.
    """
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    try:
        from icd.models import IcdVersion
    except Exception:  # pragma: no cover - icd app optional
        return {}

    states: dict[str, dict[str, Any]] = {}
    for iv in IcdVersion.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(iv.id)] = {
            "artifact_type": "icd",
            "version_number": iv.version_number,
            "direction": iv.direction,
            "interface_type": iv.interface_type,
            "semantic_description": iv.semantic_description,
            "preconditions": iv.preconditions,
            "postconditions": iv.postconditions,
            "invariants": iv.invariants,
        }
    return states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_uuids(item_ids: list[str]) -> list[uuid.UUID]:
    """Convert string ids to UUIDs, skipping malformed values."""
    result: list[uuid.UUID] = []
    for raw in item_ids:
        parsed = _safe_uuid(raw)
        if parsed is not None:
            result.append(parsed)
    return result


def _safe_uuid(raw: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


__all__ = ["capture_states"]
