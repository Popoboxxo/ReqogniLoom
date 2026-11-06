/**
 * P2 Task 2.10 — the workspace tier ladder editor.
 *
 * Rendered in `WorkspaceSettings`'s "Allgemein" tab, next to the rigor preset
 * and the terminology profile: the ladder is workspace configuration, not a
 * personal preference. It edits the ladder of exactly one workspace
 * (`GET|PUT /api/v1/workspaces/<id>/tiers/`, see `api/tiers.ts`).
 *
 * Interaction:
 *   - a loaded ladder is edited as a draft: rename (DE/EN), change the rule,
 *     reorder with ↑/↓, remove with ×, append with "Ebene hinzufügen";
 *   - nothing is sent until "Leiter speichern" is pressed, so a half-edited
 *     ladder never becomes the stored one;
 *   - a save that the server rejects (rule violation, or a removed tier still
 *     referenced by requirements) is shown inline and the draft is kept, so
 *     the admin can correct it instead of losing the edit;
 *   - the "three names" shortcut replaces the draft with exactly three tiers
 *     (erste / dazwischen / letzte, see `buildThreeNameLadder`).
 *
 * Read-only: `readOnly` disables every control for a non-admin. The server
 * re-asserts workspace-admin on PUT, so the flag is a UI affordance, not the
 * authorization boundary.
 *
 * Server-derived fields (`position`, `level`) are never edited here: the order
 * of the array is the order of the ladder, and the server derives both.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import {
  buildThreeNameLadder,
  tiersApi,
  type TierName,
  type TierRule,
  type TierWriteEntry,
  type ThreeNameLabels,
} from "../../api/tiers";
import styles from "./TierLadderSection.module.css";

export interface TierLadderSectionProps {
  /** The workspace whose ladder this section edits. */
  workspaceId: string;
  /** Non-admins see the ladder but cannot change it. */
  readOnly?: boolean;
}

/** One editable ladder row (draft state, not the wire shape). */
interface DraftTier {
  tier_key: string;
  nameDe: string;
  nameEn: string;
  rule: TierRule;
  /**
   * Input value for `rule: "from_end"` — a string so an intermediate empty
   * value does not turn into `0` while the admin is typing. Ignored otherwise.
   */
  fromEnd: string;
}

/** A ladder entry from either the GET/PUT answer or the PUT body. */
type LadderEntryLike = {
  tier_key: string;
  name: Partial<TierName>;
  rule: TierRule;
  from_end: number | null;
};

const RULES: TierRule[] = ["first", "middle", "from_end"];

function toDraft(entry: LadderEntryLike): DraftTier {
  return {
    tier_key: entry.tier_key,
    nameDe: entry.name.de ?? "",
    nameEn: entry.name.en ?? "",
    rule: entry.rule,
    fromEnd: entry.from_end === null ? "" : String(entry.from_end),
  };
}

function toWrite(draft: DraftTier): TierWriteEntry {
  let fromEnd: number | null = null;
  if (draft.rule === "from_end") {
    const parsed = draft.fromEnd.trim() === "" ? 0 : Number(draft.fromEnd);
    // A non-numeric entry is sent as `null`; the server's validation message
    // ("Every from_end tier needs a non-negative from_end value") is the one
    // the admin then sees, instead of a silently invented number.
    fromEnd = Number.isFinite(parsed) ? parsed : null;
  }
  return {
    tier_key: draft.tier_key,
    name: { de: draft.nameDe, en: draft.nameEn },
    rule: draft.rule,
    from_end: fromEnd,
  };
}

/** Smallest `tier_<n>` key not yet used by the draft. */
function nextTierKey(drafts: readonly DraftTier[]): string {
  const used = new Set(drafts.map((draft) => draft.tier_key));
  let index = drafts.length + 1;
  while (used.has(`tier_${index}`)) index += 1;
  return `tier_${index}`;
}

/**
 * Next unused `from_end` value — a newly added position defaults to the leaf
 * side. `from_end` values must be unique inside a ladder, so reusing `0` would
 * always produce a server error.
 */
function nextFromEnd(drafts: readonly DraftTier[]): string {
  const used = new Set(
    drafts
      .filter((draft) => draft.rule === "from_end" && draft.fromEnd !== "")
      .map((draft) => Number(draft.fromEnd))
  );
  let value = 0;
  while (used.has(value)) value += 1;
  return String(value);
}

export function TierLadderSection({
  workspaceId,
  readOnly = false,
}: TierLadderSectionProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const lang = i18n?.language?.startsWith("de") ? "de" : "en";

  const [drafts, setDrafts] = useState<DraftTier[]>([]);
  const [threeNames, setThreeNames] = useState<ThreeNameLabels>({
    erste: "",
    dazwischen: "",
    letzte: "",
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setSaved(false);
    tiersApi
      .get(workspaceId)
      .then((payload) => {
        if (cancelled) return;
        setDrafts(payload.tiers.map(toDraft));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(extractApiErrorMessage(err) ?? "");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const editable = !readOnly && !isSaving;

  /** Apply a change to one row and drop a stale "saved" confirmation. */
  const updateDraft = useCallback(
    (index: number, patch: Partial<DraftTier>): void => {
      setSaved(false);
      setDrafts((current) =>
        current.map((draft, position) =>
          position === index ? { ...draft, ...patch } : draft
        )
      );
    },
    []
  );

  const changeRule = useCallback(
    (index: number, rule: TierRule): void => {
      // Switching to `from_end` needs an unused height, otherwise a row that
      // was `middle` would immediately collide with the existing leaf.
      updateDraft(index, {
        rule,
        fromEnd: rule === "from_end" ? nextFromEnd(drafts) : "",
      });
    },
    [drafts, updateDraft]
  );

  const move = useCallback((index: number, delta: number): void => {
    setSaved(false);
    setDrafts((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }, []);

  const remove = useCallback((tierKey: string): void => {
    setSaved(false);
    setDrafts((current) => current.filter((draft) => draft.tier_key !== tierKey));
  }, []);

  const add = useCallback((): void => {
    setSaved(false);
    setDrafts((current) => {
      const key = nextTierKey(current);
      const ordinal = current.length + 1;
      return [
        ...current,
        {
          tier_key: key,
          nameDe: t("tiers.defaultNameDe", { n: ordinal }),
          nameEn: t("tiers.defaultNameEn", { n: ordinal }),
          rule: "from_end",
          fromEnd: nextFromEnd(current),
        },
      ];
    });
  }, [t]);

  /** Prefill one three-name slot from the draft, the UI language first. */
  const labelFor = useCallback(
    (tierKey: string): string => {
      const draft = drafts.find((entry) => entry.tier_key === tierKey);
      if (!draft) return "";
      const preferred = lang === "de" ? draft.nameDe : draft.nameEn;
      return preferred || (lang === "de" ? draft.nameEn : draft.nameDe);
    },
    [drafts, lang]
  );

  const applyThreeNames = useCallback((): void => {
    const name = (key: keyof ThreeNameLabels, fallbackKey: string): string =>
      threeNames[key].trim() || labelFor(key) || t(fallbackKey);
    setSaved(false);
    setDrafts(
      buildThreeNameLadder({
        erste: name("erste", "tiers.threeNames.erste"),
        dazwischen: name("dazwischen", "tiers.threeNames.dazwischen"),
        letzte: name("letzte", "tiers.threeNames.letzte"),
      }).map(toDraft)
    );
  }, [threeNames, labelFor, t]);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload = await tiersApi.replace(
        workspaceId,
        drafts.map(toWrite)
      );
      // Render the server's ladder, not the draft: `position` and `level` are
      // derived there, and a merge/validation on the server must not leave a
      // local list that disagrees with the stored one.
      setDrafts(payload.tiers.map(toDraft));
      setSaved(true);
    } catch (err: unknown) {
      setError(extractApiErrorMessage(err) ?? "");
    } finally {
      setIsSaving(false);
    }
  }, [drafts, workspaceId]);

  return (
    <section className={styles.section} data-testid="tier-ladder">
      <h3 className={styles.heading}>{t("tiers.title")}</h3>
      <p className={styles.hint}>{t("tiers.hint")}</p>

      {readOnly && (
        <p className={styles.readOnly} data-testid="tier-ladder-readonly">
          {t("tiers.readOnly")}
        </p>
      )}

      {error !== null && (
        <p role="alert" className={styles.error} data-testid="tier-ladder-error">
          {error || t("tiers.saveFailed")}
        </p>
      )}

      {saved && (
        <p role="status" className={styles.saved} data-testid="tier-ladder-saved">
          {t("tiers.saved")}
        </p>
      )}

      {isLoading ? (
        <p role="status" className={styles.hint} data-testid="tier-ladder-loading">
          {t("tiers.loading")}
        </p>
      ) : (
        <>
          <ol className={styles.list} data-testid="tier-ladder-list">
            {drafts.map((draft, index) => (
              <li
                key={draft.tier_key}
                className={styles.row}
                data-testid={`tier-row-${draft.tier_key}`}
              >
                <span className={styles.key} data-testid={`tier-key-${draft.tier_key}`}>
                  {draft.tier_key}
                </span>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>{t("tiers.nameDe")}</span>
                  <input
                    className="field-input"
                    value={draft.nameDe}
                    aria-label={`${t("tiers.nameDe")}: ${draft.tier_key}`}
                    disabled={!editable}
                    onChange={(event) =>
                      updateDraft(index, { nameDe: event.target.value })
                    }
                    data-testid={`tier-name-de-${draft.tier_key}`}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>{t("tiers.nameEn")}</span>
                  <input
                    className="field-input"
                    value={draft.nameEn}
                    aria-label={`${t("tiers.nameEn")}: ${draft.tier_key}`}
                    disabled={!editable}
                    onChange={(event) =>
                      updateDraft(index, { nameEn: event.target.value })
                    }
                    data-testid={`tier-name-en-${draft.tier_key}`}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>{t("tiers.ruleLabel")}</span>
                  <select
                    className="field-select"
                    value={draft.rule}
                    aria-label={`${t("tiers.ruleLabel")}: ${draft.tier_key}`}
                    disabled={!editable}
                    onChange={(event) =>
                      changeRule(index, event.target.value as TierRule)
                    }
                    data-testid={`tier-rule-${draft.tier_key}`}
                  >
                    {RULES.map((rule) => (
                      <option key={rule} value={rule}>
                        {t(`tiers.rule.${rule}`)}
                      </option>
                    ))}
                  </select>
                </label>

                {draft.rule === "from_end" && (
                  <label className={styles.field}>
                    <span className={styles.fieldLabel}>{t("tiers.fromEnd")}</span>
                    <input
                      className="field-input"
                      type="number"
                      min={0}
                      value={draft.fromEnd}
                      aria-label={`${t("tiers.fromEnd")}: ${draft.tier_key}`}
                      disabled={!editable}
                      onChange={(event) =>
                        updateDraft(index, { fromEnd: event.target.value })
                      }
                      data-testid={`tier-from-end-${draft.tier_key}`}
                    />
                  </label>
                )}

                <div className={styles.actions}>
                  <button
                    type="button"
                    className="btn-icon"
                    aria-label={t("tiers.moveUp")}
                    title={t("tiers.moveUp")}
                    disabled={!editable || index === 0}
                    onClick={() => move(index, -1)}
                    data-testid={`tier-up-${draft.tier_key}`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn-icon"
                    aria-label={t("tiers.moveDown")}
                    title={t("tiers.moveDown")}
                    disabled={!editable || index === drafts.length - 1}
                    onClick={() => move(index, 1)}
                    data-testid={`tier-down-${draft.tier_key}`}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="btn-icon"
                    aria-label={t("tiers.remove")}
                    title={t("tiers.remove")}
                    disabled={!editable}
                    onClick={() => remove(draft.tier_key)}
                    data-testid={`tier-remove-${draft.tier_key}`}
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
          </ol>

          <div className={styles.footer}>
            <button
              type="button"
              className="btn-secondary"
              disabled={!editable}
              onClick={add}
              data-testid="tier-add-button"
            >
              {t("tiers.addTier")}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!editable || drafts.length === 0}
              onClick={() => void handleSave()}
              data-testid="tier-save-button"
            >
              {isSaving ? "…" : t("tiers.save")}
            </button>
          </div>

          {/* Quick start: the three-position ladder, applied to the draft so a
              mistaken click is still undoable by not saving. */}
          <div className={styles.threeNames} data-testid="tier-three-names">
            <h4 className={styles.subheading}>{t("tiers.threeNames.title")}</h4>
            <p className={styles.hint}>{t("tiers.threeNames.hint")}</p>
            <div className={styles.threeNamesRow}>
              {(["erste", "dazwischen", "letzte"] as const).map((key) => (
                <label key={key} className={styles.field}>
                  <span className={styles.fieldLabel}>
                    {t(`tiers.threeNames.${key}`)}
                  </span>
                  <input
                    className="field-input"
                    value={threeNames[key]}
                    placeholder={labelFor(key)}
                    disabled={!editable}
                    onChange={(event) => {
                      const value = event.target.value;
                      setSaved(false);
                      setThreeNames((current) => ({ ...current, [key]: value }));
                    }}
                    data-testid={`tier-three-name-${key}`}
                  />
                </label>
              ))}
              <button
                type="button"
                className="btn-secondary"
                disabled={!editable}
                onClick={applyThreeNames}
                data-testid="tier-three-names-apply"
              >
                {t("tiers.threeNames.apply")}
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
