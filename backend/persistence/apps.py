"""App configuration for ARCH-L1-010 PersistenceLayer."""
from django.apps import AppConfig


class PersistenceConfig(AppConfig):
    """ARCH-L1-010 PersistenceLayer — PostgreSQL via Django ORM.

    Responsibilities:
    - Holds all entity models: Tenant, Workspace, Artifact, Requirement,
      ArchitectureElement, TraceLink, TestCase, Baseline, WorkflowDefinition,
      WorkflowState, AuditLogEntry, User, Role.
    - Custom Django Manager enforces Row-Level Tenant-Isolation on every query (ADR-03).
    - PostgreSQL indexes for hierarchical queries (Recursive CTE), TraceLink
      graph queries (GIST/GIN), and Full-Text Search (tsvector, ADR-09).

    See: docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/L2_PersistenceLayerSystem_Architecture.md
    REQ-L1: REQ-L1-015 (Multi-Tenancy prep), REQ-L1-025 (ACID), REQ-L1-026 (Performance)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "persistence"
    verbose_name = "ARCH-L1-010 PersistenceLayer"
