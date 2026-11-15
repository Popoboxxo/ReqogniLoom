/**
 * ASIL Level Utilities — REQ-L3-RF004-004
 *
 * Helper functions for ASIL (Automotive Safety Integrity Level) label mapping
 * and dropdown options.
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
