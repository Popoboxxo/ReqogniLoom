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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import type { TFunction } from "i18next";

import { DocumentFieldEditor } from "./DocumentFieldEditor";
import { DocumentLifecycle } from "./DocumentLifecycle";
import { DocumentReadingChapters } from "./DocumentReadingChapters";
import { DocumentSaveBar } from "./DocumentSaveBar";
import {
  useDocumentDrafts,
  type DocumentSaveMode,
} from "./useDocumentDrafts";
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
  /**
   * Refetch the reading object. Called after a successful inline save (so the
   * head, chapters and freeze verdicts follow the write) and by a conflicted
   * field's "reload" action.
   */
  onReload?: () => void;
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
  onReload,
}: DocumentReadingViewProps): JSX.Element {
  const { t } = useTranslation();
  // Save mode is a way of working, not a preference: it is deliberately *not*
  // persisted (no preference key), so every visit starts in the immediate mode.
  const [saveMode, setSaveMode] = useState<DocumentSaveMode>("immediate");
  const drafts = useDocumentDrafts(reading, {
    workspaceId,
    onSaved: () => onReload?.(),
  });

  const canWrite = reading.capabilities.can_write;
  const outdated = isOutdatedState(reading.status);
  const frozenFields = reading.frozen_fields ?? [];
  const isFrozen = frozenFields.length > 0 || Boolean(reading.frozen_at);
  const frozenDate = reading.frozen_at ? reading.frozen_at.slice(0, 10) : null;
  const readOnlyReason = reading.capabilities.read_only_reason;
  const showNotice = isFrozen || readOnlyReason !== null;

  const fields = (
    <section
      className={styles.readingFields}
      aria-label={t("documents.fields")}
      data-testid="document-editable-fields"
    >
      <p className={styles.sectionLabel}>{t("documents.fields")}</p>
      <div className={styles.fieldList}>
        {reading.fields.map((field) => (
          <div
            key={field.name}
            className={styles.fieldRow}
            data-testid={`document-reading-field-${field.name}`}
          >
            {canWrite ? (
              <DocumentFieldEditor
                field={field}
                label={t(FIELD_LABEL_KEY[field.name] ?? field.name)}
                draft={drafts.draftFor(field.name)}
                mode={saveMode}
                frozen={frozenFields.includes(field.name)}
                onChange={drafts.setDraft}
                onSave={(name) => {
                  void drafts.saveField(name);
                }}
                onReload={(name) => {
                  drafts.resetField(name);
                  onReload?.();
                }}
              />
            ) : (
              <FieldValue
                field={field}
                chapterCount={reading.chapters.length}
                t={t}
              />
            )}
          </div>
        ))}
      </div>
    </section>
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
              {t("documents.versionLabel", { version: drafts.version })}
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
            {/* R6: the save mode is a per-visit working style, never persisted. */}
            <div
              className={styles.modeToggle}
              role="group"
              aria-label={t("documents.saveModeLabel")}
            >
              <button
                type="button"
                className="btn-ghost"
                data-testid="document-mode-immediate"
                aria-pressed={saveMode === "immediate"}
                onClick={() => setSaveMode("immediate")}
              >
                {t("documents.saveModeImmediate")}
              </button>
              <button
                type="button"
                className="btn-ghost"
                data-testid="document-mode-batch"
                aria-pressed={saveMode === "batch"}
                onClick={() => setSaveMode("batch")}
              >
                {t("documents.saveModeBatch")}
              </button>
            </div>
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

      {canWrite && saveMode === "batch" && (
        <DocumentSaveBar
          dirtyCount={drafts.dirtyCount}
          conflicts={drafts.conflicts}
          saving={drafts.saving}
          error={drafts.saveError}
          onSaveAll={() => {
            void drafts.saveAll();
          }}
          onDiscard={drafts.resetAll}
        />
      )}

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

      {/*
       * Editors need the wide column: the table-of-contents aside is 16rem and
       * would squeeze a Markdown textarea into a peephole. The read-only
       * metadata therefore stays in the aside only when nothing is editable.
       */}
      {canWrite && fields}

      <DocumentReadingChapters
        chapters={reading.chapters}
        documentTitle={reading.title || t("documents.untitled")}
        metadata={canWrite ? undefined : fields}
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
 * Read-only rendering of one field: what a viewer sees. The value is
 * polymorphic by contract (string, ISO date or the `custom_fields` map), so the
 * surface renders it — `body` is not repeated here, it is the chapter text.
 */
function FieldValue({
  field,
  chapterCount,
  t,
}: {
  field: ReadingField;
  chapterCount: number;
  t: TFunction;
}): JSX.Element {
  return (
    <>
      <span className={styles.fieldName}>
        {t(FIELD_LABEL_KEY[field.name] ?? field.name)}
      </span>
      <span className={styles.fieldValue}>
        <span>{fieldValueText(field, chapterCount, t)}</span>
        {!field.editable && field.locked && (
          <span className={styles.fieldLock} title={field.locked.detail}>
            <Lock size={14} aria-hidden="true" />
            <span className="visually-hidden">{field.locked.detail}</span>
          </span>
        )}
      </span>
    </>
  );
}

/**
 * Wire value of one reading field, as text.
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
