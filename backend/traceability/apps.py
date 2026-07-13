"""App configuration for ARCH-L1-007 TraceabilityEngine."""
from django.apps import AppConfig


class TraceabilityConfig(AppConfig):
    """ARCH-L1-007 TraceabilityEngine — TraceLink Graph Management.

    Responsibilities:
    - Manages TraceLinks between Requirements, ArchitectureElements, TestCases
      with link types: parent-child, derives-from, satisfies, verifies,
      implements, refines, documents (new), realizes (new).
    - Upstream/downstream queries and coverage reports.
    - Performance target: < 200 ms for 10,000 items.
    - Cross-project graph traversal with cross-project annotation (REQ-L1-030).
    - Cross-tenant links are rejected (validation via AuthAndTenancy, IF-L1-056).

    See: docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/L2_TraceabilityEngineSystem_Architecture.md
    REQ-L1: REQ-L1-003 (Traceability engine)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "traceability"
    verbose_name = "ARCH-L1-007 TraceabilityEngine"
