import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { WorkflowGraph } from "../../api/workflows";
import { workflowsApi } from "../../api/workflows";
import { workflowDefaultsApi } from "../../api/workflow-defaults";
import type { WorkflowScope } from "./constants";
import { useWorkflowMutations } from "./useWorkflowMutations";
import { workflowKeys } from "./useWorkflowData";

// The real `extractWorkflowError` stays in place: only the endpoint families
// are doubled, so the hook's error path is exercised unchanged.
vi.mock("../../api/workflows", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/workflows")>();
  return {
    ...actual,
    workflowsApi: {
      createState: vi.fn(),
      updateState: vi.fn(),
      deleteState: vi.fn(),
      createTransition: vi.fn(),
      updateTransition: vi.fn(),
      deleteTransition: vi.fn(),
      initializeWorkflow: vi.fn(),
    },
  };
});

vi.mock("../../api/workflow-defaults", () => ({
  workflowDefaultsApi: {
    createState: vi.fn(),
    updateState: vi.fn(),
    deleteState: vi.fn(),
    setStateFreeze: vi.fn(),
    createTransition: vi.fn(),
    updateTransition: vi.fn(),
    deleteTransition: vi.fn(),
    initialize: vi.fn(),
  },
}));

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

const workspaceScope: WorkflowScope = {
  kind: "workspace",
  workspaceId: WORKSPACE_ID,
  preset: "standard",
};
const globalScope: WorkflowScope = { kind: "global", preset: "standard" };

function graph(preset: string): WorkflowGraph {
  return {
    entityType: "Requirement",
    preset,
    isCustom: false,
    initialized: true,
    states: [],
    transitions: [],
  };
}

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

/**
 * A promise plus its settle handles: lets a test observe the hook while an
 * operation is genuinely in flight instead of only before/after it resolves.
 */
function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function renderMutations(
  scope: WorkflowScope,
  onPropagated?: (count: number) => void
) {
  const client = createClient();
  const view = renderHook(
    () => useWorkflowMutations("Requirement", scope, onPropagated),
    { wrapper: createWrapper(client) }
  );
  return { ...view, client };
}

describe("useWorkflowMutations — scope dispatch (P2.5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("dispatches state creation to the workspace endpoints in workspace scope", async () => {
    const created = graph("standard");
    vi.mocked(workflowsApi.createState).mockResolvedValue(created);
    const { result, client } = renderMutations(workspaceScope);

    let ok = false;
    await act(async () => {
      ok = await result.current.addState("Review");
    });

    expect(ok).toBe(true);
    expect(workflowsApi.createState).toHaveBeenCalledWith(
      "Requirement",
      WORKSPACE_ID,
      "Review"
    );
    expect(workflowDefaultsApi.createState).not.toHaveBeenCalled();
    expect(
      client.getQueryData(workflowKeys.graph(workspaceScope, "Requirement"))
    ).toEqual(created);
  });

  it("dispatches state creation to the global endpoints in global scope", async () => {
    const created = graph("standard");
    vi.mocked(workflowDefaultsApi.createState).mockResolvedValue({
      graph: created,
      propagatedWorkspaceCount: 2,
    });
    const onPropagated = vi.fn();
    const { result, client } = renderMutations(globalScope, onPropagated);

    let ok = false;
    await act(async () => {
      ok = await result.current.addState("Review");
    });

    expect(ok).toBe(true);
    expect(workflowDefaultsApi.createState).toHaveBeenCalledWith(
      "Requirement",
      "standard",
      "Review"
    );
    expect(workflowsApi.createState).not.toHaveBeenCalled();
    expect(onPropagated).toHaveBeenCalledWith(2);
    expect(
      client.getQueryData(workflowKeys.graph(globalScope, "Requirement"))
    ).toEqual(created);
  });

  it("keeps every other method on the same dispatch", async () => {
    vi.mocked(workflowsApi.deleteTransition).mockResolvedValue(graph("standard"));
    const { result } = renderMutations(workspaceScope);

    await act(async () => {
      await result.current.deleteTransition("Draft", "Review");
    });

    expect(workflowsApi.deleteTransition).toHaveBeenCalledWith(
      "Requirement",
      WORKSPACE_ID,
      "Draft",
      "Review"
    );
    expect(workflowDefaultsApi.deleteTransition).not.toHaveBeenCalled();
  });
});

describe("useWorkflowMutations — setStateFreeze capability (P2.6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not expose setStateFreeze in workspace scope", () => {
    const { result } = renderMutations(workspaceScope);

    expect("setStateFreeze" in result.current).toBe(false);
    expect(result.current.setStateFreeze).toBeUndefined();
  });

  it("exposes setStateFreeze in global scope and dispatches it to the global API", async () => {
    const patched = graph("standard");
    vi.mocked(workflowDefaultsApi.setStateFreeze).mockResolvedValue({
      graph: patched,
    });
    const { result } = renderMutations(globalScope);

    const setStateFreeze = result.current.setStateFreeze;
    if (!setStateFreeze) throw new Error("setStateFreeze is missing in global scope");

    let ok = false;
    await act(async () => {
      ok = await setStateFreeze("Draft", true);
    });

    expect(ok).toBe(true);
    expect(workflowDefaultsApi.setStateFreeze).toHaveBeenCalledWith(
      "Requirement",
      "standard",
      "Draft",
      true
    );
  });
});

describe("useWorkflowMutations — busy and error contract (REQ-177)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("holds busy while an operation is in flight and releases it afterwards", async () => {
    const pending = deferred<WorkflowGraph>();
    vi.mocked(workflowsApi.createState).mockReturnValue(pending.promise);
    const { result } = renderMutations(workspaceScope);

    expect(result.current.busy).toBe(false);

    let inFlight: Promise<boolean> | undefined;
    act(() => {
      inFlight = result.current.addState("Review");
    });
    // The flag follows the dispatch, not the response.
    expect(result.current.busy).toBe(true);

    await act(async () => {
      pending.resolve(graph("standard"));
      await inFlight;
    });

    expect(result.current.busy).toBe(false);
  });

  it("surfaces a rejected operation as an error message and returns false", async () => {
    vi.mocked(workflowsApi.createState).mockRejectedValue({
      error: {
        code: "conflict",
        message: "A state with that name already exists.",
        details: [],
      },
    });
    const { result } = renderMutations(workspaceScope);

    let ok = true;
    await act(async () => {
      ok = await result.current.addState("Review");
    });

    expect(ok).toBe(false);
    expect(result.current.error).toBe("A state with that name already exists.");
    expect(result.current.busy).toBe(false);

    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toBeNull();
  });
});
