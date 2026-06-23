"""
ARCH-L1-005 WorkflowEngine — Models.

TODO(COMP-WE-001): Implement WorkflowDefinition model — per item-type and workspace.
  Fields: id, tenant_id, workspace_id, item_type, states (JSONField array),
  transitions (JSONField: {from, to, allowed_roles, require_change_reason}).
  Default definitions auto-created per preset on workspace creation.
TODO(COMP-WE-002): Implement WorkflowState model — tracks current state and
  history per artifact item.
  Fields: id, tenant_id, artifact_id, artifact_type, current_state,
  history (JSONField array: [{state, actor, timestamp, change_reason}]).
TODO(COMP-WE-003): Implement workflow-migration block: reject WorkflowDefinition
  changes if items exist in an orphaned state (OP-03, KONZEPT.md §7a).
  v2: Auto-mapping of orphaned states.

Reference: docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/L2_WorkflowEngineSystem_Architecture.md
"""
from django.db import models  # noqa: F401
