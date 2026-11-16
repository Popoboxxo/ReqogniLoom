/**
 * Task 4.5 — column picker (plan 2026-11-04-tabellenansicht-s4).
 *
 * Checklist plus reorder controls. The keyboard path is the explicit
 * up/down buttons (drag-and-drop is a pointer-only convenience on top); both
 * write the same explicit ordered column list into `TableViewState.columns`.
 */

import { useTranslation } from "react-i18next";

import type { AttributeSpec } from "../../../api/attribute-definitions";
import type { TableViewState } from "../../../api/table-views";
import { columnLabel } from "./columnModel";
import styles from "./ArtifactTable.module.css";

export interface ColumnPickerProps {
  attributes: AttributeSpec[];
  state: TableViewState;
  onChange(next: TableViewState): void;
}

/**
 * The checked columns: the stored visible set in stored order, otherwise every
 * visible attribute in definition order.
 *
 * Must stay in lockstep with {@link buildColumns}: a non-empty `state.columns`
 * is a whitelist, so a field absent from it is rendered unchecked here and
 * hidden in the grid. Appending the missing attributes (the pre-fix behaviour)
 * showed them as checked while the grid still rendered them — and let the grid
 * re-add every column the user had hidden.
 */
export function effectiveColumnOrder(
  attributes: AttributeSpec[],
  state: TableViewState
): string[] {
  const visible = attributes.filter((attr) => attr.visible !== false);
  const byName = new Set(visible.map((attr) => attr.name));
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const entry of [...(state.columns ?? [])].sort(
    (a, b) => (a.order ?? 0) - (b.order ?? 0)
  )) {
    if (byName.has(entry.field) && !seen.has(entry.field)) {
      seen.add(entry.field);
      ordered.push(entry.field);
    }
  }
  if (ordered.length > 0) return ordered;
  return visible.map((attr) => attr.name);
}

export function ColumnPicker({
  attributes,
  state,
  onChange,
}: ColumnPickerProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const order = effectiveColumnOrder(attributes, state);
  const byName = new Map(attributes.map((attr) => [attr.name, attr]));

  const commit = (fields: string[]): void =>
    onChange({
      ...state,
      columns: fields.map((field, index) => ({ field, order: index })),
    });

  const toggle = (name: string): void => {
    commit(
      order.includes(name) ? order.filter((field) => field !== name) : [...order, name]
    );
  };

  const move = (name: string, delta: number): void => {
    const index = order.indexOf(name);
    const target = index + delta;
    if (index === -1 || target < 0 || target >= order.length) return;
    const next = [...order];
    next.splice(index, 1);
    next.splice(target, 0, name);
    commit(next);
  };

  return (
    <div className={styles.picker} data-testid="column-picker">
      <p className={styles.popoverTitle}>{t("table.columnPickerTitle")}</p>
      <ul className={styles.pickerList}>
        {[
          ...order,
          ...attributes
            .filter((a) => a.visible !== false && !order.includes(a.name))
            .map((a) => a.name),
        ]
          .filter((name, index, all) => all.indexOf(name) === index)
          .map((name) => {
            const attr = byName.get(name);
            if (!attr) return null;
            const checked = order.includes(name);
            const index = order.indexOf(name);
            return (
              <li key={name} className={styles.pickerRow}>
                <label className={styles.filterOption}>
                  <input
                    type="checkbox"
                    data-testid={`column-toggle-${name}`}
                    checked={checked}
                    onChange={() => toggle(name)}
                  />
                  {columnLabel(attr, i18n.language)}
                </label>
                <span className={styles.pickerButtons}>
                  <button
                    type="button"
                    className={`btn btn-icon ${styles.iconButton}`}
                    data-testid={`column-up-${name}`}
                    aria-label={t("table.moveColumnUp", {
                      column: columnLabel(attr, i18n.language),
                    })}
                    disabled={!checked || index <= 0}
                    onClick={() => move(name, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className={`btn btn-icon ${styles.iconButton}`}
                    data-testid={`column-down-${name}`}
                    aria-label={t("table.moveColumnDown", {
                      column: columnLabel(attr, i18n.language),
                    })}
                    disabled={!checked || index === order.length - 1}
                    onClick={() => move(name, 1)}
                  >
                    ↓
                  </button>
                </span>
              </li>
            );
          })}
      </ul>
      <button
        type="button"
        className={`btn btn-secondary ${styles.secondaryButton}`}
        data-testid="column-picker-reset"
        onClick={() => onChange({ ...state, columns: [] })}
      >
        {t("table.resetColumns")}
      </button>
    </div>
  );
}
