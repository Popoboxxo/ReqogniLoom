import type { HermesPluginAPI } from "./hermes-api-types";
import {
  createRequirement,
  getRequirement,
  listRequirements,
  listWorkspaces,
  updateRequirement,
  type Connection,
  type Requirement,
  type RequirementType,
  type Workspace,
  ReqogniLoomApiError,
} from "./api";
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

const REQUIREMENT_PAGE_SIZE = 25;

export type View =
  | "connect"
  | "connected"
  | "interviews"
  | "requirements"
  | "requirement-detail"
  | "requirement-form";

export type RequirementFormMode = "create" | "edit";

/**
 * The editable requirement fields — deliberately no `level`, `tier_key`,
 * `level_source`, `status` or `version`: the first four are read-only (level is
 * derived, ADR-005/027) and `version` travels out of band from
 * `activeRequirement` (see submitForm).
 */
export interface RequirementFormValues {
  title: string;
  description: string;
  acceptance_criteria: string;
  category: string;
  type: RequirementType;
}

export interface RequirementFormState {
  mode: RequirementFormMode;
  values: RequirementFormValues;
  fieldErrors: Record<string, string>;
  changeReason: string;
}

/** A 409 from the optimistic-lock guard: keep the draft, re-read, retry. */
export const REQUIREMENT_CONFLICT_MESSAGE =
  "This requirement was changed elsewhere. Reload it to see the latest version, then apply your changes again.";

/** The standard/extended presets require a reason on every update. */
export const REQUIREMENT_CHANGE_REASON_REQUIRED_MESSAGE =
  "This workspace's preset requires a change reason for updates.";

/** A read-only API key is a permission problem, not a crash. */
export const REQUIREMENT_FORBIDDEN_MESSAGE = "This API key is not allowed to change requirements.";

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
  requirements: Requirement[];
  requirementsPage: number;
  requirementsNext: string | null;
  requirementsPrevious: string | null;
  requirementsCount: number;
  requirementsSearch: string;
  activeRequirement: Requirement | null;
  requirementForm: RequirementFormState | null;
  requirementError: string | null;
  requirementBusy: boolean;
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
    requirements: [],
    requirementsPage: 1,
    requirementsNext: null,
    requirementsPrevious: null,
    requirementsCount: 0,
    requirementsSearch: "",
    activeRequirement: null,
    requirementForm: null,
    requirementError: null,
    requirementBusy: false,
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
  const candidate = value as { baseUrl?: unknown; apiKey?: unknown };
  return (
    typeof candidate.baseUrl === "string" &&
    candidate.baseUrl !== "" &&
    typeof candidate.apiKey === "string" &&
    candidate.apiKey !== ""
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

// ---------------------------------------------------------------------------
// Requirements (Phase H / #1701)
//
// Mirrors the interview actions' shape: one busy flag, one error string, every
// mutation through setState() so the panel re-renders. Two behaviours are
// specific to the requirement write path and are load-bearing:
//
//  * an optimistic-lock 409 keeps `requirementForm` untouched (the draft is the
//    only copy of the user's edit) and asks for a reload;
//  * a 400 whose message names `change_reason` becomes a field error on that
//    field instead of a generic banner — the standard/extended presets demand
//    one and the form has to grow the field, not just show red text.
// ---------------------------------------------------------------------------

/** A paged response repeating the link just requested would loop forever. */
function endOfChain(link: string | null, requestedUrl: string | undefined): string | null {
  if (!link) return null;
  return link === requestedUrl ? null : link;
}

async function loadRequirementPage(request: { url?: string; page: number }): Promise<void> {
  if (!state.connection) return;
  setState({ requirementBusy: true, requirementError: null });
  try {
    // A next/previous link is passed through as-is (DRF builds an absolute URL);
    // the first page is assembled from the connection's workspace.
    const response = request.url
      ? await listRequirements(api().network, state.connection, { url: request.url })
      : await listRequirements(api().network, state.connection, {
          page: request.page,
          pageSize: REQUIREMENT_PAGE_SIZE,
          search: state.requirementsSearch || undefined,
        });
    setState({
      requirements: response.results,
      requirementsCount: response.count,
      requirementsPage: request.page,
      requirementsNext: endOfChain(response.next, request.url),
      requirementsPrevious: endOfChain(response.previous, request.url),
      requirementBusy: false,
    });
  } catch (err) {
    setState({
      requirementBusy: false,
      requirementError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load requirements.",
    });
  }
}

export async function openRequirements(): Promise<void> {
  if (!state.connection) return;
  // Switch first: a load failure belongs on the list view, where the error
  // banner and its retry live — not on the hub with no visible feedback.
  setState({ view: "requirements" });
  await loadRequirementPage({ page: 1 });
}

export async function searchRequirements(term: string): Promise<void> {
  if (!state.connection) return;
  // A new search invalidates the current page chain: restart at page 1 so the
  // "next" link always belongs to the term that produced it.
  setState({ requirementsSearch: term, view: "requirements" });
  await loadRequirementPage({ page: 1 });
}

export async function requirementsPageNext(): Promise<void> {
  if (!state.connection || !state.requirementsNext) return;
  await loadRequirementPage({ url: state.requirementsNext, page: state.requirementsPage + 1 });
}

export async function requirementsPagePrevious(): Promise<void> {
  if (!state.connection || !state.requirementsPrevious) return;
  await loadRequirementPage({
    url: state.requirementsPrevious,
    page: Math.max(1, state.requirementsPage - 1),
  });
}

export async function selectRequirement(id: string): Promise<void> {
  if (!state.connection) return;
  // Clearing activeRequirement avoids rendering the previously selected row's
  // data under a new id while the detail request is in flight.
  setState({
    view: "requirement-detail",
    activeRequirement: null,
    requirementError: null,
    requirementBusy: true,
  });
  try {
    const requirement = await getRequirement(api().network, state.connection, id);
    setState({ activeRequirement: requirement, requirementBusy: false });
  } catch (err) {
    setState({
      requirementBusy: false,
      requirementError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load the requirement.",
    });
  }
}

const FORM_TEXT_FIELDS: readonly string[] = ["title", "description", "acceptance_criteria", "category"];
const REQUIREMENT_TYPES: readonly string[] = ["SyReq", "UseCase", "FeatureReq"];

function isRequirementType(value: string): value is RequirementType {
  return REQUIREMENT_TYPES.includes(value);
}

export function openCreateForm(): void {
  setState({
    view: "requirement-form",
    requirementError: null,
    requirementForm: {
      mode: "create",
      values: { title: "", description: "", acceptance_criteria: "", category: "", type: "SyReq" },
      fieldErrors: {},
      changeReason: "",
    },
  });
}

export function openEditForm(): void {
  const requirement = state.activeRequirement;
  if (!requirement) return;
  setState({
    view: "requirement-form",
    requirementError: null,
    requirementForm: {
      mode: "edit",
      // Only writable fields are carried into the form. `level`/`tier_key`/
      // `level_source` stay on `activeRequirement` for display: they are
      // derived and read-only, and re-sending them would be a 400 at best.
      values: {
        title: requirement.title,
        description: requirement.description ?? "",
        acceptance_criteria: requirement.acceptance_criteria ?? "",
        category: requirement.category ?? "",
        type: requirement.type,
      },
      fieldErrors: {},
      changeReason: "",
    },
  });
}

export function updateFormField(name: string, value: string): void {
  const form = state.requirementForm;
  if (!form) return;
  const fieldErrors = { ...form.fieldErrors };
  if (name === "change_reason") {
    delete fieldErrors.change_reason;
    setState({ requirementForm: { ...form, changeReason: value, fieldErrors } });
    return;
  }
  if (name === "type") {
    if (!isRequirementType(value)) return;
    delete fieldErrors.type;
    setState({ requirementForm: { ...form, values: { ...form.values, type: value }, fieldErrors } });
    return;
  }
  if (!FORM_TEXT_FIELDS.includes(name)) return;
  delete fieldErrors[name];
  setState({ requirementForm: { ...form, values: { ...form.values, [name]: value }, fieldErrors } });
}

// Field errors arrive as {"field": ..., "errors": [...]} entries in the nested
// envelope. Anything else (a flat body, a detail block of another shape) is
// not a field error and must not fabricate one.
function formFieldErrorsFrom(err: ReqogniLoomApiError): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  const envelope = err.envelope;
  if (!envelope || typeof envelope.error !== "object" || envelope.error === null) return fieldErrors;
  const details = (envelope.error as { details?: unknown }).details;
  if (!Array.isArray(details)) return fieldErrors;
  for (const detail of details) {
    if (typeof detail !== "object" || detail === null) continue;
    const field = (detail as { field?: unknown }).field;
    if (typeof field !== "string" || field === "") continue;
    const errors = (detail as { errors?: unknown }).errors;
    const message = Array.isArray(errors)
      ? errors.filter((entry): entry is string => typeof entry === "string" && entry !== "").join(" ")
      : typeof errors === "string"
        ? errors
        : "";
    if (message) fieldErrors[field] = message;
  }
  return fieldErrors;
}

function applyRequirementFormError(err: unknown): void {
  if (!(err instanceof ReqogniLoomApiError)) {
    setState({
      requirementBusy: false,
      requirementError: err instanceof Error ? err.message : "Failed to save the requirement.",
    });
    return;
  }
  if (err.status === 409) {
    // Nothing in `requirementForm` is cleared here on purpose: the draft is the
    // only copy of the edit the user just made.
    setState({ requirementBusy: false, requirementError: REQUIREMENT_CONFLICT_MESSAGE });
    return;
  }
  if (err.status === 403) {
    setState({ requirementBusy: false, requirementError: REQUIREMENT_FORBIDDEN_MESSAGE });
    return;
  }
  if (err.status === 400) {
    const fieldErrors = formFieldErrorsFrom(err);
    // The preset gate raises a bare ValidationError with no `details`, so the
    // only signal is the message naming the field. Turning it into a field
    // error is what lets the form mark change_reason as required.
    if (Object.keys(fieldErrors).length === 0 && /change_reason/i.test(err.message)) {
      fieldErrors.change_reason = REQUIREMENT_CHANGE_REASON_REQUIRED_MESSAGE;
    }
    const form = state.requirementForm;
    if (!form) {
      setState({ requirementBusy: false, requirementError: err.message });
      return;
    }
    const hasFieldErrors = Object.keys(fieldErrors).length > 0;
    setState({
      requirementBusy: false,
      requirementError: hasFieldErrors ? null : err.message,
      requirementForm: { ...form, fieldErrors: { ...form.fieldErrors, ...fieldErrors } },
    });
    return;
  }
  setState({ requirementBusy: false, requirementError: err.message || "Failed to save the requirement." });
}

export async function submitForm(): Promise<void> {
  const form = state.requirementForm;
  if (!state.connection || !form) return;

  const title = form.values.title.trim();
  if (!title) {
    setState({
      requirementError: null,
      requirementForm: { ...form, fieldErrors: { ...form.fieldErrors, title: "A title is required." } },
    });
    return;
  }

  const connection = state.connection;
  setState({ requirementBusy: true, requirementError: null });
  // No `level`, `tier_key`, `level_source`, `status`, `uid` or `artifact_id`:
  // api.ts only forwards its writable allow-list, and the form never holds them.
  const values = {
    title,
    description: form.values.description,
    acceptance_criteria: form.values.acceptance_criteria,
    category: form.values.category,
    type: form.values.type,
  };
  try {
    if (form.mode === "create") {
      const created = await createRequirement(api().network, connection, values);
      setState({
        activeRequirement: created,
        requirementForm: null,
        requirementBusy: false,
        view: "requirement-detail",
      });
    } else {
      const current = state.activeRequirement;
      if (!current) {
        setState({ requirementBusy: false, requirementError: "No requirement loaded." });
        return;
      }
      const changeReason = form.changeReason.trim();
      const updated = await updateRequirement(api().network, connection, current.id, {
        ...values,
        // The revision this form was opened with, not one re-read now — a
        // fresh read would compare the server against itself and never detect
        // the concurrent edit the guard exists for.
        version: current.version,
        ...(changeReason ? { change_reason: changeReason } : {}),
      });
      setState({
        activeRequirement: updated,
        requirementForm: null,
        requirementBusy: false,
        view: "requirement-detail",
      });
    }
  } catch (err) {
    applyRequirementFormError(err);
    return;
  }
  // Keep the cached page in sync with what was just written, so going back to
  // the list does not show a stale row (or miss a newly created one).
  await loadRequirementPage({ page: state.requirementsPage });
}

// Navigation only. The draft stays in `requirementForm` on purpose: leaving the
// form and changing your mind must not silently discard the input; the "unsaved
// changes" confirmation is the form view's concern, not the store's.
export function backToList(): void {
  setState({ view: "requirements", requirementError: null });
}

// Leaving the requirement section entirely: drop the loaded row and the draft,
// keep the cached list so returning is instant.
export function backToConnected(): void {
  setState({
    view: "connected",
    requirementError: null,
    activeRequirement: null,
    requirementForm: null,
  });
}

// Test-only helper: resets module-level state and the cached API reference
// between test cases so tests don't leak state into each other.
export function __resetStateForTesting(): void {
  state = createInitialState();
  hermesAPI = null;
  listeners.clear();
}
