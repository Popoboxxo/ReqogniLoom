/**
 * REQ-176 — Workflow Editor shared constants + selection types.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 */

import type {
  WorkflowEntityType,
  WorkflowPresetKey,
} from "../../api/workflows";
import type { WorkspacePreset } from "../../types";

/**
 * Scope the editor operates in (REQ-178/179). ``workspace`` is the original,
 * default behaviour (per-workspace definition); ``global`` edits the tenant-wide
 * default for a specific preset (System Settings → Workflow Defaults, SCR-205).
 */
export type WorkflowScope =
  | {
      kind: "workspace";
      workspaceId: string | undefined;
      /** Active rigor tier; part of the cache identity because it selects the graph. */
      preset?: WorkspacePreset;
    }
  | { kind: "global"; preset: WorkflowPresetKey };

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
  { type: "Document", label: "Document" },
  { type: "WorkItem", label: "Work Item" },
] as const;

/** Fixed preset keys for entity types whose lifecycle does not follow the tier. */
const FIXED_ENTITY_PRESETS = {
  StakeholderNeed: "need_default",
  ArchitectureElement: "architecture_default",
  Adr: "adr_default",
  Risk: "risk_default",
  TestCase: "testcase_default",
  Issue: "issue_default",
  Goal: "goal_default",
  MainGoal: "main_goal_default",
  Document: "document_default",
} as const satisfies Record<
  Exclude<WorkflowEntityType, "Requirement" | "WorkItem">,
  WorkflowPresetKey
>;

/** WorkItem follows the rigor tier but keeps its own preset-key namespace. */
export const WORK_ITEM_WORKFLOW_PRESETS: readonly WorkflowPresetKey[] =
  WORKFLOW_PRESETS.map<WorkflowPresetKey>((preset) => `work_item_${preset}`);

/** Canonical global preset choices for one entity type. */
export function workflowPresetsForEntity(
  type: WorkflowEntityType
): readonly WorkflowPresetKey[] {
  if (type === "Requirement") return WORKFLOW_PRESETS;
  if (type === "WorkItem") return WORK_ITEM_WORKFLOW_PRESETS;
  return [FIXED_ENTITY_PRESETS[type]];
}

/** Preset used when an entity is selected without an explicit valid preset. */
export function defaultWorkflowPreset(
  type: WorkflowEntityType,
  tier: WorkspacePreset = "standard"
): WorkflowPresetKey {
  if (type === "Requirement") return tier;
  if (type === "WorkItem") return `work_item_${tier}`;
  return FIXED_ENTITY_PRESETS[type];
}

/** Validate a URL/query preset against the selected entity's canonical choices. */
export function isWorkflowPresetForEntity(
  type: WorkflowEntityType,
  preset: string | null | undefined
): preset is WorkflowPresetKey {
  return (
    preset != null && workflowPresetsForEntity(type).some((key) => key === preset)
  );
}

/** Recover the rigor tier from a Requirement or WorkItem preset key. */
export function workflowPresetTier(
  preset: WorkflowPresetKey
): WorkspacePreset | null {
  const directTier = WORKFLOW_PRESETS.find((tier) => tier === preset);
  if (directTier) return directTier;
  return (
    WORKFLOW_PRESETS.find((tier) => `work_item_${tier}` === preset) ?? null
  );
}

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
