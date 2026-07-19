"""
SysEng 2.0 SE-Auditor — RuleEngine (Phase 2 core).

UMSETZUNGSPLAN_SYSENG_2.0.md §2, Phase 2. Orchestrates the registered audit
rules for a workspace: it resolves the active rule set for the workspace's
rigor tier, runs scope-agnostic rules once and scope-aware rules once per
requested baseline scope, and aggregates the findings.

The engine holds no rule logic of its own — rules self-register in
``traceability.audit.registry`` and are discovered by importing the
``traceability.audit.rules`` package (done here at construction time). Preset
inheritance is entirely data-driven through ``RULE_PRESET_MAP``; the Minimal
tier resolves to an empty rule set, so ``run(tier="minimal", ...)`` yields zero
findings by construction, never by chance.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from traceability.audit.registry import (
    active_rule_ids_for_tier,
    get_registered_rules,
)
from traceability.audit.types import (
    AuditContext,
    AuditResult,
    AuditScope,
    Finding,
)


class RuleEngine:
    """Runs the registered SE-Auditor rules for a workspace and rigor tier."""

    def __init__(self) -> None:
        # Importing the rules package triggers @register_rule for every rule.
        # Deferred to construction (not module import) to keep import order
        # robust and to avoid a hard import cycle at package load time.
        import traceability.audit.rules  # noqa: F401  (registration side effect)

    def run(
        self,
        *,
        tier: str,
        workspace_id: str,
        tenant_id: str,
        scopes: Optional[Sequence[AuditScope]] = None,
    ) -> AuditResult:
        """Audit *workspace_id* under rigor *tier* and return all findings.

        Scope-agnostic rules run once against a scope-less context.
        Scope-aware rules run once per entry in *scopes*; each gets its own
        context carrying that scope's resolved artifact-id set. When *scopes*
        is ``None`` the engine defaults to the workspace-wide ``project`` scope
        (``document`` scopes are never auto-derived: they need an explicit root
        artifact and callers must pass them deliberately).

        Args:
            tier: Active rigor tier ("minimal" | "standard" | "extended").
            workspace_id: Target workspace UUID (as string).
            tenant_id: Active tenant UUID (as string).
            scopes: Explicit baseline scopes for scope-aware rules. Defaults to
                ``[AuditScope("project")]``.

        Returns:
            :class:`AuditResult` with all findings in rule/scope order.
        """
        active_ids = active_rule_ids_for_tier(tier)
        result = AuditResult(tier=tier, findings=[])

        # Minimal (or any tier with no active rules) short-circuits: no rule is
        # active, so no context is built and no query is issued.
        if not active_ids:
            return result

        active_rules = [
            rule
            for rule in get_registered_rules()
            if rule.rule_id in active_ids
        ]
        if not active_rules:
            return result

        scope_agnostic = [r for r in active_rules if not r.is_scope_aware]
        scope_aware = [r for r in active_rules if r.is_scope_aware]

        # --- scope-agnostic rules: single run, no scope ---
        if scope_agnostic:
            base_ctx = AuditContext(
                tier=tier,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                scope=None,
            )
            for rule in scope_agnostic:
                result.findings.extend(
                    self._run_rule(rule, base_ctx, tier)
                )

        # --- scope-aware rules: one run per requested baseline scope ---
        if scope_aware:
            effective_scopes = (
                list(scopes) if scopes is not None else [AuditScope("project")]
            )
            for audit_scope in effective_scopes:
                scope_ctx = AuditContext(
                    tier=tier,
                    workspace_id=workspace_id,
                    tenant_id=tenant_id,
                    scope=audit_scope.scope,
                    scope_artifact_id=audit_scope.artifact_id,
                )
                for rule in scope_aware:
                    result.findings.extend(
                        self._run_rule(rule, scope_ctx, tier)
                    )

        return result

    @staticmethod
    def _run_rule(rule, context: AuditContext, tier: str) -> List[Finding]:
        """Run one rule, stamping the tier-resolved severity onto findings.

        Rules return findings with their natural severity; the engine is the
        authority on per-tier severity (e.g. TRACE-P2 downgrades to WARNING at
        Standard), so it overrides each finding's severity with
        ``rule.severity_for_tier(tier)`` to keep that policy in one place.
        """
        severity = rule.severity_for_tier(tier)
        raw = rule.check(context)
        stamped: List[Finding] = []
        for finding in raw:
            if finding.severity is severity:
                stamped.append(finding)
            else:
                # Re-stamp with the tier-authoritative severity (frozen dataclass).
                stamped.append(
                    Finding(
                        rule_id=finding.rule_id,
                        severity=severity,
                        message=finding.message,
                        artifact_ids=finding.artifact_ids,
                        scope=finding.scope,
                        scope_artifact_id=finding.scope_artifact_id,
                    )
                )
        return stamped


__all__ = ["RuleEngine"]
