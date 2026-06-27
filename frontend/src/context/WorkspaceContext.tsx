/**
 * ARCH-L1-001 ReactFrontend — Workspace Context.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-007 (Preset-basierte Sichtbarkeit),
 *          REQ-L2-RF-008 (Terminologie-Profil),
 *          REQ-L2-RF-012 (Workspace-Konfigurations-UI)
 *
 * Holds active workspace state and exposes preset/profile helpers.
 * After login the provider loads the real workspaces from
 * GET /api/v1/workspaces/ and selects the first one as active.
 * Falls back to DEFAULT_WORKSPACE only if the API call fails or
 * returns no workspaces (legacy / offline mode).
 */

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import type {
  Workspace,
  WorkspacePreset,
  TerminologyProfile,
} from "../types";
import { PRESET_VISIBILITY, TERMINOLOGY_LABELS } from "../types";
import { workspacesApi } from "../api/workspaces";
import { useAuth } from "./AuthContext";

// Normalize preset field: backend may return {name: "extended"} or "extended"
function normalizePreset(ws: Workspace): Workspace {
  const raw = ws.preset as unknown;
  if (typeof raw === "object" && raw !== null && "name" in raw) {
    return { ...ws, preset: (raw as { name: string }).name as WorkspacePreset };
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

  const setActiveWorkspace = useCallback((ws: Workspace | null) => {
    setActiveWorkspaceState(ws);
    if (ws && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem("reqflow_workspace_id", ws.id);
    }
  }, []);

  // Bootstrap workspaces after authentication (REQ-L2-RF-012)
  useEffect(() => {
    if (!isAuthenticated) {
      setWorkspaces([]);
      return;
    }

    let cancelled = false;
    setIsLoadingWorkspace(true);

    async function load(): Promise<void> {
      try {
        const resp = await workspacesApi.list();
        if (cancelled) return;
        const list = (resp.results ?? []).map(normalizePreset);
        setWorkspaces(list);
        if (list.length > 0) {
          // Prefer previously selected workspace if it still exists,
          // otherwise default to the first one.
          const storedId =
            typeof sessionStorage !== "undefined"
              ? sessionStorage.getItem("reqflow_workspace_id")
              : null;
          const selected =
            (storedId && list.find((w) => w.id === storedId)) || list[0];
          setActiveWorkspaceState(selected);
          if (typeof sessionStorage !== "undefined") {
            sessionStorage.setItem("reqflow_workspace_id", selected.id);
          }
        } else {
          // No workspaces returned — keep DEFAULT_WORKSPACE fallback.
          setActiveWorkspaceState(DEFAULT_WORKSPACE);
        }
      } catch {
        if (cancelled) return;
        // Fall back to DEFAULT_WORKSPACE on error (offline / legacy backend)
        setWorkspaces([]);
        setActiveWorkspaceState(DEFAULT_WORKSPACE);
      } finally {
        if (!cancelled) setIsLoadingWorkspace(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  // Preset-based feature visibility (REQ-L2-RF-007)
  const isFeatureVisible = useCallback(
    (feature: string): boolean => {
      const preset: WorkspacePreset = activeWorkspace?.preset ?? "standard";
      return PRESET_VISIBILITY[preset][feature] ?? true;
    },
    [activeWorkspace]
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

  const value: WorkspaceState = {
    activeWorkspace,
    workspaces,
    isLoadingWorkspace,
    setActiveWorkspace,
    isFeatureVisible,
    terminologyLabel,
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
