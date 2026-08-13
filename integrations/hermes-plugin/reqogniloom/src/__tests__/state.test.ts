import { describe, it, expect, vi, beforeEach } from "vitest";
import * as apiModule from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof apiModule>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
    listRequirements: vi.fn(),
    getRequirement: vi.fn(),
    createRequirement: vi.fn(),
    updateRequirement: vi.fn(),
  };
});

import {
  initState,
  getState,
  subscribe,
  connectWithCredentials,
  chooseWorkspace,
  disconnect,
  loadRequirements,
  setSearchTerm,
  __resetStateForTesting,
  selectRequirement,
  backToList,
  openCreateForm,
  openEditForm,
  updateFormField,
  submitForm,
} from "../state";
import { ReqogniLoomApiError } from "../api";

function createMockHermesAPI(overrides?: { storedConnection?: string | null }) {
  const store = new Map<string, string>();
  if (overrides?.storedConnection) store.set("reqogniloom-connection", overrides.storedConnection);
  return {
    ui: {
      registerPanel: vi.fn(),
      showPanel: vi.fn(),
      hidePanel: vi.fn(),
      togglePanel: vi.fn(),
      showToast: vi.fn(),
      updateStatusBarItem: vi.fn(),
    },
    commands: { register: vi.fn(() => ({ dispose: vi.fn() })), execute: vi.fn() },
    storage: {
      get: vi.fn((key: string) => Promise.resolve(store.get(key) ?? null)),
      set: vi.fn((key: string, value: string) => {
        store.set(key, value);
        return Promise.resolve();
      }),
      delete: vi.fn((key: string) => {
        store.delete(key);
        return Promise.resolve();
      }),
    },
    network: { fetch: vi.fn() },
    subscriptions: [],
  };
}

const workspace = { id: "w1", name: "Demo" };
const connection = { baseUrl: "https://reqo.example.com", apiKey: "reqlo_x", workspaceId: "w1" };

beforeEach(() => {
  vi.clearAllMocks();
  __resetStateForTesting();
});

describe("initState", () => {
  it("starts in the connect view when nothing is stored", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
  });

  it("restores a stored connection and loads the list directly", async () => {
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI({ storedConnection: JSON.stringify(connection) });
    await initState(api as never);
    expect(getState().view).toBe("list");
    expect(getState().connection).toEqual(connection);
    expect(apiModule.listRequirements).toHaveBeenCalled();
  });
});

describe("connectWithCredentials", () => {
  it("auto-selects the single workspace and moves to list", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().view).toBe("list");
    expect(getState().connection).toEqual(connection);
    expect(api.storage.set).toHaveBeenCalledWith("reqogniloom-connection", JSON.stringify(connection));
  });

  it("shows a workspace picker when there is more than one", async () => {
    const second = { id: "w2", name: "Second" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace, second]);
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().view).toBe("connect");
    expect(getState().pendingWorkspaces).toEqual([workspace, second]);
    expect(getState().connection).toBeNull();
  });

  it("sets connectError with no workspaces accessible", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([]);
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().connectError).toMatch(/no workspaces/i);
  });

  it("sets connectError on 401", async () => {
    vi.mocked(apiModule.listWorkspaces).mockRejectedValue(new ReqogniLoomApiError(401, null, "Invalid API key"));
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "bad-key");

    expect(getState().connectError).toBe("Invalid API key");
    expect(getState().connecting).toBe(false);
  });
});

describe("chooseWorkspace", () => {
  it("finalizes the connection and loads the list", async () => {
    const second = { id: "w2", name: "Second" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace, second]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await chooseWorkspace(second);

    expect(getState().view).toBe("list");
    expect(getState().connection?.workspaceId).toBe("w2");
    expect(api.storage.set).toHaveBeenCalledWith(
      "reqogniloom-connection",
      JSON.stringify({ ...connection, workspaceId: "w2" })
    );
  });
});

describe("loadRequirements", () => {
  it("populates the list on success", async () => {
    const req = { id: "r1", title: "Login" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [req as never],
    });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().requirements).toEqual([req]);
    expect(getState().requirementsCount).toBe(1);
    expect(getState().listLoading).toBe(false);
  });

  it("disconnects and returns to the connect view on 401", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements)
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockRejectedValueOnce(new ReqogniLoomApiError(401, null, "Invalid API key"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(getState().view).toBe("list");

    await loadRequirements();

    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("sets listError on a non-auth failure and stays on the list view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements)
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockRejectedValueOnce(new ReqogniLoomApiError(500, null, "Server error"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await loadRequirements();

    expect(getState().view).toBe("list");
    expect(getState().listError).toBe("Server error");
  });
});

describe("setSearchTerm / loadRequirements interaction", () => {
  it("reloads page 1 with the search term applied", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    setSearchTerm("login");
    await loadRequirements();

    expect(apiModule.listRequirements).toHaveBeenLastCalledWith(
      expect.anything(),
      connection,
      expect.objectContaining({ search: "login", page: 1 })
    );
  });
});

describe("disconnect", () => {
  it("clears storage and resets to the connect view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await disconnect();

    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });
});

describe("subscribe", () => {
  it("notifies listeners on state change", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([]);
    const api = createMockHermesAPI();
    await initState(api as never);
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(listener).toHaveBeenCalled();

    listener.mockClear();
    unsubscribe();
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(listener).not.toHaveBeenCalled();
  });
});

describe("selectRequirement / backToList", () => {
  it("loads the requirement detail and switches view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockResolvedValue({ id: "r1", title: "Login" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await selectRequirement("r1");

    expect(getState().view).toBe("detail");
    expect(getState().selectedRequirement).toEqual({ id: "r1", title: "Login" });
    expect(getState().detailLoading).toBe(false);
  });

  it("sets detailError on failure", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockRejectedValue(new ReqogniLoomApiError(404, null, "Not found"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await selectRequirement("missing");

    expect(getState().detailError).toBe("Not found");
  });

  it("backToList clears selection and returns to the list view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockResolvedValue({ id: "r1", title: "Login" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    await selectRequirement("r1");

    backToList();

    expect(getState().view).toBe("list");
    expect(getState().selectedRequirement).toBeNull();
  });
});

describe("create/edit form", () => {
  it("openCreateForm starts with empty values in create mode", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);

    openCreateForm();

    expect(getState().view).toBe("form");
    expect(getState().form).toEqual({
      mode: "create",
      values: { title: "" },
      requirementId: undefined,
      fieldErrors: {},
      submitting: false,
      submitError: null,
    });
  });

  it("openEditForm pre-fills values from the requirement in edit mode", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    const req = {
      id: "r1",
      title: "Login",
      description: "desc",
      acceptance_criteria: "ac",
      category: "auth",
      type: "SyReq",
      level: 1,
    } as never;

    openEditForm(req);

    expect(getState().view).toBe("form");
    expect(getState().form?.mode).toBe("edit");
    expect(getState().form?.requirementId).toBe("r1");
    expect(getState().form?.values.title).toBe("Login");
  });

  it("updateFormField updates a single field without touching others", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    openCreateForm();

    updateFormField("title", "New title");
    updateFormField("category", "auth");

    expect(getState().form?.values).toEqual({ title: "New title", category: "auth" });
  });

  it("submitForm creates a requirement and returns to the list on success", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 1, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockResolvedValue({ id: "r2", title: "New" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();
    updateFormField("title", "New");

    await submitForm();

    expect(apiModule.createRequirement).toHaveBeenCalledWith(expect.anything(), connection, { title: "New" });
    expect(getState().view).toBe("list");
    expect(getState().form).toBeNull();
  });

  it("submitForm updates an existing requirement in edit mode", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.updateRequirement).mockResolvedValue({ id: "r1", title: "Renamed" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openEditForm({ id: "r1", title: "Old" } as never);
    updateFormField("title", "Renamed");

    await submitForm();

    expect(apiModule.updateRequirement).toHaveBeenCalledWith(expect.anything(), connection, "r1", { title: "Renamed" });
    expect(getState().view).toBe("list");
  });

  // `extended`-preset workspaces reject every PATCH without a non-empty
  // change_reason ("change_reason required by workspace preset policy"), so the
  // edit payload must carry the one the user typed.
  it("submitForm sends change_reason on edit when the user supplied one", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.updateRequirement).mockResolvedValue({ id: "r1", title: "Renamed" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openEditForm({ id: "r1", title: "Old" } as never);
    updateFormField("title", "Renamed");
    updateFormField("change_reason", "clarified the wording");

    await submitForm();

    expect(apiModule.updateRequirement).toHaveBeenCalledWith(expect.anything(), connection, "r1", {
      title: "Renamed",
      change_reason: "clarified the wording",
    });
    expect(getState().view).toBe("list");
  });

  it("submitForm omits change_reason on edit when it was left blank", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.updateRequirement).mockResolvedValue({ id: "r1", title: "Renamed" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openEditForm({ id: "r1", title: "Old" } as never); // seeds change_reason: ""
    updateFormField("title", "Renamed");

    await submitForm();

    // An empty string is rejected outright by extended-preset workspaces, and
    // the field is meaningless to minimal/standard ones — so it must be absent,
    // not sent as "".
    const payload = vi.mocked(apiModule.updateRequirement).mock.calls[0][3];
    expect(payload).not.toHaveProperty("change_reason");
    expect(payload).toMatchObject({ title: "Renamed" });
  });

  it("submitForm never sends change_reason on create", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 1, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockResolvedValue({ id: "r2", title: "New" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();
    updateFormField("title", "New");
    updateFormField("change_reason", "should never reach the create endpoint");

    await submitForm();

    const payload = vi.mocked(apiModule.createRequirement).mock.calls[0][2];
    expect(payload).not.toHaveProperty("change_reason");
    expect(payload).toEqual({ title: "New" });
  });

  it("submitForm surfaces field-level 400 errors and stays on the form", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockRejectedValue(
      new ReqogniLoomApiError(400, {
        error: { code: "VALIDATION_ERROR", message: "Validation failed", details: [{ field: "title", errors: ["Required."] }] },
      }, "Validation failed")
    );
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();

    await submitForm();

    expect(getState().view).toBe("form");
    expect(getState().form?.fieldErrors).toEqual({ title: ["Required."] });
    expect(getState().form?.submitting).toBe(false);
  });

  it("submitForm sets a generic submitError for non-validation failures", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockRejectedValue(new ReqogniLoomApiError(500, null, "Server error"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();

    await submitForm();

    expect(getState().form?.submitError).toBe("Server error");
    expect(getState().form?.fieldErrors).toEqual({});
  });

  it("submitForm handles validation errors with empty details array as submitError", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockRejectedValue(
      new ReqogniLoomApiError(400, {
        error: { code: "VALIDATION_ERROR", message: "change_reason required by workspace preset policy", details: [] },
      }, "change_reason required by workspace preset policy")
    );
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();

    await submitForm();

    expect(getState().form?.submitError).toBe("change_reason required by workspace preset policy");
    expect(getState().form?.fieldErrors).toEqual({});
    expect(getState().view).toBe("form");
  });
});

