/**
 * ARCH-L1-001 ReactFrontend — Q1 preference query/mutation hooks
 * (Plan C, T-C2-5).
 *
 * One cache namespace, `["preferences"]`, so a write invalidates every derived
 * read in one call: the level it wrote and the effective value that may have
 * moved with it.
 *
 * Degradation policy (binding): a failed load never blocks a render —
 * `usePreferenceValue` answers the caller's `fallback` (the registry default in
 * the consuming code) until the network answers and on error. Only the settings
 * surface itself shows the error.
 *
 * Visibility of the effective read: with a workspace id the workspace route
 * answers (`user > workspace > global > default`); `null` selects the
 * account-wide read (`user > global > default`), which is also the right source
 * for `SystemSettings` — there is no level below `global` to resolve.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  preferenceValuesApi,
  type PreferenceEffective,
  type PreferenceLevel,
  type PreferenceScope,
} from "../api/preference-values";
import { useOptionalWorkspace } from "../context/WorkspaceContext";

/** Five minutes: preferences change on a settings page, not mid-session. */
const PREFERENCES_STALE_TIME_MS = 5 * 60 * 1000;

export const preferenceKeys = {
  /** Prefix for every preference cache entry; a write invalidates this. */
  all: ["preferences"] as const,
  registry: () => ["preferences", "registry"] as const,
  effective: (workspaceId: string | null) =>
    ["preferences", "effective", workspaceId] as const,
  level: (scope: PreferenceScope, workspaceId?: string) =>
    ["preferences", "level", scope, workspaceId ?? null] as const,
};

/**
 * The resolved values for the caller (`source` says which level supplied each).
 *
 * `workspaceId === null` asks the account-wide route; pass an id to include the
 * workspace level.
 */
export function useEffectivePreferences(workspaceId: string | null) {
  return useQuery<PreferenceEffective>({
    queryKey: preferenceKeys.effective(workspaceId),
    queryFn: () => preferenceValuesApi.effective(workspaceId),
    staleTime: PREFERENCES_STALE_TIME_MS,
  });
}

/** The key catalogue the generic settings section renders from. */
export function usePreferenceRegistry() {
  return useQuery({
    queryKey: preferenceKeys.registry(),
    queryFn: () => preferenceValuesApi.registry(),
    staleTime: PREFERENCES_STALE_TIME_MS,
  });
}

/** One level's *stored* values (absent key = inherit, not empty). */
export function usePreferenceLevel(
  scope: PreferenceScope,
  workspaceId?: string
) {
  return useQuery<PreferenceLevel>({
    queryKey: preferenceKeys.level(scope, workspaceId),
    queryFn: () => preferenceValuesApi.getLevel(scope, workspaceId),
    staleTime: PREFERENCES_STALE_TIME_MS,
    // The workspace route needs an id; without one there is nothing to read
    // (and the wrapper would throw), so stay idle instead.
    enabled: scope !== "workspace" || Boolean(workspaceId),
  });
}

/**
 * One effective value, for a consumer that must never block on the network.
 *
 * Resolves against the active workspace (without one, the account-wide read).
 * `fallback` is returned while loading, for an unset key and on error — callers
 * pass the registry default, so the reduced behaviour is the documented one.
 *
 * Uses `??`, so a stored `false` / `0` / `""` is a value and does not fall
 * through to the fallback.
 */
export function usePreferenceValue<T>(key: string, fallback: T): T {
  const workspace = useOptionalWorkspace();
  const { data } = useEffectivePreferences(
    workspace?.activeWorkspace?.id ?? null
  );
  const entry = data?.values[key];
  return (entry?.value as T | undefined) ?? fallback;
}

/**
 * PATCH one level. `null` per key resets it (delete the row), so the next level
 * takes over again. Invalidates the whole `preferences` namespace because a
 * write moves both the level payload and the effective value.
 */
export function usePatchPreferenceLevel(
  scope: PreferenceScope,
  workspaceId?: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown | null>) =>
      preferenceValuesApi.patchLevel(scope, values, workspaceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["preferences"] });
    },
  });
}
