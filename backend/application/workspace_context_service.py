"""Workspace-context read model (REQ-L2-MC-004, ADR-01 / issue #124).

``workspace.get_context`` answers "what does this workspace currently look
like?" for an AI agent: entity counts, lightweight per-entity lists and the
most recent workflow transitions. All of that is *read-only aggregation* — no
validation, no preset gate, no audit trail, no optimistic locking.

Historically the queries lived inline in ``mcp_server/tools/cross_cutting.py``,
which broke ADR-01's Single-Entry-Point rule: the MCP transport layer talked to
the ORM directly, so the same aggregation could not be reused by the REST layer
and was invisible to the architecture ratchet. This module is that code moved
down a layer, same field aliases, same return shapes.

Datenmodell-Konsolidierung Phase 1: every entity type here is resolved the
same way — through ``workflow.state_reader.current_states`` (batched, one
query per entity type regardless of row count), falling back to the row's own
(now write-once, frozen-at-creation) ``status``/``lifecycle_status`` column
only for an item that was never wired into a ``WorkflowItemState`` (matches
the fallback convention established in the REST serializers / baseline
capture). Before this, ``Requirement``/``TestCase`` read a denormalized
``status`` mirror column directly while ``ArchitectureElement`` already went
through ``workflow.services.outdated_item_ids()`` — that asymmetry is gone
now that the mirror is no longer written.

Every function sets the tenant context itself rather than relying on the caller
having done so, which is the ``ServiceBase._set_tenant_context`` convention.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db.models import F, OuterRef, Subquery

logger = logging.getLogger(__name__)

# Item types whose titles can be resolved for ``recent_changes``. Deliberately
# the same three "core" types the counts/lists above understand; entries of any
# other type still appear, they just fall back to their raw id as the title.
_TITLE_RESOLVABLE_TYPES = ("Requirement", "ArchitectureElement", "TestCase")


def _set_tenant(tenant_id: UUID) -> None:
    """Activate the tenant context for the tenant-scoped ``objects`` managers."""
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)


def count_open_requirements(
    *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
) -> int:
    """Return the number of requirements that are not yet "done".

    "Open" means "not in a terminal-positive state of the workspace's active
    Requirement workflow" (SYSTEMAUDIT SA-56) — resolved per-workspace via
    :func:`workflow.services.terminal_positive_states`, not a hardcoded
    ``status != "approved"`` literal. That literal was preset-blind: it
    wrongly counted Extended's "implemented"/"verified" requirements (both
    *past* the approval gate) as still-open, and — for Minimal, which has no
    "approved" state at all — it counted every "done" requirement as open too.

    Soft-deleted (``"outdated"``) requirements are only counted when the
    caller explicitly asks for them (REQ-006); ``"outdated"`` is the universal
    soft-delete pseudo-state and is never a member of a preset's declared
    ``terminal_positive_states`` (see ``workflow.definition_store`` module
    docstring), so the two exclusions never overlap.

    Args:
        workspace_id:     Workspace to scope to.
        tenant_id:        Tenant whose context is activated for the query.
        include_outdated: Count soft-deleted requirements as open too.

    Returns:
        The count of open requirements.
    """
    from persistence.models import Requirement
    from workflow import state_reader
    from workflow.services import terminal_positive_states

    _set_tenant(tenant_id)
    done_states = terminal_positive_states(workspace_id, "Requirement")
    rows = list(
        Requirement.objects.filter(artifact__workspace_id=workspace_id).values("id")
    )
    if not rows:
        return 0
    states = state_reader.current_states("Requirement", (row["id"] for row in rows))
    # Task 12: the ``status`` column is dropped, so a row never wired into a
    # WorkflowItemState falls back to the "draft" preset initial state
    # instead (documented, reviewed data-loss tradeoff, see Task 12 report
    # Finding 2).
    requirement_initial_state = state_reader.initial_state("Requirement")
    open_count = 0
    for row in rows:
        resolved = states.get(str(row["id"])) or requirement_initial_state
        if done_states and resolved in done_states:
            continue
        if not include_outdated and resolved == "outdated":
            continue
        open_count += 1
    return open_count


def entity_counts(
    *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
) -> Dict[str, Any]:
    """Return per-entity-type counts for the workspace.

    ``include_outdated`` deliberately does **not** hide the ``outdated``
    counts: agents need to see how many items were soft-deleted, and ``total``
    always covers active + outdated. The flag only governs list-level
    responses and ``count_open_requirements``. ``active`` always excludes
    outdated regardless of the flag.

    Args:
        workspace_id:     Workspace to scope to.
        tenant_id:        Tenant whose context is activated for the queries.
        include_outdated: Accepted for signature symmetry with the other read
            functions; see the note above on why it does not filter here.

    Returns:
        Mapping with ``requirements``/``architecture``/``tests``/``risks``
        sub-dicts.
    """
    from application.models import Risk
    from persistence.models import (
        ArchitectureElement,
        Requirement,
        TestCase,
        TestRunResult,
    )
    from workflow import state_reader
    from workflow.services import outdated_item_ids

    _set_tenant(tenant_id)

    # Task 12: the ``status`` column is dropped from every ``.values()``
    # projection below -- a row never wired into a WorkflowItemState falls
    # back to its preset's initial state instead (documented, reviewed
    # data-loss tradeoff, see Task 12 report Finding 2).
    req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    req_rows = list(req_qs.values("id"))
    req_states = state_reader.current_states("Requirement", (r["id"] for r in req_rows))
    req_initial_state = state_reader.initial_state("Requirement")
    req_outdated = sum(
        1
        for r in req_rows
        if (req_states.get(str(r["id"])) or req_initial_state) == "outdated"
    )
    req_active = len(req_rows) - req_outdated

    arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
    arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
    arch_total = arch_qs.count()
    arch_outdated = arch_qs.filter(id__in=arch_outdated_ids).count()

    test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)
    test_rows = list(test_qs.values("id"))
    test_states = state_reader.current_states("TestCase", (r["id"] for r in test_rows))
    test_initial_state = state_reader.initial_state("TestCase")
    test_active_ids = {
        r["id"]
        for r in test_rows
        if (test_states.get(str(r["id"])) or test_initial_state) != "outdated"
    }
    test_outdated = len(test_rows) - len(test_active_ids)
    test_active_qs = test_qs.filter(id__in=test_active_ids)
    test_active = len(test_active_ids)
    # TestCase's current state (WorkflowEngine lifecycle:
    # Draft/Ready/Approved/Deprecated/outdated) does NOT carry pass/fail
    # execution results. Those live on TestRunResult (one row per TestCase
    # execution within a TestRun); "pass"/"fail" here means each TestCase's
    # most recent TestRunResult.status.
    latest_result_status = (
        TestRunResult.objects.filter(test_case_id=OuterRef("pk"))
        .order_by(F("executed_at").desc(nulls_last=True), "-id")
        .values("status")[:1]
    )
    test_pass = (
        test_active_qs.annotate(_latest_result_status=Subquery(latest_result_status))
        .filter(_latest_result_status="passed")
        .count()
    )
    test_fail = (
        test_active_qs.annotate(_latest_result_status=Subquery(latest_result_status))
        .filter(_latest_result_status="failed")
        .count()
    )

    risk_qs = Risk.objects.filter(workspace_id=workspace_id)
    risk_rows = list(risk_qs.values("id"))
    risk_states = state_reader.current_states("Risk", (r["id"] for r in risk_rows))
    risk_initial_state = state_reader.initial_state("Risk")
    resolved_risk_statuses = [
        risk_states.get(str(r["id"])) or risk_initial_state for r in risk_rows
    ]
    risk_open = resolved_risk_statuses.count(Risk.RiskStatus.IDENTIFIED)
    risk_mitigated = resolved_risk_statuses.count(Risk.RiskStatus.MITIGATED)
    risk_accepted = resolved_risk_statuses.count(Risk.RiskStatus.ACCEPTED)

    return {
        "requirements": {
            "active": req_active,
            "outdated": req_outdated,
            "total": req_active + req_outdated,
        },
        "architecture": {
            "active": arch_total - arch_outdated,
            "outdated": arch_outdated,
            "total": arch_total,
        },
        "tests": {
            "active": test_active,
            "pass": test_pass,
            "fail": test_fail,
            "outdated": test_outdated,
        },
        "risks": {
            "open": risk_open,
            "mitigated": risk_mitigated,
            "accepted": risk_accepted,
        },
    }


def entity_lists(
    *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
) -> Dict[str, Any]:
    """Return lightweight per-item lists for ``depth in ("normal", "full")``.

    Field-name notes (verified against ``persistence.models``):

    * ``ArchitectureElement`` has no ``name``/``type``/``status`` fields — it
      uses ``title``, ``element_type``, ``lifecycle_status``. The first two are
      aliased to the documented ``name``/``type`` keys via ``.values()``
      expression kwargs. ``status`` is derived from ``outdated_item_ids()``,
      *not* from the dead ``lifecycle_status`` column.
    * ``TestCase`` has no direct FK to ``Requirement``. The link is a TraceLink
      (source = TestCase artifact, target = Requirement artifact,
      ``link_type="verifies"``), resolved here via a correlated subquery
      through ``TraceLink.target__requirement__id``.

    Args:
        workspace_id:     Workspace to scope to.
        tenant_id:        Tenant whose context is activated for the queries.
        include_outdated: Include soft-deleted items in the lists.

    Returns:
        Mapping with ``requirements_list``/``architecture_list``/``tests_list``.
    """
    from persistence.models import (
        ArchitectureElement,
        Requirement,
        TestCase,
        TraceLink,
    )
    from traceability.types import LinkType
    from workflow import state_reader
    from workflow.services import outdated_item_ids

    _set_tenant(tenant_id)

    req_rows = list(
        Requirement.objects.filter(artifact__workspace_id=workspace_id).values(
            "id", "title", "level"
        )
    )
    req_states = state_reader.current_states("Requirement", (r["id"] for r in req_rows))
    # Task 12: the ``status`` column is dropped, so a row never wired into a
    # WorkflowItemState falls back to the "draft" preset initial state
    # instead (documented, reviewed data-loss tradeoff, see Task 12 report
    # Finding 2).
    requirement_initial_state = state_reader.initial_state("Requirement")
    requirements = []
    for row in req_rows:
        resolved = req_states.get(str(row["id"])) or requirement_initial_state
        if not include_outdated and resolved == "outdated":
            continue
        requirements.append({**row, "id": str(row["id"]), "status": resolved})

    arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
    arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
    if not include_outdated:
        arch_qs = arch_qs.exclude(id__in=arch_outdated_ids)
    architecture = [
        {
            # Issue #441: `item["id"]` is a UUID object here, not JSON
            # serializable. `arch_outdated_ids` membership must still be
            # checked against the raw UUID (before stringifying) — it is a
            # queryset of UUIDs, not strings.
            "id": str(item["id"]),
            "name": item["name"],
            "type": item["type"],
            "status": "outdated" if item["id"] in arch_outdated_ids else "active",
        }
        for item in arch_qs.values(
            "id",
            name=F("title"),
            type=F("element_type"),
        )
    ]

    linked_req_subquery = Subquery(
        TraceLink.objects.filter(
            source_id=OuterRef("artifact_id"),
            link_type=LinkType.VERIFIES.value,
            target__requirement__isnull=False,
        )
        .order_by("id")
        .values("target__requirement__id")[:1]
    )
    test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)
    test_rows = list(
        test_qs.annotate(linked_req_id=linked_req_subquery).values(
            "id", "title", "linked_req_id"
        )
    )
    test_states = state_reader.current_states("TestCase", (r["id"] for r in test_rows))
    # Task 12: the ``status`` column is dropped, so a row never wired into a
    # WorkflowItemState falls back to the testcase_default preset's initial
    # state instead (documented, reviewed data-loss tradeoff, see Task 12
    # report Finding 2).
    testcase_initial_state = state_reader.initial_state("TestCase")
    tests = []
    for row in test_rows:
        resolved = test_states.get(str(row["id"])) or testcase_initial_state
        if not include_outdated and resolved == "outdated":
            continue
        tests.append(
            {
                **row,
                "id": str(row["id"]),
                "status": resolved,
                "linked_req_id": str(row["linked_req_id"]) if row["linked_req_id"] else None,
            }
        )

    return {
        "requirements_list": requirements,
        "architecture_list": architecture,
        "tests_list": tests,
    }


def recent_changes(
    *, workspace_id: UUID, tenant_id: UUID, limit: int = 10
) -> List[Dict[str, Any]]:
    """Return the most recent workflow transitions across all item types.

    ``WorkflowHistoryEntry`` carries its own ``workspace_id`` column, so the
    entries are found without a per-entity-type join. Titles are resolved in a
    second, bulk step — one query per distinct entity type present in the
    result, not one per entry. Title resolution is best-effort: if it fails the
    entries are still returned, with the raw item id standing in for the title.

    Args:
        workspace_id: Workspace to scope to.
        tenant_id:    Tenant whose context is activated for the queries.
        limit:        Maximum number of entries, newest first.

    Returns:
        List of ``{entity_type, title, timestamp}`` dicts, newest first.
    """
    from workflow.models import WorkflowHistoryEntry

    _set_tenant(tenant_id)

    entries = list(
        WorkflowHistoryEntry.objects.filter(workspace_id=workspace_id)
        .select_related("item_state")
        .order_by("-transitioned_at")[:limit]
    )
    if not entries:
        return []

    ids_by_type: Dict[str, List[UUID]] = {}
    for entry in entries:
        ids_by_type.setdefault(entry.item_state.item_type, []).append(
            entry.item_state.item_id
        )

    title_lookup: Dict[Any, str] = {}
    try:
        from persistence.models import ArchitectureElement, Requirement, TestCase

        type_model_map = {
            "Requirement": Requirement,
            "ArchitectureElement": ArchitectureElement,
            "TestCase": TestCase,
        }
        for item_type, item_ids in ids_by_type.items():
            model = type_model_map.get(item_type)
            if model is None:
                continue
            title_lookup.update(
                dict(model.objects.filter(id__in=item_ids).values_list("id", "title"))
            )
    except Exception:
        logger.debug(
            "Could not resolve titles for recent_changes workspace=%s", workspace_id
        )

    return [
        {
            "entity_type": entry.item_state.item_type,
            "title": title_lookup.get(
                entry.item_state.item_id, str(entry.item_state.item_id)
            ),
            "timestamp": (
                entry.transitioned_at.isoformat() if entry.transitioned_at else None
            ),
        }
        for entry in entries
    ]


def get_workspace(*, workspace_id: UUID, tenant_id: UUID) -> Optional[Any]:
    """Return the ``Workspace`` row, or ``None`` if it does not exist.

    Used for the per-workspace ``ai_prompts["context_token_budgets"]`` override
    lookup. Returns the ORM object rather than a DTO because the caller reads a
    single JSON field off it; introducing a DTO here would be a behaviour
    change, not a refactor.

    Args:
        workspace_id: Workspace to load.
        tenant_id:    Tenant whose context is activated for the query.

    Returns:
        The ``Workspace`` instance, or ``None``.
    """
    from persistence.models import Workspace

    _set_tenant(tenant_id)
    return Workspace.objects.filter(id=workspace_id).first()


def get_tenant(*, tenant_id: UUID) -> Any:
    """Return the ``Tenant`` row for *tenant_id*.

    Thin identity lookup so REST views can resolve the ORM object needed for
    Layer-1 service calls (e.g. ``diagram.services``, ``icd.services``)
    without importing ``persistence.models`` directly, which would bypass
    ADR-01's Single-Entry-Point rule. Behaves exactly like the
    ``Tenant.objects.get(id=...)`` call it replaces: raises
    ``Tenant.DoesNotExist`` if the row is missing.

    Args:
        tenant_id: Tenant primary key.

    Returns:
        The ``Tenant`` instance.
    """
    from persistence.models import Tenant

    return Tenant.objects.get(id=tenant_id)


def get_user(*, user_id: Optional[UUID]) -> Optional[Any]:
    """Return the ``User`` row for *user_id*, or ``None``.

    Thin identity lookup, counterpart to :func:`get_tenant`. Mirrors the
    previous direct ``User.objects.filter(id=...).first()`` calls in REST
    views: a missing or absent user resolves to ``None`` rather than
    raising, since callers only use the result for optional audit fields
    (e.g. API-key-only contexts have no user).

    Args:
        user_id: User primary key, or ``None``.

    Returns:
        The ``User`` instance, or ``None``.
    """
    if user_id is None:
        return None

    from persistence.models import User

    return User.objects.filter(id=user_id).first()


__all__ = [
    "count_open_requirements",
    "entity_counts",
    "entity_lists",
    "get_tenant",
    "get_user",
    "get_workspace",
    "recent_changes",
]
