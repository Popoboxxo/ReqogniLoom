"""
ARCH-L1-002 RestApiAdapter — Models.

RestApiAdapter is a pure adapter layer (no own models).
All entities are owned by the persistence app (ARCH-L1-010).

TODO(COMP-RA-001): Implement ViewSets for all artifact types:
  RequirementViewSet, ArchitectureElementViewSet, TestCaseViewSet,
  BaselineViewSet, WorkflowViewSet, TraceabilityViewSet.
TODO(COMP-RA-002): Implement serializers for all artifact types.
TODO(COMP-RA-003): Implement i18n error response module (DE/EN).
TODO(COMP-RA-004): Implement preset-aware endpoint filtering — hides endpoints
  based on active workspace preset (via presets app).
TODO(COMP-RA-005): Implement MetricsViewSet proxy — forwards to se_metrics app (IF-L1-042).

Reference: docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/L2_RestApiAdapterSystem_Architecture.md
"""
