"""
COMP-AS-002 RequirementService — Requirement CRUD + Decomposition.

leaf_id : COMP-AS-002
req_id  : REQ-L2-AS-003 (Requirement CRUD), REQ-L2-AS-013 (LLM Orchestration),
          REQ-L2-AS-024 (Decomposition), REQ-L2-AS-015 (GitHub Integration)

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link         (parent-child links)
  IF-AS-INT-008   PresetPolicyService.is_change_reason_required
  IF-AS-INT-009   DomainEventBus  →  RequirementCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-001  workflow.services.initialize_workflow_states / transition
  IF-AS-EXT-OUT-005  llm_adapter.services.decompose_requirement / validate_artifact
  IF-AS-EXT-OUT-007  persistence.models.Requirement / Artifact (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-002_RequirementService/
      L3_COMP-AS-002_RequirementService_Architecture.md

ADR-L3-AS002-01: Decomposition is one atomic TX.
ADR-L3-AS002-02: change_reason validated via PresetPolicyService.
ADR-L3-AS002-03: LLM not configured → explicit LlmNotConfiguredError.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.core.cache import cache
from django.db.models import F, Q, QuerySet
from django.db.utils import OperationalError, ProgrammingError
from persistence.models import (
    Artifact,
    Requirement,
    RequirementLevel,
    Tenant,
    Workspace,
)
from persistence.transactions import TransactionContextManager, atomic_transaction
from traceability.types import LinkType

from application.base import (
    LlmNotConfiguredError,
    NotFoundError,
    ServiceBase,
    ValidationError,
)
from application.artifact_service import (
    _clean_custom_fields,
    clean_free_text_field,
    has_field_changes,
    snapshot_versioned_fields,
)
from application.models import DomainEventOutbox
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)

logger = logging.getLogger(__name__)

# Sentinel to distinguish "not provided" from "set to None" in update calls.
_UNSET = object()

# #45 (IEEE 29148 §5.2.4): "and"/"or" conjunctions in a requirement title
# usually indicate it bundles more than one testable statement. Word-boundary
# match so this doesn't false-positive on substrings ("Android", "Norway").
_NON_ATOMIC_TERM_PATTERN = re.compile(r"\b(and|or)\b", re.IGNORECASE)

# GH-796: check_consistency() dispatches an async Celery task and returns
# only a task_id -- with no record of which tenant dispatched it, a status
# poll could not be scoped and any authenticated caller could probe another
# tenant's task_id. Mirrors bundle_compression_service's
# _TASK_TENANT_CACHE_PREFIX pattern (ADR-03 row-level tenant isolation).
_CONSISTENCY_TASK_TENANT_CACHE_PREFIX = "requirement_consistency_task_tenant"
_CONSISTENCY_TASK_TENANT_TTL_SECONDS = 86400


def detect_non_atomic_terms(title: str) -> List[str]:
    """Return the distinct conjunction words found in ``title``, lowercased.

    Deliberately a lightweight, always-available heuristic (no LLM call) —
    a non-blocking hint, not a validation gate. Empty list means "no
    conjunctions found", not "confirmed atomic": the check cannot detect
    every non-atomic phrasing (e.g. semicolon-joined clauses), only the
    literal 'and'/'or' pattern IEEE 29148 §5.2.4 calls out.
    """
    return sorted({m.group(1).lower() for m in _NON_ATOMIC_TERM_PATTERN.finditer(title or "")})


class PgVectorUnavailableError(RuntimeError):
    """Raised when pgvector (package or ``vector`` extension) is unavailable.

    REQ-L2-VS-004: similarity search depends on pgvector. When the Python
    package is missing or the DB extension is not installed, the REST layer
    maps this to HTTP 503 (service unavailable) rather than a 500.
    """

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class RequirementDTO:
    """Read-oriented DTO returned by RequirementService methods."""

    id: UUID
    workspace_id: UUID
    title: str
    description: str
    category: str
    status: str
    version: int

    @classmethod
    def from_orm(cls, req: Requirement) -> "RequirementDTO":
        return cls(
            id=req.id,
            workspace_id=req.artifact.workspace_id,
            title=req.title,
            description=req.description,
            category=req.category,
            status=req.status,
            version=req.version,
        )


@dataclass
class DecompositionResultDTO:
    """Result of a decompose() operation."""

    parent_id: UUID
    children: List[RequirementDTO] = field(default_factory=list)
    trace_link_ids: List[UUID] = field(default_factory=list)


@dataclass
class SimilarRequirementDTO:
    """A single similarity-search hit (REQ-L2-VS-004)."""

    id: UUID
    uid: Optional[str]
    title: str
    category: str
    status: str
    similarity_score: float


# ---------------------------------------------------------------------------
# RequirementService
# ---------------------------------------------------------------------------


class RequirementService(ServiceBase):
    """COMP-AS-002 — Requirement CRUD, decomposition and LLM validation."""

    def __init__(
        self,
        trace_link_service=None,
        preset_policy_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService
        from application.preset_policy_service import get_preset_policy_service

        self._trace_link_service = trace_link_service or TraceLinkService()
        self._preset_policy = preset_policy_service or get_preset_policy_service()

    # ---------- CRUD (REQ-L2-AS-003) ----------

    def _assert_uid_unique_in_workspace(
        self,
        workspace_id: UUID,
        uid: Optional[str],
        *,
        exclude_id: Optional[UUID] = None,
    ) -> None:
        """#44: reject a client-supplied ``uid`` that collides within the
        same workspace.

        Scoped to workspace (not tenant): ReqIF import legitimately
        duplicates identifiers into a different workspace of the same
        tenant, so a tenant-wide constraint would be a behaviour change for
        that path. This check only guards the API/service-level create and
        update entry points.
        """
        if not uid:
            return
        qs = Requirement.objects.filter(artifact__workspace_id=workspace_id, uid=uid)
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        if qs.exists():
            raise ValidationError(
                f"uid '{uid}' already exists in this workspace"
            )

    @atomic_transaction
    def create_requirement(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
        acceptance_criteria: str = "",
        category: str = "",
        parent_id: Optional[UUID] = None,
        type: str = "SyReq",
        complexity_fibonacci: Optional[int] = None,
        verification_method: Optional[str] = None,
        level: Optional[int] = None,
        uid: Optional[str] = None,
        custom_fields: Optional[dict] = None,
    ) -> Requirement:
        """Create a Requirement with initial workflow state.

        REQ-L2-AS-003: creates Requirement + initialises WorkflowState.
        REQ-L3-RF003-005: Accepts SE mask fields (type,
        complexity_fibonacci, verification_method, level).
        Note: moscow_priority lives on StakeholderNeed (migration 0020).
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Tenant and Workspace are imported at module level to allow test mocking.
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        self._assert_uid_unique_in_workspace(workspace_id, uid)

        # #709: reject HTML markup / script URIs before any row is written.
        # Defense in depth (see clean_free_text_field docstring) — this is
        # what closes the MCP `requirement.create` bypass, since MCP calls
        # this service directly and never runs the REST serializer/ViewSet
        # guard that already protects the REST boundary.
        title = clean_free_text_field(title, "title")
        description = clean_free_text_field(description, "description")
        acceptance_criteria = clean_free_text_field(
            acceptance_criteria, "acceptance_criteria"
        )

        # Create the backing Artifact first
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            parent_id=parent_id,
            custom_fields=_clean_custom_fields(custom_fields),
        )

        requirement = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            # #133: denormalized workspace back-reference for the DB-level
            # (workspace, uid) UniqueConstraint.
            workspace=workspace,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            category=category,
            status="draft",
            type=type,
            complexity_fibonacci=complexity_fibonacci,
            verification_method=verification_method,
            level=level,
            uid=uid,
        )

        # Initialise workflow state (IF-AS-EXT-OUT-001)
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[requirement.id],
                item_type="Requirement",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "RequirementService: workflow init skipped (no definition) "
                "for req=%s",
                requirement.id,
            )

        # REQ-L2-VS-004: best-effort semantic embedding for similarity search.
        self._generate_and_store_embedding(requirement)

        self._audit(ctx=ctx, operation="create", entity_type="Requirement", entity_id=requirement.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_CREATED,
                entity_id=requirement.id,
                workspace_id=workspace_id,
                # artifact_id: additive, for context_graph.projector (Issue
                # #377) — entity_id above is Requirement.id, not Artifact.id.
                payload={"title": title, "artifact_id": str(requirement.artifact_id)},
            )
        )
        return requirement

    def derive_requirement(
        self,
        parent_requirement_id: UUID,
        architecture_element_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
    ) -> DecompositionResultDTO:
        """Derive a single child Requirement from *parent_requirement_id*, allocated
        to *architecture_element_id* (decomposition onto the next system level).

        Thin single-child convenience wrapper around :meth:`decompose` — reuses its
        atomic parent-child TraceLink + allocation logic (REQ-L1-043) so the "Ableiten"
        action (UI, REST, MCP) stays consistent with AI-driven decomposition. The
        architecture target is mandatory here: derivation must always state which
        system element the derived requirement belongs to.

        Issue #459 (finding 2): if no *description* is given, the child inherits
        the parent's description instead of being created with an empty one — an
        empty description otherwise leads a subsequent AI derivation on the child
        to reason about the allocated ArchitectureElement instead of the actual
        requirement content. An explicitly passed (non-empty) *description* is
        never overridden.
        """
        if not description:
            self._set_tenant_context(ctx)
            parent_req = Requirement.objects.filter(id=parent_requirement_id).first()
            if parent_req is not None:
                description = parent_req.description or ""

        return self.decompose(
            requirement_id=parent_requirement_id,
            ctx=ctx,
            children=[{"title": title, "description": description}],
            target_architecture_elements=[architecture_element_id],
        )

    @atomic_transaction
    def update_requirement(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        acceptance_criteria: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        change_reason: Optional[str] = None,
        type: Optional[str] = None,
        complexity_fibonacci: object = _UNSET,
        verification_method: object = _UNSET,
        level: object = _UNSET,
        uid: object = _UNSET,
        suspect: Optional[bool] = None,
        custom_fields: object = _UNSET,
        expected_version: Optional[int] = None,
    ) -> Requirement:
        """Update a Requirement, enforcing change_reason policy.

        REQ-L2-AS-003: change_reason required in Extended preset.
        ADR-L3-AS002-02: delegates policy check to PresetPolicyService.
        REQ-L3-RF003-005: Accepts SE mask fields (type, moscow_priority,
        complexity_fibonacci, verification_method, level).
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.

        REQ-143: `status` is the WorkflowEngine-owned lifecycle mirror. The REST
        and MCP boundaries no longer forward it — a client-sent status is
        ignored there. The parameter is retained on this internal method for
        low-level/administrative callers only; normal state changes must go
        through a workflow transition (see docs/architecture/ADR-status-single-source.md).

        SYSTEMAUDIT_2026-08-29 REST finding 1: ``expected_version`` carries the
        caller's last-seen ``version``. When supplied and stale, the update is
        refused with ``OptimisticLockError`` (409 CONFLICT) instead of silently
        overwriting a concurrent edit. Omitting it keeps the previous
        last-writer-wins behaviour, so existing clients are unaffected.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        requirement = lock_for_version_check(
            Requirement.objects.select_related("artifact").filter(id=requirement_id),
            expected_version,
        ).first()
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        assert_expected_version(
            requirement, expected_version, entity_type="Requirement"
        )

        workspace_id = requirement.artifact.workspace_id

        # Enforce change_reason policy (ADR-L3-AS002-02)
        if self._preset_policy.is_change_reason_required(str(workspace_id)):
            if not change_reason:
                raise ValidationError("change_reason required by workspace preset policy")

        # #269 finding 5: snapshot BEFORE any assignment so the version bump
        # below can be gated on a real value change.
        _before = snapshot_versioned_fields(requirement)
        _custom_fields_changed = False

        # #709: same MCP-bypass defense in depth as create_requirement — only
        # applied to fields actually being changed (``is not None`` already
        # gates "was this field provided").
        if title is not None:
            requirement.title = clean_free_text_field(title, "title")
        if description is not None:
            requirement.description = clean_free_text_field(description, "description")
        if acceptance_criteria is not None:
            requirement.acceptance_criteria = clean_free_text_field(
                acceptance_criteria, "acceptance_criteria"
            )
        if category is not None:
            requirement.category = category
        if status is not None:
            requirement.status = status
        if type is not None:
            requirement.type = type
        if complexity_fibonacci is not _UNSET:
            requirement.complexity_fibonacci = complexity_fibonacci
        if verification_method is not _UNSET:
            requirement.verification_method = verification_method
        if level is not _UNSET:
            requirement.level = level
        if uid is not _UNSET:
            self._assert_uid_unique_in_workspace(
                workspace_id, uid, exclude_id=requirement.id
            )
            requirement.uid = uid

        # REQ-L2-AS-037: custom_fields lives on the backing Artifact, so it is
        # outside the Requirement snapshot and has to be compared separately.
        if custom_fields is not _UNSET:
            cleaned_custom_fields = _clean_custom_fields(custom_fields)
            _custom_fields_changed = (
                cleaned_custom_fields != (requirement.artifact.custom_fields or {})
            )
            requirement.artifact.custom_fields = cleaned_custom_fields
            requirement.artifact.save(update_fields=["custom_fields", "modified_at"])

        # SN-30: If title, description, or status changed, we will propagate suspect
        changed_critical = any(x is not None for x in [title, description, status])

        if hasattr(requirement, "suspect"):
            if suspect is not None:
                requirement.suspect = suspect

        requirement.save()
        # Atomic version increment (REQ-L3-PL001-002): requirement_service was
        # missing any version bump at all — the baseline diff engine compares
        # stored version numbers, so without this increment every update appears
        # as version=1 forever, producing incorrect/empty diffs.
        #
        # #269 finding 5: gated on an actual value change. Bumping on every call
        # made a no-op PATCH (unknown field, or a field re-sent with its current
        # value) look like a new revision and produced diffs between identical
        # snapshots.
        if has_field_changes(requirement, _before) or _custom_fields_changed:
            Requirement.objects.filter(id=requirement.id).update(
                version=F("version") + 1
            )
            requirement.refresh_from_db(fields=["version"])

        # REQ-L2-VS-004: refresh the embedding only when embedding-relevant text
        # (title/description) changed, to avoid needless LLM calls on metadata-
        # only updates. Best-effort — never fails the update.
        if title is not None or description is not None:
            self._generate_and_store_embedding(requirement)

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Requirement",
            entity_id=requirement_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_UPDATED,
                entity_id=requirement_id,
                workspace_id=workspace_id,
                # artifact_id: additive, for context_graph.projector (Issue #377).
                payload={"change_reason": change_reason, "artifact_id": str(requirement.artifact_id)},
            )
        )

        if changed_critical:
            try:
                self._trace_link_service.propagate_suspect_status(requirement.artifact_id, ctx)
            except Exception as e:
                logger.error(f"Error propagating suspect status: {e}", exc_info=True)

        return requirement

    @atomic_transaction
    def delete_requirement(
        self, requirement_id: UUID, ctx: AuthContext, change_reason: str = ""
    ) -> None:
        """Soft-delete Requirement by setting lifecycle_status to 'deleted' (REQ-006).

        Physical deletion is intentionally avoided for end-user operations.
        The Requirement and its TraceLinks remain in the database for audit
        trail purposes. Hard-delete is available only via the Django admin panel.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        requirement = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = requirement.artifact.workspace_id

        # #604: delete used to skip the workspace's change_reason preset
        # policy entirely -- a silent audit-trail gap next to
        # StakeholderNeedService.delete(), which already enforces it.
        if self._preset_policy.is_change_reason_required(str(workspace_id)):
            if not change_reason:
                raise ValidationError("change_reason is required by preset policy.")

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of writing lifecycle_status directly.
        from workflow.services import outdate

        outdate(
            item_id=requirement.id,
            item_type="Requirement",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via requirement.delete",
        )

        self._audit(ctx=ctx, operation="delete", entity_type="Requirement", entity_id=requirement_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_DELETED,
                entity_id=requirement_id,
                workspace_id=workspace_id,
            )
        )

    def get_requirement(self, requirement_id: UUID, ctx: AuthContext) -> Requirement:
        """Fetch a single Requirement (tenant-scoped).

        GH-443: a soft-deleted requirement (``status == "outdated"``, written
        by :meth:`delete_requirement` via ``workflow.services.outdate()``) is
        returned normally, carrying that status. It used to be reported as
        *not found*, which made DELETE look like a hard delete from the
        outside — the row was still there, but no caller could observe it, and
        the behaviour disagreed with every sibling service
        (``get_test_case`` / ``get_adr`` / ``get_issue`` / ``get_risk``, none
        of which filter on the soft-delete state either).

        Detail reads therefore stay reachable after a delete, so a client can
        tell "gone" (404) apart from "soft-deleted" (200 +
        ``status="outdated"``) and can restore the item via
        ``POST /api/v1/requirements/{id}/reactivate/``. *List* reads still hide
        outdated requirements by default — see :meth:`list_requirements`.
        """
        self._set_tenant_context(ctx)
        req = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return req

    def list_requirements(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        include_deleted: bool = False,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> QuerySet[Requirement]:
        """Return Requirements in *workspace_id*.

        REQ-006: Excludes soft-deleted requirements (lifecycle_status='deleted') by default.
        Pass ``include_deleted=True`` for admin/audit access.

        REQ-144: Pass ``status`` to filter by the WorkflowEngine-owned lifecycle
        mirror (e.g. ``status="in_review"`` for the review queue). ``status`` is
        a pure read filter on the denormalized mirror column — it does not
        affect the workflow engine and does not accept the client to *write*
        status (see ``update_requirement``).

        GH-443: ``status="outdated"`` implies ``include_deleted``. Without
        that, the default soft-delete exclusion ran first and the explicit
        filter could only ever return an empty page — so the UI's status
        filter had no way to surface soft-deleted requirements at all.

        Issue #267 regression fix: ``search`` case-insensitively filters on
        title/description/uid via ``icontains`` (bound query parameters — not
        raw SQL, so search terms are always treated as literal text, never
        interpreted as SQL). Previously this parameter did not exist at all,
        so ``?search=`` was silently ignored by the ViewSet and every item in
        the workspace was returned unfiltered regardless of the search term.

        REQ-088: Returns a lazy ``QuerySet`` (no ``list()``) so the caller —
        e.g. the paginating ViewSet (REQ-034) — can slice with LIMIT/OFFSET
        instead of materialising the full result set.
        """
        self._set_tenant_context(ctx)
        qs = Requirement.objects.select_related("artifact").filter(
            artifact__workspace_id=workspace_id
        )
        if not include_deleted and status != "outdated":
            # Phase 0: delete_requirement() routes through workflow.services.outdate(),
            # which mirrors the new state into Requirement.status (not
            # lifecycle_status) via _STATUS_MIRROR_MODELS. Filter on the field
            # that outdate() actually writes.
            qs = qs.exclude(status="outdated")
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(uid__icontains=search)
            )
        return qs

    # ---------- Semantic similarity (REQ-L2-VS-004) ----------

    @staticmethod
    def _generate_and_store_embedding(requirement: Requirement) -> None:
        """Best-effort: generate and persist the requirement's embedding.

        REQ-L2-VS-004. Uses a bare ``.update()`` so it neither bumps the
        version nor emits a domain event. Never raises: the embedding is
        supplementary to full-text search, so a provider/network failure must
        not fail the surrounding create/update transaction.

        ``Requirement.embedding`` is a fixed-dimension pgvector column, sized
        from ``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS``.
        A vector of any other width is rejected by Postgres at the DB level
        (``DataError``), and — because ``.update()`` runs inside the caller's
        ambient transaction — an uncaught DataError here would poison that
        whole transaction (every subsequent query on the connection then fails
        with "current transaction is aborted") rather than just skip the
        embedding. Guard by comparing the generated vector's length against
        the column's declared dimension *before* issuing the write, so a
        mismatch is a no-op skip, not a DB round-trip that fails.

        Issue #794: that guard used to skip 100% of writes under the shipped
        default (a 384-dim provider against a hardcoded ``vector(1536)``
        column) and reported it only at DEBUG, so the feature was silently
        dead. The column now matches the default provider, and a mismatch
        left by a non-default provider is reported at WARNING via
        ``warn_dimension_mismatch``.
        """
        try:
            from llm_adapter.embedding_service import (
                generate_embedding,
                get_embedding_text,
                warn_dimension_mismatch,
            )

            embedding = generate_embedding(get_embedding_text(requirement))
            field_dimensions = Requirement._meta.get_field("embedding").dimensions
            if embedding is not None and len(embedding) == field_dimensions:
                Requirement.objects.filter(id=requirement.id).update(
                    embedding=embedding
                )
            elif embedding is not None:
                warn_dimension_mismatch(
                    "RequirementService", len(embedding), field_dimensions
                )
        except Exception as exc:  # noqa: BLE0001 — best-effort
            logger.debug(
                "RequirementService: embedding generation skipped for req=%s: %s",
                requirement.id,
                exc,
            )

    def find_similar_requirements(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        limit: int = 10,
        workspace_id: Optional[UUID] = None,
    ) -> List[SimilarRequirementDTO]:
        """Return the top-N requirements most similar to *requirement_id*.

        REQ-L2-VS-004: cosine-distance nearest-neighbour search over the
        pgvector ``embedding`` column, tenant-scoped and excluding the query
        requirement itself.

        Args:
            requirement_id: Query requirement (must have a non-null embedding).
            ctx: AuthContext for tenant scoping.
            limit: Max results (clamped to 1..50, default 10).
            workspace_id: Optional workspace filter.

        Returns:
            Ordered list of SimilarRequirementDTO (closest first).

        Raises:
            NotFoundError: Query requirement does not exist.
            ValidationError: Query requirement has no embedding.
            PgVectorUnavailableError: pgvector package/extension unavailable.
        """
        self._set_tenant_context(ctx)

        req = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        if req.embedding is None:
            raise ValidationError(
                "Requirement has no embedding — similarity search not possible"
            )

        try:
            from pgvector.django import CosineDistance
        except ImportError as exc:
            raise PgVectorUnavailableError(
                "pgvector package not installed — similarity search unavailable"
            ) from exc

        safe_limit = max(1, min(int(limit or 10), 50))

        queryset = Requirement.objects.filter(
            tenant_id=ctx.tenant_id, embedding__isnull=False
        )
        if workspace_id is not None:
            queryset = queryset.filter(artifact__workspace_id=workspace_id)
        queryset = (
            queryset.exclude(id=req.id)
            .select_related("artifact")
            .annotate(distance=CosineDistance("embedding", req.embedding))
            .order_by("distance")[:safe_limit]
        )

        try:
            rows = list(queryset)
        except (ProgrammingError, OperationalError) as exc:
            raise PgVectorUnavailableError(
                "pgvector extension not available — similarity search unavailable"
            ) from exc

        return [
            SimilarRequirementDTO(
                id=row.id,
                uid=row.uid,
                title=row.title,
                category=row.category,
                status=row.status,
                # Cosine distance in [0, 2]; similarity = 1 - distance.
                similarity_score=round(1.0 - float(row.distance), 6),
            )
            for row in rows
        ]

    # ---------- Decomposition (REQ-L2-AS-024) ----------

    def decompose(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        children: Optional[List[Dict[str, Any]]] = None,
        target_architecture_elements: Optional[List[UUID]] = None,
    ) -> DecompositionResultDTO:
        """Decompose a Requirement into child Requirements.

        If *children* are provided: validate + persist directly.
        Otherwise: delegate to LlmAdapter for AI decomposition.

        REQ-L2-AS-024: decomposition logic
        REQ-L1-043: optional allocation of children to ArchitectureElements
        ADR-L3-AS002-01 (single atomic TX).

        Links emitted per child (issue #395 — the full SE decomposition set,
        identical to ``ArchitectureDecomposeService._link_node``):

        * ``decomposes``   : parent Requirement -> child Requirement
        * ``derives-from`` : child Requirement -> parent Requirement
        * ``allocated-to`` : child Requirement -> ArchitectureElement
          (only when *target_architecture_elements* is given)

        Each child also inherits ``level = parent.level + 1`` (P1-9), unless
        the parent's level is unknown or already the bottom of the cascade —
        see the inline comment at the derivation for both exceptions.

        Args:
            requirement_id: UUID of parent requirement to decompose.
            ctx: AuthContext for tenant scoping and audit.
            children: Optional list of child requirement data dicts.
                     If None, LLM will generate decomposition.
            target_architecture_elements: Optional list of ArchitectureElement UUIDs
                                         to allocate children to (in order).
                                         If provided, must match children count.

        Returns:
            DecompositionResultDTO containing created children and trace links.

        Raises:
            NotFoundError: Parent requirement or ArchitectureElement not found.
            ValidationError: Mismatch between children and target elements count,
                            or empty target_architecture_elements list.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        parent_req = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if parent_req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = parent_req.artifact.workspace_id

        if children is None:
            children = self._decompose_via_llm(
                str(requirement_id),
                title=parent_req.title,
                content=parent_req.description or "",
            )

        # REQ-L1-043: Validate target_architecture_elements if provided
        if target_architecture_elements is not None:
            if len(target_architecture_elements) == 0:
                raise ValidationError(
                    "target_architecture_elements cannot be empty when provided"
                )
            if len(target_architecture_elements) != len(children):
                raise ValidationError(
                    f"Number of target_architecture_elements ({len(target_architecture_elements)}) "
                    f"must match number of children ({len(children)})"
                )

            # Validate existence and workspace membership of all ArchitectureElements
            from persistence.models import ArchitectureElement
            for arch_el_id in target_architecture_elements:
                arch_el = ArchitectureElement.objects.filter(id=arch_el_id).first()
                if arch_el is None:
                    raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")
                if arch_el.artifact.workspace_id != workspace_id:
                    raise ValidationError(
                        f"ArchitectureElement {arch_el_id} is not in workspace {workspace_id}"
                    )

        # UMSETZUNGSPLAN_SYSENG_2.0.md §1.4: decompose() is hardcoded to always
        # create LinkType.DECOMPOSES links, for ALL workspaces, regardless of
        # Workspace.decomposition_link_type. That field is now functionally
        # dead for this creation path (kept on the model — no migration/backfill;
        # existing parent-child TraceLinks and baselines remain untouched).
        decomposition_link_type = LinkType.DECOMPOSES.value

        result = DecompositionResultDTO(parent_id=requirement_id)

        # SYSTEMAUDIT_2026-08-27 P1-9: derive the child's V-model cascade level
        # from the parent instead of leaving it NULL. Decomposition is by
        # definition a move one level down the cascade (RequirementLevel: the
        # stored integer IS the level), so the value is knowable here — and
        # this method is the dominant creator of Requirements, which is why
        # ``level`` used to be NULL for practically the whole corpus (see the
        # level-vocabulary sections of the SE-Auditor rule modules).
        #
        # Two cases deliberately keep NULL rather than guessing:
        #   * parent.level is NULL — every Requirement decomposed before this
        #     change. Inventing a level for the child would fabricate a
        #     cascade position from no evidence and would make the new CONS-P11
        #     rule audit derived data against derived data.
        #   * parent is already at L4_PRESENTATION — the cascade has no tier
        #     below it. Clamping to L4 would emit a child at the *same* level
        #     as its parent, i.e. a self-inflicted CONS-P11 finding on every
        #     such decomposition; NULL ("not assigned") is the honest answer.
        parent_level = parent_req.level
        child_level: Optional[int]
        if parent_level is None or parent_level >= RequirementLevel.L4_PRESENTATION:
            child_level = None
        else:
            child_level = parent_level + 1

        with TransactionContextManager():
            for idx, child_data in enumerate(children):
                child_req = self.create_requirement(
                    workspace_id=workspace_id,
                    title=child_data.get("title", ""),
                    ctx=ctx,
                    description=child_data.get("description", ""),
                    parent_id=parent_req.artifact_id,
                    level=child_level,
                )
                result.children.append(RequirementDTO.from_orm(child_req))

                # IF-AS-INT-002: create TraceLink using configured type.
                #
                # Best-effort, historically: a missing 'decomposes' link no
                # longer hides the hierarchy from the SE-Auditor since issue
                # #395 made root/leaf classification read the reciprocal
                # 'derives-from' edge too, so a failure here degrades the
                # graph without breaking it. Logged at warning (not debug):
                # it is still a defect worth seeing in production logs.
                try:
                    tl = self._trace_link_service.create_trace_link(
                        source_id=UUID(str(parent_req.artifact_id)),
                        target_id=UUID(str(child_req.artifact_id)),
                        link_type=decomposition_link_type,
                        ctx=ctx,
                    )
                    if hasattr(tl, "id"):
                        result.trace_link_ids.append(tl.id)
                except Exception:
                    logger.warning(
                        "RequirementService.decompose: '%s' TraceLink %s -> %s "
                        "could not be created; the derivation hierarchy will "
                        "rest on the 'derives-from' link alone.",
                        decomposition_link_type,
                        parent_req.artifact_id,
                        child_req.artifact_id,
                        exc_info=True,
                    )

                # Issue #395: the reciprocal 'derives-from' link (child ->
                # parent). TRACE-P5 explicitly requires the pair — "a
                # Requirement decomposed via 'decomposes' must carry a
                # matching 'derives-from' back to that parent" — and
                # TRACE-P1b requires every Requirement to have an outgoing
                # 'derives-from'. Emitting only 'decomposes' meant the tool's
                # own guided "Ableiten" flow produced two blocking
                # SE-Auditor findings per derived Requirement and made
                # baseline creation impossible without manual repair. This
                # mirrors ArchitectureDecomposeService._link_node, which has
                # always emitted all three links (allocated-to, decomposes,
                # derives-from) for the AI decomposition path.
                #
                # Deliberately NOT wrapped in the best-effort try above (F2 of
                # the #395 review): sharing that scope would let a failure
                # here commit the 'decomposes' half of the pair on its own —
                # precisely the state TRACE-P5 reports as a BLOCKER, produced
                # silently by the very code meant to prevent it. The
                # back-link is a correctness precondition of this method, so
                # it propagates and the surrounding TransactionContextManager
                # rolls the whole decomposition back. Same reasoning as the
                # allocation block below.
                #
                # No backfill ships with this change (F6 of the #395 review):
                # Requirements derived before it still carry 'decomposes'
                # without the back-link and keep reporting TRACE-P5. That is
                # intentional — TRACE-P5 has a deterministic, automatic
                # remediation (RequirementDecompositionDerivationRemediation,
                # "Anpassen" in the audit dashboard) that creates exactly this
                # link from the finding's own endpoints, so existing data is
                # repairable per finding without a migration.
                derives = self._trace_link_service.create_trace_link(
                    source_id=UUID(str(child_req.artifact_id)),
                    target_id=UUID(str(parent_req.artifact_id)),
                    link_type=LinkType.DERIVES_FROM.value,
                    ctx=ctx,
                )
                if hasattr(derives, "id"):
                    result.trace_link_ids.append(derives.id)

                # REQ-L1-043: Allocation to ArchitectureElements. Not caught: a
                # caller that explicitly passes target_architecture_elements
                # expects the allocation to actually happen (REQ-L1-042), so
                # NotFoundError/ValidationError must propagate rather than be
                # silently swallowed — otherwise "derive" could create the
                # child requirement while its mandatory allocation silently
                # fails.
                if target_architecture_elements is not None:
                    target_arch_id = target_architecture_elements[idx]
                    alloc_link = self._trace_link_service.allocate(
                        requirement_id=child_req.id,
                        architecture_element_id=target_arch_id,
                        ctx=ctx,
                    )
                    if hasattr(alloc_link, "id"):
                        result.trace_link_ids.append(alloc_link.id)

        return result

    @staticmethod
    def _decompose_via_llm(
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Call LlmAdapter to generate child requirements.

        The parent requirement's ``title`` / ``content`` are forwarded so the
        provider embeds the real requirement text into the prompt instead of
        only the opaque UUID (REQ-046).

        ADR-L3-AS002-03: explicit LlmNotConfiguredError if LLM unavailable.
        REQ-L2-AS-013 / REQ-L2-AS-024.
        """
        from llm_adapter.services import decompose_requirement

        response = decompose_requirement(
            requirement_id=requirement_id,
            title=title,
            content=content,
        )

        if "error" in response:
            code = response["error"].get("code", "")
            if "NOT_CONFIGURED" in code:
                raise LlmNotConfiguredError(
                    "LLM not configured — cannot decompose requirement automatically"
                )
            raise ValueError(
                f"LLM decomposition failed: {response['error'].get('message', response)}"
            )

        # Parse the LLM result (may be a task_id for async)
        # Structural validation: expect list of {title, description}
        raw_children = response.get("children") or response.get("result", {}).get(
            "children", []
        )
        if not isinstance(raw_children, list):
            raise ValueError(
                "LLM returned unexpected decomposition structure; expected 'children' list"
            )

        validated: List[Dict[str, Any]] = []
        for item in raw_children:
            if not isinstance(item, dict) or "title" not in item:
                raise ValueError(
                    "Structurally invalid LLM child requirement — missing 'title'"
                )
            validated.append({"title": item["title"], "description": item.get("description", "")})

        return validated

    # ---------- LLM Validation (REQ-L2-AS-013) ----------

    def validate_requirement(self, requirement_id: UUID, ctx: AuthContext) -> Dict[str, Any]:
        """Validate a Requirement using the LlmAdapter.

        REQ-L2-AS-013: returns structured result or raises LlmNotConfiguredError.
        """
        self._set_tenant_context(ctx)

        from llm_adapter.services import validate_artifact

        # REQ-046: fetch the requirement so the provider embeds its real text
        # into the prompt instead of only the opaque UUID. A missing row simply
        # degrades to an id-only prompt (title/content stay None).
        req = (
            Requirement.objects.filter(id=requirement_id)
            .only("id", "title", "description")
            .first()
        )
        result = validate_artifact(
            artifact_id=str(requirement_id),
            title=req.title if req is not None else None,
            content=(req.description or "") if req is not None else None,
        )
        if isinstance(result, dict) and "error" in result:
            code = result["error"].get("code", "")
            if "NOT_CONFIGURED" in code:
                raise LlmNotConfiguredError("LLM not configured")
            raise ValueError(result["error"].get("message", str(result)))

        # validate_artifact() returns an LlmResult dataclass on success (see
        # its docstring) -- serialise it into a plain dict instead of a
        # Python repr string, which API/MCP consumers can't parse (#576).
        if is_dataclass(result) and not isinstance(result, type):
            return asdict(result)
        return result if isinstance(result, dict) else {"result": str(result)}

    def check_consistency(
        self, workspace_id: UUID, ctx: AuthContext
    ) -> Dict[str, Any]:
        """Check consistency across a workspace's requirements via the LlmAdapter.

        REQ-089: wires the previously unreachable ``check_consistency``
        capability into the application layer — before this, the LlmAdapter
        exposed it but no service or MCP tool ever invoked it.

        REQ-046: forwards each requirement's real title/content as artifact
        summary dicts so the provider embeds the artifact text into the
        consistency prompt instead of only opaque IDs.

        The capability is asynchronous: it returns a ``{"task_id": ...}`` dict
        immediately; poll the outcome via ``llm_adapter.services.get_task_status``.
        """
        self._set_tenant_context(ctx)

        from llm_adapter.services import check_consistency as _llm_check_consistency

        rows = (
            Requirement.objects.filter(artifact__workspace_id=workspace_id)
            # Phase 0: outdate() mirrors into `status`, not `lifecycle_status`.
            .exclude(status="outdated")
            .only("id", "title", "description")
        )
        artifacts = [
            {"id": str(r.id), "title": r.title, "content": r.description or ""}
            for r in rows
        ]
        result = _llm_check_consistency(str(workspace_id), artifacts=artifacts)
        if isinstance(result, dict) and "error" in result:
            code = result["error"].get("code", "")
            if "NOT_CONFIGURED" in code:
                raise LlmNotConfiguredError("LLM not configured")
            raise ValueError(result["error"].get("message", str(result)))

        # GH-796: record which tenant dispatched this task_id so
        # get_consistency_status() can enforce ownership on every poll --
        # the Celery result backend itself has no concept of tenant.
        task_id = result.get("task_id") if isinstance(result, dict) else None
        if task_id:
            cache.set(
                f"{_CONSISTENCY_TASK_TENANT_CACHE_PREFIX}:{task_id}",
                str(ctx.tenant_id),
                _CONSISTENCY_TASK_TENANT_TTL_SECONDS,
            )

        return result if isinstance(result, dict) else {"result": str(result)}

    def get_consistency_status(self, task_id: str, ctx: AuthContext) -> Dict[str, Any]:
        """Poll the outcome of a previously dispatched ``check_consistency`` task.

        GH-796: ``check_consistency`` returned a ``task_id`` with no way for a
        caller to ever retrieve the result -- the LlmAdapter's generic
        ``get_task_status`` existed but was never wired to this capability.
        Tenant-scoped the same way as
        ``BundleCompressionService.get_compression_status`` (ADR-03): an
        unknown or foreign-tenant task_id is deliberately reported as
        ``status="not_found"`` so a cross-tenant probe cannot even learn
        "this task_id exists but isn't mine".
        """
        self._set_tenant_context(ctx)

        from llm_adapter.services import get_task_status as _llm_get_task_status

        owning_tenant_id = cache.get(
            f"{_CONSISTENCY_TASK_TENANT_CACHE_PREFIX}:{task_id}"
        )
        if owning_tenant_id is None or owning_tenant_id != str(ctx.tenant_id):
            return {"task_id": task_id, "status": "not_found"}

        status = _llm_get_task_status(task_id)
        return status if isinstance(status, dict) else {"result": str(status)}


__all__ = [
    "RequirementService",
    "RequirementDTO",
    "DecompositionResultDTO",
    "SimilarRequirementDTO",
    "PgVectorUnavailableError",
]
