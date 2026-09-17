/**
 * GH-353 Task 8 — DiagramGraphEditor barrel export (named exports only).
 *
 * Design decisions (ADR-DS-02):
 *   - Node positions are persisted in the node_graph JSON payload, not localStorage.
 *     See useGraphPayload.ts:flowToPayload() for the serialization boundary.
 *     This ensures positions survive browser restart and are shareable across team members.
 *   - Preview uses React Flow canvas renderer (client-side); SVG export is explicit
 *     (Task 6 endpoint: POST /diagrams/{id}/export?format=svg).
 *   - Positions stored in payload (REQ-L1-100) enables DIAGRAM_REF reconciliation (REQ-L1-101).
 */

export { DiagramGraphEditorPage } from "./DiagramGraphEditorPage";
