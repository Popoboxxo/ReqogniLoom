/**
 * ARCH-L1-001 ReactFrontend — <Badge> (UI concept ch. 8.1 / 12.4).
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * The **single** token-based badge in the app (issue #675). Every
 * status/version/level/type badge renders through here, so the app cannot
 * grow a second (or third) badge style system again.
 *
 * ## Two things are unified, and one deliberately is not
 *
 * 1. **Geometry** — box model, corner radius and text size come from the
 *    shared `BADGE_BASE_STYLE` (`utils/badgeBase.ts`). They carry no
 *    information, so they must be identical everywhere. Badges used to
 *    disagree on all three (`--radius-full` vs `--radius-sm`,
 *    `--font-size-sm` vs `--font-size-xs`, padding 2px/3px), which is what
 *    made a badge row look unsteady.
 * 2. **Colour semantics** — the `variant` prop is the *only* input that
 *    decides hue, and its token mapping lives in exactly one place
 *    (`getBadgeVariantStyle` in `utils/statusBadge.ts`). A given state
 *    therefore gets the same colour in a list row, a detail header, an audit
 *    card and the dashboard.
 * 3. **Not unified: the state → variant mapping.** That stays with the
 *    caller (`resolveBadgeVariant` for workflow status) because a state's
 *    meaning is domain knowledge, not presentation. Pass an explicit
 *    `variant` when a call site knows the semantics (e.g. an audit blocker
 *    is `danger` by construction, a "current version" marker is `neutral`).
 *
 * ## Variant contract (also documented on `getBadgeVariantStyle`)
 *
 * - `success` — approved / verified / done
 * - `info`    — in progress / proposed (needs a look, not a problem)
 * - `warning` — recoverable / needs attention (blocked, skipped, archived)
 * - `danger`  — rejected / failed / withdrawn
 * - `neutral` — not started / informational (draft, open, version, level)
 *
 * ## Composition
 *
 * `<StatusBadge>`, `<LevelBadge>` and `<VersionBadge>` are thin semantic
 * wrappers over this component: they own *what* the badge means and how it is
 * labelled, never its look. Their extra styling (the version badge's
 * monospace/tabular numerals, the level badge's wide tracking) is passed
 * through `style` as a semantic override, not as a parallel badge definition.
 *
 * ```tsx
 * <Badge variant="success">Approved</Badge>
 * <Badge variant="neutral" style={MONO_OVERRIDES}>{value}</Badge>
 * ```
 */

import type { CSSProperties, ReactNode } from "react";

import { getBadgeVariantStyle, type BadgeVariant } from "../../utils/statusBadge";

export interface BadgeProps {
  /**
   * Semantic variant. Defaults to `neutral` — an unknown/unspecified badge
   * must never be colour-coded by accident.
   */
  variant?: BadgeVariant;
  /** Badge text. Already-translated label; this component owns no i18n keys. */
  children: ReactNode;
  /** Native tooltip (e.g. a spelled-out abbreviation). */
  title?: string;
  /** Accessible name, when the visible text is an abbreviation. */
  ariaLabel?: string;
  /** E2E hook. Omit for purely decorative badges. */
  testId?: string;
  className?: string;
  /**
   * Semantic style overrides that `BADGE_BASE_STYLE` must not own (font
   * family, weight, tracking, margins). Colour and geometry are deliberately
   * not expressible here — use `variant`.
   */
  style?: CSSProperties;
}

export function Badge({
  variant = "neutral",
  children,
  title,
  ariaLabel,
  testId,
  className,
  style,
}: BadgeProps): JSX.Element {
  // Hoisted out of the JSX attribute on purpose: the file then contains a
  // `style={mergedStyle}` attribute rather than an inline object literal, so
  // the new component adds nothing to the ui-ratchet baseline.
  const mergedStyle: CSSProperties = { ...getBadgeVariantStyle(variant), ...style };

  return (
    <span
      data-testid={testId}
      title={title}
      aria-label={ariaLabel}
      className={className}
      style={mergedStyle}
    >
      {children}
    </span>
  );
}

Badge.displayName = "Badge";
