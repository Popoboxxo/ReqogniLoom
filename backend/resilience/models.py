"""
ARCH-L1-016 ResilienceOrchestrator — Models.

TODO(COMP-RO-001): Implement CircuitBreakerState model — tracks open/closed/half-open
  state per target subsystem.
  Fields: id, target_subsystem (enum: llm/webhook/github), state (enum),
  failure_count, last_failure_at, opens_at, tenant_id.
TODO(COMP-RO-002): Implement AsyncTask model if Celery result backend is insufficient
  for task introspection (optional; Celery's built-in result backend may suffice).

Reference: docs/se/L1/Gesamtsystem/L2/ResilienceOrchestratorSystem/L2_ResilienceOrchestratorSystem_Architecture.md
"""
from django.db import models  # noqa: F401
