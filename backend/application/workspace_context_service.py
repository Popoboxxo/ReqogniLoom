"""Workspace-context read model (REQ-L2-MC-004, ADR-01 / issue #124).

``workspace.get_context`` answers "what does this workspace currently look
like?" for an AI agent: entity counts, lightweight per-entity lists and the
most recent workflow transitions. All of that is *read-only aggregation* — no
validation, no preset gate, no audit trail, no optimistic locking.

Historically the queries lived inline in ``mcp_server/tools/cross_cutting.py``,
which broke ADR-01's Single-Entry-Point rule: the MCP transport layer talked to
the ORM directly, so the same aggregation could not be reused by the REST layer
and was invisible to the architecture ratchet. This module is that code moved
down a layer, unchanged — same querysets, same field aliases, same
outdated-exclusion semantics, same return shapes.

Two different "outdated" exclusion mechanisms are in play, and both are
preserved verbatim because they are *not* interchangeable:

* ``Requirement`` and ``TestCase`` carry a denormalized ``status`` mirror
  column, so ``"outdated"`` is excluded with ``.exclude(status="outdated")``.
* ``ArchitectureElement`` does **not** — its ``lifecycle_status`` column is
  dead (``outdate()`` never writes it). The real state lives only in
  ``WorkflowItemState``, so it is resolved via
  ``workflow.services.outdated_item_ids()``.

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
    """Return the number of requirements that are not yet approved.

    "Open" means ``status != "approved"``. Soft-deleted (``"outdated"``)
    requirements are only counted when the caller explicitly asks for them
    (REQ-006).

    Args:
        workspace_id:     Workspace to scope to.
        tenant_id:        Tenant whose context is activated for the query.
        include_outdated: Count soft-deleted requirements as open too.

    Returns:
        The count of open requirements.
    """
    from persistence.models import Requirement

    _set_tenant(tenant_id)
    qs = Requirement.objects.filter(artifact__workspace_id=workspace_id).exclude(
        status="approved"
    )
    if not include_outdated:
        qs = qs.exclude(status="outdated")
    return qs.count()


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
    from workflow.services import outdated_item_ids

    _set_tenant(tenant_id)

    req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    req_outdated = req_qs.filter(status="outdated").count()
    req_active = req_qs.exclude(status="outdated").count()

    arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
    arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
    arch_total = arch_qs.count()
    arch_outdated = arch_qs.filter(id__in=arch_outdated_ids).count()

    test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)
    test_outdated = test_qs.filter(status="outdated").count()
    test_active_qs = test_qs.exclude(status="outdated")
    test_active = test_active_qs.count()
    # TestCase.status is the WorkflowEngine lifecycle mirror
    # (Draft/Ready/Approved/Deprecated/outdated) — it does NOT carry pass/fail
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
    risk_open = risk_qs.filter(status=Risk.RiskStatus.IDENTIFIED).count()
    risk_mitigated = risk_qs.filter(status=Risk.RiskStatus.MITIGATED).count()
    risk_accepted = risk_qs.filter(status=Risk.RiskStatus.ACCEPTED).count()

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
    from workflow.services import outdated_item_ids

    _set_tenant(tenant_id)

    req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    if not include_outdated:
        req_qs = req_qs.exclude(status="outdated")
    requirements = list(req_qs.values("id", "title", "status", "level"))

    arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
    arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
    if not include_outdated:
        arch_qs = arch_qs.exclude(id__in=arch_outdated_ids)
    architecture = [
        {
            "id": item["id"],
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
    if not include_outdated:
        test_qs = test_qs.exclude(status="outdated")
    tests = list(
        test_qs.annotate(linked_req_id=linked_req_subquery).values(
            "id", "title", "status", "linked_req_id"
        )
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


__all__ = [
    "count_open_requirements",
    "entity_counts",
    "entity_lists",
    "get_workspace",
    "recent_changes",
]
