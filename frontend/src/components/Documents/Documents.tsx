/**
 * ARCH-L1-001 ReactFrontend — Documents route (Plan F F2-T8, ADR-026).
 *
 * Composition only: the list owns filtering/selection, the detail owns the
 * read view, the editor owns the freeze-aware form. TanStack Query hooks in
 * `queries/documents.ts` provide the state machine (loading / error / empty /
 * success) for every data-bound surface; no panel renders as if data were
 * always present.
 *
 * Lifecycle actions are delegated to `<WorkflowStatusEditor>` (F2-T2's
 * `document_default` state machine): `Entwurf → In Prüfung → Freigegeben`
 * with the F-1 freeze on release and the G-1…G-4 gates server-side.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "../shared/PageHeader";
import { SplitView } from "../SplitView/SplitView";
import { EmptyState } from "../shared/EmptyState";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { EditorPageShell } from "../shared/EditorPageShell";
import { MarkdownField } from "../shared/MarkdownField/MarkdownField";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useHasRole } from "../../hooks/useHasRole";
import { extractApiErrorMessage } from "../../api/client";
import {
  documentKeys,
  useCreateDocument,
  useDeleteDocument,
  useDocument,
  useDocuments,
  useReactivateDocument,
  useUpdateDocument,
} from "../../queries/documents";
import { DOCUMENT_KINDS } from "../../types";
import type { DocumentKind } from "../../types";
import type { DocumentUpdatePayload } from "../../api/documents";
import { DocumentList } from "./DocumentList";
import { DocumentDetail } from "./DocumentDetail";
import { DocumentForm } from "./DocumentForm";
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

interface CreateFormState {
  title: string;
  kind: DocumentKind;
  docDate: string;
  description: string;
  body: string;
}

const EMPTY_CREATE_FORM: CreateFormState = {
  title: "",
  kind: "Spec",
  docDate: "",
  description: "",
  body: "",
};

export default function Documents(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: selectedId } = useParams<{ id?: string }>();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const hasRole = useHasRole();
  const canWrite = hasRole("editor");
  const workspaceId = activeWorkspace?.id;

  const [includeDeleted, setIncludeDeleted] = useState(false);
  const listQuery = useDocuments(
    workspaceId,
    includeDeleted,
    !isLoadingWorkspace
  );
  const detailQuery = useDocument(selectedId);

  const createMutation = useCreateDocument(workspaceId, includeDeleted);
  const updateMutation = useUpdateDocument(workspaceId, includeDeleted);
  const deleteMutation = useDeleteDocument(workspaceId, includeDeleted);
  const reactivateMutation = useReactivateDocument(workspaceId, includeDeleted);

  const [isEditing, setIsEditing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] =
    useState<CreateFormState>(EMPTY_CREATE_FORM);
  const [createError, setCreateError] = useState<string | null>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // A route change replaces the edited entity; an open editor must not keep
  // the previous document's draft fields.
  useEffect(() => {
    setIsEditing(false);
    setActionError(null);
  }, [selectedId]);

  const refreshAll = useCallback((): void => {
    void queryClient.invalidateQueries({ queryKey: documentKeys.all });
  }, [queryClient]);

  const openCreate = useCallback((): void => {
    setCreateForm(EMPTY_CREATE_FORM);
    setCreateError(null);
    setCreateOpen(true);
  }, []);

  const closeCreate = useCallback((): void => {
    if (createMutation.isPending) return;
    setCreateOpen(false);
  }, [createMutation.isPending]);

  const submitCreate = useCallback((): void => {
    setCreateError(null);
    if (!workspaceId || createForm.title.trim().length === 0) return;
    createMutation.mutate(
      {
        payload: {
          workspace_id: workspaceId,
          title: createForm.title.trim(),
          kind: createForm.kind,
          description: createForm.description,
          body: createForm.body,
          doc_date: createForm.docDate || null,
        },
      },
      {
        onSuccess: (created) => {
          setCreateOpen(false);
          navigate(`/documents/${created.id}`);
        },
        onError: (error) => {
          setCreateError(
            extractApiErrorMessage(error) ?? t("documents.createFailed")
          );
        },
      }
    );
  }, [createForm, createMutation, navigate, t, workspaceId]);

  const saveDocument = useCallback(
    (payload: DocumentUpdatePayload): void => {
      const document = detailQuery.data;
      if (!document) return;
      setActionError(null);
      updateMutation.mutate(
        { id: document.id, payload, expectedVersion: document.version },
        {
          onSuccess: () => setIsEditing(false),
          onError: (error) => {
            setActionError(
              extractApiErrorMessage(error) ?? t("documents.saveFailed")
            );
          },
        }
      );
    },
    [detailQuery.data, t, updateMutation]
  );

  const confirmDelete = useCallback((): void => {
    const document = detailQuery.data;
    if (!document) return;
    setDeleteError(null);
    deleteMutation.mutate(
      { id: document.id, changeReason: deleteReason.trim() || undefined },
      {
        onSuccess: () => {
          setDeleteOpen(false);
          setDeleteReason("");
        },
        onError: (error) => {
          setDeleteError(
            extractApiErrorMessage(error) ?? t("documents.deleteFailed")
          );
        },
      }
    );
  }, [deleteMutation, deleteReason, detailQuery.data, t]);

  const reactivate = useCallback((): void => {
    const document = detailQuery.data;
    if (!document) return;
    setActionError(null);
    reactivateMutation.mutate(document.id, {
      onError: (error) => {
        setActionError(
          extractApiErrorMessage(error) ?? t("documents.reactivateFailed")
        );
      },
    });
  }, [detailQuery.data, reactivateMutation, t]);

  const detail = (() => {
    if (!selectedId) {
      return (
        <p className={styles.placeholder} data-testid="documents-select-prompt">
          {t("documents.selectDocument")}
        </p>
      );
    }
    if (detailQuery.isLoading) {
      return (
        <EmptyState
          variant="loading"
          testId="document-detail-loading"
          label={t("documents.loading")}
        />
      );
    }
    if (detailQuery.error) {
      return (
        <EmptyState
          variant="error"
          testId="document-detail-error"
          title={t("documents.loadFailed")}
          description={detailQuery.error.message}
          onRetry={() => {
            void detailQuery.refetch();
          }}
          retryLabel={t("documents.retry")}
        />
      );
    }
    const document = detailQuery.data;
    if (!document) {
      return (
        <p className={styles.placeholder} data-testid="documents-not-found">
          {t("documents.notFound")}
        </p>
      );
    }
    if (isEditing) {
      return (
        <DocumentForm
          document={document}
          isSaving={updateMutation.isPending}
          error={actionError}
          onSave={saveDocument}
          onCancel={() => {
            setActionError(null);
            setIsEditing(false);
          }}
        />
      );
    }
    return (
      <DocumentDetail
        document={document}
        canWrite={canWrite}
        workspaceId={workspaceId}
        onEdit={() => setIsEditing(true)}
        onDelete={() => {
          setDeleteReason("");
          setDeleteError(null);
          setDeleteOpen(true);
        }}
        onReactivate={reactivate}
        onTransitionComplete={refreshAll}
        actionError={actionError}
      />
    );
  })();

  return (
    <div className={styles.page} data-testid="documents-view">
      <PageHeader
        title={t("documents.title")}
        summary={t("documents.summary", {
          value: listQuery.data?.length ?? 0,
        })}
        primaryAction={
          canWrite
            ? {
                label: t("documents.newDocument"),
                prefixWithPlus: true,
                onClick: openCreate,
                testId: "documents-new",
              }
            : undefined
        }
      />

      <SplitView
        moduleType="documents"
        list={
          <DocumentList
            items={listQuery.data ?? []}
            selectedId={selectedId}
            onSelect={(id) => navigate(`/documents/${id}`)}
            onCreateNew={openCreate}
            canCreate={canWrite}
            isLoading={isLoadingWorkspace || listQuery.isLoading}
            error={listQuery.error}
            onRetry={() => {
              void listQuery.refetch();
            }}
            includeDeleted={includeDeleted}
            onIncludeDeletedChange={setIncludeDeleted}
            workspaceId={workspaceId ?? null}
          />
        }
        detail={detail}
      />

      {createOpen && (
        <EditorPageShell
          open={createOpen}
          title={t("documents.newDocument")}
          testId="document-create-dialog"
          formId="document-create-form"
          initialFocusRef={titleInputRef}
          onClose={closeCreate}
          onSubmit={submitCreate}
          isSaving={createMutation.isPending}
          canSave={createForm.title.trim().length > 0}
          cancelTestId="document-create-cancel"
          saveTestId="document-create-save"
          error={createError}
          errorClassName={styles.error}
        >
          <div className={styles.field}>
            <label className={styles.label} htmlFor="document-create-title">
              {t("documents.fieldTitle")}
            </label>
            <input
              ref={titleInputRef}
              id="document-create-title"
              data-testid="document-create-title"
              className={styles.input}
              type="text"
              value={createForm.title}
              maxLength={255}
              required
              onChange={(event) =>
                setCreateForm((prev) => ({
                  ...prev,
                  title: event.target.value,
                }))
              }
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="document-create-kind">
              {t("documents.fieldKind")}
            </label>
            <select
              id="document-create-kind"
              data-testid="document-create-kind"
              className={styles.select}
              value={createForm.kind}
              onChange={(event) =>
                setCreateForm((prev) => ({
                  ...prev,
                  kind: event.target.value as DocumentKind,
                }))
              }
            >
              {DOCUMENT_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {t(KIND_LABEL_KEY[kind])}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="document-create-date">
              {t("documents.fieldDate")}
            </label>
            <input
              id="document-create-date"
              data-testid="document-create-date"
              className={styles.input}
              type="date"
              value={createForm.docDate}
              onChange={(event) =>
                setCreateForm((prev) => ({
                  ...prev,
                  docDate: event.target.value,
                }))
              }
            />
          </div>

          <div className={styles.field}>
            <label
              className={styles.label}
              htmlFor="document-create-description"
            >
              {t("documents.fieldDescription")}
            </label>
            <textarea
              id="document-create-description"
              data-testid="document-create-description"
              className={styles.textarea}
              value={createForm.description}
              rows={3}
              maxLength={20000}
              onChange={(event) =>
                setCreateForm((prev) => ({
                  ...prev,
                  description: event.target.value,
                }))
              }
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="document-create-body">
              {t("documents.fieldBody")}
            </label>
            <MarkdownField
              id="document-create-body"
              value={createForm.body}
              onChange={(next) =>
                setCreateForm((prev) => ({ ...prev, body: next }))
              }
            />
          </div>
        </EditorPageShell>
      )}

      {deleteOpen && (
        <ConfirmDialog
          title={t("documents.deleteTitle")}
          message={t("documents.deleteMessage")}
          confirmLabel={t("documents.deleteConfirm")}
          cancelLabel={t("documents.cancel")}
          onConfirm={confirmDelete}
          onCancel={() => {
            if (!deleteMutation.isPending) setDeleteOpen(false);
          }}
          testId="document-delete-dialog"
          isSubmitting={deleteMutation.isPending}
          confirmTestId="document-delete-confirm"
          cancelTestId="document-delete-cancel"
        >
          <div className={styles.field}>
            <label className={styles.label} htmlFor="document-delete-reason">
              {t("documents.fieldChangeReason")}
            </label>
            <input
              id="document-delete-reason"
              data-testid="document-delete-reason"
              className={styles.input}
              type="text"
              value={deleteReason}
              maxLength={2000}
              disabled={deleteMutation.isPending}
              onChange={(event) => setDeleteReason(event.target.value)}
            />
          </div>
          {deleteError && (
            <p role="alert" className={styles.error}>
              {deleteError}
            </p>
          )}
        </ConfirmDialog>
      )}
    </div>
  );
}
