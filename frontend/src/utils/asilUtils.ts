/**
 * ASIL Level Utilities — REQ-L3-RF004-004
 *
 * Helper functions for ASIL (Automotive Safety Integrity Level) rendering,
 * color coding, and label mapping.
 */

import type { ASILLevel } from '../types';

/**
 * Maps ASIL level to human-readable label and description.
 *
 * @param level - ASIL level (QM, A, B, C, D) or null
 * @returns Object with label and description
 */
export function getAsilLabel(
  level: ASILLevel
): { label: string; description: string } {
  switch (level) {
    case 'QM':
      return {
        label: 'QM — No Functional Safety',
        description: 'Quality Management level (no functional safety required)',
      };
    case 'A':
      return {
        label: 'A — Low',
        description: 'ASIL A: Low functional safety integrity',
      };
    case 'B':
      return {
        label: 'B — Medium',
        description: 'ASIL B: Medium functional safety integrity',
      };
    case 'C':
      return {
        label: 'C — High',
        description: 'ASIL C: High functional safety integrity',
      };
    case 'D':
      return {
        label: 'D — Highest',
        description: 'ASIL D: Highest functional safety integrity',
      };
    default:
      return {
        label: 'Not set',
        description: 'ASIL level not specified',
      };
  }
}

/**
 * Returns CSS color for ASIL level badge.
 *
 * @param level - ASIL level
 * @returns Color string (var(--color-*) or hex)
 */
export function getAsilColor(level: ASILLevel): string {
  switch (level) {
    case 'QM':
      return '#9CA3AF'; // gray
    case 'A':
      return '#FBBF24'; // amber/yellow
    case 'B':
      return '#F97316'; // orange
    case 'C':
      return '#EF4444'; // red
    case 'D':
      return '#7F1D1D'; // dark red
    default:
      return '#D1D5DB'; // light gray
  }
}

/**
 * Returns background and text colors for ASIL badge.
 *
 * @param level - ASIL level
 * @returns { background, text } color pair
 */
export function getAsilBadgeStyle(level: ASILLevel): {
  background: string;
  text: string;
} {
  switch (level) {
    case 'QM':
      return { background: '#F3F4F6', text: '#4B5563' };
    case 'A':
      return { background: '#FEF3C7', text: '#92400E' };
    case 'B':
      return { background: '#FFEDD5', text: '#9A3412' };
    case 'C':
      return { background: '#FEE2E2', text: '#991B1B' };
    case 'D':
      return { background: '#7F1D1D', text: '#FFFFFF' };
    default:
      return { background: '#F3F4F6', text: '#6B7280' };
  }
}

/**
 * Make-or-Buy decision options.
 */
export const MAKE_OR_BUY_OPTIONS = [
  { value: 'Make', label: 'Make (develop in-house)' },
  { value: 'Buy', label: 'Buy (commercial off-the-shelf)' },
  { value: 'Reuse', label: 'Reuse (from existing component)' },
] as const;

/**
 * ASIL level options for dropdown.
 */
export const ASIL_LEVEL_OPTIONS = [
  { value: 'QM', label: 'QM — No Functional Safety' },
  { value: 'A', label: 'A — Low' },
  { value: 'B', label: 'B — Medium' },
  { value: 'C', label: 'C — High' },
  { value: 'D', label: 'D — Highest' },
] as const;
