/**
 * REQ-176 — Workflow Editor shared constants + selection types.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 */

import type { WorkflowEntityType } from "../../api/workflows";
import type { WorkspacePreset } from "../../types";

/**
 * Scope the editor operates in (REQ-178/179). ``workspace`` is the original,
 * default behaviour (per-workspace definition); ``global`` edits the tenant-wide
 * default for a specific preset (System Settings → Workflow Defaults, SCR-205).
 */
export type WorkflowScope =
  | { kind: "workspace"; workspaceId: string | undefined }
  | { kind: "global"; preset: WorkspacePreset };

/** The three rigor presets, in ascending order (global defaults are per-preset). */
export const WORKFLOW_PRESETS: readonly WorkspacePreset[] = [
  "minimal",
  "standard",
  "extended",
] as const;

/** The entity types the editor visualises, with human-readable labels. */
export interface EntityTypeDescriptor {
  type: WorkflowEntityType;
  label: string;
}

export const WORKFLOW_ENTITY_TYPES: readonly EntityTypeDescriptor[] = [
  { type: "Requirement", label: "Requirement" },
  { type: "StakeholderNeed", label: "Stakeholder Need" },
  { type: "ArchitectureElement", label: "Architecture" },
  { type: "Adr", label: "ADR" },
  { type: "Risk", label: "Risk" },
  { type: "TestCase", label: "Test Case" },
  { type: "Issue", label: "Issue" },
  { type: "Goal", label: "Goal" },
  { type: "MainGoal", label: "Main Goal" },
] as const;

/** Default entity type shown when the route carries none. */
export const DEFAULT_ENTITY_TYPE: WorkflowEntityType = "Requirement";

/** Map a URL slug (lower-case) to the canonical entity type, or null. */
export function entityTypeFromSlug(
  slug: string | undefined
): WorkflowEntityType | null {
  if (!slug) return null;
  const match = WORKFLOW_ENTITY_TYPES.find(
    (e) => e.type.toLowerCase() === slug.toLowerCase()
  );
  return match ? match.type : null;
}

/** Human label for an entity type. */
export function entityTypeLabel(type: WorkflowEntityType): string {
  return WORKFLOW_ENTITY_TYPES.find((e) => e.type === type)?.label ?? type;
}

/** What the user has currently selected on the canvas. */
export type Selection =
  | { kind: "none" }
  | { kind: "state"; id: string }
  | { kind: "transition"; id: string };
