/**
 * Task 4.5 — auto-persisted per-user table state
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * Loads the state once per `(workspace, itemType)`, keeps the UI local while
 * the user edits and writes back after 800 ms of inactivity (plus a flush on
 * unmount and on a subject switch, so no edit is lost). A failing `PUT` never
 * breaks the surface: the local state stays authoritative and the caller gets
 * one `error` string to surface. A missing slice-3 route (404) degrades to the
 * defaults and marks the state ready — no endless loading.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  EMPTY_TABLE_VIEW_STATE,
  tableViewStateApi,
  type TableViewState,
} from "../../../api/table-views";
import { extractErrorMessage } from "../../../api/client";
import type { UUID } from "../../../types";

export const TABLE_STATE_DEBOUNCE_MS = 800;

export interface UseTableViewStateResult {
  state: TableViewState;
  setState(next: TableViewState): void;
  ready: boolean;
  /** Last persistence failure, for one toast/alert. Cleared on the next save. */
  error: string | null;
}

function isMissingRoute(error: unknown): boolean {
  const code = (error as { error?: { code?: string } } | null)?.error?.code;
  return code === "NOT_FOUND";
}

export function useTableViewState(
  workspaceId: string | undefined,
  itemType: string
): UseTableViewStateResult {
  const [state, setStateInternal] = useState<TableViewState>(
    EMPTY_TABLE_VIEW_STATE
  );
  const [ready, setReady] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const stateRef = useRef<TableViewState>(EMPTY_TABLE_VIEW_STATE);
  const dirtyRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const subjectRef = useRef<string>("");
  const mountedRef = useRef(true);

  const key = `${workspaceId ?? ""}:${itemType}`;

  const clearTimer = useCallback((): void => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const flush = useCallback((): void => {
    clearTimer();
    if (!dirtyRef.current) return;
    const [ws, type] = subjectRef.current.split(":");
    if (!ws || !type) return;
    dirtyRef.current = false;
    const snapshot = stateRef.current;
    tableViewStateApi
      .put(ws as UUID, type, snapshot)
      .then(() => {
        if (mountedRef.current) setError(null);
      })
      .catch((exc: unknown) => {
        // The local state stays authoritative; one message, no retry loop.
        if (mountedRef.current) setError(extractErrorMessage(exc));
      });
  }, [clearTimer]);

  // Load on subject change; flush whatever the previous subject still owed.
  useEffect(() => {
    mountedRef.current = true;
    const previous = subjectRef.current;
    if (previous && previous !== key) flush();

    subjectRef.current = key;
    dirtyRef.current = false;
    clearTimer();
    setReady(false);
    setError(null);
    stateRef.current = EMPTY_TABLE_VIEW_STATE;

    if (!workspaceId) {
      setStateInternal(EMPTY_TABLE_VIEW_STATE);
      setReady(true);
      return undefined;
    }

    let cancelled = false;
    tableViewStateApi
      .get(workspaceId, itemType)
      .then((loaded) => {
        if (cancelled) return;
        stateRef.current = loaded;
        setStateInternal(loaded);
        setReady(true);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        stateRef.current = EMPTY_TABLE_VIEW_STATE;
        setStateInternal(EMPTY_TABLE_VIEW_STATE);
        setReady(true);
        if (!isMissingRoute(exc)) setError(extractErrorMessage(exc));
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, itemType, key, clearTimer, flush]);

  // Flush on unmount only (the subject-change flush is above).
  useEffect(
    () => () => {
      mountedRef.current = false;
      flush();
    },
    [flush]
  );

  const setState = useCallback(
    (next: TableViewState): void => {
      stateRef.current = next;
      setStateInternal(next);
      dirtyRef.current = true;
      clearTimer();
      timerRef.current = window.setTimeout(flush, TABLE_STATE_DEBOUNCE_MS);
    },
    [clearTimer, flush]
  );

  return { state, setState, ready, error };
}
