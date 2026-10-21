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
 * plan Phase 5a (docs/plans/2026-10-15-frontend-audit-fixes.md, §5 bullet 5a;
 * FE-01/F-03): this file used to be a 588-LOC God-Component carrying three
 * unrelated concerns. It now orchestrates two focused hooks —
 * `useWorkspaceLanguage` (language override + i18next restore) and
 * `useWorkspacePreferences` (per-user visibility overrides) — and keeps only
 * workspace *selection*, the terminology lookup and the Context value. The
 * public `WorkspaceState` API is unchanged 1:1.
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
  type ReactNode,
} from "react";
import type {
  Workspace,
  WorkspacePreset,
  TerminologyProfile,
} from "../types";
import { TERMINOLOGY_LABELS } from "../types";
import { workspacesApi } from "../api/workspaces";
import {
  type FeatureOverrides,
  type OptionalArtifactFeature,
} from "../api/preferences";
import { useAuth } from "./AuthContext";
import { safeSessionStorage } from "../utils/safeStorage";
import { useWorkspaceLanguage } from "../hooks/useWorkspaceLanguage";
import { useWorkspacePreferences } from "../hooks/useWorkspacePreferences";
// Theme Presets: WorkspaceContext no longer seeds a workspace `theme` into
// the theme system — ThemeContext resolves (paletteKey, mode) itself from
// user preference > tenant default > fallback. Workspace.theme stays a
// backend field but is functionally superseded (see design spec).

// Normalize preset field: backend may return {name: "extended"}, {tier: "minimal", language, terminology_profile}, or "extended"
function normalizePreset(ws: Workspace): Workspace {
  const raw = ws.preset as unknown;
  if (typeof raw === "object" && raw !== null) {
    const blob = raw as Record<string, unknown>;
    if (typeof blob.name === "string") {
      return { ...ws, preset: blob.name as WorkspacePreset };
    }
    if (typeof blob.tier === "string") {
      const p = raw as { tier: string; language?: string; terminology_profile?: string; decomposition_link_type?: string };
      return {
        ...ws,
        preset: p.tier as WorkspacePreset,
        language: ws.language ?? p.language,
        terminology_profile: ws.terminology_profile ?? (p.terminology_profile as import("../types").TerminologyProfile | undefined),
        decomposition_link_type: ws.decomposition_link_type ?? p.decomposition_link_type,
      };
    }
    // Malformed/empty preset blob (e.g. `{}` from a workspace created without
    // a preset): fall back to a valid tier. Without this a single bad row
    // crashed the whole dashboard, because `WorkspaceCard` renders
    // `workspace.preset` as a React child and an object is not a valid child.
    return { ...ws, preset: "standard" };
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
  // language-restore effect owned by `useWorkspaceLanguage` must not
  // overwrite `i18next.language` from `activeWorkspace.language` on some
  // unrelated `reloadWorkspaces()` call (workspace switch aside — that one
  // explicitly clears it via `setActiveWorkspace`).
  markLanguageOverrideActive: () => void;
  clearLanguageOverride: () => void;
}

// ---------------------------------------------------------------------------
// Defaults (used until workspace loads / fallback)
// ---------------------------------------------------------------------------

// Allow E2E tests (and future workspace bootstrap) to override the workspace ID
// by storing a real UUID in sessionStorage under "reqflow_workspace_id".
const _storedWorkspaceId = safeSessionStorage.getItem("reqflow_workspace_id");

// Exported (not just module-local) so callers outside this file — e.g. the
// sidebar language toggle (F-04) — can reliably detect "no real workspace
// loaded yet" via reference equality, the same way the language hook's effect
// does, instead of PATCHing the placeholder's fake UUID and swallowing the
// resulting 404.
export const DEFAULT_WORKSPACE: Workspace = {
  id: _storedWorkspaceId ?? "00000000-0000-0000-0000-000000000000",
  name: "",
  preset: "standard",
  terminology_profile: "se_mode",
  language: "en",
  theme: "dark",
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
  const { isAuthenticated, status: authStatus } = useAuth();

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

  // Language override + i18next restore (F-04-Residual, BUG-01/REQ-133).
  const { markLanguageOverrideActive, clearLanguageOverride } =
    useWorkspaceLanguage({
      isWorkspaceReady,
      activeWorkspace,
      defaultWorkspace: DEFAULT_WORKSPACE,
    });

  const setActiveWorkspace = useCallback(
    (ws: Workspace | null) => {
      setActiveWorkspaceState(ws);
      // An explicit workspace switch is the one case where "the language
      // should now follow the (new) workspace's persisted value" is exactly
      // right — clear any override left over from the previous workspace.
      clearLanguageOverride();
      if (ws) {
        safeSessionStorage.setItem("reqflow_workspace_id", ws.id);
      }
    },
    [clearLanguageOverride]
  );

  // Reusable loader so callers can refresh workspaces (e.g. after create).
  const reloadWorkspaces = useCallback(
    async (selectId?: string): Promise<void> => {
      setIsLoadingWorkspace(true);
      try {
        // Code-review GESAMTTEST_BERICHT §10.2 (Critical): `list()` only
        // returns page 1 (default page size 25) — a tenant with more
        // workspaces than that had entries #26+ unreachable via the UI
        // switcher (no pagination, no search there). `listAll()` follows
        // `next` across all pages via the shared `getAllPages` helper.
        const all = await workspacesApi.listAll();
        const list = all.map(normalizePreset);
        setWorkspaces(list);
        if (list.length > 0) {
          const storedId = safeSessionStorage.getItem("reqflow_workspace_id");
          const preferredId = selectId ?? storedId;
          const selected =
            (preferredId && list.find((w) => w.id === preferredId)) || list[0];
          setActiveWorkspaceState(selected);
          safeSessionStorage.setItem("reqflow_workspace_id", selected.id);
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
      clearLanguageOverride();
      // #568 final-review fix (2 rounds): the naive `!isAuthenticated`
      // guard is TRUE both during the transient "restoring" phase (every
      // fresh mount starts here, before the session check resolves — see
      // AuthContext.tsx's `AuthStatus`) and on a confirmed "anonymous"
      // Theme Presets: the theme-override machinery (seed/reset dance) was
      // removed together with the workspace-theme restore effect —
      // ThemeContext owns theme resolution end to end now, so there is no
      // local override state left to reset on logout.
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
  }, [isAuthenticated, authStatus, reloadWorkspaces, clearLanguageOverride]);

  // Theme Presets: the workspace-default-theme restore effect was removed —
  // ThemeContext now owns theme resolution end to end (server-side user
  // preference + tenant default), so a workspace row can no longer override it.

  // Per-user preferences: owned by `useWorkspacePreferences` (REQ-L1-027).
  const {
    userOverrides,
    hideAllOptional,
    isFeatureVisible,
    setFeatureVisible,
    setHideAllOptional,
    resetFeatureOverride,
    isFeatureOverridden,
  } = useWorkspacePreferences({
    isAuthenticated,
    isWorkspaceReady,
    activeWorkspace,
  });

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

/**
 * Non-throwing reader — `null` when no `WorkspaceProvider` is mounted.
 *
 * Exists for the hooks that model "no workspace to resolve against" as an
 * explicit state instead of an error (`useArtifactDefinition`,
 * `useCreateFormFields`, `useFieldContract`). They used to reach it through a
 * `try`/`catch` around `useWorkspace()`, which also swallowed any future throw
 * from inside `useWorkspace` itself into a silent "no workspace" state.
 * Everything else keeps using `useWorkspace()` and its loud failure.
 */
export function useOptionalWorkspace(): WorkspaceState | null {
  return useContext(WorkspaceContext);
}

