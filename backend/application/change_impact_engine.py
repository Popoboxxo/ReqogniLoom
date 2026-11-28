"""Deterministic change-impact chain engine (S4.1–S4.5, S4.7).

Spec: ``docs/superpowers/specs/2026-11-28-change-artefakt-wirkketten-design.md``
§4.2.3–§4.2.5 and §4.3. Plan slice: ``S4`` (S4.1–S4.5 + the idempotency core of
S4.7).

This is the Layer-2 service that turns one :class:`ChangeRequest`'s change set
into an auditable :class:`ChangeImpactRun` with deterministic findings and
effect chains. It is deliberately *not* an LLM feature: severity is derived
exclusively by :func:`application.change_impact_severity.classify_severity`, and
the advisory LLM annotation (S4.6), Celery triggers (S4.8/S4.12) and the
REST/MCP trigger surface (S4.9) live outside this slice.

Design notes and documented deviations
--------------------------------------
* **Hierarchy edges are built here, not via ``application.tier_compute``.**
  ``tier_compute`` does not expose a generic graph provider: it is
  Requirement-tier-specific (it computes ``tier_key``/``level`` for
  Requirements from *their* parent links plus ``allocates``; it does not walk
  ``Document``/``WorkItem``, and it is the single writer of a persisted column,
  so reusing it as a read-only edge source would distort it). This module
  therefore reads the **same authoritative source** directly —
  ``Artifact.parent_id`` for the hierarchy-bearing types
  (:data:`HIERARCHY_ARTIFACT_TYPES`) — and emits ``link_type="hierarchy"``,
  ``origin="deterministic"`` edges. That is a documented deviation from the
  plan's "über ``application.tier_compute``" wording, chosen because the plan's
  own S4.4 note ("``tier_compute`` um ``Document``/``WorkItem`` erweitern")
  would otherwise require turning a tier calculator into a generic graph
  provider.
* **Semantic edges are opt-in and never blocking.** ``ContextEdge`` rows are
  read read-only (no projector call, no write), only when the effective policy
  allows semantic edges, and they are always ``origin="semantic"`` — a finding
  sourced from them can never be ``blocking`` (enforced by
  ``classify_severity`` and a DB constraint).
* **Content hashing does not use ``Artifact.version``.** The fingerprint is a
  content image, not a version counter: a no-op save must not make a run
  stale, and a suspect/bulk update must not stay invisible. ``content_hash``
  is computed over ``baseline.state_capture.capture_states`` minus the keys
  ``version``/``status``/``suspect``/``baseline``; the workflow state, lifecycle
  status and suspect flag are hashed separately.
* **Idempotency** is anchored by the partial unique index
  ``uq_change_impact_run_cr_graph_fp`` *and* a Postgres advisory lock over the
  change-request UUID for the duration of the writing transaction, so two
  concurrent ``analyze`` calls cannot both insert.

leaf_id : COMP-AS-021
req_id  : REQ-216
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final
from uuid import UUID, uuid4

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError
from application.change_impact_policy import (
    MAX_DEPTH_KEY,
    MAX_NODES_KEY,
    MAX_PATHS_PER_FINDING,
    MIN_WEIGHT_KEY,
    SEMANTIC_EDGES_KEY,
    TRIGGER_CHOICES,
    clamp_parameters,
    policy_hash,
    resolved_policy,
)
from application.change_impact_severity import classify_severity
from application.models import (
    ChangeImpactChain,
    ChangeImpactFinding,
    ChangeImpactRun,
    ChangeRequest,
    ChangeRequestAffectedItem,
)
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple
from link_types.catalog import resolve_catalog
from persistence.artifact_backing import model_for
from persistence.models import Artifact, TraceLink
from workflow import state_reader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Algorithm version persisted on every run; part of both fingerprints.
ALGORITHM_VERSION: Final = "v1"

#: Content-hash exclusions (spec §4.3.5). ``version`` is the optimistic-lock
#: counter (a no-op save bumps it), ``status``/``suspect`` are hashed on their
#: own axis, ``baseline`` is provenance and must never enter the hash.
CONTENT_HASH_EXCLUDED_KEYS: Final[frozenset[str]] = frozenset(
    {"version", "status", "suspect", "baseline"}
)

#: Artifact types whose ``Artifact.parent_id`` tree is a propagation edge.
HIERARCHY_ARTIFACT_TYPES: Final[frozenset[str]] = frozenset(
    {"Requirement", "ArchitectureElement", "Document", "WorkItem"}
)

#: Required incident link types for an ``add`` change-set item (spec §4.3.3).
ADD_REQUIRED_LINK_TYPES: Final[frozenset[str]] = frozenset(
    {"allocated-to", "decomposes"}
)

#: S2's warning code for an ``add`` root without a mandatory trace edge. The
#: run model has no warnings column (spec §4.2.3), so this slice logs it and
#: keeps the constant named for S2's warning enum instead of polluting the
#: gate with a synthetic finding.
WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE: Final = "change_set_item_without_trace"

#: Truncation reasons written to ``ChangeImpactRun.truncated_reason``.
TRUNCATION_DEPTH: Final = "depth"
TRUNCATION_NODES: Final = "nodes"
TRUNCATION_PATHS: Final = "paths"
TRUNCATION_SCOPE: Final = "scope"

_QUANTUM: Final = Decimal("0.0001")
_ZERO: Final = Decimal("0")
_ONE: Final = Decimal("1")

#: Change actions (mirrors ``ChangeRequestAffectedItem.change_action``).
ACTION_ADD: Final = "add"
ACTION_MODIFY: Final = "modify"
ACTION_REMOVE: Final = "remove"


# ---------------------------------------------------------------------------
# Pure fingerprint helpers (reusable by the S5 gate read)
# ---------------------------------------------------------------------------


def _canonical_json(payload: Any) -> str:
    """Return canonical JSON (sorted keys, no whitespace, ASCII)."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_content_hash(state: Mapping[str, Any]) -> str:
    """Hash the curated content fields of one captured artifact state.

    Excludes :data:`CONTENT_HASH_EXCLUDED_KEYS` so a no-op save (which bumps
    ``version``) does not change the hash, while a real content edit does.
    An empty mapping returns ``""`` — callers treat that as a capture failure.
    """
    filtered = {
        key: value
        for key, value in state.items()
        if key not in CONTENT_HASH_EXCLUDED_KEYS
    }
    if not filtered:
        return ""
    return _sha256(_canonical_json(filtered))


def compute_catalog_hash(catalog: Mapping[str, Mapping[str, Any]]) -> str:
    """Hash the effective link-type catalog (definitions, sorted by key)."""
    normalised = {
        str(key): dict(value or {}) for key, value in sorted(catalog.items())
    }
    return _sha256(_canonical_json(normalised))


def compute_affected_items_hash(roots: Iterable["NodeState"]) -> str:
    """Hash the change-set roots only (``artifact_id``/content/lifecycle)."""
    return _sha256(_canonical_json(sorted(_root_tuple(n) for n in roots)))


def compute_graph_fingerprint(
    *,
    algorithm_version: str,
    roots: Sequence["NodeState"],
    nodes: Sequence["NodeState"],
    edges: Iterable[Sequence[str]],
    hierarchy_edges: Iterable[Sequence[str]],
    semantic_edges: Iterable[Sequence[str]] = (),
    catalog_hash: str,
    policy_hash_value: str,
) -> str:
    """Hash the full run evidence (roots, neighbourhood, edges, catalog, policy).

    ``baseline_id`` and ``Artifact.version`` are deliberately absent — the
    baseline link is attached on approval and would otherwise invalidate the
    run it is checking (spec §4.3.5).
    """
    payload = {
        "algorithm_version": algorithm_version,
        "catalog_hash": catalog_hash,
        "policy_hash": policy_hash_value,
        "roots": sorted(_root_tuple(n) for n in roots),
        "nodes": sorted(_node_tuple(n) for n in nodes),
        "edges": sorted([str(part) for part in edge] for edge in edges),
        "hierarchy_edges": sorted(
            [str(part) for part in edge] for edge in hierarchy_edges
        ),
        "semantic_edges": sorted(
            [str(part) for part in edge] for edge in semantic_edges
        ),
    }
    return _sha256(_canonical_json(payload))


def compute_gate_fingerprint(
    *,
    algorithm_version: str,
    roots: Sequence["NodeState"],
    nodes: Sequence["NodeState"],
    edges: Iterable[Sequence[str]],
    hierarchy_edges: Iterable[Sequence[str]],
    semantic_edges: Iterable[Sequence[str]] = (),
    catalog_hash: str,
    policy_hash_value: str,
) -> str:
    """Hash the gate re-check image over the stored frontier (spec §4.3.5).

    Identical topology to :func:`compute_graph_fingerprint`, but every node
    carries ``suspect`` too: that is the axis a gate must not miss, and it is
    also why the gate read never needs a full re-traversal.
    """
    payload = {
        "algorithm_version": algorithm_version,
        "catalog_hash": catalog_hash,
        "policy_hash": policy_hash_value,
        "roots": sorted(_root_tuple(n) for n in roots),
        "nodes": sorted(_gate_node_tuple(n) for n in nodes),
        "edges": sorted([str(part) for part in edge] for edge in edges),
        "hierarchy_edges": sorted(
            [str(part) for part in edge] for edge in hierarchy_edges
        ),
        "semantic_edges": sorted(
            [str(part) for part in edge] for edge in semantic_edges
        ),
    }
    return _sha256(_canonical_json(payload))


def compute_path_hash(hops: Iterable[Any]) -> str:
    """Hash a canonical effect-chain path.

    Each hop contributes ``artifact_id|link_id|link_type|direction`` with
    lowercase UUIDs and a fixed hop order. Accepts :class:`Hop` instances or
    the stored ``path`` dicts, so the S5 gate read and the writer agree by
    construction.
    """
    parts: list[str] = []
    for hop in hops:
        if isinstance(hop, Mapping):
            artifact_id = hop["artifact_id"]
            link_id = hop["link_id"]
            link_type = hop["link_type"]
            direction = hop["direction"]
        else:
            artifact_id = hop.target_id
            link_id = hop.link_id
            link_type = hop.link_type
            direction = hop.direction
        parts.append(
            "|".join(
                (
                    str(artifact_id).lower(),
                    str(link_id).lower(),
                    str(link_type),
                    str(direction),
                )
            )
        )
    return _sha256("\n".join(parts))


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeState:
    """Fingerprint-relevant state of one visited artifact."""

    artifact_id: str
    artifact_type: str
    content_hash: str
    lifecycle_status: str
    workflow_state: str = ""
    suspect: bool = False


def _root_tuple(node: NodeState) -> list[str]:
    return [node.artifact_id, node.content_hash, node.lifecycle_status]


def _node_tuple(node: NodeState) -> list[str]:
    return [
        node.artifact_id,
        node.content_hash,
        node.lifecycle_status,
        node.workflow_state,
    ]


def _gate_node_tuple(node: NodeState) -> list[str]:
    return [
        node.artifact_id,
        node.content_hash,
        node.lifecycle_status,
        node.workflow_state,
        "1" if node.suspect else "0",
    ]


@dataclass(frozen=True)
class Hop:
    """One oriented propagation step."""

    target_id: str
    link_id: str
    link_type: str
    direction: str
    weight: Decimal
    suspect: bool = False
    coverage_relevant: bool = False
    origin: str = "deterministic"

    def path_entry(self) -> dict[str, Any]:
        """Return the stored ``path`` element for this hop."""
        return {
            "artifact_id": self.target_id,
            "link_id": self.link_id,
            "link_type": self.link_type,
            "direction": self.direction,
            "suspect": self.suspect,
            "weight": str(self.weight),
        }


@dataclass
class PathState:
    """A partial chain from a root to its current node."""

    hops: tuple[Hop, ...] = ()
    weight: Decimal = _ONE
    action: str = ACTION_MODIFY
    root_id: str = ""
    path_hash: str = ""

    @property
    def origin(self) -> str:
        return (
            "semantic"
            if any(hop.origin == "semantic" for hop in self.hops)
            else "deterministic"
        )

    @property
    def suspect(self) -> bool:
        return any(hop.suspect for hop in self.hops)

    @property
    def coverage_relevant(self) -> bool:
        return any(hop.coverage_relevant for hop in self.hops)

    @property
    def via_link_types(self) -> list[str]:
        return sorted({hop.link_type for hop in self.hops})


@dataclass
class _ObservedEdges:
    """Every edge seen while traversing, for the two fingerprints."""

    links: dict[str, tuple[str, str, str, str, str]] = field(default_factory=dict)
    hierarchy: set[tuple[str, str]] = field(default_factory=set)
    semantic: dict[str, tuple[str, str, str, str, str]] = field(default_factory=dict)


@dataclass
class _Roots:
    """Resolved change-set roots and their provenance."""

    ids: list[str]
    source: str
    gate_eligible: bool
    actions: dict[str, str]


@dataclass
class _Traversal:
    """Traversal output, before fingerprints/persistence."""

    roots: list[str]
    depth_of: dict[str, int]
    paths_by_node: dict[str, list[PathState]]
    observed: _ObservedEdges
    truncated: bool
    truncated_reason: str


@dataclass
class _Plan:
    """Everything known about the graph before the fingerprints are hashed."""

    roots: _Roots
    traversal: _Traversal
    node_meta: dict[str, tuple[str, str]]
    policy: dict[str, Any]
    catalog: dict[str, dict[str, Any]]
    include_semantic: bool


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ChangeImpactEngine(ServiceBase):
    """Run one deterministic change-impact analysis for a change request."""

    #: Persisted on every run and part of both fingerprints.
    ALGORITHM_VERSION = ALGORITHM_VERSION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        cr_id: UUID,
        ctx: Any,
        *,
        root_item_ids: list[UUID | str] | None = None,
        max_depth: int | None = None,
        max_nodes: int | None = None,
        include_semantic: bool | None = None,
        include_llm: bool | None = None,
        force: bool = False,
        trigger: str = "manual",
    ) -> ChangeImpactRun:
        """Run (or reuse) a change-impact analysis and return its run.

        Args:
            cr_id: Change request to analyse; must be inside ``ctx``'s tenant.
            ctx: Authenticated caller (write role required).
            root_item_ids: Analyze an explicit artifact set instead of the
                change set (a ``draft`` pre-analysis). ``None`` uses
                ``ChangeRequestAffectedItem``.
            max_depth: Requested traversal depth; the policy is a ceiling, so
                this can only narrow it.
            max_nodes: Requested node cap; likewise ceiling-limited.
            include_semantic: Requested semantic-edge opt-in; the policy
                ceiling decides whether it can be enabled at all.
            include_llm: Accepted for API symmetry with the transport layer;
                LLM annotation is S4.6 and is not executed here.
            force: Create a new run even when an identical one exists.
            trigger: ``manual``/``on_submit``/``on_write``/``scheduled``.

        Returns:
            The persisted :class:`ChangeImpactRun`; an existing run when
            ``(change_request, graph_fingerprint)`` is unchanged and
            ``force=False``.

        Raises:
            NotFoundError: No such change request in the caller's tenant.
            ValidationError: Unknown trigger, or explicit roots outside the
                change request's workspace.
            PermissionDeniedError: The caller lacks write authority.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if trigger not in TRIGGER_CHOICES:
            raise ValidationError(
                f"Unknown change-impact trigger {trigger!r}; "
                f"expected one of {list(TRIGGER_CHOICES)}"
            )

        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        # #1716: the run is a write, so the CR's item-level rule set applies
        # exactly as it does for update/delete in ChangeRequestService.
        self._assert_item_write_permission(
            ctx, cr.artifact_id, workspace_id=cr.workspace_id
        )

        policy = resolved_policy(
            tenant_id=ctx.tenant_id, workspace_id=cr.workspace_id
        )
        effective = policy["effective"]
        parameters, _clamped = clamp_parameters(
            effective=effective,
            max_depth=max_depth,
            max_nodes=max_nodes,
            include_semantic=include_semantic,
            include_llm=include_llm,
        )
        # S4.6 (LLM annotation) is out of this slice: ``clamp_parameters``
        # resolves and clamps ``change_impact.llm_annotation`` so the transport
        # contract is complete, but nothing calls a provider here.
        catalog = resolve_catalog(cr.workspace_id)
        roots = self._resolve_roots(
            cr, ctx=ctx, root_item_ids=root_item_ids
        )

        plan = self._build_plan(
            cr=cr,
            roots=roots,
            parameters=parameters,
            policy=policy,
            catalog=catalog,
            include_semantic=bool(parameters[SEMANTIC_EDGES_KEY]),
        )

        self._warn_add_items_without_trace(cr=cr, roots=roots)

        content_states, capture_error = self._capture_states(
            plan=plan, tenant_id=ctx.tenant_id
        )
        if capture_error is not None:
            return self._persist_failed(
                cr=cr,
                ctx=ctx,
                plan=plan,
                trigger=trigger,
                force=force,
                error=capture_error,
            )

        return self._persist(
            cr=cr,
            ctx=ctx,
            plan=plan,
            content_states=content_states,
            trigger=trigger,
            force=force,
        )

    # ------------------------------------------------------------------
    # Roots
    # ------------------------------------------------------------------

    def _resolve_roots(
        self,
        cr: ChangeRequest,
        *,
        ctx: Any,
        root_item_ids: list[UUID | str] | None,
    ) -> _Roots:
        """Resolve the traversal roots and their gate eligibility."""
        affected = list(
            ChangeRequestAffectedItem.objects.filter(
                change_request_id=cr.id, tenant_id=cr.tenant_id
            ).values_list("item_id", "change_action")
        )
        affected_ids = sorted({str(item_id) for item_id, _action in affected})
        actions = {
            str(item_id): (action or ACTION_MODIFY)
            for item_id, action in affected
        }

        if root_item_ids is None:
            # Only Artifact-backed change-set members can be traversal roots; a
            # trace-link/glossary change-set entry is not a graph node. Dropping
            # it (instead of failing) keeps the run usable and is reflected in
            # ``gate_eligible`` (set equality below then fails, correctly).
            artifact_ids = set(
                str(value)
                for value in Artifact.unscoped.filter(
                    tenant_id=cr.tenant_id,
                    workspace_id=cr.workspace_id,
                    id__in=[UUID(value) for value in affected_ids],
                ).values_list("id", flat=True)
            )
            roots = [value for value in affected_ids if value in artifact_ids]
            gate_eligible = bool(roots) and set(roots) == set(affected_ids)
            return _Roots(
                ids=roots,
                source=ChangeImpactRun.RootsSource.CHANGE_SET,
                gate_eligible=gate_eligible,
                actions={value: actions.get(value, ACTION_MODIFY) for value in roots},
            )

        requested: list[str] = []
        for value in root_item_ids:
            try:
                requested.append(str(UUID(str(value))))
            except (TypeError, ValueError):
                raise ValidationError(
                    "root_item_ids must contain artifact UUIDs"
                ) from None
        requested = sorted(set(requested))

        found = set(
            str(value)
            for value in Artifact.unscoped.filter(
                tenant_id=cr.tenant_id,
                workspace_id=cr.workspace_id,
                id__in=[UUID(value) for value in requested],
            ).values_list("id", flat=True)
        )
        missing = [value for value in requested if value not in found]
        if missing:
            # No id is echoed: a foreign id must not become an existence oracle.
            raise ValidationError(
                f"{len(missing)} root artifact(s) are not part of this workspace"
            )

        return _Roots(
            ids=requested,
            source=ChangeImpactRun.RootsSource.EXPLICIT,
            gate_eligible=False,
            actions={value: ACTION_MODIFY for value in requested},
        )

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def _build_plan(
        self,
        *,
        cr: ChangeRequest,
        roots: _Roots,
        parameters: Mapping[str, Any],
        policy: Mapping[str, Any],
        catalog: Mapping[str, dict[str, Any]],
        include_semantic: bool,
    ) -> _Plan:
        """Build the bounded, frontier-batched traversal."""
        max_depth = int(parameters[MAX_DEPTH_KEY])
        max_nodes = int(parameters[MAX_NODES_KEY])
        # ``min_weight`` is not a call parameter (policy only); it is part of
        # the effective policy and therefore of ``policy_hash``.
        min_weight = _to_decimal(policy["effective"][MIN_WEIGHT_KEY])

        truncated = False
        truncated_reason = ""

        root_ids = sorted(roots.ids)
        if len(root_ids) > max_nodes:
            root_ids = root_ids[:max_nodes]
            truncated = True
            truncated_reason = TRUNCATION_NODES
        elif len(root_ids) != len(roots.ids):
            truncated = True
            truncated_reason = TRUNCATION_SCOPE

        root_meta = self._artifact_meta(
            root_ids, tenant_id=cr.tenant_id, workspace_id=cr.workspace_id
        )
        # A change-set member that vanished between the change-set read and the
        # traversal is a scope truncation, not a hard failure.
        missing_roots = [value for value in root_ids if value not in root_meta]
        if missing_roots:
            root_ids = [value for value in root_ids if value in root_meta]
            truncated = True
            truncated_reason = truncated_reason or TRUNCATION_SCOPE

        observed = _ObservedEdges()
        depth_of: dict[str, int] = {}
        paths_by_node: dict[str, list[PathState]] = {}
        root_set = set(root_ids)

        current: dict[str, list[PathState]] = {}
        for root_id in root_ids:
            depth_of[root_id] = 0
            initial = PathState(
                hops=(),
                weight=_ONE,
                action=roots.actions.get(root_id, ACTION_MODIFY),
                root_id=root_id,
            )
            initial.path_hash = compute_path_hash(initial.hops)
            paths_by_node[root_id] = [initial]
            current[root_id] = [initial]

        depth = 0
        while current and depth < max_depth:
            depth += 1
            hops_by_node = self._expansion_hops(
                sorted(current),
                tenant_id=cr.tenant_id,
                workspace_id=cr.workspace_id,
                catalog=catalog,
                include_semantic=include_semantic,
                observed=observed,
            )
            node_meta = self._artifact_meta(
                sorted(
                    {
                        hop.target_id
                        for hops in hops_by_node.values()
                        for hop in hops
                    }
                ),
                tenant_id=cr.tenant_id,
                workspace_id=cr.workspace_id,
            )

            next_paths: dict[str, list[PathState]] = {}
            for node_id in sorted(current):
                hops = hops_by_node.get(node_id, ())
                if not hops:
                    continue
                for path in current[node_id]:
                    for hop in hops:
                        if hop.target_id not in node_meta:
                            # Outside the CR workspace: enforced edge fence.
                            continue
                        if hop.target_id in root_set:
                            continue
                        if not _hop_allowed(hop, path.action):
                            continue
                        known_depth = depth_of.get(hop.target_id)
                        if known_depth is not None and known_depth < depth:
                            continue
                        if hop.target_id not in next_paths and (
                            len(depth_of) + len(next_paths) >= max_nodes
                        ):
                            truncated = True
                            truncated_reason = (
                                truncated_reason or TRUNCATION_NODES
                            )
                            continue
                        new_weight = path.weight * hop.weight
                        if new_weight > _ONE:
                            new_weight = _ONE
                        if new_weight < min_weight:
                            continue
                        candidate = PathState(
                            hops=path.hops + (hop,),
                            weight=new_weight,
                            action=path.action,
                            root_id=path.root_id,
                        )
                        candidate.path_hash = compute_path_hash(candidate.hops)
                        next_paths.setdefault(hop.target_id, []).append(candidate)

            if not next_paths:
                break

            current = {}
            for node_id in sorted(next_paths):
                kept, dropped = _keep_best(
                    next_paths[node_id], MAX_PATHS_PER_FINDING
                )
                if dropped:
                    truncated = True
                    truncated_reason = truncated_reason or TRUNCATION_PATHS
                depth_of[node_id] = depth
                paths_by_node[node_id] = kept
                current[node_id] = kept

            if depth >= max_depth and current:
                truncated = True
                truncated_reason = truncated_reason or TRUNCATION_DEPTH

        node_meta_all = dict(root_meta)
        node_meta_all.update(
            self._artifact_meta(
                sorted(set(depth_of) - set(root_meta)),
                tenant_id=cr.tenant_id,
                workspace_id=cr.workspace_id,
            )
        )

        traversal = _Traversal(
            roots=root_ids,
            depth_of=depth_of,
            paths_by_node=paths_by_node,
            observed=observed,
            truncated=truncated,
            truncated_reason=truncated_reason,
        )
        return _Plan(
            roots=_Roots(
                ids=root_ids,
                source=roots.source,
                gate_eligible=roots.gate_eligible
                and set(root_ids) == set(roots.ids),
                actions=roots.actions,
            ),
            traversal=traversal,
            node_meta={
                key: (value[0], value[1]) for key, value in node_meta_all.items()
            },
            policy=dict(policy),
            catalog=dict(catalog),
            include_semantic=include_semantic,
        )

    def _expansion_hops(
        self,
        frontier: Sequence[str],
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        catalog: Mapping[str, dict[str, Any]],
        include_semantic: bool,
        observed: _ObservedEdges,
    ) -> dict[str, list[Hop]]:
        """Return the allowed propagation hops leaving each frontier node.

        Three queries maximum (trace links, semantic edges, hierarchy children)
        regardless of the frontier size — the ``O(max_depth)`` guarantee.
        """
        frontier_ids = [UUID(value) for value in frontier]
        hops: dict[str, list[Hop]] = {value: [] for value in frontier}

        links = (
            TraceLink.unscoped.filter(
                tenant_id=tenant_id,
                source__workspace_id=workspace_id,
                target__workspace_id=workspace_id,
            )
            .filter(
                Q(source_id__in=frontier_ids) | Q(target_id__in=frontier_ids)
            )
            .values(
                "id",
                "source_id",
                "target_id",
                "link_type",
                "suspect_flagged_at",
            )
        )
        for link in links:
            definition = catalog.get(link["link_type"]) or {}
            rule = definition.get("suspect_rule", "none")
            if rule == "none":
                continue
            weight = _to_decimal(definition.get("impact_weight", 1.0))
            source_id = str(link["source_id"])
            target_id = str(link["target_id"])
            observed.links[str(link["id"])] = (
                str(link["id"]),
                str(link["link_type"]),
                source_id,
                target_id,
                _iso(link["suspect_flagged_at"]),
            )
            if rule == "target_change_flags_source":
                hop_from, hop_to, direction = target_id, source_id, "backward"
            elif rule in (
                "source_change_flags_target",
                "parent_change_flags_children",
            ):
                hop_from, hop_to, direction = source_id, target_id, "forward"
            else:  # pragma: no cover - catalog validates the four rules
                continue
            if hop_from not in hops:
                continue
            hops[hop_from].append(
                Hop(
                    target_id=hop_to,
                    link_id=str(link["id"]),
                    link_type=str(link["link_type"]),
                    direction=direction,
                    weight=weight,
                    suspect=link["suspect_flagged_at"] is not None,
                    coverage_relevant=bool(
                        definition.get("coverage_relevant", False)
                    ),
                    origin="deterministic",
                )
            )

        # Hierarchy union: Artifact.parent_id for the hierarchy-bearing types.
        for child in (
            Artifact.unscoped.filter(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                parent_id__in=frontier_ids,
                artifact_type__in=sorted(HIERARCHY_ARTIFACT_TYPES),
            ).values("id", "parent_id")
        ):
            parent_id = str(child["parent_id"])
            child_id = str(child["id"])
            observed.hierarchy.add((child_id, parent_id))
            if parent_id not in hops:
                continue
            hops[parent_id].append(
                Hop(
                    target_id=child_id,
                    link_id=parent_id,
                    link_type="hierarchy",
                    direction="hierarchy",
                    weight=_ONE,
                    suspect=False,
                    coverage_relevant=False,
                    origin="deterministic",
                )
            )

        if include_semantic:
            hops = self._add_semantic_hops(
                hops,
                frontier_ids=frontier_ids,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                observed=observed,
            )

        for node_id in hops:
            hops[node_id].sort(
                key=lambda hop: (hop.link_type, hop.target_id, hop.link_id)
            )
        return hops

    def _add_semantic_hops(
        self,
        hops: dict[str, list[Hop]],
        *,
        frontier_ids: Sequence[UUID],
        tenant_id: UUID,
        workspace_id: UUID,
        observed: _ObservedEdges,
    ) -> dict[str, list[Hop]]:
        """Add read-only ``ContextEdge`` hops (opt-in, never blocking)."""
        from context_graph.models import ContextEdge

        rows = (
            ContextEdge.unscoped.filter(
                tenant_id=tenant_id,
                source__workspace_id=workspace_id,
                target__workspace_id=workspace_id,
            )
            .filter(Q(source_id__in=frontier_ids) | Q(target_id__in=frontier_ids))
            .values(
                "id",
                "source_id",
                "target_id",
                "edge_kind",
                "origin",
                "confidence",
            )
        )
        for row in rows:
            source_id = str(row["source_id"])
            target_id = str(row["target_id"])
            observed.semantic[str(row["id"])] = (
                str(row["id"]),
                str(row["edge_kind"]),
                str(row["origin"]),
                source_id,
                target_id,
                f"{float(row['confidence'] or 0.0):.4f}",
            )
            weight = _to_decimal(row["confidence"] or 0.0)
            link_type = f"context:{row['edge_kind']}"
            # A soft edge is undirected; both directions are expanded, but for
            # ``remove`` they are filtered out by ``_hop_allowed``.
            for hop_from, hop_to in (
                (source_id, target_id),
                (target_id, source_id),
            ):
                if hop_from not in hops:
                    continue
                hops[hop_from].append(
                    Hop(
                        target_id=hop_to,
                        link_id=str(row["id"]),
                        link_type=link_type,
                        direction="semantic",
                        weight=weight,
                        suspect=False,
                        coverage_relevant=False,
                        origin="semantic",
                    )
                )
        return hops

    # ------------------------------------------------------------------
    # Capture + fingerprints
    # ------------------------------------------------------------------

    def _capture_states(
        self, *, plan: _Plan, tenant_id: UUID
    ) -> tuple[dict[str, NodeState], str | None]:
        """Capture every visited node's state; fail closed on incompleteness.

        ``capture_states`` silently skips missing rows and yields an empty
        workflow state outside a tenant context, so completeness is checked
        explicitly (spec §4.3.5).
        """
        ids = sorted(plan.traversal.depth_of)
        if not ids:
            return {}, None
        missing_meta = [value for value in ids if value not in plan.node_meta]
        if missing_meta:
            logger.warning(
                "Change-impact capture incomplete: %s visited node(s) have no "
                "artifact row",
                len(missing_meta),
            )
            return {}, "capture_incomplete"
        delta_index = [
            DeltaIndexTuple(item_id=value, version=0, entity_type="item")
            for value in ids
        ]
        states = capture_states(delta_index, tenant_id)
        if len(states) != len(ids):
            logger.warning(
                "Change-impact capture incomplete: %s of %s states",
                len(states),
                len(ids),
            )
            return {}, "capture_incomplete"

        workflow_states = self._workflow_states(
            {value: plan.node_meta[value][0] for value in ids},
            tenant_id=tenant_id,
        )
        nodes: dict[str, NodeState] = {}
        for value in ids:
            state = states[value]
            artifact_type, lifecycle_status = plan.node_meta[value]
            content_hash = compute_content_hash(state)
            workflow_state = workflow_states.get(value, "")
            if not content_hash or not workflow_state:
                logger.warning(
                    "Change-impact capture incomplete for %s "
                    "(content_hash=%r, workflow_state=%r)",
                    value,
                    content_hash,
                    workflow_state,
                )
                return {}, "capture_incomplete"
            nodes[value] = NodeState(
                artifact_id=value,
                artifact_type=artifact_type,
                content_hash=content_hash,
                lifecycle_status=lifecycle_status,
                workflow_state=workflow_state,
                suspect=bool(state.get("suspect", False)),
            )
        return nodes, None

    def _workflow_states(
        self, artifact_types: Mapping[str, str], *, tenant_id: UUID
    ) -> dict[str, str]:
        """Resolve the workflow state of every visited node, batched per type.

        ``capture_states`` carries ``status`` only for the types that had a
        mirror column; this resolves the authoritative state for *all* types
        through :mod:`workflow.state_reader` instead (two queries per type per
        run, independent of the node count).
        """
        by_type: dict[str, list[str]] = defaultdict(list)
        for artifact_id, artifact_type in artifact_types.items():
            by_type[artifact_type].append(artifact_id)

        resolved: dict[str, str] = {}
        for artifact_type in sorted(by_type):
            artifact_ids = by_type[artifact_type]
            try:
                initial = state_reader.initial_state(artifact_type)
            except KeyError:
                continue
            try:
                model = model_for(artifact_type)
            except KeyError:
                model = None

            entity_ids: dict[str, str] = {}
            if model is not None:
                entity_ids = {
                    str(artifact_id): str(entity_id)
                    for artifact_id, entity_id in model.unscoped.filter(
                        tenant_id=tenant_id,
                        artifact_id__in=[UUID(value) for value in artifact_ids],
                    ).values_list("artifact_id", "id")
                }
            states = (
                state_reader.current_states(
                    artifact_type, entity_ids.values(), tenant_id=tenant_id
                )
                if entity_ids
                else {}
            )
            for artifact_id in artifact_ids:
                entity_id = entity_ids.get(artifact_id)
                resolved[artifact_id] = (
                    states.get(entity_id) if entity_id else None
                ) or initial
        return resolved

    def _artifact_meta(
        self, ids: Sequence[str], *, tenant_id: UUID, workspace_id: UUID
    ) -> dict[str, tuple[str, str]]:
        """Return ``{artifact_id: (artifact_type, lifecycle_status)}``.

        The workspace filter is the CR workspace fence (defense in depth on top
        of the TraceLink endpoint filter).
        """
        if not ids:
            return {}
        return {
            str(row["id"]): (row["artifact_type"], row["lifecycle_status"])
            for row in Artifact.unscoped.filter(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                id__in=[UUID(value) for value in ids],
            ).values("id", "artifact_type", "lifecycle_status")
        }

    # ------------------------------------------------------------------
    # ``add`` warning
    # ------------------------------------------------------------------

    def _warn_add_items_without_trace(
        self, *, cr: ChangeRequest, roots: _Roots
    ) -> None:
        """Log ``change_set_item_without_trace`` for untraced ``add`` items.

        Deliberately no Finding and no gate impact: the run model has no
        warning channel, and a synthetic finding would pollute the gate. The
        code is S2's warning enum value (:data:`WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE`).
        """
        add_roots = [
            UUID(value)
            for value in roots.ids
            if roots.actions.get(value) == ACTION_ADD
        ]
        if not add_roots:
            return
        traced = set()
        for source_id, target_id, link_type in (
            TraceLink.unscoped.filter(
                tenant_id=cr.tenant_id,
                source__workspace_id=cr.workspace_id,
                target__workspace_id=cr.workspace_id,
                link_type__in=sorted(ADD_REQUIRED_LINK_TYPES),
            )
            .filter(Q(source_id__in=add_roots) | Q(target_id__in=add_roots))
            .values_list("source_id", "target_id", "link_type")
        ):
            traced.add(str(source_id))
            traced.add(str(target_id))
        for root in add_roots:
            if str(root) not in traced:
                logger.warning(
                    "%s: change-set item %s is 'add' without a "
                    "allocated-to/decomposes edge",
                    WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE,
                    root,
                )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(
        self,
        *,
        cr: ChangeRequest,
        ctx: Any,
        plan: _Plan,
        content_states: Mapping[str, NodeState],
        trigger: str,
        force: bool,
    ) -> ChangeImpactRun:
        """Compute the fingerprints and write run/findings/chains atomically."""
        traversal = plan.traversal
        nodes = [content_states[value] for value in sorted(content_states)]
        root_nodes = [
            content_states[value]
            for value in traversal.roots
            if value in content_states
        ]
        catalog_hash = compute_catalog_hash(plan.catalog)
        effective_policy_hash = policy_hash(plan.policy["effective"])

        edges = [observed for observed in traversal.observed.links.values()]
        hierarchy_edges = [
            (child, parent) for child, parent in traversal.observed.hierarchy
        ]
        semantic_edges = [
            observed for observed in traversal.observed.semantic.values()
        ]

        graph_fingerprint = compute_graph_fingerprint(
            algorithm_version=self.ALGORITHM_VERSION,
            roots=root_nodes,
            nodes=nodes,
            edges=edges,
            hierarchy_edges=hierarchy_edges,
            semantic_edges=semantic_edges,
            catalog_hash=catalog_hash,
            policy_hash_value=effective_policy_hash,
        )
        gate_fingerprint = compute_gate_fingerprint(
            algorithm_version=self.ALGORITHM_VERSION,
            roots=root_nodes,
            nodes=nodes,
            edges=edges,
            hierarchy_edges=hierarchy_edges,
            semantic_edges=semantic_edges,
            catalog_hash=catalog_hash,
            policy_hash_value=effective_policy_hash,
        )
        affected_items_hash = compute_affected_items_hash(root_nodes)

        finding_specs = self._finding_specs(plan=plan, states=content_states)

        with transaction.atomic():
            _acquire_change_request_lock(cr.id)

            if not force:
                existing = (
                    ChangeImpactRun.objects.filter(
                        change_request_id=cr.id,
                        graph_fingerprint=graph_fingerprint,
                        forced=False,
                        status__in=[
                            ChangeImpactRun.Status.PENDING,
                            ChangeImpactRun.Status.RUNNING,
                            ChangeImpactRun.Status.COMPLETED,
                        ],
                    )
                    .order_by("-created_at", "-id")
                    .first()
                )
                if existing is not None:
                    return existing

            predecessor = (
                ChangeImpactRun.objects.filter(
                    change_request_id=cr.id,
                    status=ChangeImpactRun.Status.COMPLETED,
                )
                .order_by("-created_at", "-id")
                .first()
            )
            inherited_findings, inherited_chains = self._inheritance_maps(
                predecessor
            )

            run = ChangeImpactRun.objects.create(
                tenant_id=ctx.tenant_id,
                change_request=cr,
                workspace_id=cr.workspace_id,
                baseline_id=cr.baseline_id,
                status=ChangeImpactRun.Status.RUNNING,
                trigger=trigger,
                algorithm_version=self.ALGORITHM_VERSION,
                root_item_ids=sorted(traversal.roots),
                roots_source=plan.roots.source,
                gate_eligible=plan.roots.gate_eligible,
                graph_fingerprint=graph_fingerprint,
                gate_fingerprint=gate_fingerprint,
                affected_items_hash=affected_items_hash,
                catalog_hash=catalog_hash,
                policy_hash=effective_policy_hash,
                visited_node_ids=sorted(traversal.depth_of),
                node_count=len(traversal.depth_of),
                edge_count=len(edges) + len(hierarchy_edges) + len(semantic_edges),
                path_count=0,
                truncated=traversal.truncated,
                truncated_reason=traversal.truncated_reason,
                include_semantic=plan.include_semantic,
                forced=bool(force),
                started_at=timezone.now(),
            )

            # Bulk inserts, not one INSERT per finding/chain: the persistence
            # cost must stay flat for a 500-node run (the traversal guarantee is
            # only half the story). ``AuditableModel`` assigns its UUID at
            # instantiation, so chains can reference the finding ids before the
            # rows are written.
            findings: list[ChangeImpactFinding] = []
            chains: list[ChangeImpactChain] = []
            for spec in finding_specs:
                inherited = inherited_findings.get(spec["artifact_id"])
                if inherited is not None and inherited.severity != spec["severity"]:
                    # A severity change re-opens the finding: a carried-over
                    # waiver must not open the gate after a weight/catalog change.
                    inherited = None
                carried = (
                    inherited is not None
                    and inherited.disposition
                    != ChangeImpactFinding.Disposition.OPEN
                )
                finding = ChangeImpactFinding(
                    id=uuid4(),
                    tenant_id=ctx.tenant_id,
                    run=run,
                    artifact_id=spec["artifact_id"],
                    entity_type=spec["entity_type"],
                    hop_distance=spec["hop_distance"],
                    weight=spec["weight"],
                    severity=spec["severity"],
                    origin=spec["origin"],
                    via_link_types=spec["via_link_types"],
                    chain_count=len(spec["paths"]),
                    disposition=(
                        inherited.disposition
                        if inherited is not None
                        else ChangeImpactFinding.Disposition.OPEN
                    ),
                    inherited_from_run_id=(
                        predecessor.id if carried else None
                    ),
                    decided_by_id=(
                        inherited.decided_by_id if carried else None
                    ),
                    decided_at=(inherited.decided_at if carried else None),
                    note=(inherited.note if carried else ""),
                )
                findings.append(finding)
                for path in spec["paths"]:
                    previous_chain = inherited_chains.get(
                        (spec["artifact_id"], spec["severity"], path.path_hash)
                    )
                    chain_carried = (
                        previous_chain is not None
                        and previous_chain.disposition is not None
                    )
                    chains.append(
                        ChangeImpactChain(
                            id=uuid4(),
                            tenant_id=ctx.tenant_id,
                            finding_id=finding.id,
                            root_artifact_id=path.root_id,
                            path_hash=path.path_hash,
                            path=[hop.path_entry() for hop in path.hops],
                            hop_distance=len(path.hops),
                            weight=_quantize(path.weight),
                            origin=path.origin,
                            via_link_types=path.via_link_types,
                            disposition=(
                                previous_chain.disposition
                                if previous_chain is not None
                                else None
                            ),
                            inherited_from_run_id=(
                                predecessor.id if chain_carried else None
                            ),
                            decided_by_id=(
                                previous_chain.decided_by_id
                                if chain_carried
                                else None
                            ),
                            decided_at=(
                                previous_chain.decided_at
                                if chain_carried
                                else None
                            ),
                            note=(
                                previous_chain.note if chain_carried else ""
                            ),
                        )
                    )

            ChangeImpactFinding.objects.bulk_create(findings, batch_size=200)
            ChangeImpactChain.objects.bulk_create(chains, batch_size=200)

            run.path_count = len(chains)
            run.status = ChangeImpactRun.Status.COMPLETED
            run.finished_at = timezone.now()
            run.save(
                update_fields=[
                    "path_count",
                    "status",
                    "finished_at",
                    "modified_at",
                ]
            )
            return run

    def _persist_failed(
        self,
        *,
        cr: ChangeRequest,
        ctx: Any,
        plan: _Plan,
        trigger: str,
        force: bool,
        error: str,
    ) -> ChangeImpactRun:
        """Write a ``failed`` run and persist no findings (fail-closed)."""
        traversal = plan.traversal
        with transaction.atomic():
            _acquire_change_request_lock(cr.id)
            run = ChangeImpactRun.objects.create(
                tenant_id=ctx.tenant_id,
                change_request=cr,
                workspace_id=cr.workspace_id,
                baseline_id=cr.baseline_id,
                status=ChangeImpactRun.Status.FAILED,
                trigger=trigger,
                algorithm_version=self.ALGORITHM_VERSION,
                root_item_ids=sorted(traversal.roots),
                roots_source=plan.roots.source,
                gate_eligible=False,
                visited_node_ids=sorted(traversal.depth_of),
                node_count=len(traversal.depth_of),
                edge_count=0,
                path_count=0,
                truncated=traversal.truncated,
                truncated_reason=traversal.truncated_reason,
                include_semantic=plan.include_semantic,
                forced=bool(force),
                error=error,
                started_at=timezone.now(),
                finished_at=timezone.now(),
            )
        logger.error(
            "Change-impact run %s failed for CR %s: %s", run.id, cr.id, error
        )
        return run

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    def _finding_specs(
        self, *, plan: _Plan, states: Mapping[str, NodeState]
    ) -> list[dict[str, Any]]:
        """Build the deterministic finding list (roots excluded)."""
        traversal = plan.traversal
        specs: list[dict[str, Any]] = []
        for artifact_id in sorted(traversal.depth_of):
            hop_distance = traversal.depth_of[artifact_id]
            if hop_distance < 1:
                continue
            paths = traversal.paths_by_node.get(artifact_id) or []
            if not paths:
                continue
            best = paths[0]
            state = states.get(artifact_id)
            if state is None:  # pragma: no cover - capture guarantees presence
                continue
            severity = classify_severity(
                weight=best.weight,
                hop_distance=hop_distance,
                coverage_relevant=best.coverage_relevant,
                suspect=best.suspect,
                origin=best.origin,
            )
            specs.append(
                {
                    "artifact_id": artifact_id,
                    "entity_type": state.artifact_type,
                    "hop_distance": hop_distance,
                    "weight": _quantize(best.weight),
                    "severity": severity,
                    "origin": best.origin,
                    "via_link_types": sorted(
                        {
                            link_type
                            for path in paths
                            for link_type in path.via_link_types
                        }
                    ),
                    "paths": paths,
                }
            )
        return specs

    def _inheritance_maps(
        self, predecessor: ChangeImpactRun | None
    ) -> tuple[dict[str, ChangeImpactFinding], dict[tuple[str, str, str], Any]]:
        """Return ``(findings_by_artifact, chains_by_(artifact, severity, hash))``.

        Dispositions of the last *completed* run are carried over only when
        ``(artifact_id, severity)`` (finding) resp. ``(artifact_id, severity,
        path_hash)`` (chain) are unchanged (spec §4.3.6).
        """
        if predecessor is None:
            return {}, {}
        findings = list(
            ChangeImpactFinding.objects.filter(run=predecessor).prefetch_related(
                "chains"
            )
        )
        findings_by_artifact = {
            finding.artifact_id: finding for finding in findings
        }
        chains: dict[tuple[str, str, str], Any] = {}
        for finding in findings:
            for chain in finding.chains.all():
                chains[
                    (finding.artifact_id, finding.severity, chain.path_hash)
                ] = chain
        return findings_by_artifact, chains


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal:
    """Return *value* as a ``Decimal`` clamped to ``[0, 1]``."""
    if isinstance(value, Decimal):
        number = value
    else:
        number = Decimal(str(value))
    if number < _ZERO:
        return _ZERO
    if number > _ONE:
        return _ONE
    return number


def _quantize(weight: Decimal) -> Decimal:
    """Clamp to ``[0, 1]`` and quantize to four decimal places."""
    return _to_decimal(weight).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _hop_allowed(hop: Hop, action: str) -> bool:
    """Apply the change-action semantics to one oriented hop.

    ``modify``/``add`` follow every catalog-oriented hop (which already covers
    both outgoing and incoming links, because the orientation may point either
    way). ``remove`` follows only incoming links — i.e. the hop where the
    current node is the link's target (``direction="backward"``).
    """
    if action == ACTION_REMOVE:
        return hop.direction == "backward"
    return True


def _path_sort_key(path: PathState) -> tuple[int, int, Decimal, str]:
    """Rank paths: shortest, then deterministic before semantic, then weight."""
    return (
        len(path.hops),
        0 if path.origin == "deterministic" else 1,
        -path.weight,
        path.path_hash,
    )


def _keep_best(
    paths: Sequence[PathState], limit: int
) -> tuple[list[PathState], bool]:
    """Deduplicate by ``path_hash`` and keep the best *limit* paths.

    Returns ``(kept, dropped)`` where ``dropped`` is True when a distinct path
    had to be discarded (the ``truncated_reason="paths"`` signal).
    """
    by_hash: dict[str, PathState] = {}
    for path in paths:
        current = by_hash.get(path.path_hash)
        if current is None or _path_sort_key(path) < _path_sort_key(current):
            by_hash[path.path_hash] = path
    ordered = sorted(by_hash.values(), key=_path_sort_key)
    return ordered[:limit], len(ordered) > limit


def _acquire_change_request_lock(cr_id: UUID) -> None:
    """Serialize concurrent runs for one change request.

    A transaction-scoped advisory lock over a 64-bit hash of the CR UUID. The
    partial unique index is the durable anchor; the lock turns the race into a
    deterministic reuse instead of an ``IntegrityError``.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [str(cr_id)],
        )


__all__ = [
    "ADD_REQUIRED_LINK_TYPES",
    "ALGORITHM_VERSION",
    "CONTENT_HASH_EXCLUDED_KEYS",
    "ChangeImpactEngine",
    "HIERARCHY_ARTIFACT_TYPES",
    "Hop",
    "NodeState",
    "PathState",
    "TRUNCATION_DEPTH",
    "TRUNCATION_NODES",
    "TRUNCATION_PATHS",
    "TRUNCATION_SCOPE",
    "WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE",
    "compute_affected_items_hash",
    "compute_catalog_hash",
    "compute_content_hash",
    "compute_gate_fingerprint",
    "compute_graph_fingerprint",
    "compute_path_hash",
]
