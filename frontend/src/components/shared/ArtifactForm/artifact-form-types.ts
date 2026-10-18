/**
 * Shared type surface of the definition-driven artifact form (spec section 6).
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01) so
 * the orchestrator, the state hook, the section renderer and the payload
 * helpers can agree on one set of types without importing each other. The
 * public names (`ArtifactFormValues`, `ArtifactFormProps`, `FormSection`) are
 * re-exported from `ArtifactForm.tsx` — the barrel `index.ts` is unchanged.
 */

import type { ReactNode } from "react";

import type {
  AttributeAudience,
  AttributeItemType,
  AttributeSpec,
  SectionLayout,
  SpacerSize,
} from "../../../api/attribute-definitions";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";

export interface ArtifactFormValues {
  [name: string]: unknown;
  custom_fields?: Record<string, unknown>;
}

export interface ArtifactFormProps {
  /** Attribute-definition item type, e.g. "Risk". */
  itemType: AttributeItemType;
  /** `null` = create mode: no delete affordance, no workflow status editor. */
  artifactId: string | null;
  initialValues: ArtifactFormValues;
  onSave: (values: ArtifactFormValues) => Promise<ArtifactFormValues | void>;
  /**
   * Runs the workflow transition that marks the artifact outdated/deprecated.
   * `targetState` is the outdated-equivalent target the transitions API
   * currently allows; `changeReason` is mandatory when the transition (or the
   * workspace preset) demands one, the empty string otherwise.
   */
  onDeprecate?: (targetState: string, changeReason?: string) => Promise<void>;
  onDirtyChange?: (isDirty: boolean) => void;
  /** `"read"` disables every control (Rollenbasierte-Sichten spec). */
  mode?: "edit" | "read";
  /** Enables the workflow status editor for `editable: "workflow"` attributes. */
  workflowArtifactType?: WorkflowArtifactType;
  /**
   * Extended-preset rule (REQ-162): a save (and, per F-1, a delete) must
   * carry a change reason. The capability lives here, opt-in via this prop,
   * rather than in one adapter — so it is AVAILABLE to every type, not
   * automatically active for every type; only Requirement passes it today.
   * Ignored in create mode (`artifactId === null`): there is no change to explain.
   */
  requiresChangeReason?: boolean;
  /**
   * Per-attribute overrides on top of the resolved definition (issue #889).
   *
   * A type adapter uses this to align a server-side definition that fell back
   * to a plain field type with the enum its create dialog and list filter
   * already use — the canonical case is `Requirement.category`, whose Django
   * column carries no `choices`, so introspection declares `type: "text"` and
   * the detail form rendered free text while create/list only recognize the six
   * `REQ_CATEGORIES` values. Applied before rendering AND before the payload is
   * built, so the control and the emitted value stay in sync.
   *
   * Callers pass a module-level constant so the object identity stays stable
   * across renders (an inline literal would invalidate every definition-derived
   * memo on each render).
   */
  attributeOverrides?: Record<string, Partial<AttributeSpec>>;
  /** Optional legacy create form, shown alongside the definition-load error. */
  definitionFallback?: ReactNode;
  /** Create-dialog cancel action; edit adapters may omit it. */
  onCancel?: () => void;
  /** Adapter-owned selectors for existing create-dialog automation. */
  fieldTestIds?: Record<string, string>;
  saveTestId?: string;
  /**
   * Adapter-owned action row rendered at the top of the form, before the
   * sections (issue #424: the TestCase "mark reviewed" action). Additive and
   * optional — the shared renderer keeps owning layout, the adapter owns what
   * the actions mean.
   */
  headerActions?: ReactNode;
}

export interface FormSection {
  name: string;
  audience: AttributeAudience;
  attributes: AttributeSpec[];
}

/** One grid item of the section area (WS4 #938): a rendered section or an
 * empty spacer. */
export type SectionEntry =
  | { kind: "section"; section: FormSection; layout: SectionLayout }
  | { kind: "spacer"; size: SpacerSize };

/** One outstanding "move the focus to what failed" request. */
export interface FocusRequest {
  /** Distinguishes two consecutive failed saves with the same field. */
  nonce: number;
  /** Attribute name to focus, or `null` for a form-level failure. */
  field: string | null;
}
