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
 *     *result* ("New requirement"), not the gesture ("+ New"). Everything
 *     else moves into the overflow menu — export and import are rare.
 *
 * Backwards compatibility: `count` and `secondaryActions` are the original
 * API and still render as before, so routes outside the current pilot are
 * untouched. New call sites use `summary` and `overflowActions`.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./PageHeader.module.css";

interface PageHeaderAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  testId?: string;
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
  const summaryText =
    summary ??
    (count
      ? count.shown === count.total
        ? String(count.total)
        : `${count.shown} / ${count.total}`
      : null);

  return (
    <div ref={containerRef} data-testid={testId} className={styles.header}>
      <div style={{ minWidth: 0 }}>
        <h1
          style={{
            fontSize: isCompact ? "var(--font-size-lg)" : "var(--font-size-3xl)",
            lineHeight: "var(--leading-tight)",
            letterSpacing: "var(--tracking-tight)",
            fontWeight: "var(--weight-semibold)",
            margin: 0,
            color: "var(--color-text)",
          }}
        >
          {title}
        </h1>
        {summaryText != null && (
          <p
            data-testid="page-header-count"
            style={{
              margin: "var(--space-1) 0 0",
              fontSize: "var(--font-size-sm)",
              lineHeight: "var(--leading-normal)",
              color: "var(--color-text-muted)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
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
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: "var(--space-2)",
          alignItems: "center",
          minWidth: 0,
        }}
      >
        {secondaryActions.map((action) => (
          <button
            key={action.label}
            type="button"
            className="btn-secondary"
            data-testid={action.testId}
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
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            {primaryAction.label}
          </button>
        )}

        {overflowActions.length > 0 && (
          <div style={{ position: "relative" }}>
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
                style={{
                  position: "absolute",
                  top: "calc(100% + var(--space-1))",
                  right: 0,
                  zIndex: 20,
                  minWidth: "200px",
                  display: "flex",
                  flexDirection: "column",
                  padding: "var(--space-1)",
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "var(--shadow-card)",
                }}
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
                    style={{
                      background: "transparent",
                      color: action.disabled
                        ? "var(--color-text-muted)"
                        : "var(--color-text)",
                      textAlign: "left",
                      padding: "var(--space-2) var(--space-3)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "var(--font-size-sm)",
                      fontWeight: "var(--weight-medium)",
                      cursor: action.disabled ? "not-allowed" : "pointer",
                      opacity: action.disabled ? 0.55 : 1,
                    }}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
