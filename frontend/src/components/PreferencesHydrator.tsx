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
 * Task 2 extends the same lifecycle to the two independent display flags
 * (`trace_footer_enabled`, `inspector_enabled`). They come from the
 * self-service endpoint, NOT the Q1 effective-values route: their Q1 keys are
 * backend-internal and never appear in client code. The localStorage stores of
 * `useTraceFooterVisible` / `useInspectorVisible` paint synchronously on first
 * render; this component replaces both with the server values once the query
 * settles, so a fresh device gets the account's choice without visiting
 * `/profile`.
 *
 * It draws nothing: this is a lifecycle component, not a UI surface.
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../context/AuthContext";
import { useWorkspace } from "../context/WorkspaceContext";
import { useEffectivePreferences } from "../queries/preferences";
import { displayPreferencesApi } from "../api/display-preferences";
import {
  getReadableIdsVisible,
  setReadableIdsVisible,
} from "../hooks/useReadableIdsVisible";
import {
  getInspectorVisible,
  setInspectorVisible,
} from "../hooks/useInspectorVisible";
import {
  getTraceFooterVisible,
  setTraceFooterVisible,
} from "../hooks/useTraceFooterVisible";

/**
 * Q1 key backing `UserDisplayPreference.show_readable_ids` (T-C2-6 / #1096).
 * Registered in `auth_tenancy/apps.py` as a three-level `bool`.
 */
export const SHOW_READABLE_IDS_KEY = "ui.ids.show_readable";

/** Cache key for the self-service display-preferences query (Task 2). */
export const DISPLAY_PREFERENCES_QUERY_KEY = ["display-preferences", "me"] as const;

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
 * Task 2: hydrate the two independent display flags from the self-service
 * endpoint. Same degradation policy as above — while loading, on error and for
 * a missing field the localStorage first-render cache stays authoritative, and
 * a redundant write is skipped. Only the field the server actually returned is
 * applied, so one flag can never move the other.
 */
function AuthenticatedDisplayPreferencesHydrator(): null {
  const { data } = useQuery({
    queryKey: DISPLAY_PREFERENCES_QUERY_KEY,
    queryFn: () => displayPreferencesApi.get(),
  });

  useEffect(() => {
    if (data?.trace_footer_enabled !== undefined &&
        data.trace_footer_enabled !== getTraceFooterVisible()) {
      setTraceFooterVisible(data.trace_footer_enabled);
    }
    if (data?.inspector_enabled !== undefined &&
        data.inspector_enabled !== getInspectorVisible()) {
      setInspectorVisible(data.inspector_enabled);
    }
  }, [data]);

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
  return (
    <>
      <AuthenticatedPreferencesHydrator />
      <AuthenticatedDisplayPreferencesHydrator />
    </>
  );
}
