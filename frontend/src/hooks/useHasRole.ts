/**
 * R2/T1 (systemaudit 2026-09-02): shared workspace-role gate.
 *
 * Extracted from the `hasRole` check Task 4 (R2/T1 nav-item gating,
 * SidebarNavigation.tsx) introduced first, so this and every later
 * consumer (RequirementForm/RequirementList/RequirementEditors Save/
 * Delete/Ableiten/Testfall-generieren/Status-ändern gating) share one
 * implementation instead of re-deriving the same `roles.includes(...)`
 * check independently. `admin` is treated as a superset of `editor` (and
 * of any other lesser role), matching every other admin check in the app.
 *
 * UX-only: real enforcement is server-side, same as every other role gate
 * in this codebase (see SidebarNavigation.tsx's NAV_ITEMS comment).
 */

import { useAuth } from '../context/AuthContext';

export type RequiredRole = 'admin' | 'editor';

export function useHasRole(): (required?: RequiredRole) => boolean {
  const { roles } = useAuth();
  return (required?: RequiredRole): boolean =>
    !required || roles.includes(required) || roles.includes('admin');
}
