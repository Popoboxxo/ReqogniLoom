"""
ApplicationService Step 3 — Re-export surface for COMP-AS-013..015.

leaf_id : COMP-AS-013, COMP-AS-014, COMP-AS-015
req_id  : REQ-L1-029

This module bundles the Step-3 services and registers them in the
application-service registry (application.services._registry).

Downstream consumers import from here OR from application.services
(after the one-line re-export added to that file).

Import paths::

    from application.services_step3 import (
        AdrService,
        AdrDTO,
        RiskService,
        RiskDTO,
        RISK_LINK_TYPES,
        IssueService,
        IssueDTO,
        ISSUE_LINK_TYPES,
    )

SeMetrics contract (stable, do not change signature without escalation)::

    from application.services_step3 import RiskService
    svc = RiskService()
    risks = svc.query_risks_by_severity(workspace_id, severity, ctx)
    # severity: "low" | "medium" | "high"
    # returns: List[application.models.Risk]

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md  (Extension pattern)
"""
from __future__ import annotations

# COMP-AS-013
from application.adr_service import AdrDTO, AdrService  # noqa: F401

# COMP-AS-014
from application.risk_service import RISK_LINK_TYPES, RiskDTO, RiskService  # noqa: F401

# COMP-AS-015
from application.issue_service import ISSUE_LINK_TYPES, IssueDTO, IssueService  # noqa: F401

# ---------- Registry hook (services.py extension pattern) ----------
from application.services import _registry  # noqa: E402

_registry["AdrService"] = AdrService
_registry["RiskService"] = RiskService
_registry["IssueService"] = IssueService

# ---------- Public surface ----------

__all__ = [
    # COMP-AS-013
    "AdrService",
    "AdrDTO",
    # COMP-AS-014
    "RiskService",
    "RiskDTO",
    "RISK_LINK_TYPES",
    # COMP-AS-015
    "IssueService",
    "IssueDTO",
    "ISSUE_LINK_TYPES",
]
