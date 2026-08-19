/**
 * ARCH-L1-001 ReactFrontend — Workspace Context.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-007 (Preset-basierte Sichtbarkeit),
 *          REQ-L2-RF-008 (Terminologie-Profil),
 *          REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L1-027 (Per-user visibility overrides)
 *
 * Holds active workspace state and exposes preset/profile/helpers plus
 * per-user visibility overrides.  After login the provider loads the
 * real workspaces from GET /api/v1/workspaces/ and selects the first
 * one as active.  Falls back to DEFAULT_WORKSPACE only if the API call
 * fails or returns no workspaces (legacy / offline mode).
 *
 * Visibility resolution order for ``isFeatureVisible``:
 *   1. hideAllOptional master switch (if feature is one of the 6 optional
 *      artifact types) → return false.
 *   2. userOverrides[feature] (if defined) → return it.
 *   3. PRESET_VISIBILITY[preset][feature] → return it.
 *   4. default → true.
 */

import { createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import type {
  Workspace,
  WorkspacePreset,
  TerminologyProfile,
} from "../types";
import { PRESET_VISIBILITY, TERMINOLOGY_LABELS } from "../types";
import { workspacesApi } from "../api/workspaces";
import {
  preferencesApi,
  OPTIONAL_FEATURES,
  type FeatureOverrides,
  type OptionalArtifactFeature,
} from "../api/preferences";
import { useAuth } from "./AuthContext";
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

// Normalize preset field: backend may return {name: "extended"}, {tier: "minimal", language, terminology_profile}, or "extended"
function normalizePreset(ws: Workspace): Workspace {
  const raw = ws.preset as unknown;
  if (typeof raw === "object" && raw !== null) {
    if ("name" in raw) {
      return { ...ws, preset: (raw as { name: string }).name as WorkspacePreset };
    }
    if ("tier" in raw) {
      const p = raw as { tier: string; language?: string; terminology_profile?: string; decomposition_link_type?: string };
      return {
        ...ws,
        preset: p.tier as WorkspacePreset,
        language: ws.language ?? p.language,
        terminology_profile: ws.terminology_profile ?? (p.terminology_profile as import("../types").TerminologyProfile | undefined),
        decomposition_link_type: ws.decomposition_link_type ?? p.decomposition_link_type,
      };
    }
  }
  return ws;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WorkspaceState {
  activeWorkspace: Workspace | null;
  workspaces: Workspace[];
  isLoadingWorkspace: boolean;
  setActiveWorkspace: (ws: Workspace | null) => void;
  isFeatureVisible: (feature: string) => boolean;
  terminologyLabel: (key: string) => string;
  reloadWorkspaces: (selectId?: string) => Promise<void>;
  // Per-user visibility overrides (REQ-L1-027)
  userOverrides: FeatureOverrides | null;
  hideAllOptional: boolean;
  setFeatureVisible: (feature: OptionalArtifactFeature, value: boolean) => Promise<void>;
  setHideAllOptional: (value: boolean) => Promise<void>;
  resetFeatureOverride: (feature: OptionalArtifactFeature) => Promise<void>;
  isFeatureOverridden: (feature: OptionalArtifactFeature) => boolean;
  // Code-review F-04-Residual: a language choice that is NOT (yet, or ever
  // going to be) reflected in `activeWorkspace.language` — a non-admin's
  // session-local toggle, or an admin PATCH that failed. While active, the
  // language-restore effect below must not overwrite `i18next.language`
  // from `activeWorkspace.language` on some unrelated `reloadWorkspaces()`
  // call (workspace switch aside — that one explicitly clears it via
  // `setActiveWorkspace`).
  markLanguageOverrideActive: () => void;
  clearLanguageOverride: () => void;
}

// ---------------------------------------------------------------------------
// Defaults (used until workspace loads / fallback)
// ---------------------------------------------------------------------------

// Allow E2E tests (and future workspace bootstrap) to override the workspace ID
// by storing a real UUID in sessionStorage under "reqflow_workspace_id".
const _storedWorkspaceId =
  typeof sessionStorage !== "undefined"
    ? sessionStorage.getItem("reqflow_workspace_id")
    : null;

// Exported (not just module-local) so callers outside this file — e.g. the
// sidebar language toggle (F-04) — can reliably detect "no real workspace
// loaded yet" via reference equality, the same way the effect above does,
// instead of PATCHing the placeholder's fake UUID and swallowing the
// resulting 404.
export const DEFAULT_WORKSPACE: Workspace = {
  id: _storedWorkspaceId ?? "00000000-0000-0000-0000-000000000000",
  name: "",
  preset: "standard",
  terminology_profile: "se_mode",
  language: "en",
  is_active: true,
  closed_at: null,
  closed_by: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const { isAuthenticated } = useAuth();

  const [activeWorkspace, setActiveWorkspaceState] = useState<Workspace | null>(
    DEFAULT_WORKSPACE
  );
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  // Starts true: until the bootstrap effect below resolves the real
  // auth/workspace state, activeWorkspace is only the DEFAULT_WORKSPACE
  // placeholder (fake UUID), so consumers must treat it as "not ready yet"
  // rather than fetch/display against it (issues #19, #24).
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState<boolean>(true);
  // True once reloadWorkspaces has completed at least once after auth.
  // The per-user-preference fetch only runs after this flag flips to true
  // (or the user explicitly picks a workspace via setActiveWorkspace),
  // so we don't burn an API call for the DEFAULT_WORKSPACE placeholder.
  const [isWorkspaceReady, setIsWorkspaceReady] = useState<boolean>(false);

  // Per-user visibility overrides (REQ-L1-027).
  // null = no preference row exists (or fetch failed) → use preset defaults.
  // Sparse: only the keys the user has actually set are present.
  const [userOverrides, setUserOverrides] = useState<FeatureOverrides | null>(
    null
  );
  const [hideAllOptional, setHideAllOptionalState] = useState<boolean>(false);

  // Track which keys the user has explicitly set, so the UI can show a
  // "Reset to preset" button only for features that are actually overridden.
  // Stored separately from userOverrides so that load-time defaults don't
  // get flagged as "user-set".
  const [overriddenKeys, setOverriddenKeys] = useState<
    Set<OptionalArtifactFeature>
  >(new Set());
  // Refs let async callbacks read the latest state without re-creating
  // the callbacks (which would re-trigger the fetch effect).
  const userOverridesRef = useRef<FeatureOverrides | null>(null);
  const hideAllOptionalRef = useRef<boolean>(false);
  const overriddenKeysRef = useRef<Set<OptionalArtifactFeature>>(new Set());

  // Code-review F-04-Residual (see `WorkspaceState.markLanguageOverrideActive`
  // doc comment above): tracks an unpersisted/local-only language choice so
  // the restore effect below can skip overwriting it on an unrelated
  // `reloadWorkspaces()` call. Deliberately state (not just a ref) — its
  // truthiness is read inside the restore effect's dependency array.
  const [hasLocalLanguageOverride, setHasLocalLanguageOverride] =
    useState<boolean>(false);
  const markLanguageOverrideActive = useCallback((): void => {
    setHasLocalLanguageOverride(true);
  }, []);
  const clearLanguageOverride = useCallback((): void => {
    setHasLocalLanguageOverride(false);
  }, []);

  const setActiveWorkspace = useCallback((ws: Workspace | null) => {
    setActiveWorkspaceState(ws);
    // An explicit workspace switch is the one case where "the language
    // should now follow the (new) workspace's persisted value" is exactly
    // right — clear any override left over from the previous workspace.
    setHasLocalLanguageOverride(false);
    if (ws && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem("reqflow_workspace_id", ws.id);
    }
  }, []);

  // Reusable loader so callers can refresh workspaces (e.g. after create).
  const reloadWorkspaces = useCallback(
    async (selectId?: string): Promise<void> => {
      setIsLoadingWorkspace(true);
      try {
        const resp = await workspacesApi.list();
        const list = (resp.results ?? []).map(normalizePreset);
        setWorkspaces(list);
        if (list.length > 0) {
          const storedId =
            typeof sessionStorage !== "undefined"
              ? sessionStorage.getItem("reqflow_workspace_id")
              : null;
          const preferredId = selectId ?? storedId;
          const selected =
            (preferredId && list.find((w) => w.id === preferredId)) || list[0];
          setActiveWorkspaceState(selected);
          if (typeof sessionStorage !== "undefined") {
            sessionStorage.setItem("reqflow_workspace_id", selected.id);
          }
        } else {
          setActiveWorkspaceState(DEFAULT_WORKSPACE);
        }
      } catch {
        setWorkspaces([]);
        setActiveWorkspaceState(DEFAULT_WORKSPACE);
      } finally {
        setIsLoadingWorkspace(false);
        setIsWorkspaceReady(true);
      }
    },
    []
  );

  // Bootstrap workspaces after authentication (REQ-L2-RF-012)
  useEffect(() => {
    if (!isAuthenticated) {
      setWorkspaces([]);
      setIsWorkspaceReady(false);
      setIsLoadingWorkspace(false);
      // Code-review R-02: WorkspaceProvider also wraps `/login`, and
      // `AuthContext.logout()` does not reload the page — without this, a
      // local/unpersisted language override left by the previous session
      // (e.g. a non-admin's session-local toggle) survived a logout and
      // silently overrode the *next* user's own persisted workspace
      // language on the very same tab.
      setHasLocalLanguageOverride(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      await reloadWorkspaces();
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, reloadWorkspaces]);

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
  // `DEFAULT_WORKSPACE` (whose `language` is hardcoded `"en"`). Without this
  // extra check, a German-browser user whose `GET /workspaces/` fails (or
  // who has no workspaces yet) would have their UI silently forced to
  // English — a regression on the error path this fix must not introduce.
  // `activeWorkspace === DEFAULT_WORKSPACE` is a reference-equality check on
  // purpose: `reloadWorkspaces` assigns that exact object (not a copy) on
  // both fallback branches, so this reliably distinguishes "no real
  // workspace loaded" from "a real workspace whose id happens to match".
  //
  // Code-review F-04-Residual: this effect's dependency array includes
  // `activeWorkspace`, and `reloadWorkspaces` assigns a *new* object on
  // every call — including calls that have nothing to do with language
  // (preset change, name save, per-user visibility toggle, switching to a
  // *different* workspace's own settings tab, ...; see the various
  // `reloadWorkspaces()` call sites in `WorkspaceSettings.tsx` and
  // `WorkspaceAdminSection.tsx`). Before the `hasLocalLanguageOverride`
  // guard, any of those unrelated reloads re-ran this effect and silently
  // snapped `i18next.language` back to the persisted `activeWorkspace
  // .language` — overwriting a non-admin's session-local toggle (F-02) or
  // re-applying a value an admin's PATCH had actually failed to save (F-04)
  // with zero indication to the user. That is BUG-01's original symptom
  // class, reproduced by this fix itself in a new scenario.
  useEffect(() => {
    if (!isWorkspaceReady) return;
    if (activeWorkspace === DEFAULT_WORKSPACE) return;
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
  }, [isWorkspaceReady, activeWorkspace, hasLocalLanguageOverride]);

  // Fetch per-user preferences whenever the active workspace changes (REQ-L1-027).
  // Gated on ``isWorkspaceReady`` so we don't burn an API call for the
  // DEFAULT_WORKSPACE placeholder on first render.
  useEffect(() => {
    if (!isAuthenticated || !activeWorkspace || !isWorkspaceReady) {
      setUserOverrides(null);
      setHideAllOptionalState(false);
      setOverriddenKeys(new Set());
      userOverridesRef.current = null;
      hideAllOptionalRef.current = false;
      overriddenKeysRef.current = new Set();
      return;
    }
    const workspaceId = activeWorkspace.id;
    let cancelled = false;
    void (async () => {
      try {
        const pref = await preferencesApi.get(workspaceId);
        if (cancelled) return;
        if (pref === null) {
          setUserOverrides(null);
          setHideAllOptionalState(false);
          setOverriddenKeys(new Set());
          userOverridesRef.current = null;
          hideAllOptionalRef.current = false;
          overriddenKeysRef.current = new Set();
        } else {
          setUserOverrides(pref.overrides);
          setHideAllOptionalState(pref.hideAllOptional);
          userOverridesRef.current = pref.overrides;
          hideAllOptionalRef.current = pref.hideAllOptional;
          // Only keys that differ from the preset get marked as "user-overridden".
          // ``pref.overrides`` is sparse — a feature the user never touched
          // is simply absent (``undefined``), not "explicitly set to the
          // opposite of the preset". Without the presence check below,
          // every untouched feature (`undefined`) compared against a
          // `true` preset default reads as "differs" and gets wrongly
          // marked overridden — reproducing BUG-16 on every page reload
          // (docs/SYSTEMAUDIT_2026-08-18.md §4, review finding F-01).
          const preset: WorkspacePreset = activeWorkspace.preset ?? "standard";
          const overridden = new Set<OptionalArtifactFeature>();
          for (const f of OPTIONAL_FEATURES) {
            const stored = pref.overrides[f];
            if (stored !== undefined && PRESET_VISIBILITY[preset][f] !== stored) {
              overridden.add(f);
            }
          }
          setOverriddenKeys(overridden);
          overriddenKeysRef.current = overridden;
        }
      } catch {
        // Network / unexpected error → fall back to preset defaults silently.
        if (cancelled) return;
        setUserOverrides(null);
        setHideAllOptionalState(false);
        setOverriddenKeys(new Set());
        userOverridesRef.current = null;
        hideAllOptionalRef.current = false;
        overriddenKeysRef.current = new Set();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, activeWorkspace, isWorkspaceReady]);

  // Feature visibility with override resolution (REQ-L1-027 + REQ-L2-RF-007).
  // 1) hideAllOptional wins for the 6 optional artifact features.
  // 2) userOverrides[feature] wins ONLY when the user has set that key
  //    (override is "defined" — the map is sparse by design).
  // 3) Otherwise fall through to the preset default.
  // 4) Final fallback: visible.
  const isFeatureVisible = useCallback(
    (feature: string): boolean => {
      const isOptional = (OPTIONAL_FEATURES as readonly string[]).includes(
        feature
      );
      if (isOptional && hideAllOptional) return false;
      if (isOptional && userOverrides) {
        const override = userOverrides[feature as OptionalArtifactFeature];
        if (override !== undefined) return override;
      }
      const preset: WorkspacePreset = activeWorkspace?.preset ?? "standard";
      return PRESET_VISIBILITY[preset][feature] ?? true;
    },
    [activeWorkspace, userOverrides, hideAllOptional]
  );

  // Terminology label lookup (REQ-L2-RF-008)
  const terminologyLabel = useCallback(
    (key: string): string => {
      const profile: TerminologyProfile =
        activeWorkspace?.terminology_profile ?? "se_mode";
      const labels = TERMINOLOGY_LABELS[profile];
      return (labels as Record<string, string>)[key] ?? key;
    },
    [activeWorkspace]
  );

  // ---- Per-user visibility mutators (REQ-L1-027) ------------------------

  const setFeatureVisible = useCallback(
    async (
      feature: OptionalArtifactFeature,
      value: boolean
    ): Promise<void> => {
      const workspaceId = activeWorkspace?.id;
      if (!workspaceId) return;
      // "Overridden" means the effective value differs from the preset
      // default — mirrors the load-time computation below (BUG-16 fix).
      // Previously this unconditionally added the feature to
      // ``overriddenKeys``, so ``resetFeatureOverride`` (which calls this
      // with the preset's own value) could never actually clear the
      // override flag and the reset button stayed permanently active.
      const preset: WorkspacePreset = activeWorkspace?.preset ?? "standard";
      const presetValue = PRESET_VISIBILITY[preset][feature] === true;
      // Optimistic local update — keep overrides sparse.
      const prev = userOverridesRef.current;
      const prevOverriddenKeys = overriddenKeysRef.current;
      const next: FeatureOverrides = { ...(prev ?? {}), [feature]: value };
      setUserOverrides(next);
      userOverridesRef.current = next;
      const nextKeys = new Set(prevOverriddenKeys);
      if (value !== presetValue) {
        nextKeys.add(feature);
      } else {
        nextKeys.delete(feature);
      }
      setOverriddenKeys(nextKeys);
      overriddenKeysRef.current = nextKeys;
      try {
        await preferencesApi.update(workspaceId, { [feature]: value });
      } catch (err) {
        // Rollback on failure — restore the exact previous overridden state
        // instead of assuming the feature was never overridden.
        setUserOverrides(prev);
        userOverridesRef.current = prev;
        setOverriddenKeys(prevOverriddenKeys);
        overriddenKeysRef.current = prevOverriddenKeys;
        throw err;
      }
    },
    [activeWorkspace]
  );

  const resetFeatureOverride = useCallback(
    async (feature: OptionalArtifactFeature): Promise<void> => {
      const workspaceId = activeWorkspace?.id;
      if (!workspaceId) return;
      // "Reset to preset" = set the override back to the preset value.
      const preset: WorkspacePreset = activeWorkspace?.preset ?? "standard";
      const presetValue = PRESET_VISIBILITY[preset][feature] === true;
      await setFeatureVisible(feature, presetValue);
    },
    [activeWorkspace, setFeatureVisible]
  );

  const setHideAllOptional = useCallback(
    async (value: boolean): Promise<void> => {
      const workspaceId = activeWorkspace?.id;
      if (!workspaceId) {
        setHideAllOptionalState(value);
        hideAllOptionalRef.current = value;
        return;
      }
      setHideAllOptionalState(value);
      hideAllOptionalRef.current = value;
      try {
        await preferencesApi.update(workspaceId, {
          _hide_all_optional: value,
        });
      } catch (err) {
        setHideAllOptionalState(!value);
        hideAllOptionalRef.current = !value;
        throw err;
      }
    },
    [activeWorkspace]
  );

  const isFeatureOverridden = useCallback(
    (feature: OptionalArtifactFeature): boolean =>
      overriddenKeys.has(feature),
    [overriddenKeys]
  );

  const value = useMemo<WorkspaceState>(
    () => ({
      activeWorkspace,
      workspaces,
      isLoadingWorkspace,
      setActiveWorkspace,
      isFeatureVisible,
      terminologyLabel,
      reloadWorkspaces,
      userOverrides,
      hideAllOptional,
      setFeatureVisible,
      setHideAllOptional,
      resetFeatureOverride,
      isFeatureOverridden,
      markLanguageOverrideActive,
      clearLanguageOverride,
    }),
    [
      activeWorkspace,
      workspaces,
      isLoadingWorkspace,
      setActiveWorkspace,
      isFeatureVisible,
      terminologyLabel,
      reloadWorkspaces,
      userOverrides,
      hideAllOptional,
      setFeatureVisible,
      setHideAllOptional,
      resetFeatureOverride,
      isFeatureOverridden,
      markLanguageOverrideActive,
      clearLanguageOverride,
    ]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx)
    throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
