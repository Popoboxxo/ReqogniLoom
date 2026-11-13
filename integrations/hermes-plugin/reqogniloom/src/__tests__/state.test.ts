import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HermesPluginAPI } from "../hermes-api-types";
import {
  createRequirement,
  getRequirement,
  listRequirements,
  listWorkspaces,
  updateRequirement,
  type Requirement,
  type Workspace,
  ReqogniLoomApiError,
} from "../api";
import type { InterviewState } from "../mcpClient";

// Mock the api module so state.ts's calls to listWorkspaces are fully
// controlled by each test without touching real network.fetch.
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
    listRequirements: vi.fn(),
    getRequirement: vi.fn(),
    createRequirement: vi.fn(),
    updateRequirement: vi.fn(),
  };
});

// Mock the mcpClient module so state.ts's interview.* calls are fully
// controlled by each test without touching real network.fetch.
vi.mock("../mcpClient", async () => {
  const actual = await vi.importActual<typeof import("../mcpClient")>("../mcpClient");
  return {
    ...actual,
    interviewStart: vi.fn(),
    interviewGetState: vi.fn(),
    interviewAnswer: vi.fn(),
    interviewList: vi.fn(),
    interviewFormalize: vi.fn(),
    interviewGroundingContext: vi.fn(),
    interviewSetTarget: vi.fn(),
  };
});

import * as mcpClient from "../mcpClient";
import {
  __resetStateForTesting,
  answerInterviewField,
  backToConnected,
  backToList,
  cancelInterview,
  chooseWorkspace,
  closeInterview,
  connectWithCredentials,
  disconnect,
  formalizeInterview,
  getState,
  initState,
  openCreateForm,
  openEditForm,
  openInBrowser,
  openInterviews,
  openRequirements,
  REQUIREMENT_CHANGE_REASON_REQUIRED_MESSAGE,
  REQUIREMENT_CONFLICT_MESSAGE,
  REQUIREMENT_FORBIDDEN_MESSAGE,
  requirementsPageNext,
  requirementsPagePrevious,
  resumeInterview,
  searchRequirements,
  selectRequirement,
  setInterviewTarget,
  startNewInterview,
  submitForm,
  subscribe,
  updateFormField,
} from "../state";

const listWorkspacesMock = vi.mocked(listWorkspaces);
const listRequirementsMock = vi.mocked(listRequirements);
const getRequirementMock = vi.mocked(getRequirement);
const createRequirementMock = vi.mocked(createRequirement);
const updateRequirementMock = vi.mocked(updateRequirement);

function createMockApi(storedValue: string | null = null): HermesPluginAPI {
  const storage = new Map<string, string>();
  if (storedValue !== null) {
    storage.set("reqogniloom-connection", storedValue);
  }

  return {
    ui: {
      updateStatusBarItem: vi.fn(),
    },
    storage: {
      get: vi.fn(async (key: string) => storage.get(key) ?? null),
      set: vi.fn(async (key: string, value: string) => {
        storage.set(key, value);
      }),
      delete: vi.fn(async (key: string) => {
        storage.delete(key);
      }),
    },
    network: {
      fetch: vi.fn(),
    },
    shell: {
      openExternal: vi.fn(async () => {}),
    },
  } as unknown as HermesPluginAPI;
}

const workspaceA: Workspace = { id: "ws-1", name: "Alpha" };
const workspaceB: Workspace = { id: "ws-2", name: "Beta" };

beforeEach(() => {
  __resetStateForTesting();
  listWorkspacesMock.mockReset();
  listRequirementsMock.mockReset();
  getRequirementMock.mockReset();
  createRequirementMock.mockReset();
  updateRequirementMock.mockReset();
});

describe("initState", () => {
  it("stays on connect view with no stored connection", async () => {
    const api = createMockApi(null);
    await initState(api);

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(api.ui.updateStatusBarItem).toHaveBeenCalledWith("reqogniloom.status", {
      text: "ReqogniLoom",
      tooltip: "Open ReqogniLoom panel",
    });
  });

  it("restores connected view from stored connection", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);

    const state = getState();
    expect(state.view).toBe("connected");
    expect(state.workspaceName).toBe("Alpha");
    expect(state.connection).toEqual({ baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" });
    expect(api.ui.updateStatusBarItem).toHaveBeenCalledWith("reqogniloom.status", {
      text: "ReqogniLoom: Alpha",
      tooltip: "Connected to Alpha",
    });
  });

  it("drops a stored entry whose connection is null and stays on the connect view", async () => {
    const api = createMockApi(JSON.stringify({ connection: null }));
    await initState(api);

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(state.workspaceName).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("drops a stored connection with an empty apiKey instead of restoring a dead panel", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("drops a stored connection with an empty baseUrl", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "", apiKey: "reqlo_abc", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);

    expect(getState().view).toBe("connect");
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });
});

describe("connectWithCredentials", () => {
  it("auto-selects a single workspace and moves to connected", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([workspaceA]);

    await connectWithCredentials("https://example.com", "reqlo_abc");

    const state = getState();
    expect(state.view).toBe("connected");
    expect(state.workspaceName).toBe("Alpha");
    expect(state.connection).toEqual({
      baseUrl: "https://example.com",
      apiKey: "reqlo_abc",
      workspaceId: "ws-1",
    });
    expect(state.connecting).toBe(false);
    expect(api.storage.set).toHaveBeenCalled();
  });

  it("populates pendingWorkspaces and stays on connect for multiple workspaces", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([workspaceA, workspaceB]);

    await connectWithCredentials("https://example.com", "reqlo_abc");

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.pendingWorkspaces).toEqual([workspaceA, workspaceB]);
    expect(state.pendingCredentials).toEqual({ baseUrl: "https://example.com", apiKey: "reqlo_abc" });
    expect(state.connection).toBeNull();
  });

  it("sets connectError for zero workspaces", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([]);

    await connectWithCredentials("https://example.com", "reqlo_abc");

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connectError).toBe("No workspaces accessible with this API key.");
    expect(state.connecting).toBe(false);
  });

  it("sets connectError to the ReqogniLoomApiError message for a bad key", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockRejectedValue(new ReqogniLoomApiError(401, null, "Invalid API key"));

    await connectWithCredentials("https://example.com", "reqlo_bad");

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connectError).toBe("Invalid API key");
    expect(state.connecting).toBe(false);
  });

  it("clears connecting and surfaces an error when the request aborts on timeout", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockRejectedValue(new DOMException("The operation was aborted", "TimeoutError"));

    await connectWithCredentials("https://example.com", "reqlo_abc");

    const state = getState();
    expect(state.connecting).toBe(false);
    expect(state.connectError).not.toBeNull();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
  });});

describe("chooseWorkspace", () => {
  it("finalizes connection with the picked workspace", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([workspaceA, workspaceB]);
    await connectWithCredentials("https://example.com", "reqlo_abc");

    await chooseWorkspace(workspaceB);

    const state = getState();
    expect(state.view).toBe("connected");
    expect(state.workspaceName).toBe("Beta");
    expect(state.connection).toEqual({
      baseUrl: "https://example.com",
      apiKey: "reqlo_abc",
      workspaceId: "ws-2",
    });
    expect(state.pendingWorkspaces).toEqual([]);
    expect(state.pendingCredentials).toBeNull();
  });

  it("sets connectError instead of an unhandled rejection when finalizing fails", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([workspaceA, workspaceB]);
    await connectWithCredentials("https://example.com", "reqlo_abc");
    expect(getState().view).toBe("connect");

    vi.mocked(api.storage.set).mockRejectedValueOnce(new ReqogniLoomApiError(500, null, "Storage write failed"));

    await expect(chooseWorkspace(workspaceB)).resolves.not.toThrow();

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connectError).toBe("Storage write failed");
    expect(state.connecting).toBe(false);
    // still stuck picking, but now with visible feedback instead of silence
    expect(state.pendingWorkspaces).toEqual([workspaceA, workspaceB]);
  });
});

describe("disconnect", () => {
  it("clears storage and resets to connect view", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);
    expect(getState().view).toBe("connected");

    await disconnect();

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(state.workspaceName).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("still returns to the connect view when storage.delete rejects, without rejecting to the fire-and-forget call site", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);
    expect(getState().view).toBe("connected");

    vi.mocked(api.storage.delete).mockRejectedValueOnce(new Error("storage unavailable"));

    // The panel calls this as `void disconnect()`, so a rejection here would
    // surface only as an unhandled rejection -- it must not escape.
    await expect(disconnect()).resolves.toBeUndefined();

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(state.workspaceName).toBeNull();
  });
});

describe("openInBrowser", () => {
  it("calls shell.openExternal with the connection baseUrl when connected", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);

    await openInBrowser();

    expect(api.shell.openExternal).toHaveBeenCalledWith("https://example.com");
  });

  it("does nothing when not connected", async () => {
    const api = createMockApi(null);
    await initState(api);

    await expect(openInBrowser()).resolves.not.toThrow();
    expect(api.shell.openExternal).not.toHaveBeenCalled();
  });
});

// Drives the real connect flow (with listWorkspaces mocked) rather than
// poking at module-internal state directly, so these tests exercise the
// same path a user would take to reach the "connected" view.
async function connectedState(): Promise<HermesPluginAPI> {
  const api = createMockApi();
  await initState(api);
  listWorkspacesMock.mockResolvedValue([workspaceA]);
  await connectWithCredentials("https://example.com", "reqlo_abc");
  return api;
}

const fakeInterviewState = {
  session_id: "s-1",
  status: "in_progress" as const,
  phase: "elicitation",
  collected_fields: {},
  missing_fields: [{ name: "title", type: "text" as const, choices: null }],
  grounding_snapshot: { candidates: [] },
};

describe("interview state", () => {
  it("startNewInterview stores the returned InterviewState and switches view", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);

    await startNewInterview("Requirement");

    expect(getState().view).toBe("interviews");
    expect(getState().activeInterview).toEqual(fakeInterviewState);
  });

  it("answerInterviewField calls interviewAnswer and refreshes activeInterview", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewAnswer).mockResolvedValue({
      session_id: "s-1",
      status: "in_progress",
      phase: "elicitation",
      collected_fields: { title: "SSO login" },
      missing_fields: [],
      grounding_snapshot: { candidates: [] },
    });

    await answerInterviewField("title", "SSO login");

    expect(mcpClient.interviewAnswer).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      "s-1",
      "title",
      "SSO login"
    );
    expect(getState().activeInterview?.collected_fields.title).toBe("SSO login");
  });

  it("a failed interviewStart sets interviewError and does not switch view", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockRejectedValue(new Error("boom"));

    await startNewInterview("Requirement");

    expect(getState().interviewError).toBe("boom");
    expect(getState().view).not.toBe("interviews");
  });

  it("closeInterview clears activeInterview and returns to the connected view", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");

    closeInterview();

    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("connected");
  });

  it("cancelInterview clears activeInterview and returns to the interviews list instead of skipping past it", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    const summaries = [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }];
    vi.mocked(mcpClient.interviewList).mockResolvedValue(summaries);

    await cancelInterview();

    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("interviews");
    expect(getState().interviewList).toEqual(summaries);
  });

  it("resumeInterview loads an existing session via interviewGetState", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewGetState).mockResolvedValue(fakeInterviewState);

    await resumeInterview("s-1");

    expect(mcpClient.interviewGetState).toHaveBeenCalledWith(expect.anything(), expect.anything(), "s-1");
    expect(getState().view).toBe("interviews");
    expect(getState().activeInterview).toEqual(fakeInterviewState);
  });

  it("startNewInterview fetches grounding context and merges candidates into activeInterview", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    vi.mocked(mcpClient.interviewGroundingContext).mockResolvedValue({
      candidates: [{ artifact_id: "art-9", title: "Similar existing req", score: null }],
    });

    await startNewInterview("Requirement");

    expect(mcpClient.interviewGroundingContext).toHaveBeenCalledWith(expect.anything(), expect.anything(), "s-1");
    expect(getState().activeInterview?.grounding_snapshot.candidates).toEqual([
      { artifact_id: "art-9", title: "Similar existing req", score: null },
    ]);
  });

  it("startNewInterview still succeeds (no interviewError) when grounding context lookup fails", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    vi.mocked(mcpClient.interviewGroundingContext).mockRejectedValue(new Error("grounding boom"));

    await startNewInterview("Requirement");

    expect(getState().activeInterview).not.toBeNull();
    expect(getState().activeInterview?.session_id).toBe("s-1");
    expect(getState().interviewError).toBeNull();
  });

  it("openInterviews loads the interview list and switches view", async () => {
    await connectedState();
    const summaries = [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }];
    vi.mocked(mcpClient.interviewList).mockResolvedValue(summaries);

    await openInterviews();

    expect(mcpClient.interviewList).toHaveBeenCalledWith(expect.anything(), expect.anything(), "in_progress");
    expect(getState().view).toBe("interviews");
    expect(getState().interviewList).toEqual(summaries);
  });

  it("setInterviewTarget calls interviewSetTarget and refreshes activeInterview", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewSetTarget).mockResolvedValue({
      session_id: "s-1",
      status: "in_progress",
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [],
      grounding_snapshot: { candidates: [{ artifact_id: "art-9", title: "Similar existing req", score: null }] },
    });

    await setInterviewTarget("art-9");

    expect(mcpClient.interviewSetTarget).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      "s-1",
      "art-9"
    );
    expect(getState().activeInterview?.missing_fields).toEqual([]);
  });

  it("a failed setInterviewTarget sets interviewError and leaves activeInterview untouched", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewSetTarget).mockRejectedValue(new Error("not a Requirement session"));

    await setInterviewTarget("art-9");

    expect(getState().interviewError).toBe("not a Requirement session");
    expect(getState().activeInterview).toEqual(fakeInterviewState);
  });

  it("formalizeInterview calls interviewFormalize and returns the result", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewFormalize).mockResolvedValue({
      resulting_artifact_ids: ["REQ-1"],
      status: "completed",
    });

    const result = await formalizeInterview();

    expect(mcpClient.interviewFormalize).toHaveBeenCalledWith(expect.anything(), expect.anything(), "s-1");
    expect(result).toEqual({ resulting_artifact_ids: ["REQ-1"], status: "completed" });
    // activeInterview must flip to completed so InterviewFormView's read-only
    // branch takes over instead of re-rendering the (now stale) in-progress form.
    expect(getState().activeInterview?.status).toBe("completed");
  });

  it("formalizeInterview uses the server's returned status rather than hardcoding 'completed'", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewFormalize).mockResolvedValue({
      resulting_artifact_ids: [],
      status: "abandoned",
    });

    await formalizeInterview();

    expect(getState().activeInterview?.status).toBe("abandoned");
  });

  it("answerInterviewField discards a stale response if the session was closed while the call was in flight", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");

    let resolveAnswer!: (value: InterviewState) => void;
    vi.mocked(mcpClient.interviewAnswer).mockReturnValue(
      new Promise((resolve) => {
        resolveAnswer = resolve;
      })
    );

    const pending = answerInterviewField("title", "SSO login");
    closeInterview(); // user navigates away while the call is still in flight
    resolveAnswer({
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: { title: "SSO login" }, missing_fields: [],
      grounding_snapshot: { candidates: [] },
    });
    await pending;

    // Must not resurrect a phantom activeInterview after the user navigated away.
    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("connected");
  });

  it("formalizeInterview discards a stale response if the session was closed while formalizing", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");

    let resolveFormalize!: (value: { resulting_artifact_ids: string[]; status: string }) => void;
    vi.mocked(mcpClient.interviewFormalize).mockReturnValue(
      new Promise((resolve) => {
        resolveFormalize = resolve;
      })
    );

    const pending = formalizeInterview();
    closeInterview();
    resolveFormalize({ resulting_artifact_ids: ["REQ-1"], status: "completed" });
    await pending;

    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("connected");
  });

  it("setInterviewTarget discards a stale response if the session was closed while the call was in flight", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");

    let resolveTarget!: (value: InterviewState) => void;
    vi.mocked(mcpClient.interviewSetTarget).mockReturnValue(
      new Promise((resolve) => {
        resolveTarget = resolve;
      })
    );

    const pending = setInterviewTarget("art-9");
    closeInterview();
    resolveTarget({
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: {}, missing_fields: [],
      grounding_snapshot: { candidates: [{ artifact_id: "art-9", title: "x", score: null }] },
    });
    await pending;

    expect(getState().activeInterview).toBeNull();
  });

  it("clears interviewBusy and surfaces an error when a list request aborts on timeout", async () => {
    await connectedState();
    // What an AbortSignal.timeout rejection actually is: a DOMException, not
    // an Error subclass in every host, so the specific message is not
    // guaranteed here -- the contract is a cleared busy flag and a visible
    // error rather than a stuck "Loading…" panel.
    vi.mocked(mcpClient.interviewList).mockRejectedValue(
      new DOMException("The operation was aborted", "TimeoutError")
    );

    await openInterviews();

    const state = getState();
    expect(state.interviewBusy).toBe(false);
    expect(state.interviewError).not.toBeNull();
    expect(state.interviewList).toEqual([]);
  });

  it("clears interviewBusy and surfaces the abort message when a formalize request fails", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewFormalize).mockRejectedValue(
      new Error("The operation was aborted due to timeout")
    );

    const result = await formalizeInterview();

    expect(result).toBeNull();
    expect(getState().interviewBusy).toBe(false);
    expect(getState().interviewError).toMatch(/aborted due to timeout/);
  });
});

describe("subscribe", () => {
  it("notifies listeners on state changes and stops after unsubscribe", async () => {
    const api = createMockApi();
    await initState(api);
    listWorkspacesMock.mockResolvedValue([workspaceA]);

    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    await connectWithCredentials("https://example.com", "reqlo_abc");
    expect(listener).toHaveBeenCalled();

    unsubscribe();
    listener.mockClear();

    await disconnect();
    expect(listener).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Requirements (Phase H / #1701, Task 2)
// ---------------------------------------------------------------------------

const requirementFixture: Requirement = {
  id: "req-1",
  artifact_id: "art-1",
  global_uuid: "art-1",
  workspace_id: "ws-1",
  parent_id: null,
  uid: "REQ-1",
  title: "Login must work",
  description: "Users sign in with SSO.",
  acceptance_criteria: "A valid token grants access.",
  category: "security",
  type: "SyReq",
  complexity_fibonacci: 3,
  verification_method: "Test",
  level: 2,
  tier_key: "system",
  tier_name: "System",
  released_tier_key: null,
  level_source: "derived",
  allocation_intent: "unassigned",
  status: "draft",
  suspect: false,
  atomicity_warning: null,
  version: 7,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

function emptyRequirementPage() {
  return { count: 0, next: null, previous: null, results: [] };
}

// Selects the fixture as the active requirement, so openEditForm() has a
// version to send — the same path a user takes (list → row → form).
async function openEditFormForFixture(): Promise<void> {
  getRequirementMock.mockResolvedValue(requirementFixture);
  await selectRequirement("req-1");
  openEditForm();
}

describe("requirement list state", () => {
  it("openRequirements loads page 1 and switches the view", async () => {
    await connectedState();
    listRequirementsMock.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [requirementFixture],
    });

    await openRequirements();

    expect(listRequirementsMock).toHaveBeenCalledWith(expect.anything(), expect.anything(), {
      page: 1,
      pageSize: 25,
      search: undefined,
    });
    const state = getState();
    expect(state.view).toBe("requirements");
    expect(state.requirements).toEqual([requirementFixture]);
    expect(state.requirementsCount).toBe(1);
    expect(state.requirementsPage).toBe(1);
    expect(state.requirementBusy).toBe(false);
    expect(state.requirementError).toBeNull();
  });

  it("openRequirements stays on the list view and shows the error when the request fails", async () => {
    await connectedState();
    listRequirementsMock.mockRejectedValue(new ReqogniLoomApiError(500, null, "Server error"));

    await openRequirements();

    const state = getState();
    expect(state.view).toBe("requirements");
    expect(state.requirementError).toBe("Server error");
    expect(state.requirementBusy).toBe(false);
    expect(state.requirements).toEqual([]);
  });

  it("searchRequirements restarts at page 1 with the term", async () => {
    await connectedState();
    listRequirementsMock.mockResolvedValue(emptyRequirementPage());

    await searchRequirements("login");

    expect(listRequirementsMock).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), {
      page: 1,
      pageSize: 25,
      search: "login",
    });
    expect(getState().requirementsSearch).toBe("login");
    expect(getState().view).toBe("requirements");
  });

  it("pagination follows next and previous and stops on a repeated next link", async () => {
    await connectedState();
    const page1 = "https://example.com/api/v1/requirements/?workspace_id=ws-1&page=1&page_size=25";
    const page2 = "https://example.com/api/v1/requirements/?workspace_id=ws-1&page=2&page_size=25";
    listRequirementsMock
      .mockResolvedValueOnce({ count: 30, next: page2, previous: null, results: [requirementFixture] })
      .mockResolvedValueOnce({
        count: 30,
        next: page2,
        previous: page1,
        results: [{ ...requirementFixture, id: "req-2" }],
      })
      .mockResolvedValueOnce({ count: 30, next: page2, previous: null, results: [requirementFixture] });

    await openRequirements();
    await requirementsPageNext();

    expect(listRequirementsMock).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), { url: page2 });
    expect(getState().requirementsPage).toBe(2);
    expect(getState().requirements[0].id).toBe("req-2");
    expect(getState().requirementsPrevious).toBe(page1);
    // A `next` that repeats the link just requested would loop forever; the
    // chain ends instead of storing it.
    expect(getState().requirementsNext).toBeNull();

    await requirementsPageNext();
    expect(listRequirementsMock).toHaveBeenCalledTimes(2);

    await requirementsPagePrevious();
    expect(listRequirementsMock).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), { url: page1 });
    expect(getState().requirementsPage).toBe(1);
    expect(getState().requirementsNext).toBe(page2);
  });

  it("requirementsPageNext does nothing without a next link", async () => {
    await connectedState();
    listRequirementsMock.mockResolvedValue(emptyRequirementPage());
    await openRequirements();

    await requirementsPageNext();

    expect(listRequirementsMock).toHaveBeenCalledTimes(1);
  });
});

describe("requirement detail state", () => {
  it("selectRequirement loads the detail and switches the view", async () => {
    await connectedState();
    getRequirementMock.mockResolvedValue(requirementFixture);

    await selectRequirement("req-1");

    expect(getRequirementMock).toHaveBeenCalledWith(expect.anything(), expect.anything(), "req-1");
    const state = getState();
    expect(state.view).toBe("requirement-detail");
    expect(state.activeRequirement).toEqual(requirementFixture);
    expect(state.requirementBusy).toBe(false);
  });

  it("selectRequirement reports a failed detail load without keeping a stale row", async () => {
    await connectedState();
    getRequirementMock.mockRejectedValue(new ReqogniLoomApiError(404, null, "Requirement not found"));

    await selectRequirement("req-1");

    const state = getState();
    expect(state.view).toBe("requirement-detail");
    expect(state.activeRequirement).toBeNull();
    expect(state.requirementError).toBe("Requirement not found");
    expect(state.requirementBusy).toBe(false);
  });
});

describe("requirement form state", () => {
  it("openCreateForm starts an empty create form that holds no level field", () => {
    openCreateForm();

    const form = getState().requirementForm;
    expect(getState().view).toBe("requirement-form");
    expect(form?.mode).toBe("create");
    expect(form?.values).toEqual({
      title: "",
      description: "",
      acceptance_criteria: "",
      category: "",
      type: "SyReq",
    });
    expect(form?.values).not.toHaveProperty("level");
    expect(form?.values).not.toHaveProperty("tier_key");
    expect(form?.values).not.toHaveProperty("level_source");
  });

  it("openEditForm prefills the writable fields of the active requirement", async () => {
    await connectedState();
    await openEditFormForFixture();

    const form = getState().requirementForm;
    expect(getState().view).toBe("requirement-form");
    expect(form?.mode).toBe("edit");
    expect(form?.values).toEqual({
      title: "Login must work",
      description: "Users sign in with SSO.",
      acceptance_criteria: "A valid token grants access.",
      category: "security",
      type: "SyReq",
    });
    expect(form?.values).not.toHaveProperty("level");
    expect(form?.values).not.toHaveProperty("tier_key");
    expect(form?.values).not.toHaveProperty("level_source");
  });

  it("openEditForm is a no-op without a loaded requirement", async () => {
    await connectedState();

    openEditForm();

    expect(getState().requirementForm).toBeNull();
    expect(getState().view).toBe("connected");
  });

  it("updateFormField writes a value and ignores a field the form does not own", () => {
    openCreateForm();

    updateFormField("title", "Login");
    updateFormField("level", "3");
    updateFormField("tier_key", "system");

    const form = getState().requirementForm;
    expect(form?.values.title).toBe("Login");
    expect(form?.values).not.toHaveProperty("level");
    expect(form?.values).not.toHaveProperty("tier_key");
  });

  it("updateFormField stores the change reason separately from the values", () => {
    openCreateForm();

    updateFormField("change_reason", "because the requirement changed");

    expect(getState().requirementForm?.changeReason).toBe("because the requirement changed");
    expect(getState().requirementForm?.values).not.toHaveProperty("change_reason");
  });
});

describe("submitForm", () => {
  it("in create mode posts only writable fields and opens the new requirement", async () => {
    await connectedState();
    createRequirementMock.mockResolvedValue(requirementFixture);
    listRequirementsMock.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [requirementFixture],
    });

    openCreateForm();
    updateFormField("title", "  Login must work  ");
    updateFormField("description", "Users sign in with SSO.");
    await submitForm();

    expect(createRequirementMock).toHaveBeenCalledTimes(1);
    const payload = createRequirementMock.mock.calls[0][2];
    expect(payload).toEqual({
      title: "Login must work",
      description: "Users sign in with SSO.",
      acceptance_criteria: "",
      category: "",
      type: "SyReq",
    });
    expect(payload).not.toHaveProperty("level");
    expect(payload).not.toHaveProperty("tier_key");
    expect(payload).not.toHaveProperty("level_source");
    expect(payload).not.toHaveProperty("version");
    const state = getState();
    expect(state.view).toBe("requirement-detail");
    expect(state.activeRequirement).toEqual(requirementFixture);
    expect(state.requirementForm).toBeNull();
    expect(state.requirementBusy).toBe(false);
  });

  it("refreshes the cached list page after a successful create", async () => {
    await connectedState();
    createRequirementMock.mockResolvedValue(requirementFixture);
    listRequirementsMock.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [requirementFixture],
    });

    openCreateForm();
    updateFormField("title", "Login must work");
    await submitForm();

    expect(listRequirementsMock).toHaveBeenCalledWith(expect.anything(), expect.anything(), {
      page: 1,
      pageSize: 25,
      search: undefined,
    });
    expect(getState().requirements).toEqual([requirementFixture]);
  });

  it("sends nothing and sets a title error when the title is empty", async () => {
    await connectedState();
    openCreateForm();

    await submitForm();

    expect(createRequirementMock).not.toHaveBeenCalled();
    const state = getState();
    expect(state.view).toBe("requirement-form");
    expect(state.requirementForm?.fieldErrors.title).toBe("A title is required.");
  });

  it("in edit mode PATCHes with the loaded version and no level field", async () => {
    await connectedState();
    await openEditFormForFixture();
    updateRequirementMock.mockResolvedValue({ ...requirementFixture, title: "Login must work twice", version: 8 });
    listRequirementsMock.mockResolvedValue(emptyRequirementPage());

    updateFormField("title", "Login must work twice");
    await submitForm();

    expect(updateRequirementMock).toHaveBeenCalledTimes(1);
    const [, , id, payload] = updateRequirementMock.mock.calls[0];
    expect(id).toBe("req-1");
    expect(payload.version).toBe(7);
    expect(payload.title).toBe("Login must work twice");
    expect(payload).not.toHaveProperty("level");
    expect(payload).not.toHaveProperty("tier_key");
    expect(payload).not.toHaveProperty("level_source");
    expect(payload).not.toHaveProperty("change_reason");
    expect(getState().view).toBe("requirement-detail");
    expect(getState().activeRequirement?.version).toBe(8);
  });

  it("sends the change reason when one was typed", async () => {
    await connectedState();
    await openEditFormForFixture();
    updateRequirementMock.mockResolvedValue(requirementFixture);
    listRequirementsMock.mockResolvedValue(emptyRequirementPage());

    updateFormField("change_reason", "clarified wording");
    await submitForm();

    expect(updateRequirementMock.mock.calls[0][3].change_reason).toBe("clarified wording");
  });

  it("shows field errors from a 400 details array and keeps the input", async () => {
    await connectedState();
    await openEditFormForFixture();
    updateRequirementMock.mockRejectedValue(
      new ReqogniLoomApiError(
        400,
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Invalid request.",
            details: [{ field: "title", errors: ["Ensure this field has no more than 500 characters."] }],
          },
        },
        "Invalid request."
      )
    );

    updateFormField("title", "x".repeat(501));
    await submitForm();

    const state = getState();
    expect(state.view).toBe("requirement-form");
    expect(state.requirementError).toBeNull();
    expect(state.requirementForm?.fieldErrors.title).toBe("Ensure this field has no more than 500 characters.");
    expect(state.requirementForm?.values.title).toHaveLength(501);
  });

  it("marks change_reason as required when the server demands a reason", async () => {
    await connectedState();
    await openEditFormForFixture();
    const message = "change_reason required by workspace preset policy";
    updateRequirementMock.mockRejectedValue(
      new ReqogniLoomApiError(400, { error: { code: "VALIDATION_ERROR", message, details: [] } }, message)
    );

    await submitForm();

    const state = getState();
    expect(state.requirementForm?.fieldErrors.change_reason).toBe(REQUIREMENT_CHANGE_REASON_REQUIRED_MESSAGE);
    expect(state.requirementError).toBeNull();

    // Typing a reason clears the field error, as every other field does.
    updateFormField("change_reason", "because the preset says so");
    expect(getState().requirementForm?.fieldErrors).not.toHaveProperty("change_reason");
  });

  it("on 409 keeps the form values and shows the reload hint", async () => {
    await connectedState();
    await openEditFormForFixture();
    updateRequirementMock.mockRejectedValue(new ReqogniLoomApiError(409, null, "Version mismatch."));

    updateFormField("title", "Login must work twice");
    await submitForm();

    const state = getState();
    expect(state.view).toBe("requirement-form");
    expect(state.requirementError).toBe(REQUIREMENT_CONFLICT_MESSAGE);
    expect(state.requirementError).toMatch(/changed elsewhere/);
    expect(state.requirementForm?.mode).toBe("edit");
    expect(state.requirementForm?.values.title).toBe("Login must work twice");
    expect(state.requirementBusy).toBe(false);
  });

  it("on 403 shows the permission message and stays in the form", async () => {
    await connectedState();
    openCreateForm();
    createRequirementMock.mockRejectedValue(new ReqogniLoomApiError(403, null, "Forbidden"));

    updateFormField("title", "Login must work");
    await submitForm();

    const state = getState();
    expect(state.requirementError).toBe(REQUIREMENT_FORBIDDEN_MESSAGE);
    expect(state.view).toBe("requirement-form");
    expect(state.requirementForm?.values.title).toBe("Login must work");
    expect(state.requirementBusy).toBe(false);
  });

  it("clears requirementBusy and surfaces the message for an unexpected failure", async () => {
    await connectedState();
    openCreateForm();
    createRequirementMock.mockRejectedValue(new DOMException("The operation was aborted", "TimeoutError"));

    updateFormField("title", "Login must work");
    await submitForm();

    expect(getState().requirementBusy).toBe(false);
    expect(getState().requirementError).not.toBeNull();
    expect(getState().view).toBe("requirement-form");
  });
});

describe("requirement navigation", () => {
  it("backToList returns to the list and keeps the draft", async () => {
    await connectedState();
    openCreateForm();
    updateFormField("title", "unsaved draft");

    backToList();

    const state = getState();
    expect(state.view).toBe("requirements");
    expect(state.requirementError).toBeNull();
    expect(state.requirementForm?.values.title).toBe("unsaved draft");
  });

  it("backToConnected clears the selected requirement and the draft", async () => {
    await connectedState();
    await openEditFormForFixture();

    backToConnected();

    const state = getState();
    expect(state.view).toBe("connected");
    expect(state.activeRequirement).toBeNull();
    expect(state.requirementForm).toBeNull();
    expect(state.requirementError).toBeNull();
  });
});
