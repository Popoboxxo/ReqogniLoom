"""
ARCH-L1-006 BaselineService — Models.

TODO(COMP-BS-001): Implement Baseline model.
  Fields: id, tenant_id, workspace_id, scope (enum: document/project/global),
  document_id (nullable), name, description, created_at, created_by,
  snapshot (JSONField — artifact_ids + versions + ICD versions for scope),
  frozen (bool, True once created — immutable after creation).
  scope=global restricted to Extended preset (ADR-07).
TODO(COMP-BS-002): Implement BaselineDiff utility — compares two Baseline snapshots
  and returns added/removed/changed artifact diffs.
TODO(COMP-BS-003): Implement ICD version collection hook (IF-L1-038):
  calls icd.services.get_icd_versions(workspace_id) when building snapshot.

Reference: docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md
"""
from django.db import models  # noqa: F401
