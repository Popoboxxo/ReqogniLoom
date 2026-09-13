/**
 * ARCH-L1-001 ReactFrontend — Attribute Definition API.
 *
 * Wraps /api/v1/attribute-defaults/ (tenant-wide, per item_type + preset) and
 * /api/v1/workspaces/{id}/attribute-definitions/{item_type}/ (resolved copy).
 *
 * The resolved shape is what ArtifactForm renders and what the table view
 * derives its columns and filter operators from — it is the single client-side
 * source for "what fields does this artifact type have".
 */

import { apiClient } from "./client";
import type { UUID, WorkspacePreset } from "../types";

/**
 * The 11 bootstrapped item types (verified against
 * `backend/attribute_definitions/schema.py::ITEM_TYPES`) — kept as its own
 * union instead of a bare `string` because the frontend already has two other,
 * incompatible item-type vocabularies (`WorkflowEntityType`,
 * `ArtifactKind` in `components/shared/ArtifactInspector/types.ts`, the latter
 * lowercase camelCase) that a caller could pass here by mistake and get a
 * silent 404 instead of a compile error.
 */
export type AttributeItemType =
  | "Requirement"
  | "StakeholderNeed"
  | "ArchitectureElement"
  | "TestCase"
  | "Adr"
  | "Risk"
  | "Issue"
  | "Goal"
  | "Icd"
  | "GlossaryTerm"
  | "ChangeRequest";

export type AttributeKind = "core" | "extended";

export type AttributeType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "enum"
  | "multi-enum"
  | "date"
  | "reference"
  | "user"
  | "actor"
  | "widget";

/**
 * How an attribute may be changed.
 *
 * `true`/`false` are the ordinary editable/read-only pair; `"workflow"` means
 * "changeable only through a workflow transition"; `"system"` means
 * server-owned (the Artifact's own `id`) and `"automation"` is reserved for
 * AWMS-derived values (spec section 6). Mirrors the backend's
 * `attribute_definitions.schema.EDITABLE_VALUES`; `"system"`/`"automation"`
 * were missing here, so a definition carrying them narrowed to `never` in a
 * comparison and could fall through to an editable control (WS2 #936).
 */
export type AttributeEditable = boolean | "workflow" | "system" | "automation";

/** Display density only — never a visibility or security boundary. */
export type AttributeAudience = "basic" | "expert";

/**
 * Generic display/interaction properties (Attribut v3 WS3, #937, spec section
 * 5). They apply to **every** attribute regardless of `kind`/`type`:
 * `reveal` selects the "always visible / reveal on click / reveal on
 * shortcut" mode, `mask` shortens the *rendered* label while `copyable`
 * copies the full value, and `display_format` is a purely visual choice.
 * Mirrors the backend's `attribute_definitions.schema.REVEAL_VALUES` etc.
 */
export type AttributeReveal = "always" | "click" | "shortcut";
export type AttributeMask = "none" | "short";
export type AttributeDisplayFormat = "text" | "mono" | "chips";

export type WidgetKey =
  | "risk_matrix_rpz"
  | "markdown_tab_group"
  | "steps_editor"
  | "tag_input";

export interface AttributeOption {
  value: string;
  label_de: string;
  label_en: string;
}

export interface LocalizedText {
  de: string;
  en: string;
}

export interface AttributeValidationRules {
  regex?: string;
  min?: number;
  max?: number;
  length?: number;
}

/** One entry of `definition_json.attributes[]` — the published contract. */
export interface AttributeSpec {
  name: string;
  kind: AttributeKind;
  type: AttributeType;
  widget_key: WidgetKey | null;
  fields: string[];
  options: AttributeOption[];
  required: boolean;
  visible: boolean;
  locked: boolean;
  editable: AttributeEditable;
  section: string;
  order: number;
  label: LocalizedText;
  help_text: LocalizedText;
  default: unknown;
  validation: AttributeValidationRules;
  ai_elicit: boolean;
  export: boolean;
  audience: AttributeAudience;
  /**
   * Actor-specific properties (Attribut v3 WS2, #936, spec section 4). The
   * backend normalizes them onto every attribute (`schema.py::_DEFAULTS`) but
   * only consumes them when `type == "actor"`; the field renderer therefore
   * reads them only for that type. Optional here so every pre-existing
   * `AttributeSpec` literal (tests, fixtures) stays valid.
   *
   * `multiple` selects the wire value shape (`{"multiple": true, "items":
   * [...]}` vs. a single entry) and `allow_external` gates the "create as
   * external person" affordance.
   */
  multiple?: boolean;
  allow_external?: boolean;
  /**
   * Generic display/interaction properties (Attribut v3 WS3, #937, spec
   * section 5). The backend normalizes them onto every attribute
   * (`schema.py::_DEFAULTS`: `copyable=false`, `reveal="always"`,
   * `mask="none"`, `display_format="text"`), so an attribute written before
   * this feature existed keeps its old rendering. They are optional here so
   * every pre-existing `AttributeSpec` literal (tests, fixtures) stays valid;
   * consumers resolve them through `resolveDisplayProps` (which applies the
   * same defaults) rather than reading the fields directly.
   */
  copyable?: boolean;
  reveal?: AttributeReveal;
  mask?: AttributeMask;
  display_format?: AttributeDisplayFormat;
}

/** Where an attribute in a resolved (workspace-scoped) definition comes from
 * — Task 4's "Herkunft" table column. `"global_customized"` marks EVERY
 * inherited attribute once the workspace has any local edit at all
 * (`is_customized` is per-definition, not per-attribute — see the backend's
 * `AttributeDefinitionService._workspace_payload` docstring). */
export type AttributeOrigin = "global" | "global_customized" | "workspace_only";

/** Section-level layout in `ArtifactForm`'s CSS Grid (Task 7/8, spec section
 * 4.4/4.5): `"full"` spans both columns, `"half"` shares a row with another
 * `"half"` section (or leaves the second column empty if it is alone). Mapped
 * onto the 12-column grid as full=12/half=6 (WS4 #938). */
export type SectionLayout = "full" | "half";

/**
 * An attribute's width on the 12-column grid (Attribut v3 WS4 #938, spec
 * section 7): `full`=12, `half`=6, `quarter`=3. Mirrors the backend's
 * `attribute_definitions.schema.SPAN_COLUMNS`.
 */
export type AttributeSpan = "full" | "half" | "quarter";

/**
 * Relative size of a spacer token (spec section 7): `sm`=1, `md`=2, `lg`=4
 * columns. Mirrors `attribute_definitions.schema.SPACER_COLUMNS`.
 */
export type SpacerSize = "sm" | "md" | "lg";

/** One definition-level `section_flow` token positioning a whole section.
 * The section's own width still comes from its `layout` — a section token
 * carries no width of its own (spec section 7). */
export interface SectionFlowToken {
  kind: "section";
  name: string;
}

/** One section-level `attribute_flow` token positioning an attribute.
 * `span` is optional: omitted means `"full"` (the backend's
 * `_DEFAULT_ATTRIBUTE_SPAN`, i.e. the pre-WS4 full-width stacking). */
export interface AttributeFlowToken {
  kind: "attribute";
  name: string;
  span?: AttributeSpan;
}

/** A spacer on either level — consumes `sm`=1/`md`=2/`lg`=4 of the 12 columns
 * and renders as empty space (spec section 7). */
export interface SpacerFlowToken {
  kind: "spacer";
  size: SpacerSize;
}

/**
 * A single layout token of a `section_flow` or `attribute_flow` (WS4 #938).
 *
 * One flat union for both levels: which kinds are legal per level (`section`
 * vs `attribute`) is enforced server-side by
 * `attribute_definitions.schema.SECTION_FLOW_KINDS`/`ATTRIBUTE_FLOW_KINDS`,
 * not by this type — the frontend only ever reads flows the backend already
 * normalized.
 */
export type LayoutToken = SectionFlowToken | AttributeFlowToken | SpacerFlowToken;

export interface SectionSpec {
  name: string;
  order: number;
  visible: boolean;
  layout: SectionLayout;
  /**
   * Section-level layout tokens (WS4 #938, spec section 7). Optional and
   * **additive**: a section without the key renders its attributes in `order`
   * at full span, exactly as before the 12-column engine existed. Consumers
   * derive the default through `resolveAttributeFlow` instead of assuming the
   * key exists (mirrors the backend's `effective_attribute_flow`).
   */
  attribute_flow?: LayoutToken[];
}

export interface ResolvedAttributeDefinition {
  item_type: AttributeItemType;
  preset: WorkspacePreset;
  is_customized: boolean;
  version: number;
  attributes: AttributeSpec[];
  /** `attribute.name` -> its origin. Present on every resolved (workspace-
   * scoped) definition; absent on the global-scope payload, which has no
   * origin concept. */
  origins: Record<string, AttributeOrigin>;
  sections: SectionSpec[];
  /**
   * Definition-level layout tokens (WS4 #938, spec section 7). Optional and
   * additive — absent means "no stored flow", i.e. sections render in their
   * own order (the backend's `effective_section_flow` derivation). Consumers
   * must NOT treat `undefined` and `[]` alike: an empty stored flow is a real
   * (if degenerate) value and is passed through unchanged.
   */
  section_flow?: LayoutToken[];
}

/** What `AttributeCreateDialog` collects — always creates a `kind: "extended"`
 * entry (only the bootstrap command may create `kind: "core"`). */
export interface NewAttributeInput {
  name: string;
  type: AttributeType;
  required: boolean;
  section: string;
  options?: AttributeOption[];
}

/** Task 9/10/11: `export_definition`'s output, and `import_definition`'s
 * expected input — a whole definition serialized for download/re-upload. */
export interface AttributeDefinitionDocument {
  schema_version: number;
  item_type: AttributeItemType;
  attributes: AttributeSpec[];
  sections: SectionSpec[];
  /** Definition-level layout tokens (WS4 #938) — present only when the
   * exported definition stored one; the import path sends the document back
   * as-is, so this travels without extra handling. */
  section_flow?: LayoutToken[];
}

export type OnCollision = "skip" | "overwrite" | "rename";

export interface GlobalAttributeDefinition {
  item_type: AttributeItemType;
  preset: WorkspacePreset;
  initialized: boolean;
  version: number;
  attributes: AttributeSpec[];
  sections: SectionSpec[];
  /** Definition-level layout tokens (WS4 #938) — see
   * {@link ResolvedAttributeDefinition.section_flow}. */
  section_flow?: LayoutToken[];
  /** Present on a PUT response: how many on-default workspaces were updated. */
  propagated_workspace_count?: number;
}

function globalPath(itemType: AttributeItemType, preset: WorkspacePreset): string {
  return `/attribute-defaults/${encodeURIComponent(itemType)}/${encodeURIComponent(
    preset
  )}/`;
}

function workspacePath(workspaceId: UUID, itemType: AttributeItemType): string {
  return `/workspaces/${workspaceId}/attribute-definitions/${encodeURIComponent(
    itemType
  )}/`;
}

function createPayload(input: NewAttributeInput): Record<string, unknown> {
  return {
    name: input.name,
    kind: "extended",
    type: input.type,
    required: input.required,
    section: input.section,
    ...(input.options ? { options: input.options } : {}),
  };
}

export const attributeDefinitionsApi = {
  async listGlobal(filters?: {
    itemType?: AttributeItemType;
    preset?: WorkspacePreset;
  }): Promise<GlobalAttributeDefinition[]> {
    const query = new URLSearchParams();
    if (filters?.itemType) query.set("item_type", filters.itemType);
    if (filters?.preset) query.set("preset", filters.preset);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const raw = await apiClient.get<{ definitions: GlobalAttributeDefinition[] }>(
      `/attribute-defaults/${suffix}`
    );
    return raw.definitions;
  },

  /** Never 404s: an unseeded type returns `initialized: false` with no attributes. */
  getGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.get<GlobalAttributeDefinition>(globalPath(itemType, preset));
  },

  /** `sections` (Task 8) and `sectionFlow` (WS4 #938) are optional —
   * omitted, the backend preserves the row's current value unchanged; passed,
   * it replaces it. An explicit empty `sectionFlow` is passed through (a real
   * stored value), `undefined` omits the key entirely. */
  putGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    attributes: AttributeSpec[],
    sections?: SectionSpec[],
    sectionFlow?: LayoutToken[]
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.put<GlobalAttributeDefinition>(globalPath(itemType, preset), {
      attributes,
      ...(sections ? { sections } : {}),
      ...(sectionFlow !== undefined ? { section_flow: sectionFlow } : {}),
    });
  },

  getWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.get<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType)
    );
  },

  /** `sections`/`sectionFlow` are optional — see {@link putGlobal}. */
  putWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType,
    attributes: AttributeSpec[],
    sections?: SectionSpec[],
    sectionFlow?: LayoutToken[]
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.put<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType),
      {
        attributes,
        ...(sections ? { sections } : {}),
        ...(sectionFlow !== undefined ? { section_flow: sectionFlow } : {}),
      }
    );
  },

  resetWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}reset/`,
      {}
    );
  },

  createGlobalAttribute(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    input: NewAttributeInput
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.post<GlobalAttributeDefinition>(
      globalPath(itemType, preset),
      createPayload(input)
    );
  },

  deleteGlobalAttribute(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    name: string
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.delete<GlobalAttributeDefinition>(
      `${globalPath(itemType, preset)}?name=${encodeURIComponent(name)}`
    );
  },

  createWorkspaceAttribute(
    workspaceId: UUID,
    itemType: AttributeItemType,
    input: NewAttributeInput
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType),
      createPayload(input)
    );
  },

  deleteWorkspaceAttribute(
    workspaceId: UUID,
    itemType: AttributeItemType,
    name: string
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.delete<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}?name=${encodeURIComponent(name)}`
    );
  },

  /** Artifacts in this workspace referencing `name` — call before showing a
   * delete/option-removal confirmation (Task 5). Workspace-scoped only: the
   * backend's `count_usages` takes a single workspace, there is no
   * cross-workspace aggregate for the global scope. */
  getUsageCount(
    workspaceId: UUID,
    itemType: AttributeItemType,
    name: string,
    optionValue?: string
  ): Promise<number> {
    const query = new URLSearchParams({ name });
    if (optionValue !== undefined) query.set("option", optionValue);
    return apiClient
      .get<{ count: number }>(`${workspacePath(workspaceId, itemType)}usage/?${query}`)
      .then((result) => result.count);
  },

  exportGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset
  ): Promise<AttributeDefinitionDocument> {
    return apiClient.get<AttributeDefinitionDocument>(
      `${globalPath(itemType, preset)}export/`
    );
  },

  importGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    document: AttributeDefinitionDocument,
    onCollision: OnCollision = "skip"
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.post<GlobalAttributeDefinition>(
      `${globalPath(itemType, preset)}import/?on_collision=${onCollision}`,
      document
    );
  },

  exportWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType
  ): Promise<AttributeDefinitionDocument> {
    return apiClient.get<AttributeDefinitionDocument>(
      `${workspacePath(workspaceId, itemType)}export/`
    );
  },

  importWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType,
    document: AttributeDefinitionDocument,
    onCollision: OnCollision = "skip"
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}import/?on_collision=${onCollision}`,
      document
    );
  },
};

/** Triggers a browser download of *doc* as pretty-printed JSON. Mirrors
 * `api/export.ts`'s CSV/ReqIF download functions' Blob + `<a download>`
 * pattern -- this codebase has no shared helper for it (checked: both
 * existing instances duplicate it independently), so a third small
 * duplicate matches the established convention rather than introducing a
 * new shared utility for three call sites. */
export function downloadAttributeDefinitionDocument(
  doc: AttributeDefinitionDocument,
  filename: string
): void {
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
  const link = window.document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}
