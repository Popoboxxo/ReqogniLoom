/**
 * UI-02 (docs/SYSTEMAUDIT_2026-08-27_RESTPLAN.md, AP-3) — unsaved-work
 * protection for the node_graph editor.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-002 (payload_format=node_graph)
 *
 * Before this hook the whole editor draft lived in `DiagramGraphEditorPage`'s
 * local state and reached the server only when the user clicked Save. Every
 * other exit — sidebar link, browser Back, tab close, reload — dropped the
 * complete edit session silently: no autosave, no dirty indicator, no guard.
 * This hook adds all three, modelled on the two editors that already had them
 * (`canvas/CanvasEditor.tsx`, 5s debounce; `mermaid/MermaidEditor.tsx`, 2s).
 *
 * Three deliberate divergences from those two:
 *
 * 1. **Dirty is tracked by draft IDENTITY, not by re-serializing on render.**
 *    The shared `hooks/use-form-dirty.ts` compares `JSON.stringify(values)`
 *    against a baseline on *every* render, which is right for a flat form but
 *    not for a graph that can carry hundreds of nodes and edges — the
 *    inspector's text fields re-render the page on every keystroke. Here every
 *    draft mutation produces a new draft object (all of the page's handlers go
 *    through `setDraft`), so a reference check is enough to know "something
 *    changed", and the expensive serialization happens only when a save is
 *    actually about to run.
 *
 * 2. **The debounce never sees an intermediate drag state.** The canvas
 *    reports positions through `onNodeDragStop`, not per frame, so a drag
 *    produces exactly one draft mutation and therefore at most one autosave.
 *
 * 3. **In-app navigation is guarded by saving, not by blocking.** React
 *    Router's `useBlocker` is not available: it calls `useDataRouterContext`
 *    and throws unless the tree is mounted under a data router, and `App.tsx`
 *    mounts a plain `<BrowserRouter>`. Converting the whole app to
 *    `createBrowserRouter` is far outside this fix. Instead the unmount
 *    cleanup flushes the pending draft (see `flush` below), which is also the
 *    better contract for an autosaving editor — there is no "discard" concept
 *    on this page that a confirm dialog could meaningfully offer.
 *    `beforeunload` still covers tab close / reload, where no asynchronous
 *    save can be awaited at all.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { NodeGraphPayload } from "../../types";

export type GraphSaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

/**
 * Debounce window between the last edit and the autosave PATCH.
 *
 * 5s, matching `CanvasEditor` (the closest analogue: both persist a whole
 * re-serialized payload rather than one text field, and every PATCH mints a
 * new immutable DiagramVersion, so a shorter window mostly buys version
 * churn). The data-loss window this leaves open is covered by the unmount
 * flush and the `beforeunload` guard, so the delay only matters for a hard
 * crash — trading it against version churn is the right way round.
 */
export const GRAPH_AUTOSAVE_DELAY_MS = 5000;

/** How long the transient "Saved" confirmation stays up before going back to `idle`. */
export const GRAPH_SAVED_BADGE_MS = 2000;

export interface UseGraphAutosaveOptions {
  /**
   * The editor draft. Only its *identity* is read: a new object means "the
   * user changed something". `null` while no diagram has been loaded yet.
   */
  draft: object | null;
  /**
   * Serializes the CURRENT draft into a saveable payload, or `null` when
   * there is nothing to save. Always read through a ref, never used as a
   * dependency, so it does not need to be memoized by the caller.
   */
  buildPayload: () => NodeGraphPayload | null;
  /** Awaited persistence path — drives the visible save status. */
  save: (payload: NodeGraphPayload) => Promise<void>;
  /**
   * Best-effort, fire-and-forget persistence used from the unmount cleanup,
   * where React cannot await anything and the caller's mutation observer is
   * already being torn down.
   */
  flush: (payload: NodeGraphPayload) => void;
  /**
   * `false` while the diagram is still loading, failed to load, or while
   * `draft` still belongs to a *different* diagram than the one now routed
   * to (see `resetKey`).
   */
  enabled: boolean;
  /**
   * Identity of the diagram the draft belongs to. When it changes, every
   * piece of accumulated state (armed timer, baseline, dirty flag) is
   * dropped, because none of it describes the newly routed diagram any more.
   */
  resetKey?: string;
  delayMs?: number;
}

export interface UseGraphAutosaveResult {
  status: GraphSaveStatus;
  isDirty: boolean;
  /**
   * Manual save. Unconditional on purpose — an explicit click always issues
   * the request, even when the draft is byte-identical to the server copy,
   * so the pre-existing manual Save contract (and the GH-353 E2E's
   * `waitForResponse` on the PATCH) is unchanged by autosave being added.
   * Resolves `true` only when the payload actually reached the server.
   */
  saveNow: () => Promise<boolean>;
}

export function useGraphAutosave({
  draft,
  buildPayload,
  save,
  flush,
  enabled,
  resetKey,
  delayMs = GRAPH_AUTOSAVE_DELAY_MS,
}: UseGraphAutosaveOptions): UseGraphAutosaveResult {
  const [status, setStatus] = useState<GraphSaveStatus>("idle");
  const [isDirty, setIsDirty] = useState(false);

  // Everything the debounce timer, the unload handler and the unmount cleanup
  // touch has to be reached through a ref: each of them runs from a render
  // that is already stale by the time it fires, so closing over the
  // render-scoped value would act on an outdated draft (or, for `isDirty`,
  // abort every scheduled save — the exact trap MermaidEditor's `isDirtyRef`
  // documents).
  const buildPayloadRef = useRef(buildPayload);
  const saveRef = useRef(save);
  const flushRef = useRef(flush);
  const isDirtyRef = useRef(false);
  const runSaveRef = useRef<(manual: boolean) => Promise<boolean>>(() => Promise.resolve(false));

  useEffect(() => {
    buildPayloadRef.current = buildPayload;
    saveRef.current = save;
    flushRef.current = flush;
  });

  /** JSON of the payload last known to be on the server. */
  const baselineRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const badgeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const rerunRef = useRef(false);
  const lastDraftRef = useRef<object | null>(null);
  /** Bumped on every edit, so a save can tell whether the draft moved under it. */
  const revisionRef = useRef(0);

  /**
   * Serialize the current draft without ever throwing into a timer, an unload
   * handler or an unmount cleanup. `flowToPayload` rejects a structurally
   * broken edge; for autosave the right degradation is "do nothing", while
   * the manual Save button still surfaces the same failure loudly.
   */
  const safeBuild = useCallback((): { payload: NodeGraphPayload; json: string } | null => {
    try {
      const payload = buildPayloadRef.current();
      if (!payload) return null;
      return { payload, json: JSON.stringify(payload) };
    } catch {
      return null;
    }
  }, []);

  const clearTimer = useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const scheduleSave = useCallback(
    (ms: number): void => {
      clearTimer();
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void runSaveRef.current(false);
      }, ms);
    },
    [clearTimer]
  );

  const runSave = useCallback(
    async (manual: boolean): Promise<boolean> => {
      const built = safeBuild();
      if (!built) return false;

      // An edit that cancels itself out (a node dragged back to where it
      // started, a label retyped identically) leaves the payload byte-identical
      // to what the server already holds. Autosave must not turn that into a
      // request, because every PATCH mints a new immutable DiagramVersion.
      if (!manual && built.json === baselineRef.current) {
        setIsDirty(false);
        isDirtyRef.current = false;
        setStatus((prev) => (prev === "dirty" ? "idle" : prev));
        return false;
      }

      // Two concurrent PATCHes would race two versions of the same diagram.
      // Queue instead, and re-arm the debounce once the in-flight one settles.
      if (inFlightRef.current) {
        rerunRef.current = true;
        return false;
      }

      const revisionAtStart = revisionRef.current;
      inFlightRef.current = true;
      if (badgeTimerRef.current !== null) {
        clearTimeout(badgeTimerRef.current);
        badgeTimerRef.current = null;
      }
      setStatus("saving");

      try {
        await saveRef.current(built.payload);
        baselineRef.current = built.json;

        if (revisionRef.current === revisionAtStart) {
          setIsDirty(false);
          isDirtyRef.current = false;
          setStatus("saved");
          badgeTimerRef.current = setTimeout(() => {
            badgeTimerRef.current = null;
            setStatus((prev) => (prev === "saved" ? "idle" : prev));
          }, GRAPH_SAVED_BADGE_MS);
        } else {
          // The user kept editing while this save was in flight, so those
          // edits are still unpersisted: stay dirty (the guard must keep
          // warning) and let the already-scheduled debounce pick them up.
          setStatus("dirty");
        }
        return true;
      } catch {
        // `isDirty` deliberately stays true — the draft is still unpersisted,
        // so the beforeunload guard must keep warning, the next edit retries,
        // and the unmount flush still has something to do. The error *text*
        // is surfaced by the caller's own `saveError`.
        setStatus("error");
        return false;
      } finally {
        inFlightRef.current = false;
        if (rerunRef.current) {
          rerunRef.current = false;
          scheduleSave(delayMs);
        }
      }
    },
    [safeBuild, scheduleSave, delayMs]
  );

  useEffect(() => {
    runSaveRef.current = runSave;
  }, [runSave]);

  // --- diagram switch ------------------------------------------------------

  // `/diagrams/:id/graph` is a single route element, so moving from diagram A
  // to diagram B reuses this component instance: `draft` still holds A's
  // graph for the window until B's content arrives, while `save`/`flush`
  // already target B. An autosave armed for A would then write A's graph onto
  // B. Dropping the accumulated state here — together with the caller gating
  // `enabled` on "the draft belongs to the routed diagram" — closes that
  // window. Declared before the edit-detection effect so it runs first on the
  // commit that changes the id.
  const resetKeyRef = useRef(resetKey);
  useEffect(() => {
    if (resetKeyRef.current === resetKey) return;
    resetKeyRef.current = resetKey;

    clearTimer();
    baselineRef.current = null;
    lastDraftRef.current = null;
    // Invalidate any in-flight save's completion bookkeeping: its result no
    // longer says anything about the diagram now on screen. (The request
    // itself is safe — the mutation captured the old id when it was fired.)
    revisionRef.current += 1;
    rerunRef.current = false;
    isDirtyRef.current = false;
    setIsDirty(false);
    setStatus("idle");
  }, [resetKey, clearTimer]);

  // --- edit detection + debounce -------------------------------------------

  useEffect(() => {
    if (!enabled || draft === null) return;
    // A re-run caused by a non-draft dependency (`enabled` flipping, say)
    // must not be mistaken for an edit.
    if (lastDraftRef.current === draft) return;

    const isFirstDraft = lastDraftRef.current === null;
    lastDraftRef.current = draft;

    if (isFirstDraft) {
      // The first draft this editor sees is the freshly seeded server state,
      // not an edit. Record it as the baseline and stop — without this,
      // merely OPENING a diagram would autosave (and re-version) it.
      baselineRef.current = safeBuild()?.json ?? null;
      return;
    }

    revisionRef.current += 1;
    setIsDirty(true);
    isDirtyRef.current = true;
    setStatus((prev) => (prev === "saving" ? prev : "dirty"));
    scheduleSave(delayMs);
  }, [draft, enabled, delayMs, safeBuild, scheduleSave]);

  // --- guard: tab close / reload -------------------------------------------

  useEffect(() => {
    if (!isDirty) return undefined;

    function handleBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
      // Legacy browsers key off `returnValue`; the string itself is never
      // shown, every current browser renders its own copy.
      event.returnValue = "";
    }

    // Registered ONLY while dirty, so it is entirely absent from the clean
    // flows the Playwright specs drive (they click Save and wait for the
    // PATCH before `page.reload()`), where a beforeunload dialog would
    // otherwise have to be handled by the test.
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  // --- guard: in-app navigation (unmount flush) ----------------------------

  useEffect(() => {
    return () => {
      clearTimer();
      if (badgeTimerRef.current !== null) {
        clearTimeout(badgeTimerRef.current);
        badgeTimerRef.current = null;
      }
      if (!isDirtyRef.current) return;

      const built = safeBuild();
      if (!built || built.json === baselineRef.current) return;

      // See the module doc: `useBlocker` needs a data router this app does
      // not have, so the pending draft is persisted on the way out instead of
      // the navigation being blocked. Necessarily fire-and-forget — a React
      // cleanup function cannot be awaited.
      flushRef.current(built.payload);
    };
  }, [clearTimer, safeBuild]);

  const saveNow = useCallback((): Promise<boolean> => {
    clearTimer();
    return runSave(true);
  }, [clearTimer, runSave]);

  return { status, isDirty, saveNow };
}
