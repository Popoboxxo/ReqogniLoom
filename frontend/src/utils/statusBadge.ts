/**
 * Shared status badge styling for List components.
 *
 * Centralizes badge colors as CSS custom properties (see styles/tokens.css)
 * so every list renders theme-safe badges in both light and dark mode.
 * Previously each List defined its own hardcoded hex palette which broke
 * dark mode.
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 */

import type { CSSProperties } from 'react';

/**
 * The five semantic variants of UI concept ch. 8.2. Exported because
 * <StatusBadge> accepts an explicit variant, which is the seam a future
 * server-provided `badge_variant` on the workflow definition would plug
 * into (see resolveBadgeVariant).
 */
export type BadgeVariant = 'info' | 'danger' | 'success' | 'warning' | 'neutral';

const BADGE_BASE: CSSProperties = {
  borderRadius: 'var(--radius-full)',
  fontSize: 'var(--font-size-sm)',
  padding: '2px 8px',
  fontWeight: 500,
  whiteSpace: 'nowrap',
};

const VARIANT_COLORS: Record<BadgeVariant, { bg: string; color: string }> = {
  info: { bg: 'var(--color-badge-info-bg)', color: 'var(--color-badge-info-text)' },
  danger: { bg: 'var(--color-badge-danger-bg)', color: 'var(--color-badge-danger-text)' },
  success: { bg: 'var(--color-badge-success-bg)', color: 'var(--color-badge-success-text)' },
  warning: { bg: 'var(--color-badge-warning-bg)', color: 'var(--color-badge-warning-text)' },
  neutral: { bg: 'var(--color-badge-neutral-bg)', color: 'var(--color-badge-neutral-text)' },
};

/**
 * Maps raw status/type strings (any casing, space or underscore separated)
 * to a badge variant. Keys are lowercase; both `in_progress` and
 * `in progress` style spellings are covered.
 */
const STATUS_VARIANT_MAP: Record<string, BadgeVariant> = {
  // Positive / done
  approved: 'success',
  active: 'success',
  done: 'success',
  passed: 'success',
  resolved: 'success',
  implemented: 'success',
  verified: 'success',
  mitigated: 'success',
  // Goal / MainGoal workflow (backend/workflow/definition_store.py) uses
  // German state names; without these keys every Goal badge fell back to
  // neutral grey, i.e. "approved" and "draft" looked identical (ch. 8.2).
  freigegeben: 'success',

  // In-progress / under review
  review: 'info',
  in_review: 'info',
  'in review': 'info',
  in_progress: 'info',
  'in progress': 'info',
  monitored: 'info',
  submitted: 'info',
  under_review: 'info',
  'under review': 'info',
  ready: 'info',

  // Negative
  rejected: 'danger',
  deprecated: 'danger',
  failed: 'danger',
  wontfix: 'danger',
  superseded: 'danger',

  // Warning / attention — "outdated"/"archived" mean superseded but
  // recoverable, which ch. 8.2 maps to warning rather than danger.
  suspect: 'warning',
  partial: 'warning',
  outdated: 'warning',
  archiviert: 'warning',

  // Neutral / draft / terminal
  draft: 'neutral',
  entwurf: 'neutral',
  open: 'neutral',
  identified: 'neutral',
  accepted: 'neutral',
  closed: 'neutral',
  not_run: 'neutral',
};

/**
 * Resolves the semantic badge variant for a workflow state.
 *
 * UI concept ch. 8.2.1 wants this to come from the workflow definition
 * (`badge_variant` per state) so workspace-defined states get a deliberate
 * colour instead of a guess. That field does **not** exist in the backend
 * today — neither on WorkflowDefinition nor on any serializer — so the
 * signature already accepts it while the name-based table below stays the
 * fallback. Once the backend ships it, callers pass it through and this
 * table only serves legacy/unknown states.
 */
export const resolveBadgeVariant = (
  status: string,
  badgeVariant?: BadgeVariant | null,
): BadgeVariant => {
  if (badgeVariant && badgeVariant in VARIANT_COLORS) return badgeVariant;
  return STATUS_VARIANT_MAP[status.toLowerCase().trim()] ?? 'neutral';
};

/**
 * Returns the inline style for a status badge based on its raw status string.
 * Unknown statuses fall back to the neutral variant.
 */
export const getStatusBadgeStyle = (
  status: string,
  badgeVariant?: BadgeVariant | null,
): CSSProperties => {
  const colors = VARIANT_COLORS[resolveBadgeVariant(status, badgeVariant)];
  return { ...BADGE_BASE, background: colors.bg, color: colors.color };
};

/** Background style for the currently selected/active card in a list. */
export const ACTIVE_CARD_STYLE: CSSProperties = {
  backgroundColor: 'var(--color-card-active-bg)',
};

/** Raw token reference for use inside inline ternary background expressions. */
export const ACTIVE_CARD_BG = 'var(--color-card-active-bg)';
