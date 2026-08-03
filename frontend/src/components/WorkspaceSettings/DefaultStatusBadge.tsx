/**
 * REQ-180/183 — DefaultStatusBadge + ResetToDefaultButton (shared, SCR-202).
 *
 * Surfaces whether a workspace's workflow/permission configuration mirrors the
 * tenant-wide global default ("On Default") or has diverged ("Customized"), and
 * offers a one-click reset. The badge itself renders through the single
 * project-wide `shared/StatusBadge` (Task 1.6, UI-Konzept-Vollrollout) — this
 * component only translates the config-sync state into a status/label/variant
 * triple; it owns no rendering or color logic of its own. Badge labels are
 * always visible text (never color-only) for accessibility.
 */

import { StatusBadge } from "../shared/StatusBadge";

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
      <StatusBadge
        status="no-source"
        label="No Global Source"
        badgeVariant="neutral"
        testId="default-status-badge"
      />
    );
  }
  if (isCustomized) {
    return (
      <StatusBadge
        status="customized"
        label="Customized"
        badgeVariant="warning"
        testId="default-status-badge"
      />
    );
  }
  return (
    <StatusBadge
      status="on-default"
      label="On Default"
      badgeVariant="success"
      testId="default-status-badge"
    />
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
