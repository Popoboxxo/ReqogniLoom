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

import { BADGE_BASE_STYLE } from './badgeBase';

/**
 * The five semantic variants of UI concept ch. 8.2. Exported because
 * <StatusBadge> accepts an explicit variant, which is the seam a future
 * server-provided `badge_variant` on the workflow definition would plug
 * into (see resolveBadgeVariant).
 */
export type BadgeVariant = 'info' | 'danger' | 'success' | 'warning' | 'neutral';

/**
 * Geometry now comes from the app-wide badge base (issue #675). This used to
 * be a local `--radius-full` / `--font-size-sm` box, which made the status
 * badge visibly taller and rounder than the level and version badges sitting
 * next to it in the same `<ArtifactRow>` line. Only the colour channel — the
 * one thing that is semantically load-bearing here (ch. 8.1) — is still
 * decided in this file.
 */
const BADGE_BASE: CSSProperties = BADGE_BASE_STYLE;

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
 *
 * **One flat table across all domains — deliberate, not an oversight.**
 * The UI audit flagged that run status, result status and workflow status
 * share it, so a string cannot mean two things (`accepted` is approval for an
 * ADR but deliberate exposure for a Risk). Splitting it per domain was
 * rejected: `components/Goals/goal-workflow.ts` uses the *variant* as a
 * semantic classifier — `resolveBadgeVariant(state) === 'warning'` is how the
 * archive transition is found and `=== 'success'` how an approved goal is
 * counted, precisely so no German state name is hardcoded (issue #220). A
 * per-domain table would silently reclassify those states and break the Goal
 * lifecycle. Domain-specific colouring therefore goes through the explicit
 * `badgeVariant` argument at the call site, never through a second table.
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
  archived: 'warning',
  // Test-result vocabulary (`mcp_server/tools/tests.py::
  // _VALID_RUN_RESULT_STATUSES` = passed|failed|blocked|not_run, plus the
  // ReqIF/baseline "skipped"). Both were missing entirely, so a blocked
  // result rendered in the same neutral grey as an untouched `not_run` one —
  // i.e. "we tried and could not" was indistinguishable from "nobody looked
  // at it yet" (UI-55). `blocked` is a reported outcome that needs attention,
  // `skipped` is a deliberate omission.
  blocked: 'warning',
  skipped: 'warning',

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
