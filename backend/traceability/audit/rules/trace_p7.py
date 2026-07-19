"""
TRACE-P7 — Baseline-scope consistency (SysEng 2.0 SE-Auditor).

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2. Rigor: Extended only, scope-aware.

Operational definition (see the DECISION note in the delivery report):
When a baseline is snapshotted at a given scope, it captures exactly the
artifacts in that scope's membership set (resolved via
``baseline.services.resolve_scope_item_ids``). A trace link that has *exactly
one* endpoint inside the scope leaks out of it — the snapshot would contain a
link whose other endpoint it does not contain, i.e. a dangling reference. Such
a link is reported as a finding.

Why "exactly one endpoint" (XOR):
- both endpoints inside  → the link is fully captured → conformant.
- both endpoints outside → the link is not part of this scope at all → ignored.
- one in, one out        → scope leak → finding.

This naturally honours the "same-or-superordinate scope is allowed" wording of
§2.2: a superordinate scope's membership set is a superset, so a link that
stays within a wider scope is fully contained (both endpoints inside) when that
wider scope is audited, and produces no finding there. The rule therefore flags
"audit this at a wider scope if you want the link to be legal".

This rule intentionally does NOT check endpoint-type legality — that is
``SE_LINK_SEMANTICS`` territory (enforced at link creation, §2.1). It only
checks scope membership.
"""
from __future__ import annotations

from typing import List

from traceability.audit.registry import TRACE_P7, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity


@register_rule
class BaselineScopeConsistencyRule(Rule):
    """TRACE-P7: no trace link may leak out of the audited baseline scope."""

    rule_id = TRACE_P7
    is_scope_aware = True

    def check(self, context: AuditContext) -> List[Finding]:
        """Return one finding per trace link that straddles the scope boundary.

        A scope-agnostic context (``scope is None``) yields no findings — the
        rule is only meaningful relative to a concrete baseline scope.
        """
        if context.scope is None:
            return []

        scope_ids = context.scope_item_ids
        if not scope_ids:
            # Empty scope (e.g. unknown/empty document): nothing is captured,
            # so nothing can leak. A link with both endpoints outside is not
            # part of this scope.
            return []

        findings: List[Finding] = []
        for link in context.iter_trace_links():
            source_in = link["source_id"] in scope_ids
            target_in = link["target_id"] in scope_ids
            if source_in == target_in:
                # both inside (conformant) or both outside (not in scope)
                continue

            outside_id = link["target_id"] if source_in else link["source_id"]
            inside_id = link["source_id"] if source_in else link["target_id"]
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P7] Trace link {link['id']} "
                        f"({link['link_type']}) leaks out of the "
                        f"'{context.scope}' baseline scope: artifact "
                        f"{inside_id} is inside the scope but the linked "
                        f"artifact {outside_id} is not. Baseline the wider "
                        f"(superordinate) scope, or remove the cross-scope link."
                    ),
                    artifact_ids=(inside_id, outside_id),
                    scope=context.scope,
                    scope_artifact_id=context.scope_artifact_id,
                )
            )
        return findings


__all__ = ["BaselineScopeConsistencyRule"]
