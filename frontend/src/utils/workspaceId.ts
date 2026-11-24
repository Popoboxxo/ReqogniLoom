/**
 * Standalone placeholder-id check for first-load request gates.
 *
 * Kept free of any WorkspaceContext import on purpose: widely consumed hooks
 * need this predicate, and importing a named export from WorkspaceContext would
 * force every WorkspaceContext mock in the test suite to expose it too.
 */

/** The fake UUID WorkspaceContext uses until a real workspace resolves. */
export const PLACEHOLDER_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000";

/** True for the placeholder id (and only for it), including a null id. */
export function isPlaceholderWorkspaceId(
  id: string | null | undefined
): boolean {
  return id === PLACEHOLDER_WORKSPACE_ID;
}
