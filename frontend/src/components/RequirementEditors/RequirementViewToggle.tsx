/**
 * Task 4.9 — list/table switch for the Requirements page
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * The mode is persisted in `localStorage` on a best-effort basis: a browser
 * that blocks storage (privacy mode, quota) must not break the page — the
 * toggle then simply starts in list mode and the write is a no-op.
 */

import { useTranslation } from "react-i18next";

import styles from "./RequirementViewToggle.module.css";

export type RequirementViewMode = "list" | "table";

export const REQUIREMENT_VIEW_MODE_KEY = "reqogniLoom.requirements.viewMode";

export function readRequirementViewMode(): RequirementViewMode {
  try {
    return window.localStorage.getItem(REQUIREMENT_VIEW_MODE_KEY) === "table"
      ? "table"
      : "list";
  } catch {
    return "list";
  }
}

export function writeRequirementViewMode(mode: RequirementViewMode): void {
  try {
    window.localStorage.setItem(REQUIREMENT_VIEW_MODE_KEY, mode);
  } catch {
    // Storage is a convenience, never a requirement.
  }
}

export interface RequirementViewToggleProps {
  mode: RequirementViewMode;
  onChange(mode: RequirementViewMode): void;
}

export function RequirementViewToggle({
  mode,
  onChange,
}: RequirementViewToggleProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div
      className={styles.toggle}
      role="group"
      aria-label={t("table.viewToggleLabel")}
      data-testid="req-view-toggle"
    >
      <button
        type="button"
        className={`btn ${mode === "list" ? "btn-primary" : "btn-ghost"}`}
        data-testid="req-view-toggle-list"
        aria-pressed={mode === "list"}
        onClick={() => onChange("list")}
      >
        {t("table.viewList")}
      </button>
      <button
        type="button"
        className={`btn ${mode === "table" ? "btn-primary" : "btn-ghost"}`}
        data-testid="req-view-toggle-table"
        aria-pressed={mode === "table"}
        onClick={() => onChange("table")}
      >
        {t("table.viewTable")}
      </button>
    </div>
  );
}
