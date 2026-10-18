/**
 * Form state, derived memos, handlers and effects of the definition-driven
 * artifact form (spec section 6).
 *
 * Extracted verbatim from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 /
 * F-01) so the component becomes a thin orchestrator. Behaviour is unchanged:
 * every `useMemo`/`useCallback`/`useEffect` below keeps its dependencies and
 * its position relative to the others. In particular `widgetOwned` and
 * `sectionMeta` stay memoized derivations — verified genuine deps of
 * `groupedSections`/`sectionEntries` (frontend audit §2/§3.3, NOT premature).
 *
 * The hook takes the props the form needs for state; the component keeps the
 * props that are pure rendering concerns (`headerActions`, `onCancel`,
 * `definitionFallback`) and the public props API of the 8 render sites is
 * untouched.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  AttributeItemType,
  AttributeSpec,
  ResolvedAttributeDefinition,
  SectionSpec,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import type {
  WorkflowAllowedTransition,
  WorkflowArtifactType,
} from "../../../api/workflow-transitions";
import { useAllowedTransitions } from "../../../hooks/use-allowed-transitions";
import { useEntityReset } from "../../../hooks/use-entity-reset";
import { findOutdatedTransition } from "../../../utils/outdatedStates";
import { useFormDirty } from "../../../hooks/use-form-dirty";
import { useSaveShortcut } from "../../../hooks/useSaveShortcut";
import { useCreateFormFields } from "../../../hooks/useCreateFormFields";
import { fieldErrorsFromException } from "./field-errors";
import {
  FOCUSABLE_SELECTOR,
  findFieldControl,
  firstErroredField,
  groupIntoSections,
  readValue,
  writeValue,
} from "./form-helpers";
import { orderedSectionTokens, resolveAttributeFlow } from "./layout-flow";
import { stripNonEditableValues } from "./payload";
import { useArtifactDefinition } from "./useArtifactDefinition";
import { useGateRequiredFields } from "./useGateRequiredFields";
import { resolveWidget } from "./widget-registry";
import type {
  ArtifactFormValues,
  FocusRequest,
  FormSection,
  SectionEntry,
} from "./artifact-form-types";

export interface UseArtifactFormStateArgs {
  itemType: AttributeItemType;
  artifactId: string | null;
  initialValues: ArtifactFormValues;
  onSave: (values: ArtifactFormValues) => Promise<ArtifactFormValues | void>;
  onDeprecate?: (targetState: string, changeReason?: string) => Promise<void>;
  onDirtyChange?: (isDirty: boolean) => void;
  mode?: "edit" | "read";
  workflowArtifactType?: WorkflowArtifactType;
  requiresChangeReason?: boolean;
  attributeOverrides?: Record<string, Partial<AttributeSpec>>;
  fieldTestIds?: Record<string, string>;
}

export interface ArtifactFormState {
  /** Definition loading / load-error branch inputs. */
  loading: boolean;
  loadError: string | null;
  definition: ResolvedAttributeDefinition | null;
  /** Current artifact values — `data-version` on the `<form>`. */
  values: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  formError: string | null;
  saving: boolean;
  isReadOnly: boolean;
  isCreateMode: boolean;
  missingCreateValue: boolean;
  /** Refs the shell attaches: the `<form>`, the error banner, the change-reason input. */
  formRef: React.RefObject<HTMLFormElement | null>;
  formErrorRef: React.RefObject<HTMLDivElement | null>;
  changeReasonRef: React.RefObject<HTMLInputElement | null>;
  changeReasonErrorId: string;
  changeReasonNeeded: boolean;
  changeReason: string;
  changeReasonInvalid: boolean;
  onChangeChangeReason: (value: string) => void;
  handleSave: () => Promise<void>;
  // Section renderer inputs.
  sectionEntries: SectionEntry[];
  sectionMeta: Map<string, SectionSpec>;
  specByName: Map<string, AttributeSpec>;
  formValues: ArtifactFormValues;
  isSectionOpen: (section: FormSection) => boolean;
  onToggleSection: (section: FormSection, open: boolean) => void;
  update: (attribute: AttributeSpec, next: unknown) => void;
  // Deprecate flow inputs.
  deprecateTransition: WorkflowAllowedTransition | undefined;
  deprecateReasonNeeded: boolean;
  deprecateReasonMissing: boolean;
  deprecateReason: string;
  confirmDeprecate: boolean;
  onRequestDeprecate: () => void;
  onCancelDeprecate: () => void;
  onChangeDeprecateReason: (value: string) => void;
  handleDeprecate: () => Promise<void>;
}

export function useArtifactFormState({
  itemType,
  artifactId,
  initialValues,
  onSave,
  onDeprecate,
  onDirtyChange,
  mode = "edit",
  workflowArtifactType,
  requiresChangeReason = false,
  attributeOverrides,
  fieldTestIds,
}: UseArtifactFormStateArgs): ArtifactFormState {
  const { t } = useTranslation();
  const { definition: resolvedDefinition, loading, error: loadError } =
    useArtifactDefinition(itemType);
  // GitHub #1192: field names the active preset's approval gate (Rule 5) will
  // demand — a superset of the definition's own `required` flags. Best-effort;
  // an empty set when the discovery request fails.
  const gateRequired = useGateRequiredFields(itemType);

  // Issue #1263: the create dialog's configurable form definition. Only the
  // CREATE path consults it (the edit dialog is the artifact's own state, not a
  // "which fields do we ask for" question). Best-effort: `entries === null`
  // leaves the attribute definition in charge — the pre-#1263 behaviour.
  const createForm = useCreateFormFields(itemType, artifactId === null);

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
    const gated = !gateRequired.size
      ? overridden
      : {
          ...overridden,
          attributes: overridden.attributes.map((attribute) =>
            gateRequired.has(attribute.name)
              ? { ...attribute, is_required: true }
              : attribute
          ),
        };
    // Issue #1263: overlay the create-form definition (visible / order /
    // required / default) on the attribute definition. One render path: the
    // dialog reads ONLY the form definition, never a second hardcoded list. The
    // overlay is per-attribute, so it composes with the section/flow layout the
    // renderer already applies; a field the entry list does not name (a
    // non-editable one) keeps the definition's own flags.
    const entries = createForm.entries;
    if (!entries || entries.length === 0) return gated;
    const entryByKey = new Map(entries.map((entry) => [entry.field_key, entry]));
    return {
      ...gated,
      attributes: gated.attributes.map((attribute) => {
        const entry = entryByKey.get(attribute.name);
        if (!entry) return attribute;
        return {
          ...attribute,
          visible: entry.visible,
          required: entry.required,
          default: entry.default,
          order: entry.order,
        };
      }),
    };
  }, [resolvedDefinition, attributeOverrides, gateRequired, createForm.entries]);

  const [values, setValues] = useState<ArtifactFormValues>(initialValues);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDeprecate, setConfirmDeprecate] = useState(false);
  const [deprecateReason, setDeprecateReason] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [changeReason, setChangeReason] = useState<string>("");

  const { isDirty, markClean } = useFormDirty(values, initialValues);
  const isReadOnly = mode === "read";
  const isCreateMode = artifactId === null;
  const changeReasonNeeded = requiresChangeReason && artifactId !== null && !isReadOnly;
  const changeReasonMissing = changeReasonNeeded && !changeReason.trim();
  const allowedTransitions = useAllowedTransitions(workflowArtifactType, artifactId);
  const deprecateTransition = isReadOnly
    ? undefined
    : findOutdatedTransition(allowedTransitions);
  const deprecateReasonNeeded = deprecateTransition?.requires_change_reason === true;
  const deprecateReasonMissing = deprecateReasonNeeded && !deprecateReason.trim();
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
    setConfirmDeprecate(false);
    setDeprecateReason("");
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
    [artifactId, expanded, fieldErrors]
  );

  const onToggleSection = useCallback(
    (section: FormSection, open: boolean): void => {
      setExpanded((current) => ({ ...current, [section.name]: !open }));
    },
    []
  );

  const update = useCallback((attribute: AttributeSpec, next: unknown): void => {
    setValues((current) => writeValue(current, attribute, next));
  }, []);

  const onChangeChangeReason = useCallback((value: string): void => {
    setChangeReason(value);
    // Preserve the original guard exactly: only a previously-refused change
    // reason clears the shared banner — typing here must NOT wipe an unrelated
    // server error that happens to be showing at the same time.
    if (changeReasonInvalid) {
      setChangeReasonInvalid(false);
      setFormError(null);
    }
  }, [changeReasonInvalid]);

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
      const response = await onSave(payload);
      const reconciled = response ?? values;
      setValues(reconciled);
      markClean(reconciled);
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

  const handleDeprecate = useCallback(async (): Promise<void> => {
    if (!onDeprecate || !deprecateTransition) return;
    if (deprecateReasonMissing) return;
    try {
      await onDeprecate(
        deprecateTransition.target_state,
        deprecateReasonNeeded ? deprecateReason.trim() : ""
      );
      setConfirmDeprecate(false);
      setDeprecateReason("");
    } catch (exc: unknown) {
      setConfirmDeprecate(false);
      setFormError(extractErrorMessage(exc));
    }
  }, [
    deprecateReason,
    deprecateReasonMissing,
    deprecateReasonNeeded,
    deprecateTransition,
    onDeprecate,
  ]);

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

  return {
    loading,
    loadError,
    definition,
    values,
    fieldErrors,
    formError,
    saving,
    isReadOnly,
    isCreateMode,
    missingCreateValue,
    formRef,
    formErrorRef,
    changeReasonRef,
    changeReasonErrorId,
    changeReasonNeeded,
    changeReason,
    changeReasonInvalid,
    onChangeChangeReason,
    handleSave,
    sectionEntries,
    sectionMeta,
    specByName,
    formValues,
    isSectionOpen,
    onToggleSection,
    update,
    deprecateTransition,
    deprecateReasonNeeded,
    deprecateReasonMissing,
    deprecateReason,
    confirmDeprecate,
    onRequestDeprecate: () => setConfirmDeprecate(true),
    onCancelDeprecate: () => {
      setConfirmDeprecate(false);
      setDeprecateReason("");
    },
    onChangeDeprecateReason: (value: string) => setDeprecateReason(value),
    handleDeprecate,
  };
}
