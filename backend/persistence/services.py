"""
ARCH-L1-010 PersistenceLayer — public foundation surface.

This module re-exports the stable foundation API that other apps consume, so a
downstream app can do a single import:

    from persistence.services import (
        TenantScopedModel, TenantContext, atomic_transaction,
    )

The canonical locations remain:
- Base models / entities → persistence.models (COMP-PL-001, COMP-PL-005)
- Tenant isolation        → persistence.tenancy (COMP-PL-002)
- Transactions            → persistence.transactions (COMP-PL-003)

Reference: docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/
           L2_PersistenceLayerSystem_Architecture.md
"""
from __future__ import annotations

from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditableModel,
    AuditLogEntry,
    Baseline,
    Requirement,
    Role,
    Tenant,
    TenantScopedModel,
    TestCase,
    TraceLink,
    User,
    Workspace,
    WorkflowDefinition,
    WorkflowState,
)
from persistence.tenancy import (
    TenantContext,
    TenantContextNotSetError,
    TenantManager,
    TenantQuerySet,
    UnscopedManager,
)
from persistence.transactions import (
    TransactionContextManager,
    TransactionTimeoutError,
    atomic_transaction,
)

__all__ = [
    # base classes (foundation)
    "AuditableModel",
    "TenantScopedModel",
    # entities
    "Tenant",
    "User",
    "Role",
    "Workspace",
    "Artifact",
    "Requirement",
    "ArchitectureElement",
    "TraceLink",
    "TestCase",
    "Baseline",
    "WorkflowDefinition",
    "WorkflowState",
    "AuditLogEntry",
    # tenancy
    "TenantContext",
    "TenantContextNotSetError",
    "TenantManager",
    "TenantQuerySet",
    "UnscopedManager",
    # transactions
    "atomic_transaction",
    "TransactionContextManager",
    "TransactionTimeoutError",
]
