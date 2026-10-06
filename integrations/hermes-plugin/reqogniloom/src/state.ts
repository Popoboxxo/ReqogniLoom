import type { HermesPluginAPI } from "./hermes-api-types";
import { listWorkspaces, type Connection, type Workspace, ReqogniLoomApiError } from "./api";
import {
  interviewAbandon,
  interviewAnswer,
  interviewFormalize,
  interviewGetState,
  interviewGroundingContext,
  interviewList as fetchInterviewList,
  interviewSetTarget,
  interviewStart,
  memoryAsk,
  memoryDigest,
  memoryQuery,
  memoryWrite,
  type InterviewState,
  type InterviewSummary,
  type MemoryEntry,
} from "./mcpClient";

const STORAGE_KEY = "reqogniloom-connection";

export type View = "connect" | "connected" | "interviews";

export interface AppState {
  view: View;
  connection: Connection | null;
  workspaceName: string | null;
  pendingCredentials: { baseUrl: string; apiKey: string } | null;
  pendingWorkspaces: Workspace[];
  connectError: string | null;
  connecting: boolean;
  activeInterview: InterviewState | null;
  interviewList: InterviewSummary[];
  interviewError: string | null;
  interviewBusy: boolean;
  // Memory read (memory.query / memory.digest / memory.ask). `memoryDegraded`
  // + `memoryDetail` keep "backend down" distinct from "nothing remembered":
  // an empty `memoryEntries` with `memoryDegraded === false` is a genuine
  // empty result, while `memoryDegraded === true` means the backend could not
  // answer.
  memoryEntries: MemoryEntry[];
  memoryDigest: string | null;
  memoryAnswer: string | null;
  memoryDegraded: boolean;
  memoryDetail: string | null;
  memoryLoading: boolean;
  memoryError: string | null;
  // True once a loadMemoryContext run has completed (success OR failure).
  // Without it, the initial `memoryEntries=[]`/`memoryDegraded=false`/
  // `memoryLoading=false` triple satisfies the UI's "no entries" condition on
  // first paint, so the panel would assert "nothing remembered" before any
  // query ever ran -- the exact false-empty the degraded/detail split exists
  // to prevent.
  memoryLoaded: boolean;
  // Gated capture (memory.write). `captureEnabled` is the user's on/off gate;
  // `pendingCapture` is the REVIEW draft. Nothing reaches memory.write until
  // confirmCapture() is called explicitly -- there is no auto-submit anywhere.
  // `captureBusy` is the in-flight guard that makes Confirm idempotent under a
  // double-click; `captureError` keeps a write failure inside the Capture
  // section instead of leaking into the read section's ErrorBanner.
  // NOTE: the downstream "capture -> artifact proposal (proposed -> accept)"
  // stage belongs to P4 and is intentionally NOT implemented here.
  captureEnabled: boolean;
  pendingCapture: string | null;
  captureBusy: boolean;
  captureError: string | null;
}

function createInitialState(): AppState {
  return {
    view: "connect",
    connection: null,
    workspaceName: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    connecting: false,
    activeInterview: null,
    interviewList: [],
    interviewError: null,
    interviewBusy: false,
    memoryEntries: [],
    memoryDigest: null,
    memoryAnswer: null,
    memoryDegraded: false,
    memoryDetail: null,
    memoryLoading: false,
    memoryError: null,
    memoryLoaded: false,
    captureEnabled: false,
    pendingCapture: null,
    captureBusy: false,
    captureError: null,
  };
}

let state: AppState = createInitialState();
let hermesAPI: HermesPluginAPI | null = null;
const listeners = new Set<() => void>();

export function getState(): AppState {
  return state;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setState(patch: Partial<AppState>) {
  state = { ...state, ...patch };
  for (const l of listeners) {
    try {
      l();
    } catch {
      /* a listener throwing must not break the others */
    }
  }
}

function api(): HermesPluginAPI {
  if (!hermesAPI) throw new Error("state not initialized — call initState() first");
  return hermesAPI;
}

function updateStatusBar() {
  if (!hermesAPI) return;
  hermesAPI.ui.updateStatusBarItem("reqogniloom.status", {
    text: state.connection ? `ReqogniLoom: ${state.workspaceName}` : "ReqogniLoom",
    tooltip: state.connection ? `Connected to ${state.workspaceName}` : "Open ReqogniLoom panel",
  });
}

// A restored store is only usable if it can actually drive the panel: a
// truncated/legacy entry (e.g. {"connection":null}) parses fine but leaves
// ConnectedView with an undefined workspaceName and every action a silent
// no-op, so it is rejected and dropped like a parse failure.
function isRestorableConnection(value: unknown): value is Connection {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as { baseUrl?: unknown; apiKey?: unknown; workspaceId?: unknown };
  return (
    typeof candidate.baseUrl === "string" &&
    candidate.baseUrl !== "" &&
    typeof candidate.apiKey === "string" &&
    candidate.apiKey !== "" &&
    // workspaceId is part of the Connection contract too: restoring without it
    // left every memory/interview call sending `workspace_id: undefined`,
    // which the backend rejects only at call time -- validate it here so a
    // truncated store is dropped instead of producing a half-dead panel.
    typeof candidate.workspaceId === "string" &&
    candidate.workspaceId !== ""
  );
}

export async function initState(pluginApi: HermesPluginAPI): Promise<void> {
  hermesAPI = pluginApi;
  const stored = await pluginApi.storage.get(STORAGE_KEY);
  if (!stored) {
    updateStatusBar();
    return;
  }
  try {
    const parsed = JSON.parse(stored) as { connection?: unknown; workspaceName?: string };
    if (!isRestorableConnection(parsed.connection)) {
      throw new Error("stored connection is missing baseUrl/apiKey");
    }
    setState({ connection: parsed.connection, workspaceName: parsed.workspaceName, view: "connected" });
    updateStatusBar();
  } catch {
    await pluginApi.storage.delete(STORAGE_KEY);
  }
}

export async function connectWithCredentials(baseUrl: string, apiKey: string): Promise<void> {
  setState({ connecting: true, connectError: null });
  try {
    const workspaces = await listWorkspaces(api().network, { baseUrl, apiKey });
    if (workspaces.length === 0) {
      setState({ connecting: false, connectError: "No workspaces accessible with this API key." });
      return;
    }
    if (workspaces.length === 1) {
      await finalizeConnection({ baseUrl, apiKey, workspaceId: workspaces[0].id }, workspaces[0].name);
      return;
    }
    setState({
      connecting: false,
      pendingCredentials: { baseUrl, apiKey },
      pendingWorkspaces: workspaces,
    });
  } catch (err) {
    setState({
      connecting: false,
      connectError: err instanceof ReqogniLoomApiError ? err.message : "Connection failed.",
    });
  }
}

export async function chooseWorkspace(workspace: Workspace): Promise<void> {
  if (!state.pendingCredentials) return;
  try {
    await finalizeConnection({ ...state.pendingCredentials, workspaceId: workspace.id }, workspace.name);
  } catch (err) {
    setState({
      connecting: false,
      connectError: err instanceof ReqogniLoomApiError ? err.message : "Connection failed.",
    });
  }
}

async function finalizeConnection(connection: Connection, workspaceName: string): Promise<void> {
  await api().storage.set(STORAGE_KEY, JSON.stringify({ connection, workspaceName }));
  // Reconnecting must not inherit the previous session's slices: memory
  // entries/digest/answer, interview list, capture draft, or a stale
  // `memoryLoading: true` left behind by an in-flight read. Reset every
  // non-connection slice from the initial state; the connection fields are
  // applied afterwards so they win.
  setState({
    ...createInitialState(),
    connection,
    workspaceName,
    view: "connected",
    connecting: false,
  });
  updateStatusBar();
}

export async function disconnect(): Promise<void> {
  try {
    await api().storage.delete(STORAGE_KEY);
  } catch {
    /* the stored entry may survive a failed delete, but the user asked to
       drop this connection -- keeping the panel on it would be a lie, and
       the call site is a fire-and-forget void, so nothing would report the
       failure either */
  } finally {
    setState({ ...createInitialState() });
    updateStatusBar();
  }
}

export async function openInBrowser(): Promise<void> {
  if (!state.connection) return;
  await api().shell.openExternal(state.connection.baseUrl);
}

// True if *connection* is still the live connection. Guards async flows that
// capture a connection before awaiting (openInterviews, startNewInterview,
// resumeInterview, loadMemoryContext, ...): if the user disconnects (or
// reconnects to a different workspace) while the call is in flight, the
// resolved response must not be written into state -- otherwise a phantom
// interview list / memory context would appear on the connect view, or worse,
// overwrite the newly connected session's state.
function isStillConnectedTo(connection: Connection): boolean {
  return state.connection === connection;
}

export async function openInterviews(): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const list = await fetchInterviewList(api().network, connection, "in_progress");
    if (!isStillConnectedTo(connection)) return;
    setState({ interviewList: list, view: "interviews", interviewBusy: false });
  } catch (err) {
    if (!isStillConnectedTo(connection)) return;
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to load interviews." });
  }
}

// Grounding is a nice-to-have hint, not a blocker (matches the backend's own
// fail-open design for this feature): a lookup failure must not fail the
// start/resume flow, and must not surface as interviewError -- it just leaves
// grounding_snapshot as whatever the start/resume call already returned
// (likely {}).
async function withGroundingContext(connection: Connection, interview: InterviewState): Promise<InterviewState> {
  try {
    const grounding = await interviewGroundingContext(api().network, connection, interview.session_id);
    return { ...interview, grounding_snapshot: { ...interview.grounding_snapshot, candidates: grounding.candidates } };
  } catch {
    return interview;
  }
}

export async function startNewInterview(artifactType: string): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewStart(api().network, connection, artifactType);
    if (!isStillConnectedTo(connection)) return;
    const withGrounding = await withGroundingContext(connection, interview);
    if (!isStillConnectedTo(connection)) return;
    setState({ activeInterview: withGrounding, view: "interviews", interviewBusy: false });
  } catch (err) {
    if (!isStillConnectedTo(connection)) return;
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to start interview." });
  }
}

export async function resumeInterview(sessionId: string): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewGetState(api().network, connection, sessionId);
    if (!isStillConnectedTo(connection)) return;
    const withGrounding = await withGroundingContext(connection, interview);
    if (!isStillConnectedTo(connection)) return;
    setState({ activeInterview: withGrounding, view: "interviews", interviewBusy: false });
  } catch (err) {
    if (!isStillConnectedTo(connection)) return;
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to resume interview." });
  }
}

// True if *sessionId* still identifies the current activeInterview. Guards
// every interview.* mutation below against overwriting state with a stale
// response that resolves after the user has already navigated away (closed,
// cancelled, or resumed a different session) -- without it, an in-flight
// answer/formalize/set_target call could resurrect a phantom activeInterview
// (or, for formalizeInterview, spread `null` into `{...null, status}`).
function isStillActiveSession(sessionId: string): boolean {
  return state.activeInterview?.session_id === sessionId;
}

export async function answerInterviewField(field: string, value: unknown): Promise<void> {
  if (!state.connection || !state.activeInterview) return;
  const sessionId = state.activeInterview.session_id;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const refreshed = await interviewAnswer(api().network, state.connection, sessionId, field, value);
    if (isStillActiveSession(sessionId)) {
      setState({ activeInterview: refreshed, interviewBusy: false });
    } else {
      setState({ interviewBusy: false });
    }
  } catch (err) {
    if (isStillActiveSession(sessionId)) {
      setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to save answer." });
    } else {
      setState({ interviewBusy: false });
    }
  }
}

export async function setInterviewTarget(artifactId: string): Promise<void> {
  if (!state.connection || !state.activeInterview) return;
  const sessionId = state.activeInterview.session_id;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const refreshed = await interviewSetTarget(api().network, state.connection, sessionId, artifactId);
    if (isStillActiveSession(sessionId)) {
      setState({ activeInterview: refreshed, interviewBusy: false });
    } else {
      setState({ interviewBusy: false });
    }
  } catch (err) {
    if (isStillActiveSession(sessionId)) {
      setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to set target." });
    } else {
      setState({ interviewBusy: false });
    }
  }
}

export async function formalizeInterview(): Promise<{ resulting_artifact_ids: string[] } | null> {
  if (!state.connection || !state.activeInterview) return null;
  const sessionId = state.activeInterview.session_id;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const result = await interviewFormalize(api().network, state.connection, sessionId);
    const current = state.activeInterview;
    if (current && current.session_id === sessionId) {
      setState({
        interviewBusy: false,
        activeInterview: { ...current, status: result.status as InterviewState["status"] },
      });
    } else {
      setState({ interviewBusy: false });
    }
    return result;
  } catch (err) {
    if (isStillActiveSession(sessionId)) {
      setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to formalize interview." });
    } else {
      setState({ interviewBusy: false });
    }
    return null;
  }
}

export function closeInterview(): void {
  setState({ activeInterview: null, view: "connected" });
}

// Cancel out of the in-progress form back to the interview list -- unlike
// closeInterview() (used by the completed/abandoned read-only view's "Close",
// where there is genuinely nothing left to browse), Cancel must not skip past
// the list the user came from. It also actually abandons the session
// server-side via interview.abandon (#1152) so cancelled sessions stop piling
// up as in_progress; re-fetching the list then shows the correct remainder.
export async function cancelInterview(): Promise<void> {
  const sessionId = state.activeInterview?.session_id;
  let abandonError: string | null = null;
  if (state.connection && sessionId) {
    try {
      await interviewAbandon(api().network, state.connection, sessionId);
    } catch (err) {
      abandonError =
        err instanceof Error ? err.message : "Failed to cancel interview.";
    }
  }
  setState({ activeInterview: null });
  await openInterviews();
  // openInterviews clears interviewError on success; restore the abandon
  // failure afterwards so the user learns the session was NOT ended.
  if (abandonError) {
    setState({ interviewError: abandonError });
  }
}

// ---------------------------------------------------------------------------
// Memory read (memory.query / memory.digest / memory.ask)
// ---------------------------------------------------------------------------

// memory.query requires a non-empty `query` server-side (MemoryEntryService
// .search raises ValidationError otherwise), so a bare "load context" call
// needs a seed term. Callers may pass a real search term; this is only the
// fallback used by the panel's refresh button.
const DEFAULT_MEMORY_QUERY = "workspace context";

// Loads the workspace memory context: entries from memory.query plus the
// prompt-ready memory.digest summary (optional -- a digest failure must not
// discard entries). Merges the read envelopes' `degraded`/`detail` so the UI
// can distinguish "backend down" from "nothing remembered". Guarded against
// a disconnect during flight via isStillConnectedTo.
export async function loadMemoryContext(
  workspaceId: string,
  query: string = DEFAULT_MEMORY_QUERY
): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ memoryLoading: true, memoryError: null });
  try {
    const queryResult = await memoryQuery(api().network, connection, {
      query,
      scope: "workspace",
      workspace_id: workspaceId,
    });
    if (!isStillConnectedTo(connection)) return;

    let digest: string | null = null;
    let degraded = queryResult.degraded === true;
    const detail =
      typeof queryResult.detail === "string" && queryResult.detail !== "" ? queryResult.detail : null;

    try {
      const digestResult = await memoryDigest(api().network, connection, { workspace_id: workspaceId });
      if (!isStillConnectedTo(connection)) return;
      digest = digestResult.digest;
      if (digestResult.degraded === true) degraded = true;
    } catch {
      // Digest is optional context: a failed summary must not throw away the
      // entries memory.query already returned. The query envelope's own
      // degraded/detail still describe the backend's health.
    }

    setState({
      memoryEntries: queryResult.entries,
      memoryDigest: digest,
      memoryDegraded: degraded,
      memoryDetail: detail,
      memoryLoading: false,
      memoryError: null,
      memoryLoaded: true,
    });
  } catch (err) {
    if (!isStillConnectedTo(connection)) return;
    setState({
      memoryLoading: false,
      memoryError: err instanceof Error ? err.message : "Failed to load memory.",
      // A failed load also counts as "loaded" for the UI: the panel now has a
      // definitive answer (the error), not an un-run query, so the empty state
      // stays hidden and the error is what the user sees.
      memoryLoaded: true,
    });
  }
}

// memory.ask drives a generative LLM call on the backend and is RBAC
// write-gated there, but from the panel's point of view it is a read surface:
// it never mutates the panel's local state beyond the answer field. Guarded
// like the other reads.
export async function askMemory(workspaceId: string, query: string): Promise<void> {
  const connection = state.connection;
  if (!connection || query.trim() === "") return;
  setState({ memoryLoading: true, memoryError: null });
  try {
    const result = await memoryAsk(api().network, connection, {
      query,
      workspace_id: workspaceId,
    });
    if (!isStillConnectedTo(connection)) return;
    setState({
      memoryAnswer: result.answer,
      memoryDegraded: result.degraded === true,
      memoryDetail: typeof result.detail === "string" && result.detail !== "" ? result.detail : null,
      memoryLoading: false,
      memoryError: null,
    });
  } catch (err) {
    if (!isStillConnectedTo(connection)) return;
    setState({
      memoryLoading: false,
      memoryError: err instanceof Error ? err.message : "Failed to ask memory.",
    });
  }
}

// ---------------------------------------------------------------------------
// Gated capture (memory.write)
// ---------------------------------------------------------------------------
//
// Two-step, explicitly user-driven flow:
//   1. requestCapture(text)  -- REVIEW only; sets `pendingCapture`, NO network.
//   2. confirmCapture()      -- the ONLY call site of memory.write.
// cancelCapture() drops the draft. There is no auto-submit anywhere: turning
// the toggle on or typing a fact never reaches the backend. The downstream
// "capture -> artifact proposal (proposed -> accept)" stage is P4 and is NOT
// implemented here.

export function setCaptureEnabled(enabled: boolean): void {
  // Disabling the gate discards any unreviewed draft -- a disabled capture
  // surface must not retain a fact that a later re-enable could confirm.
  setState({ captureEnabled: enabled, pendingCapture: enabled ? state.pendingCapture : null });
}

export function requestCapture(text: string): void {
  if (!state.captureEnabled) return;
  const trimmed = text.trim();
  if (trimmed === "") return;
  setState({ pendingCapture: trimmed, captureError: null });
}

export function cancelCapture(): void {
  setState({ pendingCapture: null, captureError: null });
}

export async function confirmCapture(): Promise<void> {
  // `captureBusy` makes Confirm idempotent: a double-click's second call
  // returns here before it can read the (still uncleared) draft and fire a
  // second memory.write. setState is synchronous on the module singleton, so
  // the flag is observed by the second click immediately.
  if (!state.captureEnabled || state.captureBusy) return;
  const connection = state.connection;
  const content = state.pendingCapture;
  setState({ captureBusy: true, captureError: null });
  try {
    if (!connection || !content) return;
    await memoryWrite(api().network, connection, {
      content,
      scope: "workspace",
      workspace_id: connection.workspaceId,
    });
    if (!isStillConnectedTo(connection)) return;
    setState({ pendingCapture: null });
  } catch (err) {
    if (!connection || !isStillConnectedTo(connection)) return;
    // Keep the draft on failure so the user can retry without retyping.
    setState({ captureError: err instanceof Error ? err.message : "Failed to save memory." });
  } finally {
    // Release the guard only if this run's connection is still live: a
    // disconnect resets the whole state (captureBusy back to false) and a late
    // resolver must not overwrite the fresh session's state.
    if (connection && isStillConnectedTo(connection)) {
      setState({ captureBusy: false });
    }
  }
}

// Test-only helper: resets module-level state and the cached API reference
// between test cases so tests don't leak state into each other.
export function __resetStateForTesting(): void {
  state = createInitialState();
  hermesAPI = null;
  listeners.clear();
}
