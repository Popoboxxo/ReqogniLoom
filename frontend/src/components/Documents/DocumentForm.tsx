/**
 * ARCH-L1-001 ReactFrontend — Document editor (Plan F F2-T8).
 *
 * Uses the existing `<MarkdownField>` for the body (Plan C C2) instead of a
 * second markdown editor. Freeze is a first-class editor state: fields named
 * in `frozen_fields` are disabled and omitted from the PATCH, because the
 * service rejects *any* write that touches a frozen field with
 * `409 FIELD_FROZEN` — even when the value is unchanged. `doc_date` stays
 * editable while frozen (F-2).
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownField } from "../shared/MarkdownField/MarkdownField";
import { DOCUMENT_KINDS } from "../../types";
import type { Document, DocumentKind } from "../../types";
import type { DocumentUpdatePayload } from "../../api/documents";
import styles from "./Documents.module.css";

const KIND_LABEL_KEY: Record<DocumentKind, string> = {
  Spec: "documents.kinds.spec",
  Plan: "documents.kinds.plan",
  AuditReport: "documents.kinds.auditReport",
  Review: "documents.kinds.review",
  Conclusion: "documents.kinds.conclusion",
  Concept: "documents.kinds.concept",
  Guide: "documents.kinds.guide",
};

export interface DocumentFormProps {
  document: Document;
  isSaving: boolean;
  error: string | null;
  onSave: (payload: DocumentUpdatePayload) => void;
  onCancel: () => void;
}

export function DocumentForm({
  document,
  isSaving,
  error,
  onSave,
  onCancel,
}: DocumentFormProps): JSX.Element {
  const { t } = useTranslation();
  const frozenFields = useMemo(
    () => new Set(document.frozen_fields ?? []),
    [document.frozen_fields]
  );

  const [title, setTitle] = useState(document.title);
  const [kind, setKind] = useState<DocumentKind>(document.kind);
  const [docDate, setDocDate] = useState(document.doc_date ?? "");
  const [description, setDescription] = useState(document.description);
  const [body, setBody] = useState(document.body);
  const [changeReason, setChangeReason] = useState("");

  const titleFrozen = frozenFields.has("title");
  const kindFrozen = frozenFields.has("kind");
  const descriptionFrozen = frozenFields.has("description");
  const bodyFrozen = frozenFields.has("body");

  const payload = useMemo((): DocumentUpdatePayload => {
    const next: DocumentUpdatePayload = {};
    if (!titleFrozen && title !== document.title) next.title = title;
    if (!kindFrozen && kind !== document.kind) next.kind = kind;
    if (!descriptionFrozen && description !== document.description) {
      next.description = description;
    }
    if (!bodyFrozen && body !== document.body) next.body = body;
    if (docDate !== (document.doc_date ?? "")) {
      next.doc_date = docDate || null;
    }
    if (changeReason.trim()) next.change_reason = changeReason.trim();
    return next;
  }, [
    body,
    bodyFrozen,
    changeReason,
    description,
    descriptionFrozen,
    docDate,
    document.body,
    document.description,
    document.doc_date,
    document.kind,
    document.title,
    kind,
    kindFrozen,
    title,
    titleFrozen,
  ]);

  const hasChanges = Object.keys(payload).length > 0 && title.trim().length > 0;

  const submit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!hasChanges || isSaving) return;
    onSave(payload);
  };

  return (
    <form
      className={styles.form}
      data-testid="document-form"
      onSubmit={submit}
    >
      <div className={styles.formHeader}>
        <h2 className={styles.detailTitle}>{t("documents.editTitle")}</h2>
      </div>

      {frozenFields.size > 0 && (
        <div role="note" className={styles.freezeBanner}>
          <strong>{t("documents.frozenTitle")}</strong>
          <p>{t("documents.frozenEditHint")}</p>
        </div>
      )}

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-title">
          {t("documents.fieldTitle")}
        </label>
        <input
          id="document-edit-title"
          data-testid="document-edit-title"
          className={styles.input}
          type="text"
          value={title}
          maxLength={255}
          required
          disabled={titleFrozen || isSaving}
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-kind">
          {t("documents.fieldKind")}
        </label>
        <select
          id="document-edit-kind"
          data-testid="document-edit-kind"
          className={styles.select}
          value={kind}
          disabled={kindFrozen || isSaving}
          onChange={(event) => setKind(event.target.value as DocumentKind)}
        >
          {DOCUMENT_KINDS.map((value) => (
            <option key={value} value={value}>
              {t(KIND_LABEL_KEY[value])}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-date">
          {t("documents.fieldDate")}
        </label>
        <input
          id="document-edit-date"
          data-testid="document-edit-date"
          className={styles.input}
          type="date"
          value={docDate}
          disabled={isSaving}
          onChange={(event) => setDocDate(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-description">
          {t("documents.fieldDescription")}
        </label>
        <textarea
          id="document-edit-description"
          data-testid="document-edit-description"
          className={styles.textarea}
          value={description}
          rows={3}
          maxLength={20000}
          disabled={descriptionFrozen || isSaving}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-body">
          {t("documents.fieldBody")}
        </label>
        <MarkdownField
          id="document-edit-body"
          value={body}
          onChange={setBody}
          disabled={bodyFrozen || isSaving}
          artifactId={document.artifact_id ?? null}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="document-edit-change-reason">
          {t("documents.fieldChangeReason")}
        </label>
        <input
          id="document-edit-change-reason"
          data-testid="document-edit-change-reason"
          className={styles.input}
          type="text"
          value={changeReason}
          maxLength={2000}
          disabled={isSaving}
          onChange={(event) => setChangeReason(event.target.value)}
        />
      </div>

      {error && (
        <p role="alert" className={styles.error} data-testid="document-form-error">
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="submit"
          className="btn-primary"
          data-testid="document-save"
          disabled={!hasChanges || isSaving}
        >
          {isSaving ? t("documents.saving") : t("documents.save")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="document-cancel"
          onClick={onCancel}
          disabled={isSaving}
        >
          {t("documents.cancel")}
        </button>
      </div>
    </form>
  );
}

DocumentForm.displayName = "DocumentForm";
