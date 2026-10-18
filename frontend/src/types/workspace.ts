/**
 * Workspace, presets, terminology profile and visibility rules.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { GlossaryReferenceMode, ISODateTime, UUID } from "./common";

// ---------------------------------------------------------------------------
// Workspace (not yet in backend API — see ESCALATION notes)
// ---------------------------------------------------------------------------

export type WorkspacePreset = "minimal" | "standard" | "extended";
export type TerminologyProfile = "dev_mode" | "se_mode";

export interface Workspace {
  id: UUID;
  name: string;
  preset: WorkspacePreset;
  terminology_profile: TerminologyProfile;
  language: string;
  /** Workspace-default theme id (multi-palette theming, #568). Matches a
   *  `ThemeDefinition.id` from `context/ThemeContext.tsx`'s `THEMES`
   *  registry; defaults to `"dark"` server-side. */
  theme: string;
  /**
   * @deprecated Legacy free-form prompt blob, no longer read or written by the
   * UI (issue #119). Prompt templates live in the `PromptTemplate` model and
   * are edited via `/api/v1/prompt-templates/slots/` (see
   * `api/prompt-templates.ts`). Still serialized by the backend, so the field
   * is kept on the type until it is dropped there.
   */
  ai_prompts?: Record<string, string>;
  decomposition_link_type?: string;
  default_link_type?: string;
  is_active: boolean;
  closed_at: ISODateTime | null;
  closed_by: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  /** Ziele-Feature (Goal/MainGoal) für diesen Workspace aktiviert. */
  goals_enabled?: boolean;
  /** KI-gestützte MainGoal-Generierung aktiviert (erfordert goals_enabled). */
  goals_ai_enabled?: boolean;
  /** #1266: Auflösung von Glossar-Referenz-Tokens (Default `pinned`). */
  glossary_reference_mode?: GlossaryReferenceMode;
}

export interface WorkspaceWithMetrics extends Workspace {
  requirement_count: number;
  open_item_count: number;
}

// ---------------------------------------------------------------------------
// Preset visibility rules (REQ-L2-RF-007)
// ---------------------------------------------------------------------------

export const PRESET_VISIBILITY: Record<WorkspacePreset, Record<string, boolean>> = {
  minimal: {
    baselines: false,
    global_baselines: false,
    workflow_config: false,
    approver_ui: false,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
    adr: false,
    risk: false,
    issue: false,
    csv_import: false,
    icds: false,
    diagrams: false,
    metrics: false,
    testCases: false,
  },
  standard: {
    baselines: true,
    global_baselines: false,
    workflow_config: true,
    approver_ui: false,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
    adr: true,
    risk: true,
    issue: true,
    csv_import: true,
    icds: true,
    diagrams: true,
    metrics: true,
    testCases: true,
  },
  extended: {
    baselines: true,
    global_baselines: true,
    workflow_config: true,
    approver_ui: true,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
    adr: true,
    risk: true,
    issue: true,
    csv_import: true,
    icds: true,
    diagrams: true,
    metrics: true,
    testCases: true,
  },
};

// ---------------------------------------------------------------------------
// Terminology profile label maps (REQ-L2-RF-008)
// ---------------------------------------------------------------------------

export type TerminologyLabels = {
  requirement: string;
  requirements: string;
  epic: string;
  story: string;
  task: string;
  system: string;
  subsystem: string;
  component: string;
};

export const TERMINOLOGY_LABELS: Record<TerminologyProfile, TerminologyLabels> = {
  dev_mode: {
    requirement: "Story",
    requirements: "Stories",
    epic: "Epic",
    story: "Story",
    task: "Task",
    system: "System",
    subsystem: "Module",
    component: "Component",
  },
  se_mode: {
    requirement: "Requirement",
    requirements: "Requirements",
    epic: "System",
    story: "Subsystem",
    task: "Component",
    system: "System",
    subsystem: "Subsystem",
    component: "Component",
  },
};
