/**
 * ARCH-L1-001 ReactFrontend — shared workflow-transition contract.
 *
 * req_id: REQ-161 (Unified Workflow Status Editor)
 *
 * Every `POST /{resource}/{id}/transitions/` route of the WorkflowEngine
 * answers the same state change (`id`, `previous_state`, `new_state`). The
 * artifact-specific wrappers extend that base with their own extras — the
 * entity revision (`version`) on document/work-item routes and the serialized
 * entity payload. The base therefore lives here, in the type layer, instead of
 * being restated per API module.
 */

/** The state change every workflow transition returns. */
export interface WorkflowTransitionStateChange {
  id: string;
  previous_state: string;
  new_state: string;
}
