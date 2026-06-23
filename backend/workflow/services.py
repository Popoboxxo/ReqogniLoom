"""
ARCH-L1-005 WorkflowEngine — Service stubs.

TODO(COMP-WE-001): Implement WorkflowService:
  - transition(item_id, target_state, change_reason, ctx) -> WorkflowState
    Validates role (via auth_tenancy), change_reason obligation (via presets),
    then persists transition to WorkflowState.history.
  - find_incomplete_states(workspace_id) -> list[dict]  (IF-L1-046 for SeMetrics)
  - get_definition(workspace_id, item_type) -> WorkflowDefinition

Reference: docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/L2_WorkflowEngineSystem_Architecture.md
"""
