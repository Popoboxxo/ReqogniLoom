import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HermesPluginAPI } from "../hermes-api-types";
import { ReqogniLoomApiError, type Workspace } from "../api";

// Mock the api module so state.ts's calls to listWorkspaces are fully
// controlled by each test without touching real network.fetch.
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
  };
});

import { listWorkspaces } from "../api";
import {
  __resetStateForTesting,
  chooseWorkspace,
  connectWithCredentials,
  disconnect,
  getState,
  initState,
  openInBrowser,
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
      registerPanel: vi.fn(),
      showPanel: vi.fn(),
      hidePanel: vi.fn(),
      togglePanel: vi.fn(),
      showToast: vi.fn(),
      updateStatusBarItem: vi.fn(),
    },
    commands: {
      register: vi.fn(),
      execute: vi.fn(),
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
    subscriptions: [],
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
