import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HermesPluginAPI } from "../hermes-api-types";
import { ReqogniLoomApiError, type Workspace } from "../api";
import type { InterviewState } from "../mcpClient";

// Mock the api module so state.ts's calls to listWorkspaces are fully
// controlled by each test without touching real network.fetch.
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
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

import { listWorkspaces } from "../api";
import * as mcpClient from "../mcpClient";
import {
  __resetStateForTesting,
  answerInterviewField,
  cancelInterview,
  chooseWorkspace,
  closeInterview,
  connectWithCredentials,
  disconnect,
  formalizeInterview,
  getState,
  initState,
  openInBrowser,
  openInterviews,
  resumeInterview,
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
});

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
