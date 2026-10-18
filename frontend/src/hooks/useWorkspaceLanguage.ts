/**
 * ARCH-L1-001 ReactFrontend — workspace language ownership hook.
 *
 * plan Phase 5a (docs/plans/2026-10-15-frontend-audit-fixes.md, §5 bullet 5a;
 * frontend audit FE-01/F-03 "WorkspaceContext is a 588-LOC God-Component").
 *
 * Extracted verbatim from `context/WorkspaceContext.tsx`: the module (a) owns
 * the `hasLocalLanguageOverride` flag, (b) exposes the two mutators the
 * Context value re-exports, and (c) runs the workspace→i18next language
 * restore effect.
 *
 * The provider still owns workspace *selection* (it is shared with the
 * preference hook), so the two inputs the restore effect re-evaluates on —
 * `isWorkspaceReady` and `activeWorkspace` — are passed in; the
 * `defaultWorkspace` sentinel is passed in too (rather than imported) so this
 * hook does not have to depend on the context module that consumes it
 * (avoids a circular import while keeping `DEFAULT_WORKSPACE` exported from
 * its original home).
 *
 * Behaviour is unchanged, including the exact guard order of the restore
 * effect: `isWorkspaceReady` → `activeWorkspace === defaultWorkspace` →
 * `hasLocalLanguageOverride` → `i18next.isInitialized`.
 *
 * OWNERSHIP NOTE: this hook is intended to be called exactly once, by
 * `WorkspaceProvider`. Its `changeLanguage` side effect is deliberately keyed
 * to the inputs above — calling it twice would apply the same workspace value
 * twice, which is idempotent but pointless.
 */

import { useCallback, useEffect, useState } from "react";
// Code-review F-01 (BLOCKER): import the raw `i18next` singleton, NOT
// `../i18n/index` — that barrel eagerly runs `.use(initReactI18next)` at
// module load (a side effect of importing `react-i18next`). WorkspaceContext
// is a root provider transitively imported by nearly every component test;
// pulling that side effect in broke every test file that partially mocks
// `react-i18next` without exporting `initReactI18next` (import-time crash,
// "0 tests collected" — 19 test files, ~154 tests). `i18next` itself has no
// such dependency, and it is the very same singleton instance `../i18n/index`
// configures (module resolution dedupes it), so reading/writing `.language`
// here observes the identical state.
import i18next from "i18next";
import type { Workspace } from "../types";

export interface UseWorkspaceLanguageOptions {
  /** True once the workspace bootstrap resolved at least once. */
  isWorkspaceReady: boolean;
  /** Currently selected workspace (or the placeholder / null). */
  activeWorkspace: Workspace | null;
  /**
   * Reference-equality sentinel for "no real workspace loaded yet"
   * (see `DEFAULT_WORKSPACE` in `WorkspaceContext.tsx`).
   */
  defaultWorkspace: Workspace;
}

export interface UseWorkspaceLanguageResult {
  /**
   * True while a language choice that is NOT (yet, or ever going to be)
   * reflected in `activeWorkspace.language` is active — a non-admin's
   * session-local toggle, or an admin PATCH that failed. The restore effect
   * must not overwrite `i18next.language` from `activeWorkspace.language`
   * while this is set.
   */
  hasLocalLanguageOverride: boolean;
  /** Mark a local/unpersisted language choice active. */
  markLanguageOverrideActive: () => void;
  /** Drop the local override (workspace switch, logout). */
  clearLanguageOverride: () => void;
}

/**
 * Round-trip the persisted UI language from the active workspace into
 * `i18next` (BUG-01, REQ-133) while honouring a local override flag.
 */
export function useWorkspaceLanguage({
  isWorkspaceReady,
  activeWorkspace,
  defaultWorkspace,
}: UseWorkspaceLanguageOptions): UseWorkspaceLanguageResult {
  // Code-review F-04-Residual: deliberately state (not just a ref) — its
  // truthiness is read inside the restore effect's dependency array.
  const [hasLocalLanguageOverride, setHasLocalLanguageOverride] =
    useState<boolean>(false);

  const markLanguageOverrideActive = useCallback((): void => {
    setHasLocalLanguageOverride(true);
  }, []);
  const clearLanguageOverride = useCallback((): void => {
    setHasLocalLanguageOverride(false);
  }, []);

  // Restore the persisted UI language from the active workspace (BUG-01,
  // REQ-133). `i18n/index.ts` only seeds the initial language from the
  // browser locale — nothing re-applied the value already saved via
  // `PATCH /workspaces/{id}/` after that. Without this, any language choice
  // (whether made here or via the sidebar quick-toggle) survived only until
  // the next real navigation/reload, which reset `i18n.language` back to
  // the browser default — exactly the "falls back to German" symptom.
  //
  // Code-review F-03 (Medium): `isWorkspaceReady` alone is NOT sufficient to
  // guard against the DEFAULT_WORKSPACE placeholder — `reloadWorkspaces`
  // sets `isWorkspaceReady = true` in its `finally` block on *every* path,
  // including the empty-list and network-failure branches that fall back to
  // `DEFAULT_WORKSPACE` (whose `language` is hardcoded `"en"`). Without the
  // extra reference check below, a German-browser user whose
  // `GET /workspaces/` fails (or who has no workspaces yet) would have their
  // UI silently forced to English — a regression on the error path this fix
  // must not introduce. `activeWorkspace === defaultWorkspace` is a
  // reference-equality check on purpose: `reloadWorkspaces` assigns that
  // exact object (not a copy) on both fallback branches, so this reliably
  // distinguishes "no real workspace loaded" from "a real workspace whose id
  // happens to match".
  //
  // Code-review F-04-Residual: this effect's dependency array includes
  // `activeWorkspace`, and `reloadWorkspaces` assigns a *new* object on
  // every call — including calls that have nothing to do with language
  // (preset change, name save, per-user visibility toggle, ...). Before the
  // `hasLocalLanguageOverride` guard, any of those unrelated reloads re-ran
  // this effect and silently snapped `i18next.language` back to the
  // persisted `activeWorkspace.language` — overwriting a non-admin's
  // session-local toggle (F-02) or re-applying a value an admin's PATCH had
  // actually failed to save (F-04) with zero indication to the user. That is
  // BUG-01's original symptom class, reproduced by this fix itself in a new
  // scenario.
  useEffect(() => {
    if (!isWorkspaceReady) return;
    if (activeWorkspace === defaultWorkspace) return;
    if (hasLocalLanguageOverride) return;
    // `i18next.init()` (called once, from `i18n/index.ts`, at app bootstrap
    // before anything renders) has not necessarily run in every test that
    // mounts WorkspaceProvider without also loading that bootstrap module —
    // `changeLanguage` on an uninitialized instance throws internally
    // (`hasLanguageSomeTranslations` on an undefined resource store). In the
    // real app this is always true by the time this effect can fire.
    if (!i18next.isInitialized) return;
    const lang = activeWorkspace?.language;
    if (!lang || i18next.language === lang) return;
    void i18next.changeLanguage(lang);
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
    }
  }, [isWorkspaceReady, activeWorkspace, defaultWorkspace, hasLocalLanguageOverride]);

  return {
    hasLocalLanguageOverride,
    markLanguageOverrideActive,
    clearLanguageOverride,
  };
}
