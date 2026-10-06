import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HermesPluginAPI } from "../hermes-api-types";
import { ReqogniLoomApiError, type Workspace } from "../api";
import type { InterviewState, InterviewSummary, MemoryQueryResult } from "../mcpClient";

// Mock the api module so state.ts's calls to listWorkspaces are fully
// controlled by each test without touching real network.fetch.
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
  };
});

// Mock the mcpClient module so state.ts's interview.* / memory.* calls are
// fully controlled by each test without touching real network.fetch.
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
    interviewAbandon: vi.fn(),
    memoryQuery: vi.fn(),
    memoryDigest: vi.fn(),
    memoryAsk: vi.fn(),
    memoryWrite: vi.fn(),
  };
});

import { listWorkspaces } from "../api";
import * as mcpClient from "../mcpClient";
import {
  __resetStateForTesting,
  answerInterviewField,
  askMemory,
  cancelCapture,
  cancelInterview,
  chooseWorkspace,
  closeInterview,
  confirmCapture,
  connectWithCredentials,
  disconnect,
  formalizeInterview,
  getState,
  initState,
  loadMemoryContext,
  openInBrowser,
  openInterviews,
  requestCapture,
  resumeInterview,
  setCaptureEnabled,
  setInterviewTarget,
  startNewInterview,
  subscribe,
} from "../state";

const listWorkspacesMock = vi.mocked(listWorkspaces);

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
  vi.mocked(mcpClient.memoryQuery).mockReset();
  vi.mocked(mcpClient.memoryDigest).mockReset();
  vi.mocked(mcpClient.memoryAsk).mockReset();
  vi.mocked(mcpClient.memoryWrite).mockReset();
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

  it("drops a stored connection with a missing workspaceId instead of restoring a half-dead panel", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc" },
      workspaceName: "Alpha",
    });
    const api = createMockApi(stored);
    await initState(api);

    const state = getState();
    expect(state.view).toBe("connect");
    expect(state.connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("drops a stored connection with an empty workspaceId", async () => {
    const stored = JSON.stringify({
      connection: { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "" },
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

  it("cancelInterview abandons the session server-side and returns to the interviews list", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewAbandon).mockResolvedValue({
      ...fakeInterviewState,
      status: "abandoned",
    });
    const summaries = [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }];
    vi.mocked(mcpClient.interviewList).mockResolvedValue(summaries);

    await cancelInterview();

    expect(mcpClient.interviewAbandon).toHaveBeenCalledWith(expect.anything(), expect.anything(), "s-1");
    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("interviews");
    expect(getState().interviewList).toEqual(summaries);
  });

  it("cancelInterview surfaces a failed abandon but still returns to the list", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeInterviewState);
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewAbandon).mockRejectedValue(new Error("not in_progress"));
    vi.mocked(mcpClient.interviewList).mockResolvedValue([]);

    await cancelInterview();

    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("interviews");
    expect(getState().interviewError).toBe("not in_progress");
  });

  it("cancelInterview calls no abandon tool when there is no active interview", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewAbandon).mockClear();
    vi.mocked(mcpClient.interviewList).mockResolvedValue([]);

    await cancelInterview();

    expect(mcpClient.interviewAbandon).not.toHaveBeenCalled();
    expect(getState().view).toBe("interviews");
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

describe("stale async guards", () => {
  it("openInterviews discards a stale response when the user disconnects mid-flight", async () => {
    await connectedState();
    let resolveList!: (value: InterviewSummary[]) => void;
    vi.mocked(mcpClient.interviewList).mockReturnValue(
      new Promise<InterviewSummary[]>((resolve) => {
        resolveList = resolve;
      })
    );

    const pending = openInterviews();
    await disconnect();
    resolveList([{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }]);
    await pending;

    const state = getState();
    expect(state.connection).toBeNull();
    expect(state.view).toBe("connect");
    expect(state.interviewList).toEqual([]);
  });

  it("startNewInterview discards a stale response when the user disconnects mid-flight", async () => {
    await connectedState();
    let resolveStart!: (value: InterviewState) => void;
    vi.mocked(mcpClient.interviewStart).mockReturnValue(
      new Promise<InterviewState>((resolve) => {
        resolveStart = resolve;
      })
    );

    const pending = startNewInterview("Requirement");
    await disconnect();
    resolveStart(fakeInterviewState);
    await pending;

    const state = getState();
    expect(state.connection).toBeNull();
    expect(state.view).toBe("connect");
    expect(state.activeInterview).toBeNull();
  });

  it("resumeInterview discards a stale response when the user disconnects mid-flight", async () => {
    await connectedState();
    let resolveGet!: (value: InterviewState) => void;
    vi.mocked(mcpClient.interviewGetState).mockReturnValue(
      new Promise<InterviewState>((resolve) => {
        resolveGet = resolve;
      })
    );

    const pending = resumeInterview("s-1");
    await disconnect();
    resolveGet(fakeInterviewState);
    await pending;

    const state = getState();
    expect(state.connection).toBeNull();
    expect(state.view).toBe("connect");
    expect(state.activeInterview).toBeNull();
  });
});

describe("memory read", () => {
  const sampleEntry = { entry_id: "e-1", content: "SSO required", scope: "workspace" as const, workspace_id: "ws-1" };

  it("loadMemoryContext loads entries and merges the digest", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryQuery).mockResolvedValue({ entries: [sampleEntry], degraded: false, detail: null });
    vi.mocked(mcpClient.memoryDigest).mockResolvedValue({ digest: "Workspace summary", degraded: false });

    await loadMemoryContext("ws-1");

    expect(mcpClient.memoryQuery).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ scope: "workspace", workspace_id: "ws-1", query: expect.any(String) })
    );
    const state = getState();
    expect(state.memoryEntries).toEqual([sampleEntry]);
    expect(state.memoryDigest).toBe("Workspace summary");
    expect(state.memoryDegraded).toBe(false);
    expect(state.memoryLoading).toBe(false);
    expect(state.memoryLoaded).toBe(true);
  });

  it("memoryLoaded starts false and flips true even when a load fails", async () => {
    await connectedState();
    expect(getState().memoryLoaded).toBe(false);

    vi.mocked(mcpClient.memoryQuery).mockRejectedValue(new Error("boom"));
    await loadMemoryContext("ws-1");

    expect(getState().memoryLoaded).toBe(true);
  });

  it("keeps a degraded read distinct from a genuine empty result", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryQuery).mockResolvedValue({
      entries: [],
      degraded: true,
      detail: "engine_error:TimeoutError",
    });
    vi.mocked(mcpClient.memoryDigest).mockRejectedValue(new Error("digest down"));

    await loadMemoryContext("ws-1");

    const state = getState();
    expect(state.memoryEntries).toEqual([]);
    expect(state.memoryDegraded).toBe(true);
    expect(state.memoryDetail).toBe("engine_error:TimeoutError");
    expect(state.memoryError).toBeNull();
  });

  it("an empty healthy read is not degraded", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryQuery).mockResolvedValue({ entries: [], degraded: false, detail: null });
    vi.mocked(mcpClient.memoryDigest).mockResolvedValue({ digest: "", degraded: false });

    await loadMemoryContext("ws-1");

    expect(getState().memoryDegraded).toBe(false);
    expect(getState().memoryEntries).toEqual([]);
  });

  it("a failed digest does not discard the entries memory.query returned", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryQuery).mockResolvedValue({ entries: [sampleEntry], degraded: false });
    vi.mocked(mcpClient.memoryDigest).mockRejectedValue(new Error("no digest"));

    await loadMemoryContext("ws-1");

    expect(getState().memoryEntries).toEqual([sampleEntry]);
    expect(getState().memoryDigest).toBeNull();
  });

  it("loadMemoryContext surfaces a query failure as memoryError", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryQuery).mockRejectedValue(new Error("boom"));

    await loadMemoryContext("ws-1");

    expect(getState().memoryError).toBe("boom");
    expect(getState().memoryLoading).toBe(false);
  });

  it("loadMemoryContext discards a stale response when the user disconnects mid-flight", async () => {
    await connectedState();
    let resolveQuery!: (value: MemoryQueryResult) => void;
    vi.mocked(mcpClient.memoryQuery).mockReturnValue(
      new Promise<MemoryQueryResult>((resolve) => {
        resolveQuery = resolve;
      })
    );

    const pending = loadMemoryContext("ws-1");
    await disconnect();
    resolveQuery({ entries: [sampleEntry], degraded: false });
    await pending;

    const state = getState();
    expect(state.connection).toBeNull();
    expect(state.memoryEntries).toEqual([]);
  });

  it("askMemory stores the answer", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryAsk).mockResolvedValue({ answer: "yes", degraded: false, detail: "" });

    await askMemory("ws-1", "is sso required?");

    expect(mcpClient.memoryAsk).toHaveBeenCalledWith(expect.anything(), expect.anything(), {
      query: "is sso required?",
      workspace_id: "ws-1",
    });
    expect(getState().memoryAnswer).toBe("yes");
    expect(getState().memoryLoading).toBe(false);
  });

  it("askMemory surfaces a failure and ignores a blank query", async () => {
    await connectedState();
    vi.mocked(mcpClient.memoryAsk).mockRejectedValue(new Error("llm down"));

    await askMemory("ws-1", "is sso required?");
    expect(getState().memoryError).toBe("llm down");

    vi.mocked(mcpClient.memoryAsk).mockClear();
    await askMemory("ws-1", "   ");
    expect(mcpClient.memoryAsk).not.toHaveBeenCalled();
  });
});

describe("gated capture", () => {
  it("requestCapture stages a draft without any network call", async () => {
    await connectedState();
    setCaptureEnabled(true);

    requestCapture("Use PostgreSQL 16");

    expect(getState().pendingCapture).toBe("Use PostgreSQL 16");
    expect(mcpClient.memoryWrite).not.toHaveBeenCalled();
  });

  it("does nothing while capture is disabled", async () => {
    await connectedState();

    requestCapture("fact");

    expect(getState().captureEnabled).toBe(false);
    expect(getState().pendingCapture).toBeNull();
  });

  it("confirmCapture performs memory.write and clears the draft", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("Use PostgreSQL 16");
    vi.mocked(mcpClient.memoryWrite).mockResolvedValue({
      entry_id: "e-1",
      content: "Use PostgreSQL 16",
      scope: "workspace",
    });

    await confirmCapture();

    expect(mcpClient.memoryWrite).toHaveBeenCalledTimes(1);
    expect(mcpClient.memoryWrite).toHaveBeenCalledWith(expect.anything(), expect.anything(), {
      content: "Use PostgreSQL 16",
      scope: "workspace",
      workspace_id: "ws-1",
    });
    expect(getState().pendingCapture).toBeNull();
  });

  it("confirmCapture does not write without a pending draft", async () => {
    await connectedState();
    setCaptureEnabled(true);

    await confirmCapture();

    expect(mcpClient.memoryWrite).not.toHaveBeenCalled();
  });

  it("does not write when capture was disabled before confirm", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("fact");
    setCaptureEnabled(false);

    await confirmCapture();

    expect(mcpClient.memoryWrite).not.toHaveBeenCalled();
  });

  it("toggling off discards a pending draft", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("fact");

    setCaptureEnabled(false);

    expect(getState().captureEnabled).toBe(false);
    expect(getState().pendingCapture).toBeNull();
  });

  it("cancelCapture clears the draft without a network call", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("fact");

    cancelCapture();

    expect(getState().pendingCapture).toBeNull();
    expect(mcpClient.memoryWrite).not.toHaveBeenCalled();
  });

  it("keeps the draft and surfaces captureError when memory.write fails", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("fact");
    vi.mocked(mcpClient.memoryWrite).mockRejectedValue(new Error("rate limited"));

    await confirmCapture();

    expect(getState().pendingCapture).toBe("fact");
    // A write failure belongs to the capture surface, not the read section.
    expect(getState().captureError).toBe("rate limited");
    expect(getState().memoryError).toBeNull();
    expect(getState().captureBusy).toBe(false);
  });

  it("clears captureError when a new draft is requested or cancelled", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("first");
    vi.mocked(mcpClient.memoryWrite).mockRejectedValue(new Error("boom"));
    await confirmCapture();
    expect(getState().captureError).toBe("boom");

    requestCapture("second");
    expect(getState().captureError).toBeNull();

    vi.mocked(mcpClient.memoryWrite).mockRejectedValue(new Error("boom again"));
    await confirmCapture();
    expect(getState().captureError).toBe("boom again");
    cancelCapture();
    expect(getState().captureError).toBeNull();
  });

  it("ignores a second confirmCapture while the first is in flight (no double write)", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("Use PostgreSQL 16");

    let resolveWrite!: (value: { entry_id: string; content: string; scope: "workspace" }) => void;
    vi.mocked(mcpClient.memoryWrite).mockReturnValue(
      new Promise((resolve) => {
        resolveWrite = resolve;
      })
    );

    const first = confirmCapture();
    // Second click while the first awaits: must be a no-op, not a second write.
    const second = confirmCapture();

    expect(mcpClient.memoryWrite).toHaveBeenCalledTimes(1);
    expect(getState().captureBusy).toBe(true);

    resolveWrite({ entry_id: "e-1", content: "Use PostgreSQL 16", scope: "workspace" });
    await Promise.all([first, second]);

    expect(mcpClient.memoryWrite).toHaveBeenCalledTimes(1);
    expect(getState().captureBusy).toBe(false);
    expect(getState().pendingCapture).toBeNull();
  });

  it("leaves captureBusy false after a successful confirm", async () => {
    await connectedState();
    setCaptureEnabled(true);
    requestCapture("fact");
    vi.mocked(mcpClient.memoryWrite).mockResolvedValue({ entry_id: "e-1", content: "fact", scope: "workspace" });

    await confirmCapture();

    expect(getState().captureBusy).toBe(false);
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
