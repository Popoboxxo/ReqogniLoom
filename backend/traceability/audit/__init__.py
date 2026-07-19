"""
SysEng 2.0 SE-Auditor — RuleEngine package (UMSETZUNGSPLAN_SYSENG_2.0.md §2).

Public surface for callers (application-layer audit service, Phase 3 UI):

    from traceability.audit import RuleEngine, AuditScope
    result = RuleEngine().run(
        tier="extended",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
        scopes=[AuditScope("document", artifact_id=str(root.id)),
                AuditScope("project")],
    )
    for finding in result.blockers():
        ...

See ``registry.py`` for the rule interface and the "adding a new rule" guide.
"""
from __future__ import annotations

from traceability.audit.registry import (
    Rule,
    active_rule_ids_for_tier,
    get_registered_rules,
    register_rule,
)
from traceability.audit.rule_engine import RuleEngine
from traceability.audit.types import (
    AuditContext,
    AuditResult,
    AuditScope,
    Finding,
    Severity,
)

__all__ = [
    "RuleEngine",
    "Rule",
    "register_rule",
    "get_registered_rules",
    "active_rule_ids_for_tier",
    "AuditContext",
    "AuditResult",
    "AuditScope",
    "Finding",
    "Severity",
]
