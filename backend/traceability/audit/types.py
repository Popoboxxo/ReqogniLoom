"""
SysEng 2.0 SE-Auditor — shared data types for the RuleEngine.

UMSETZUNGSPLAN_SYSENG_2.0.md §2 (SE-Auditor), Phase 2 (RuleEngine Core).

This module holds the interface contracts exchanged between the RuleEngine,
the individual audit rules and their callers (interface discipline: no circular
imports — rules and the engine both import from here, never the other way).

Scope boundary (see §2.1):
- ``SE_LINK_SEMANTICS`` / ``check_se_link_semantics`` (traceability/types.py)
  answers "may these two artifact *types* be connected by this link type?" and
  is enforced synchronously at link-creation time.
- The RuleEngine answers a different, graph-wide question at *audit* time
  ("is the trace graph complete / self-consistent per baseline scope?"). Rules
  that need endpoint-type legality MUST call ``check_se_link_semantics`` — they
  must never re-implement it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """Severity of an audit finding.

    ``BLOCKER`` findings are meant to block gated transitions (e.g. approval);
    ``WARNING`` findings are advisory. A single rule may map to different
    severities per rigor tier (e.g. TRACE-P2 is a warning at Standard and a
    blocker at Extended) — see :meth:`Rule.severity_for_tier`.
    """

    BLOCKER = "blocker"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """A single audit finding produced by a rule.

    Attributes:
        rule_id: The originating rule id (e.g. ``"TRACE-P7"``).
        severity: BLOCKER or WARNING (already resolved for the active tier).
        message: Human-readable, self-contained explanation of the violation.
        artifact_ids: Ids of the artifacts the finding concerns (may be empty
            for graph-level findings that reference no single artifact).
        scope: The baseline scope this finding was detected in
            (``"document"`` | ``"project"`` | ``"global"``); ``None`` for
            scope-agnostic rules.
        scope_artifact_id: For ``scope == "document"``, the root artifact whose
            subtree was audited (disambiguates findings across documents).
    """

    rule_id: str
    severity: Severity
    message: str
    artifact_ids: tuple[str, ...] = ()
    scope: Optional[str] = None
    scope_artifact_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "artifact_ids": list(self.artifact_ids),
            "scope": self.scope,
            "scope_artifact_id": self.scope_artifact_id,
        }


@dataclass(frozen=True)
class AuditScope:
    """A concrete baseline scope to audit.

    ``artifact_id`` is required for ``scope == "document"`` (the subtree root)
    and ignored otherwise, mirroring
    :func:`baseline.services.resolve_scope_item_ids`.
    """

    scope: str
    artifact_id: Optional[str] = None


@dataclass
class AuditContext:
    """Everything a rule needs to run one check.

    Constructed by the RuleEngine per run (scope-agnostic rules) or per scope
    (scope-aware rules). Data access is lazy: ``scope_item_ids`` and
    ``iter_trace_links`` hit the database only when a rule actually asks for
    them, so scope-agnostic rules never pay for scope resolution.

    Attributes:
        tier: Active rigor tier ("minimal" | "standard" | "extended").
        workspace_id: Target workspace UUID (as string).
        tenant_id: Active tenant UUID (as string) for row-level isolation.
        scope: The baseline scope being audited, or ``None`` for scope-agnostic
            rules.
        scope_artifact_id: Document-scope root artifact id (``None`` otherwise).
    """

    tier: str
    workspace_id: str
    tenant_id: str
    scope: Optional[str] = None
    scope_artifact_id: Optional[str] = None
    _scope_item_ids: Optional[frozenset[str]] = field(
        default=None, repr=False, compare=False
    )

    @property
    def scope_item_ids(self) -> frozenset[str]:
        """Return the full set of artifact ids contained in the current scope.

        Resolved once via :func:`baseline.services.resolve_scope_item_ids`
        (the single source of truth for scope membership) and cached for the
        lifetime of this context. Returns an empty set for scope-agnostic
        contexts (``scope is None``).
        """
        if self._scope_item_ids is not None:
            return self._scope_item_ids
        if self.scope is None:
            self._scope_item_ids = frozenset()
            return self._scope_item_ids

        # Deferred import: baseline is a Layer-1 sibling; importing at module
        # load time would couple the audit package to the baseline app.
        from baseline.services import resolve_scope_item_ids

        ids = resolve_scope_item_ids(
            scope=self.scope,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            artifact_id=self.scope_artifact_id,
        )
        self._scope_item_ids = frozenset(ids)
        return self._scope_item_ids

    def iter_trace_links(self):
        """Yield the tenant's trace links as lightweight dicts.

        Each item has ``id``, ``source_id``, ``target_id`` and ``link_type``
        (ids are strings). Uses the ``unscoped`` manager with an explicit
        ``tenant_id`` filter so resolution is deterministic regardless of the
        thread-local tenant context (the tenant is supplied explicitly to the
        engine — audit infrastructure, read-only, analogous to baseline).
        """
        from persistence.models import TraceLink

        rows = TraceLink.unscoped.filter(tenant_id=self.tenant_id).values(
            "id", "source_id", "target_id", "link_type"
        )
        for row in rows:
            yield {
                "id": str(row["id"]),
                "source_id": str(row["source_id"]),
                "target_id": str(row["target_id"]),
                "link_type": row["link_type"],
            }


@dataclass
class AuditResult:
    """Aggregated result of a full RuleEngine run.

    Attributes:
        tier: The rigor tier the run was executed for.
        findings: All findings from all rules that ran, in rule/scope order.
    """

    tier: str
    findings: list[Finding] = field(default_factory=list)

    def blockers(self) -> list[Finding]:
        """Return only the BLOCKER findings."""
        return [f for f in self.findings if f.severity is Severity.BLOCKER]

    def warnings(self) -> list[Finding]:
        """Return only the WARNING findings."""
        return [f for f in self.findings if f.severity is Severity.WARNING]

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "tier": self.tier,
            "findings": [f.to_dict() for f in self.findings],
        }


__all__ = [
    "Severity",
    "Finding",
    "AuditScope",
    "AuditContext",
    "AuditResult",
]
