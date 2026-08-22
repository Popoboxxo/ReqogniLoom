/**
 * ARCH-L1-001 ReactFrontend — WorkspaceContext / Terminology Profile test.
 *
 * leaf_id: COMP-RF-001..004 (shared context)
 * req_id:  REQ-L2-RF-008 (Terminologie-Profil-Rendering),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering)
 *
 * Acceptance criterion (REQ-L2-RF-008 AC):
 *   Unit-Test: Setze Profil auf SE-Modus → alle Labels entsprechen SE-Terminologie
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider, useWorkspace } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import type { Workspace } from "../types";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider (now
// a WorkspaceProvider dependency, #568 phase 1) reads synchronously on mount.
// Polyfill a minimal in-memory implementation so ThemeProvider does not throw.
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

// ---------------------------------------------------------------------------
// Test component that reads terminology labels
// ---------------------------------------------------------------------------

function LabelDisplay(): JSX.Element {
  const { terminologyLabel } = useWorkspace();
  return (
    <div>
      <span data-testid="req-label">{terminologyLabel("requirement")}</span>
      <span data-testid="reqs-label">{terminologyLabel("requirements")}</span>
    </div>
  );
}

function ControlledWorkspace({
  preset,
  profile,
}: {
  preset: Workspace["preset"];
  profile: Workspace["terminology_profile"];
}): JSX.Element {
  const { setActiveWorkspace } = useWorkspace();

  React.useEffect(() => {
    setActiveWorkspace({
      id: "ws-test",
      name: "Test Workspace",
      preset,
      terminology_profile: profile,
      language: "en",
      theme: "dark",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  }, [preset, profile, setActiveWorkspace]);

  return <LabelDisplay />;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  installLocalStorageStub();
  // Auth is restored via GET /auth/me/ (httpOnly cookie, REQ-052). These tests
  // drive the workspace directly via setActiveWorkspace, so a 401 (anonymous)
  // is sufficient and keeps the bootstrap effect from hitting the network.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) }) as unknown as Response)
  );
});

describe("WorkspaceContext / Terminology Profile (REQ-L2-RF-008)", () => {
  it("SE-Modus: requirement label is 'Requirement'", () => {
    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <ControlledWorkspace preset="standard" profile="se_mode" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    expect(screen.getByTestId("req-label").textContent).toBe("Requirement");
    expect(screen.getByTestId("reqs-label").textContent).toBe("Requirements");
  });

  it("Dev-Modus: requirement label is 'Story'", () => {
    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <ControlledWorkspace preset="standard" profile="dev_mode" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    expect(screen.getByTestId("req-label").textContent).toBe("Story");
    expect(screen.getByTestId("reqs-label").textContent).toBe("Stories");
  });
});

// ---------------------------------------------------------------------------
// Preset visibility tests (REQ-L2-RF-007)
// ---------------------------------------------------------------------------

function VisibilityDisplay({ feature }: { feature: string }): JSX.Element {
  const { isFeatureVisible } = useWorkspace();
  return (
    <span data-testid="visible">
      {isFeatureVisible(feature) ? "visible" : "hidden"}
    </span>
  );
}

function ControlledPreset({
  preset,
  feature,
}: {
  preset: Workspace["preset"];
  feature: string;
}): JSX.Element {
  const { setActiveWorkspace } = useWorkspace();

  React.useEffect(() => {
    setActiveWorkspace({
      id: "ws-test",
      name: "Test",
      preset,
      terminology_profile: "se_mode",
      language: "en",
      theme: "dark",
      created_at: "",
      updated_at: "",
    });
  }, [preset, setActiveWorkspace]);

  return <VisibilityDisplay feature={feature} />;
}

describe("WorkspaceContext / Preset visibility (REQ-L2-RF-007)", () => {
  it("Minimal preset: baselines are hidden", () => {
    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <ControlledPreset preset="minimal" feature="baselines" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("hidden");
  });

  it("Extended preset: baselines are visible", () => {
    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <ControlledPreset preset="extended" feature="baselines" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("visible");
  });

  it("Standard preset: requirements are visible", () => {
    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <ControlledPreset preset="standard" feature="requirements" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("visible");
  });
});

// ---------------------------------------------------------------------------
// Task 1 regression: workspace-switcher pagination
// (GESAMTTEST_BERICHT_2026-08-21.md §10.2, Critical)
//
// `reloadWorkspaces` used to call `workspacesApi.list()`, which only fetches
// page 1 of the paginated `/api/v1/workspaces/` response — a tenant with
// more than one page of workspaces could never reach entries beyond the
// first page through the UI switcher. The fix wires `reloadWorkspaces` to
// `workspacesApi.listAll()`, which follows `next` via the shared
// `getAllPages` helper. This test exercises the real (unmocked)
// `workspacesApi`/`client` code paths against a stubbed `fetch` returning a
// genuinely 2-page paginated response, so it proves the real pagination
// logic — not just that `reloadWorkspaces` trusts whatever a mock hands it.
// ---------------------------------------------------------------------------

function WorkspaceCountDisplay(): JSX.Element {
  const { workspaces } = useWorkspace();
  return (
    <div data-testid="ws-count">{workspaces.length}</div>
  );
}

function makeWorkspace(id: string, name: string): Workspace {
  return {
    id,
    name,
    preset: "standard",
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

describe("WorkspaceContext / reloadWorkspaces pagination (Task 1, GESAMTTEST_BERICHT §10.2)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
    installLocalStorageStub();
  });

  it("fetches all pages of the workspace list, not just page 1", async () => {
    const page1 = [makeWorkspace("ws-1", "WS 1"), makeWorkspace("ws-2", "WS 2")];
    const page2 = [makeWorkspace("ws-3", "WS 3")];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/me/")) {
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
        if (url.includes("/workspaces/") && url.includes("page=2")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              count: 3,
              next: null,
              previous: "/api/v1/workspaces/?page_size=100",
              results: page2,
            }),
          } as unknown as Response;
        }
        if (url.includes("/workspaces/")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              count: 3,
              next: "/api/v1/workspaces/?page_size=100&page=2",
              previous: null,
              results: page1,
            }),
          } as unknown as Response;
        }
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      })
    );

    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <WorkspaceCountDisplay />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    // Regression: with the pre-fix `workspacesApi.list()` call, this would
    // stop at 2 (page 1 only). The fix must surface all 3 across both pages.
    await waitFor(() => {
      expect(screen.getByTestId("ws-count").textContent).toBe("3");
    });
  });
});
