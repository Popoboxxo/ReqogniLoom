/**
 * REQ-180/183 — DefaultStatusBadge + ResetToDefaultButton (shared, SCR-202).
 *
 * Surfaces whether a workspace's workflow/permission configuration mirrors the
 * tenant-wide global default ("On Default") or has diverged ("Customized"), and
 * offers a one-click reset. Reuses the existing ``permission_level`` pill shape
 * (rounded-full, xs, bold) — only the color pairs (success/warning/muted) are
 * new, all from existing CSS variables. Badge labels are always visible text
 * (never color-only) for accessibility.
 */

const pillBase: React.CSSProperties = {
  display: "inline-block",
  padding: "1px var(--space-2)",
  borderRadius: "var(--radius-full)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

interface DefaultStatusBadgeProps {
  isCustomized: boolean;
  /** When false (no linked global source), renders the neutral variant. */
  hasSource: boolean;
}

export function DefaultStatusBadge({
  isCustomized,
  hasSource,
}: DefaultStatusBadgeProps): JSX.Element {
  if (!hasSource) {
    return (
      <span
        data-testid="default-status-badge"
        data-variant="no-source"
        style={{
          ...pillBase,
          background: "var(--color-surface-raised)",
          color: "var(--color-text-muted)",
        }}
      >
        No Global Source
      </span>
    );
  }
  if (isCustomized) {
    return (
      <span
        data-testid="default-status-badge"
        data-variant="customized"
        style={{
          ...pillBase,
          background: "rgba(245,158,11,0.12)",
          color: "var(--color-warning, #f59e0b)",
        }}
      >
        Customized
      </span>
    );
  }
  return (
    <span
      data-testid="default-status-badge"
      data-variant="on-default"
      style={{
        ...pillBase,
        background: "rgba(22,163,74,0.12)",
        color: "var(--color-success, #16a34a)",
      }}
    >
      On Default
    </span>
  );
}

interface ResetToDefaultButtonProps {
  onReset: () => void;
  /** Disabled when already on-default or when no global source exists. */
  disabled: boolean;
  busy?: boolean;
  /** Accessible label — includes the entity name to disambiguate rows. */
  ariaLabel: string;
  title?: string;
  testId?: string;
}

export function ResetToDefaultButton({
  onReset,
  disabled,
  busy = false,
  ariaLabel,
  title,
  testId = "reset-to-default-btn",
}: ResetToDefaultButtonProps): JSX.Element {
  const isDisabled = disabled || busy;
  return (
    <button
      type="button"
      onClick={onReset}
      disabled={isDisabled}
      aria-label={ariaLabel}
      title={title}
      data-testid={testId}
      style={{
        background: "transparent",
        color: "var(--color-primary)",
        border: "1px solid var(--color-primary)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-1) var(--space-3)",
        fontSize: "var(--font-size-sm)",
        cursor: isDisabled ? "not-allowed" : "pointer",
        opacity: isDisabled ? 0.5 : 1,
      }}
    >
      {busy ? "…" : "Reset to Default"}
    </button>
  );
}
