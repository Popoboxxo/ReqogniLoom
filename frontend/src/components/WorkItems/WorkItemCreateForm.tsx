/**
 * ARCH-L1-001 ReactFrontend — work-item create form (Plan F F3-T9).
 *
 * Creates an item inside the open document. `document_id` is mandatory on the
 * wire (E11/O7); the form never offers a document picker because the panel is
 * already document-scoped.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useRequiredValidation } from "../shared/useRequiredValidation";

import { MarkdownField } from "../shared/MarkdownField/MarkdownField";
import type { WorkItemKind } from "../../types";
import { WORK_ITEM_KINDS } from "../../types";
import type { WorkItemCreatePayload } from "../../api/workItems";
import { workItemKindLabel } from "./workItemLabels";
import styles from "./WorkItems.module.css";

export interface WorkItemCreateFormProps {
  workspaceId: string;
  documentId: string;
  isSaving: boolean;
  error: string | null;
  onCreate: (payload: WorkItemCreatePayload) => void;
  onCancel: () => void;
}

export function WorkItemCreateForm({
  workspaceId,
  documentId,
  isSaving,
  error,
  onCreate,
  onCancel,
}: WorkItemCreateFormProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<WorkItemKind>("Step");
  const [ordinal, setOrdinal] = useState("0");
  const [nextAction, setNextAction] = useState("");
  const [body, setBody] = useState("");

  const ordinalNumber = Number(ordinal);
  const ordinalValid = Number.isInteger(ordinalNumber) && ordinalNumber >= 0;
  // #1732: the submit stays active and explains itself on click. The old
  // `canSave` predicate combined "title empty" with "ordinal malformed" and
  // hid both behind a disabled button.
  const {
    errors: requiredErrors,
    validate,
    focusFirstInvalid,
    clearError,
    fieldProps,
    errorId,
  } = useRequiredValidation();

  const submit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (isSaving) return;
    const fields = [
      { name: "title", value: title, inputId: "work-item-create-title" },
      {
        name: "ordinal",
        value: String(ordinal),
        inputId: "work-item-create-ordinal",
        isValid: ordinalValid,
        message: t("validation.numberInteger"),
      },
    ];
    const invalid = validate(fields);
    if (invalid.length > 0) {
      focusFirstInvalid(fields, invalid);
      return;
    }
    onCreate({
      workspace_id: workspaceId,
      document_id: documentId,
      title: title.trim(),
      kind,
      ordinal: ordinalNumber,
      next_action: nextAction,
      body,
    });
  };

  return (
    // `noValidate`: the app's own click-time validation is the contract
    // (#1732); the browser bubble would pre-empt it and break the
    // `aria-invalid`/`role="alert"` pairing.
    <form
      className={styles.form}
      data-testid="work-item-create"
      noValidate
      onSubmit={submit}
    >
      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-create-title">
          {t("work_items.fieldTitle")}
        </label>
        <input
          id="work-item-create-title"
          data-testid="work-item-create-title"
          className={styles.input}
          type="text"
          value={title}
          maxLength={255}
          required
          disabled={isSaving}
          onChange={(event) => {
            setTitle(event.target.value);
            clearError("title");
          }}
          {...fieldProps("title")}
        />
        {requiredErrors.title ? (
          <p
            id={errorId("title")}
            role="alert"
            className={styles.error}
            data-testid="work-item-create-title-error"
          >
            {requiredErrors.title}
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-create-kind">
          {t("work_items.fieldKind")}
        </label>
        <select
          id="work-item-create-kind"
          data-testid="work-item-create-kind"
          className={styles.select}
          value={kind}
          disabled={isSaving}
          onChange={(event) => setKind(event.target.value as WorkItemKind)}
        >
          {WORK_ITEM_KINDS.map((candidate) => (
            <option key={candidate} value={candidate}>
              {workItemKindLabel(t, candidate)}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-create-ordinal">
          {t("work_items.fieldOrdinal")}
        </label>
        <input
          id="work-item-create-ordinal"
          data-testid="work-item-create-ordinal"
          className={styles.input}
          type="number"
          min={0}
          step={1}
          value={ordinal}
          disabled={isSaving}
          onChange={(event) => {
            setOrdinal(event.target.value);
            clearError("ordinal");
          }}
          {...fieldProps("ordinal")}
        />
        {requiredErrors.ordinal ? (
          <p
            id={errorId("ordinal")}
            role="alert"
            className={styles.error}
            data-testid="work-item-create-ordinal-error"
          >
            {requiredErrors.ordinal}
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-create-next">
          {t("work_items.fieldNextAction")}
        </label>
        <input
          id="work-item-create-next"
          data-testid="work-item-create-next"
          className={styles.input}
          type="text"
          value={nextAction}
          maxLength={255}
          disabled={isSaving}
          onChange={(event) => setNextAction(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-create-body">
          {t("work_items.fieldBody")}
        </label>
        <MarkdownField
          id="work-item-create-body"
          value={body}
          onChange={setBody}
          disabled={isSaving}
        />
      </div>

      {error && (
        <p role="alert" className={styles.error} data-testid="work-item-create-error">
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="submit"
          className="btn-primary"
          data-testid="work-item-create-save"
          disabled={isSaving}
        >
          {isSaving ? t("work_items.saving") : t("work_items.create")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="work-item-create-cancel"
          disabled={isSaving}
          onClick={onCancel}
        >
          {t("work_items.cancel")}
        </button>
      </div>
    </form>
  );
}
