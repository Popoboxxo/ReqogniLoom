/**
 * Tests for the status -> badge-variant classifier (REQ-L2-RF-030).
 */

import { describe, it, expect } from 'vitest';
import { BADGE_BASE_STYLE } from './badgeBase';
import {
  getBadgeVariantStyle,
  getStatusBadgeStyle,
  resolveBadgeVariant,
  type BadgeVariant,
} from './statusBadge';

describe('resolveBadgeVariant', () => {
  it('classifies the German "archiviert" state as the warning family', () => {
    expect(resolveBadgeVariant('archiviert')).toBe('warning');
  });

  it('classifies the English "archived" state as the warning family', () => {
    // Review finding 3: the map previously only listed "archiviert", even
    // though the surrounding comment already names both "outdated" and
    // "archived" as the intended warning-family states. A Goal/MainGoal
    // workflow using the English state name fell through to the
    // `lifecycleTransitions` list instead of being recognised as the
    // dedicated, confirmation-required archive move (goal-workflow.ts
    // `isArchiveTransition`).
    expect(resolveBadgeVariant('archived')).toBe('warning');
  });

  it('is case- and whitespace-insensitive for the archived state', () => {
    expect(resolveBadgeVariant(' Archived ')).toBe('warning');
  });

  it('falls back to neutral for an unrecognised state', () => {
    expect(resolveBadgeVariant('some-custom-state')).toBe('neutral');
  });

  it('prefers an explicit badgeVariant override over the name-based table', () => {
    expect(resolveBadgeVariant('archived', 'success')).toBe('success');
  });
});

/**
 * Issue #675 — the variant contract every badge in the app renders through.
 *
 * These are the two halves of "the same state must look the same everywhere":
 * a state resolves to a variant (`resolveBadgeVariant`) and a variant resolves
 * to exactly one token pair (`getBadgeVariantStyle`). Both tables are frozen
 * here, so re-colouring one call site's badge cannot happen silently.
 */
describe('badge variant contract (issue #675)', () => {
  /** variant -> the ONLY token pair it may render with. */
  const VARIANT_TOKENS: Record<BadgeVariant, { bg: string; text: string }> = {
    success: { bg: 'var(--color-badge-success-bg)', text: 'var(--color-badge-success-text)' },
    info: { bg: 'var(--color-badge-info-bg)', text: 'var(--color-badge-info-text)' },
    warning: { bg: 'var(--color-badge-warning-bg)', text: 'var(--color-badge-warning-text)' },
    danger: { bg: 'var(--color-badge-danger-bg)', text: 'var(--color-badge-danger-text)' },
    neutral: { bg: 'var(--color-badge-neutral-bg)', text: 'var(--color-badge-neutral-text)' },
  };

  const ALL_VARIANTS = Object.keys(VARIANT_TOKENS) as BadgeVariant[];

  it.each(ALL_VARIANTS)('maps variant "%s" onto its single token pair', (variant) => {
    const style = getBadgeVariantStyle(variant);
    expect(style.background).toBe(VARIANT_TOKENS[variant].bg);
    expect(style.color).toBe(VARIANT_TOKENS[variant].text);
  });

  it('gives every variant the identical box model (geometry is not variant-specific)', () => {
    for (const variant of ALL_VARIANTS) {
      const style = getBadgeVariantStyle(variant);
      expect(style.minHeight).toBe(BADGE_BASE_STYLE.minHeight);
      expect(style.padding).toBe(BADGE_BASE_STYLE.padding);
      expect(style.borderRadius).toBe(BADGE_BASE_STYLE.borderRadius);
      expect(style.fontSize).toBe(BADGE_BASE_STYLE.fontSize);
    }
  });

  it('falls back to neutral for an unknown/absent variant', () => {
    expect(getBadgeVariantStyle(null).background).toBe(VARIANT_TOKENS.neutral.bg);
    expect(getBadgeVariantStyle(undefined).color).toBe(VARIANT_TOKENS.neutral.text);
  });

  /**
   * The documented state -> variant mapping. `blocked` is deliberately
   * `warning`, not `danger` (UI-55): "we tried and could not" needs attention
   * but is not a rejection — and it must not look like the untouched
   * `not_run` neutral either.
   */
  const STATE_VARIANTS: Array<[string, BadgeVariant]> = [
    // success — approved / verified / done
    ['approved', 'success'],
    ['verified', 'success'],
    ['mitigated', 'success'],
    ['freigegeben', 'success'],
    // info — in progress / proposed
    ['in_review', 'info'],
    ['in progress', 'info'],
    ['proposed', 'info'],
    ['submitted', 'info'],
    // warning — recoverable / needs attention
    ['blocked', 'warning'],
    ['skipped', 'warning'],
    ['archived', 'warning'],
    ['suspect', 'warning'],
    // danger — rejected / failed / withdrawn
    ['rejected', 'danger'],
    ['failed', 'danger'],
    ['deprecated', 'danger'],
    ['superseded', 'danger'],
    // neutral — not started / informational
    ['draft', 'neutral'],
    ['entwurf', 'neutral'],
    ['open', 'neutral'],
    ['accepted', 'neutral'],
    ['not_run', 'neutral'],
  ];

  it.each(STATE_VARIANTS)('classifies state "%s" as "%s"', (state, variant) => {
    expect(resolveBadgeVariant(state)).toBe(variant);
    // ... and the status-badge style helper is not a second mapping: it must
    // render exactly the variant's token pair.
    expect(getStatusBadgeStyle(state)).toEqual(getBadgeVariantStyle(variant));
  });

  it('is case- and whitespace-insensitive for every documented state', () => {
    for (const [state, variant] of STATE_VARIANTS) {
      expect(resolveBadgeVariant(`  ${state.toUpperCase()}  `)).toBe(variant);
    }
  });
});
