/**
 * ARCH-L1-001 ReactFrontend — MemorySection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Two self-service surfaces over the caller's OWN data:
 *
 *   * Plan A T-A1-7: the personal memory switches
 *     (`GET/PUT /memory/me/settings/`) — an `enabled` toggle plus the
 *     per-AI-activity slot list. `?workspace_id=` adds the workspace policy
 *     hint (`effective.opt_out_allowed`); when that is `false` the workspace
 *     does not honour the opt-out, and the hint says so. The stored switch is
 *     never silently rewritten to match (ENT-A7 = B).
 *   * RFC #1002 PR D: the authenticated user's OWN user-scoped facts
 *     (`GET /memory/me/?include_entries=true`) with a per-row forget action, on
 *     top of the existing "delete everything" self-service control. Never
 *     touches workspace/artifact memory, which is team-owned (see
 *     `memory/policy.py`).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractApiErrorMessage } from "../../api/client";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import {
  memoryMeSettingsApi,
  type MemorySelfServiceSettingsUpdate,
} from "../../api/memory-me-settings";
import { memorySettingsApi, type MemorySlot } from "../../api/memory-settings";
import { useOptionalWorkspace } from "../../context/WorkspaceContext";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { formatMemoryDate } from "../Memory/memory-format";
import styles from "./MemorySection.module.css";

const PAGE_SIZE = 100;

/**
 * `data-testid` segment for one slot: `interview.chat_turn` →
 * `interview-chat-turn`, `testcase_derive` → `testcase-derive`.
 */
function slotTestIdSegment(name: string): string {
  return name.replace(/[._\s]+/g, "-").toLowerCase();
}

export function MemorySection(): JSX.Element {
  const { t } = useTranslation();
  // Non-throwing reader: the profile is reachable without a workspace, and
  // then there is simply no slot catalogue and no workspace policy hint.
  const workspace = useOptionalWorkspace();
  const activeWorkspaceId = workspace?.activeWorkspace?.id ?? null;

  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [entryCount, setEntryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [pendingForget, setPendingForget] = useState<MemoryEntry | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // --- own memory switches (Plan A T-A1-4/T-A1-7) -------------------------
  const [selfEnabled, setSelfEnabled] = useState(true);
  const [selfDisabledSlots, setSelfDisabledSlots] = useState<string[]>([]);
  const [optOutBlocked, setOptOutBlocked] = useState(false);
  const [availableSlots, setAvailableSlots] = useState<MemorySlot[]>([]);
  const [isLoadingSettings, setIsLoadingSettings] = useState(true);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const overview = await memoryApi.getSelfOverview({
        includeEntries: true,
        pageSize: PAGE_SIZE,
      });
      setEntries(overview.entries ?? []);
      setEntryCount(overview.entry_count);
      setLastUpdated(overview.last_updated_at);
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht geladen werden.")
      );
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  const loadSettings = useCallback(async (): Promise<void> => {
    setIsLoadingSettings(true);
    setSettingsError(null);
    try {
      const settings = await memoryMeSettingsApi.get(activeWorkspaceId ?? undefined);
      setSelfEnabled(settings.enabled);
      setSelfDisabledSlots(settings.disabled_slots ?? []);
      setOptOutBlocked(settings.effective?.opt_out_allowed === false);
    } catch (err: unknown) {
      setSettingsError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht geladen werden.")
      );
    } finally {
      setIsLoadingSettings(false);
    }
    if (!activeWorkspaceId) {
      setAvailableSlots([]);
      return;
    }
    // The slot catalogue is owned by the workspace surface (the self-service
    // payload carries none). A failed read leaves the switches usable and only
    // drops the per-slot list — never the whole section.
    try {
      const workspaceSettings = await memorySettingsApi.get(activeWorkspaceId);
      setAvailableSlots(workspaceSettings.available_slots ?? []);
    } catch {
      setAvailableSlots([]);
    }
  }, [activeWorkspaceId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const saveSettings = async (
    update: MemorySelfServiceSettingsUpdate,
    rollback: () => void
  ): Promise<void> => {
    setIsSavingSettings(true);
    setSettingsError(null);
    try {
      const updated = await memoryMeSettingsApi.update(update);
      setSelfEnabled(updated.enabled);
      if (updated.disabled_slots) setSelfDisabledSlots(updated.disabled_slots);
    } catch (err: unknown) {
      rollback();
      setSettingsError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht gespeichert werden.")
      );
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleSelfEnabledToggle = (next: boolean): void => {
    setSelfEnabled(next);
    void saveSettings({ enabled: next }, () => setSelfEnabled(!next));
  };

  const handleSlotToggle = (slot: MemorySlot, nextOn: boolean): void => {
    // A HARD_OFF slot is never writable — the backend rejects it.
    if (slot.hard_off) return;
    const previous = selfDisabledSlots;
    const next = nextOn
      ? previous.filter((name) => name !== slot.name)
      : [...previous, slot.name];
    setSelfDisabledSlots(next);
    void saveSettings({ disabled_slots: next }, () => setSelfDisabledSlots(previous));
  };

  const handleDelete = useCallback(async (): Promise<void> => {
    setIsDeleting(true);
    setError(null);
    try {
      await memoryApi.deleteSelfMemory();
      setEntries([]);
      setEntryCount(0);
      setLastUpdated(null);
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht gelöscht werden.")
      );
    } finally {
      setIsDeleting(false);
    }
  }, [t]);

  const handleForget = useCallback(async (): Promise<void> => {
    if (!pendingForget) return;
    const entryId = pendingForget.entry_id;
    setPendingForget(null);
    setBusyId(entryId);
    setError(null);
    try {
      await memoryApi.forgetEntry(entryId);
      await load();
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.forgetError", "Eintrag konnte nicht gelöscht werden.")
      );
    } finally {
      setBusyId(null);
    }
  }, [pendingForget, load, t]);

  return (
    <section className={styles.section} data-testid="memory-self-service-section">
      <h2 className={styles.heading}>{t("memorySelfService.title", "Mein Memory")}</h2>
      <p className={styles.hint}>
        {t(
          "memorySelfService.hint",
          "Das KI-Langzeitgedächtnis speichert Kontext über dich, um Antworten zu personalisieren. Du kannst deine eigenen Einträge jederzeit vollständig löschen."
        )}
      </p>

      {settingsError && (
        <p role="alert" data-testid="memory-self-service-settings-error" className={styles.error}>
          {settingsError}
        </p>
      )}

      {isLoadingSettings ? (
        <div className={styles.card}>
          <p
            role="status"
            data-testid="memory-self-service-settings-loading"
            className={styles.loadingText}
          >
            {t("loading", "Loading...")}
          </p>
        </div>
      ) : settingsError ? null : (
        <div className={styles.card} data-testid="memory-self-service-settings">
          <label className={styles.toggleLabel} data-disabled={isSavingSettings}>
            <input
              type="checkbox"
              data-testid="memory-self-service-enabled-toggle"
              checked={selfEnabled}
              disabled={isSavingSettings}
              onChange={(e) => handleSelfEnabledToggle(e.target.checked)}
            />
            {t("memorySelfService.enabledLabel", "Memory for my AI activities")}
          </label>

          {optOutBlocked && (
            <p data-testid="memory-self-service-optout-blocked-hint" className={styles.hint}>
              {t(
                "memorySelfService.optOutBlocked",
                "Not honoured for workspace memory in this workspace — your personal memory stays off."
              )}
            </p>
          )}

          {availableSlots.length > 0 && (
            <fieldset
              className={styles.slotGroup}
              data-testid="memory-self-service-disabled-slots"
            >
              <legend className={styles.slotLegend}>
                {t("memorySelfService.enabledLabel", "Memory for my AI activities")}
              </legend>
              {availableSlots.map((slot) => {
                const hintId = `memory-self-service-hard-off-hint-${slotTestIdSegment(
                  slot.name
                )}`;
                return (
                  // The hint sits *outside* the label so it is the checkbox's
                  // description (aria-describedby), not part of its accessible
                  // name.
                  <div key={slot.name} className={styles.slotRow}>
                    <label
                      className={styles.toggleLabel}
                      data-disabled={isSavingSettings || slot.hard_off}
                    >
                      <input
                        type="checkbox"
                        data-testid={`memory-self-service-slot-toggle-${slotTestIdSegment(
                          slot.name
                        )}`}
                        checked={!slot.hard_off && !selfDisabledSlots.includes(slot.name)}
                        disabled={isSavingSettings || slot.hard_off}
                        aria-describedby={slot.hard_off ? hintId : undefined}
                        onChange={(e) => handleSlotToggle(slot, e.target.checked)}
                      />
                      <span>{t(`memorySlots.${slot.name}`, slot.name)}</span>
                    </label>
                    {slot.hard_off && (
                      <span id={hintId} className={styles.inlineHint}>
                        {t("settings.memory.hardOffHint", "never uses memory")}
                      </span>
                    )}
                  </div>
                );
              })}
            </fieldset>
          )}
        </div>
      )}

      {error && (
        <p role="alert" data-testid="memory-self-service-error" className={styles.error}>
          {error}
        </p>
      )}

      {isLoading ? (
        <div className={styles.card}>
          <p role="status" data-testid="memory-self-service-loading" className={styles.loadingText}>
            {t("loading", "Loading...")}
          </p>
        </div>
      ) : (
        <div className={styles.card}>
          <div className={styles.headerRow}>
            <div>
              <p className={styles.metaLine}>
                {t("memorySelfService.countLabel", "Gespeicherte Einträge")}:{" "}
                <span data-testid="memory-self-service-count" className={styles.countValue}>
                  {entryCount}
                </span>
              </p>
              <p className={styles.metaLine}>
                {t("memorySelfService.lastUpdatedLabel", "Zuletzt aktualisiert")}:{" "}
                <span data-testid="memory-self-service-last-updated">
                  {formatMemoryDate(lastUpdated)}
                </span>
              </p>
              {entries.length === 0 && (
                <p data-testid="memory-self-service-empty" className={styles.empty}>
                  {t("memorySelfService.empty", "Noch keine Memory-Einträge vorhanden.")}
                </p>
              )}
            </div>
            <button
              type="button"
              data-testid="memory-self-service-delete-btn"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={entryCount === 0 || isDeleting}
              className={`btn-danger ${styles.deleteBtn}`}
            >
              {isDeleting ? "…" : t("memorySelfService.deleteButton", "Mein Memory löschen")}
            </button>
          </div>

          {entries.length > 0 && (
            <ul className={styles.list} data-testid="memory-self-service-list">
              {entries.map((entry) => (
                <li
                  key={entry.entry_id}
                  className={styles.listRow}
                  data-testid={`memory-self-service-row-${entry.entry_id}`}
                >
                  <div className={styles.listRowMain}>
                    <p className={styles.listContent}>{entry.content}</p>
                    <span className={styles.metaLine}>
                      {formatMemoryDate(entry.created_at)}
                    </span>
                  </div>
                  <button
                    type="button"
                    data-testid={`memory-self-service-forget-${entry.entry_id}`}
                    onClick={() => setPendingForget(entry)}
                    disabled={busyId === entry.entry_id}
                    className={`btn-danger ${styles.forgetBtn}`}
                  >
                    {t("memorySelfService.forgetButton", "Vergessen")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t("memorySelfService.deleteButton", "Mein Memory löschen")}
          message={t(
            "memorySelfService.deleteConfirm",
            "Delete ALL of your own memory entries? This removes everything the AI has remembered about you and cannot be undone."
          )}
          confirmLabel={t("memorySelfService.deleteButton", "Mein Memory löschen")}
          onConfirm={() => {
            setShowDeleteConfirm(false);
            void handleDelete();
          }}
          onCancel={() => setShowDeleteConfirm(false)}
          testId="memory-self-service-delete-confirm"
        />
      )}

      {pendingForget && (
        <ConfirmDialog
          title={t("memorySelfService.forgetButton", "Vergessen")}
          message={t(
            "memorySelfService.forgetConfirm",
            "Diesen Eintrag endgültig löschen? Das kann nicht rückgängig gemacht werden."
          )}
          confirmLabel={t("memorySelfService.forgetButton", "Vergessen")}
          onConfirm={() => void handleForget()}
          onCancel={() => setPendingForget(null)}
          testId="memory-self-service-forget-confirm"
        />
      )}
    </section>
  );
}
