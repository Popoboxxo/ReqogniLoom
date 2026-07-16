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

const DEFAULT_WORKSPACE: Workspace = {
  id: _storedWorkspaceId ?? "00000000-0000-0000-0000-000000000000",
  name: "Default Workspace",
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
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState<boolean>(false);
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

  const setActiveWorkspace = useCallback((ws: Workspace | null) => {
    setActiveWorkspaceState(ws);
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
          const preset: WorkspacePreset = activeWorkspace.preset ?? "standard";
          const overridden = new Set<OptionalArtifactFeature>();
          for (const f of OPTIONAL_FEATURES) {
            if (PRESET_VISIBILITY[preset][f] !== pref.overrides[f]) {
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
      // Optimistic local update — keep overrides sparse.
      const prev = userOverridesRef.current;
      const next: FeatureOverrides = { ...(prev ?? {}), [feature]: value };
      setUserOverrides(next);
      userOverridesRef.current = next;
      const nextKeys = new Set(overriddenKeysRef.current);
      nextKeys.add(feature);
      setOverriddenKeys(nextKeys);
      overriddenKeysRef.current = nextKeys;
      try {
        await preferencesApi.update(workspaceId, { [feature]: value });
      } catch (err) {
        // Rollback on failure.
        setUserOverrides(prev);
        userOverridesRef.current = prev;
        const rolledKeys = new Set(overriddenKeysRef.current);
        rolledKeys.delete(feature);
        setOverriddenKeys(rolledKeys);
        overriddenKeysRef.current = rolledKeys;
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

  const value: WorkspaceState = {
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
  };

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
