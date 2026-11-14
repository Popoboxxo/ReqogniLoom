/**
 * ARCH-L1-001 ReactFrontend — connection view "Matrix" renderer
 * (P3 Task 3.4, renderer C).
 *
 * Rows are requirements, columns are architecture elements. A requirement is
 * allocated to at most one element (N:1), so each row shows at most one dot.
 * The matrix is a *window* over the current filter result: page `x` of `y` is
 * rendered explicitly, and the footer sums per column plus a grand total over
 * the visible window.
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

import type { AllocationRow } from "../../api/allocation-view";
import { LevelBadge } from "../shared/LevelBadge";
import { isRowLocked, lockStateName } from "../../utils/allocation";
import styles from "./ConnectionView.module.css";

export interface MatrixRendererProps {
  requirements: AllocationRow[];
  elements: AllocationRow[];
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function MatrixRenderer({
  requirements,
  elements,
  page,
  pageSize,
  onPageChange,
}: MatrixRendererProps): JSX.Element {
  const { t } = useTranslation();

  const totalPages = Math.max(1, Math.ceil(requirements.length / pageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);
  const windowRows = useMemo(
    () =>
      requirements.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize
      ),
    [requirements, currentPage, pageSize]
  );

  const columnSums = useMemo(() => {
    const sums = new Map<string, number>();
    for (const element of elements) sums.set(element.id, 0);
    for (const row of windowRows) {
      // `allocated_to` is the element's backing *Artifact* id, while the
      // matrix columns are keyed by the element entity id. Prefer the
      // resolved `element_id`; fall back for fixtures that only set the
      // artifact id (and for rows an older read object did not resolve).
      const target = row.element_id ?? row.allocated_to;
      if (target && sums.has(target)) {
        sums.set(target, (sums.get(target) ?? 0) + 1);
      }
    }
    return sums;
  }, [elements, windowRows]);

  const totalDots = Array.from(columnSums.values()).reduce(
    (sum, value) => sum + value,
    0
  );

  return (
    <div className={styles.matrixArea} data-testid="matrix-renderer">
      <div className={styles.matrixScroll}>
        <table className={styles.matrix}>
          <thead>
            <tr>
              <th scope="col" className={styles.matrixRowHeader}>
                {t("connectionView.requirements")}
              </th>
              {elements.map((element) => (
                <th
                  key={element.id}
                  scope="col"
                  data-testid={`matrix-column-${element.id}`}
                  title={element.title}
                >
                  {element.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {windowRows.map((row) => (
              <tr
                key={row.id}
                data-testid={`matrix-row-${row.id}`}
                data-locked={isRowLocked(row.locked) ? "true" : "false"}
              >
                <th scope="row" className={styles.matrixRowHeader}>
                  {/* V6 (triage 2026-11-10): the level was readable in the
                      requirement list only. The matrix read object already
                      carries `level` + `tier_name`, so the row shows the same
                      neutral badge the list uses (shared <LevelBadge>, the
                      single implementation the ui-ratchet freezes). */}
                  <span className={styles.matrixRowLevel}>
                    <LevelBadge
                      level={row.level}
                      title={row.tier_name ?? undefined}
                      testId={`matrix-level-${row.id}`}
                    />
                  </span>
                  <span className={styles.matrixRowTitle}>{row.title}</span>
                  {isRowLocked(row.locked) && (
                    <span
                      className={styles.lockIcon}
                      data-testid={`matrix-lock-${row.id}`}
                      title={
                        lockStateName(row.locked) ??
                        t("connectionView.locked")
                      }
                      aria-label={t("connectionView.lockedTooltip", {
                        state:
                          lockStateName(row.locked) ??
                          t("connectionView.locked"),
                      })}
                    >
                      <Lock aria-hidden="true" size={14} />
                    </span>
                  )}
                </th>
                {elements.map((element) => {
                  const allocated =
                    (row.element_id ?? row.allocated_to) === element.id;
                  return (
                    <td key={element.id}>
                      {allocated ? (
                        <span
                          className={styles.dot}
                          data-testid={`matrix-dot-${row.id}-${element.id}`}
                          aria-label={t("connectionView.allocated")}
                        />
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot className={styles.matrixFooter}>
            <tr>
              <th scope="row" className={styles.matrixRowHeader}>
                {t("connectionView.sum")}
              </th>
              {elements.map((element) => (
                <td
                  key={element.id}
                  data-testid={`matrix-sum-${element.id}`}
                >
                  {columnSums.get(element.id) ?? 0}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row" className={styles.matrixRowHeader}>
                {t("connectionView.total")}
              </th>
              <td colSpan={Math.max(1, elements.length)} data-testid="matrix-sum-total">
                {totalDots}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className={styles.pager}>
        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid="matrix-prev"
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
        >
          {t("connectionView.previous")}
        </button>
        <span data-testid="matrix-page-indicator">
          {t("connectionView.pageOf", {
            page: currentPage,
            total: totalPages,
          })}
        </span>
        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid="matrix-next"
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
        >
          {t("connectionView.next")}
        </button>
      </div>
    </div>
  );
}
