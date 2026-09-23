/**
 * Shared PageHeader — the single page head of every artifact route.
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * UI concept ch. 12.1. Consolidates five divergent per-page headers
 * (issue #172) and now also enforces the three rules the first version did
 * not:
 *
 *  1. Exactly one `<h1>`, at `--font-size-3xl` / `--leading-tight` /
 *     `--tracking-tight`.
 *  2. The summary is **always** visible, not only while a filter is
 *     active. It answers "how many do we have?" up front and makes a
 *     silently truncated list noticeable.
 *  3. Exactly one filled primary action, top right, named after its
 *     *result* ("New requirement"). Set `primaryAction.prefixWithPlus` to
 *     additionally render the gesture ("+ New requirement") — the label
 *     itself stays result-named either way. Everything else moves into the
 *     overflow menu — export and import are rare.
 *
 * Backwards compatibility: `count` and `secondaryActions` are the original
 * API and still render as before, so routes outside the current pilot are
 * untouched. New call sites use `summary` and `overflowActions`.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./PageHeader.module.css";

export interface PageHeaderAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  testId?: string;
  /**
   * Overrides the accessible name (falls back to `label` otherwise). Use
   * this when the visible `label` text would collide with another
   * simultaneously-rendered control's accessible name (issue #678) — e.g.
   * a page header action and a related in-panel action that share the same
   * visible wording but need genuinely distinct names for a11y trees and
   * `getByRole` queries.
   */
  ariaLabel?: string;
  /**
   * Renders `label` prefixed with the "+ " gesture marker, e.g.
   * "+ New requirement" — the CTA-button convention (issue #594). `label`
   * itself stays result-named; only `primaryAction` honors this.
   */
  prefixWithPlus?: boolean;
}

interface PageHeaderCount {
  shown: number;
  total: number;
}

interface PageHeaderProps {
  title: string;
  /**
   * Always-visible one-line summary, e.g. "128 requirements · 12 in review".
   * Preferred over `count`; when both are given, `summary` wins.
   */
  summary?: string;
  /** Legacy numeric counter. Rendered next to the title when no summary. */
  count?: PageHeaderCount;
  primaryAction?: PageHeaderAction;
  /** Legacy: rendered as a plain button row next to the primary action. */
  secondaryActions?: PageHeaderAction[];
  /** Rare actions (export, import, baseline) behind a single "⋯" menu. */
  overflowActions?: PageHeaderAction[];
  /**
   * `compact` keeps the smaller pre-existing heading for the one route that
   * renders its header inside a narrow split-view panel rather than at page
   * level. Page-level headers use the default.
   */
  density?: "page" | "compact";
  testId?: string;
}

export function PageHeader({
  title,
  summary,
  count,
  primaryAction,
  secondaryActions = [],
  overflowActions = [],
  density = "page",
  testId = "page-header",
}: PageHeaderProps): JSX.Element {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const closeMenu = useCallback(
    (restoreFocus: boolean) => {
      setMenuOpen(false);
      if (restoreFocus) triggerRef.current?.focus();
    },
    [],
  );

  // Escape closes and returns focus to the trigger; a click anywhere outside
  // dismisses without stealing focus (ch. 12.8 dialog rules applied to the
  // menu, minus the focus trap — a menu is not modal).
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeMenu(true);
      }
    };
    const onPointerDown = (e: MouseEvent): void => {
      if (!containerRef.current?.contains(e.target as Node)) closeMenu(false);
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [menuOpen, closeMenu]);

  const isCompact = density === "compact";
  // The <h1>'s `fontSize` stays on the `style` prop as a hoisted identifier:
  // it switches between `--font-size-3xl` and `--font-size-lg` from `density`
  // (a genuine per-instance runtime value, not a static declaration), and
  // `PageHeader.test.tsx:29` pins it via
  // `toHaveStyle({ fontSize: "var(--font-size-3xl)" })`. vitest's `css: false`
  // means CSS Modules never load in the test run, so moving it onto a class
  // would break that pinned assertion — the documented house pattern, same as
  // `MetricsDashboard.helpToggleStyle` (Etappe 5) and `SplitView.tsx`. See the
  // module header.
  const titleStyle: React.CSSProperties = {
    fontSize: isCompact ? "var(--font-size-lg)" : "var(--font-size-3xl)",
  };
  // Issue #718: this container used to render unconditionally, even with zero
  // actions (e.g. AuditDashboard, CsvImport — title+summary only). An empty
  // flex item still participates in `.header`'s `flex-wrap` + `gap`: in a
  // narrow parent (e.g. CsvImport's 640px reading column) the title/summary
  // block alone could leave less free width than the gap needs for a second
  // (empty) flex item, so it wrapped onto its own line and the `row-gap`
  // between the two lines added ~8px of dead header height — a route with no
  // actions at all ended up *taller* than one with a real button row. Since
  // an empty actions row has no visible content, it should not exist in the
  // DOM at all.
  const hasActions =
    secondaryActions.length > 0 || !!primaryAction || overflowActions.length > 0;
  const summaryText =
    summary ??
    (count
      ? count.shown === count.total
        ? String(count.total)
        : `${count.shown} / ${count.total}`
      : null);

  return (
    <div ref={containerRef} data-testid={testId} className={styles.header}>
      <div className={styles.titleBlock}>
        <h1 className={styles.title} style={titleStyle}>
          {title}
        </h1>
        {summaryText != null && (
          <p data-testid="page-header-count" className={styles.summary}>
            {summaryText}
          </p>
        )}
      </div>

      {/* issue #314: the actions group previously had no `flexWrap` / `minWidth`
          of its own — as a nested flex row (row direction, no wrap) its
          automatic min-width equals the sum of its children's min-content
          widths, so a route with both a long `primaryAction` label and an
          `overflowActions` trigger (e.g. Architecture) could refuse to
          shrink below that sum and run past the viewport's right edge
          instead of wrapping onto a second line like `.header` itself
          already does. `flexWrap: "wrap"` + `minWidth: 0` let it reflow
          the same way. */}
      {hasActions && (
      <div className={styles.actions}>
        {secondaryActions.map((action) => (
          <button
            key={action.label}
            type="button"
            className="btn-secondary"
            data-testid={action.testId}
            aria-label={action.ariaLabel}
            onClick={action.onClick}
            disabled={action.disabled}
          >
            {action.label}
          </button>
        ))}

        {primaryAction && (
          <button
            type="button"
            className="btn-primary"
            data-testid={primaryAction.testId ?? "page-header-primary-action"}
            aria-label={primaryAction.ariaLabel}
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            {primaryAction.prefixWithPlus
              ? `+ ${primaryAction.label}`
              : primaryAction.label}
          </button>
        )}

        {overflowActions.length > 0 && (
          <div className={styles.overflow}>
            <button
              ref={triggerRef}
              type="button"
              className="btn-secondary"
              data-testid="page-header-overflow-trigger"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-controls={menuOpen ? menuId : undefined}
              aria-label={t("pageHeader.moreLabel", "Weitere Aktionen anzeigen")}
              title={t("pageHeader.more", "Weitere Aktionen")}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span aria-hidden="true">⋯</span>
            </button>
            {menuOpen && (
              <div
                id={menuId}
                role="menu"
                data-testid="page-header-overflow-menu"
                aria-label={t("pageHeader.more", "Weitere Aktionen")}
                className={styles.menu}
              >
                {overflowActions.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    role="menuitem"
                    data-testid={action.testId}
                    disabled={action.disabled}
                    onClick={() => {
                      closeMenu(true);
                      action.onClick();
                    }}
                    className={`${styles.menuItem} ${action.disabled ? styles.menuItemDisabled : ""}`}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      )}
    </div>
  );
}
