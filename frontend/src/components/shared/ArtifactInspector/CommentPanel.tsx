/**
 * CommentPanel — comments on the currently inspected artifact.
 *
 * Menschen-im-System spec §4. Mounted as the fourth stacked panel of the
 * RightSidebar rather than as a tab: the inspector has no tab/anchor concept
 * (see the comment in RightSidebar.tsx), and inventing one for a single panel
 * would be disproportionate.
 *
 * Comments are never edited — create, resolve, delete only.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { commentsApi, type Comment } from "../../../api/comments";
import { ConfirmDialog } from "../ConfirmDialog";
import type { ArtifactKind } from "./types";
import styles from "./CommentPanel.module.css";

export interface CommentPanelProps {
  /** The inspected artifact's kind — used for the panel heading only. */
  kind: ArtifactKind;
  /** The generic Artifact id (not the business-entity id). */
  artifactId: string;
}

export function CommentPanel({ kind, artifactId }: CommentPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Comment | null>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      setComments(await commentsApi.list(artifactId));
      setError(null);
    } catch {
      setError(t("comments.loadFailed", "Could not load comments."));
    }
  }, [artifactId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSubmit = useCallback(async (): Promise<void> => {
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    try {
      await commentsApi.create(artifactId, text);
      setDraft("");
      await load();
    } catch {
      setError(t("comments.createFailed", "Could not save the comment."));
    } finally {
      setBusy(false);
    }
  }, [artifactId, draft, load, t]);

  const handleResolve = useCallback(
    async (comment: Comment): Promise<void> => {
      setBusy(true);
      try {
        await commentsApi.resolve(comment.id);
        await load();
      } catch {
        setError(t("comments.resolveFailed", "Could not resolve the comment."));
      } finally {
        setBusy(false);
      }
    },
    [load, t]
  );

  const handleDeleteConfirmed = useCallback(async (): Promise<void> => {
    if (!pendingDelete) return;
    setBusy(true);
    try {
      await commentsApi.remove(pendingDelete.id);
      // Close on the success path too — a dialog left open after a completed
      // action is the #669/#670 failure mode.
      setPendingDelete(null);
      await load();
    } catch {
      setError(t("comments.deleteFailed", "Could not delete the comment."));
      setPendingDelete(null);
    } finally {
      setBusy(false);
    }
  }, [load, pendingDelete, t]);

  return (
    <section
      className={styles.panel}
      aria-label={t("comments.ariaLabel", "Comments")}
      data-testid="comment-panel"
      data-artifact-kind={kind}
    >
      <h3 className={styles.heading}>{t("comments.heading", "Comments")}</h3>

      {error && (
        <p className={styles.error} role="alert" data-testid="comment-panel-error">
          {error}
        </p>
      )}

      {comments.length === 0 ? (
        <p className={styles.empty} data-testid="comment-panel-empty">
          {t("comments.empty", "No comments yet.")}
        </p>
      ) : (
        <ul className={styles.list} data-testid="comment-panel-list">
          {comments.map((comment) => (
            <li
              key={comment.id}
              className={
                comment.resolved ? `${styles.item} ${styles.itemResolved}` : styles.item
              }
              data-testid={`comment-panel-item-${comment.id}`}
            >
              <div className={styles.meta}>
                <span>{comment.authorDisplay ?? t("comments.unknownAuthor", "Unknown")}</span>
                <span>{comment.createdAt}</span>
              </div>
              <p className={styles.text}>{comment.text}</p>
              <div className={styles.actions}>
                {!comment.resolved && (
                  <button
                    type="button"
                    className={styles.actionBtn}
                    disabled={busy}
                    onClick={() => void handleResolve(comment)}
                    data-testid={`comment-panel-resolve-${comment.id}`}
                  >
                    {t("comments.resolve", "Resolve")}
                  </button>
                )}
                <button
                  type="button"
                  className={styles.actionBtn}
                  disabled={busy}
                  onClick={() => setPendingDelete(comment)}
                  data-testid={`comment-panel-delete-${comment.id}`}
                >
                  {t("comments.delete", "Delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.composer}>
        <textarea
          className={styles.input}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("comments.placeholder", "Write a comment…")}
          aria-label={t("comments.inputLabel", "New comment")}
          data-testid="comment-panel-input"
        />
        <button
          type="button"
          className={styles.actionBtn}
          disabled={busy || draft.trim().length === 0}
          onClick={() => void handleSubmit()}
          data-testid="comment-panel-submit"
        >
          {t("comments.submit", "Comment")}
        </button>
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title={t("comments.deleteTitle", "Delete comment")}
          message={t("comments.deleteMessage", "This cannot be undone.")}
          confirmLabel={t("comments.delete", "Delete")}
          cancelLabel={t("actions.cancel", "Cancel")}
          onConfirm={() => void handleDeleteConfirmed()}
          onCancel={() => setPendingDelete(null)}
          isSubmitting={busy}
          testId="comment-delete-dialog"
          confirmTestId="comment-delete-confirm"
          cancelTestId="comment-delete-cancel"
        />
      )}
    </section>
  );
}
