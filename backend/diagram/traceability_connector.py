"""
ARCH-L1-013 DiagramService — Traceability connector.

leaf_id: COMP-DS-004_TraceabilityConnector
req_id: REQ-L1-027, REQ-L2-DS-004, REQ-L3-TC-001

Internal interface:
  IF-DS-INT-003: create_document_link(diagram_id, target_id, created_by_id) -> TraceLink

External interface (outgoing):
  IF-L1-034: creates a TraceLink of link_type='documents' via
             traceability.services.create_trace_link

Links a Diagram's shadow-Artifact to a target artifact (Requirement or
ArchitectureElement) using the TraceabilityEngine (ARCH-L1-007) with
link_type='documents' (LinkType.DOCUMENTS).

Shadow-Artifact pattern (Codeberg #353 Task 3, closes #392):
  Diagram entities do not inherit from persistence.models.Artifact — they
  remain a standalone domain entity in the DiagramService module (bounded
  context, unchanged by this fix). What changed: a Diagram's *raw* UUID is no
  longer used directly as a TraceLink source_id. TraceLinkManager.create looks
  up the source via ``Artifact.unscoped.get(pk=source_id)`` — a bare
  ``diagram.id`` never resolves there, so every "documents" link creation
  raised SourceNotFoundError (#392). Diagram now owns an optional, lazily-
  created 1:1 ``Diagram.artifact`` side-channel FK (persistence/models.py via
  diagram/models.py, migration 0007) to a *real*, persisted Artifact row.
  ``_resolve_artifact_id`` is the single choke point that creates/looks up
  that shadow Artifact; both this module's own "documents" link path and the
  Task 4 "diagram-ref" reconciler call it, so the fix lives in exactly one
  place.

Per-node artifact_ref reconciler (Codeberg #353 Task 4):
  ``sync_node_links`` reconciles the *desired* set of ``LinkType.DIAGRAM_REF``
  TraceLinks (derived from a ``node_graph`` payload's per-node
  ``artifact_ref`` fields, see ``diagram.node_graph.extract_artifact_refs``)
  against the *current* set already persisted for the Diagram's shadow
  Artifact — creating what's missing, deleting what's no longer referenced,
  and leaving the rest untouched. It is reconciler-owned and MUST NEVER read,
  create or delete a TraceLink of any other ``link_type`` (in particular the
  hand-authored ``documents`` link created by ``create_document_link`` above)
  on the same Diagram/artifact pair — every query and mutation below is
  therefore hard-filtered to ``link_type=LinkType.DIAGRAM_REF``.
"""
from __future__ import annotations

import uuid
from typing import Optional

from diagram.models import Diagram
from persistence.models import Artifact
from traceability.services import create_trace_link
from traceability.exceptions import TraceLinkError


# ---------------------------------------------------------------------------
# Shadow-Artifact resolution (Codeberg #353 Task 3 / #392)
# ---------------------------------------------------------------------------

def _resolve_artifact_id(diagram: Diagram) -> uuid.UUID:
    """Resolve the shadow Artifact id backing *diagram*, creating it lazily.

    Idempotent: if ``diagram.artifact_id`` is already set, it is returned
    unchanged — no second shadow Artifact is ever created for the same
    Diagram.

    Concurrency-safety (code review round 1, Codeberg #353 Task 3): a plain
    read-then-write here is a TOCTOU race — two concurrent callers (e.g. two
    MCP ``diagram.create``/``update`` requests referencing the same
    pre-existing Diagram) could both observe ``artifact_id is None`` and both
    ``INSERT`` a shadow Artifact, orphaning one of them. There is no unique
    constraint that would reject the second Artifact (``Diagram.artifact``'s
    OneToOneField index only prevents two *Diagrams* sharing one Artifact, it
    does not limit how many Artifacts a Diagram can be pointed at over
    successive writes). To close this, the *fast-path* check above is only a
    cheap optimization for the already-resolved case; whenever it is
    ambiguous we re-fetch the row via ``select_for_update()`` so a second,
    concurrent caller blocks on the row lock until the first caller's
    transaction commits (or rolls back) — at which point it observes the
    now-set ``artifact_id`` and returns it instead of creating a duplicate.

    Transaction-safety: performs a write (Artifact creation + Diagram save)
    but never opens its own transaction. It must be called from inside the
    caller's existing atomic block (DiagramManager's write paths are already
    wrapped in ``@atomic_transaction`` — persistence.transactions) so that a
    rollback of the outer operation also rolls back the shadow Artifact.
    ``select_for_update()`` itself requires an active transaction (Django
    raises ``TransactionManagementError`` otherwise), which doubles as a
    guard against this function ever being called outside one.

    Args:
        diagram: The Diagram ORM instance to resolve/attach a shadow
            Artifact for.

    Returns:
        The UUID of the (possibly newly-created) shadow Artifact.

    Raises:
        TraceLinkError: If the diagram has no ``workspace_id`` set. An
            Artifact row requires a non-null ``workspace`` FK
            (persistence.models.Artifact), so a Diagram must first be
            assigned to a workspace (REQ-173) before it can back a TraceLink.
    """
    if diagram.artifact_id is not None:
        return diagram.artifact_id

    # Ambiguous fast-path: re-fetch under a row lock so a concurrent caller
    # racing us here blocks instead of also creating a shadow Artifact.
    locked_diagram = Diagram.objects.select_for_update().get(pk=diagram.pk)

    if locked_diagram.artifact_id is not None:
        # Another caller created it while we were waiting for the lock.
        diagram.artifact_id = locked_diagram.artifact_id
        return locked_diagram.artifact_id

    if locked_diagram.workspace_id is None:
        raise TraceLinkError(
            f"Diagram {locked_diagram.id} has no workspace_id; a Diagram "
            "must be assigned to a workspace before it can back a TraceLink."
        )

    artifact = Artifact.objects.create(
        artifact_type="Diagram",
        tenant=locked_diagram.tenant,
        workspace_id=locked_diagram.workspace_id,
    )
    locked_diagram.artifact = artifact
    locked_diagram.save(update_fields=["artifact", "modified_at"])
    diagram.artifact = artifact
    return artifact.id


# ---------------------------------------------------------------------------
# Per-node artifact_ref -> Artifact resolution (Codeberg #353 Task 4)
# ---------------------------------------------------------------------------

def _resolve_target_artifact_id(
    entity_type: Optional[str],
    ref_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """Resolve one validated node_graph ``artifact_ref`` to a target Artifact id.

    Returns ``None`` — a single "unresolvable" outcome — for all three abort
    conditions the Task 4 brief lists as equivalent: the referenced entity
    does not exist, belongs to a different tenant, or is soft-deleted. The
    caller (``sync_node_links``) turns a ``None`` into a save-aborting
    ``DiagramValidationError`` naming the offending node.

    Tenant scoping differs by entity type:
      * ``Requirement`` / ``StakeholderNeed`` / ``ArchitectureElement`` /
        ``TestCase`` are ``persistence.models.TenantScopedModel`` — their
        default ``objects`` manager already filters to the active
        ``TenantContext`` (persistence.tenancy), so a foreign-tenant id is
        simply invisible here, the same outcome as a nonexistent id.
      * ``Adr`` / ``Risk`` / ``Issue`` / ``Goal`` / ``MainGoal``
        (``application.models``) are plain ``models.Model`` with an explicit
        ``tenant_id`` column and no tenant-scoping manager (mirrors
        ``RiskService.delete_risk`` / ``IssueService.delete_issue``, which
        filter ``tenant_id=ctx.tenant_id`` explicitly for the same reason) —
        filtered explicitly against *tenant_id* here.
      * ``GlossaryTerm`` has no backing Artifact at all
        (``persistence.models.GlossaryTerm`` carries no ``artifact`` FK) and
        can therefore never back a TraceLink; always unresolvable. This is a
        pre-existing data-model gap (Task 4 does not attempt to close it),
        not a bug introduced by the reconciler.

    Soft-delete, per entity type's actual mechanism in this codebase (two
    independent mechanisms coexist — see REQ-006 vs. the WorkflowEngine
    "outdated" state):
      * ``Requirement`` / ``TestCase``: denormalized WorkflowEngine ``status``
        mirror == ``"outdated"`` (mirrors
        ``traceability.coverage_calculator._exclude_outdated_testcase_ids``).
      * ``ArchitectureElement``: no status mirror -> excluded via
        ``workflow.services.outdated_item_ids("ArchitectureElement")``.
      * ``StakeholderNeed``: REQ-006 ``lifecycle_status == "deleted"``.
      * ``Adr``: its own ``Adr.Status.DELETED`` sentinel on ``status``.
      * ``Risk`` / ``Issue``: hard-deleted by ``RiskService.delete_risk`` /
        ``IssueService.delete_issue`` — a missing row already covers this,
        no extra exclusion needed.
      * ``Goal`` / ``MainGoal``: append-only, versioned rows with no
        soft-delete concept — existence + tenant match is sufficient.

    Args:
        entity_type: One of ``diagram.node_graph.KNOWN_ARTIFACT_ENTITY_TYPES``
            (already validated by ``validate_node_graph`` before this runs).
        ref_id:      The referenced entity's own primary key (already
            validated as a UUID string by ``validate_node_graph``).
        tenant_id:   The active tenant (``diagram.tenant_id``), used for the
            explicit-filter entity types above.

    Returns:
        The resolved target Artifact UUID, or ``None`` if unresolvable.
    """
    if entity_type == "Requirement":
        from persistence.models import Requirement
        from workflow import state_reader

        obj = Requirement.objects.filter(id=ref_id).first()
        if obj is None:
            return None
        # Datenmodell-Konsolidierung Phase 1: resolved through the engine.
        # Task 12: the ``status`` column is dropped -- a row never wired into
        # a WorkflowItemState falls back to the "draft" preset initial state
        # instead (documented, reviewed data-loss tradeoff, see Task 12
        # report Finding 2). Never "outdated", so it still resolves.
        current = state_reader.current_state(
            "Requirement", obj.id
        ) or state_reader.initial_state("Requirement")
        return obj.artifact_id if current != "outdated" else None

    if entity_type == "TestCase":
        from persistence.models import TestCase
        from workflow import state_reader

        obj = TestCase.objects.filter(id=ref_id).first()
        if obj is None:
            return None
        current = state_reader.current_state(
            "TestCase", obj.id
        ) or state_reader.initial_state("TestCase")
        return obj.artifact_id if current != "outdated" else None

    if entity_type == "StakeholderNeed":
        from persistence.models import StakeholderNeed

        obj = (
            StakeholderNeed.objects.filter(id=ref_id)
            .exclude(lifecycle_status="deleted")
            .first()
        )
        return obj.artifact_id if obj else None

    if entity_type == "ArchitectureElement":
        from persistence.models import ArchitectureElement
        from workflow.services import outdated_item_ids

        obj = (
            ArchitectureElement.objects.filter(id=ref_id)
            .exclude(id__in=outdated_item_ids("ArchitectureElement"))
            .first()
        )
        return obj.artifact_id if obj else None

    if entity_type == "Adr":
        from application.models import Adr
        from workflow import state_reader

        obj = Adr.objects.filter(
            id=ref_id, tenant_id=tenant_id, artifact_id__isnull=False
        ).first()
        if obj is None:
            return None
        # Datenmodell-Konsolidierung Phase 1: AdrService.delete_adr() routes
        # through workflow.services.outdate(), which writes "outdated" (the
        # universal soft-delete state) — not the Adr.Status.DELETED enum
        # value this used to check, which no production write path ever set.
        # Task 12: the ``status`` column is dropped -- an untracked row falls
        # back to the adr_default preset's initial state instead (documented,
        # reviewed data-loss tradeoff, see Task 12 report Finding 2). Never
        # "outdated", so it still resolves.
        current = state_reader.current_state(
            "Adr", obj.id
        ) or state_reader.initial_state("Adr")
        return obj.artifact_id if current != "outdated" else None

    if entity_type == "Risk":
        from application.models import Risk

        obj = Risk.objects.filter(
            id=ref_id, tenant_id=tenant_id, artifact_id__isnull=False
        ).first()
        return obj.artifact_id if obj else None

    if entity_type == "Issue":
        from application.models import Issue

        obj = Issue.objects.filter(
            id=ref_id, tenant_id=tenant_id, artifact_id__isnull=False
        ).first()
        return obj.artifact_id if obj else None

    if entity_type == "Goal":
        from application.models import Goal

        obj = Goal.objects.filter(id=ref_id, tenant_id=tenant_id).first()
        return obj.artifact_id if obj else None

    if entity_type == "MainGoal":
        from application.models import MainGoal

        obj = MainGoal.objects.filter(id=ref_id, tenant_id=tenant_id).first()
        return obj.artifact_id if obj else None

    # GlossaryTerm (not Artifact-backed) and any unrecognised entity_type:
    # always unresolvable.
    return None


# ---------------------------------------------------------------------------
# Per-node trace-link reconciler — IF-DS-INT-003 (Codeberg #353 Task 4)
# ---------------------------------------------------------------------------

def sync_node_links(
    diagram: Diagram,
    node_graph_payload: dict,
    created_by_id: Optional[uuid.UUID] = None,
) -> None:
    """Reconcile a Diagram's ``DIAGRAM_REF`` TraceLinks to its node_graph refs.

    Called by DiagramManager after a ``node_graph`` payload has been
    validated and (for create/update) persisted, so that the set of
    ``LinkType.DIAGRAM_REF`` TraceLinks whose source is this Diagram's shadow
    Artifact always mirrors the distinct set of ``artifact_ref`` targets
    currently present in the payload:

      * A target referenced by one or more nodes but with no existing link
        gets one created (never more than one, even if N nodes reference the
        same artifact — REQ dedupe).
      * An existing link whose target is no longer referenced by any node
        gets deleted.
      * An existing link whose target is still referenced is left alone
        (re-saving an unchanged graph is a no-op: no new rows, no deletes).

    Global safety invariant (the entire point of this function): the
    "current" query below filters ``link_type=LinkType.DIAGRAM_REF`` and
    NEVER omits that filter — a hand-authored ``documents`` link (or any
    other link_type) on the exact same Diagram/artifact pair is therefore
    never read, created or deleted by this reconciler, no matter what the
    node_graph payload contains.

    Unresolvable refs abort the *entire* save (no partial application): if
    any node's ``artifact_ref`` does not resolve to an existing, same-tenant,
    non-soft-deleted Artifact, this raises before any TraceLink is created or
    deleted, naming the offending node id. Callers (DiagramManager) run this
    inside the same ``@atomic_transaction`` as the diagram/version write, so
    an abort here also rolls back the diagram save itself.

    Args:
        diagram:            The just-created/updated Diagram ORM instance
            (must belong to the active tenant; ``diagram.tenant_id`` is used
            for the entity types without a tenant-scoping manager).
        node_graph_payload: The already-validated ``node_graph`` payload
            dict (call ``diagram.node_graph.validate_node_graph`` first).
        created_by_id:      Optional actor UUID for audit metadata on newly
            created links.

    Raises:
        DiagramValidationError: A node's ``artifact_ref`` does not resolve to
            an existing, same-tenant, non-soft-deleted Artifact. Mapped to
            ``400 VALIDATION_ERROR`` by the same REST/MCP handlers that
            already catch this exception for payload validation (CR-02) —
            no separate exception-mapping code needed at those layers.
        TraceLinkError: The Diagram has no ``workspace_id`` (via
            ``_resolve_artifact_id`` — REQ-173, unchanged Task 3 contract).
    """
    from diagram.node_graph import extract_artifact_refs
    from diagram.validator import DiagramValidationError
    from persistence.models import TraceLink
    from traceability.types import LinkType

    refs = extract_artifact_refs(node_graph_payload)

    desired_ids: set[uuid.UUID] = set()
    for node_id, artifact_ref in refs:
        entity_type = artifact_ref.get("entity_type")
        raw_ref_id = artifact_ref.get("id")
        try:
            ref_uuid = uuid.UUID(str(raw_ref_id))
        except (ValueError, TypeError, AttributeError):
            ref_uuid = None

        resolved = (
            _resolve_target_artifact_id(entity_type, ref_uuid, diagram.tenant_id)
            if ref_uuid is not None
            else None
        )
        if resolved is None:
            raise DiagramValidationError(
                f"Node '{node_id}': artifact_ref "
                f"(entity_type={entity_type!r}, id={raw_ref_id!r}) does not "
                "resolve to an existing, same-tenant artifact."
            )
        desired_ids.add(resolved)

    if not desired_ids and diagram.artifact_id is None:
        # No refs in the payload, and this Diagram has never had a shadow
        # Artifact created — so no DIAGRAM_REF link could possibly exist for
        # it yet either. Skip _resolve_artifact_id entirely: it requires
        # diagram.workspace_id to be set, and a node_graph payload with no
        # artifact_ref nodes at all must keep working for workspace-less
        # Diagrams (see diagram.tests.test_manager.TestNodeGraphWritePath,
        # none of which pass workspace_id).
        return

    diagram_artifact_id = _resolve_artifact_id(diagram)

    # Step 4 (the entire safety mechanism) — see module/function docstring:
    # this filter MUST always include link_type=LinkType.DIAGRAM_REF.
    current_links = list(
        TraceLink.objects.filter(
            source_id=diagram_artifact_id, link_type=LinkType.DIAGRAM_REF
        )
    )
    current_ids = {link.target_id for link in current_links}

    to_delete_ids = current_ids - desired_ids
    to_create_ids = desired_ids - current_ids

    if to_delete_ids:
        TraceLink.objects.filter(
            source_id=diagram_artifact_id,
            link_type=LinkType.DIAGRAM_REF,
            target_id__in=to_delete_ids,
        ).delete()

    for target_id in to_create_ids:
        create_trace_link(
            source_id=diagram_artifact_id,
            target_id=target_id,
            link_type=LinkType.DIAGRAM_REF,
            created_by_id=created_by_id,
        )


# ---------------------------------------------------------------------------
# Public interface — IF-DS-INT-003 / IF-L1-034
# ---------------------------------------------------------------------------

class TraceabilityConnector:
    """COMP-DS-004: Creates 'documents' TraceLinks via the TraceabilityEngine.

    req_id: REQ-L2-DS-004, REQ-L3-TC-001
    leaf_id: COMP-DS-004_TraceabilityConnector

    Called exclusively by DiagramManager (COMP-DS-001) via IF-DS-INT-003.
    Delegates to traceability.services.create_trace_link (IF-L1-034).
    """

    LINK_TYPE: str = "documents"

    def create_document_link(
        self,
        diagram_id: uuid.UUID,
        target_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> object:
        """Create a 'documents' TraceLink between a diagram and a target artifact.

        IF-DS-INT-003 contract: create_document_link(diagram_id, target_id)

        #392 fix: resolves *diagram_id* to its shadow Artifact id via
        ``_resolve_artifact_id`` before delegating to the TraceabilityEngine,
        instead of passing the raw Diagram UUID as source_id.

        Args:
            diagram_id:     UUID of the Diagram (source side).
            target_id:      UUID of the target Artifact (Requirement or
                            ArchitectureElement).
            created_by_id:  Optional actor UUID for audit metadata.

        Returns:
            The created TraceLink ORM object (from TraceabilityEngine).

        Raises:
            Diagram.DoesNotExist: If diagram_id does not resolve to a Diagram
                                  in the active tenant.
            TraceLinkError:       If TraceabilityEngine rejects the link
                                  (e.g. target not found, cross-tenant, cycle),
                                  or if the Diagram has no workspace assigned.
                                  REQ-L3-TC-001: errors propagated transparently.
        """
        diagram = Diagram.objects.get(id=diagram_id)
        resolved_source_id = _resolve_artifact_id(diagram)

        # IF-L1-034: delegate to TraceabilityEngine public facade
        return create_trace_link(
            source_id=resolved_source_id,
            target_id=target_id,
            link_type=self.LINK_TYPE,
            created_by_id=created_by_id,
        )


__all__ = [
    "TraceabilityConnector",
    "_resolve_artifact_id",
    "sync_node_links",
]
