"""Plan F F4.4 (PR-F11a) — additive baseline rollback (ADR-025).

This is the **service half** of the additive rollback: it reads a baseline,
computes what a rollback would change, opens a change request for it and
performs the restore. Transport (REST/MCP) is a separate PR — nothing here
knows about HTTP status codes beyond the ones the error classes advertise for
the later mapping.

Why additive
------------
``bl_baseline_snapshot`` / ``bl_delta_index_entry`` are immutable by database
trigger (``bl_raise_immutable``, see ADR-025 §2). A rollback therefore never
writes the baseline tables; it restores content by writing **new versions**
through the domain service of each artifact type. ``baseline_rollback_service``
is consequently a read-only consumer of ``baseline.models`` and
``baseline.state_capture``.

The rules implemented here are exactly ADR-025 R1–R9 (each helper names its
rule):

===========  ===========================================================
R1           additive only — no ``UPDATE``/``DELETE`` on ``bl_*``; every
             restore is a new version through the type's domain service
R2           a ``ChangeRequest`` in state ``approved`` for *this* baseline
             and workspace, with non-empty ``affected_items``
R3           plan binding — per item the current version must equal the
             ``version_before`` captured when the CR was created
R4           scope — only :data:`baseline.restorable_fields.RESTORABLE_FIELDS`;
             soft-deleted items via ``reactivate``; missing trace links
             recreated (system-owned types skipped and reported); workflow
             state / ``level`` / ``uid`` / uncaptured fields / artifacts
             created after the baseline are **not** restored
R5           one transaction, ``select_for_update`` on the CR row first,
             deterministic write order, ``expected_version`` on the closing
             transition
R6           the CR ends ``implemented`` and exactly **one** rollback-level
             audit entry is written
R7           item rights — hidden items are absent from the plan; ``apply``
             checks WRITE before the first write
R8           humans only — ``apply`` refuses agent principals
R9           ``MAX_ROLLBACK_ITEMS`` mass limit, synchronous, no worker
===========  ===========================================================

Known, deliberate limits (reported, never hidden)
-------------------------------------------------
* **Glossary terms are not rolled back.** A project/global baseline stores a
  glossary term under the delta-index id ``glossary_term`` → the *term* row id,
  while ``ChangeRequestService.set_affected_items`` accepts **Artifact** ids
  only and captures ``version_before`` from the artifact-backed ``item``
  snapshot — which carries no content and no ``version`` for a glossary hull.
  A term therefore cannot be bound to a CR with the current service contract,
  and R3 forbids restoring it unbound. ``preview`` reports such entries as
  ``unsupported`` so the gap is visible instead of silent; a follow-up has to
  either widen ``ChangeRequestAffectedItem`` to non-Artifact ids or capture
  ``Artifact.version`` for bare hulls.
* **Fields without a domain-service parameter are not restorable.** ADR-025
  R4 allows the ``RESTORABLE_FIELDS`` coverage to grow only with the services;
  ``level_source``, ``TestCase.origin``, ``TestCase.reviewed`` and
  ``Issue.assignee_id``/``assignee_changed_date`` are consequently declared
  ``NON_RESTORABLE`` in :mod:`baseline.restorable_fields` (each with its reason)
  instead of being written by a raw ``UPDATE``.
* ``acceptance_criteria_items`` is written through
  ``RequirementService.set_acceptance_criteria``, which audits but does **not**
  bump the row version (pre-existing behaviour of that setter), and the
  Artifact hull fields go through ``ArtifactAttributeGateway.write``, which
  also does not bump it. A rollback that changes *only* those fields therefore
  leaves the entity version unchanged — the write is still additive and
  audited, it just is not a new revision. Every content field goes through the
  updating domain service and does bump it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID

from django.db import transaction

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.change_request_service import ChangeRequestService
from auth_tenancy.context import AuthContext
from baseline.restorable_fields import RESTORABLE_FIELDS
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple

logger = logging.getLogger(__name__)

#: R9 — the mass limit for one rollback. ``request`` and ``apply`` both enforce
#: it; the execution stays synchronous on purpose (ADR-025 R9), so an oversized
#: project baseline needs several change requests instead of a background job.
MAX_ROLLBACK_ITEMS = 2000

#: The eight artifact types an additive rollback addresses (ADR-025 R4 /
#: F4.1). Keep in sync with ``baseline.restorable_fields.RESTORABLE_FIELDS`` —
#: the F4.1 meta-test asserts the two sets are equal.
SUPPORTED_ITEM_TYPES: frozenset[str] = frozenset(RESTORABLE_FIELDS)

#: Captured ``state["artifact_type"]`` label -> ADR item type. ``state_capture``
#: emits lower-case labels for the five ``persistence`` models and the raw
#: ``Artifact.artifact_type`` for Adr/Risk/Issue (see its module docstring), so
#: both spellings are mapped here. Sub-type tags (``Typ:Subtag``) are stripped
#: before matching.
_LABEL_TO_ITEM_TYPE: dict[str, str] = {
    "requirement": "Requirement",
    "stakeholder_need": "StakeholderNeed",
    "stakeholderneed": "StakeholderNeed",
    "architecture_element": "ArchitectureElement",
    "architectureelement": "ArchitectureElement",
    "test_case": "TestCase",
    "testcase": "TestCase",
    "glossary_term": "GlossaryTerm",
    "glossaryterm": "GlossaryTerm",
    "adr": "Adr",
    "risk": "Risk",
    "issue": "Issue",
}

#: Artifact hull keys restored through ``ArtifactAttributeGateway`` (R4). They
#: live on the shared Artifact row, not on the type's own table, so no domain
#: service parameter exists for them. ``custom_fields`` is deliberately absent:
#: every updating service accepts it directly.
_HULL_FIELDS: frozenset[str] = frozenset({"owner", "reporter", "priority", "stakeholder"})

#: ``Risk`` publishes its legacy free-text ``owner`` (``Risk.owner_name``) under
#: the snapshot key ``owner`` (WS7 #940), which shadows the hull Actor owner
#: (``state_capture`` merges the hull with ``setdefault``). For Risk the key is
#: therefore *not* a hull field — it is restored via ``update_risk(owner=…)``.
_HULL_FIELDS_WITHOUT_OWNER: frozenset[str] = _HULL_FIELDS - {"owner"}

#: Fields a service takes as a ``date`` that the snapshot holds as an ISO-8601
#: string (``state_capture`` serialises them for JSON round-tripping).
_DATE_FIELDS: dict[str, frozenset[str]] = {
    "Issue": frozenset({"due_date"}),
}

#: Content fields per type that the updating service accepts 1:1 by name.
_CONTENT_FIELDS: dict[str, frozenset[str]] = {
    "Requirement": frozenset(
        {
            "title",
            "description",
            "rationale",
            "source",
            "acceptance_criteria",
            "category",
            "type",
            "complexity_fibonacci",
            "verification_method",
        }
    ),
    "StakeholderNeed": frozenset({"title", "description", "category", "moscow_priority"}),
    "ArchitectureElement": frozenset(
        {"title", "description", "element_type", "parent_id", "asil_level", "make_or_buy"}
    ),
    "TestCase": frozenset({"title", "description", "steps", "test_type", "scenario_kind"}),
    "Adr": frozenset({"title", "description", "context", "decision", "consequences"}),
    "Risk": frozenset(
        {
            "title",
            "description",
            "category",
            "probability",
            "impact",
            "detection",
            "mitigation_strategy",
            "owner",
            "owner_user_id",
        }
    ),
    "Issue": frozenset(
        {"title", "description", "severity", "category", "due_date", "tags"}
    ),
    "GlossaryTerm": frozenset({"term", "definition", "synonyms", "abbreviation"}),
}


# ---------------------------------------------------------------------------
# Errors — stable codes + the HTTP status the later transport PR maps them to.
# ---------------------------------------------------------------------------


class RollbackError(Exception):
    """Base class for every baseline-rollback failure (ADR-025 „Fehlercodes").

    Each subclass carries a stable :attr:`code` (what the client branches on)
    and the :attr:`http_status` the REST layer will answer with. Subclasses
    that end in a 400 additionally inherit ``ValidationError`` so every
    existing ``except ValidationError`` caller keeps working unchanged.
    """

    code: str = "ROLLBACK_ERROR"
    http_status: int = 409

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details if details is not None else {}


class RollbackNotApprovedError(RollbackError):
    """R2/R5 — the change request is not in the ``approved`` state (409)."""

    code = "ROLLBACK_NOT_APPROVED"
    http_status = 409


class RollbackAlreadyAppliedError(RollbackError):
    """R5 — the change request already reached ``implemented`` (409)."""

    code = "ROLLBACK_ALREADY_APPLIED"
    http_status = 409


class RollbackPlanStaleError(RollbackError):
    """R3 — at least one item changed since the request was opened (409).

    ``details`` lists the affected items as
    ``{"item_id", "version_before", "current_version"}`` so the client can show
    exactly which items invalidated the plan.
    """

    code = "ROLLBACK_PLAN_STALE"
    http_status = 409


class RollbackEmptyError(RollbackError, ValidationError):
    """R2/R4 — the plan restores nothing at all (400).

    A change request that would do nothing must not exist; ``request`` answers
    with this instead of creating a pointless CCB item.
    """

    code = "ROLLBACK_EMPTY"
    http_status = 400


class RollbackTooLargeError(RollbackError, ValidationError):
    """R9 — more affected items than :data:`MAX_ROLLBACK_ITEMS` (400)."""

    code = "ROLLBACK_TOO_LARGE"
    http_status = 400


class RollbackForbiddenError(RollbackError, PermissionDeniedError):
    """R7/R8 — item-level WRITE missing, or an agent principal (403).

    ``details`` for R7 is ``{"readable_item_ids": [...], "denied_count": n}``
    (only the ids the caller may read — R7 forbids disclosing the rest); for R8
    it is ``{"actor_type": "agent"}``.
    """

    code = "PERMISSION_DENIED"
    http_status = 403


# ---------------------------------------------------------------------------
# Public value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackItem:
    """One baseline member as the rollback sees it.

    Attributes:
        item_id: Delta-index id of the member — the **Artifact** UUID for
            artifact-backed items, the term row id for a ``glossary_term``
            entry (documented as such by ``baseline.state_capture``).
        artifact_type: Canonical ADR item type (``"Requirement"``, …) or
            ``""`` when the entry carries no supported type.
        action: What a rollback would do:
            ``restore`` (content/hull fields differ), ``reactivate`` (the item
            is soft-deleted and will be restored to active), ``unchanged``,
            ``unsupported`` (no domain service path — see the module docstring)
            or ``created_since`` (artifact created after the baseline; ENT-F6 =
            a: untouched).
        field_changes: ``{field: {"current": v, "baseline": v}}`` for every
            restorable field whose value differs.
        unrestorable_fields: Restorable fields the (possibly older) snapshot
            does not carry. Reported, never guessed (ADR-025 R4).
        current_version: The entity's current optimistic-lock version, or
            ``None`` when the entity row is gone.
    """

    item_id: str
    artifact_type: str
    action: Literal["restore", "reactivate", "unchanged", "unsupported", "created_since"]
    field_changes: dict[str, dict[str, Any]]
    unrestorable_fields: list[str]
    current_version: int | None


@dataclass(frozen=True)
class RollbackPlan:
    """The complete, read-only result of :meth:`BaselineRollbackService.preview`.

    Attributes:
        baseline_id: The baseline the plan was computed against.
        items: One :class:`RollbackItem` per visible baseline member (plus the
            ``created_since`` artifacts), sorted by ``item_id``.
        links_to_recreate: Baseline trace links that no longer exist and may be
            recreated — ``{"source_id", "target_id", "link_type"}``.
        skipped_links: Missing links that will **not** be recreated, each with
            an extra ``reason`` key (system-owned / unknown type / no snapshot).
        baseline_name: Convenience copy of the baseline name (change-reason
            text, REST label).
        workspace_id: The baseline's workspace (R2 scope check).
    """

    baseline_id: UUID
    items: list[RollbackItem]
    links_to_recreate: list[dict[str, str]]
    skipped_links: list[dict[str, str]]
    baseline_name: str = ""
    workspace_id: UUID | None = None

    @property
    def summary(self) -> dict[str, int]:
        """Counts per action plus the link totals (REST ``summary`` payload)."""
        counts = {
            "restore": 0,
            "reactivate": 0,
            "unchanged": 0,
            "unsupported": 0,
            "created_since": 0,
        }
        for item in self.items:
            counts[item.action] += 1
        counts["links_to_recreate"] = len(self.links_to_recreate)
        counts["skipped_links"] = len(self.skipped_links)
        return counts

    @property
    def restorable_item_ids(self) -> list[str]:
        """Ids a rollback would actually write (R2/R9 affected-item set)."""
        return [
            item.item_id
            for item in self.items
            if item.action in ("restore", "reactivate")
        ]


@dataclass(frozen=True)
class RollbackResult:
    """The outcome of :meth:`BaselineRollbackService.apply`.

    Attributes:
        restored: Items written through their content service (R4).
        reactivated: Soft-deleted items set back to active (R4).
        links_recreated: Missing baseline trace links re-inserted (R4).
        skipped: Everything the run deliberately did not write, as
            ``{"kind": "item"|"link"|"hull_fields", …, "reason": …}``.
        change_request_status: The CR's state after the run (``implemented``).
    """

    restored: int
    reactivated: int
    links_recreated: int
    skipped: list[dict[str, Any]]
    change_request_status: str


@dataclass
class _Member:
    """Internal analysis of one delta-index entry (not part of the contract)."""

    item_id: str
    item_type: str
    baseline_state: dict[str, Any]
    current_state: dict[str, Any] | None
    current_version: int | None
    lifecycle_status: str
    field_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    unrestorable_fields: list[str] = field(default_factory=list)
    #: Canonical entity row id (``Requirement.id`` etc.) — ``apply`` only.
    entity_id: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BaselineRollbackService(ServiceBase):
    """Additive baseline rollback (ADR-025, Plan F F4.4 / PR-F11a).

    Usage::

        svc = BaselineRollbackService()
        plan = svc.preview(baseline_id, ctx)            # read-only
        cr = svc.request(baseline_id, ctx, change_reason="…")
        # … CCB approves the CR …
        result = svc.apply(baseline_id, cr.id, ctx)      # humans only
    """

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def preview(self, baseline_id: UUID, ctx: AuthContext) -> RollbackPlan:
        """Compute what a rollback to *baseline_id* would change (R4/R7).

        Read-only: nothing is written and no change request is needed, so an
        agent principal may call it (R8).

        R7: items on which the caller has no *read* right are absent from
        ``items``, from every count of :attr:`RollbackPlan.summary` and from
        both link lists — a hidden item must not leak even as a count.
        """
        self._set_tenant_context(ctx)

        detail = self._load_baseline(baseline_id, ctx)
        item_entries = [e for e in detail.entries if e.entity_type == "item"]
        term_entries = [e for e in detail.entries if e.entity_type == "glossary_term"]
        link_entries = [e for e in detail.entries if e.entity_type == "trace_link"]

        # Permission lookups need the Artifact id of every candidate. Glossary
        # terms are addressed by their *term* id in the delta index, so resolve
        # the backing Artifact first (R7 asks about artifacts).
        term_artifact = self._glossary_artifact_ids(term_entries, ctx)
        created_since = self._created_since_artifacts(detail, ctx)

        read_checked: set[str] = {e.item_id for e in item_entries}
        read_checked |= {artifact_id for artifact_id in term_artifact.values() if artifact_id}
        for link in link_entries:
            state = link.state or {}
            if state.get("source_id"):
                read_checked.add(str(state["source_id"]))
            if state.get("target_id"):
                read_checked.add(str(state["target_id"]))
        read_checked |= set(created_since)
        readable = self._readable_ids(read_checked, detail.workspace_id, ctx)

        items: list[RollbackItem] = []
        # One batched capture for every member (constant query count, no N+1).
        current_states = self._capture_current(item_entries + term_entries, ctx)
        for entry in item_entries:
            if entry.item_id not in readable:
                continue
            member = self._analyse(entry, current_states.get(entry.item_id))
            items.append(self._to_item(member))

        # A glossary term is reported (never silently dropped) but cannot be
        # restored — see the module docstring's "Known, deliberate limits".
        for entry in term_entries:
            if term_artifact.get(entry.item_id) not in readable:
                continue
            member = self._analyse(entry, current_states.get(entry.item_id))
            items.append(self._to_item(member))

        for artifact_id, raw_type in created_since.items():
            if artifact_id not in readable:
                continue
            items.append(
                RollbackItem(
                    item_id=artifact_id,
                    artifact_type=self._canonical_type(raw_type) or "",
                    action="created_since",
                    field_changes={},
                    unrestorable_fields=[],
                    current_version=None,
                )
            )

        items.sort(key=lambda item: item.item_id)
        links_to_recreate, skipped_links = self._analyse_links(
            link_entries, detail.workspace_id, readable, ctx
        )

        return RollbackPlan(
            baseline_id=detail.baseline_id,
            items=items,
            links_to_recreate=links_to_recreate,
            skipped_links=skipped_links,
            baseline_name=detail.name,
            workspace_id=detail.workspace_id,
        )

    # ------------------------------------------------------------------
    # request
    # ------------------------------------------------------------------

    def request(
        self,
        baseline_id: UUID,
        ctx: AuthContext,
        *,
        title: str | None = None,
        change_reason: str,
    ) -> Any:
        """Open the change request a rollback has to pass through (R2/R9).

        Only existing service methods are used:
        ``create_change_request`` → ``set_affected_items`` → ``link_baseline``.
        ``set_affected_items`` is what records ``version_before`` /
        ``state_before`` per item (``ChangeRequestService._replace_affected_items``
        → ``_capture_states`` → ``baseline.state_capture.capture_states``); the
        same helper also runs inside ``create_change_request`` when
        ``affected_item_ids`` is passed, so both paths record it — this one is
        used because it keeps the "which items does the plan restore" decision
        next to the plan itself.

        R8: allowed for agent principals — the CR is created in ``draft`` and
        the approval stays in the CCB.

        Raises:
            RollbackEmptyError: R2/R4 — nothing would be restored.
            RollbackTooLargeError: R9 — more affected items than the limit.
            ValidationError: ``change_reason`` missing.
        """
        self._set_tenant_context(ctx)

        if not change_reason or not str(change_reason).strip():
            raise ValidationError("change_reason is required to open a rollback")

        plan = self.preview(baseline_id, ctx)
        item_ids = plan.restorable_item_ids
        if not item_ids:
            # R4: a plan whose only work is a missing trace link is *not* empty
            # („kein restorable Item, keine Reaktivierung, kein nachzuziehender
            # Link"). R2 still demands a non-empty affected-item set, so a
            # link-only rollback binds to the link endpoints — the artifacts the
            # change actually touches.
            item_ids = sorted(
                {link["source_id"] for link in plan.links_to_recreate}
                | {link["target_id"] for link in plan.links_to_recreate}
            )
        if not item_ids:
            raise RollbackEmptyError(
                "Nothing to roll back: the plan contains no restorable or "
                "reactivatable item and no missing trace link.",
                details={"summary": plan.summary},
            )
        if len(item_ids) > MAX_ROLLBACK_ITEMS:
            raise RollbackTooLargeError(
                f"Rollback covers {len(item_ids)} items; at most "
                f"{MAX_ROLLBACK_ITEMS} are allowed per change request.",
                details={"count": len(item_ids), "max": MAX_ROLLBACK_ITEMS},
            )

        summary = plan.summary
        description = (
            f"Additive rollback to baseline '{plan.baseline_name}' "
            f"({baseline_id}).\n\n"
            f"Restore: {summary['restore']}, reactivate: "
            f"{summary['reactivate']}, unchanged: {summary['unchanged']}, "
            f"unsupported: {summary['unsupported']}, created since baseline: "
            f"{summary['created_since']}, trace links to recreate: "
            f"{summary['links_to_recreate']}."
        )
        cr_title = title or f"Rollback to baseline '{plan.baseline_name}'"[:255]

        service = ChangeRequestService()
        cr = service.create_change_request(
            workspace_id=plan.workspace_id,
            title=cr_title,
            ctx=ctx,
            description=description,
            impact_assessment=description,
            change_reason=change_reason,
        )
        service.set_affected_items(cr_id=cr.id, item_ids=item_ids, ctx=ctx)
        service.link_baseline(cr_id=cr.id, ctx=ctx, baseline_id=plan.baseline_id)
        return cr

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------

    def apply(
        self,
        baseline_id: UUID,
        change_request_id: UUID,
        ctx: AuthContext,
    ) -> RollbackResult:
        """Execute an approved rollback plan (R1–R9).

        Runs in **one** ``transaction.atomic()`` block:

        1. R8 — an agent principal is refused before any database work.
        2. R5 — ``select_for_update()`` on the change-request row; the

           status/version are read *after* the lock is held, from
           ``WorkflowItemState`` (the CR's status does not live on its own row).
        3. R2 — the CR must be ``approved``, linked to *this* baseline, in the
           baseline's workspace, with non-empty ``affected_items``.
        4. R9 — the affected-item count.
        5. R7 — WRITE per artifact the run will touch, before the first write.
        6. R3 — per item ``current_version == version_before``.
        7. Writes in ``item_id`` order (R1/R4), then missing trace links.
        8. ``transition_status(..., "implemented", expected_version=<locked
           version>)`` in the same transaction (R5) and one audit entry (R6).

        Any failure rolls the whole transaction back: nothing is written and
        the CR stays ``approved``. Rejected attempts log a WARNING with the CR
        id, the acting user and the error code (R6).
        """
        if getattr(ctx, "actor_type", "user") != "user":
            self._log_rejection("apply", change_request_id, ctx, RollbackForbiddenError)
            raise RollbackForbiddenError(
                "Baseline rollback is a human-only operation; agent principals "
                "may preview and open the change request, not execute it.",
                details={"actor_type": ctx.actor_type},
            )

        self._set_tenant_context(ctx)

        try:
            with transaction.atomic():
                return self._apply_locked(baseline_id, change_request_id, ctx)
        except Exception as exc:
            # R6: every refused attempt leaves a WARNING with CR id, user and
            # error code. Deliberately broad — an OptimisticLockError from a
            # concurrent CCB decision (R5 step 4) and a plain ValidationError
            # from the R2 scope check are refusals too, not just RollbackError.
            self._log_rejection("apply", change_request_id, ctx, type(exc))
            raise

    # ------------------------------------------------------------------
    # apply — the locked body
    # ------------------------------------------------------------------

    def _apply_locked(
        self, baseline_id: UUID, change_request_id: UUID, ctx: AuthContext
    ) -> RollbackResult:
        from application.models import ChangeRequest
        from persistence.models import ChangeRequestAffectedItem

        # R5 step 1 — the row lock. A second, parallel apply on the same CR
        # waits here and then observes the committed ``implemented`` state.
        cr = (
            ChangeRequest.objects.select_for_update()
            .filter(id=change_request_id, tenant_id=ctx.tenant_id)
            .first()
        )
        if cr is None:
            raise NotFoundError(f"ChangeRequest {change_request_id} not found")

        # R5 step 2 — read status + revision AFTER the lock.
        status, wf_version = self._cr_status_and_version(cr.id)
        if status == "implemented":
            raise RollbackAlreadyAppliedError(
                "This change request has already been implemented.",
                details={"change_request_id": str(cr.id), "status": status},
            )
        if status != "approved":
            raise RollbackNotApprovedError(
                "Baseline rollback requires an approved change request.",
                details={"change_request_id": str(cr.id), "status": status},
            )

        detail = self._load_baseline(baseline_id, ctx)

        # R2 — the CR must be bound to *this* baseline and workspace.
        if cr.baseline_id is None or str(cr.baseline_id) != str(detail.baseline_id):
            raise ValidationError(
                "Change request is not linked to the baseline being rolled back "
                f"({detail.baseline_id})."
            )
        if str(cr.workspace_id) != str(detail.workspace_id):
            raise ValidationError(
                "Change request belongs to a different workspace than the baseline."
            )

        rows = list(
            ChangeRequestAffectedItem.objects.filter(
                change_request_id=cr.id, tenant_id=ctx.tenant_id
            ).order_by("item_id")
        )
        if not rows:
            raise ValidationError(
                "Change request has no affected items; a rollback without a "
                "recorded impact set is not executable."
            )

        # R9 — mass limit, checked before any permission/diff work.
        if len(rows) > MAX_ROLLBACK_ITEMS:
            raise RollbackTooLargeError(
                f"Rollback covers {len(rows)} items; at most "
                f"{MAX_ROLLBACK_ITEMS} are allowed.",
                details={"count": len(rows), "max": MAX_ROLLBACK_ITEMS},
            )

        by_item_id = {str(entry.item_id): entry for entry in detail.entries}
        affected_entries = [
            by_item_id[str(row.item_id)]
            for row in rows
            if str(row.item_id) in by_item_id
            and by_item_id[str(row.item_id)].entity_type == "item"
        ]
        members = self._analyse_affected(
            rows, by_item_id, self._capture_current(affected_entries, ctx), ctx
        )

        link_entries = [e for e in detail.entries if e.entity_type == "trace_link"]
        link_endpoints: set[str] = set()
        for entry in link_entries:
            state = entry.state or {}
            if state.get("source_id"):
                link_endpoints.add(str(state["source_id"]))
            if state.get("target_id"):
                link_endpoints.add(str(state["target_id"]))
        links_to_recreate, skipped_links = self._analyse_links(
            link_entries,
            detail.workspace_id,
            self._readable_ids(link_endpoints, detail.workspace_id, ctx),
            ctx,
        )

        # R7 — one WRITE check for every artifact this run will write to
        # (affected items *and* link endpoints), before the first write.
        write_ids = {m.item_id for m in members if m.item_type}
        for link in links_to_recreate:
            write_ids.add(link["source_id"])
            write_ids.add(link["target_id"])
        self._assert_write_access(write_ids, detail.workspace_id, ctx)

        # R3 — plan binding against the ``version_before`` captured at request.
        stale = self._stale_items(rows, members)
        if stale:
            raise RollbackPlanStaleError(
                "Items changed since the change request was opened; create a "
                "new request.",
                details=stale,
            )

        change_reason = (
            f"Rollback to baseline '{detail.name}' (CR {cr.id})"
        )

        restored = 0
        reactivated = 0
        skipped: list[dict[str, Any]] = list(skipped_links)

        for member in sorted(members, key=lambda m: m.item_id):
            if not member.item_type:
                skipped.append(
                    {
                        "kind": "item",
                        "item_id": member.item_id,
                        "reason": "unsupported_type",
                    }
                )
                continue
            if member.item_type == "GlossaryTerm":
                # Cannot be bound to a CR affected item — see module docstring.
                skipped.append(
                    {
                        "kind": "item",
                        "item_id": member.item_id,
                        "reason": "glossary_term_not_bindable",
                    }
                )
                continue

            was_reactivated = self._reactivate_if_outdated(member, ctx)
            if was_reactivated:
                reactivated += 1

            written, hull_skipped = self._restore_item(member, ctx, change_reason)
            if written:
                restored += 1
            skipped.extend(hull_skipped)

        links_recreated = self._recreate_links(links_to_recreate, ctx)

        # R5 step 4 + R6 — the closing transition carries the revision read
        # under the lock; a concurrent CCB decision makes it fail (409).
        ChangeRequestService().transition_status(
            cr_id=cr.id,
            target_status="implemented",
            ctx=ctx,
            change_reason=change_reason,
            expected_version=wf_version,
        )

        # R6 — exactly ONE rollback-level audit entry, in this transaction.
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Baseline",
            entity_id=detail.baseline_id,
            change_reason=change_reason,
            details={
                "rollback_change_request": str(cr.id),
                "restored": restored,
                "reactivated": reactivated,
                "links_recreated": links_recreated,
                "actor_type": "user",
            },
        )

        return RollbackResult(
            restored=restored,
            reactivated=reactivated,
            links_recreated=links_recreated,
            skipped=skipped,
            change_request_status="implemented",
        )

    # ------------------------------------------------------------------
    # Baseline access (R1: read-only)
    # ------------------------------------------------------------------

    def _load_baseline(self, baseline_id: UUID, ctx: AuthContext):
        """Read the baseline header + delta entries (SELECT only — R1)."""
        from application.baseline_facade import BaselineFacade

        return BaselineFacade().get_baseline(baseline_id, ctx)

    def _glossary_artifact_ids(self, entries, ctx: AuthContext) -> dict[str, str]:
        """``term_id -> backing Artifact id`` for the delta's glossary entries."""
        term_ids = [e.item_id for e in entries]
        if not term_ids:
            return {}

        from persistence.models import GlossaryTerm

        return {
            str(term_id): str(artifact_id)
            for term_id, artifact_id in GlossaryTerm.unscoped.filter(
                id__in=term_ids, tenant_id=ctx.tenant_id
            ).values_list("id", "artifact_id")
            if artifact_id is not None
        }

    def _created_since_artifacts(self, detail, ctx: AuthContext) -> dict[str, str]:
        """Artifacts of the workspace created after the baseline (R4/ENT-F6 = a).

        They are reported as ``created_since`` and never touched: a rollback
        produces an additively cleaned state, not a historical one. Only the
        header (id + type) is needed, in one query.
        """
        from persistence.models import Artifact

        baseline_ids = {e.item_id for e in detail.entries}
        rows = Artifact.unscoped.filter(
            workspace_id=detail.workspace_id,
            tenant_id=ctx.tenant_id,
            created_at__gt=detail.created_at,
        ).values_list("id", "artifact_type")
        return {
            str(artifact_id): raw_type
            for artifact_id, raw_type in rows
            if str(artifact_id) not in baseline_ids
        }

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyse(self, entry, current: dict[str, Any] | None) -> _Member:
        """Build the internal analysis for one delta-index entry.

        *current* is the entry's batched current-state capture
        (:meth:`_capture_current`), or ``None`` when the entity row is gone.
        """
        baseline_state = entry.state or {}
        item_type = self._type_for_entry(entry, baseline_state)

        if entry.entity_type == "glossary_term":
            # Reported but not restorable (see module docstring).
            return _Member(
                item_id=entry.item_id,
                item_type=item_type,
                baseline_state=baseline_state,
                current_state=None,
                current_version=baseline_state.get("version"),
                lifecycle_status=baseline_state.get("lifecycle_status", "active"),
                field_changes={},
                unrestorable_fields=list(RESTORABLE_FIELDS.get(item_type, ())),
            )

        member = _Member(
            item_id=entry.item_id,
            item_type=item_type,
            baseline_state=baseline_state,
            current_state=current,
            current_version=(current or {}).get("version"),
            lifecycle_status=(current or {}).get("lifecycle_status", "active"),
        )
        if item_type and current is not None:
            member.field_changes, member.unrestorable_fields = self._diff_fields(
                item_type, baseline_state, current
            )
        elif item_type:
            member.unrestorable_fields = list(RESTORABLE_FIELDS[item_type])
        return member

    @staticmethod
    def _capture_current(entries, ctx: AuthContext) -> dict[str, dict[str, Any]]:
        """One batched current-state capture for every delta-index entry.

        Uses the same curated field set as a baseline snapshot
        (``baseline.state_capture``), so "what would change" is answered in
        exactly the vocabulary the snapshot uses — and the same helper the
        change request uses to record ``state_before``.
        """
        tuples = [
            DeltaIndexTuple(item_id=e.item_id, version=0, entity_type=e.entity_type)
            for e in entries
        ]
        if not tuples:
            return {}
        return capture_states(tuples, ctx.tenant_id)

    def _analyse_affected(
        self,
        rows,
        by_item_id,
        current_states: dict[str, dict[str, Any]],
        ctx: AuthContext,
    ) -> list[_Member]:
        """Analyse the CR's affected items against the baseline (apply side).

        Resolves the canonical entity row id per member — the updating services
        are addressed by the *entity* id, not by the Artifact id.
        """
        members: list[_Member] = []
        for row in rows:
            item_id = str(row.item_id)
            entry = by_item_id.get(item_id)
            if entry is None or entry.entity_type != "item":
                members.append(
                    _Member(
                        item_id=item_id,
                        item_type="",
                        baseline_state={},
                        current_state=None,
                        current_version=None,
                        lifecycle_status="active",
                        unrestorable_fields=["not_in_baseline"],
                    )
                )
                continue
            members.append(self._analyse(entry, current_states.get(item_id)))

        entity_ids = self._resolve_entity_ids(
            {m.item_id for m in members if m.item_type}, ctx
        )
        for member in members:
            resolved = entity_ids.get(member.item_id)
            if resolved is not None:
                member.entity_id = resolved[0]
            elif member.item_type:
                member.item_type = ""  # entity row gone -> nothing to write
        return members

    def _resolve_entity_ids(
        self, artifact_ids: set[str], ctx: AuthContext
    ) -> dict[str, tuple[str, int]]:
        """``artifact_id -> (entity row id, entity version)`` in 8 batched queries.

        Constant in the number of items (one query per artifact-backed ADR
        type), mirroring ``baseline.state_capture``'s batching discipline. All
        eight models live in ``persistence`` (Datenmodell-Konsolidierung Phase
        2), so this is a plain downward import — no registry indirection needed.
        """
        if not artifact_ids:
            return {}

        from persistence.models import (
            Adr,
            ArchitectureElement,
            GlossaryTerm,
            Issue,
            Requirement,
            Risk,
            StakeholderNeed,
            TestCase,
        )

        models = {
            "Requirement": Requirement,
            "StakeholderNeed": StakeholderNeed,
            "ArchitectureElement": ArchitectureElement,
            "TestCase": TestCase,
            "GlossaryTerm": GlossaryTerm,
            "Adr": Adr,
            "Risk": Risk,
            "Issue": Issue,
        }
        ids = list(artifact_ids)
        resolved: dict[str, tuple[str, int]] = {}
        for model in models.values():
            for artifact_id, entity_id, version in model.unscoped.filter(
                artifact_id__in=ids,
                tenant_id=ctx.tenant_id,
            ).values_list("artifact_id", "id", "version"):
                resolved[str(artifact_id)] = (str(entity_id), int(version))
        return resolved

    def _diff_fields(
        self, item_type: str, baseline_state: dict[str, Any], current_state: dict[str, Any]
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """Field-level diff over ``RESTORABLE_FIELDS`` (R4).

        A field the snapshot does not carry is *unrestorable*, not "unchanged":
        reporting it is the difference between an honest partial restore and a
        rollback that silently guesses.
        """
        changed: dict[str, dict[str, Any]] = {}
        unrestorable: list[str] = []
        for name in RESTORABLE_FIELDS.get(item_type, ()):
            if name not in baseline_state:
                if name not in unrestorable:
                    unrestorable.append(name)
                continue
            baseline_value = baseline_state[name]
            current_value = current_state.get(name)
            if not self._values_equal(baseline_value, current_value):
                changed[name] = {"current": current_value, "baseline": baseline_value}
        return changed, unrestorable

    @staticmethod
    def _values_equal(left: Any, right: Any) -> bool:
        """JSON-safe equality for snapshot values.

        ``state_capture`` serialises every value to a JSON-compatible shape, so
        a plain ``==`` is enough; the only wrinkle is ``None`` vs an empty
        collection, which the capture normalises already. Kept as one seam so a
        future normalisation rule has a single place to live.
        """
        return left == right

    def _to_item(self, member: _Member) -> RollbackItem:
        """Project the internal analysis onto the public dataclass (R4)."""
        unsupported = member.item_id and (
            not member.item_type
            or member.item_type == "GlossaryTerm"
            or member.current_state is None
            or not member.baseline_state
        )
        if unsupported:
            action: str = "unsupported"
        elif member.lifecycle_status == "outdated":
            action = "reactivate"
        elif member.field_changes:
            action = "restore"
        else:
            action = "unchanged"

        return RollbackItem(
            item_id=member.item_id,
            artifact_type=member.item_type,
            action=action,  # type: ignore[arg-type]
            field_changes=member.field_changes,
            unrestorable_fields=member.unrestorable_fields,
            current_version=member.current_version,
        )

    @staticmethod
    def _canonical_type(raw: str | None) -> str:
        """Map a captured/raw ``Artifact.artifact_type`` to the ADR item type."""
        if not raw:
            return ""
        base = str(raw).split(":", 1)[0].strip()
        return _LABEL_TO_ITEM_TYPE.get(base.lower(), "")

    def _type_for_entry(self, entry, baseline_state: dict[str, Any]) -> str:
        """Resolve the canonical item type of a delta-index entry."""
        if entry.entity_type == "glossary_term":
            return "GlossaryTerm"
        return self._canonical_type(baseline_state.get("artifact_type"))

    # ------------------------------------------------------------------
    # Links (R4)
    # ------------------------------------------------------------------

    def _analyse_links(
        self,
        link_entries,
        workspace_id: UUID,
        readable: set[str],
        ctx: AuthContext,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Split the baseline's trace links into recreate / skipped (R4/R7).

        A link is *missing* when no ``TraceLink`` with the same
        ``(source, target, link_type)`` exists any more. System-owned types
        (``diagram-ref``) and unknown/inactive types are never re-created by a
        manual path (``TraceLinkService.create_trace_link`` would reject them),
        so they are reported instead. R7: a link with an endpoint the caller
        cannot read is dropped entirely — not even counted.
        """
        if not link_entries:
            return [], []

        from link_types.catalog import get_definition
        from persistence.models import TraceLink

        states = [e.state or {} for e in link_entries]
        sources = {s["source_id"] for s in states if s.get("source_id")}
        targets = {t["target_id"] for t in states if t.get("target_id")}

        existing: set[tuple[str, str, str]] = set()
        if sources and targets:
            existing = {
                (str(source), str(target), str(link_type))
                for source, target, link_type in TraceLink.unscoped.filter(
                    tenant_id=ctx.tenant_id,
                    source_id__in=sources,
                    target_id__in=targets,
                ).values_list("source_id", "target_id", "link_type")
            }

        recreate: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        for state in states:
            source_id = state.get("source_id")
            target_id = state.get("target_id")
            link_type = state.get("link_type")
            if not (source_id and target_id and link_type):
                skipped.append(
                    {
                        "source_id": str(source_id or ""),
                        "target_id": str(target_id or ""),
                        "link_type": str(link_type or ""),
                        "reason": "no_snapshot",
                    }
                )
                continue
            entry = {
                "source_id": str(source_id),
                "target_id": str(target_id),
                "link_type": str(link_type),
            }
            if (entry["source_id"], entry["target_id"], entry["link_type"]) in existing:
                continue
            # R7 — an endpoint the caller cannot read is invisible, link and all.
            if entry["source_id"] not in readable or entry["target_id"] not in readable:
                continue
            definition = get_definition(workspace_id, entry["link_type"])
            if definition is None:
                skipped.append({**entry, "reason": "unknown_link_type"})
                continue
            if definition.get("system_owned") or not definition.get(
                "manual_creatable", True
            ):
                skipped.append({**entry, "reason": "system_owned"})
                continue
            recreate.append(entry)
        return recreate, skipped

    def _recreate_links(self, links: list[dict[str, str]], ctx: AuthContext) -> int:
        """Re-insert the missing links through the manual service path (R1/R4)."""
        if not links:
            return 0

        from application.trace_link_service import TraceLinkService

        service = TraceLinkService()
        for link in sorted(
            links, key=lambda item: (item["source_id"], item["target_id"], item["link_type"])
        ):
            service.create_trace_link(
                UUID(link["source_id"]),
                UUID(link["target_id"]),
                link["link_type"],
                ctx,
                rationale="Restored by additive baseline rollback",
            )
        return len(links)

    # ------------------------------------------------------------------
    # Writes (R1/R4)
    # ------------------------------------------------------------------

    def _reactivate_if_outdated(self, member: _Member, ctx: AuthContext) -> bool:
        """Soft-deleted item -> active via ``WorkflowFacade.reactivate`` (R4)."""
        if member.lifecycle_status != "outdated" or not member.entity_id:
            return False

        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().reactivate(
            member.entity_id,
            ctx,
            item_type=member.item_type,
            workspace_id=self._member_workspace_id(member, ctx),
        )
        return True

    def _restore_item(
        self, member: _Member, ctx: AuthContext, change_reason: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Write one item's restorable fields through its domain service (R1/R4).

        Returns ``(content_written, skipped)``. Only fields whose value actually
        differs are passed, so an unchanged field can never cause a phantom
        version bump or trip a service-level validation (e.g. a title shorter
        than the type's minimum) for a value the snapshot already holds.
        """
        if not member.field_changes or not member.entity_id:
            return False, []

        item_type = member.item_type
        content_names = _CONTENT_FIELDS.get(item_type, frozenset())
        hull_names = (
            _HULL_FIELDS_WITHOUT_OWNER if item_type == "Risk" else _HULL_FIELDS
        )

        kwargs: dict[str, Any] = {}
        hull: dict[str, Any] = {}
        criteria_items: list | None = None
        for name, change in member.field_changes.items():
            if name in hull_names:
                hull[name] = change["baseline"]
            elif name == "acceptance_criteria_items" and item_type == "Requirement":
                criteria_items = change["baseline"]
            elif name == "custom_fields":
                kwargs["custom_fields"] = change["baseline"]
            elif name in content_names:
                kwargs[name] = self._coerce(item_type, name, change["baseline"])

        written = self._call_update_service(
            item_type, member, kwargs, ctx, change_reason
        )

        if criteria_items is not None:
            from application.requirement_service import RequirementService

            RequirementService().set_acceptance_criteria(
                UUID(member.entity_id),
                ctx,
                criteria_items or [],
                change_reason=change_reason,
            )
            written = True

        skipped: list[dict[str, Any]] = []
        if hull:
            hull_skipped = self._write_hull_fields(
                item_type, member, hull, ctx, skipped
            )
            written = written or hull_skipped
        return written, skipped

    def _call_update_service(
        self,
        item_type: str,
        member: _Member,
        kwargs: dict[str, Any],
        ctx: AuthContext,
        change_reason: str,
    ) -> bool:
        """Dispatch one item's content write to its type's service (R1)."""
        if not kwargs:
            return False

        entity_id = UUID(member.entity_id)
        expected_version = member.current_version

        if item_type == "Requirement":
            from application.requirement_service import RequirementService

            RequirementService().update_requirement(
                entity_id,
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "StakeholderNeed":
            from application.stakeholder_need_service import StakeholderNeedService

            StakeholderNeedService().update(
                ctx,
                entity_id,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "ArchitectureElement":
            # update_architecture_element takes no change_reason (pre-existing).
            from application.architecture_service import ArchitectureService

            ArchitectureService().update_architecture_element(
                entity_id,
                ctx,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "TestCase":
            from application.test_service import TestService

            TestService().update_test_case(
                entity_id,
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "Adr":
            from application.adr_service import AdrService

            AdrService().update_adr(
                entity_id,
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "Risk":
            from application.risk_service import RiskService

            RiskService().update_risk(
                entity_id,
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        elif item_type == "Issue":
            from application.issue_service import IssueService

            IssueService().update_issue(
                entity_id,
                ctx,
                change_reason=change_reason,
                expected_version=expected_version,
                **kwargs,
            )
        else:  # pragma: no cover - guarded by the caller (unsupported types)
            raise ValidationError(f"Rollback does not support '{item_type}'")
        return True

    def _write_hull_fields(
        self,
        item_type: str,
        member: _Member,
        hull: dict[str, Any],
        ctx: AuthContext,
        skipped: list[dict[str, Any]],
    ) -> bool:
        """Restore ``owner``/``reporter``/``priority``/``stakeholder`` (R4).

        Goes through ``ArtifactAttributeGateway.write`` — the one seam REST and
        MCP use — never a raw column write. An actor value is resolved back to
        the wire form the gateway expects; an external actor is not restorable
        there (``allow_external`` is false for ``owner``/``reporter``), and a
        missing attribute definition degrades to a no-op exactly as it does on
        the transport paths. Both cases are reported, not swallowed.
        """
        from application.artifact_attribute_gateway import (
            ArtifactAttributeGateway,
            AttributeValues,
        )
        from application.attribute_definition_service import AttributeDefinitionNotFound
        from persistence.models import Artifact

        core: dict[str, Any] = {}
        for name, value in hull.items():
            if name in ("owner", "reporter"):
                wire = self._actor_wire_value(value)
                if wire is _ACTOR_UNRESTORABLE:
                    skipped.append(
                        {
                            "kind": "hull_fields",
                            "item_id": member.item_id,
                            "fields": [name],
                            "reason": "actor_not_restorable",
                        }
                    )
                    continue
                core[name] = wire
            else:
                core[name] = value

        if not core:
            return False

        artifact = Artifact.unscoped.filter(
            id=member.item_id, tenant_id=ctx.tenant_id
        ).first()
        if artifact is None:  # pragma: no cover - entity row implies artifact
            return False

        try:
            ArtifactAttributeGateway().write(
                ctx, item_type, artifact, AttributeValues(core=core)
            )
        except AttributeDefinitionNotFound:
            skipped.append(
                {
                    "kind": "hull_fields",
                    "item_id": member.item_id,
                    "fields": sorted(core),
                    "reason": "no_attribute_definition",
                }
            )
            return False
        return True

    def _actor_wire_value(self, value: Any) -> Any:
        """Snapshot Actor pk -> the gateway's actor wire form.

        The snapshot stores ``Artifact.owner_id``/``reporter_id`` (an ``Actor``
        primary key, ``state_capture``). ``ActorService.resolve_reference``
        accepts an Actor id under ``kind="user"``, which is what a user-kind
        actor needs; an external actor cannot be written through this seam
        (``allow_external=False``) and is reported instead.
        """
        if value in (None, ""):
            return None

        from persistence.models import Actor

        actor = Actor.objects.filter(id=value).first()
        if actor is None:
            return _ACTOR_UNRESTORABLE
        if actor.kind != Actor.Kind.USER:
            return _ACTOR_UNRESTORABLE
        return {"kind": "user", "id": str(actor.id)}

    @staticmethod
    def _coerce(item_type: str, name: str, value: Any) -> Any:
        """Convert a JSON-serialised snapshot value back to its column type."""
        if name in _DATE_FIELDS.get(item_type, frozenset()):
            if isinstance(value, str) and value:
                return date.fromisoformat(value)
            return value
        if name == "owner_user_id" and isinstance(value, str) and value:
            return UUID(value)
        return value

    # ------------------------------------------------------------------
    # Rights (R7/R8)
    # ------------------------------------------------------------------

    def _readable_ids(
        self, artifact_ids: set[str], workspace_id: UUID, ctx: AuthContext
    ) -> set[str]:
        """Subset of *artifact_ids* the caller may READ (R7)."""
        if not artifact_ids:
            return set()
        return {
            artifact_id
            for artifact_id in artifact_ids
            if self._allowed(artifact_id, workspace_id, ctx, "read")
        }

    def _assert_write_access(
        self, artifact_ids: set[str], workspace_id: UUID, ctx: AuthContext
    ) -> None:
        """R7 — deny the whole run before the first write when WRITE is missing.

        ``details`` names only the ids the caller may *read* (plus the number of
        the rest): a denial must not become a directory of hidden artifacts.
        """
        denied = [
            artifact_id
            for artifact_id in sorted(artifact_ids)
            if not self._allowed(artifact_id, workspace_id, ctx, "write")
        ]
        if not denied:
            return
        denied_set = set(denied)
        readable_denied = sorted(
            artifact_id
            for artifact_id in denied
            if artifact_id in self._readable_ids(denied_set, workspace_id, ctx)
        )
        raise RollbackForbiddenError(
            "Rollback requires write permission on every affected artifact.",
            details={
                "readable_item_ids": readable_denied,
                "denied_count": len(denied),
            },
        )

    @staticmethod
    def _allowed(
        artifact_id: str, workspace_id: UUID, ctx: AuthContext, level: str
    ) -> bool:
        """``EffectivePermissionService`` verdict for one artifact."""
        from application.effective_permission_service import EffectivePermissionService

        try:
            uuid_value = UUID(str(artifact_id))
        except (TypeError, ValueError):  # pragma: no cover - ids come from the DB
            return False
        decision = EffectivePermissionService().resolve_effective_permission(
            active_roles=ctx.active_roles,
            user_id=ctx.user_id,
            workspace_id=workspace_id,
            artifact_id=uuid_value,
            level=level,
        )
        return decision.is_allowed

    # ------------------------------------------------------------------
    # Plan binding (R3) and CR state (R5)
    # ------------------------------------------------------------------

    def _stale_items(self, rows, members: list[_Member]) -> list[dict[str, Any]]:
        """R3 — items whose current version differs from ``version_before``.

        Only items the baseline actually carries are bound: an affected item
        outside the baseline has nothing to restore, so it cannot make the plan
        stale (a link-only rollback binds its endpoints, and the far endpoint of
        a cross-scope link is exactly such an item).
        """
        current = {
            member.item_id: member.current_version
            for member in members
            if member.baseline_state
        }
        stale: list[dict[str, Any]] = []
        for row in rows:
            item_id = str(row.item_id)
            if item_id not in current:
                continue
            if current.get(item_id) != row.version_before:
                stale.append(
                    {
                        "item_id": item_id,
                        "version_before": row.version_before,
                        "current_version": current.get(item_id),
                    }
                )
        return stale

    @staticmethod
    def _cr_status_and_version(change_request_id: UUID) -> tuple[str | None, int | None]:
        """Read the CR's workflow state + revision (it lives in ``we_item_state``)."""
        from workflow.models import WorkflowItemState

        row = WorkflowItemState.objects.filter(
            item_id=change_request_id, item_type="ChangeRequest"
        ).first()
        if row is None:
            return None, None
        return row.current_state, row.version

    @staticmethod
    def _member_workspace_id(member: _Member, ctx: AuthContext) -> UUID:
        """Workspace of a member, resolved from its backing Artifact."""
        from persistence.models import Artifact

        workspace_id = (
            Artifact.unscoped.filter(id=member.item_id, tenant_id=ctx.tenant_id)
            .values_list("workspace_id", flat=True)
            .first()
        )
        if workspace_id is None:  # pragma: no cover - entity row implies artifact
            raise NotFoundError(f"Artifact {member.item_id} not found")
        return workspace_id

    # ------------------------------------------------------------------
    # Logging (R6)
    # ------------------------------------------------------------------

    @staticmethod
    def _log_rejection(
        action: str, change_request_id: UUID, ctx: AuthContext, exc_type: type
    ) -> None:
        """WARNING with CR id, user and error code for every refused attempt."""
        code = getattr(exc_type, "code", getattr(exc_type, "error_code", exc_type.__name__))
        logger.warning(
            "Baseline rollback %s rejected: change_request=%s user=%s code=%s",
            action,
            change_request_id,
            getattr(ctx, "user_id", None),
            code,
        )


#: Sentinel: a snapshot actor value that cannot be written back through the
#: gateway (external actor, or an actor row that no longer exists).
_ACTOR_UNRESTORABLE = object()


__all__ = [
    "MAX_ROLLBACK_ITEMS",
    "SUPPORTED_ITEM_TYPES",
    "BaselineRollbackService",
    "RollbackAlreadyAppliedError",
    "RollbackEmptyError",
    "RollbackError",
    "RollbackForbiddenError",
    "RollbackItem",
    "RollbackNotApprovedError",
    "RollbackPlan",
    "RollbackPlanStaleError",
    "RollbackResult",
    "RollbackTooLargeError",
]
