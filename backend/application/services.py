"""
ARCH-L1-004 ApplicationService — Public service facade.

leaf_id : ApplicationService Foundation (Step 1 of 3)
req_id  : REQ-L2-AS-001 through REQ-L2-AS-025, REQ-L2-AS-029

This module is the ONLY public import surface for downstream systems
(rest_api, mcp_server).  ADR-01: Single Entry Point.

Step-1 components (this file):
  COMP-AS-001  ArtifactService
  COMP-AS-002  RequirementService
  COMP-AS-003  ArchitectureService
  COMP-AS-004  TestService
  COMP-AS-005  TraceLinkService
  COMP-AS-012  PresetPolicyService
  COMP-AS-016  DomainEventBus

Extension pattern for Steps 2+3 (DO NOT modify this file):
  1. Create application/services_step2.py (or services_step3.py).
  2. Define your service class (subclass ServiceBase if writing).
  3. At the bottom of that file add:

       from application.services import _registry
       _registry["MyNewService"] = MyNewService

     OR simply import and re-export in a thin wrapper:

       # services_step2.py
       from application.baseline_facade import BaselineFacade      # noqa: F401
       from application.workflow_facade import WorkflowFacade       # noqa: F401
       __all__ = ["BaselineFacade", "WorkflowFacade"]

  4. Downstream consumers then import from application.services_step2
     OR from application.services after adding a re-export line (see below).

Files NOT to modify when adding new services:
  - application/base.py          (ServiceBase contract)
  - application/event_bus.py     (DomainEventBus)
  - application/models.py        (Outbox/DLQ models)
  - application/services.py      (this file — except the __all__ extension)

Import paths for downstream consumers:

    from application.services import (
        ArtifactService,
        RequirementService,
        ArchitectureService,
        TestService,
        TraceLinkService,
        PresetPolicyService,
        DomainEventBus,
        get_event_bus,
        poll_and_dispatch,
        # Exceptions
        PermissionDeniedError,
        NotFoundError,
        ValidationError,
        OptimisticLockError,
        LlmNotConfiguredError,
        # Event type
        DomainEvent,
    )

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Step-1 components — re-exported as the public facade
# ---------------------------------------------------------------------------

# COMP-AS-001
from application.artifact_service import ArtifactService, TreeNodeDTO  # noqa: F401

# COMP-AS-002
from application.requirement_service import (  # noqa: F401
    DecompositionResultDTO,
    RequirementDTO,
    RequirementService,
)

# COMP-AS-003
from application.architecture_service import ArchitectureService  # noqa: F401

# COMP-AS-004
from application.test_service import TestService  # noqa: F401

# COMP-AS-005
from application.trace_link_service import TraceLinkService, VALID_LINK_TYPES  # noqa: F401

# COMP-AS-012
from application.preset_policy_service import (  # noqa: F401
    PresetPolicyService,
    get_preset_policy_service,
)

# COMP-AS-016
from application.event_bus import (  # noqa: F401
    DomainEvent,
    DomainEventBus,
    get_event_bus,
    poll_and_dispatch,
)

# Shared exceptions
from application.base import (  # noqa: F401
    LlmNotConfiguredError,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Service registry (for Steps 2+3 to hook into without modifying this file)
# ---------------------------------------------------------------------------
# Steps 2+3 may call:
#   from application.services import _registry
#   _registry["MyNewService"] = MyNewService
# This allows discovery without changing any existing import path.

_registry: dict = {
    "ArtifactService": ArtifactService,
    "RequirementService": RequirementService,
    "ArchitectureService": ArchitectureService,
    "TestService": TestService,
    "TraceLinkService": TraceLinkService,
    "PresetPolicyService": PresetPolicyService,
}

# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step-2 re-export (COMP-AS-006..011) — DO NOT modify above this line
# ---------------------------------------------------------------------------
from application.services_step2 import *  # noqa: F401,F403,E402

__all__ = [
    # Step-1 services
    "ArtifactService",
    "RequirementService",
    "ArchitectureService",
    "TestService",
    "TraceLinkService",
    "PresetPolicyService",
    # COMP-AS-016
    "DomainEventBus",
    "DomainEvent",
    "get_event_bus",
    "poll_and_dispatch",
    # DTOs
    "TreeNodeDTO",
    "RequirementDTO",
    "DecompositionResultDTO",
    # Exceptions
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "OptimisticLockError",
    "LlmNotConfiguredError",
    # Base (for Steps 2+3 inheritance)
    "ServiceBase",
    # Registry (for extension)
    "_registry",
    # Constants
    "VALID_LINK_TYPES",
    # Helpers
    "get_preset_policy_service",
    # Step-2 services (COMP-AS-006..011)
    "BaselineFacade",
    "WorkflowFacade",
    "ExportService",
    "ExportResult",
    "ImportService",
    "ImportResult",
    "ImportRowError",
    "SearchService",
    "SearchResult",
    "SearchHit",
    "QueryParser",
    "WebhookDispatcher",
    "SUBSCRIBED_EVENT_TYPES",
    "get_webhook_dispatcher",
]
