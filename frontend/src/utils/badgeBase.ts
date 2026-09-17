/**
 * Shared geometry for every badge in the app (issue #675).
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * The three shared badge components had drifted into three different box
 * models — `<StatusBadge>` (via `getStatusBadgeStyle`) rendered a
 * `--radius-full` pill at `--font-size-sm`, `<VersionBadge>` a `--radius-sm`
 * rectangle at `--font-size-xs`, `<LevelBadge>` a `--radius-sm` rectangle
 * whose height came from a `line-height: 1.8` trick rather than padding. In
 * `<ArtifactRow>` all three sit on the same line (UI concept ch. 12.4), so
 * the mismatch was directly visible as three different pill heights and two
 * different corner radii in one row.
 *
 * ## What this constant does and does not own
 *
 * It owns only the **semantically meaningless** part of a badge: box model,
 * corner radius and text size. Those carry no information, so they must be
 * identical everywhere.
 *
 * It deliberately does NOT own colour, font family, letter-spacing or weight
 * — in this app those are load-bearing and differ on purpose (ch. 8.1, the
 * "colour belongs to state" rule):
 *
 *   - `<StatusBadge>` is the *only* colour-coded badge; its palette comes
 *     from `getStatusBadgeStyle`'s variant map.
 *   - `<VersionBadge>` is neutral, `--font-mono` + `tabular-nums`, and
 *     carries the current/superseded distinction in its font *weight*, which
 *     is why weight stays overridable here.
 *   - `<LevelBadge>` is neutral by design (a level is not a state, ch. 3.3 /
 *     ch. 8.3) and adds `--tracking-wide` for its all-caps `L0`-style label.
 *
 * So this is a base, not a merge: unifying the colour channel too would
 * destroy the very distinction the badges exist to make.
 *
 * ## Why a TS constant and not a `.badge-base` CSS class
 *
 * Issue #675 proposed a `.badge-base` class in `styles/tokens.css`. Two facts
 * made that the wrong shape here:
 *
 *   1. `tokens.css` is, by its own file header, a pure two-layer *token*
 *      file (`--palette-*` primitives / `--color-*` semantics) and contains
 *      no CSS classes at all — shared component classes live in
 *      `global.css` (`.btn-primary`, `.glass-panel`, ...).
 *   2. More importantly, `getStatusBadgeStyle()` returns a `CSSProperties`
 *      object that three call sites (`StatusBadge`, `NeedList`,
 *      `WorkflowStatusEditor`) spread onto a `style` prop. A CSS class
 *      cannot reach those, so a class-based base would have unified two of
 *      the three badges and quietly left the status badge behind — i.e. it
 *      would have recreated the very drift the issue is about.
 *
 * A shared `CSSProperties` constant reaches every consumer, including
 * `getStatusBadgeStyle`, and matches the pattern already used next door
 * (`ACTIVE_CARD_STYLE` in `statusBadge.ts`).
 */

import type { CSSProperties } from 'react';

/**
 * Fixed outer height, in px, of every badge.
 *
 * `min-height` + `box-sizing: border-box` rather than a computed line box:
 * `<StatusBadge>` has no border while `<LevelBadge>` and `<VersionBadge>`
 * each have a 1px one, so without a border-box floor the bordered badges
 * would stand 2px taller than the unbordered one on the same row.
 */
const BADGE_HEIGHT = '22px';

/**
 * Box model, radius and text size shared by every badge.
 *
 * Spread it first and override only what is semantically meaningful:
 *
 * ```ts
 * { ...BADGE_BASE_STYLE, background: colors.bg, color: colors.color }
 * ```
 */
export const BADGE_BASE_STYLE: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  boxSizing: 'border-box',
  /* Never let a badge get squeezed by a flex sibling — tree rows and
     `<ArtifactRow>` both place badges next to a `flex: 1` title that would
     otherwise win the shrink negotiation and clip the badge text. */
  flexShrink: 0,
  minHeight: BADGE_HEIGHT,
  /* Horizontal rhythm inside a row is `--space-2` (UI concept ch. 9). The
     2px vertical is below the `--space-*` scale's smallest step (4px), which
     at this height would read as a button rather than a badge. */
  padding: `2px var(--space-2)`,
  borderRadius: 'var(--radius-sm)',
  /* ch. 9 assigns `--font-size-xs` (12px) to "Badges, Zähler, Fußnoten".
     `<StatusBadge>` was the outlier at `--font-size-sm`. */
  fontSize: 'var(--font-size-xs)',
  fontWeight: 'var(--weight-semibold)',
  lineHeight: '16px',
  whiteSpace: 'nowrap',
};
