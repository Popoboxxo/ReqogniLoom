/**
 * ARCH-L1-001 ReactFrontend — MemorySettingsSection (WorkspaceSettings,
 * "LLM & Prompts" tab). Spec 2026-08-24, Task 11; Plan A T-A1-7 slot switches.
 *
 * M-03: relocated from the "Allgemein" tab — what the AI is allowed to
 * remember is LLM configuration, not a general workspace property.
 *
 * Three controls, all server-enforced (``WorkspaceMemorySettingsView``):
 *
 *   * `enabled` — the feature toggle; editor+ may write it.
 *   * `disabled_slots` — the per-AI-activity switches (Plan A T-A1-3), admin
 *     only. A HARD_OFF slot (T-A1-1) can never receive memory, so it is
 *     rendered disabled with a hint instead of offering a value the writer
 *     rejects with "slot is hard-off".
 *   * `allow_user_opt_out` — whether members may switch memory off for
 *     themselves; admin only.
 *
 * Every save is a partial PUT: only the changed field is sent, so the other
 * levels/fields keep their stored value. A viewer/editor who lacks the role
 * gets the PUT's 403 surfaced via `error` and the optimistic change is rolled
 * back.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  memorySettingsApi,
  type MemorySettings,
  type MemorySettingsUpdate,
  type MemorySlot,
} from "../../api/memory-settings";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";
import styles from "./MemorySettingsSection.module.css";

interface Props {
  workspaceId: UUID;
}

/**
 * `data-testid` segment for one slot: `interview.chat_turn` →
 * `interview-chat-turn`, `testcase_derive` → `testcase-derive`.
 */
function slotTestIdSegment(name: string): string {
  return name.replace(/[._\s]+/g, "-").toLowerCase();
}

export function MemorySettingsSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(true);
  const [disabledSlots, setDisabledSlots] = useState<string[]>([]);
  const [allowUserOptOut, setAllowUserOptOut] = useState(true);
  const [availableSlots, setAvailableSlots] = useState<MemorySlot[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  // A failed GET means nothing on screen was ever read, so every control is
  // disabled until a read succeeds — otherwise one click would PUT a policy
  // value seeded from this component's defaults (allow_user_opt_out=true,
  // enabled=true) that nobody ever confirmed. A failed PUT is different: the
  // shown values *were* read, so it only reports and keeps the controls usable.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  const error = loadError ?? saveError;
  const controlsDisabled = isSaving || loadError !== null;
  const hardOffSlotCount = availableSlots.filter((slot) => slot.hard_off).length;

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);
    memorySettingsApi
      .get(workspaceId)
      .then((settings) => {
        if (cancelled) return;
        setEnabled(settings.enabled);
        setDisabledSlots(settings.disabled_slots ?? []);
        setAllowUserOptOut(settings.allow_user_opt_out ?? true);
        setAvailableSlots(settings.available_slots ?? []);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(extractErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  /**
   * Adopt a PUT's answer. The response is the stored state, never the merged
   * `effective_disabled_slots` (that one is display-only and must not leak
   * back into the editable level).
   */
  const applySettings = (updated: MemorySettings): void => {
    setEnabled(updated.enabled);
    if (updated.disabled_slots) setDisabledSlots(updated.disabled_slots);
    if (typeof updated.allow_user_opt_out === "boolean") {
      setAllowUserOptOut(updated.allow_user_opt_out);
    }
    if (updated.available_slots) setAvailableSlots(updated.available_slots);
  };

  const save = async (
    update: MemorySettingsUpdate,
    rollback: () => void
  ): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    setSavedOk(false);
    try {
      applySettings(await memorySettingsApi.update(workspaceId, update));
      setSavedOk(true);
    } catch (err) {
      rollback();
      setSaveError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggle = (next: boolean): void => {
    // Belt and braces next to `disabled`: a synthetic/programmatic click must
    // not write a value the failed GET never read.
    if (loadError !== null) return;
    setEnabled(next);
    void save({ enabled: next }, () => setEnabled(!next));
  };

  const handleSlotToggle = (slot: MemorySlot, nextOn: boolean): void => {
    // A HARD_OFF slot is never writable — the backend rejects it.
    if (slot.hard_off) return;
    if (loadError !== null) return;
    const previous = disabledSlots;
    const next = nextOn
      ? previous.filter((name) => name !== slot.name)
      : [...previous, slot.name];
    setDisabledSlots(next);
    void save({ disabled_slots: next }, () => setDisabledSlots(previous));
  };

  const handleAllowUserOptOut = (next: boolean): void => {
    if (loadError !== null) return;
    setAllowUserOptOut(next);
    void save({ allow_user_opt_out: next }, () => setAllowUserOptOut(!next));
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="memory-settings-section">
        <h3 className={styles.heading}>{t("settings.memory.title", "AI Memory")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="memory-settings-section">
      <h3 className={styles.heading}>{t("settings.memory.title", "AI Memory")}</h3>
      <p className={styles.description}>
        {t(
          "settings.memory.description",
          "Learns and recalls facts from interactions in this workspace to improve AI-assisted suggestions over time.",
        )}
      </p>

      <label className={styles.toggleLabel} data-disabled={controlsDisabled}>
        <input
          type="checkbox"
          data-testid="memory-settings-toggle"
          checked={enabled}
          disabled={controlsDisabled}
          onChange={(e) => handleToggle(e.target.checked)}
        />
        {t("settings.memory.enabled", "Enabled")}
      </label>

      {error && (
        <p role="alert" className={styles.error} data-testid="memory-settings-error">
          {error}
        </p>
      )}

      {/* Stays mounted when the GET failed (the alert above explains why every
          control is disabled) so the slot switches never disappear silently. */}
      <fieldset
        className={styles.slotGroup}
        data-testid="memory-settings-disabled-slots"
        disabled={controlsDisabled}
      >
        <legend className={styles.slotLegend}>
          {t("settings.memory.disabledSlots", "Memory per AI activity")}
        </legend>
        {hardOffSlotCount > 0 && (
          <p className={styles.hardOffSummary}>
            {t(
              "settings.memory.hardOffSummary",
              "AI activities that never use memory: {{total}}",
              { total: hardOffSlotCount }
            )}
          </p>
        )}
        {availableSlots.map((slot) => {
          const hintId = `memory-settings-hard-off-hint-${slotTestIdSegment(slot.name)}`;
          return (
            // The hint sits *outside* the label so it is the checkbox's
            // description (aria-describedby), not part of its accessible name.
            <div key={slot.name} className={styles.slotRow}>
              <label
                className={styles.toggleLabel}
                data-disabled={controlsDisabled || slot.hard_off}
              >
                <input
                  type="checkbox"
                  data-testid={`memory-settings-slot-toggle-${slotTestIdSegment(slot.name)}`}
                  checked={!slot.hard_off && !disabledSlots.includes(slot.name)}
                  disabled={controlsDisabled || slot.hard_off}
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

      <label className={styles.toggleLabel} data-disabled={controlsDisabled}>
        <input
          type="checkbox"
          data-testid="memory-settings-allow-user-opt-out"
          checked={allowUserOptOut}
          disabled={controlsDisabled}
          onChange={(e) => handleAllowUserOptOut(e.target.checked)}
        />
        {t("settings.memory.allowUserOptOut", "Users may opt out")}
      </label>

      {savedOk && (
        <p className={styles.saved} data-testid="memory-settings-saved">
          {t("settings.saved", "Saved")}
        </p>
      )}
    </section>
  );
}
