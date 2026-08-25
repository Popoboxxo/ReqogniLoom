/**
 * ARCH-L1-001 ReactFrontend — System Health Dialog (admin-only).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings admin tab)
 *
 * Modal showing a live snapshot of runtime infrastructure (database,
 * redis, celery worker/beat, MCP server, LLM provider config) plus the
 * most recent audit-log entries. Fetched once when the dialog opens (and
 * again on explicit refresh) via ``adminOpsApi.getSystemHealth()``.
 *
 * Modal chrome mirrors NavigationShell's CreateWorkspaceModal pattern
 * (overlay/dialog/header/body/footer + backdrop-click-to-close).
 */

import type { CSSProperties } from "react";
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

const STATUS_COLORS: Record<SystemHealthStatus, string> = {
  ok: "var(--color-success)",
  degraded: "var(--color-warning)",
  down: "var(--color-danger)",
  unknown: "var(--color-text-muted)",
};

// ---------------------------------------------------------------------------
// Styles — the overlay/panel/header chrome now comes from <Dialog>; only the
// body/footer/content styles specific to this dialog remain here.
// ---------------------------------------------------------------------------

const bodyStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-4)",
};

const versionLineStyle: CSSProperties = {
  fontSize: "var(--font-size-xs)",
  color: "var(--color-text-muted)",
};

const footerStyle: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "var(--space-2)",
};

const sectionHeadingStyle: CSSProperties = {
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  margin: "0 0 var(--space-2) 0",
};

const componentRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "var(--space-2) var(--space-3)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
};

const secondaryButtonStyle: CSSProperties = {
  background: "transparent",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  padding: "var(--space-2) var(--space-4)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};

const primaryButtonStyle: CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "var(--space-2) var(--space-4)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
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

  // Prevent background scroll while the dialog is open (same as CreateWorkspaceModal).
  useEffect(() => {
    if (!isOpen) return;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = "";
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
        <div style={footerStyle}>
          <button
            type="button"
            data-testid="system-health-refresh"
            onClick={() => void load()}
            disabled={isLoading}
            style={{ ...secondaryButtonStyle, opacity: isLoading ? 0.6 : 1 }}
          >
            {isLoading ? "…" : t("systemHealth.refresh", "Refresh")}
          </button>
          <button
            type="button"
            data-testid="system-health-done"
            onClick={onClose}
            style={primaryButtonStyle}
          >
            {t("common.close", "Close")}
          </button>
        </div>
      }
    >
      <div style={bodyStyle}>
        {(versionInfo || versionFailed) && (
          <span data-testid="system-health-version" style={versionLineStyle}>
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
            <p role="status" style={{ color: "var(--color-text-muted)", margin: 0 }}>
              {t("loading", "Loading...")}
            </p>
          )}

          {error && (
            <p
              role="alert"
              data-testid="system-health-error"
              style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", margin: 0 }}
            >
              {error}
            </p>
          )}

          {snapshot && (
            <>
              <section>
                <h3 style={sectionHeadingStyle}>
                  {t("systemHealth.components", "Components")}
                </h3>
                <ul
                  data-testid="system-health-components"
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-2)",
                  }}
                >
                  {snapshot.components.map((component) => (
                    <li
                      key={component.name}
                      data-testid={`system-health-component-${component.name}`}
                      style={componentRowStyle}
                    >
                      <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                        <span
                          aria-hidden="true"
                          style={{
                            width: "0.6rem",
                            height: "0.6rem",
                            borderRadius: "50%",
                            background: STATUS_COLORS[component.status],
                            display: "inline-block",
                            flexShrink: 0,
                          }}
                        />
                        <span style={{ fontWeight: 600, color: "var(--color-text)" }}>
                          {t(`systemHealth.componentNames.${component.name}`, component.name)}
                        </span>
                        <span
                          style={{
                            fontSize: "var(--font-size-xs)",
                            color: "var(--color-text-muted)",
                          }}
                        >
                          {component.detail}
                        </span>
                      </span>
                      <span className={styles.statusCluster}>
                        <span
                          data-testid={`system-health-status-${component.name}`}
                          style={{
                            fontSize: "var(--font-size-xs)",
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                            color: STATUS_COLORS[component.status],
                          }}
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
                <h3 style={sectionHeadingStyle}>
                  {t("systemHealth.recentEvents", "Recent Audit Events")}
                </h3>
                {snapshot.recent_events.length === 0 ? (
                  <p
                    data-testid="system-health-events-empty"
                    style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)", margin: 0 }}
                  >
                    {t("systemHealth.noEvents", "No recent events.")}
                  </p>
                ) : (
                  <ul
                    data-testid="system-health-events"
                    style={{
                      listStyle: "none",
                      padding: 0,
                      margin: 0,
                      maxHeight: "240px",
                      overflowY: "auto",
                      display: "flex",
                      flexDirection: "column",
                      border: "1px solid var(--color-border)",
                      borderRadius: "var(--radius-md)",
                    }}
                  >
                    {snapshot.recent_events.map((event) => (
                      <li
                        key={event.id}
                        data-testid={`system-health-event-${event.id}`}
                        style={{
                          fontSize: "var(--font-size-xs)",
                          padding: "var(--space-2) var(--space-3)",
                          borderBottom: "1px solid var(--color-border)",
                          color: "var(--color-text)",
                        }}
                      >
                        <span style={{ fontFamily: "monospace", color: "var(--color-text-muted)" }}>
                          {formatDate(event.timestamp)}
                        </span>
                        {" — "}
                        <strong>{event.actor}</strong>{" "}
                        <span style={{ color: "var(--color-text-muted)" }}>[{event.source}]</span>{" "}
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
