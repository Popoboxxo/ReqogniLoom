/**
 * ARCH-L1-001 ReactFrontend — Document reading view (R4, plan
 * 2026-11-15-document-view-on-document.md).
 *
 * Replaces the former read-only `<DocumentDetail>`: it renders the document
 * head, the capability/lock notice, the document fields and the chaptered body
 * with its table of contents. Content comes from the reading object
 * (`GET /documents/{id}/view/`), which already resolves the per-field write
 * verdicts server-side — the surface never offers a write the backend would
 * reject.
 *
 * Management actions stay opt-in: the lifecycle control only renders when the
 * caller passes `onTransitionComplete`, delete/reactivate only when their
 * handlers are passed. A caller that renders just the read surface (or a
 * viewer without write capability) therefore cannot accidentally expose an
 * edit affordance.
 */

import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import type { TFunction } from "i18next";

import { DocumentLifecycle } from "./DocumentLifecycle";
import { DocumentReadingChapters } from "./DocumentReadingChapters";
import { WorkItemsPanel } from "../WorkItems/WorkItemsPanel";
import { InlineReferenceHints } from "../WorkItems/InlineReferenceHints";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import { isOutdatedState } from "../../utils/outdatedStates";
import type {
  Document,
  DocumentKind,
  DocumentReading,
  ReadingField,
} from "../../types";
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

const FIELD_LABEL_KEY: Record<string, string> = {
  title: "documents.fieldTitle",
  description: "documents.fieldDescription",
  body: "documents.fieldBody",
  doc_date: "documents.fieldDate",
  custom_fields: "documents.customFields",
};

const READ_ONLY_REASON_KEY: Record<string, string> = {
  REPO_EXTERNAL: "documents.readOnlyRepoExternal",
  PERMISSION: "documents.readOnlyPermission",
};

export interface DocumentReadingViewProps {
  /** Backing document — carries the lifecycle identity (`status`, `version`). */
  document: Document;
  /** Chaptered read object from `GET /documents/{id}/view/`. */
  reading: DocumentReading;
  onEdit: () => void;
  workspaceId?: string;
  onDelete?: () => void;
  onReactivate?: () => void;
  /** Opt-in lifecycle control; omitted by pure read surfaces. */
  onTransitionComplete?: () => void;
  actionError?: string | null;
}

export function DocumentReadingView({
  document,
  reading,
  onEdit,
  workspaceId,
  onDelete,
  onReactivate,
  onTransitionComplete,
  actionError = null,
}: DocumentReadingViewProps): JSX.Element {
  const { t } = useTranslation();
  const canWrite = reading.capabilities.can_write;
  const outdated = isOutdatedState(reading.status);
  const frozenFields = reading.frozen_fields ?? [];
  const isFrozen = frozenFields.length > 0 || Boolean(reading.frozen_at);
  const frozenDate = reading.frozen_at ? reading.frozen_at.slice(0, 10) : null;
  const readOnlyReason = reading.capabilities.read_only_reason;
  const showNotice = isFrozen || readOnlyReason !== null;

  const fields = (
    <div className={styles.readingFields}>
      <p className={styles.sectionLabel}>{t("documents.fields")}</p>
      <dl className={styles.fieldList}>
        {reading.fields.map((field) => (
          <div
            key={field.name}
            className={styles.fieldRow}
            data-testid={`document-reading-field-${field.name}`}
          >
            <dt className={styles.fieldName}>
              {t(FIELD_LABEL_KEY[field.name] ?? field.name)}
            </dt>
            <dd className={styles.fieldValue}>
              <span>{fieldValueText(field, reading.chapters.length, t)}</span>
              {!field.editable && field.locked && (
                <span className={styles.fieldLock} title={field.locked.detail}>
                  <Lock size={14} aria-hidden="true" />
                  <span className="visually-hidden">{field.locked.detail}</span>
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );

  return (
    <article
      className={styles.detail}
      data-testid="document-reading-view"
      aria-labelledby="document-reading-title"
    >
      <header className={styles.detailHeader}>
        <div>
          <h2 id="document-reading-title" className={styles.detailTitle}>
            {reading.title || t("documents.untitled")}
          </h2>
          <p className={styles.meta}>
            <span data-testid="document-detail-uid">
              {reading.uid ?? reading.id.slice(0, 8)}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-kind">
              {t(KIND_LABEL_KEY[reading.kind])}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-status">
              {getWorkflowStatusLabel(reading.status)}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-version">
              {t("documents.versionLabel", { version: reading.version })}
            </span>
            {reading.doc_date && (
              <>
                <span aria-hidden="true">·</span>
                <span data-testid="document-detail-date">
                  {reading.doc_date}
                </span>
              </>
            )}
          </p>
        </div>

        {canWrite && !outdated && (
          <div className={styles.actions}>
            <button
              type="button"
              className="btn-primary"
              data-testid="document-edit"
              onClick={onEdit}
            >
              {t("documents.edit")}
            </button>
            {onDelete && (
              <button
                type="button"
                className="btn-danger"
                data-testid="document-delete"
                onClick={onDelete}
              >
                {t("documents.delete")}
              </button>
            )}
          </div>
        )}
        {canWrite && outdated && onReactivate && (
          <div className={styles.actions}>
            <button
              type="button"
              className="btn-secondary"
              data-testid="document-reactivate"
              onClick={onReactivate}
            >
              {t("documents.reactivate")}
            </button>
          </div>
        )}
      </header>

      {onTransitionComplete && (
        <section
          className={styles.lifecycle}
          aria-label={t("documents.lifecycle")}
        >
          <span className={styles.sectionLabel}>{t("documents.lifecycle")}</span>
          <DocumentLifecycle
            document={document}
            canWrite={canWrite}
            workspaceId={workspaceId}
            onTransitionComplete={onTransitionComplete}
          />
        </section>
      )}

      {showNotice && (
        <div
          role="note"
          className={styles.capabilityNotice}
          data-testid="document-reading-capability-notice"
        >
          {isFrozen && (
            <div data-testid="document-frozen-banner">
              <strong>{t("documents.frozenTitle")}</strong>
              <p>
                {frozenDate
                  ? t("documents.frozenSince", { date: frozenDate })
                  : t("documents.frozenHint")}
              </p>
              {frozenFields.length > 0 && (
                <p data-testid="document-frozen-fields">
                  {t("documents.frozenFields", {
                    fields: frozenFields.join(", "),
                  })}
                </p>
              )}
            </div>
          )}
          {readOnlyReason && (
            <p data-testid="document-read-only-reason">
              {t(
                READ_ONLY_REASON_KEY[readOnlyReason] ??
                  "documents.readOnlyPermission"
              )}
            </p>
          )}
        </div>
      )}

      {actionError && (
        <p
          role="alert"
          className={styles.error}
          data-testid="document-action-error"
        >
          {actionError}
        </p>
      )}

      {reading.description && (
        <section aria-label={t("documents.description")}>
          <h3 className={styles.sectionLabel}>{t("documents.description")}</h3>
          <p className={styles.description}>{reading.description}</p>
        </section>
      )}

      <DocumentReadingChapters
        chapters={reading.chapters}
        documentTitle={reading.title || t("documents.untitled")}
        metadata={fields}
      />

      {reading.chapters.length === 0 && (
        <p className={styles.placeholder} data-testid="document-reading-empty">
          {t("documents.bodyEmpty")}
        </p>
      )}

      <InlineReferenceHints
        text={reading.body}
        workspaceId={workspaceId}
        testId="document-inline-reference-hints"
      />

      <WorkItemsPanel
        documentId={reading.id}
        workspaceId={workspaceId}
        canWrite={canWrite}
      />
    </article>
  );
}

/**
 * Wire value of one reading field. The value is polymorphic by contract
 * (string, ISO date or the `custom_fields` map), so the surface renders it —
 * `body` is not repeated here, it is the chapter text.
 */
function fieldValueText(
  field: ReadingField,
  chapterCount: number,
  t: TFunction
): string {
  if (field.name === "body") {
    return t("documents.readingBodyInChapters", { total: chapterCount });
  }
  if (field.name === "custom_fields") {
    const entries = Object.entries(
      (field.value ?? {}) as Record<string, unknown>
    );
    if (entries.length === 0) return t("documents.fieldEmpty");
    return entries.map(([key, value]) => `${key}: ${String(value)}`).join(", ");
  }
  if (field.value === null || field.value === undefined || field.value === "") {
    return t("documents.fieldEmpty");
  }
  return String(field.value);
}

DocumentReadingView.displayName = "DocumentReadingView";
