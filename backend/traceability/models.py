"""
ARCH-L1-007 TraceabilityEngine — Models and Query Engines.

**Note:** The TraceLink data model (with link_type enum and tenant isolation) is defined
in `backend/persistence/models.py:1294` as part of the unified artifact persistence layer.

This module houses the **graph traversal and analysis engines**:

- `TraceLinkManager` (trace_link_manager.py) — upstream/downstream query engine with
  Recursive CTEs for hierarchical traversal, cycle detection via SCC (Strongly Connected Components)
- `CoverageCalculator` (coverage_calculator.py) — computes traceability coverage
  per workspace for SeMetrics (REQ-L1-045)
- `QueryEngine` (query_engine.py) — Transitive closure, impact analysis, multi-level navigation
- Cross-tenant boundary validation enforced by `auth_tenancy.permission_cache`

All 15 trace-link types (parent-child, derives-from, satisfies, verifies, implements,
refines, documents, realizes, traces, copy-of, allocated-to, uses-term, decides,
decomposes, diagram-ref) are implemented and RLS-protected.

Reference: docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/L2_TraceabilityEngineSystem_Architecture.md
"""
from django.db import models  # noqa: F401
