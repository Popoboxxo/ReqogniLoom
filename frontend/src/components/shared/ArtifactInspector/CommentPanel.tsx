/**
 * CommentPanel — comments on the currently inspected artifact.
 *
 * Menschen-im-System spec §4. Mounted as the Comments tab of the shared
 * shell (#1762); `variant="panel"` is the legacy stacked form kept for the
 * panel's own contract tests.
 *
 * Comments are never edited — create, resolve, delete only.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { commentsApi, type Comment } from "../../../api/comments";
import { useInspectorAnnouncer, useInspectorCounts } from "./InspectorLiveRegions";
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
   * Artifact id yet (Adr/Risk/Issue/MainGoal — see the shell's docs). When
   * it is absent the panel renders an explicit "not available" state instead
   * of firing a request that is guaranteed to 404.
   */
  artifactId?: string;
  /**
   * `"panel"` is the legacy stacked form with its own `h3`
   * heading and its own `role="alert"` banner. `"tab"` is the tabbed shell
   * (#1762): the tab label names the area and the shell owns the single alert
   * region, so the panel renders neither.
   */
  variant?: "panel" | "tab";
}

export function CommentPanel({
  kind,
  artifactId,
  variant = "panel",
}: CommentPanelProps): JSX.Element {
  const { t } = useTranslation();
  // Async callbacks must not depend on `t`'s identity: some hosts (and test
  // harnesses) return a fresh function per render, which would turn the
  // fetch effect into a loop. The ref keeps the latest `t` without re-keying
  // the callback.
  const tRef = useRef(t);
  tRef.current = t;
  const announcer = useInspectorAnnouncer();
  const reportCount = useInspectorCounts()?.reportCount;
  const isTab = variant === "tab";
  // A retry is its own announcement, never an extra `commentsLoaded`
  // (spec §5.3 rule 1).
  const retryingRef = useRef(false);
  // Late fetch after unmount must not announce (see VersionPanel).
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Comment | null>(null);

  const announceLoad = useCallback(
    (list: Comment[]): void => {
      const open = list.filter((comment) => !comment.resolved).length;
      reportCount?.("comments", open);
      if (!isTab || !announcer) return;
      const wasRetry = retryingRef.current;
      retryingRef.current = false;
      const panelLabel = tRef.current("comments.heading", "Comments");
      announcer.polite(
        wasRetry
          ? tRef.current("sidebar.inspector.live.retrySucceeded", {
              panel: panelLabel,
              defaultValue: "{{panel}} loaded.",
            })
          : tRef.current("sidebar.inspector.live.commentsLoaded", {
              count: list.length,
              open,
              defaultValue: "{{count}} comments, {{open}} open.",
            }),
      );
    },
    [announcer, isTab, reportCount],
  );

  // No Artifact UUID → no request at all. `load` stays a no-op so the
  // mount effect cannot leak a 404 into the panel's error state; it does drop
  // any rows it still holds from a previously inspected artifact.
  const load = useCallback(async (options?: { announce?: boolean }): Promise<void> => {
    if (!artifactId) {
      // Function updater, not `setComments([])`: an already-empty list must
      // keep its identity. The effect below also re-runs whenever `t` changes
      // identity, and a fresh `[]` on every run would re-render forever.
      setComments((prev) => (prev.length === 0 ? prev : []));
      setError(null);
      return;
    }
    try {
      const list = await commentsApi.list(artifactId);
      if (!mountedRef.current) return;
      setComments(list);
      setError(null);
      if (options?.announce !== false) announceLoad(list);
    } catch {
      if (!mountedRef.current) return;
      setError(tRef.current("comments.loadFailed", "Could not load comments."));
      if (isTab && announcer) {
        const wasRetry = retryingRef.current;
        retryingRef.current = false;
        const panelLabel = tRef.current("comments.heading", "Comments");
        announcer.alert(
          wasRetry
            ? tRef.current("sidebar.inspector.live.retryFailed", {
                panel: panelLabel,
                defaultValue: "{{panel}} still unavailable.",
              })
            : tRef.current("sidebar.inspector.error.comments", {
                panel: panelLabel,
                defaultValue: "{{panel}} could not be loaded. Try again.",
              }),
        );
      }
    }
  }, [artifactId, announceLoad, isTab, announcer]);

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
      // The action announcement ("Comment created.") is the one announcement
      // of this interaction — the reload must not add `commentsLoaded`
      // (spec §5.3 rule 1).
      await load({ announce: false });
      announcer?.polite(t("sidebar.inspector.live.commentCreated"));
    } catch {
      setError(t("comments.createFailed"));
      announcer?.alert(
        t("sidebar.inspector.error.comments", {
          panel: t("comments.heading"),
          defaultValue: "{{panel}} could not be loaded. Try again.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }, [artifactId, draft, load, t, announcer]);

  const handleResolve = useCallback(
    async (comment: Comment): Promise<void> => {
      setBusy(true);
      try {
        await commentsApi.resolve(comment.id);
        await load({ announce: false });
        announcer?.polite(
          t("sidebar.inspector.live.commentResolved"),
        );
      } catch {
        setError(t("comments.resolveFailed"));
      } finally {
        setBusy(false);
      }
    },
    [load, t, announcer]
  );

  const handleDeleteConfirmed = useCallback(async (): Promise<void> => {
    if (!pendingDelete) return;
    setBusy(true);
    try {
      await commentsApi.remove(pendingDelete.id);
      // Close on the success path too — a dialog left open after a completed
      // action is the #669/#670 failure mode.
      setPendingDelete(null);
      await load({ announce: false });
      announcer?.polite(t("sidebar.inspector.live.commentDeleted"));
    } catch {
      setError(t("comments.deleteFailed"));
      setPendingDelete(null);
    } finally {
      setBusy(false);
    }
  }, [load, pendingDelete, t, announcer]);

  return (
    <section
      className={styles.panel}
      aria-label={t("comments.ariaLabel")}
      data-testid="comment-panel"
      data-artifact-kind={kind}
    >
      {!isTab && <h3 className={styles.heading}>{t("comments.heading")}</h3>}

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
            <div
              className={styles.error}
              // Tab form: the shell's single alert region announces the
              // failure; the visible text stays here so the message is never
              // only spoken (spec §4.3/§5.3 rule 4).
              role={isTab ? undefined : "alert"}
              data-testid="comment-panel-error"
            >
              <span>{error}</span>
              <button
                type="button"
                className="btn-secondary"
                onClick={(): void => {
                  retryingRef.current = true;
                  void load();
                }}
                data-testid="comment-panel-retry"
              >
                {t("actions.retry")}
              </button>
            </div>
          )}

          {comments.length === 0 ? (
            <p className={styles.empty} data-testid="comment-panel-empty">
              {t("comments.empty")}
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
                    <span>{comment.authorDisplay ?? t("comments.unknownAuthor")}</span>
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
                        {t("comments.resolve")}
                      </button>
                    )}
                    <button
                      type="button"
                      className={`btn-danger ${styles.actionBtn}`}
                      disabled={busy}
                      onClick={() => setPendingDelete(comment)}
                      data-testid={`comment-panel-delete-${comment.id}`}
                    >
                      {t("comments.delete")}
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
              placeholder={t("comments.placeholder")}
              aria-label={t("comments.inputLabel")}
              data-testid="comment-panel-input"
            />
            <button
              type="button"
              className={`btn-primary ${styles.actionBtn}`}
              disabled={busy || draft.trim().length === 0}
              onClick={() => void handleSubmit()}
              data-testid="comment-panel-submit"
            >
              {t("comments.submit")}
            </button>
          </div>
        </>
      )}

      {artifactId && pendingDelete && (
        <ConfirmDialog
          title={t("comments.deleteTitle")}
          message={t("comments.deleteMessage")}
          confirmLabel={t("comments.delete")}
          cancelLabel={t("actions.cancel")}
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
