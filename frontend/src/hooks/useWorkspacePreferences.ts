/**
 * ARCH-L1-001 ReactFrontend — per-user visibility preference hook.
 *
 * plan Phase 5a (docs/plans/2026-10-15-frontend-audit-fixes.md, §5 bullet 5a;
 * frontend audit FE-01/F-03 "WorkspaceContext God-Component" and FE-02/F-05
 * "doppelter State: `overriddenKeys`-Set neben `userOverrides`-Map").
 *
 * Extracted verbatim from `context/WorkspaceContext.tsx`, with one deliberate
 * deduplication: the ref-twins (`userOverridesRef`, `hideAllOptionalRef`,
 * `overriddenKeysRef`) and the separately-held `overriddenKeys` state are
 * gone. `overriddenKeys` is now *derived* from `userOverrides +
 * activeWorkspace.preset` via `useMemo` — the same formula the load-time
 * computation and `setFeatureVisible`'s add/delete branch both reduced to:
 *
 *   overridden(f)  ⇔  userOverrides[f] !== undefined
 *                     && PRESET_VISIBILITY[preset][f] !== userOverrides[f]
 *
 * Equivalence proof (why deriving is exact, not just "close"):
 *   - Load path (old L385-393): iterates OPTIONAL_FEATURES and adds `f` under
 *     exactly the condition above — identical.
 *   - `setFeatureVisible` (old L468-475) computed the post-optimistic set by
 *     carrying `prevKeys` forward and adding/deleting only the touched key
 *     based on `value !== (PRESET_VISIBILITY[preset][feature] === true)`.
 *     Since PRESET_VISIBILITY values are booleans,
 *     `PRESET_VISIBILITY[preset][f] !== value` ⇔ `value !== presetValue`, so
 *     the touched key matches the formula; every untouched key's stored value
 *     is unchanged, so by induction the whole set matches the formula.
 *   - `resetFeatureOverride` calls `setFeatureVisible(feature, presetValue)`,
 *     which the formula then rates as NOT overridden — the BUG-16 fix.
 *
 * The optimistic-update + rollback-on-error semantics of `setFeatureVisible`
 * and `setHideAllOptional` are preserved. With the refs gone the pre-update
 * "previous" values for rollback come from state (both callbacks read the
 * current state variables and list them as `useCallback` deps). There is no
 * stale-closure regression for the real UI flow — each toggle is a discrete
 * event, so React re-renders (and rebuilds the callback) between clicks; the
 * production call sites (`UserProfileSettings`, `SidebarNavigation`) never
 * invoke the mutators twice within a single render tick.
 *
 * req_id: REQ-L1-027 (per-user visibility overrides), REQ-L2-RF-007
 *         (preset-based visibility)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Workspace, WorkspacePreset } from "../types";
import { PRESET_VISIBILITY } from "../types";
import {
  preferencesApi,
  OPTIONAL_FEATURES,
  type FeatureOverrides,
  type OptionalArtifactFeature,
} from "../api/preferences";

export interface UseWorkspacePreferencesOptions {
  /** Whether a session is established (gates the preference fetch). */
  isAuthenticated: boolean;
  /** True once the workspace bootstrap resolved at least once. */
  isWorkspaceReady: boolean;
  /** Currently selected workspace (or the placeholder / null). */
  activeWorkspace: Workspace | null;
}

export interface UseWorkspacePreferencesResult {
  /** Sparse per-user overrides; `null` = no preference row (use preset). */
  userOverrides: FeatureOverrides | null;
  /** Master switch: hide all 6 optional artifact features. */
  hideAllOptional: boolean;
  isFeatureVisible: (feature: string) => boolean;
  setFeatureVisible: (
    feature: OptionalArtifactFeature,
    value: boolean
  ) => Promise<void>;
  setHideAllOptional: (value: boolean) => Promise<void>;
  resetFeatureOverride: (feature: OptionalArtifactFeature) => Promise<void>;
  isFeatureOverridden: (feature: OptionalArtifactFeature) => boolean;
}

export function useWorkspacePreferences({
  isAuthenticated,
  isWorkspaceReady,
  activeWorkspace,
}: UseWorkspacePreferencesOptions): UseWorkspacePreferencesResult {
  // Per-user visibility overrides (REQ-L1-027).
  // null = no preference row exists (or fetch failed) → use preset defaults.
  // Sparse: only the keys the user has actually set are present.
  const [userOverrides, setUserOverrides] = useState<FeatureOverrides | null>(
    null
  );
  const [hideAllOptional, setHideAllOptionalState] = useState<boolean>(false);

  // Track which keys the user has explicitly set, so the UI can show a
  // "Reset to preset" button only for features that are actually overridden.
  // Derived from `userOverrides` + the active preset (never stored
  // separately), so load-time defaults can't be flagged as "user-set" and the
  // set can't drift from the map it describes (FE-02/F-05). See the file
  // header for the equivalence proof against the old imperative
  // add/delete logic.
  const overriddenKeys = useMemo<Set<OptionalArtifactFeature>>(() => {
    const keys = new Set<OptionalArtifactFeature>();
    if (!userOverrides) return keys;
    const preset: WorkspacePreset = activeWorkspace?.preset ?? "standard";
    for (const f of OPTIONAL_FEATURES) {
      const stored = userOverrides[f];
      if (stored !== undefined && PRESET_VISIBILITY[preset][f] !== stored) {
        keys.add(f);
      }
    }
    return keys;
  }, [userOverrides, activeWorkspace]);

  // Fetch per-user preferences whenever the active workspace changes
  // (REQ-L1-027). Gated on `isWorkspaceReady` so we don't burn an API call for
  // the DEFAULT_WORKSPACE placeholder on first render.
  useEffect(() => {
    if (!isAuthenticated || !activeWorkspace || !isWorkspaceReady) {
      setUserOverrides(null);
      setHideAllOptionalState(false);
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
        } else {
          setUserOverrides(pref.overrides);
          setHideAllOptionalState(pref.hideAllOptional);
        }
      } catch {
        // Network / unexpected error → fall back to preset defaults silently.
        if (cancelled) return;
        setUserOverrides(null);
        setHideAllOptionalState(false);
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

  // ---- Per-user visibility mutators (REQ-L1-027) ------------------------

  const setFeatureVisible = useCallback(
    async (
      feature: OptionalArtifactFeature,
      value: boolean
    ): Promise<void> => {
      const workspaceId = activeWorkspace?.id;
      if (!workspaceId) return;
      // Optimistic local update — keep overrides sparse. The pre-update value
      // for rollback is the current state (see the file header on why no ref
      // is needed and why there is no stale-closure regression).
      const prev = userOverrides;
      const next: FeatureOverrides = { ...(prev ?? {}), [feature]: value };
      setUserOverrides(next);
      try {
        await preferencesApi.update(workspaceId, { [feature]: value });
      } catch (err) {
        // Rollback on failure — restore the exact previous override state
        // instead of assuming the feature was never overridden.
        setUserOverrides(prev);
        throw err;
      }
    },
    [activeWorkspace, userOverrides]
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
        return;
      }
      setHideAllOptionalState(value);
      try {
        await preferencesApi.update(workspaceId, {
          _hide_all_optional: value,
        });
      } catch (err) {
        setHideAllOptionalState(!value);
        throw err;
      }
    },
    [activeWorkspace]
  );

  const isFeatureOverridden = useCallback(
    (feature: OptionalArtifactFeature): boolean => overriddenKeys.has(feature),
    [overriddenKeys]
  );

  return {
    userOverrides,
    hideAllOptional,
    isFeatureVisible,
    setFeatureVisible,
    setHideAllOptional,
    resetFeatureOverride,
    isFeatureOverridden,
  };
}
