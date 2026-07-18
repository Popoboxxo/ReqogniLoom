/**
 * REQ-176 — Mermaid stateDiagram-v2 export for the workflow graph.
 *
 * Read-only export used by the "Copy as Mermaid" action (design brief §5, §10).
 * State names may contain spaces (e.g. Adr "In Review"), which are not valid
 * mermaid state identifiers, so each state gets a sanitized id plus a label.
 */

import type { WorkflowGraph, WorkflowState } from "../../api/workflows";

/** Sanitize a state name into a mermaid-safe identifier. */
function stateId(name: string): string {
  const id = name.replace(/[^a-zA-Z0-9_]/g, "_");
  return /^[a-zA-Z_]/.test(id) ? id : `s_${id}`;
}

/**
 * Render a WorkflowGraph as mermaid ``stateDiagram-v2`` source text.
 * The initial state is linked from ``[*]``; terminal states link to ``[*]``.
 */
export function toMermaid(graph: WorkflowGraph): string {
  const lines: string[] = ["stateDiagram-v2"];

  // Declare states with human labels when the id had to be sanitized.
  for (const state of graph.states) {
    const id = stateId(state.name);
    if (id !== state.name) {
      lines.push(`  ${id}: ${state.name}`);
    }
  }

  const initial = graph.states.find((s: WorkflowState) => s.isInitial);
  if (initial) {
    lines.push(`  [*] --> ${stateId(initial.name)}`);
  }

  for (const t of graph.transitions) {
    const from = stateId(t.from_state);
    const to = stateId(t.to_state);
    const guard = t.signature_gate ? " [sig]" : "";
    const lock = t.change_reason_required ? " 🔒" : "";
    lines.push(`  ${from} --> ${to}: ${t.to_state}${guard}${lock}`);
  }

  // Terminal states (no outgoing transitions) flow to the final pseudo-state.
  for (const state of graph.states) {
    if (state.outgoingCount === 0 && !state.isInitial) {
      lines.push(`  ${stateId(state.name)} --> [*]`);
    }
  }

  return lines.join("\n");
}
