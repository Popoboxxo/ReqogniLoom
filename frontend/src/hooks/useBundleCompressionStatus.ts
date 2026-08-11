/**
 * ARCH-L1-001 ReactFrontend — Requirement Bundle compression status poll hook.
 *
 * Polls GET /api/v1/bundle-compression-status/{task_id}/ (via
 * `requirementBundleApi.getCompressionStatus`) on a fixed interval while a
 * dispatched async compression task is still `pending`/`running`, and stops
 * the moment it reaches a terminal status (`done`/`failed`/`not_found`).
 *
 * Genuinely new polling infrastructure for this frontend — no
 * `setInterval`-based REST-status-poll hook existed anywhere before this
 * (confirmed by repo-wide search; the one other `task_id`-returning
 * wrapper, `stakeholder-need.ts`'s `derive()`, is fire-and-forget).
 */

import { useEffect, useState } from "react";
import { requirementBundleApi } from "../api/requirementBundle";
import type { CompressionStatus } from "../api/requirementBundle";

const TERMINAL_STATUSES = new Set<CompressionStatus["status"]>(["done", "failed", "not_found"]);

export interface BundleCompressionStatusState {
  status: CompressionStatus["status"] | null;
  result: string | null;
  error: string | null;
  isPolling: boolean;
}

export function useBundleCompressionStatus(
  taskId: string | null,
  intervalMs = 2000
): BundleCompressionStatusState {
  const [state, setState] = useState<BundleCompressionStatusState>({
    status: null,
    result: null,
    error: null,
    isPolling: false,
  });

  useEffect(() => {
    if (!taskId) {
      setState({ status: null, result: null, error: null, isPolling: false });
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const poll = async () => {
      try {
        const next = await requirementBundleApi.getCompressionStatus(taskId);
        if (cancelled) return;
        setState({
          status: next.status,
          result: next.result?.result ?? null,
          error: next.error,
          isPolling: !TERMINAL_STATUSES.has(next.status),
        });
        if (TERMINAL_STATUSES.has(next.status) && intervalId !== undefined) {
          clearInterval(intervalId);
        }
      } catch (err) {
        if (cancelled) return;
        setState({
          status: "failed",
          result: null,
          error: err instanceof Error ? err.message : "Status poll failed",
          isPolling: false,
        });
        if (intervalId !== undefined) clearInterval(intervalId);
      }
    };

    setState((prev) => ({ ...prev, isPolling: true }));
    poll();
    intervalId = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [taskId, intervalMs]);

  return state;
}
