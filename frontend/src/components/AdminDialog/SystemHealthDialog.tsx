/**
 * ARCH-L1-001 ReactFrontend — System Health Dialog (admin-only).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings admin tab)
 *
 * Modal showing a live snapshot of runtime infrastructure (database,
 * redis, celery worker/beat, MCP server, LLM provider config, memory
 * embedding provider, memory backend) plus the most recent audit-log
 * entries. Fetched once when the dialog opens (and again on explicit
 * refresh) via ``adminOpsApi.getSystemHealth()``.
 *
 * Modal chrome mirrors NavigationShell's CreateWorkspaceModal pattern
 * (overlay/dialog/header/body/footer + backdrop-click-to-close).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  adminOpsApi,
  type SystemHealthSnapshot,
  type SystemHealthStatus,
} from "../../api/admin-ops";
import { versionApi, type VersionInfo } from "../../api/version";
import { Dialog } from "../shared/Dialog";
import styles from "./SystemHealthDialog.module.css";

export interface SystemHealthDialogProps {
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Called when the user closes the dialog. */
  onClose: () => void;
}

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Issue #876 (Etappe 5): the per-status fg colour moved onto one CSS class per
// status (composed at the call site) for both the dot and the status label —
// see SystemHealthDialog.module.css.
const STATUS_DOT_CLASS: Record<SystemHealthStatus, string> = {
  ok: styles.statusDotOk,
  degraded: styles.statusDotDegraded,
  down: styles.statusDotDown,
  unknown: styles.statusDotUnknown,
};

const STATUS_TEXT_CLASS: Record<SystemHealthStatus, string> = {
  ok: styles.statusTextOk,
  degraded: styles.statusTextDegraded,
  down: styles.statusTextDown,
  unknown: styles.statusTextUnknown,
};

/**
 * Admin-only system health dialog — live component status + recent
 * audit-log entries. The trigger button lives in WorkspaceSettings'
 * "admin" tab, gated by the same `isAdmin` check as BackupRestoreSection.
 */
export function SystemHealthDialog({
  isOpen,
  onClose,
}: SystemHealthDialogProps): JSX.Element | null {
  const { t } = useTranslation();

  const [snapshot, setSnapshot] = useState<SystemHealthSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [versionFailed, setVersionFailed] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await adminOpsApi.getSystemHealth();
      setSnapshot(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch once whenever the dialog opens.
  useEffect(() => {
    if (!isOpen) return;
    void load();
  }, [isOpen, load]);

  // Fetch the deployed build/commit info independently of the health snapshot
  // (public, unauthenticated endpoint — meant to work even when other
  // components are degraded). Non-critical: fail silently, dialog still works.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setVersionInfo(null);
    setVersionFailed(false);
    void versionApi
      .getVersion()
      .then((info) => {
        if (!cancelled) setVersionInfo(info);
      })
      .catch(() => {
        // Non-critical build indicator — surface a terse "unavailable"
        // marker instead of crashing the dialog.
        if (!cancelled) setVersionFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  // UI-41 (systemaudit 2026-08-27): this used to *also* set/reset
  // `body.style.overflow` itself, duplicating the shared `<Dialog>`'s own
  // scroll-lock below. `<Dialog>` correctly saves and restores whatever
  // overflow value was present before it mounted (so it never clobbers a
  // lock some other, already-open view had set) — but effect cleanups run
  // parent-after-child on unmount, so this component's unconditional
  // `overflow = ""` cleanup ran *after* Dialog's cleanup and blindly
  // overwrote whatever Dialog had correctly restored. Only the scrollbar-
  // width compensation is genuinely this component's own concern (Dialog's
  // lock does not compensate for the disappearing scrollbar); the
  // hide/restore of `overflow` itself is entirely `<Dialog>`'s job now.
  useEffect(() => {
    if (!isOpen) return;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.paddingRight = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <Dialog
      title={t("systemHealth.title", "System Health")}
      onClose={onClose}
      size="md"
      testId="system-health-dialog"
      footer={
        <>
          {/* issue #954: admin-dialog footer buttons now come from the shared
              `.btn-*` system instead of a local inline style, so they match
              every entity dialog's buttons (height/radius via tokens). */}
          <button
            type="button"
            className="btn-secondary"
            data-testid="system-health-refresh"
            onClick={() => void load()}
            disabled={isLoading}
          >
            {isLoading ? "…" : t("systemHealth.refresh", "Refresh")}
          </button>
          <button
            type="button"
            className="btn-primary"
            data-testid="system-health-done"
            onClick={onClose}
          >
            {t("common.close", "Close")}
          </button>
        </>
      }
    >
      <div className={styles.body}>
        {(versionInfo || versionFailed) && (
          <span data-testid="system-health-version" className={styles.versionLine}>
            {versionInfo
              ? (versionInfo.app_version && versionInfo.app_version !== "unknown"
                  ? `${t("systemHealth.appVersion", {
                      version: versionInfo.app_version,
                      defaultValue: `v${versionInfo.app_version}`,
                    })} · `
                  : "") +
                t("systemHealth.version", {
                  sha: versionInfo.commit_short,
                  defaultValue: `Version: ${versionInfo.commit_short}`,
                })
              : t("systemHealth.versionUnavailable", "Version: unavailable")}
          </span>
        )}

        {isLoading && !snapshot && (
            <p role="status" className={styles.loadingText}>
              {t("loading", "Loading...")}
            </p>
          )}

          {error && (
            <p
              role="alert"
              data-testid="system-health-error"
              className={styles.errorText}
            >
              {error}
            </p>
          )}

          {snapshot && (
            <>
              <section>
                <h3 className={styles.sectionHeading}>
                  {t("systemHealth.components", "Components")}
                </h3>
                <ul
                  data-testid="system-health-components"
                  className={styles.componentList}
                >
                  {snapshot.components.map((component) => (
                    <li
                      key={component.name}
                      data-testid={`system-health-component-${component.name}`}
                      className={styles.componentRow}
                    >
                      <span className={styles.componentMain}>
                        <span
                          aria-hidden="true"
                          className={styles.statusDot + ' ' + STATUS_DOT_CLASS[component.status]}
                        />
                        <span className={styles.componentName}>
                          {t(`systemHealth.componentNames.${component.name}`, component.name)}
                        </span>
                        <span className={styles.componentDetail}>
                          {component.detail}
                        </span>
                      </span>
                      <span className={styles.statusCluster}>
                        <span
                          data-testid={`system-health-status-${component.name}`}
                          className={styles.statusText + ' ' + STATUS_TEXT_CLASS[component.status]}
                        >
                          {t(`systemHealth.status.${component.status}`, component.status)}
                        </span>
                        {component.status === "unknown" && (
                          <span
                            data-testid={`system-health-unknown-hint-${component.name}`}
                            role="img"
                            aria-label={t(
                              "systemHealth.unknownExplanationLabel",
                              "Why is this unknown?"
                            )}
                            title={t(
                              "systemHealth.unknownExplanation",
                              "This check cannot verify process liveness from this endpoint by design — it does not mean the component is down."
                            )}
                            className={styles.unknownHint}
                          >
                            ?
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <h3 className={styles.sectionHeading}>
                  {t("systemHealth.recentEvents", "Recent Audit Events")}
                </h3>
                {snapshot.recent_events.length === 0 ? (
                  <p
                    data-testid="system-health-events-empty"
                    className={styles.eventsEmpty}
                  >
                    {t("systemHealth.noEvents", "No recent events.")}
                  </p>
                ) : (
                  <ul
                    data-testid="system-health-events"
                    className={styles.eventsList}
                  >
                    {snapshot.recent_events.map((event) => (
                      <li
                        key={event.id}
                        data-testid={`system-health-event-${event.id}`}
                        className={styles.eventItem}
                      >
                        <span className={styles.eventTimestamp}>
                          {formatDate(event.timestamp)}
                        </span>
                        {" — "}
                        <strong>{event.actor}</strong>{" "}
                        <span className={styles.eventSource}>[{event.source}]</span>{" "}
                        {event.op} {event.entity_type}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
      </div>
    </Dialog>
  );
}
