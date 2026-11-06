/**
 * P5 Task 5.2 — shared building blocks for the two card types.
 *
 * Field rendering, the mandatory markers and the card actions live here once;
 * `RequirementCard`/`ElementCard` only add their handles and band styling.
 */

import { useTranslation } from "react-i18next";

import type { AllocationRow } from "./buildGraph";
import {
  layoutCardFields,
  type CardFieldConfig,
  type CardFieldKey,
} from "./cardFields";
import type { AllocationCardData } from "./types";
import styles from "./AllocationGraph.module.css";

function formatId(row: AllocationRow): string {
  const raw = row.uid;
  if (typeof raw === "string" && raw) return raw;
  return row.id;
}

function formatOwner(value: unknown): string {
  if (typeof value === "string" && value) return value;
  if (value && typeof value === "object") {
    const record = value as { name?: unknown; id?: unknown };
    if (typeof record.name === "string" && record.name) return record.name;
    if (typeof record.id === "string" && record.id) return record.id;
  }
  return "—";
}

/** Display value for one configured field; `—` for an absent value. */
export function formatCardFieldValue(
  row: AllocationRow,
  key: CardFieldKey,
  allocationCount: number
): string {
  switch (key) {
    case "id":
      return formatId(row);
    case "title":
      return row.title;
    case "state":
      return row.state ?? "—";
    case "tier":
      return row.tier_name ?? row.tier_key ?? (row.level != null ? `L${row.level}` : "—");
    case "type":
      return row.type ?? "—";
    case "category":
      return row.category ?? "—";
    case "group":
      return row.group ?? "—";
    case "allocationCount":
      return String(allocationCount);
    case "owner":
      return formatOwner(row.owner);
    case "lock":
      return "—";
    default:
      return "—";
  }
}

export interface CardFieldRowsProps {
  row: AllocationRow;
  config: CardFieldConfig;
  allocationCount: number;
  /** Field already shown in the card header (avoids rendering it twice). */
  exclude?: CardFieldKey;
}

/** The configured field rows (the `lock` marker is rendered separately). */
export function CardFieldRows({
  row,
  config,
  allocationCount,
  exclude,
}: CardFieldRowsProps): JSX.Element | null {
  const { t } = useTranslation();
  const rows = layoutCardFields(config)
    .map((keys) => keys.filter((key) => key !== exclude))
    .filter((keys) => keys.length > 0);
  if (rows.length === 0) return null;

  return (
    <div className={styles.fieldRows}>
      {rows.map((keys, rowIndex) => (
        <div
          key={rowIndex}
          className={styles.fieldRow}
          data-testid={`card-field-row-${rowIndex}`}
        >
          {keys.map((key) => {
            const value = formatCardFieldValue(row, key, allocationCount);
            return (
              <span
                key={key}
                className={styles.field}
                data-field={key}
                data-testid={`card-field-${key}`}
                title={`${t(`allocationGraph.fields.${key}`)}: ${value}`}
              >
                <span className={styles.fieldLabel}>
                  {t(`allocationGraph.fields.${key}`)}
                </span>
                <span className={styles.fieldValue}>{value}</span>
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/** Lock/finding/unallocated markers — never hideable, always rendered. */
export function CardMarkers({ data }: { data: AllocationCardData }): JSX.Element {
  const { t } = useTranslation();
  const { row } = data;
  const findings = row.findings ?? [];
  const lockState =
    typeof row.locked === "string"
      ? row.locked
      : row.locked && typeof row.locked === "object"
        ? row.locked.state
        : undefined;

  return (
    <div className={styles.markers}>
      {data.frozen && (
        <span
          className={`${styles.marker} ${styles.markerLock}`}
          data-testid={`card-lock-${row.id}`}
          title={lockState ?? t("allocationGraph.locked")}
        >
          {t("allocationGraph.locked")}
          {lockState ? `: ${lockState}` : ""}
        </span>
      )}
      {findings.length > 0 && (
        <span
          className={`${styles.marker} ${styles.markerFinding}`}
          data-testid={`card-finding-${row.id}`}
        >
          {t("allocationGraph.findingCount", { count: findings.length })}
        </span>
      )}
      {data.unallocated && (
        <span
          className={`${styles.marker} ${styles.markerUnallocated}`}
          data-testid={`card-unallocated-${row.id}`}
        >
          {t("allocationGraph.unallocated")}
        </span>
      )}
    </div>
  );
}

export interface CardActionsProps {
  nodeId: string;
  data: AllocationCardData;
}

/** Collapse/expand and the keyboard "Allokieren auf …" path. */
export function CardActions({ nodeId, data }: CardActionsProps): JSX.Element | null {
  const { t } = useTranslation();
  const canCollapse = data.descendantCount > 0;
  const canAllocate =
    data.editMode && data.kind === "requirement" && !data.frozen;
  if (!canCollapse && !canAllocate) return null;

  return (
    <div className={styles.actions}>
      {canCollapse && (
        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid={`card-collapse-${data.row.id}`}
          aria-expanded={!data.collapsed}
          title={
            data.collapsed
              ? t("allocationGraph.expand", { title: data.row.title })
              : t("allocationGraph.collapse", { title: data.row.title })
          }
          onClick={() => data.onToggleCollapse?.(nodeId)}
        >
          {data.collapsed
            ? t("allocationGraph.expand", { title: data.row.title })
            : t("allocationGraph.collapse", { title: data.row.title })}
          {data.collapsed && data.hiddenDescendantCount > 0
            ? ` (${data.hiddenDescendantCount})`
            : ""}
        </button>
      )}
      {canAllocate && (
        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid={`card-allocate-${data.row.id}`}
          onClick={() => data.onOpenAllocator?.(data.row)}
        >
          {t("connectionView.allocateTo")}
        </button>
      )}
    </div>
  );
}
