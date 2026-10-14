/**
 * ARCH-L1-001 ReactFrontend — useMetricWidgets (Issue #1265).
 *
 * The per-user statistics-widget selection for the MetricsDashboard.
 *
 * The catalogue is the backend's central statistics registry
 * (`GET /api/v1/metrics/catalog/`, `se_metrics.registry`), and the selection is
 * stored on the caller's own display preference
 * (`GET/PATCH /api/v1/users/me/display-preferences/`, field `visible_metrics`).
 * Both halves are already-existing server contracts; this hook only composes
 * them and owns the load/save lifecycle.
 *
 * Contract:
 *   - `visible_metrics === null` means "no explicit selection" -> the
 *     registry's `default_keys` are rendered.
 *   - The list is the selection *and* its order; `MetricsDashboard` renders the
 *     tiles in this order.
 *   - Keys the catalogue no longer knows are dropped on load (a metric renamed
 *     on the server must not render an empty tile).
 *   - A toggle PATCHes and then adopts the server's returned list — the UI never
 *     keeps a change the server rejected (rollback on error).
 *   - A failed catalogue load leaves the caller's fallback set in place, so the
 *     dashboard still renders instead of going blank.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { extractApiErrorMessage } from "../../api/client";
import { displayPreferencesApi } from "../../api/display-preferences";
import { metricsApi, type MetricCatalogEntry } from "../../api/metrics";

export interface MetricWidgetsState {
  /** Catalogue entries from the registry (empty until loaded / on failure). */
  catalog: MetricCatalogEntry[];
  /** Ordered metric keys the dashboard renders. */
  visibleKeys: string[];
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  toggle: (key: string, next: boolean) => void;
}

/**
 * @param fallbackKeys metric keys rendered when the catalogue is unavailable
 *   (e.g. the request failed). Kept caller-supplied so this hook owns no tile
 *   knowledge.
 */
export function useMetricWidgets(
  fallbackKeys: readonly string[],
): MetricWidgetsState {
  const fallbackRef = useRef<readonly string[]>(fallbackKeys);
  const [catalog, setCatalog] = useState<MetricCatalogEntry[]>([]);
  const [defaultKeys, setDefaultKeys] = useState<string[]>([...fallbackKeys]);
  const [visibleKeys, setVisibleKeys] = useState<string[]>([...fallbackKeys]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    Promise.all([metricsApi.catalog(), displayPreferencesApi.get()])
      .then(([catalogResponse, preferences]) => {
        if (cancelled) return;
        const entries = Array.isArray(catalogResponse.metrics)
          ? catalogResponse.metrics
          : [];
        const defaults =
          Array.isArray(catalogResponse.default_keys) &&
          catalogResponse.default_keys.length > 0
            ? catalogResponse.default_keys
            : [...fallbackRef.current];
        const requested = preferences.visible_metrics ?? defaults;
        const known = new Set(entries.map((entry) => entry.key));
        // Unknown keys (renamed/removed metrics) are dropped; with no
        // catalogue at all the caller's fallback selection is kept verbatim.
        const resolved =
          known.size > 0 ? requested.filter((key) => known.has(key)) : [...requested];

        setCatalog(entries);
        setDefaultKeys(defaults);
        setVisibleKeys(resolved);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(extractApiErrorMessage(err) ?? "");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = useCallback(
    (key: string, next: boolean): void => {
      if (isSaving) return;
      const previous = visibleKeys;
      const nextList = next
        ? previous.includes(key)
          ? previous
          : [...previous, key]
        : previous.filter((visible) => visible !== key);

      setError(null);
      setIsSaving(true);
      // Optimistic: the tile set updates immediately so the click feels live.
      setVisibleKeys(nextList);
      displayPreferencesApi
        .update({ visible_metrics: nextList })
        .then((preferences) => {
          // The server's returned flags win — never assume the click took effect.
          setVisibleKeys(preferences.visible_metrics ?? defaultKeys);
        })
        .catch((err: unknown) => {
          // Roll back so the UI does not keep claiming a change the server rejected.
          setVisibleKeys(previous);
          setError(extractApiErrorMessage(err) ?? "");
        })
        .finally(() => {
          setIsSaving(false);
        });
    },
    [defaultKeys, isSaving, visibleKeys],
  );

  return { catalog, visibleKeys, isLoading, isSaving, error, toggle };
}
