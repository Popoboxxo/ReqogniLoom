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
  All *domain-row* queries (Requirement, StakeholderNeed, TestCase, Adr, Risk,
  Issue, Goal, MainGoal, Artifact, TraceLink, ...) go through the ``unscoped``
  manager with an explicit ``tenant_id`` filter, mirroring ``BaselineStore``
  and ``ScopeResolver`` — this module does not depend on a thread-local
  tenant context for those reads.

  The status lookups added in Datenmodell-Konsolidierung Phase 1
  (``_engine_status`` -> ``workflow.state_reader.current_states``) are the one
  exception: that seam reads via ``WorkflowItemState.objects``, the
  tenant-*scoped* manager, so it relies on an active ``TenantContext`` and
  ignores the explicit ``tenant_id`` threaded through this module. Both
  production entry points (``application.baseline_facade.BaselineFacade`` and
  ``ChangeRequestService``) always set ``TenantContext`` before reaching this
  code, so this holds in practice — but a caller that invokes
  ``capture_states`` without an active tenant context would not get an error:
  the Requirement/StakeholderNeed/TestCase/Adr/Risk/Issue/Goal/MainGoal rows
  would still be captured (those reads stay ``unscoped``), only their engine
  status would silently come back empty.

  Task 12 dropped the ``status`` column this fallback used to read. A row
  with no engine status now (both the "no active TenantContext" case above
  and the genuine "no WorkflowItemState row at all" case, e.g. a
  definition-less workspace) is captured at its type's fixed-preset initial
  state (``state_reader.initial_state``) instead of a frozen legacy value.
  This is an explicit, reviewed data-loss tradeoff, not a bug — see the Task
  12 report, Finding 2.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from baseline.types import DeltaIndexTuple
from workflow import state_reader


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
    # Datenmodell-Konsolidierung Task 24: ``lifecycle_status`` rides along in
    # this same query -- it used to be a per-entity mirror column, now it is
    # this shared Artifact envelope's own field (Decision D-3), so there is
    # no separate query needed to resolve it.
    artifact_header_by_id: dict[str, dict[str, Any]] = {}
    artifact_lifecycle: dict[str, str] = {}
    for art_id, art_type, custom_fields, parent_id, lifecycle_status in (
        Artifact.unscoped.filter(id__in=uuids, tenant_id=tenant_id)
        .values_list("id", "artifact_type", "custom_fields", "parent_id", "lifecycle_status")
    ):
        artifact_header_by_id[str(art_id)] = {
            "artifact_type_raw": art_type,
            "custom_fields": custom_fields or {},
            "artifact_parent_id": str(parent_id) if parent_id else None,
        }
        artifact_lifecycle[str(art_id)] = lifecycle_status

    states: dict[str, dict[str, Any]] = {}

    # Requirement
    requirements = list(
        Requirement.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id)
    )
    req_states = _engine_status("Requirement", [r.id for r in requirements])
    req_initial_state = state_reader.initial_state("Requirement")
    for req in requirements:
        states[str(req.artifact_id)] = {
            "artifact_type": "requirement",
            "uid": req.uid,
            "title": req.title,
            "description": req.description,
            "acceptance_criteria": req.acceptance_criteria,
            "category": req.category,
            "status": req_states.get(str(req.id)) or req_initial_state,
            "type": req.type,
            "level": req.level,
            "complexity_fibonacci": req.complexity_fibonacci,
            "verification_method": req.verification_method,
            "suspect": req.suspect,
            "lifecycle_status": artifact_lifecycle.get(str(req.artifact_id), "active"),
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
            "lifecycle_status": artifact_lifecycle.get(str(ae.artifact_id), "active"),
            "version": ae.version,
        }

    # StakeholderNeed
    stakeholder_needs = list(
        StakeholderNeed.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id)
    )
    sn_states = _engine_status(
        "StakeholderNeed", [sn.id for sn in stakeholder_needs]
    )
    sn_initial_state = state_reader.initial_state("StakeholderNeed")
    for sn in stakeholder_needs:
        states[str(sn.artifact_id)] = {
            "artifact_type": "stakeholder_need",
            "uid": sn.uid,
            "title": sn.title,
            "description": sn.description,
            "category": sn.category,
            "status": sn_states.get(str(sn.id)) or sn_initial_state,
            "moscow_priority": sn.moscow_priority,
            "suspect": sn.suspect,
            "lifecycle_status": artifact_lifecycle.get(str(sn.artifact_id), "active"),
            "version": sn.version,
        }

    # TestCase
    test_cases = list(
        TestCase.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id)
    )
    tc_states = _engine_status("TestCase", [tc.id for tc in test_cases])
    tc_initial_state = state_reader.initial_state("TestCase")
    for tc in test_cases:
        states[str(tc.artifact_id)] = {
            "artifact_type": "test_case",
            "uid": tc.uid,
            "title": tc.title,
            "description": tc.description,
            "steps": tc.steps,
            "test_type": tc.test_type,
            "status": tc_states.get(str(tc.id)) or tc_initial_state,
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

    SA-21: the five models are resolved via the Layer-0 domain-model
    registry rather than importing application.models directly (Layer 1 ->
    Layer 2) — see persistence.domain_model_registry's module docstring.
    """
    from persistence.domain_model_registry import get_models

    app_models = get_models("Adr", "Risk", "Issue", "Goal", "MainGoal")
    Adr = app_models["Adr"]
    Risk = app_models["Risk"]
    Issue = app_models["Issue"]
    Goal = app_models["Goal"]
    MainGoal = app_models["MainGoal"]

    states: dict[str, dict[str, Any]] = {}

    def _raw_type(artifact_id: Any, fallback: str) -> str:
        header = artifact_header_by_id.get(str(artifact_id))
        if header is None:
            return fallback
        return header.get("artifact_type_raw") or fallback

    adrs = list(Adr.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id))
    adr_states = _engine_status("Adr", [adr.id for adr in adrs])
    adr_initial_state = state_reader.initial_state("Adr")
    for adr in adrs:
        states[str(adr.artifact_id)] = {
            "artifact_type": _raw_type(adr.artifact_id, "Adr"),
            "uid": adr.uid,
            "title": adr.title,
            "description": adr.description,
            "context": adr.context,
            "decision": adr.decision,
            "consequences": adr.consequences,
            "status": adr_states.get(str(adr.id)) or adr_initial_state,
            "version": adr.version,
        }

    risks = list(Risk.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id))
    risk_states = _engine_status("Risk", [risk.id for risk in risks])
    risk_initial_state = state_reader.initial_state("Risk")
    for risk in risks:
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
            "status": risk_states.get(str(risk.id)) or risk_initial_state,
            "version": risk.version,
        }

    issues = list(Issue.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id))
    issue_states = _engine_status("Issue", [issue.id for issue in issues])
    issue_initial_state = state_reader.initial_state("Issue")
    for issue in issues:
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
            "status": issue_states.get(str(issue.id)) or issue_initial_state,
            "version": issue.version,
        }

    goals = list(Goal.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id))
    goal_states = _engine_status("Goal", [goal.id for goal in goals])
    goal_initial_state = state_reader.initial_state("Goal")
    for goal in goals:
        states[str(goal.artifact_id)] = {
            "artifact_type": _raw_type(goal.artifact_id, "Goal"),
            "lineage_id": str(goal.lineage_id),
            "sequence_number": goal.sequence_number,
            "title": goal.title,
            "description": goal.description,
            "status": goal_states.get(str(goal.id)) or goal_initial_state,
            "version": goal.version,
        }

    main_goals = list(
        MainGoal.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id)
    )
    mg_states = _engine_status("MainGoal", [mg.id for mg in main_goals])
    mg_initial_state = state_reader.initial_state("MainGoal")
    for mg in main_goals:
        states[str(mg.artifact_id)] = {
            "artifact_type": _raw_type(mg.artifact_id, "MainGoal"),
            "sequence_number": mg.sequence_number,
            "content": mg.content,
            "source": mg.source,
            "generated_from_goal_ids": mg.generated_from_goal_ids,
            "status": mg_states.get(str(mg.id)) or mg_initial_state,
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
    """Capture state for ICD entries in one batched query.

    ``item_id`` is expected to be an :class:`icd.models.Icd` UUID. This handler
    is included for completeness — the current ScopeResolver does not emit
    ``icd`` entries, but keeping the capture logic here means the feature works
    the moment they are added, without touching this module again.

    Datenmodell-Konsolidierung Task 28c-2: reads the contract off the ``Icd``
    header, which is where it lives now that ``IcdVersion`` is retired. The
    captured keys are unchanged, so any stored baseline state stays comparable.
    """
    uuids = _to_uuids(item_ids)
    if not uuids:
        return {}

    # SA-21: resolved via the Layer-0 domain-model registry rather than
    # importing icd.models directly (Layer 1 -> Layer 1 sibling) — see
    # persistence.domain_model_registry's module docstring. Preserves the
    # previous "icd app optional" degrade-gracefully behaviour: a name that
    # was never registered (icd app absent) comes back None.
    from persistence.domain_model_registry import get_model

    Icd = get_model("Icd")
    if Icd is None:  # pragma: no cover - icd app optional
        return {}

    states: dict[str, dict[str, Any]] = {}
    for icd in Icd.unscoped.filter(id__in=uuids, tenant_id=tenant_id):
        states[str(icd.id)] = {
            "artifact_type": "icd",
            "version_number": icd.current_revision,
            "direction": icd.direction,
            "interface_type": icd.interface_type,
            "semantic_description": icd.semantic_description,
            "preconditions": icd.preconditions,
            "postconditions": icd.postconditions,
            "invariants": icd.invariants,
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


def _engine_status(item_type: str, entity_ids: list) -> dict[str, str]:
    """Resolve the workflow state of *entity_ids* keyed by ``str(entity_id)``.

    Datenmodell-Konsolidierung Phase 1: baselines used to snapshot the
    denormalized ``status`` column directly. ``WorkflowItemState`` is now the
    source of truth for a captured item's status; callers fall back to
    ``state_reader.initial_state`` (Task 12: the column is dropped) for items
    the engine does not track (e.g. no ``WorkflowItemState`` row yet, or a
    definition-less workspace) — mirroring ``rest_api.mixins.workflow_state``
    and every Phase-1 service migration (D-1: same value vocabulary, only the
    source changes). One query per entity type keeps capture O(types), not
    O(rows).
    """
    return state_reader.current_states(item_type, entity_ids)


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
