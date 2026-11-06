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

import type { AllocationRow } from "../../api/allocation-view";
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
      if (row.allocated_to && sums.has(row.allocated_to)) {
        sums.set(row.allocated_to, (sums.get(row.allocated_to) ?? 0) + 1);
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
              <tr key={row.id} data-testid={`matrix-row-${row.id}`}>
                <th scope="row" className={styles.matrixRowHeader}>
                  {row.title}
                </th>
                {elements.map((element) => {
                  const allocated = row.allocated_to === element.id;
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
