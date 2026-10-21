/**
 * EditorPageShell — the shared page-level glue for the hand-written create
 * dialogs of the artifact editors (REUSE finding F-15, frontend audit
 * 2026-10-15, plan Phase 3 §3.7).
 *
 * HONEST SCOPE — derived from the real call sites, not from the plan's wording
 * -------------------------------------------------------------------------
 * `AdrEditors`, `RiskEditors`, `IssueEditors` and `TestCaseEditors` each carry
 * the *same* create-dialog scaffold, verified line by line before extraction:
 *
 *   - the dialog wrapper: `<Dialog title onClose testId initialFocusRef footer>`,
 *   - the footer: a Cancel (`btn-secondary`) + a Create (`btn-primary`) button
 *     with `aria-keyshortcuts` / the `artifactForm.saveShortcutHint` title,
 *   - the `<form id ref onSubmit>` the submit button targets via `form=`,
 *   - a `role="alert"` error paragraph as the form's last child,
 *   - the page-level glue: the form ref, the `Ctrl`/`Cmd`+`S` wiring, and a
 *     synchronous same-tick submit guard (`submittingRef`) that the button and
 *     the chord both funnel through.
 *
 * Only those genuinely-shared pieces live here. The plan's §3.7 wording also
 * named a "Dirty-Wrapper", "Workflow-Status" and "ConfirmDialog" as part of the
 * shell. Those are NOT page-level create-dialog glue and are deliberately NOT
 * included:
 *   - dirty handling is per-page `customFields`/`scenario` sibling logic (the
 *     `useFormDirty` + `CustomFieldsEditor` pair), which differs per route and
 *     belongs to the page, not to the dialog chrome;
 *   - the workflow status editor lives inside `ArtifactForm` on the detail
 *     forms, never in a create dialog;
 *   - `ConfirmDialog` is rendered by only some pages, and for unsaved-changes /
 *     delete flows — not by the create dialog at all.
 * Folding any of those in would have meant inventing behaviour no call site
 * has, not extracting behaviour all of them share.
 *
 * Prop-surface deviations from the plan's proposed list
 * -----------------------------------------------------
 *   - `errorClassName` was ADDED. The four pages render the error as
 *     `<p role="alert" className={styles.createError}>` from their own CSS
 *     modules; to keep the rendered DOM byte-identical the class has to be
 *     passed in rather than hardcoded here.
 *   - `triggerRef` was DROPPED. Only `ArchitectureEditors` passes one, and that
 *     dialog is not a shell consumer (see below), so nothing uses it.
 *   - `errorTestId` was DROPPED. None of the four consumers set a test id on the
 *     error paragraph; adding an unused prop would be dead API.
 *
 * Who consumes it, and who deliberately does not
 * ----------------------------------------------
 *   - Consumers: `AdrEditors`, `RiskEditors`, `IssueEditors`, `TestCaseEditors`
 *     — their create dialogs are structurally identical (tested as one class by
 *     `AdrEditors.save-shortcut.test.tsx`).
 *   - `ArchitectureEditors` is NOT a consumer: its inline create form renders
 *     its Cancel/Create pair *inside* the `<form>` (in a `createActions` row,
 *     not via `Dialog`'s `footer` slot), has no `role="alert"` error inside the
 *     form (rejections surface in the list-level `arch-action-error` banner)
 *     and uses a `triggerRef`. Reproducing that shape through this shell would
 *     change the rendered DOM, which is out of scope for a behaviour-preserving
 *     extraction.
 *   - `NeedsEditors` is NOT a consumer: it owns the create state and shortcut,
 *     but its dialog MARKUP (and its `<form>`) is rendered by `NeedList`, so the
 *     shell's chrome cannot be applied from the route shell.
 *   - `RequirementEditors` is NOT a consumer: its create dialog renders the
 *     shared `<ArtifactForm>` (`artifactId={null}`), which already owns the save
 *     shortcut internally — there is nothing page-level to extract.
 *
 * The save shortcut itself is NOT reimplemented here — this file composes the
 * existing `hooks/useSaveShortcut` (the same hook `ArtifactForm` and the pages
 * used before), so the chord, its topmost-form arbitration and its
 * interaction-context `containerRef` gate keep exactly one implementation.
 */

import { useRef, type ReactNode, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { SAVE_SHORTCUT_ARIA, useSaveShortcut } from "../../hooks/useSaveShortcut";
import { Dialog } from "./Dialog";

export interface EditorPageShellProps {
  /** Whether the create dialog is mounted. `false` renders nothing. */
  open: boolean;
  /** Accessible dialog title, repeating the label of the button that opened it. */
  title: string;
  /** `data-testid` of the dialog panel (the overlay gets `${testId}-overlay`). */
  testId: string;
  /** `id` of the `<form>`, referenced by the submit button's `form=`. */
  formId: string;
  /** Element focused on open — the first field the user wants to type into. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Escape, backdrop click, the close (×) button and the Cancel button. */
  onClose: () => void;
  /** The page's create path. Wrapped in the same-tick guard; its result is awaited. */
  onSubmit: () => void | Promise<void>;
  /** A create is in flight: disables both buttons and swallows the chord. */
  isSaving: boolean;
  /** Mirrors the Save button's `disabled` gate and the shortcut's `canSave`. */
  canSave: boolean;
  /** `data-testid` of the Cancel button. */
  cancelTestId: string;
  /** `data-testid` of the Create/submit button. */
  saveTestId: string;
  /** Server/validation error, rendered as a `role="alert"` inside the form. */
  error?: string | null;
  /** Class for the error paragraph — the host's own `styles.createError`. */
  errorClassName?: string;
  /** The dialog's form fields (labels, inputs, textareas, selects). */
  children: ReactNode;
}

export function EditorPageShell({
  open,
  title,
  testId,
  formId,
  initialFocusRef,
  onClose,
  onSubmit,
  isSaving,
  canSave,
  cancelTestId,
  saveTestId,
  error,
  errorClassName,
  children,
}: EditorPageShellProps): JSX.Element | null {
  const { t } = useTranslation();
  // The form owns the shortcut: threaded into `useSaveShortcut`'s `containerRef`
  // so a covering modal suspends the chord instead of saving behind it.
  const formRef = useRef<HTMLFormElement>(null);
  // FR-U5-01: synchronous same-tick guard for BOTH submit entry points (the
  // Create button's `onSubmit` and the `Ctrl`/`Cmd`+`S` chord). `isSaving` is
  // React state, so a click followed by the chord inside one event-loop turn
  // still reads a stale `false` and submits twice. Mirrors `savingRef` in
  // `shared/ArtifactForm/ArtifactForm.tsx`.
  const submittingRef = useRef(false);

  const submit = async (): Promise<void> => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      await onSubmit();
    } finally {
      submittingRef.current = false;
    }
  };

  useSaveShortcut({
    onSave: submit,
    enabled: open,
    isSaving,
    containerRef: formRef,
    // Mirrors the Save button's `disabled={isSaving || !canSave}`: an empty
    // required field must not reach a submit path that only early-returns
    // silently (WCAG 3.3.1).
    canSave,
  });

  // `useSaveShortcut` above is called unconditionally (Rules of Hooks); the
  // dialog itself is only mounted while open, matching the pages' previous
  // `{showCreateDialog && <Dialog …/>}`.
  if (!open) return null;

  return (
    <Dialog
      title={title}
      onClose={onClose}
      testId={testId}
      initialFocusRef={initialFocusRef}
      footer={
        <>
          <button
            type="button"
            data-testid={cancelTestId}
            className="btn-secondary"
            onClick={onClose}
            disabled={isSaving}
          >
            {t("actions.cancel", "Cancel")}
          </button>
          <button
            type="submit"
            form={formId}
            data-testid={saveTestId}
            className="btn-primary"
            disabled={isSaving || !canSave}
            aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
            title={t("artifactForm.saveShortcutHint", "Speichern (Strg/Cmd+S)")}
          >
            {isSaving ? t("actions.saving", "Saving...") : t("actions.create", "Erstellen")}
          </button>
        </>
      }
    >
      <form
        id={formId}
        ref={formRef}
        // The controls carry a native `required` attribute (via
        // `useFieldContract`'s `controlProps`) for `:required` styling and the
        // accessible flag. `noValidate` keeps the browser's validation bubble
        // from pre-empting the app's own error flow — the `details[].field`
        // messages rendered per field, exactly as `ArtifactForm` already does.
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {children}
        {error && (
          <p role="alert" className={errorClassName}>
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
