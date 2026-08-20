/**
 * ARCH-L1-001 ReactFrontend — Workspace Context Graph settings section
 * (Issue #377, Task 9).
 *
 * Per-workspace on/off toggle for the event-sourced semantic context graph
 * (derived "shares-term" edges etc., additive to the hard TraceLink graph —
 * see backend/context_graph/models.py's module docstring), a read-only
 * operational status display (last_projected_at/node_count/edge_count/
 * last_error), and a manual "Rebuild now" button.
 *
 * `schedule_enabled`/`refresh_interval_minutes` exist on the backend model
 * but are deliberately NOT surfaced here — they are unused until Folge-Issue
 * B (cron scheduling), and shipping a UI control for a setting nothing reads
 * yet would be misleading (Task 9 spec).
 *
 * Styled via a co-located CSS Module, not inline style objects — matches
 * this codebase's UI-concept ratchet direction for new components
 * (src/test/ui-ratchet.test.ts).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  contextGraphSettingsApi,
  type ContextGraphSettings,
} from "../../api/context-graph-settings";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";
import styles from "./ContextGraphSettingsSection.module.css";

interface Props {
  workspaceId: UUID;
}

export function ContextGraphSettingsSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<ContextGraphSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  const [rebuildQueued, setRebuildQueued] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    contextGraphSettingsApi
      .get(workspaceId)
      .then(setSettings)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [workspaceId]);

  const handleToggle = async (nextEnabled: boolean): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await contextGraphSettingsApi.update(workspaceId, {
        enabled: nextEnabled,
        enabled_generators: settings?.enabled_generators?.length
          ? settings.enabled_generators
          : ["glossary"],
      });
      setSettings(updated);
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleRebuild = async (): Promise<void> => {
    setIsRebuilding(true);
    setError(null);
    setRebuildQueued(false);
    try {
      await contextGraphSettingsApi.rebuild(workspaceId);
      setRebuildQueued(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsRebuilding(false);
    }
  };

  if (isLoading || settings === null) {
    return (
      <section className={styles.section} data-testid="context-graph-settings-section">
        <h3 className={styles.heading}>
          {t("settings.contextGraph.title", "Semantic Context Graph")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="context-graph-settings-section">
      <h3 className={styles.heading}>
        {t("settings.contextGraph.title", "Semantic Context Graph")}
      </h3>
      <p className={styles.description}>
        {t(
          "settings.contextGraph.description",
          "Derives additional, machine-suggested relationships between artifacts (e.g. shared glossary terms) alongside the manually-authored trace links. Never counted as a trace link and never used in coverage/baseline calculations."
        )}
      </p>

      <label className={styles.toggleLabel} data-disabled={isSaving}>
        <input
          type="checkbox"
          data-testid="context-graph-enabled-toggle"
          checked={settings.enabled}
          disabled={isSaving}
          onChange={(e) => handleToggle(e.target.checked)}
        />
        {t("settings.contextGraph.enabled", "Enabled")}
      </label>

      <div className={styles.status} data-testid="context-graph-status">
        <div className={styles.statusRow}>
          <span>{t("settings.contextGraph.nodeCount", "Artifacts covered")}</span>
          <span data-testid="context-graph-node-count">{settings.node_count}</span>
        </div>
        <div className={styles.statusRow}>
          <span>{t("settings.contextGraph.edgeCount", "Derived edges")}</span>
          <span data-testid="context-graph-edge-count">{settings.edge_count}</span>
        </div>
        <div className={styles.statusRow}>
          <span>{t("settings.contextGraph.lastProjectedAt", "Last updated")}</span>
          <span data-testid="context-graph-last-projected-at">
            {settings.last_projected_at ?? t("settings.contextGraph.never", "Never")}
          </span>
        </div>
        {settings.last_error && (
          <div className={styles.lastError} data-testid="context-graph-last-error">
            {t("settings.contextGraph.lastError", "Last error")}: {settings.last_error}
          </div>
        )}
      </div>

      {error && (
        <p className={styles.error} data-testid="context-graph-settings-error">
          {error}
        </p>
      )}
      {savedOk && (
        <p className={styles.saved} data-testid="context-graph-settings-saved">
          {t("settings.saved", "Saved")}
        </p>
      )}
      {rebuildQueued && (
        <p className={styles.rebuildQueued} data-testid="context-graph-rebuild-queued">
          {t("settings.contextGraph.rebuildQueued", "Rebuild queued")}
        </p>
      )}

      <button
        type="button"
        className={styles.rebuildButton}
        data-testid="context-graph-rebuild-button"
        onClick={handleRebuild}
        disabled={isRebuilding}
      >
        {isRebuilding
          ? t("settings.contextGraph.rebuilding", "Rebuilding...")
          : t("settings.contextGraph.rebuildNow", "Rebuild now")}
      </button>
    </section>
  );
}
