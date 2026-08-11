"""
COMP-AS-N1 ArchitectureDecomposeService — KI-Copilot N1 (`architecture.decompose`).

UMSETZUNGSPLAN_SYSENG_2.0.md §3.1 + §4 Phase 4a. The most architecturally
involved copilot: it recursively decomposes a selected ArchitectureElement
(Subsystem) into child elements, generates a derived Requirement per child, and
wires the full internal trace-link set — all under a strict **Draft-Staging**
discipline (§3.1, Korrektur 4).

Two-phase, human-in-the-loop flow (no direct commit):

  1. :meth:`generate_draft` — the LLM proposes a decomposition tree in a
     **non-persistent** draft object (zero DB writes). Returned to the caller /
     UI for a diff-style review.
  2. :meth:`commit_draft` — after explicit confirmation the whole draft is
     persisted in **one transaction**; a partial failure rolls the entire batch
     back (no orphaned architecture element without its requirements).

Key architectural decisions (documented here as the ADR-01 single entry point):

  * **Draft state = response/frontend state, NOT server-persisted** (§4 Phase 4a
    migration note prefers the simpler variant). ``generate_draft`` returns the
    full draft; the client echoes it back to ``commit_draft``. No new table, no
    migration, no TTL/cleanup job. ``commit_draft`` re-validates every endpoint
    through the existing validated domain services (tenant scoping + SE endpoint
    semantics) and re-audits the result, so a tampered draft cannot bypass the
    invariants.
  * **RuleEngine check = post-commit-in-transaction, with rollback** (not a
    simulated pre-commit check). The RuleEngine reads ORM rows; simulating an
    un-persisted graph in memory would fork its query logic. Instead the draft
    is persisted inside the atomic block, the *real* RuleEngine runs against the
    now-visible rows (forced to the ``extended`` tier so ARCH-003/TRACE-P4/P5
    are all active regardless of the workspace's own tier), and any BLOCKER
    touching a newly created artifact raises :class:`DecompositionAuditError` —
    which rolls the whole transaction back. This simultaneously satisfies the
    "commit is transactional" and "N1 output passes ARCH-003/TRACE-P4/P5"
    acceptance criteria with one mechanism.
  * **N1 explicitly creates the ``derives-from`` link** (unlike the raw
    ``RequirementService.decompose()``, which only emits ``decomposes`` +
    ``allocated-to``). TRACE-P5 requires every decomposed child requirement to
    carry a ``derives-from`` back to its parent; emitting it here is what makes
    N1's output pass the auditor by construction rather than needing an Adopt
    step afterwards.
  * **Preset gate lives in this Layer-2 facade** (single entry point): N1 is
    available only at ``standard``/``extended`` rigor, never ``minimal``. Both
    phases gate, so REST and MCP are covered uniformly.

Precondition: the selected element must already have at least one
``allocated-to`` Requirement (the derivation anchor). Without a parent
requirement to derive from, ARCH-003 could never be satisfied for the generated
level, so the service refuses up front with a clear :class:`ValidationError`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import ArchitectureElement, Requirement, TraceLink
from persistence.transactions import TransactionContextManager
from traceability.audit import Finding, RuleEngine, Severity
from traceability.audit.registry import ARCH_003, TRACE_P4, TRACE_P5
from traceability.types import LinkType

from application.audit_service import AuditService
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Rule ids N1 output is contractually required to pass (acceptance criterion,
# UMSETZUNGSPLAN_SYSENG_2.0.md §4 Phase 4a). Post-commit verification fails the
# commit iff one of these fires on a newly created artifact.
_N1_VERIFICATION_RULES = frozenset({ARCH_003, TRACE_P4, TRACE_P5})

# The verification always runs at the strictest tier so ARCH-003 and TRACE-P5
# (extended-only in RULE_PRESET_MAP) are active even for a standard-tier
# workspace — N1 output must satisfy them regardless of the workspace preset.
_VERIFICATION_TIER = "extended"

# Bounds on the generated tree so a single draft cannot explode into an
# unbounded transaction (§3.1 blast-radius concern).
_MAX_BREADTH = 5
_MAX_DEPTH = 3

# Prompt template for the recursive decomposition (llm_adapter capability
# ``arch_decompose_tree``). Kept here as a module constant — N1 does not read a
# per-tenant PromptTemplate row (no new slot / migration); the mock provider
# ignores the text and answers deterministically from the structured context.
ARCH_DECOMPOSE_PROMPT_TEMPLATE = (
    "Decompose the architecture element '{element_title}' into {breadth} "
    "child elements across {depth} level(s). For each child element propose a "
    "concise title, a description, and a single derived requirement (title, "
    "description, rationale) that the child element must satisfy. Return a JSON "
    "array of nodes, each optionally carrying a nested 'children' array."
)


class DecompositionNotAvailableError(PermissionDeniedError):
    """Raised when N1 is invoked in a ``minimal``-rigor workspace.

    Subclasses :class:`PermissionDeniedError` so the REST layer maps it to 403
    and the MCP layer surfaces it as FEATURE_NOT_ENABLED — N1 is a
    preset-gated feature, not an authorisation failure per se, but "not
    available in this preset" is the closest existing envelope.
    """


class DecompositionAuditError(ValidationError):
    """Raised when the committed draft fails ARCH-003/TRACE-P4/P5.

    Carries the offending findings so the caller can explain *why* the commit
    was rolled back. Subclasses :class:`ValidationError` → HTTP 422.
    """

    def __init__(self, message: str, findings: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.findings = findings


# ---------------------------------------------------------------------------
# Draft DTOs (JSON-serialisable — no persistence).
# ---------------------------------------------------------------------------


@dataclass
class DraftRequirement:
    """A proposed derived Requirement for one draft node."""

    title: str
    description: str = ""
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DraftRequirement":
        return cls(
            title=str((data or {}).get("title", "")),
            description=str((data or {}).get("description", "")),
            rationale=str((data or {}).get("rationale", "")),
        )


@dataclass
class DraftNode:
    """One proposed (ArchitectureElement + derived Requirement) pair.

    ``temp_id`` is a client-side draft identifier (stable within one draft);
    ``parent_temp_id`` is ``None`` for a direct child of the selected element,
    or another node's ``temp_id`` for deeper recursion levels.
    """

    temp_id: str
    parent_temp_id: Optional[str]
    title: str
    description: str
    element_type: str
    requirement: DraftRequirement

    def to_dict(self) -> dict:
        return {
            "temp_id": self.temp_id,
            "parent_temp_id": self.parent_temp_id,
            "title": self.title,
            "description": self.description,
            "element_type": self.element_type,
            "requirement": self.requirement.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DraftNode":
        temp_id = str((data or {}).get("temp_id", "")).strip()
        if not temp_id:
            raise ValidationError("Draft node is missing 'temp_id'.")
        title = str((data or {}).get("title", "")).strip()
        if not title:
            raise ValidationError(f"Draft node '{temp_id}' is missing 'title'.")
        parent = data.get("parent_temp_id")
        return cls(
            temp_id=temp_id,
            parent_temp_id=str(parent) if parent else None,
            title=title,
            description=str(data.get("description", "")),
            element_type=str(data.get("element_type") or "component"),
            requirement=DraftRequirement.from_dict(data.get("requirement") or {}),
        )


@dataclass
class DecompositionDraft:
    """The full, non-persistent proposal returned by :meth:`generate_draft`."""

    workspace_id: str
    root_element_id: str
    parent_requirement_id: str
    provider: str
    degraded: bool
    nodes: List[DraftNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "root_element_id": self.root_element_id,
            "parent_requirement_id": self.parent_requirement_id,
            "provider": self.provider,
            "degraded": self.degraded,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DecompositionDraft":
        if not isinstance(data, dict):
            raise ValidationError("Draft payload must be an object.")
        root_element_id = str(data.get("root_element_id", "")).strip()
        parent_requirement_id = str(data.get("parent_requirement_id", "")).strip()
        if not root_element_id or not parent_requirement_id:
            raise ValidationError(
                "Draft is missing 'root_element_id' or 'parent_requirement_id'."
            )
        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise ValidationError("Draft must contain a non-empty 'nodes' list.")
        return cls(
            workspace_id=str(data.get("workspace_id", "")),
            root_element_id=root_element_id,
            parent_requirement_id=parent_requirement_id,
            provider=str(data.get("provider", "")),
            degraded=bool(data.get("degraded", False)),
            nodes=[DraftNode.from_dict(n) for n in raw_nodes],
        )


@dataclass
class CommitResult:
    """Outcome of a successful :meth:`commit_draft`."""

    root_element_id: str
    created_element_ids: List[str] = field(default_factory=list)
    created_requirement_ids: List[str] = field(default_factory=list)
    created_link_ids: List[str] = field(default_factory=list)
    verified_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "committed": True,
            "root_element_id": self.root_element_id,
            "created_element_ids": self.created_element_ids,
            "created_requirement_ids": self.created_requirement_ids,
            "created_link_ids": self.created_link_ids,
            "verified_rules": sorted(self.verified_rules),
            "counts": {
                "elements": len(self.created_element_ids),
                "requirements": len(self.created_requirement_ids),
                "links": len(self.created_link_ids),
            },
        }


class ArchitectureDecomposeService(ServiceBase):
    """Single-Entry-Point facade for the N1 architecture-decompose copilot."""

    def __init__(
        self,
        architecture_service=None,
        requirement_service=None,
        trace_link_service=None,
        engine: Optional[RuleEngine] = None,
    ) -> None:
        # Deferred imports keep the module import graph acyclic (these services
        # import back into application/*).
        from application.architecture_service import ArchitectureService
        from application.requirement_service import RequirementService
        from application.trace_link_service import TraceLinkService

        self._architecture = architecture_service or ArchitectureService()
        self._requirements = requirement_service or RequirementService()
        self._trace = trace_link_service or TraceLinkService()
        self._engine = engine or RuleEngine()

    # ------------------------------------------------------------------
    # Preset gate (single entry point)
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_preset_allows(workspace_id: str | UUID) -> str:
        """Return the workspace tier, refusing ``minimal`` (§3.1 preset gate).

        Reuses :meth:`AuditService.resolve_tier` (the preset SSOT), which never
        returns ``minimal`` on a lookup glitch — so only a genuinely
        minimal-rigor workspace is blocked.
        """
        tier = AuditService.resolve_tier(workspace_id)
        if tier == "minimal":
            raise DecompositionNotAvailableError(
                "architecture.decompose (N1) is not available in the 'minimal' "
                "rigor preset; switch the workspace to 'standard' or 'extended'."
            )
        return tier

    # ------------------------------------------------------------------
    # Phase 1 — generate draft (no persistence)
    # ------------------------------------------------------------------

    def generate_draft(
        self,
        ctx: AuthContext,
        element_id: UUID | str,
        *,
        breadth: int = 2,
        depth: int = 1,
    ) -> DecompositionDraft:
        """Propose a recursive decomposition for *element_id* (no DB writes).

        Args:
            ctx: Authenticated, tenant-scoped context.
            element_id: The ArchitectureElement (Subsystem) to decompose.
            breadth: Children per level (clamped to 1..``_MAX_BREADTH``).
            depth: Recursion depth (clamped to 1..``_MAX_DEPTH``).

        Returns:
            A :class:`DecompositionDraft` for review — nothing is persisted.

        Raises:
            DecompositionNotAvailableError: Workspace is minimal-rigor.
            NotFoundError: The element does not exist for this tenant.
            ValidationError: The element has no allocated anchor requirement.
        """
        self._set_tenant_context(ctx)

        element = (
            ArchitectureElement.objects.select_related("artifact")
            .filter(id=element_id)
            .first()
        )
        if element is None:
            raise NotFoundError(f"ArchitectureElement {element_id} not found")

        workspace_id = str(element.artifact.workspace_id)
        self._assert_preset_allows(workspace_id)

        anchor = self._resolve_anchor_requirement(element)
        if anchor is None:
            raise ValidationError(
                "The selected architecture element has no allocated requirement "
                "to derive from. Allocate a requirement to it before running "
                "architecture.decompose (the derived requirements need a parent "
                "to satisfy ARCH-003/TRACE-P5)."
            )

        breadth = max(1, min(int(breadth), _MAX_BREADTH))
        depth = max(1, min(int(depth), _MAX_DEPTH))

        raw_tree, provider_name, degraded = self._complete_tree(
            element_title=element.title,
            breadth=breadth,
            depth=depth,
            artifact_id=str(element.artifact_id),
        )
        nodes = self._flatten_tree(raw_tree)
        if not nodes:
            raise ValidationError(
                "The LLM returned no decomposition nodes for this element."
            )

        return DecompositionDraft(
            workspace_id=workspace_id,
            root_element_id=str(element.id),
            parent_requirement_id=str(anchor.id),
            provider=provider_name,
            degraded=degraded,
            nodes=nodes,
        )

    # ------------------------------------------------------------------
    # Phase 2 — commit draft (one transaction, verified, rollback on failure)
    # ------------------------------------------------------------------

    def commit_draft(
        self, ctx: AuthContext, draft: DecompositionDraft
    ) -> CommitResult:
        """Persist *draft* atomically, verify it, and roll back on any failure.

        Args:
            ctx: Authenticated, tenant-scoped context (must have write role).
            draft: The reviewed draft (as returned by :meth:`generate_draft` and
                echoed back by the client).

        Returns:
            A :class:`CommitResult` describing what was created.

        Raises:
            DecompositionNotAvailableError: Workspace is minimal-rigor.
            PermissionDeniedError: Caller lacks write permission.
            NotFoundError: The root element or anchor requirement is gone.
            ValidationError: The draft is structurally invalid.
            DecompositionAuditError: The committed graph fails ARCH-003/TRACE-P4/P5
                (the transaction is rolled back — no orphans remain).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        root_element = (
            ArchitectureElement.objects.select_related("artifact")
            .filter(id=draft.root_element_id)
            .first()
        )
        if root_element is None:
            raise NotFoundError(
                f"ArchitectureElement {draft.root_element_id} not found"
            )
        workspace_id = str(root_element.artifact.workspace_id)
        self._assert_preset_allows(workspace_id)

        anchor = (
            Requirement.objects.select_related("artifact")
            .filter(id=draft.parent_requirement_id)
            .first()
        )
        if anchor is None:
            raise NotFoundError(
                f"Anchor Requirement {draft.parent_requirement_id} not found"
            )
        if str(anchor.artifact.workspace_id) != workspace_id:
            raise ValidationError(
                "Anchor requirement and root element are in different workspaces."
            )

        result = CommitResult(root_element_id=str(root_element.id))
        # temp_id -> (architecture_element_id, requirement_id) for parent lookup.
        created: Dict[str, Tuple[UUID, UUID]] = {}
        # Issue #366: Requirement PK -> backing Artifact id. create_requirement's
        # ``parent_id`` addresses the *Artifact* tree (see
        # RequirementService.decompose, which passes ``parent_req.artifact_id``),
        # while _resolve_parents works in the Requirement PK space. Without this
        # translation the derived requirements were created with a NULL
        # Artifact.parent and artifact.get_tree reported an empty subtree.
        req_artifact_ids: Dict[UUID, UUID] = {anchor.id: anchor.artifact_id}
        new_artifact_ids: set[str] = set()

        with TransactionContextManager():
            for node in draft.nodes:
                parent_element_id, parent_req_id = self._resolve_parents(
                    node, root_element, anchor, created
                )
                child_element = self._architecture.create_architecture_element(
                    workspace_id=UUID(workspace_id),
                    title=node.title,
                    ctx=ctx,
                    description=node.description,
                    element_type=node.element_type,
                    parent_id=parent_element_id,
                )
                child_req = self._requirements.create_requirement(
                    workspace_id=UUID(workspace_id),
                    title=node.requirement.title or node.title,
                    ctx=ctx,
                    description=node.requirement.description,
                    parent_id=req_artifact_ids.get(parent_req_id),
                )
                req_artifact_ids[child_req.id] = child_req.artifact_id
                created[node.temp_id] = (child_element.id, child_req.id)
                result.created_element_ids.append(str(child_element.id))
                result.created_requirement_ids.append(str(child_req.id))
                # Match keys for the post-commit finding filter. Findings mix id
                # spaces: TRACE-P4 references ArchitectureElement PKs, ARCH-003
                # mixes an element PK with a Requirement artifact id, TRACE-P5
                # uses Requirement artifact ids. Register every id a finding
                # could name for a newly created node so none slips the filter.
                new_artifact_ids.add(str(child_element.id))
                new_artifact_ids.add(str(child_element.artifact_id))
                new_artifact_ids.add(str(child_req.id))
                new_artifact_ids.add(str(child_req.artifact_id))

                self._link_node(
                    ctx,
                    result,
                    child_req_id=child_req.id,
                    child_element_id=child_element.id,
                    parent_req_id=parent_req_id,
                )

            # --- post-commit-in-transaction verification (rollback on BLOCKER) ---
            self._verify_or_rollback(
                workspace_id=workspace_id,
                tenant_id=str(ctx.tenant_id),
                new_artifact_ids=new_artifact_ids,
            )
            result.verified_rules = sorted(_N1_VERIFICATION_RULES)

        return result

    # ------------------------------------------------------------------
    # Internal — linking
    # ------------------------------------------------------------------

    def _link_node(
        self,
        ctx: AuthContext,
        result: CommitResult,
        *,
        child_req_id: UUID,
        child_element_id: UUID,
        parent_req_id: UUID,
    ) -> None:
        """Emit the full internal link set for one committed node.

        Three links per node, mirroring the SE decomposition semantics:
          * ``allocated-to``  : child requirement -> child element
          * ``decomposes``    : parent requirement -> child requirement
          * ``derives-from``  : child requirement -> parent requirement
        The ``derives-from`` link is what makes the output pass TRACE-P5 (and,
        together with the allocation, ARCH-003) by construction.

        Deliberately **no** link is emitted for the parent-element ->
        child-element edge (issue #365). Architecture hierarchy is an FK tree
        (``ArchitectureElement.parent``, mirrored onto ``Artifact.parent`` so
        ``artifact.get_tree`` can walk it — issue #366), not a TraceLink:
        ``traceability.types.SE_LINK_SEMANTICS`` restricts ``derives-from`` to
        Requirement/StakeholderNeed endpoints, and
        ``CrossCuttingToolGroup._handle_change_impact`` walks the FK tree
        explicitly for exactly this reason. Emitting a redundant link here
        would add a *fourth* hierarchy representation instead of removing one.
        """
        alloc = self._trace.allocate(
            requirement_id=child_req_id,
            architecture_element_id=child_element_id,
            ctx=ctx,
        )
        self._record_link(result, alloc)

        decomposes = self._trace.create_trace_link(
            source_id=parent_req_id,
            target_id=child_req_id,
            link_type=LinkType.DECOMPOSES.value,
            ctx=ctx,
        )
        self._record_link(result, decomposes)

        derives = self._trace.create_trace_link(
            source_id=child_req_id,
            target_id=parent_req_id,
            link_type=LinkType.DERIVES_FROM.value,
            ctx=ctx,
        )
        self._record_link(result, derives)

    @staticmethod
    def _record_link(result: CommitResult, link: Any) -> None:
        link_id = getattr(link, "id", None)
        if link_id is not None:
            result.created_link_ids.append(str(link_id))

    @staticmethod
    def _resolve_parents(
        node: DraftNode,
        root_element: ArchitectureElement,
        anchor: Requirement,
        created: Dict[str, Tuple[UUID, UUID]],
    ) -> Tuple[UUID, UUID]:
        """Return (parent_element_id, parent_requirement_id) for *node*.

        Top-level nodes (``parent_temp_id is None``) hang off the selected root
        element and derive from the anchor requirement. Deeper nodes reference a
        sibling node that must already have been created (pre-order guarantee).
        """
        if node.parent_temp_id is None:
            return root_element.id, anchor.id
        parent = created.get(node.parent_temp_id)
        if parent is None:
            raise ValidationError(
                f"Draft node '{node.temp_id}' references unknown or out-of-order "
                f"parent '{node.parent_temp_id}'."
            )
        return parent

    # ------------------------------------------------------------------
    # Internal — verification
    # ------------------------------------------------------------------

    def _verify_or_rollback(
        self, *, workspace_id: str, tenant_id: str, new_artifact_ids: set[str]
    ) -> None:
        """Run the RuleEngine and raise (→ rollback) on any relevant BLOCKER.

        Runs at the ``extended`` tier so ARCH-003/TRACE-P4/P5 are all active,
        then keeps only BLOCKER findings for those three rules that touch a
        newly created artifact — pre-existing, unrelated violations elsewhere in
        the workspace must not fail an otherwise-correct N1 commit.
        """
        engine_result = self._engine.run(
            tier=_VERIFICATION_TIER,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )
        offending: List[Finding] = [
            f
            for f in engine_result.findings
            if f.rule_id in _N1_VERIFICATION_RULES
            and f.severity is Severity.BLOCKER
            and new_artifact_ids.intersection(f.artifact_ids)
        ]
        if offending:
            findings = [f.to_dict() for f in offending]
            rules = sorted({f.rule_id for f in offending})
            raise DecompositionAuditError(
                "The generated decomposition failed SE-Auditor verification "
                f"({', '.join(rules)}); the commit was rolled back and nothing "
                "was persisted.",
                findings=findings,
            )

    # ------------------------------------------------------------------
    # Internal — anchor + LLM plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_anchor_requirement(
        element: ArchitectureElement,
    ) -> Optional[Requirement]:
        """Return the first Requirement allocated to *element*, or None.

        ``allocated-to`` links point Requirement (source) -> ArchitectureElement
        Artifact (target). The first (lowest-id) allocated requirement is chosen
        deterministically as the derivation anchor.
        """
        source_ids = list(
            TraceLink.objects.filter(
                target_id=element.artifact_id,
                link_type=LinkType.ALLOCATED_TO.value,
            ).values_list("source_id", flat=True)
        )
        if not source_ids:
            return None
        return (
            Requirement.objects.select_related("artifact")
            .filter(artifact_id__in=source_ids)
            .order_by("id")
            .first()
        )

    def _complete_tree(
        self, *, element_title: str, breadth: int, depth: int, artifact_id: str
    ) -> Tuple[list, str, bool]:
        """Call the LLM provider for a decomposition tree (graceful degradation).

        Returns ``(parsed_tree, provider_name, degraded)``. On any provider
        error it degrades to the credential-free deterministic mock so the draft
        flow never crashes (§4 Phase 4a: "mit mock ... kein Crash").

        Code review finding: this call bypassed REQ-106 (per-tenant daily LLM
        token budget) and the LlmAuditLog trail entirely -- it called
        provider.complete() directly with neither an is_over_daily_limit()
        check beforehand nor a LlmAuditLogger.log_llm_call()/
        record_token_usage() call after, unlike every other free-form LLM
        flow in this codebase (AiDerivationService._complete,
        BundleCompressionService._call_provider). Both are now applied here,
        mirroring those call sites' pattern exactly.

        Raises:
            LlmResponseError: The tenant's daily LLM token budget is already
                exceeded (checked before the real-provider call only -- the
                mock-fallback path is exempt, matching every other flow's
                graceful-degradation contract, ADR-02).
        """
        from django.conf import settings

        from application.ai_derivation_service import LlmResponseError
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.token_tracking import is_over_daily_limit, record_token_usage

        prompt = ARCH_DECOMPOSE_PROMPT_TEMPLATE.format(
            element_title=element_title, breadth=breadth, depth=depth
        )
        context = {
            "element_title": element_title,
            "breadth": breadth,
            "depth": depth,
        }
        provider_name = getattr(settings, "LLM_PROVIDER", "mock")
        audit_logger = LlmAuditLogger()
        degraded = False
        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "architecture.decompose: provider %s unavailable, using mock. %s",
                provider_name,
                error,
            )
            provider = MockLlmProvider()
            provider_name = "mock"
            degraded = True

        if not degraded and is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="arch_decompose_tree",
                artifact_id=artifact_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise LlmResponseError(
                "Daily LLM token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        try:
            raw = provider.complete(
                prompt, purpose="arch_decompose_tree", context=context
            )
        except Exception as error:
            if degraded:
                raise
            logger.warning(
                "architecture.decompose: provider %s call failed: %s",
                provider_name,
                error,
            )
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="arch_decompose_tree",
                artifact_id=artifact_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise LlmResponseError(
                f"architecture.decompose LLM call failed: {error}"
            ) from error

        if not degraded:
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="arch_decompose_tree",
                artifact_id=artifact_id,
                token_usage=None,
                success=True,
                error=None,
            )
            record_token_usage(
                provider=provider_name, capability="arch_decompose_tree", input_tokens=0
            )
        return self._parse_tree(raw), provider_name, degraded

    @staticmethod
    def _parse_tree(raw: str) -> list:
        """Parse the provider completion into a JSON list, tolerating fences."""
        from application.ai_derivation_service import MOCK_FALLBACK_MARKER

        text = (raw or "").strip()
        if text.startswith(MOCK_FALLBACK_MARKER):
            text = text[len(MOCK_FALLBACK_MARKER):].strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationError(
                "The LLM decomposition response was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise ValidationError(
                "The LLM decomposition response was not a JSON array."
            )
        return parsed

    def _flatten_tree(self, raw_tree: list) -> List[DraftNode]:
        """Flatten a nested provider tree into pre-order :class:`DraftNode` list.

        Assigns stable ``temp_id``s (``n1``, ``n1.1`` …) and wires
        ``parent_temp_id`` so :meth:`commit_draft` can process parents before
        children in a single pass.
        """
        nodes: List[DraftNode] = []

        def _walk(items: list, parent_temp_id: Optional[str], prefix: str) -> None:
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                temp_id = f"{prefix}{i + 1}"
                title = str(item.get("title", "")).strip()
                if not title:
                    continue
                nodes.append(
                    DraftNode(
                        temp_id=temp_id,
                        parent_temp_id=parent_temp_id,
                        title=title,
                        description=str(item.get("description", "")),
                        element_type=str(item.get("element_type") or "component"),
                        requirement=DraftRequirement.from_dict(
                            item.get("requirement") or {}
                        ),
                    )
                )
                children = item.get("children")
                if isinstance(children, list) and children:
                    _walk(children, temp_id, f"{temp_id}.")

        _walk(raw_tree, None, "n")
        return nodes


__all__ = [
    "ArchitectureDecomposeService",
    "DecompositionDraft",
    "DraftNode",
    "DraftRequirement",
    "CommitResult",
    "DecompositionNotAvailableError",
    "DecompositionAuditError",
    "ARCH_DECOMPOSE_PROMPT_TEMPLATE",
]
