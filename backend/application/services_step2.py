"""
ApplicationService Step 2 — Re-export surface for COMP-AS-006..011.

leaf_id : COMP-AS-006, COMP-AS-007, COMP-AS-008, COMP-AS-009,
          COMP-AS-010, COMP-AS-011
req_id  : REQ-L1-018, REQ-L1-019, REQ-L1-020, REQ-L1-021,
          REQ-L1-023, REQ-L1-024

This module bundles the Step-2 services and registers them in the
application-service registry (application.services._registry).

Downstream consumers import from here OR from application.services
(after the one-line re-export added to that file).

Import paths::

    from application.services_step2 import (
        BaselineFacade,
        WorkflowFacade,
        ExportService,
        ExportResult,
        ImportService,
        ImportResult,
        ImportRowError,
        SearchService,
        SearchResult,
        SearchHit,
        QueryParser,
        WebhookDispatcher,
        SUBSCRIBED_EVENT_TYPES,
        get_webhook_dispatcher,
    )

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md  (Extension pattern)
"""
from __future__ import annotations

# COMP-AS-006
from application.baseline_facade import BaselineFacade  # noqa: F401

# COMP-AS-007
from application.workflow_facade import WorkflowFacade  # noqa: F401

# COMP-AS-008
from application.export_service import ExportResult, ExportService  # noqa: F401

# COMP-AS-009
from application.import_service import (  # noqa: F401
    ImportResult,
    ImportRowError,
    ImportService,
)

# COMP-AS-010
from application.search_service import (  # noqa: F401
    QueryParser,
    SearchHit,
    SearchResult,
    SearchService,
)

# COMP-AS-011
from application.webhook_dispatcher import (  # noqa: F401
    SUBSCRIBED_EVENT_TYPES,
    WebhookDispatcher,
    get_webhook_dispatcher,
)

# COMP-AS-WS (read-only Workspace surface, REQ-L1-017)
from application.workspace_service import WorkspaceService  # noqa: F401

# ---------- Registry hook (services.py extension pattern) ----------
from application.services import _registry  # noqa: E402

_registry["BaselineFacade"] = BaselineFacade
_registry["WorkflowFacade"] = WorkflowFacade
_registry["ExportService"] = ExportService
_registry["ImportService"] = ImportService
_registry["SearchService"] = SearchService
_registry["WebhookDispatcher"] = WebhookDispatcher
_registry["WorkspaceService"] = WorkspaceService

# ---------- Public surface ----------

__all__ = [
    # COMP-AS-006
    "BaselineFacade",
    # COMP-AS-007
    "WorkflowFacade",
    # COMP-AS-008
    "ExportService",
    "ExportResult",
    # COMP-AS-009
    "ImportService",
    "ImportResult",
    "ImportRowError",
    # COMP-AS-010
    "SearchService",
    "SearchResult",
    "SearchHit",
    "QueryParser",
    # COMP-AS-011
    "WebhookDispatcher",
    "SUBSCRIBED_EVENT_TYPES",
    "get_webhook_dispatcher",
    # COMP-AS-WS
    "WorkspaceService",
]
