import type { HermesPluginAPI } from "./hermes-api-types";
import {
  listWorkspaces,
  listRequirements,
  getRequirement,
  createRequirement,
  updateRequirement,
  type Connection,
  type Workspace,
  type Requirement,
  type CreateRequirementInput,
  ReqogniLoomApiError,
} from "./api";

const STORAGE_KEY = "reqogniloom-connection";

export type View = "connect" | "list" | "detail" | "form";

/**
 * Editable form fields. `change_reason` is edit-only: workspaces on the
 * `extended` rigor preset reject every PATCH that does not carry a non-empty
 * one ("change_reason required by workspace preset policy"), so the edit form
 * must be able to supply it. It is never sent on create.
 */
export type FormValues = CreateRequirementInput & { change_reason?: string };

export interface FormState {
  mode: "create" | "edit";
  values: FormValues;
  requirementId?: string;
  fieldErrors: Record<string, string[]>;
  submitting: boolean;
  submitError: string | null;
}

export interface AppState {
  view: View;
  connection: Connection | null;
  pendingCredentials: { baseUrl: string; apiKey: string } | null;
  pendingWorkspaces: Workspace[];
  connectError: string | null;
  connecting: boolean;
  requirements: Requirement[];
  requirementsCount: number;
  requirementsPage: number;
  hasMoreRequirements: boolean;
  searchTerm: string;
  listLoading: boolean;
  listError: string | null;
  selectedRequirement: Requirement | null;
  detailLoading: boolean;
  detailError: string | null;
  form: FormState | null;
}

let state: AppState = {
  view: "connect",
  connection: null,
  pendingCredentials: null,
  pendingWorkspaces: [],
  connectError: null,
  connecting: false,
  requirements: [],
  requirementsCount: 0,
  requirementsPage: 1,
  hasMoreRequirements: false,
  searchTerm: "",
  listLoading: false,
  listError: null,
  selectedRequirement: null,
  detailLoading: false,
  detailError: null,
  form: null,
};

let hermesAPI: HermesPluginAPI | null = null;
const listeners = new Set<() => void>();

export function getState(): AppState {
  return state;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function __resetStateForTesting(): void {
  state = {
    view: "connect",
    connection: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    connecting: false,
    requirements: [],
    requirementsCount: 0,
    requirementsPage: 1,
    hasMoreRequirements: false,
    searchTerm: "",
    listLoading: false,
    listError: null,
    selectedRequirement: null,
    detailLoading: false,
    detailError: null,
    form: null,
  };
  hermesAPI = null;
  listeners.clear();
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

export async function initState(pluginApi: HermesPluginAPI): Promise<void> {
  hermesAPI = pluginApi;
  const stored = await pluginApi.storage.get(STORAGE_KEY);
  if (!stored) return;
  try {
    const connection = JSON.parse(stored) as Connection;
    setState({ connection, view: "list" });
    await loadRequirements();
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
      await finalizeConnection({ baseUrl, apiKey, workspaceId: workspaces[0].id });
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
  await finalizeConnection({ ...state.pendingCredentials, workspaceId: workspace.id });
}

async function finalizeConnection(connection: Connection): Promise<void> {
  await api().storage.set(STORAGE_KEY, JSON.stringify(connection));
  setState({
    connection,
    connecting: false,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    view: "list",
  });
  await loadRequirements();
}

export async function disconnect(): Promise<void> {
  await api().storage.delete(STORAGE_KEY);
  setState({
    view: "connect",
    connection: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    requirements: [],
    requirementsCount: 0,
    requirementsPage: 1,
    hasMoreRequirements: false,
    selectedRequirement: null,
    detailError: null,
    form: null,
  });
}

export function setSearchTerm(term: string): void {
  setState({ searchTerm: term });
}

export async function loadRequirements(page = 1): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ listLoading: true, listError: null });
  try {
    const response = await listRequirements(api().network, connection, {
      page,
      search: state.searchTerm || undefined,
    });
    setState({
      requirements: response.results,
      requirementsCount: response.count,
      requirementsPage: page,
      hasMoreRequirements: response.next !== null,
      listLoading: false,
    });
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    setState({
      listLoading: false,
      listError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load requirements.",
    });
  }
}

export async function selectRequirement(id: string): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ view: "detail", detailLoading: true, detailError: null });
  try {
    const requirement = await getRequirement(api().network, connection, id);
    setState({ selectedRequirement: requirement, detailLoading: false });
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    setState({
      detailLoading: false,
      detailError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load requirement.",
    });
  }
}

export function backToList(): void {
  setState({ view: "list", selectedRequirement: null, detailError: null, form: null });
}

export function openCreateForm(): void {
  setState({
    view: "form",
    form: { mode: "create", values: { title: "" }, fieldErrors: {}, submitting: false, submitError: null },
  });
}

export function openEditForm(requirement: Requirement): void {
  setState({
    view: "form",
    form: {
      mode: "edit",
      requirementId: requirement.id,
      values: {
        title: requirement.title,
        description: requirement.description,
        acceptance_criteria: requirement.acceptance_criteria,
        category: requirement.category,
        type: requirement.type,
        complexity_fibonacci: requirement.complexity_fibonacci ?? undefined,
        verification_method: requirement.verification_method ?? undefined,
        level: requirement.level ?? undefined,
        parent_id: requirement.parent_id ?? undefined,
        change_reason: "",
      },
      fieldErrors: {},
      submitting: false,
      submitError: null,
    },
  });
}

export function updateFormField<K extends keyof FormValues>(field: K, value: FormValues[K]): void {
  if (!state.form) return;
  setState({ form: { ...state.form, values: { ...state.form.values, [field]: value } } });
}

export async function submitForm(): Promise<void> {
  const form = state.form;
  const connection = state.connection;
  if (!form || !connection) return;
  setState({ form: { ...form, submitting: true, fieldErrors: {}, submitError: null } });
  try {
    const { change_reason: changeReason, ...fields } = form.values;
    if (form.mode === "create") {
      await createRequirement(api().network, connection, fields);
    } else {
      // Only send change_reason when the user actually typed one: an empty
      // string is rejected outright by `extended`-preset workspaces, and the
      // field is meaningless to `minimal`/`standard` ones.
      await updateRequirement(api().network, connection, form.requirementId!, {
        ...fields,
        ...(changeReason ? { change_reason: changeReason } : {}),
      });
    }
    setState({ view: "list", form: null });
    await loadRequirements(state.requirementsPage);
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    if (err instanceof ReqogniLoomApiError && err.envelope && err.envelope.error.details.length > 0) {
      const fieldErrors: Record<string, string[]> = {};
      for (const d of err.envelope.error.details) fieldErrors[d.field] = d.errors;
      setState({ form: { ...form, submitting: false, fieldErrors } });
      return;
    }
    setState({
      form: {
        ...form,
        submitting: false,
        submitError: err instanceof ReqogniLoomApiError ? err.message : "Failed to save.",
      },
    });
  }
}
