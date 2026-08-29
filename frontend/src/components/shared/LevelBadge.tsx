/**
 * ARCH-L1-001 ReactFrontend — <LevelBadge> (UI concept ch. 12.4).
 *
 * Shows the position of an artifact in the derivation tree (`L0`, `L1`, …)
 * or a short type marker next to the title.
 *
 * Explicitly **neutral**: a level is not a state (ch. 3.3, ch. 8.3). The
 * pre-existing coloured `L0`/`SR` badges were the concrete finding behind
 * that rule — a green `SR` reads as "approved" to anyone who learned the
 * status palette.
 *
 * Note on depth: `ArchitectureElement.get_level()` returns the real tree
 * depth (ch. 5.1), not an enum, so this component takes whatever number the
 * backend annotated and does not validate it against a fixed L0–L4 range.
 *
 * This is the **single** level-badge implementation (issue #674); the
 * `ui-ratchet` suite freezes that count at 1. `WorkspaceTree` used to carry
 * its own colour-ramped copy — see the note there for why the colour went
 * away rather than moving in here.
 */

import { BADGE_BASE_STYLE } from "../../utils/badgeBase";

export interface LevelBadgeProps {
  /** Tree depth. Rendered as `L{level}` when no explicit label is given. */
  level?: number | null;
  /** Explicit label, e.g. a type marker. Takes precedence over `level`. */
  label?: string | null;
  /** Native tooltip, e.g. the spelled-out level name. */
  title?: string;
  testId?: string;
}

export function LevelBadge({
  level,
  label,
  title,
  testId = "level-badge",
}: LevelBadgeProps): JSX.Element | null {
  const text = label ?? (level != null ? `L${level}` : null);
  if (!text) return null;

  return (
    <span
      data-testid={testId}
      title={title}
      aria-label={title}
      style={{
        ...BADGE_BASE_STYLE,
        border: "1px solid var(--color-border)",
        background: "var(--color-badge-neutral-bg)",
        color: "var(--color-badge-neutral-text)",
        // Kept local (ch. 9): `L0`-style labels are all-caps short text, which
        // needs the wide tracking to stay legible. Not part of the shared base
        // because most badges render mixed-case words.
        letterSpacing: "var(--tracking-wide)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {text}
    </span>
  );
}
