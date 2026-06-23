"""
ARCH-L1-006 BaselineService — Service stubs.

TODO(COMP-BS-001): Implement BaselineService:
  - build(scope, workspace_id, ctx) -> Baseline  (IF-L1-004 from ApplicationService)
    Collects trace graph (IF via traceability), ICD versions (IF via icd),
    checks preset for global scope permission, persists atomically.
  - diff(baseline_a_id, baseline_b_id) -> BaselineDiff

Reference: docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md
"""
