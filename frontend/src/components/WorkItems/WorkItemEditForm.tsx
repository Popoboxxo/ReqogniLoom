/**
 * ARCH-L1-001 ReactFrontend — work-item editor (Plan F F3-T9).
 *
 * Uses the shared `<MarkdownField>` (Plan C C2) for the item body. The term
 * sidebar is the drag source for `[[glossary:…]]` tokens (ENT-F3 = a); a drop
 * on the editor inserts the canonical token at the textarea caret. Saving
 * forwards the item's own `version` as the `If-Match` precondition (KA-F-08).
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRequiredValidation } from "../shared/useRequiredValidation";

import { MarkdownField } from "../shared/MarkdownField/MarkdownField";
import type { WorkItem, WorkItemKind } from "../../types";
import { WORK_ITEM_KINDS } from "../../types";
import type { WorkItemUpdatePayload } from "../../api/workItems";
import { workItemKindLabel } from "./workItemLabels";
import { TermSidebar } from "./TermSidebar";
import styles from "./WorkItems.module.css";

export interface WorkItemEditFormProps {
  item: WorkItem;
  workspaceId?: string;
  isSaving: boolean;
  error: string | null;
  onSave: (payload: WorkItemUpdatePayload) => void;
  onCancel: () => void;
}

export function WorkItemEditForm({
  item,
  workspaceId,
  isSaving,
  error,
  onSave,
  onCancel,
}: WorkItemEditFormProps): JSX.Element {
  const { t } = useTranslation();
  const bodyId = `work-item-body-${item.id}`;
  const [title, setTitle] = useState(item.title);
  const [kind, setKind] = useState<WorkItemKind>(item.kind);
  const [ordinal, setOrdinal] = useState(String(item.ordinal));
  const [progress, setProgress] = useState(
    item.progress === null ? "" : String(item.progress)
  );
  const [nextAction, setNextAction] = useState(item.next_action);
  const [blockedReason, setBlockedReason] = useState(item.blocked_reason);
  const [body, setBody] = useState(item.body);
  const [evidenceRef, setEvidenceRef] = useState(item.evidence_ref);
  const [exitCriteria, setExitCriteria] = useState(item.exit_criteria);
  const [changeReason, setChangeReason] = useState("");
  const [dropActive, setDropActive] = useState(false);
  const pendingCaret = useRef<number | null>(null);

  useEffect(() => {
    const el = document.getElementById(bodyId) as HTMLTextAreaElement | null;
    const caret = pendingCaret.current;
    if (!el || caret === null) return;
    pendingCaret.current = null;
    el.focus();
    el.setSelectionRange(caret, caret);
  }, [body, bodyId]);

  const insertToken = (token: string): void => {
    if (!token) return;
    const el = document.getElementById(bodyId) as HTMLTextAreaElement | null;
    const start = el?.selectionStart ?? body.length;
    const end = el?.selectionEnd ?? body.length;
    setBody(`${body.slice(0, start)}${token}${body.slice(end)}`);
    pendingCaret.current = start + token.length;
  };

  const progressValue = progress.trim();
  const progressNumber = progressValue === "" ? null : Number(progressValue);
  const progressValid =
    progressNumber === null ||
    (Number.isInteger(progressNumber) &&
      progressNumber >= 0 &&
      progressNumber <= 100);
  const ordinalNumber = Number(ordinal);
  const ordinalValid = Number.isInteger(ordinalNumber) && ordinalNumber >= 0;
  // #1732: the submit stays active and explains itself on click; the old
  // `canSave` predicate hid the reason behind a disabled button.
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
      { name: "title", value: title, inputId: "work-item-edit-title" },
      {
        name: "ordinal",
        value: String(ordinal),
        inputId: "work-item-edit-ordinal",
        isValid: ordinalValid,
        message: t("validation.numberInteger"),
      },
      {
        name: "progress",
        value: progress,
        inputId: "work-item-edit-progress",
        isValid: progressValid,
        message: t("validation.percentRange"),
      },
    ];
    const invalid = validate(fields);
    if (invalid.length > 0) {
      focusFirstInvalid(fields, invalid);
      return;
    }
    const payload: WorkItemUpdatePayload = {};
    if (title !== item.title) payload.title = title;
    if (kind !== item.kind) payload.kind = kind;
    if (ordinalNumber !== item.ordinal) payload.ordinal = ordinalNumber;
    if (progressNumber !== item.progress) payload.progress = progressNumber;
    if (nextAction !== item.next_action) payload.next_action = nextAction;
    if (blockedReason !== item.blocked_reason) {
      payload.blocked_reason = blockedReason;
    }
    if (body !== item.body) payload.body = body;
    if (evidenceRef !== item.evidence_ref) payload.evidence_ref = evidenceRef;
    if (exitCriteria !== item.exit_criteria) {
      payload.exit_criteria = exitCriteria;
    }
    if (changeReason.trim()) payload.change_reason = changeReason.trim();
    onSave(payload);
  };

  return (
    // `noValidate`: the app's click-time validation is the contract (#1732).
    <form
      className={styles.form}
      data-testid="work-item-edit"
      noValidate
      onSubmit={submit}
    >
      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-title">
          {t("work_items.fieldTitle")}
        </label>
        <input
          id="work-item-edit-title"
          data-testid="work-item-edit-title"
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
            data-testid="work-item-edit-title-error"
          >
            {requiredErrors.title}
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-kind">
          {t("work_items.fieldKind")}
        </label>
        <select
          id="work-item-edit-kind"
          data-testid="work-item-edit-kind"
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
        <label className={styles.label} htmlFor="work-item-edit-ordinal">
          {t("work_items.fieldOrdinal")}
        </label>
        <input
          id="work-item-edit-ordinal"
          data-testid="work-item-edit-ordinal"
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
            data-testid="work-item-edit-ordinal-error"
          >
            {requiredErrors.ordinal}
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-progress">
          {t("work_items.fieldProgress")}
        </label>
        <input
          id="work-item-edit-progress"
          data-testid="work-item-edit-progress"
          className={styles.input}
          type="number"
          min={0}
          max={100}
          step={1}
          value={progress}
          disabled={isSaving}
          onChange={(event) => {
            setProgress(event.target.value);
            clearError("progress");
          }}
          {...fieldProps("progress")}
        />
        {requiredErrors.progress ? (
          <p
            id={errorId("progress")}
            role="alert"
            className={styles.error}
            data-testid="work-item-edit-progress-error"
          >
            {requiredErrors.progress}
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-next">
          {t("work_items.fieldNextAction")}
        </label>
        <input
          id="work-item-edit-next"
          data-testid="work-item-edit-next"
          className={styles.input}
          type="text"
          value={nextAction}
          maxLength={255}
          disabled={isSaving}
          onChange={(event) => setNextAction(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-blocked">
          {t("work_items.fieldBlockedReason")}
        </label>
        <textarea
          id="work-item-edit-blocked"
          data-testid="work-item-edit-blocked"
          className={styles.textarea}
          value={blockedReason}
          rows={2}
          disabled={isSaving}
          onChange={(event) => setBlockedReason(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor={bodyId}>
          {t("work_items.fieldBody")}
        </label>
        <div
          className={`${styles.dropZone} ${dropActive ? styles.dropActive : ""}`}
          data-testid="work-item-drop-zone"
          role="group"
          aria-label={t("work_items.termSidebar.dragHint")}
          onDragOver={(event) => {
            event.preventDefault();
            setDropActive(true);
          }}
          onDragLeave={() => setDropActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDropActive(false);
            insertToken(event.dataTransfer.getData("text/plain"));
          }}
        >
          <MarkdownField
            id={bodyId}
            value={body}
            onChange={setBody}
            disabled={isSaving}
            artifactId={item.artifact_id}
          />
        </div>
        <TermSidebar
          workspaceId={workspaceId}
          disabled={isSaving}
          onInsert={insertToken}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-evidence">
          {t("work_items.fieldEvidence")}
        </label>
        <input
          id="work-item-edit-evidence"
          data-testid="work-item-edit-evidence"
          className={styles.input}
          type="text"
          value={evidenceRef}
          maxLength={512}
          disabled={isSaving}
          onChange={(event) => setEvidenceRef(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-exit">
          {t("work_items.fieldExitCriteria")}
        </label>
        <textarea
          id="work-item-edit-exit"
          data-testid="work-item-edit-exit"
          className={styles.textarea}
          value={exitCriteria}
          rows={2}
          disabled={isSaving}
          onChange={(event) => setExitCriteria(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="work-item-edit-reason">
          {t("work_items.fieldChangeReason")}
        </label>
        <input
          id="work-item-edit-reason"
          data-testid="work-item-edit-reason"
          className={styles.input}
          type="text"
          value={changeReason}
          maxLength={2000}
          disabled={isSaving}
          onChange={(event) => setChangeReason(event.target.value)}
        />
      </div>

      {!progressValid && (
        <p role="alert" className={styles.error}>
          {t("work_items.progressInvalid")}
        </p>
      )}

      {error && (
        <p role="alert" className={styles.error} data-testid="work-item-edit-error">
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="submit"
          className="btn-primary"
          data-testid="work-item-edit-save"
          disabled={isSaving}
        >
          {isSaving ? t("work_items.saving") : t("work_items.save")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="work-item-edit-cancel"
          disabled={isSaving}
          onClick={onCancel}
        >
          {t("work_items.cancel")}
        </button>
      </div>
    </form>
  );
}
