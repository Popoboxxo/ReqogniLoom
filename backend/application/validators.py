"""
ArchitectureElementInvariantValidator — hierarchy invariants I1-I4 (rigor-gated).

req_id : REQ-L1-044 (Invarianten-Validator I1-I4)

Enforces structural invariants on the ArchitectureElement hierarchy
(REQ-L1-041 parent_id) and on the allocated-to TraceLink structure
(REQ-L1-042).  Which invariants are active depends on the workspace's
rigor preset tier (Minimal / Standard / Extended):

    I1  no circular parent references (direct or transitive)   standard, extended
    I2  level ordering: parent.level < child.level              standard, extended
    I3  no dangling / cross-workspace parent references         all tiers
    I4  allocated-to must not target an ancestor of the source  extended

Design notes:
- The invariant/tier mapping is data-driven in RIGOR_INVARIANT_PRESETS.
  Following ADR-PC-02 (preset rules live in code, never in DB), this module
  is the runtime single source of truth.  The declarative concept mirror
  lives in .meta-config/project.yaml (architecture.rigor_presets).
  Deployments may override via settings.ARCHITECTURE_RIGOR_INVARIANTS.
- The active tier is resolved per workspace through FeatureGateService
  (COMP-PC-003) — the same mechanism that gates all other preset features.
- All checks are read-only; callers run them inside their own transaction.
- I1 runs before I2 by design: get_level() recurses through the parent
  chain and would not terminate on a corrupted (cyclic) hierarchy, while
  the I1 walk is guarded by a visited-set.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Mapping, Optional
from uuid import UUID

from application.base import ValidationError

# ---------------------------------------------------------------------------
# Invariant codes and rigor gating (REQ-L1-044)
# ---------------------------------------------------------------------------

INVARIANT_I1 = "I1"
INVARIANT_I2 = "I2"
INVARIANT_I3 = "I3"
INVARIANT_I4 = "I4"

ALL_INVARIANTS: FrozenSet[str] = frozenset(
    {INVARIANT_I1, INVARIANT_I2, INVARIANT_I3, INVARIANT_I4}
)

#: Default invariant sets per rigor tier — single source of truth at runtime.
RIGOR_INVARIANT_PRESETS: Mapping[str, FrozenSet[str]] = {
    "minimal": frozenset({INVARIANT_I3}),
    "standard": frozenset({INVARIANT_I1, INVARIANT_I2, INVARIANT_I3}),
    "extended": frozenset(
        {INVARIANT_I1, INVARIANT_I2, INVARIANT_I3, INVARIANT_I4}
    ),
}

#: Fallback tier when the workspace tier cannot be resolved.  Matches the
#: WorkspacePresetConfig bootstrap default (presets.gate).
_FALLBACK_TIER = "minimal"


def _get_rigor_invariant_presets() -> Mapping[str, FrozenSet[str]]:
    """Return the effective tier→invariants mapping.

    Reads the optional ``ARCHITECTURE_RIGOR_INVARIANTS`` Django setting
    (dict of tier name → iterable of invariant codes) and merges it over
    the built-in defaults.  Unknown settings values fall back silently to
    the defaults so a misconfiguration can never disable I3 everywhere
    by accident.
    """
    try:
        from django.conf import settings

        override = getattr(settings, "ARCHITECTURE_RIGOR_INVARIANTS", None)
    except Exception:  # pragma: no cover — settings not configured (tooling)
        override = None

    if not isinstance(override, dict):
        return RIGOR_INVARIANT_PRESETS

    merged = dict(RIGOR_INVARIANT_PRESETS)
    for tier, codes in override.items():
        try:
            merged[tier] = frozenset(codes) & ALL_INVARIANTS
        except TypeError:
            continue
    return merged


class ArchitectureElementInvariantValidator:
    """Rigor-gated invariant checks for the ArchitectureElement hierarchy.

    Instances are cheap and stateless apart from the enabled invariant set;
    construct one per validation via :meth:`for_workspace` (preferred, uses
    the workspace's active preset tier) or :meth:`for_tier`.

    Each ``check_iN`` method is self-gating: it becomes a no-op when the
    invariant is not enabled for the configured rigor level.
    """

    def __init__(self, enabled_invariants: Iterable[str]) -> None:
        self._enabled: FrozenSet[str] = frozenset(enabled_invariants)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def for_tier(cls, tier: str) -> "ArchitectureElementInvariantValidator":
        """Build a validator for a rigor *tier* name.

        Unknown tiers (e.g. custom presets) fall back to the "standard"
        invariant set — mid-rigor is the safest default for unknown input.
        """
        presets = _get_rigor_invariant_presets()
        enabled = presets.get(tier)
        if enabled is None:
            enabled = presets["standard"]
        return cls(enabled)

    @classmethod
    def for_workspace(
        cls, workspace_id: UUID | str | None
    ) -> "ArchitectureElementInvariantValidator":
        """Build a validator using the workspace's active preset tier.

        Resolution failures (missing workspace, unavailable persistence in
        unit-test contexts) fall back to the Minimal tier, matching the
        WorkspacePresetConfig bootstrap default.
        """
        tier = _FALLBACK_TIER
        if workspace_id is not None:
            try:
                from presets.gate import get_gate_service

                tier = get_gate_service().get_preset(str(workspace_id)).tier
            except Exception:
                tier = _FALLBACK_TIER
        return cls.for_tier(tier)

    # ------------------------------------------------------------------
    # Gating
    # ------------------------------------------------------------------

    def is_enabled(self, invariant: str) -> bool:
        """Return True if *invariant* (e.g. ``"I1"``) is active."""
        return invariant in self._enabled

    # ------------------------------------------------------------------
    # ORM seam — patched in unit tests
    # ------------------------------------------------------------------

    @staticmethod
    def _get_element(element_id):
        """Fetch an ArchitectureElement by primary key (or None)."""
        from persistence.models import ArchitectureElement

        return (
            ArchitectureElement.objects.select_related("artifact")
            .filter(id=element_id)
            .first()
        )

    # ------------------------------------------------------------------
    # I1 — no circular parent references (standard, extended)
    # ------------------------------------------------------------------

    def check_i1(
        self, element_id: Optional[UUID], parent_id: Optional[UUID]
    ) -> None:
        """Reject parent assignments that create a cycle (REQ-L1-044 I1).

        Walks the ancestor chain starting at *parent_id*.  Encountering
        *element_id* (or any already-visited node — a pre-existing corrupted
        cycle) raises ValidationError.  The visited-set guarantees
        termination even on corrupted data.
        """
        if not self.is_enabled(INVARIANT_I1) or parent_id is None:
            return

        visited: set = set()
        if element_id is not None:
            visited.add(element_id)

        current_id = parent_id
        while current_id is not None:
            if current_id in visited:
                raise ValidationError(
                    f"[I1] Circular parent reference detected: assigning "
                    f"parent {parent_id} to ArchitectureElement "
                    f"{element_id or parent_id} would close a cycle"
                )
            visited.add(current_id)
            current = self._get_element(current_id)
            current_id = current.parent_id if current is not None else None

    # ------------------------------------------------------------------
    # I2 — level ordering parent.level < child.level (standard, extended)
    # ------------------------------------------------------------------

    def check_i2(self, element, parent) -> None:
        """Enforce level ordering parent.level < child.level (REQ-L1-044 I2).

        Levels are derived via ``get_level()`` (REQ-L1-041).  The check is
        evaluated against the element's current level, i.e. re-parenting an
        element below a parent at an equal or deeper level is rejected at
        Standard/Extended rigor.

        No-op when the invariant is disabled or either side is missing
        (creation path: the element does not exist yet).
        """
        if not self.is_enabled(INVARIANT_I2) or element is None or parent is None:
            return

        parent_level = parent.get_level()
        child_level = element.get_level()
        if parent_level >= child_level:
            raise ValidationError(
                f"[I2] Level inconsistency for ArchitectureElement "
                f"{element.id}: parent level {parent_level} must be lower "
                f"than child level {child_level}"
            )

    # ------------------------------------------------------------------
    # I3 — no dangling / cross-workspace parent references (all tiers)
    # ------------------------------------------------------------------

    def check_i3(
        self,
        parent_id: Optional[UUID],
        workspace_id: UUID | str | None = None,
    ):
        """Validate that *parent_id* references a real element (REQ-L1-044 I3).

        Also rejects cross-workspace parent references when *workspace_id*
        is provided.  Returns the resolved parent element (or None) so
        callers can reuse it for the I2 check without a second query.
        """
        if parent_id is None:
            return None

        parent = self._get_element(parent_id)
        if not self.is_enabled(INVARIANT_I3):
            return parent

        if parent is None:
            raise ValidationError(
                f"[I3] Dangling parent reference: ArchitectureElement "
                f"{parent_id} does not exist"
            )
        if workspace_id is not None:
            parent_ws = getattr(parent.artifact, "workspace_id", None)
            if parent_ws is not None and str(parent_ws) != str(workspace_id):
                raise ValidationError(
                    f"[I3] Cross-workspace parent reference: parent "
                    f"{parent_id} belongs to workspace {parent_ws}, "
                    f"not {workspace_id}"
                )
        return parent

    # ------------------------------------------------------------------
    # I4 — allocated-to must not target an ancestor (extended)
    # ------------------------------------------------------------------

    def check_i4(self, source_element, target_element) -> None:
        """Reject allocated-to links onto an ancestor (REQ-L1-044 I4).

        An ArchitectureElement must not allocate to its own parent or any
        transitive ancestor — that would collapse the allocation structure.
        Walks the source's ancestor chain with a visited-set guard
        (pre-existing cycles are I1 territory and terminate the walk).
        """
        if (
            not self.is_enabled(INVARIANT_I4)
            or source_element is None
            or target_element is None
        ):
            return

        visited = {source_element.id}
        current_id = source_element.parent_id
        while current_id is not None:
            if current_id == target_element.id:
                raise ValidationError(
                    f"[I4] Invalid allocation: ArchitectureElement "
                    f"{source_element.id} cannot allocate to its ancestor "
                    f"{target_element.id}"
                )
            if current_id in visited:
                break  # corrupted cycle — detected and reported by I1
            visited.add(current_id)
            current = self._get_element(current_id)
            current_id = current.parent_id if current is not None else None

    # ------------------------------------------------------------------
    # Orchestration entry points
    # ------------------------------------------------------------------

    def validate_parent_assignment(
        self,
        *,
        parent_id: Optional[UUID],
        element=None,
        element_id: Optional[UUID] = None,
        workspace_id: UUID | str | None = None,
    ) -> None:
        """Run I3 → I1 → I2 for a (proposed) parent assignment.

        Order matters: I3 resolves the parent, I1 guards against cycles
        before I2 triggers the recursive get_level() traversal.

        Args:
            parent_id: The proposed parent (None = root, always valid).
            element: The element being re-parented (None on creation).
            element_id: Explicit element id (used when *element* is None).
            workspace_id: Workspace for the cross-workspace check (I3).
        """
        if parent_id is None:
            return
        parent = self.check_i3(parent_id, workspace_id=workspace_id)
        effective_id = element_id if element_id is not None else getattr(
            element, "id", None
        )
        self.check_i1(element_id=effective_id, parent_id=parent_id)
        self.check_i2(element, parent)

    def validate_allocation(self, *, source_element, target_element) -> None:
        """Run I4 for an allocated-to TraceLink between two elements."""
        self.check_i4(source_element, target_element)

    # ------------------------------------------------------------------
    # Serializer convenience (REST layer, REQ-L1-044)
    # ------------------------------------------------------------------

    @classmethod
    def validate_hierarchy_change(
        cls,
        *,
        parent_id: Optional[UUID],
        element_id: Optional[UUID] = None,
        workspace_id: UUID | str | None = None,
    ) -> None:
        """One-shot validation used by DRF serializers.

        Resolves the element (update path) to derive the workspace when it
        is not part of the request payload, then delegates to
        :meth:`validate_parent_assignment` with the workspace's rigor tier.
        A missing element is *not* an error here — the service layer raises
        NotFoundError on its own authority.
        """
        if parent_id is None:
            return
        element = None
        if element_id is not None:
            element = cls._get_element(element_id)
            if element is not None and workspace_id is None:
                workspace_id = getattr(element.artifact, "workspace_id", None)
        validator = cls.for_workspace(workspace_id)
        validator.validate_parent_assignment(
            parent_id=parent_id,
            element=element,
            element_id=element_id,
            workspace_id=workspace_id,
        )


__all__ = [
    "ArchitectureElementInvariantValidator",
    "RIGOR_INVARIANT_PRESETS",
    "ALL_INVARIANTS",
    "INVARIANT_I1",
    "INVARIANT_I2",
    "INVARIANT_I3",
    "INVARIANT_I4",
]
