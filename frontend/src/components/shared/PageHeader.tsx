/**
 * Shared PageHeader — single consistent header for artifact list pages.
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * Consolidates five divergent per-page headers (issue #172): different
 * heading tags (h1/h2/h3), sizes (18px/24px), weights (600/700) and
 * primary-action placement (under the filters vs. top-right of the header).
 * Requirements and Stakeholder Needs previously buried "+ New" under the
 * filter row (or had no heading at all); this component puts the title,
 * live count and primary action in one place, matching the pattern
 * Architecture/Glossary already used correctly.
 *
 * Rule: every artifact page renders exactly one `<h1>` via this component;
 * the primary action always sits top-right, secondary actions render as a
 * plain button row (kept simple — no overflow menu yet, see issue #172
 * follow-up for a ratchet test).
 */

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
  count?: PageHeaderCount;
  primaryAction?: PageHeaderAction;
  secondaryActions?: PageHeaderAction[];
}

export function PageHeader({
  title,
  count,
  primaryAction,
  secondaryActions = [],
}: PageHeaderProps): JSX.Element {
  return (
    <div
      data-testid="page-header"
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "space-between",
        alignItems: "center",
        rowGap: "var(--space-2)",
        marginBottom: "var(--space-3)",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-2)" }}>
        <h1
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            margin: 0,
            color: "var(--color-text)",
          }}
        >
          {title}
        </h1>
        {count && (
          <span
            data-testid="page-header-count"
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
            }}
          >
            {count.shown === count.total ? count.total : `${count.shown} / ${count.total}`}
          </span>
        )}
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
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
      </div>
    </div>
  );
}
