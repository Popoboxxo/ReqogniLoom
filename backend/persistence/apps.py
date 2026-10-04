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

    def ready(self) -> None:
        """Register the staged-RLS config-drift system check (issue #1136).

        Registered unconditionally so ``manage.py check`` is exactly where an
        operator learns that a flipped RLS flag is not actually wired into the
        app-role connection OPTIONS (AC-25).
        """
        from django.core.checks import register

        from persistence.checks import check_rls_guc_flags_match_db_options

        register(check_rls_guc_flags_match_db_options)
