"""
SysEng 2.0 SE-Auditor — Remediation analysis for audit findings (Phase 3).

UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3 ("Auditor UI", Adopt/Modify-Workflow).

This module is the read-only *analysis* half of the Adopt/Modify mechanism.
It mirrors the rule-registry pattern in ``registry.py``: one small
:class:`Remediation` subclass per rule id, self-registered via
``@register_remediation``. Given a :class:`~traceability.audit.types.Finding`
each remediation decides whether the "missing correction" the finding describes
can be derived *unambiguously* from the current graph and, if so, produces a
concrete, JSON-serialisable :class:`RemediationProposal` (the exact
service-call parameters). It never mutates anything.

Execution is deliberately NOT here. A remediation only *proposes*; the
application-layer ``AuditService`` (Layer 2, ADR-01 single entry point) is the
sole component that applies a proposal — by calling the existing validated
domain services (e.g. ``TraceLinkService.create_trace_link``). This keeps the
layering clean:

    Finding  --(Remediation.propose, read-only, Layer 1)-->  RemediationProposal
    RemediationProposal  --(AuditService, Layer 2)-->  TraceLinkService (mutation)

Why not one generic "Adopt" for everything
-------------------------------------------
The ten active rules have ten different "what is missing" semantics (a missing
``derives-from`` link, a missing ``allocated-to`` allocation, a dangling
architecture parent, a missing verifying TestCase, ...). Some are *deterministic*
(the finding already names both endpoints, e.g. TRACE-P5), some are
*candidate-based* (auto-fixable only if exactly one plausible target exists,
e.g. TRACE-P1/TRACE-P2), and some have no unambiguous auto-fix at all (e.g.
TRACE-P4's dangling parent, VERIF-P8's missing TestCase — a TestCase cannot be
invented). This module therefore models three outcomes explicitly:

    (a) automatic + deterministic — endpoints come straight from the finding.
    (b) automatic + unique candidate — exactly one plausible target in scope.
    (c) not automatic — zero or many candidates, or no meaningful auto-fix;
        the UI must fall back to a manual "Modify" action.

Rules without a registered remediation resolve to outcome (c) by default (see
:func:`get_remediation` returning ``None`` and ``AuditService`` building a
not-automatic proposal), so every rule — including the deferred CONS-P9/CONS-P10
— yields a correct, crash-free answer.

Adding a remediation for a new rule
-----------------------------------
1. Subclass :class:`Remediation`, set ``rule_id`` (a constant from
   ``registry.py``) and implement ``propose(finding, *, tenant_id, workspace_id)``.
2. Decorate with ``@register_remediation``.
3. Import the module in ``rules/__init__.py`` (or wherever the remediations are
   wired) so the decorator runs. If a new *action kind* is required (beyond
   ``create_trace_link``), add it to :class:`RemediationActionKind` and teach
   ``AuditService._execute_action`` how to run it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional

from traceability.audit.registry import TRACE_P1, TRACE_P2, TRACE_P5
from traceability.audit.types import Finding
from traceability.types import LinkType


class RemediationActionKind(str, Enum):
    """The concrete mutation an automatic proposal maps to.

    Kept as a small closed enum so the executor in ``AuditService`` can
    dispatch exhaustively. Extend this (and the executor) when a rule needs a
    different kind of fix — e.g. a future ``UPDATE_FIELD`` for field-level
    corrections.
    """

    CREATE_TRACE_LINK = "create_trace_link"


@dataclass(frozen=True)
class RemediationProposal:
    """The outcome of analysing one finding for automatic remediation.

    Attributes:
        rule_id: The rule the underlying finding belongs to.
        automatic: ``True`` if the fix can be applied without user input.
        reason: Human-readable explanation — *what* will be done (automatic) or
            *why* it cannot be done automatically (manual).
        finding_artifact_ids: The finding's artifact ids, echoed back so the
            caller can correlate the proposal with the finding it came from.
        action_kind: The :class:`RemediationActionKind` value when
            ``automatic`` is ``True``; ``None`` otherwise.
        params: Parameters for the action (e.g. ``source_id``/``target_id``/
            ``link_type`` for ``create_trace_link``). Empty when not automatic.
    """

    rule_id: str
    automatic: bool
    reason: str
    finding_artifact_ids: tuple[str, ...] = ()
    action_kind: Optional[str] = None
    params: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "rule_id": self.rule_id,
            "automatic": self.automatic,
            "reason": self.reason,
            "finding_artifact_ids": list(self.finding_artifact_ids),
            "action_kind": self.action_kind,
            "params": dict(self.params),
        }

    @classmethod
    def manual(
        cls,
        rule_id: str,
        reason: str,
        finding_artifact_ids: tuple[str, ...] = (),
    ) -> "RemediationProposal":
        """Build a not-automatic proposal (outcome (c))."""
        return cls(
            rule_id=rule_id,
            automatic=False,
            reason=reason,
            finding_artifact_ids=finding_artifact_ids,
        )

    @classmethod
    def create_trace_link(
        cls,
        rule_id: str,
        *,
        source_id: str,
        target_id: str,
        link_type: str,
        reason: str,
        finding_artifact_ids: tuple[str, ...] = (),
    ) -> "RemediationProposal":
        """Build an automatic ``create_trace_link`` proposal (outcome (a)/(b))."""
        return cls(
            rule_id=rule_id,
            automatic=True,
            reason=reason,
            finding_artifact_ids=finding_artifact_ids,
            action_kind=RemediationActionKind.CREATE_TRACE_LINK.value,
            params={
                "source_id": source_id,
                "target_id": target_id,
                "link_type": link_type,
            },
        )


# ---------------------------------------------------------------------------
# Remediation interface + registry (mirrors registry.py's rule registry)
# ---------------------------------------------------------------------------


class Remediation(ABC):
    """Analyses a finding of one rule and proposes a correction.

    Stateless; instantiated once at registration. Implementations MUST be
    read-only — no mutation, no service calls. They may query the persistence
    layer to search for candidates (mirroring the audit rules' own read-only
    ``unscoped.filter(tenant_id=..., artifact__workspace_id=...)`` access).
    """

    rule_id: str = ""

    @abstractmethod
    def propose(
        self, finding: Finding, *, tenant_id: str, workspace_id: str
    ) -> RemediationProposal:
        """Return a proposal for *finding* (automatic or manual)."""
        raise NotImplementedError


_REMEDIATION_REGISTRY: Dict[str, Remediation] = {}


def register_remediation(cls: type[Remediation]) -> type[Remediation]:
    """Class decorator: instantiate *cls* and register it under its ``rule_id``.

    Rejects a missing ``rule_id`` and duplicate registrations (mirrors
    ``registry.register_rule``).
    """
    instance = cls()
    rule_id = instance.rule_id
    if not rule_id:
        raise ValueError(f"{cls.__name__} must define a non-empty rule_id")
    if rule_id in _REMEDIATION_REGISTRY:
        raise ValueError(f"Remediation for {rule_id!r} is already registered")
    _REMEDIATION_REGISTRY[rule_id] = instance
    return cls


def get_remediation(rule_id: str) -> Optional[Remediation]:
    """Return the registered remediation for *rule_id*, or ``None``."""
    return _REMEDIATION_REGISTRY.get(rule_id)


def get_registered_remediations() -> Dict[str, Remediation]:
    """Return a copy of the ``rule_id -> Remediation`` registry."""
    return dict(_REMEDIATION_REGISTRY)


def clear_remediation_registry() -> None:  # pragma: no cover — test/tooling helper
    """Empty the remediation registry."""
    _REMEDIATION_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Read-only candidate-search helpers (mirror the audit rules' data access:
# tenant + workspace supplied explicitly, ``unscoped`` manager, exclude
# soft-deleted rows). Return Artifact ids, because every TraceLink endpoint is
# an Artifact id.
# ---------------------------------------------------------------------------


def _stakeholder_need_artifact_ids(tenant_id: str, workspace_id: str) -> FrozenSet[str]:
    """Return artifact ids of active StakeholderNeeds in the workspace."""
    from persistence.models import LifecycleStatus, StakeholderNeed

    qs = StakeholderNeed.unscoped.filter(
        tenant_id=tenant_id, artifact__workspace_id=workspace_id
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
    return frozenset(str(v) for v in qs.values_list("artifact_id", flat=True))


def _architecture_artifact_ids(tenant_id: str, workspace_id: str) -> FrozenSet[str]:
    """Return artifact ids of active ArchitectureElements in the workspace.

    ArchitectureElement has no status mirror — ``outdate()`` writes only
    ``WorkflowItemState`` (the dead ``lifecycle_status`` column is never
    touched), so "active" is computed against
    ``workflow.services.outdated_item_ids`` instead.
    """
    from persistence.models import ArchitectureElement
    from workflow.services import outdated_item_ids

    qs = ArchitectureElement.unscoped.filter(
        tenant_id=tenant_id, artifact__workspace_id=workspace_id
    ).exclude(id__in=outdated_item_ids("ArchitectureElement", tenant_id=tenant_id))
    return frozenset(str(v) for v in qs.values_list("artifact_id", flat=True))


# ---------------------------------------------------------------------------
# TRACE-P5 — deterministic (outcome (a)). The finding already names both
# endpoints: (child_req_id, parent_req_id). The fix is the missing
# ``derives-from`` link child -> parent, no candidate search required.
# ---------------------------------------------------------------------------


@register_remediation
class RequirementDecompositionDerivationRemediation(Remediation):
    """TRACE-P5: create the missing ``derives-from`` link child -> parent."""

    rule_id = TRACE_P5

    def propose(
        self, finding: Finding, *, tenant_id: str, workspace_id: str
    ) -> RemediationProposal:
        # TRACE-P5 finding.artifact_ids == (child_id, parent_id) — see
        # rules/decomposition_consistency.py RequirementDecompositionDerivationRule.
        if len(finding.artifact_ids) < 2:
            return RemediationProposal.manual(
                self.rule_id,
                "Finding is missing the child/parent endpoints required to "
                "derive the correction.",
                finding.artifact_ids,
            )
        child_id, parent_id = finding.artifact_ids[0], finding.artifact_ids[1]
        return RemediationProposal.create_trace_link(
            self.rule_id,
            source_id=child_id,
            target_id=parent_id,
            link_type=LinkType.DERIVES_FROM.value,
            reason=(
                f"Create the missing 'derives-from' link from Requirement "
                f"{child_id} to its decomposition parent {parent_id}."
            ),
            finding_artifact_ids=finding.artifact_ids,
        )


# ---------------------------------------------------------------------------
# TRACE-P1 — candidate-based (outcome (b)/(c)). Root Requirement has no
# ``derives-from`` to any StakeholderNeed. Auto-fixable iff exactly one
# StakeholderNeed exists in the workspace; otherwise the target is ambiguous
# and the user must pick one (Modify).
# ---------------------------------------------------------------------------


@register_remediation
class SystemRequirementDerivesFromNeedRemediation(Remediation):
    """TRACE-P1: link the root Requirement to the unique StakeholderNeed."""

    rule_id = TRACE_P1

    def propose(
        self, finding: Finding, *, tenant_id: str, workspace_id: str
    ) -> RemediationProposal:
        if not finding.artifact_ids:
            return RemediationProposal.manual(
                self.rule_id,
                "Finding is missing the Requirement id.",
                finding.artifact_ids,
            )
        req_id = finding.artifact_ids[0]
        need_ids = _stakeholder_need_artifact_ids(tenant_id, workspace_id)
        if len(need_ids) == 1:
            (need_id,) = tuple(need_ids)
            return RemediationProposal.create_trace_link(
                self.rule_id,
                source_id=req_id,
                target_id=need_id,
                link_type=LinkType.DERIVES_FROM.value,
                reason=(
                    f"Create a 'derives-from' link from root Requirement "
                    f"{req_id} to the workspace's only StakeholderNeed "
                    f"{need_id}."
                ),
                finding_artifact_ids=finding.artifact_ids,
            )
        if not need_ids:
            return RemediationProposal.manual(
                self.rule_id,
                "No StakeholderNeed exists in this workspace — create one and "
                "link it manually (Modify).",
                finding.artifact_ids,
            )
        return RemediationProposal.manual(
            self.rule_id,
            f"{len(need_ids)} StakeholderNeeds exist — the correct derivation "
            "target is ambiguous; choose one manually (Modify).",
            finding.artifact_ids,
        )


# ---------------------------------------------------------------------------
# TRACE-P2 — candidate-based (outcome (b)/(c)). Requirement is not allocated to
# any ArchitectureElement. Auto-fixable iff exactly one ArchitectureElement
# exists; otherwise the allocation target is ambiguous (Modify).
# ---------------------------------------------------------------------------


@register_remediation
class RequirementAllocatedToArchitectureRemediation(Remediation):
    """TRACE-P2: allocate the Requirement to the unique ArchitectureElement."""

    rule_id = TRACE_P2

    def propose(
        self, finding: Finding, *, tenant_id: str, workspace_id: str
    ) -> RemediationProposal:
        if not finding.artifact_ids:
            return RemediationProposal.manual(
                self.rule_id,
                "Finding is missing the Requirement id.",
                finding.artifact_ids,
            )
        req_id = finding.artifact_ids[0]
        arch_ids = _architecture_artifact_ids(tenant_id, workspace_id)
        if len(arch_ids) == 1:
            (arch_id,) = tuple(arch_ids)
            return RemediationProposal.create_trace_link(
                self.rule_id,
                source_id=req_id,
                target_id=arch_id,
                link_type=LinkType.ALLOCATED_TO.value,
                reason=(
                    f"Allocate Requirement {req_id} to the workspace's only "
                    f"ArchitectureElement {arch_id} ('allocated-to' link)."
                ),
                finding_artifact_ids=finding.artifact_ids,
            )
        if not arch_ids:
            return RemediationProposal.manual(
                self.rule_id,
                "No ArchitectureElement exists in this workspace — create one "
                "and allocate manually (Modify).",
                finding.artifact_ids,
            )
        return RemediationProposal.manual(
            self.rule_id,
            f"{len(arch_ids)} ArchitectureElements exist — the allocation "
            "target is ambiguous; choose one manually (Modify).",
            finding.artifact_ids,
        )


__all__ = [
    "RemediationActionKind",
    "RemediationProposal",
    "Remediation",
    "register_remediation",
    "get_remediation",
    "get_registered_remediations",
    "clear_remediation_registry",
    "RequirementDecompositionDerivationRemediation",
    "SystemRequirementDerivesFromNeedRemediation",
    "RequirementAllocatedToArchitectureRemediation",
]
