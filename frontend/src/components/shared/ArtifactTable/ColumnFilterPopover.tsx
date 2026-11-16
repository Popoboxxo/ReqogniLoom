/**
 * Task 4.4 — type-aware column filter popover
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * One popover per column. It emits the frozen DSL constraints for its type:
 * enum/reference → `in`, text → `contains`, number/date → a `gte`+`lte` list,
 * boolean → `eq`. An empty result removes the field's constraint. Escape and
 * the Close button both call `onClose`; every control is a native, labelled
 * form element (arrow keys and Space work without extra handlers).
 */

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import type { FilterConstraint } from "../../../api/table-views";
import type { TableColumn } from "./columnModel";
import { constraintsFor, withConstraints } from "./filters";
import { filterControlFor, optionLabel } from "./fieldComponents";
import styles from "./ArtifactTable.module.css";

export interface ColumnFilterPopoverProps {
  column: TableColumn;
  constraints: FilterConstraint[];
  onChange(next: FilterConstraint[]): void;
  onClose(): void;
}

export function ColumnFilterPopover({
  column,
  constraints,
  onChange,
  onClose,
}: ColumnFilterPopoverProps): JSX.Element | null {
  const { t, i18n } = useTranslation();
  const headingId = useId();
  const control = filterControlFor(column.type);
  // Hooks must run before the non-filterable early return.
  const containsValue = constraints.find((c) => c.op === "contains")?.value;
  const inValues = constraints.find((c) => c.op === "in")?.value;
  const [textDraft, setTextDraft] = useState(String(containsValue ?? ""));
  const [referenceDraft, setReferenceDraft] = useState(
    Array.isArray(inValues) ? inValues.map(String).join(", ") : ""
  );

  if (!column.filterable || control === null) return null;

  const emit = (next: FilterConstraint[]): void => onChange(next);

  const gte = constraints.find((c) => c.op === "gte")?.value;
  const lte = constraints.find((c) => c.op === "lte")?.value;
  const eq = constraints.find((c) => c.op === "eq")?.value;
  const selectedIn = Array.isArray(inValues) ? inValues.map(String) : [];
  // The text/reference controls keep their own draft: normalising on every
  // keystroke would eat the comma that separates reference ids while typing.

  const panel = (body: React.ReactNode): JSX.Element => (
    <div
      className={styles.popover}
      role="group"
      aria-labelledby={headingId}
      data-testid={`filter-popover-${column.name}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <p id={headingId} className={styles.popoverTitle}>
        {t("table.filterTitle", { column: column.label })}
      </p>
      {body}
      <button
        type="button"
        className={`btn btn-secondary ${styles.secondaryButton}`}
        data-testid={`filter-close-${column.name}`}
        onClick={onClose}
      >
        {t("table.filterClose")}
      </button>
    </div>
  );

  if (control === "enum") {
    const options = column.options ?? [];
    return panel(
      <fieldset className={styles.filterFieldset}>
        <legend className={styles.srOnly}>{t("table.filterValues")}</legend>
        {options.map((option) => {
          const checked = selectedIn.includes(option.value);
          return (
            <label key={option.value} className={styles.filterOption}>
              <input
                type="checkbox"
                data-testid={`filter-option-${column.name}-${option.value}`}
                checked={checked}
                onChange={() => {
                  const next = checked
                    ? selectedIn.filter((value) => value !== option.value)
                    : [...selectedIn, option.value];
                  emit(next.length ? [{ op: "in", value: next }] : []);
                }}
              />
              {optionLabel(option, i18n.language)}
            </label>
          );
        })}
        {options.length === 0 && (
          <p className={styles.hint}>{t("table.filterNoOptions")}</p>
        )}
      </fieldset>
    );
  }

  if (control === "text" || control === "reference") {
    const value = control === "text" ? textDraft : referenceDraft;
    return panel(
      <label className={styles.filterLabel}>
        {control === "text" ? t("table.filterContains") : t("table.filterValues")}
        <input
          type="text"
          className={styles.input}
          data-testid={`filter-${column.name}-${control === "text" ? "contains" : "in"}`}
          value={value}
          onChange={(event) => {
            const raw = event.target.value;
            if (control === "text") {
              setTextDraft(raw);
              emit(raw ? [{ op: "contains", value: raw }] : []);
              return;
            }
            setReferenceDraft(raw);
            const values = raw
              .split(",")
              .map((entry) => entry.trim())
              .filter(Boolean);
            emit(values.length ? [{ op: "in", value: values }] : []);
          }}
        />
      </label>
    );
  }

  if (control === "boolean") {
    const current = eq === true ? "true" : eq === false ? "false" : "all";
    return panel(
      <label className={styles.filterLabel}>
        {t("table.filterValue")}
        <select
          className={styles.input}
          data-testid={`filter-${column.name}-boolean`}
          value={current}
          onChange={(event) => {
            const raw = event.target.value;
            emit(raw === "all" ? [] : [{ op: "eq", value: raw === "true" }]);
          }}
        >
          <option value="all">{t("table.filterAll")}</option>
          <option value="true">{t("table.filterTrue")}</option>
          <option value="false">{t("table.filterFalse")}</option>
        </select>
      </label>
    );
  }

  // number-range / date-range: emitted as a two-element list.
  const isDate = control === "date-range";
  const updateRange = (nextGte: string, nextLte: string): void => {
    const next: FilterConstraint[] = [];
    if (nextGte) next.push({ op: "gte", value: nextGte });
    if (nextLte) next.push({ op: "lte", value: nextLte });
    emit(next);
  };

  return panel(
    <div className={styles.rangeRow}>
      <label className={styles.filterLabel}>
        {t("table.filterFrom")}
        <input
          type={isDate ? "date" : "number"}
          className={styles.input}
          data-testid={`filter-${column.name}-gte`}
          value={gte === undefined || gte === null ? "" : String(gte)}
          onChange={(event) =>
            updateRange(event.target.value, lte === undefined ? "" : String(lte))
          }
        />
      </label>
      <label className={styles.filterLabel}>
        {t("table.filterTo")}
        <input
          type={isDate ? "date" : "number"}
          className={styles.input}
          data-testid={`filter-${column.name}-lte`}
          value={lte === undefined || lte === null ? "" : String(lte)}
          onChange={(event) =>
            updateRange(gte === undefined ? "" : String(gte), event.target.value)
          }
        />
      </label>
    </div>
  );
}

export { constraintsFor, withConstraints };
