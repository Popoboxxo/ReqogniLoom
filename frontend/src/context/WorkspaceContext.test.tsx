/**
 * WorkspaceContext regressions — FE-002 (logout race) and R2F-005
 * (unknown backend preset).
 *
 * FE-002: the bootstrap effect used a `cancelled` flag but the dead-code
 * `if (cancelled) return` sat *after* `await reloadWorkspaces()` — by then
 * `reloadWorkspaces` had already written `workspaces`/`activeWorkspace`.
 * Logging out while the `/workspaces/` request was in flight let the late
 * response repopulate a logged-out provider. The fix applies state only
 * while the effect is live.
 *
 * R2F-005: `normalizePreset` used to cast arbitrary backend strings to
 * `WorkspacePreset`; an unknown value such as `"ultra"` then made
 * `PRESET_VISIBILITY[preset][feature]` throw. The fix adds a real guard and
 * falls back to `"standard"`.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import {
  DEFAULT_WORKSPACE,
  WorkspaceProvider,
  useWorkspace,
} from "./WorkspaceContext";
import { workspacesApi } from "../api/workspaces";
import type { Workspace } from "../types";

function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}

function makeWorkspace(id: string, preset: Workspace["preset"] = "standard"): Workspace {
  return {
    id,
    name: `WS ${id}`,
    preset,
    terminology_profile: "se_mode",
    language: "en",
    theme: "dark",
    is_active: true,
    closed_at: null,
    closed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function authenticatedFetch(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      user: {
        id: "u-1",
        username: "tester",
        email: "t@x",
        first_name: "",
        last_name: "",
        is_active: true,
        tenant_id: null,
        roles: ["admin"],
      },
      tenant_id: null,
      roles: ["admin"],
    }),
  } as unknown as Response;
}

function StateHarness(): JSX.Element {
  const { logout } = useAuth();
  const { workspaces, activeWorkspace, isFeatureVisible } = useWorkspace();
  return (
    <div>
      <button type="button" data-testid="logout" onClick={logout}>
        logout
      </button>
      <div data-testid="count">{workspaces.length}</div>
      <div data-testid="active-id">{activeWorkspace?.id ?? "none"}</div>
      <div data-testid="visible">{isFeatureVisible("baselines") ? "visible" : "hidden"}</div>
    </div>
  );
}

function renderProvider(): void {
  render(
    <AuthProvider>
      <WorkspaceProvider>
        <StateHarness />
      </WorkspaceProvider>
    </AuthProvider>
  );
}

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  installLocalStorageStub();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("WorkspaceContext / FE-002 logout race", () => {
  it("does not repopulate state when the workspace request resolves after logout", async () => {
    let resolveList!: (value: Workspace[]) => void;
    const deferred = new Promise<Workspace[]>((resolve) => {
      resolveList = resolve;
    });
    const listAllSpy = vi.spyOn(workspacesApi, "listAll").mockReturnValue(deferred);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/auth/me/")) return authenticatedFetch();
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      })
    );

    renderProvider();

    // Wait until the bootstrap effect actually issued the (still pending)
    // /workspaces/ request — this is the window the bug raced against.
    await waitFor(() => expect(listAllSpy).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("count").textContent).toBe("0");

    // Log out while the request is in flight.
    fireEvent.click(screen.getByTestId("logout"));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("0"));

    // Now let the stale response land. It must NOT repopulate the provider.
    await act(async () => {
      resolveList([makeWorkspace("ws-1")]);
      await deferred;
    });

    expect(screen.getByTestId("count").textContent).toBe("0");
    expect(screen.getByTestId("active-id").textContent).toBe(DEFAULT_WORKSPACE.id);
  });
});

describe("WorkspaceContext / R2F-005 unknown preset", () => {
  it("normalizes an unknown backend preset to 'standard' without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/me/")) return authenticatedFetch();
        if (url.includes("/workspaces/")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              count: 1,
              next: null,
              previous: null,
              results: [{ ...makeWorkspace("ws-ultra"), preset: "ultra" }],
            }),
          } as unknown as Response;
        }
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      })
    );

    renderProvider();

    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
    // "standard" hides global_baselines but shows baselines; an unknown
    // preset used to make PRESET_VISIBILITY[preset][feature] throw.
    expect(screen.getByTestId("visible").textContent).toBe("visible");
  });
});
