/**
 * T-C2-7 (Plan C) / issue #1094 REST — hydrate the readable-id display
 * preference from the server at app start.
 *
 * #1096 made `ui.ids.show_readable` server-backed, but only the profile page
 * (`IdentifiersSection`) ever read it. A new device therefore showed the
 * cached/localStorage default until the user happened to open `/profile` — the
 * UI promise "gilt auf allen Geräten" was only true after that detour.
 *
 * This component closes that gap: it mounts once, inside `WorkspaceProvider`,
 * and writes the resolved effective value into the shared store
 * (`hooks/useReadableIdsVisible`) as soon as the query settles. Every
 * `<IdChip>` / `<ArtifactRow>` in the app follows the store, so no component
 * has to know about preferences.
 *
 * Deliberate non-behaviours (a preference must never break a page):
 *
 *   - **loading, error, missing key** → do nothing. The `localStorage`
 *     first-render cache stays authoritative, so the UI keeps painting instead
 *     of waiting for the network or blanking on a failure;
 *   - **signed out** → nothing is mounted, so no preference request is fired
 *     for an anonymous session;
 *   - **redundant writes** → the setter is only called when the resolved value
 *     actually differs from the current store value, so hydration cannot loop.
 *
 * It draws nothing: this is a lifecycle component, not a UI surface.
 */

import { useEffect } from "react";

import { useAuth } from "../context/AuthContext";
import { useWorkspace } from "../context/WorkspaceContext";
import { useEffectivePreferences } from "../queries/preferences";
import {
  getReadableIdsVisible,
  setReadableIdsVisible,
} from "../hooks/useReadableIdsVisible";

/**
 * Q1 key backing `UserDisplayPreference.show_readable_ids` (T-C2-6 / #1096).
 * Registered in `auth_tenancy/apps.py` as a three-level `bool`.
 */
export const SHOW_READABLE_IDS_KEY = "ui.ids.show_readable";

/**
 * The actual hydration. Split from the exported component so the query hook is
 * only mounted once a session exists — an internal `enabled` flag would still
 * register the cache entry, and the task contract is "no request without a
 * signed-in user".
 */
function AuthenticatedPreferencesHydrator(): null {
  const { activeWorkspace } = useWorkspace();
  const { data } = useEffectivePreferences(activeWorkspace?.id ?? null);
  // `undefined` while loading, on error, and for an unset key — all three must
  // leave the cache alone. A stored `false` is a value and survives this check.
  const resolved = data?.values[SHOW_READABLE_IDS_KEY]?.value;

  useEffect(() => {
    if (resolved === undefined) return;
    const next = Boolean(resolved);
    if (next !== getReadableIdsVisible()) setReadableIdsVisible(next);
  }, [resolved]);

  return null;
}

/**
 * Renders nothing visible: the component exists for its lifecycle effect.
 *
 * The return type is `JSX.Element | null` rather than a literal `null` because
 * gating the query on a session means mounting the inner hook component in the
 * signed-in branch — a component cannot both call that child and be typed
 * `null`. Every branch draws nothing, so the contract callers rely on ("no UI
 * surface of its own") holds.
 */
export function PreferencesHydrator(): JSX.Element | null {
  const { status } = useAuth();
  if (status !== "authenticated") return null;
  return <AuthenticatedPreferencesHydrator />;
}
