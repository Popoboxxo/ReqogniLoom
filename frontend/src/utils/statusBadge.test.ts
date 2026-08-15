/**
 * Tests for the status -> badge-variant classifier (REQ-L2-RF-030).
 */

import { describe, it, expect } from 'vitest';
import { resolveBadgeVariant } from './statusBadge';

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
