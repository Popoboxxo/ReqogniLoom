"""
ARCH-L1-010 PersistenceLayer — Entity models.

TODO(COMP-PL-001): Implement TenantAwareManager — Custom Django Manager that
  injects tenant_id filter on every queryset (ADR-03, REQ-L1-015).
  No Query may bypass this filter. Example:
    class TenantAwareManager(models.Manager):
        def get_queryset(self):
            from threading import local
            _state = local()
            tenant_id = getattr(_state, 'tenant_id', None)
            qs = super().get_queryset()
            if tenant_id is not None:
                qs = qs.filter(tenant_id=tenant_id)
            return qs

TODO(COMP-PL-002): Implement Tenant, Workspace models.
TODO(COMP-PL-003): Implement Artifact base model (generic, polymorphic artefact, ADR-05).
TODO(COMP-PL-004): Implement Requirement, ArchitectureElement, TestCase models
  derived from Artifact (REQ-L1-001, REQ-L1-002, REQ-L1-004, REQ-L1-012).
TODO(COMP-PL-005): Implement TraceLink model with link-type enum (6 types + documents/realizes,
  ADR-05, REQ-L1-003). Add GIST/GIN indexes for graph queries.
TODO(COMP-PL-006): Implement Baseline, BaselineItem models (ADR-07, REQ-L1-008).
TODO(COMP-PL-007): Implement WorkflowDefinition, WorkflowState models (ADR-06, REQ-L1-009).
TODO(COMP-PL-008): Implement AuditLogEntry model — append-only (REQ-L1-011, ADR-10).
TODO(COMP-PL-009): Implement User, Role models with RBAC (REQ-L1-010).
  Add PostgreSQL tsvector field and index for Full-Text Search (ADR-09, REQ-L1-020).

Reference: docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/L2_PersistenceLayerSystem_Architecture.md
"""
from django.db import models  # noqa: F401 — imported for future model definitions
