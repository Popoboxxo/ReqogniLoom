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
  StakeholderNeed, TestCase, Adr, Risk, Issue, Goal or MainGoal — one query per
  candidate domain table is issued (a constant, independent of item count) plus
  one for the Artifact headers.

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
    if "test_run" in by_type:
        states.update(_capture_test_runs(by_type["test_run"], tenant_id))
    if "test_run_result" in by_type:
        states.update(_capture_test_run_results(by_type["test_run_result"], tenant_id))

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
    fixed number of queries (one per candidate table plus one for the Artifact
    headers) regardless of how many items are captured.

    Issue #398: the captured field set is the *only* thing a baseline diff can
    ever see, because :mod:`baseline.diff_engine` compares snapshotted values
    rather than a version counter. A field that is not captured here is a field
    whose drift is structurally invisible — so every user-editable column of
    every artifact-backed entity belongs in this map. Before #398 the map was
    missing ``Requirement.acceptance_criteria`` / ``level``, the workflow
    ``status`` of TestCases, ``lifecycle_status`` (soft-delete) everywhere, the
    element re-parenting signal, ``Artifact.custom_fields`` (which is where
    user-defined attributes such as a "rationale" live) and, most severely, the
    entire content of ADRs / Risks / Issues / Goals — those fell through to the
    "bare artifact" branch and were snapshotted as ``{"artifact_type": "Adr"}``.
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

    # Artifact headers — the shared envelope of every artifact-backed entity.
    # ``artifact_type`` doubles as a fallback discriminator; ``custom_fields``
    # and ``parent`` are real, user-visible state that no subtype table holds.
    artifact_header_by_id: dict[str, dict[str, Any]] = {}
    for art_id, art_type, custom_fields, parent_id in (
        Artifact.unscoped.filter(id__in=uuids, tenant_id=tenant_id)
        .values_list("id", "artifact_type", "custom_fields", "parent_id")
    ):
        artifact_header_by_id[str(art_id)] = {
            "artifact_type_raw": art_type,
            "custom_fields": custom_fields or {},
            "artifact_parent_id": str(parent_id) if parent_id else None,
        }

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
            "acceptance_criteria": req.acceptance_criteria,
            "category": req.category,
            "status": req.status,
            "type": req.type,
            "level": req.level,
            "complexity_fibonacci": req.complexity_fibonacci,
            "verification_method": req.verification_method,
            "suspect": req.suspect,
            "lifecycle_status": req.lifecycle_status,
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
            "parent_id": str(ae.parent_id) if ae.parent_id else None,
            "asil_level": ae.asil_level,
            "make_or_buy": ae.make_or_buy,
            "suspect": ae.suspect,
            "lifecycle_status": ae.lifecycle_status,
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
            "lifecycle_status": sn.lifecycle_status,
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
            "test_type": tc.test_type,
            "status": tc.status,
            "suspect": tc.suspect,
            "version": tc.version,
        }

    states.update(
        _capture_application_entities(uuids, tenant_id, artifact_header_by_id)
    )

    # Merge the shared Artifact envelope into every captured state and give
    # bare artifacts (no domain entity found) at least that envelope, so their
    # entry is not left effectively stateless.
    for item_id in item_ids:
        header = artifact_header_by_id.get(item_id)
        if header is None:
            continue
        state = states.get(item_id)
        if state is None:
            state = {"artifact_type": header["artifact_type_raw"]}
            states[item_id] = state
        state["custom_fields"] = header["custom_fields"]
        state["artifact_parent_id"] = header["artifact_parent_id"]

    return states


def _capture_application_entities(
    uuids: list[uuid.UUID],
    tenant_id: uuid.UUID,
    artifact_header_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Capture Artifact-backed entities that live in ``application.models``.

    ADR / Risk / Issue / Goal / MainGoal each own a backing Artifact (their
    ``artifact`` OneToOne) and therefore appear in every project and global
    baseline — but none of them had a state capture, so their entire content
    was invisible to a baseline diff (issue #398).

    One batched query per table, matching the pattern above. These models are
    plain (non-tenant-scoped) ``models.Model`` subclasses with a flat
    ``tenant_id`` UUID column, so the tenant filter is applied explicitly.

    ``artifact_type`` deliberately echoes the raw ``Artifact.artifact_type``
    string rather than a normalized label: these entries used to fall through
    to the bare-artifact branch, which stored exactly that raw value. Keeping
    it identical means a diff that straddles this change sees only *added*
    keys (which ``_field_diff`` ignores) instead of a spurious
    ``artifact_type: "Adr" -> "adr"`` change on every ADR in the workspace.
    """
    from application.models import Adr, Goal, Issue, MainGoal, Risk

    states: dict[str, dict[str, Any]] = {}

    def _raw_type(artifact_id: Any, fallback: str) -> str:
        header = artifact_header_by_id.get(str(artifact_id))
        if header is None:
            return fallback
        return header.get("artifact_type_raw") or fallback

    for adr in Adr.objects.filter(artifact_id__in=uuids, tenant_id=tenant_id):
        states[str(adr.artifact_id)] = {
            "artifact_type": _raw_type(adr.artifact_id, "Adr"),
            "uid": adr.uid,
            "title": adr.title,
            "description": adr.description,
            "context": adr.context,
            "decision": adr.decision,
            "consequences": adr.consequences,
            "status": adr.status,
            "version": adr.version,
        }

    for risk in Risk.objects.filter(artifact_id__in=uuids, tenant_id=tenant_id):
        states[str(risk.artifact_id)] = {
            "artifact_type": _raw_type(risk.artifact_id, "Risk"),
            "uid": risk.uid,
            "title": risk.title,
            "description": risk.description,
            "category": risk.category,
            "probability": risk.probability,
            "impact": risk.impact,
            "detection": risk.detection,
            "risk_score": risk.risk_score,
            "severity": risk.severity,
            "owner": risk.owner,
            "owner_user_id": str(risk.owner_user_id) if risk.owner_user_id else None,
            "mitigation_strategy": risk.mitigation_strategy,
            "status": risk.status,
            "version": risk.version,
        }

    for issue in Issue.objects.filter(artifact_id__in=uuids, tenant_id=tenant_id):
        states[str(issue.artifact_id)] = {
            "artifact_type": _raw_type(issue.artifact_id, "Issue"),
            "uid": issue.uid,
            "title": issue.title,
            "description": issue.description,
            "severity": issue.severity,
            "category": issue.category,
            "assignee_id": str(issue.assignee_id) if issue.assignee_id else None,
            "due_date": issue.due_date.isoformat() if issue.due_date else None,
            "tags": issue.tags,
            "status": issue.status,
            "version": issue.version,
        }

    for goal in Goal.objects.filter(artifact_id__in=uuids, tenant_id=tenant_id):
        states[str(goal.artifact_id)] = {
            "artifact_type": _raw_type(goal.artifact_id, "Goal"),
            "lineage_id": str(goal.lineage_id),
            "sequence_number": goal.sequence_number,
            "title": goal.title,
            "description": goal.description,
            "status": goal.status,
            "version": goal.version,
        }

    for mg in MainGoal.objects.filter(artifact_id__in=uuids, tenant_id=tenant_id):
        states[str(mg.artifact_id)] = {
            "artifact_type": _raw_type(mg.artifact_id, "MainGoal"),
            "sequence_number": mg.sequence_number,
            "content": mg.content,
            "source": mg.source,
            "generated_from_goal_ids": mg.generated_from_goal_ids,
            "status": mg.status,
            "version": mg.version,
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
# entity_type = "test_run" (REQ-155)
# ---------------------------------------------------------------------------


def _capture_test_runs(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for TestRun entities in one batched query.

    REQ-155: TestRun entities are operational records not backed by an Artifact.
    Captured fields represent the full execution context at snapshot time.
    """
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    from persistence.models import TestRun

    states: dict[str, dict[str, Any]] = {}
    for tr in TestRun.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(tr.id)] = {
            "entity_type": "test_run",
            "uid": tr.uid,
            "name": tr.name,
            "status": tr.status,
            "started_at": tr.started_at.isoformat() if tr.started_at else None,
            "finished_at": tr.finished_at.isoformat() if tr.finished_at else None,
            "ci_job_id": tr.ci_job_id,
            "workspace_id": str(tr.workspace_id),
            "version": tr.version,
        }
    return states


# ---------------------------------------------------------------------------
# entity_type = "test_run_result" (REQ-155)
# ---------------------------------------------------------------------------


def _capture_test_run_results(
    item_ids: list[str], tenant_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Capture state for TestRunResult entities in one batched query.

    REQ-155: TestRunResult entries are the per-test-case outcomes within a run.
    """
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    from persistence.models import TestRunResult

    states: dict[str, dict[str, Any]] = {}
    for trr in TestRunResult.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(trr.id)] = {
            "entity_type": "test_run_result",
            "test_run_id": str(trr.test_run_id),
            "test_case_id": str(trr.test_case_id) if trr.test_case_id else None,
            "test_case_title": trr.test_case_title,
            "status": trr.status,
            "executed_at": trr.executed_at.isoformat() if trr.executed_at else None,
            "duration_ms": trr.duration_ms,
            "message": trr.message,
            "version": trr.version,
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
