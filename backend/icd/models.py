"""
ARCH-L1-014 IcdManagement — Models.

TODO(COMP-ICD-001): Implement Icd model.
  Fields: id, tenant_id, workspace_id, source_element_id, target_element_id,
  direction (enum: unidirectional/bidirectional), interface_type,
  current_version_id (FK), created_at, created_by.
TODO(COMP-ICD-002): Implement IcdVersion model — immutable per change.
  Fields: id, icd_id (FK), version_number, semantic_description,
  preconditions (JSONField), postconditions (JSONField), invariants (JSONField),
  created_at, created_by.
  No update/delete path — append-only.
TODO(COMP-ICD-003): Implement CompatibilityChecker — compares two IcdVersions
  and detects breaking changes in pre/post/invariant fields.
  Reports BreakingChangeWarning with diff details.

Reference: docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/L2_IcdManagementSystem_Architecture.md
"""
from django.db import models  # noqa: F401
