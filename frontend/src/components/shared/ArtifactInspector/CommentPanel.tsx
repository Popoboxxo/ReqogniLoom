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
  /**
   * The backing generic **Artifact UUID** (`Requirement.artifact_id`,
   * `ArchitectureElement.artifact_id`, …) — the only id space
   * `GET|POST /artifacts/<artifact_id>/comments/` accepts. Passing the
   * domain-entity id here 404s for every kind (#1763), which is why this is a
   * separately typed prop and not derived from the shell's `entityId`.
   *
   * Optional because not every kind's REST response publishes the backing
   * Artifact id yet (Adr/Risk/Issue/MainGoal — see `RightSidebar` docs). When
   * it is absent the panel renders an explicit "not available" state instead
   * of firing a request that is guaranteed to 404.
   */
  artifactId?: string;
}

export function CommentPanel({ kind, artifactId }: CommentPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Comment | null>(null);

  // No Artifact UUID → no request at all. `load` stays a no-op so the
  // mount effect cannot leak a 404 into the panel's error state; it does drop
  // any rows it still holds from a previously inspected artifact.
  const load = useCallback(async (): Promise<void> => {
    if (!artifactId) {
      // Function updater, not `setComments([])`: an already-empty list must
      // keep its identity. The effect below also re-runs whenever `t` changes
      // identity, and a fresh `[]` on every run would re-render forever.
      setComments((prev) => (prev.length === 0 ? prev : []));
      setError(null);
      return;
    }
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
    if (!text || !artifactId) return;
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

      {!artifactId ? (
        // No Artifact UUID for this kind (see the prop doc): say so instead of
        // rendering a load error from a request that cannot succeed (#1763).
        <p className={styles.empty} data-testid="comment-panel-unavailable">
          {t(
            "comments.unavailable",
            "Comments are not available for this artifact yet."
          )}
        </p>
      ) : (
        <>
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
                        className={`btn-ghost ${styles.actionBtn}`}
                        disabled={busy}
                        onClick={() => void handleResolve(comment)}
                        data-testid={`comment-panel-resolve-${comment.id}`}
                      >
                        {t("comments.resolve", "Resolve")}
                      </button>
                    )}
                    <button
                      type="button"
                      className={`btn-danger ${styles.actionBtn}`}
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
              className={`btn-primary ${styles.actionBtn}`}
              disabled={busy || draft.trim().length === 0}
              onClick={() => void handleSubmit()}
              data-testid="comment-panel-submit"
            >
              {t("comments.submit", "Comment")}
            </button>
          </div>
        </>
      )}

      {artifactId && pendingDelete && (
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
