"""
ARCH-L1-007 TraceabilityEngine — Models.

TODO(COMP-TE-001): Implement TraceLink model with link_type enum:
  parent-child | derives-from | satisfies | verifies | implements | refines
  | documents (REQ-L1-027) | realizes (REQ-L1-028).
  Fields: id, tenant_id, source_artifact_id, source_artifact_type,
  target_artifact_id, target_artifact_type, link_type, project_id (cross-project),
  cross_project (bool, REQ-L1-030), created_at, created_by.
  Add GIST/GIN index for graph traversal performance (< 200ms target, REQ-L1-026).
TODO(COMP-TE-002): Implement TraceLinkManager — upstream/downstream query engine
  with Recursive CTE for hierarchical traversal.
TODO(COMP-TE-003): Implement CoverageCalculator — computes traceability coverage
  per workspace for SeMetrics (IF-L1-045).
TODO(COMP-TE-004): Implement cross-tenant boundary validator (IF-L1-056) —
  calls auth_tenancy to reject cross-tenant links (REQ-L1-030).

Reference: docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/L2_TraceabilityEngineSystem_Architecture.md
"""
from django.db import models  # noqa: F401
