/**
 * Definition-driven artifact form (spec section 6).
 *
 * Replaces the seven hand-written forms. Everything it draws comes from the
 * resolved attribute definition: sections and their order, fields and their
 * order, labels, help text, requiredness, enum options, widgets and the
 * default expand density (`audience`).
 *
 * Parity policy (spec section 6.3): dirty warning, delete-in-form, status as
 * badge + transition buttons and definition-driven visibility are available for
 * EVERY type here — the migration unifies upward onto the best behaviour any of
 * the seven forms had, it never cuts one.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, ChevronDown, ChevronRight } from "lucide-react";

import type {
  AttributeAudience,
  AttributeItemType,
  AttributeSpec,
  SectionLayout,
  SectionSpec,
  SpacerSize,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import { useEntityReset } from "../../../hooks/use-entity-reset";
import { useFormDirty } from "../../../hooks/use-form-dirty";
import { SAVE_SHORTCUT_ARIA, useSaveShortcut } from "../../../hooks/useSaveShortcut";
import { ConfirmDialog } from "../ConfirmDialog";
import { RevealValue } from "../RevealValue";
import { WorkflowStatusEditor } from "../../WorkflowStatusEditor";
import styles from "./ArtifactForm.module.css";
import { fieldErrorsFromException } from "./field-errors";
import {
  orderedSectionTokens,
  resolveAttributeFlow,
  sectionLayoutColumns,
  spacerColumns,
  spanClassSuffix,
} from "./layout-flow";
import {
  BooleanToggle,
  DateField,
  DisplayField,
  EnumSelect,
  MultiEnum,
  NumberField,
  ReferencePicker,
  TextArea,
  TextField,
  UserPicker,
  ActorPicker,
  attributeLabel,
  hasConfiguredDisplay,
  resolveDisplayProps,
  type ActorFieldValue,
} from "./fields";
import { stripNonEditableValues } from "./payload";
import { useArtifactDefinition } from "./useArtifactDefinition";
import { useGateRequiredFields } from "./useGateRequiredFields";
import { resolveWidget } from "./widget-registry";

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
  onSave: (values: ArtifactFormValues) => Promise<void>;
  /**
   * `changeReason` is the trimmed value of the shared change-reason field
   * (F-1, Task 25 fix round 1) — passed only when `requiresChangeReason` is
   * active and in edit mode, `undefined` otherwise. Callers that never opt
   * into `requiresChangeReason` can ignore the argument.
   */
  onDelete?: (changeReason?: string) => Promise<void>;
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
type SectionEntry =
  | { kind: "section"; section: FormSection; layout: SectionLayout }
  | { kind: "spacer"; size: SpacerSize };

/**
 * Group attributes into sections.
 *
 * Section order is first-appearance in the definition; attribute order inside a
 * section is the definition's own `order` (the backend already sorts by
 * `(section, order, name)`, but a hand-edited definition PUT through
 * `/attribute-defaults/` is not re-sorted, so the client sorts too — one
 * `.sort` is cheaper than a rendering order nobody can explain).
 */
export function groupIntoSections(attributes: AttributeSpec[]): FormSection[] {
  const order: string[] = [];
  const bySection = new Map<string, AttributeSpec[]>();
  for (const attribute of attributes) {
    if (!bySection.has(attribute.section)) {
      bySection.set(attribute.section, []);
      order.push(attribute.section);
    }
    bySection.get(attribute.section)!.push(attribute);
  }
  return order.map((name) => {
    const sectionAttributes = [...bySection.get(name)!].sort(
      (a, b) => a.order - b.order
    );
    return {
      name,
      // A section is "expert" only when EVERY attribute in it is — one basic
      // attribute would otherwise be hidden behind a collapsed header.
      audience: sectionAttributes.every((a) => a.audience === "expert")
        ? "expert"
        : "basic",
      attributes: sectionAttributes,
    };
  });
}

function readValue(values: ArtifactFormValues, attribute: AttributeSpec): unknown {
  return attribute.kind === "extended"
    ? (values.custom_fields ?? {})[attribute.name]
    : values[attribute.name];
}

function writeValue(
  values: ArtifactFormValues,
  attribute: AttributeSpec,
  next: unknown
): ArtifactFormValues {
  if (attribute.kind === "extended") {
    return {
      ...values,
      custom_fields: { ...(values.custom_fields ?? {}), [attribute.name]: next },
    };
  }
  return { ...values, [attribute.name]: next };
}

// ---------------------------------------------------------------------------
// Issue #1087 — error-to-field focus routing
// ---------------------------------------------------------------------------

/** One outstanding "move the focus to what failed" request. */
interface FocusRequest {
  /** Distinguishes two consecutive failed saves with the same field. */
  nonce: number;
  /** Attribute name to focus, or `null` for a form-level failure. */
  field: string | null;
}

/**
 * Elements that take focus without a `tabindex`. Anything else in a field cell
 * is a composite (a widget) and needs `tabindex="-1"` before a programmatic
 * focus can land on it.
 */
const FOCUSABLE_SELECTOR = /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/;

/**
 * The first errored attribute in DEFINITION order, not in `Object.keys` order:
 * the definition is the order the fields are drawn in, so this is the topmost
 * offending control on screen. An error naming a field the definition does not
 * declare (e.g. a `custom_fields` key) still resolves, so the fallback is the
 * first key rather than nothing.
 */
export function firstErroredField(
  errors: Record<string, string[]>,
  attributes: readonly AttributeSpec[]
): string | null {
  const names = Object.keys(errors);
  if (names.length === 0) return null;
  const inDefinitionOrder = attributes
    .filter((attribute) => names.includes(attribute.name))
    .map((attribute) => attribute.name);
  return inDefinitionOrder[0] ?? names[0];
}

/**
 * Locate the focus target for the attribute named `name`.
 *
 * Two shapes, tried in this order:
 *   1. the field's own control — every `FieldShell`-based control takes its
 *      `id` AND its `data-testid` from the same `testId` (see
 *      `fields/FieldShell.tsx`), possibly renamed by the adapter's
 *      `fieldTestIds` (#583);
 *   2. the composite that draws it — an attribute with `type: "widget"` claims
 *      the fields in its `fields` list and is not rendered standalone
 *      (`widgetOwned` in the renderer), so the widget's own container is the
 *      only focusable thing on screen for a failure inside it. Widgets name
 *      their inner controls differently from each other, so resolving those
 *      per widget would be a second, drifting lookup table.
 */
export function findFieldControl(
  root: HTMLElement | null,
  name: string,
  fieldTestIds?: Record<string, string>,
  attributes?: readonly AttributeSpec[]
): HTMLElement | null {
  if (!root) return null;
  const testId = fieldTestIds?.[name] ?? `artifact-field-${name}`;
  const direct = root.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  if (direct) return direct;
  const owner = attributes?.find(
    (attribute) => attribute.type === "widget" && attribute.fields.includes(name)
  );
  return owner
    ? root.querySelector<HTMLElement>(`[data-testid="artifact-widget-${owner.name}"]`)
    : null;
}

export function ArtifactForm({
  itemType,
  artifactId,
  initialValues,
  onSave,
  onDelete,
  onDirtyChange,
  mode = "edit",
  workflowArtifactType,
  requiresChangeReason = false,
  attributeOverrides,
  definitionFallback,
  onCancel,
  fieldTestIds,
  saveTestId = "artifact-form-save",
  headerActions,
}: ArtifactFormProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const { definition: resolvedDefinition, loading, error: loadError } =
    useArtifactDefinition(itemType);
  // GitHub #1192: field names the active preset's approval gate (Rule 5) will
  // demand — a superset of the definition's own `required` flags. Best-effort;
  // an empty set when the discovery request fails.
  const gateRequired = useGateRequiredFields(itemType);

  // Issue #889: apply the adapter's per-attribute overrides once, so rendering
  // and payload building see the same definition. Kept out of the hook itself
  // because the fetched definition is the server's contract and the override is
  // a purely client-side rendering/validation decision.
  //
  // GitHub #1192: the gate flag is overlaid in the same pass, so a field the
  // approval will demand (e.g. `acceptance_criteria`, definition
  // `required: false`) renders its required marker *before* a refused
  // "Freigeben". It is deliberately a separate `is_required` key — the
  // definition's `required` stays the create/edit contract.
  const definition = useMemo(() => {
    if (!resolvedDefinition) return resolvedDefinition;
    const overridden =
      attributeOverrides && Object.keys(attributeOverrides).length
        ? {
            ...resolvedDefinition,
            attributes: resolvedDefinition.attributes.map((attribute) =>
              attribute.name in attributeOverrides
                ? { ...attribute, ...attributeOverrides[attribute.name] }
                : attribute
            ),
          }
        : resolvedDefinition;
    if (!gateRequired.size) return overridden;
    return {
      ...overridden,
      attributes: overridden.attributes.map((attribute) =>
        gateRequired.has(attribute.name)
          ? { ...attribute, is_required: true }
          : attribute
      ),
    };
  }, [resolvedDefinition, attributeOverrides, gateRequired]);
  const [values, setValues] = useState<ArtifactFormValues>(initialValues);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [changeReason, setChangeReason] = useState<string>("");

  const { isDirty, markClean } = useFormDirty(values, initialValues);
  const isReadOnly = mode === "read";
  const isCreateMode = artifactId === null;
  const changeReasonNeeded = requiresChangeReason && artifactId !== null && !isReadOnly;
  const changeReasonMissing = changeReasonNeeded && !changeReason.trim();
  // Issue #977 (proof-journey finding): track "the save was refused for a
  // missing change reason" separately from the shared form banner, so the
  // message can also render at the field the user has to fill.
  const [changeReasonInvalid, setChangeReasonInvalid] = useState(false);
  const changeReasonRef = useRef<HTMLInputElement | null>(null);
  // Only one ArtifactForm is mounted per detail pane, so a static id is safe
  // here and keeps the input's `aria-describedby` resolvable.
  const changeReasonErrorId = "artifact-form-change-reason-error";

  // Issue #1087 (behaviour rule 2): a same-tick guard for BOTH save entry
  // points. `saving` is React state, so a Save click followed by a `Ctrl+S`
  // inside the same event-loop turn reads a stale `saving === false` and
  // submits twice — which for a PATCH carrying a version tag means the second
  // request is either a duplicate write or a spurious 412 conflict. The ref is
  // set synchronously at the top of `handleSave` and cleared in its `finally`.
  const savingRef = useRef(false);

  // Issue #1087 (behaviour rule 3): a rejected save must land the user on the
  // field the server complained about, not on a banner at the very top of a
  // form that may be several screens long. `focusRequest` is bumped by a new
  // object identity per failed save (a counter, not a timestamp — a
  // `Date.now()` state value is not reproducible under StrictMode), and the
  // effect below resolves it AFTER the render that opened the errored section
  // and rendered its control.
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null);
  const focusRequestRef = useRef(0);
  const formErrorRef = useRef<HTMLDivElement | null>(null);

  // `initialValues` is an object prop and every realistic call site builds it
  // inline from the fetched artifact, so both its IDENTITY and its key ORDER
  // (e.g. a parent assembling it via a conditional spread) change on every
  // parent render without the underlying artifact actually changing.
  // `artifactId` is the one thing that stays stable across such a re-render
  // and changes exactly when the user switches to editing a different
  // artifact (the rollout waves reuse one mounted form across a list
  // selection) — the same reset primitive RequirementForm/ArchitectureForm/
  // TestCaseForm/NeedForm already share for this exact class of bug
  // (`useEntityReset`, issue #700/#673).
  const initialRef = useRef(initialValues);
  initialRef.current = initialValues;

  useEntityReset(artifactId ?? "__none__", () => {
    setValues(initialRef.current);
    markClean(initialRef.current);
    // A rejected save's errors belong to the artifact that was open at the
    // time. The rollout waves reuse one mounted form across a list selection,
    // so leaving them would pin a red "title: is required" onto the next
    // artifact the user clicks.
    setFieldErrors({});
    setFormError(null);
    // A pending focus request belongs to the artifact that was open at the
    // time; keeping it would re-focus a control on the NEXT artifact the moment
    // the form re-renders.
    setFocusRequest(null);
    // A change reason typed for the PREVIOUS artifact must not silently ride
    // along on the next one's PATCH once the user switches selection (same
    // reused-mounted-form bug class NeedArtifactForm's R-2 fix already
    // addressed for its own bespoke change-reason field, Task 23).
    setChangeReason("");
  });

  // `changeReason` lives outside `values` (it is a save-time annotation, not
  // part of the artifact's own state), so `useFormDirty`'s own comparison
  // never sees it. Without folding it in here, a user who types only a
  // change reason (no other field edit) would pass every unsaved-changes
  // guard undetected — same gap `NeedArtifactForm`'s bespoke
  // `hasPendingChangeReason` closed for its own pre-shared implementation
  // (Task 23).
  const hasPendingChangeReason = changeReasonNeeded && changeReason.trim().length > 0;
  const combinedDirty = isDirty || hasPendingChangeReason;

  // Issue #800 in create dialogs: the host Dialog's focus trap settles on the
  // panel while this form is still waiting for the definition (its loading
  // branch renders one empty div, so there is nothing operable to focus).
  // When the fields arrive, the FIRST editable control — not the panel and
  // not a section-toggle disclosure button — must take focus, or the first
  // Tab press lands on a section header instead of the form's content.
  // Runs once per mount (`focusedOnCreate`): the create dialog remounts this
  // form per open, and a later definition refresh must not yank focus.
  const formRef = useRef<HTMLFormElement | null>(null);
  const focusedOnCreate = useRef(false);
  useEffect(() => {
    if (artifactId !== null || mode === "read" || loading || !definition) return;
    if (focusedOnCreate.current) return;
    focusedOnCreate.current = true;
    // Adapted selectors (fieldTestIds) rename the controls too — the focus
    // contract is "first operable control", so select by element type, not by
    // the default `artifact-field-` prefix.
    const first = formRef.current?.querySelector<HTMLElement>(
      "input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"
    );
    first?.focus();
  }, [artifactId, definition, loading, mode]);

  useEffect(() => {
    onDirtyChange?.(combinedDirty);
    // Task 24 finding: without this cleanup, unmounting the form while
    // `isDirty` was still `true` (e.g. Delete, which navigates away and
    // unmounts the form without ever reporting `isDirty(false)`) left the
    // parent's own "has unsaved edits" state stuck at `true` — the very next
    // tree-navigation click then wrongly showed an unsaved-changes dialog for
    // a form that no longer existed. Same failure class the deleted
    // `ArchitectureForm.tsx` (issue #672) already guarded against; this
    // shared renderer had no equivalent, only reachable once a rollout wave's
    // own `*Editors` wrapper actually wires up dirty-gated navigation (the
    // first to do so, Architecture, Task 24 — Risk/Issue's Editors wrappers
    // do not implement this guard at all, so they never exercised the gap).
    return () => {
      onDirtyChange?.(false);
    };
  }, [combinedDirty, onDirtyChange]);

  const visible = useMemo(
    () => (definition?.attributes ?? []).filter(
      (a) => a.visible && (artifactId !== null || a.editable === true)
    ),
    [definition, artifactId]
  );

  const specByName = useMemo(() => {
    const map = new Map<string, AttributeSpec>();
    for (const attribute of definition?.attributes ?? []) map.set(attribute.name, attribute);
    return map;
  }, [definition]);

  // Rule 2: a field a widget draws is not rendered on its own. Only a widget we
  // can ACTUALLY render claims its fields — an unknown `widget_key` or a
  // `fields`/`widget_key` mismatch (which the backend does not prevent, see
  // `resolveWidget`) would otherwise suppress controls with nothing drawing
  // them, turning a definition typo into silently uneditable data.
  const widgetOwned = useMemo(() => {
    const owned = new Set<string>();
    for (const attribute of visible) {
      if (attribute.type === "widget" && resolveWidget(attribute)) {
        // A widget's OWN name can legitimately appear in its own `fields`
        // list (nothing stops an admin from doing that server-side). If it
        // were added here too, the widget's own name would suppress itself
        // from standalone rendering while nothing else draws it either —
        // the field vanishes with no error, no warning.
        attribute.fields.forEach((name) => {
          if (name !== attribute.name) owned.add(name);
        });
      }
    }
    return owned;
  }, [visible]);

  // Task 8 (spec section 4.4's AND-condition): a section with visible=false
  // in the definition hides itself AND every attribute in it, regardless of
  // each attribute's own `visible` flag. A section name not yet represented
  // in `definition.sections` (pre-Task-7 data, or a name introduced by an
  // attribute edit that hasn't round-tripped through ensure_sections yet)
  // defaults to visible — same "additive, no data migration" default the
  // backend's own materialize_sections uses. WS4 #938: the full spec (not
  // just visible/layout) is kept, because the section-level `attribute_flow`
  // lives on it.
  const sectionMeta = useMemo(() => {
    const map = new Map<string, SectionSpec>();
    for (const section of definition?.sections ?? []) {
      map.set(section.name, section);
    }
    return map;
  }, [definition]);

  const spanClass = useCallback(
    (columns: number): string =>
      styles[`span${spanClassSuffix(columns)}`] ?? styles.span12,
    []
  );

  const groupedSections = useMemo(
    () => groupIntoSections(visible.filter((a) => !widgetOwned.has(a.name))),
    [visible, widgetOwned]
  );

  /**
   * WS4 #938 (spec section 7): section order comes from the stored
   * `section_flow` when present, otherwise from `definition.sections` order —
   * the same order the backend's `materialize_section_flow` uses — with a
   * fallback to attribute first-appearance for pre-Task-7 definitions whose
   * `sections` list is still empty. Invisible sections are filtered out
   * BEFORE the flow is applied, so a spacer next to a hidden section survives
   * while the hidden section itself never renders.
   */
  const sectionEntries = useMemo((): SectionEntry[] => {
    const byName = new Map(groupedSections.map((section) => [section.name, section]));
    const declared = [...(definition?.sections ?? [])].sort(
      (a, b) => a.order - b.order || a.name.localeCompare(b.name)
    );
    const order: string[] = [];
    for (const section of declared) {
      if (byName.has(section.name)) order.push(section.name);
    }
    for (const section of groupedSections) {
      if (!order.includes(section.name)) order.push(section.name);
    }
    const visibleOrder = order.filter(
      (name) => sectionMeta.get(name)?.visible !== false
    );
    return orderedSectionTokens(definition?.section_flow, visibleOrder).flatMap(
      (token): SectionEntry[] => {
        if (token.kind === "spacer") return [{ kind: "spacer", size: token.size }];
        const section = byName.get(token.name);
        if (!section) return [];
        return [
          {
            kind: "section",
            section,
            layout: sectionMeta.get(section.name)?.layout ?? "full",
          },
        ];
      }
    );
  }, [definition, groupedSections, sectionMeta]);

  // Use the same section/attribute flows as the renderer. Hidden sections and
  // empty flows cannot gate Create; widget-owned fields speak through their widget.
  const renderedEditableAttributes = useMemo(() => {
    const attributes = new Map<string, AttributeSpec>();
    for (const entry of sectionEntries) {
      if (entry.kind !== "section") continue;
      for (const field of resolveAttributeFlow(sectionMeta.get(entry.section.name), entry.section.attributes)) {
        if (field.kind !== "attribute") continue;
        const attribute = field.attribute;
        if (attribute.type === "widget") continue;
        if (attribute.editable === true) {
          attributes.set(attribute.name, attribute);
        }
      }
    }
    return [...attributes.values()];
  }, [sectionEntries, sectionMeta]);

  // A required select has no empty option: its displayed first option must
  // also be the value used by validation and submission, including custom fields.
  const formValues = useMemo(() => {
    if (!isCreateMode) return values;
    return renderedEditableAttributes.reduce((current, attribute) => {
      const value = readValue(current, attribute);
      if (attribute.type !== "enum" || !attribute.required || (value != null && value !== "")) return current;
      const initial = attribute.default ?? attribute.options[0]?.value;
      return initial == null ? current : writeValue(current, attribute, initial);
    }, values);
  }, [isCreateMode, renderedEditableAttributes, values]);

  const isSectionOpen = useCallback(
    (section: FormSection): boolean => {
      // In create mode sections never collapse: a required field hidden behind
      // a collapsed header would block the save invisibly, and the toggle
      // button would otherwise be the focus trap's first Tab stop ahead of
      // the form's actual content (create-dialog focus contract, #800 class).
      if (artifactId === null) return true;
      if (section.name in expanded) return expanded[section.name];
      // Rule 5: an error anywhere in the section forces it open so the message
      // is reachable without hunting. A widget's errors belong to its bound
      // fields, which live in the same section by construction.
      if (section.attributes.some((a) => fieldErrors[a.name]?.length)) return true;
      if (
        section.attributes.some((a) =>
          a.fields.some((name) => fieldErrors[name]?.length)
        )
      ) {
        return true;
      }
      return section.audience !== "expert";
    },
    [expanded, fieldErrors]
  );

  const update = useCallback((attribute: AttributeSpec, next: unknown): void => {
    setValues((current) => writeValue(current, attribute, next));
  }, []);

  // Create requiredness comes from the definition, not from edit-time gates.
  // The bootstrap rule is `required = not blank AND not has_default`, so a
  // required attribute that declares a default is satisfiable without input —
  // the backend applies the default for a field the create payload omits.
  const missingCreateValue = isCreateMode && renderedEditableAttributes.some((attribute) => {
    if (!attribute.required || attribute.editable !== true || attribute.type === "widget") return false;
    if (attribute.default != null) return false;
    const value = readValue(formValues, attribute);
    return value == null || (typeof value === "string" && !value.trim()) ||
      (Array.isArray(value) && value.length === 0);
  });

  const handleSave = useCallback(async (): Promise<void> => {
    // Issue #1087: `savingRef` rather than the `saving` state — see its
    // declaration. Same-tick double submit is exactly what a `Ctrl+S` shortcut
    // invites (hold the chord), and the state check cannot see it.
    if (savingRef.current || missingCreateValue) return;
    if (changeReasonMissing) {
      setFormError(t("artifactForm.changeReasonRequired"));
      setChangeReasonInvalid(true);
      // Issue #977 (proof-journey finding): the change-reason field sits below
      // every section, so refusing the save without moving the user there left
      // them staring at a form that silently did nothing. Land them on the
      // field that has to be filled — the same "error next to its cause"
      // contract the field-level `role="alert"` already follows.
      changeReasonRef.current?.focus();
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setFormError(null);
    setChangeReasonInvalid(false);
    setFieldErrors({});
    // Issue #886: the backend's payload contract forbids sending a value for a
    // non-editable attribute on an update (see `payload.ts`). Discriminating
    // per attribute here — the one place EVERY adapter's `onSave` routes
    // through — beats a static key list in each adapter, which cannot know
    // about a dynamically-declared `editable: false` field.
    const editableValues = stripNonEditableValues(
      formValues,
      definition?.attributes ?? [],
      artifactId === null ? "create" : "update"
    );
    const payload: ArtifactFormValues = changeReasonNeeded
      ? { ...editableValues, change_reason: changeReason.trim() }
      : editableValues;
    try {
      await onSave(payload);
      markClean(values);
      setChangeReason("");
    } catch (exc: unknown) {
      const message = extractErrorMessage(exc);
      const parsed = fieldErrorsFromException(exc, message);
      setFieldErrors(parsed);
      if (!Object.keys(parsed).length) setFormError(message);
      // Issue #1087 (behaviour rule 3): ask for the focus move. `null` means
      // "no field-level mapping" — the effect then lands on the banner, which
      // is the only place such a message is rendered.
      focusRequestRef.current += 1;
      setFocusRequest({
        nonce: focusRequestRef.current,
        field: firstErroredField(parsed, definition?.attributes ?? []),
      });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [
    artifactId,
    changeReason,
    changeReasonMissing,
    changeReasonNeeded,
    definition,
    markClean,
    onSave,
    missingCreateValue,
    formValues,
    t,
    values,
  ]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!onDelete) return;
    // F-1 (Task 25 fix round 1): the same change-reason guard `handleSave`
    // applies before a PATCH also applies before a DELETE — the Extended
    // preset's `is_change_reason_required` check gates both server-side
    // (`RequirementService.delete_requirement`), so a delete with a missing
    // reason must fail the same way a save does, not 400 after the confirm
    // dialog already closed.
    if (changeReasonMissing) {
      setConfirmDelete(false);
      setFormError(t("artifactForm.changeReasonRequired"));
      return;
    }
    try {
      await onDelete(changeReasonNeeded ? changeReason.trim() : undefined);
      setConfirmDelete(false);
    } catch (exc: unknown) {
      setConfirmDelete(false);
      setFormError(extractErrorMessage(exc));
    }
  }, [changeReason, changeReasonMissing, changeReasonNeeded, onDelete, t]);

  /**
   * Issue #1087: `Ctrl`/`Cmd`+`S` saves, exactly like the Save button.
   *
   * Enabled for every editable `ArtifactForm`, which is every artifact type's
   * detail editor AND every create dialog (Requirement, ArchitectureElement,
   * Adr, Risk, Issue, TestCase, StakeholderNeed) — one renderer, one saving
   * mechanism, one place to get it right. Disabled when the form is read-only
   * or its definition never loaded, because there is then nothing to save and
   * swallowing the key would only deny the browser's own action.
   */
  useSaveShortcut({
    onSave: handleSave,
    enabled: !isReadOnly && !loading && !loadError && definition !== null,
    isSaving: saving,
    // #1100 follow-up: the form owns the shortcut, so a covering modal (confirm
    // dialog, legend, export panel) suspends it instead of saving the form
    // behind the overlay.
    containerRef: formRef,
    // FR-U5-02 / a11y-U5-02: a create form whose required fields are empty
    // must not have its submit path called by the chord — mirror the Save
    // button's own `disabled={saving || missingCreateValue}` so an empty
    // required field cannot reach a submit that only early-returns silently.
    // Always `true` in edit mode (`missingCreateValue` is create-mode only),
    // so the detail editor is unaffected.
    canSave: !missingCreateValue,
  });

  /**
   * Issue #1087 (behaviour rule 3) — resolve the focus request issued by the
   * last failed save.
   *
   * Runs after the render that applied `fieldErrors`, which is what matters:
   * `isSectionOpen` forces a section open when it holds an error, so the
   * offending control only exists in the DOM by then. Without that ordering the
   * lookup would find nothing and silently fall back to the banner.
   */
  useEffect(() => {
    if (focusRequest === null) return;
    const target = focusRequest.field
      ? findFieldControl(
          formRef.current,
          focusRequest.field,
          fieldTestIds,
          definition?.attributes
        )
      : null;
    if (target) {
      // A widget draws its bound fields inside one composite, so the focus
      // target may be a container that is not natively focusable. `tabindex`
      // makes the programmatic focus actually land (it stays out of the tab
      // order, which is what a composite wants).
      if (!FOCUSABLE_SELECTOR.test(target.tagName) && target.tabIndex < 0) {
        target.tabIndex = -1;
      }      target.focus();
      return;
    }
    // Form-level failure (no field mapping, or a field that is not rendered):
    // the banner is the only place the reason exists, so it takes the focus.
    formErrorRef.current?.focus();
  }, [focusRequest, fieldTestIds, definition]);

  if (loading) {
    return <div data-testid="artifact-form-loading" aria-busy="true" />;
  }
  // GitHub #677: this banner is mounted dynamically (the definition loads
  // asynchronously), so it is an assertive live region — `role="alert"` is the
  // semantics, the explicit `aria-live` states the intent for readers and for
  // the a11y regression tests.
  if (loadError || !definition) {
    return (
      <>
        <div
          className={styles.errors}
          role="alert"
          aria-live="assertive"
          data-testid="artifact-form-load-error"
        >
          <AlertCircle aria-hidden="true" size={16} />
          {loadError ?? t("artifactForm.definitionUnavailable")}
        </div>
        {definitionFallback}
      </>
    );
  }

  if (isCreateMode && definition.attributes.length === 0) {
    // A definition that loads but carries no attributes leaves no operable
    // control for the create dialog's focus trap (#800) — not even a title
    // input. Treat it like a load failure so the adapter's minimal fallback
    // (title/description/category) renders instead of an empty form.
    return (
      <>
        <div
          className={styles.errors}
          role="alert"
          aria-live="assertive"
          data-testid="artifact-form-load-error"
        >
          <AlertCircle aria-hidden="true" size={16} />
          {t("artifactForm.definitionUnavailable")}
        </div>
        {definitionFallback}
      </>
    );
  }

  return (
    <form
      ref={formRef}
      className={styles.form}
      data-testid="artifact-form"
      onSubmit={(event) => {
        event.preventDefault();
        void handleSave();
      }}
    >
      {formError ? (
        // GitHub #677: a failed save (server error, or the client-side
        // change-reason gate) must reach screen-reader users. The banner is
        // inserted dynamically at the top of the form, so it is an assertive
        // live region — otherwise the click on Save produces no audible
        // feedback at all.
        <div
          ref={formErrorRef}
          className={styles.errors}
          role="alert"
          aria-live="assertive"
          // Issue #1087: a form-level rejection (no field mapping) has its
          // reason only here, so the focus effect below lands on this element.
          // `tabindex="-1"` keeps it out of the tab order — it is a target for
          // a programmatic focus, not a stop the user has to walk through.
          tabIndex={-1}
          data-testid="artifact-form-error"
        >
          {formError}
        </div>
      ) : null}

      {headerActions ? (
        <div className={styles.headerActions} data-testid="artifact-form-header-actions">
          {headerActions}
        </div>
      ) : null}

      <div className={styles.sectionsGrid} data-testid="artifact-sections-grid">
      {sectionEntries.map((entry, entryIndex) => {
        if (entry.kind === "spacer") {
          return (
            <div
              key={`section-spacer-${entryIndex}`}
              className={`${styles.spacerToken} ${spanClass(spacerColumns(entry.size))}`}
              data-columns={spacerColumns(entry.size)}
              aria-hidden="true"
              data-testid={`artifact-section-spacer-${entryIndex}`}
            />
          );
        }
        const { section, layout } = entry;
        const open = isSectionOpen(section);
        const fieldEntries = resolveAttributeFlow(
          sectionMeta.get(section.name),
          section.attributes
        );
        return (
          <section
            key={section.name}
            data-testid={`artifact-section-${section.name}`}
            data-layout={layout}
            data-columns={sectionLayoutColumns(layout)}
            className={`${styles.section} ${spanClass(sectionLayoutColumns(layout))}`}
          >
            {isCreateMode ? (
              // Create mode: sections cannot collapse (a required field hidden
              // behind a collapsed header would block the save invisibly), so
              // the header is a plain heading — a dead disclosure button would
              // otherwise be the focus trap's first Tab stop ahead of the
              // form's content (create-dialog focus contract, #800 class).
              <span
                className={styles.sectionHeader}
                data-testid={`artifact-section-toggle-${section.name}`}
                aria-current="false"
              >
                {t(`sections.${section.name}`, { defaultValue: section.name })}
              </span>
            ) : (
            <button
              type="button"
              className={styles.sectionHeader}
              data-testid={`artifact-section-toggle-${section.name}`}
              aria-expanded={open}
              aria-label={t(
                open ? "artifactForm.collapseSection" : "artifactForm.expandSection",
                { section: t(`sections.${section.name}`, { defaultValue: section.name }) }
              )}
              onClick={() =>
                setExpanded((current) => ({ ...current, [section.name]: !open }))
              }
            >
              <span>{t(`sections.${section.name}`, { defaultValue: section.name })}</span>
              {open ? (
                <ChevronDown aria-hidden="true" size={16} />
              ) : (
                <ChevronRight aria-hidden="true" size={16} />
              )}
            </button>
            )}

            {open ? (
              <div
                className={styles.sectionBody}
                data-testid={`artifact-section-body-${section.name}`}
              >
                {fieldEntries.map((fieldEntry, fieldIndex) => {
                  if (fieldEntry.kind === "spacer") {
                    return (
                      <div
                        key={`field-spacer-${fieldIndex}`}
                        className={`${styles.spacerToken} ${spanClass(fieldEntry.columns)}`}
                        data-columns={fieldEntry.columns}
                        aria-hidden="true"
                        data-testid={`artifact-field-spacer-${section.name}-${fieldIndex}`}
                      />
                    );
                  }
                  const rendered = renderAttribute({
                    attribute: fieldEntry.attribute,
                    values: formValues,
                    fieldErrors,
                    specByName,
                    disabled:
                      isReadOnly ||
                      saving ||
                      // A workflow-owned attribute is editable through the
                      // WorkflowStatusEditor's own transition menu, not through
                      // the generic editable-control path — `editable ===
                      // "workflow"` must therefore NOT count as "not editable"
                      // here, or the status editor renders without its trigger
                      // (E2E: workflow-transition-trigger missing).
                      (fieldEntry.attribute.editable !== true &&
                        fieldEntry.attribute.editable !== "workflow"),
                    // Distinct from `disabled`: a save in flight must not switch
                    // a configured field from its editable control to the
                    // read-only display (that would flash the value format).
                    displayOnly: isReadOnly || fieldEntry.attribute.editable !== true,
                    language: i18n.language,
                    systemUnsetLabel: t("artifactForm.systemValueUnavailable"),
                    artifactId,
                    workflowArtifactType,
                    unsupportedLabel: t("artifactForm.unsupportedWidget", {
                      widget: fieldEntry.attribute.widget_key ?? "",
                    }),
                    update,
                    // The adapter's create-dialog automation selectors (#583):
                    // E2E drives the definition-driven path through the same
                    // legacy testids the fallback form has always exposed.
                    testId: fieldTestIds?.[fieldEntry.attribute.name] ?? `artifact-field-${fieldEntry.attribute.name}`,
                  });
                  if (!rendered) return null;
                  return (
                    <div
                      key={fieldEntry.attribute.name}
                      className={`${styles.fieldCell} ${spanClass(fieldEntry.columns)}`}
                      data-columns={fieldEntry.columns}
                      data-testid={`artifact-field-cell-${fieldEntry.attribute.name}`}
                    >
                      {rendered}
                    </div>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
      </div>

      {changeReasonNeeded ? (
        <label className={styles.field}>
          <span className={`${styles.label} ${styles.required}`}>
            {t("artifactForm.changeReason")}
          </span>
          <input
            className={`${styles.control} ${changeReasonInvalid ? styles.controlInvalid : ""}`}
            data-testid="artifact-form-change-reason"
            type="text"
            value={changeReason}
            ref={changeReasonRef}
            aria-required="true"
            aria-invalid={changeReasonInvalid || undefined}
            aria-describedby={changeReasonInvalid ? changeReasonErrorId : undefined}
            onChange={(event) => {
              setChangeReason(event.target.value);
              if (changeReasonInvalid) {
                setChangeReasonInvalid(false);
                setFormError(null);
              }
            }}
          />
          {changeReasonInvalid ? (
            // Issue #977 (proof-journey finding): the save was refused, but the
            // reason appeared only in the banner at the very top of the form
            // while this field sits below every section. A user who clicked
            // Save saw nothing happen where they were looking. The message now
            // also sits at the field, and focus moves there on refusal.
            <span className={styles.errors} id={changeReasonErrorId} role="alert">
              {t("artifactForm.changeReasonRequired")}
            </span>
          ) : null}
        </label>
      ) : null}

      {!isReadOnly ? (
        <div className={styles.actions}>
          {onDelete ? (
            <button
              type="button"
              data-testid="artifact-form-delete"
              disabled={saving}
              onClick={() => setConfirmDelete(true)}
            >
              {t("actions.delete")}
            </button>
          ) : null}
          {onCancel ? (
            <button type="button" className="btn-secondary" data-testid="artifact-form-cancel" disabled={saving} onClick={onCancel}>
              {t("actions.cancel")}
            </button>
          ) : null}
          <button
            type="submit"
            className="btn-primary"
            data-testid={saveTestId}
            disabled={saving || missingCreateValue}
            // Issue #1087: the shortcut has to be discoverable on the control
            // that also performs it. `aria-keyshortcuts` is the machine-
            // readable form (WAI-ARIA 1.2) and the only one assistive tech can
            // surface; the title carries the same fact for pointer users.
            // There is no app-wide shortcuts/help surface to list it in (the
            // only shortcut help in the repo is the workflow canvas's own),
            // so the button annotates itself rather than a new page appearing.
            aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
            title={t("artifactForm.saveShortcutHint", "Speichern (Strg/Cmd+S)")}
          >
            {saving ? t("actions.saving") : t(artifactId === null ? "actions.create" : "actions.save")}
          </button>
        </div>
      ) : null}

      {confirmDelete ? (
        <ConfirmDialog
          title={t("artifactForm.deleteTitle")}
          message={t("artifactForm.deleteConfirm")}
          confirmLabel={t("actions.delete")}
          cancelLabel={t("actions.cancel")}
          testId="artifact-form-delete-dialog"
          confirmTestId="artifact-form-delete-confirm"
          cancelTestId="artifact-form-delete-cancel"
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      ) : null}
    </form>
  );
}

interface RenderArgs {
  attribute: AttributeSpec;
  values: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  specByName: Map<string, AttributeSpec>;
  disabled: boolean;
  /** `data-testid` for the control — defaults to `artifact-field-<name>`. */
  testId: string;
  /**
   * `true` when the attribute is shown outside an editable context (read mode
   * or a non-editable policy) — the trigger for the generic display path.
   * Separate from `disabled` because `saving` also disables controls without
   * changing how a configured value should be rendered.
   */
  displayOnly: boolean;
  /** Active UI language — needed by the `system` static-text branch. */
  language: string;
  /** Rendered for an empty `system` attribute value. */
  systemUnsetLabel: string;
  artifactId: string | null;
  workflowArtifactType?: WorkflowArtifactType;
  unsupportedLabel: string;
  update: (attribute: AttributeSpec, next: unknown) => void;
}

function renderAttribute({
  attribute,
  values,
  fieldErrors,
  specByName,
  disabled,
  testId,
  displayOnly,
  language,
  systemUnsetLabel,
  artifactId,
  workflowArtifactType,
  unsupportedLabel,
  update,
}: RenderArgs): JSX.Element | null {
  const errors = fieldErrors[attribute.name];

  // Rule 3b (Attribut v3 WS2, #936): a `system` attribute is server-owned —
  // the Artifact's own `id` is the carrier. It is NEVER an editable control:
  // it renders through the generic `<RevealValue>` display engine, so the WS3
  // (#937) display properties (`reveal="click"`, `copyable`, `mask="short"`)
  // take effect here too.
  //
  // Checked BEFORE the `workflow` comparison on purpose: comparing against the
  // first string literal narrows `editable` to its remaining string member, so
  // a `=== "system"` test placed after it would (correctly, but unhelpfully)
  // be reported as having no overlap with the narrowed `boolean | "system"`.
  if (attribute.editable === "system") {
    const current = readValue(values, attribute);
    const hasValue = current != null && current !== "";
    const display = resolveDisplayProps(attribute);
    return (
      <div key={attribute.name} className={styles.field}>
        <span className={styles.label} id={`${testId}-label`}>
          {attributeLabel(attribute, language)}
        </span>
        <RevealValue
          value={hasValue ? String(current) : null}
          fallback={systemUnsetLabel}
          copyValue={hasValue ? String(current) : null}
          displayFormat={display.displayFormat}
          reveal={display.reveal}
          mask={display.mask}
          copyable={display.copyable && hasValue}
          label={attributeLabel(attribute, language)}
          testId={testId}
        />
      </div>
    );
  }

  // Rule 3: a workflow-owned attribute is never an editable control. In create
  // mode there is no artifact to transition yet, so it is not rendered at all —
  // the backend assigns the initial state.
  if (attribute.editable === "workflow") {
    if (!workflowArtifactType || !artifactId) return null;
    const current = readValue(values, attribute);
    return (
      <WorkflowStatusEditor
        key={attribute.name}
        artifactType={workflowArtifactType}
        artifactId={artifactId}
        currentStatus={typeof current === "string" ? current : undefined}
        disabled={disabled}
      />
    );
  }

  if (attribute.type === "widget") {
    const Widget = resolveWidget(attribute);
    if (!Widget) {
      // Unknown `widget_key`, or one whose `fields` it cannot render. Both are
      // reachable through the unenforced `/attribute-defaults/` PUT, so this
      // must be a visible message rather than `null`: the fields are still
      // rendered individually (see `widgetOwned`), and an admin gets told which
      // widget is misconfigured instead of wondering why a save 400s.
      return (
        <div
          key={attribute.name}
          className={styles.errors}
          role="alert"
          data-testid={`artifact-widget-unsupported-${attribute.name}`}
        >
          {unsupportedLabel}
        </div>
      );
    }
    const boundValues: Record<string, unknown> = {};
    const boundErrors: Record<string, string[]> = {};
    for (const name of attribute.fields) {
      const bound = specByName.get(name);
      boundValues[name] = bound ? readValue(values, bound) : values[name];
      if (fieldErrors[name]) boundErrors[name] = fieldErrors[name];
    }
    return (
      <Widget
        key={attribute.name}
        attribute={attribute}
        values={boundValues}
        onChange={(fieldName, next) =>
          update(
            specByName.get(fieldName) ?? { ...attribute, name: fieldName, kind: "core" },
            next
          )
        }
        disabled={disabled}
        errors={boundErrors}
        testId={`artifact-widget-${attribute.name}`}
      />
    );
  }

  // Rule 4 (Attribut v3 WS3, #937): an attribute with at least one NON-default
  // display property (copyable/reveal/mask/display_format) is rendered through
  // the generic display engine whenever the field is not editable. An
  // attribute without special properties falls straight through to its
  // ordinary control below and keeps rendering exactly as before — the
  // "kein Big-Bang, Defaults verhalten sich wie vorher" requirement.
  const display = resolveDisplayProps(attribute);
  if (displayOnly && hasConfiguredDisplay(display)) {
    return (
      <DisplayField
        key={attribute.name}
        attribute={attribute}
        value={readValue(values, attribute)}
        errors={errors}
        testId={testId}
      />
    );
  }

  const shared = {
    attribute,
    disabled,
    errors,
    testId,
  } as const;
  const value = readValue(values, attribute);
  const onChange = (next: unknown): void => update(attribute, next);

  switch (attribute.type) {
    case "textarea":
      return <TextArea key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "number":
      return <NumberField key={attribute.name} {...shared} value={value as number | null} onChange={onChange} />;
    case "boolean":
      return <BooleanToggle key={attribute.name} {...shared} value={value as boolean | null} onChange={onChange} />;
    case "enum":
      return <EnumSelect key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "multi-enum":
      return <MultiEnum key={attribute.name} {...shared} value={value as string[] | null} onChange={onChange} />;
    case "date":
      return <DateField key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "reference":
      return <ReferencePicker key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "user":
      return <UserPicker key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "actor":
      // Attribut v3 WS2 (#936): `multiple` selects between the single entry
      // form (`{kind, id|name}`) and the `{multiple: true, items: [...]}` form;
      // `allow_external` gates the "create as external person" affordance.
      // Both are read from the attribute, never guessed here.
      return (
        <ActorPicker
          key={attribute.name}
          {...shared}
          value={value as ActorFieldValue}
          onChange={onChange}
        />
      );
    default:
      return <TextField key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
  }
}
