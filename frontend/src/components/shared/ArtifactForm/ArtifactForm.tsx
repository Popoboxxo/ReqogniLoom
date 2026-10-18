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
 *
 * Phase 5b decomposition (FE-01 / F-01): this file is now the thin
 * orchestrator. State, derived memos, handlers and effects live in
 * `useArtifactFormState`; the section grid renders in `ArtifactSections`; the
 * action area in `ArtifactFormActions`; the per-attribute dispatch in
 * `renderAttribute`; the pure helpers in `form-helpers`. The public props API
 * of the 8 render sites and the barrel `index.ts` are unchanged — the public
 * helpers and types are re-exported below.
 */

import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import type { ArtifactFormProps } from "./artifact-form-types";
import { ArtifactSections } from "./ArtifactSections";
import { ArtifactFormActions } from "./ArtifactFormActions";
import { useArtifactFormState } from "./useArtifactFormState";
import styles from "./ArtifactForm.module.css";

// Re-exported so `./ArtifactForm` still provides the public helpers/types the
// barrel `index.ts` (and its consumers) import from it — no API change.
export { findFieldControl, firstErroredField, groupIntoSections } from "./form-helpers";
export type {
  ArtifactFormProps,
  ArtifactFormValues,
  FormSection,
} from "./artifact-form-types";

export function ArtifactForm({
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
  definitionFallback,
  onCancel,
  fieldTestIds,
  saveTestId = "artifact-form-save",
  headerActions,
}: ArtifactFormProps): JSX.Element {
  const { t } = useTranslation();

  const {
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
    onRequestDeprecate,
    onCancelDeprecate,
    onChangeDeprecateReason,
    handleDeprecate,
  } = useArtifactFormState({
    itemType,
    artifactId,
    initialValues,
    onSave,
    onDeprecate,
    onDirtyChange,
    mode,
    workflowArtifactType,
    requiresChangeReason,
    attributeOverrides,
    fieldTestIds,
  });

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
      data-version={values.version == null ? undefined : String(values.version)}
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

      <ArtifactSections
        sectionEntries={sectionEntries}
        sectionMeta={sectionMeta}
        specByName={specByName}
        formValues={formValues}
        fieldErrors={fieldErrors}
        isCreateMode={isCreateMode}
        isReadOnly={isReadOnly}
        saving={saving}
        artifactId={artifactId}
        workflowArtifactType={workflowArtifactType}
        fieldTestIds={fieldTestIds}
        isSectionOpen={isSectionOpen}
        onToggleSection={onToggleSection}
        update={update}
      />

      <ArtifactFormActions
        isReadOnly={isReadOnly}
        saving={saving}
        artifactId={artifactId}
        saveTestId={saveTestId}
        missingCreateValue={missingCreateValue}
        onCancel={onCancel}
        changeReasonNeeded={changeReasonNeeded}
        changeReason={changeReason}
        changeReasonInvalid={changeReasonInvalid}
        changeReasonRef={changeReasonRef}
        changeReasonErrorId={changeReasonErrorId}
        onChangeChangeReason={onChangeChangeReason}
        onDeprecate={onDeprecate}
        deprecateTransition={deprecateTransition}
        deprecateReasonNeeded={deprecateReasonNeeded}
        deprecateReasonMissing={deprecateReasonMissing}
        deprecateReason={deprecateReason}
        confirmDeprecate={confirmDeprecate}
        onRequestDeprecate={onRequestDeprecate}
        onCancelDeprecate={onCancelDeprecate}
        onChangeDeprecateReason={onChangeDeprecateReason}
        onConfirmDeprecate={handleDeprecate}
      />
    </form>
  );
}
