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
}: ArtifactFormProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const { definition: resolvedDefinition, loading, error: loadError } =
    useArtifactDefinition(itemType);

  // Issue #889: apply the adapter's per-attribute overrides once, so rendering
  // and payload building see the same definition. Kept out of the hook itself
  // because the fetched definition is the server's contract and the override is
  // a purely client-side rendering/validation decision.
  const definition = useMemo(() => {
    if (!resolvedDefinition || !attributeOverrides) return resolvedDefinition;
    const names = Object.keys(attributeOverrides);
    if (!names.length) return resolvedDefinition;
    return {
      ...resolvedDefinition,
      attributes: resolvedDefinition.attributes.map((attribute) =>
        attribute.name in attributeOverrides
          ? { ...attribute, ...attributeOverrides[attribute.name] }
          : attribute
      ),
    };
  }, [resolvedDefinition, attributeOverrides]);
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
    if (saving || missingCreateValue) return;
    if (changeReasonMissing) {
      setFormError(t("artifactForm.changeReasonRequired"));
      return;
    }
    setSaving(true);
    setFormError(null);
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
    } finally {
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
    saving,
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
          className={styles.errors}
          role="alert"
          aria-live="assertive"
          data-testid="artifact-form-error"
        >
          {formError}
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
            className={styles.control}
            data-testid="artifact-form-change-reason"
            type="text"
            value={changeReason}
            aria-required="true"
            onChange={(event) => setChangeReason(event.target.value)}
          />
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
          <button type="submit" className="btn-primary" data-testid={saveTestId} disabled={saving || missingCreateValue}>
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
