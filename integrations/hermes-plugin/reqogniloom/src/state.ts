import type { HermesPluginAPI } from "./hermes-api-types";
import { listWorkspaces, type Connection, type Workspace, ReqogniLoomApiError } from "./api";
import {
  interviewAnswer,
  interviewFormalize,
  interviewGetState,
  interviewGroundingContext,
  interviewList as fetchInterviewList,
  interviewSetTarget,
  interviewStart,
  type InterviewState,
  type InterviewSummary,
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

export async function initState(pluginApi: HermesPluginAPI): Promise<void> {
  hermesAPI = pluginApi;
  const stored = await pluginApi.storage.get(STORAGE_KEY);
  if (!stored) {
    updateStatusBar();
    return;
  }
  try {
    const parsed = JSON.parse(stored) as { connection: Connection; workspaceName: string };
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
  setState({
    connection,
    workspaceName,
    connecting: false,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    view: "connected",
  });
  updateStatusBar();
}

export async function disconnect(): Promise<void> {
  await api().storage.delete(STORAGE_KEY);
  setState({ ...createInitialState() });
  updateStatusBar();
}

export async function openInBrowser(): Promise<void> {
  if (!state.connection) return;
  await api().shell.openExternal(state.connection.baseUrl);
}

export async function openInterviews(): Promise<void> {
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const list = await fetchInterviewList(api().network, state.connection, "in_progress");
    setState({ interviewList: list, view: "interviews", interviewBusy: false });
  } catch (err) {
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
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewStart(api().network, state.connection, artifactType);
    const withGrounding = await withGroundingContext(state.connection, interview);
    setState({ activeInterview: withGrounding, view: "interviews", interviewBusy: false });
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to start interview." });
  }
}

export async function resumeInterview(sessionId: string): Promise<void> {
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewGetState(api().network, state.connection, sessionId);
    const withGrounding = await withGroundingContext(state.connection, interview);
    setState({ activeInterview: withGrounding, view: "interviews", interviewBusy: false });
  } catch (err) {
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
// the list the user came from. The session itself is left in_progress
// server-side (no interview.abandon MCP tool exists to actually abort it);
// re-fetching the list means it shows up there for the user to resume.
export async function cancelInterview(): Promise<void> {
  setState({ activeInterview: null });
  await openInterviews();
}

// Test-only helper: resets module-level state and the cached API reference
// between test cases so tests don't leak state into each other.
export function __resetStateForTesting(): void {
  state = createInitialState();
  hermesAPI = null;
  listeners.clear();
}
