/**
 * REQ-177 — Client-side node-position persistence for the Workflow Editor.
 *
 * The backend workflow model stores no layout coordinates (states are plain
 * status strings — see backend/workflow/definition_store.py), so hand-arranged
 * node positions are persisted per (workspace, entity type) in localStorage.
 * This is a deliberate deviation from a server-side field: layout is a
 * presentation concern local to the editing user, and adding a coordinates
 * column would require a persistence migration for data the engine never reads.
 * On load, stored positions override the dagre auto-layout; unknown nodes fall
 * back to their computed position.
 */

import { safeLocalStorage } from "../../utils/safeStorage";

export interface XY {
  x: number;
  y: number;
}

export type PositionMap = Record<string, XY>;

function key(workspaceId: string, entityType: string): string {
  return `reqflow_workflow_positions_${workspaceId}_${entityType}`;
}

export function loadPositions(
  workspaceId: string,
  entityType: string
): PositionMap {
  try {
    const raw = safeLocalStorage.getItem(key(workspaceId, entityType));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") return parsed as PositionMap;
  } catch {
    /* malformed stored payload — fall back to the computed (dagre) layout */
  }
  return {};
}

export function savePositions(
  workspaceId: string,
  entityType: string,
  positions: PositionMap
): void {
  try {
    safeLocalStorage.setItem(key(workspaceId, entityType), JSON.stringify(positions));
  } catch {
    /* unserializable payload — layout persistence is best-effort */
  }
}
