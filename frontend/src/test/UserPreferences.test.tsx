/**
 * ARCH-L1-001 ReactFrontend — User-preference override tests (REQ-L1-027).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceContext)
 * req_id:  REQ-L1-027 (Per-user visibility overrides)
 *
 * Verifies that:
 *   - When no preference row exists (404) → preset defaults apply.
 *   - When a user override exists → it beats the preset for the same key.
 *   - setFeatureVisible persists the change via preferencesApi.update.
 *   - The master "hide all optional" toggle wins over per-feature overrides.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider, useWorkspace } from "../context/WorkspaceContext";
import type { Workspace } from "../types";

// ---------------------------------------------------------------------------
// Mock preferences API
// ---------------------------------------------------------------------------

type RawKey =
  | "adr" | "risk" | "issue" | "diagrams" | "icds" | "metrics"
  | "_hide_all_optional";

type Wrapped = {
  overrides: Partial<Record<"adr" | "risk" | "issue" | "diagrams" | "icds" | "metrics", boolean>>;
  hideAllOptional: boolean;
};

function wrapPref(
  raw: Partial<Record<RawKey, boolean>>
): Wrapped {
  const overrides: Wrapped["overrides"] = {};
  for (const f of ["adr", "risk", "issue", "diagrams", "icds", "metrics"] as const) {
    const val = raw[f];
    if (typeof val === "boolean") overrides[f] = val;
  }
  return { overrides, hideAllOptional: raw._hide_all_optional === true };
}

// Single-value mock: the test sets the "next return" before the test
// runs.  Every .get() call resolves to that same payload (the test does
// not distinguish between the DEFAULT_WORKSPACE fetch and the real
// workspace fetch — both should return the same preference).
let nextGetReturn: Wrapped | null = wrapPref({});
let nextUpdateReturn: Wrapped | null = null;

const mockGet = vi.fn(async () => nextGetReturn);
const mockUpdate = vi.fn(
  async (_ws: string, payload: Partial<Record<RawKey, boolean>>) => {
    if (nextUpdateReturn) return nextUpdateReturn;
    return wrapPref(payload);
  }
);

vi.mock("../api/preferences", () => ({
  preferencesApi: {
    get: (...args: unknown[]) => mockGet(...args),
    update: (...args: unknown[]) => mockUpdate(...args),
  },
  OPTIONAL_FEATURES: ["adr", "risk", "issue", "diagrams", "icds", "metrics"] as const,
}));

// workspacesApi.list is called by the WorkspaceContext bootstrap effect
// after auth.  Mock it so we don't hit the network, AND so it returns the
// same workspace the test's ControlledWorkspace would set — otherwise the
// bootstrap effect (which sets activeWorkspace from the API result) would
// overwrite the test's setActiveWorkspace call.
let nextListResult: unknown = { count: 0, next: null, previous: null, results: [] };
vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(async () => nextListResult),
    create: vi.fn(),
    update: vi.fn(),
    setPreset: vi.fn(),
    closeWorkspace: vi.fn(),
    reactivateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Test components
// ---------------------------------------------------------------------------

function VisibilityDisplay({ feature }: { feature: string }): JSX.Element {
  const { isFeatureVisible } = useWorkspace();
  return (
    <span data-testid={`visible-${feature}`}>
      {isFeatureVisible(feature) ? "visible" : "hidden"}
    </span>
  );
}

function AllOptionalDisplay(): JSX.Element {
  const { isFeatureVisible } = useWorkspace();
  return (
    <div>
      <span data-testid="visible-adr">{isFeatureVisible("adr") ? "visible" : "hidden"}</span>
      <span data-testid="visible-risk">{isFeatureVisible("risk") ? "visible" : "hidden"}</span>
      <span data-testid="visible-issue">{isFeatureVisible("issue") ? "visible" : "hidden"}</span>
      <span data-testid="visible-diagrams">{isFeatureVisible("diagrams") ? "visible" : "hidden"}</span>
      <span data-testid="visible-icds">{isFeatureVisible("icds") ? "visible" : "hidden"}</span>
      <span data-testid="visible-metrics">{isFeatureVisible("metrics") ? "visible" : "hidden"}</span>
    </div>
  );
}

function SetterButton({
  feature,
  value,
}: {
  feature: "adr" | "risk" | "issue" | "diagrams" | "icds" | "metrics";
  value: boolean;
}): JSX.Element {
  const { setFeatureVisible } = useWorkspace();
  return (
    <button
      data-testid={`set-${feature}-${String(value)}`}
      onClick={() => void setFeatureVisible(feature, value)}
    >
      set
    </button>
  );
}

function MasterToggle(): JSX.Element {
  const { hideAllOptional, setHideAllOptional } = useWorkspace();
  return (
    <div>
      <span data-testid="hide-all-state">{hideAllOptional ? "hidden" : "shown"}</span>
      <button
        data-testid="toggle-hide-all"
        onClick={() => void setHideAllOptional(!hideAllOptional)}
      >
        toggle
      </button>
    </div>
  );
}

function ControlledWorkspace({
  preset,
}: {
  preset: Workspace["preset"];
}): JSX.Element {
  // The active workspace is driven by the workspacesApi.list mock.
  // Tests set ``nextListResult`` before render to inject the desired
  // workspace (id="ws-test") with the target preset.
  return <AllOptionalDisplay />;
}

function setListWorkspace(preset: Workspace["preset"]): void {
  nextListResult = {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: "ws-test",
        name: "Test",
        preset,
        terminology_profile: "se_mode",
        language: "en",
        is_active: true,
        closed_at: null,
        closed_by: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WorkspaceContext / User-preference overrides (REQ-L1-027)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    nextGetReturn = wrapPref({}); // default: no overrides
    nextUpdateReturn = null;
    sessionStorage.clear();
    // AuthProvider reads the token from sessionStorage on mount; without
    // a token, isAuthenticated=false and the fetch effect never runs.
    sessionStorage.setItem("reqflow_token", "test-token");
    sessionStorage.setItem(
      "reqflow_user",
      JSON.stringify({ id: "u-1", username: "tester", email: "t@x", is_active: true, tenant_id: null, roles: [] })
    );
  });

  it("falls back to preset when no preference exists (404 → null)", async () => {
    nextGetReturn = null; // 404 → null
    setListWorkspace("standard");

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <ControlledWorkspace preset="standard" />
        </WorkspaceProvider>
      </AuthProvider>
    );

    // standard preset → all 6 visible
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });
    expect(screen.getByTestId("visible-adr").textContent).toBe("visible");
    expect(screen.getByTestId("visible-risk").textContent).toBe("visible");
    expect(screen.getByTestId("visible-issue").textContent).toBe("visible");
    expect(screen.getByTestId("visible-diagrams").textContent).toBe("visible");
    expect(screen.getByTestId("visible-icds").textContent).toBe("visible");
    expect(screen.getByTestId("visible-metrics").textContent).toBe("visible");
  });

  it("user override beats preset: standard preset + adr=false override → adr hidden", async () => {
    nextGetReturn = wrapPref({ adr: false });
    setListWorkspace("standard");

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <ControlledWorkspace preset="standard" />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("visible-adr").textContent).toBe("hidden");
    });
    // other features still come from preset (standard → visible)
    expect(screen.getByTestId("visible-risk").textContent).toBe("visible");
    expect(screen.getByTestId("visible-diagrams").textContent).toBe("visible");
  });

  it("user override beats preset: minimal preset + risk=true override → risk visible", async () => {
    nextGetReturn = wrapPref({ risk: true });
    setListWorkspace("minimal");

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <ControlledWorkspace preset="minimal" />
        </WorkspaceProvider>
      </AuthProvider>
    );

    // Wait for the minimal preset to take effect (adr must be hidden).
    await waitFor(() => {
      expect(screen.getByTestId("visible-adr").textContent).toBe("hidden");
    });
    // risk override beats the minimal preset default (risk=false).
    expect(screen.getByTestId("visible-risk").textContent).toBe("visible");
    // other features still follow the minimal preset (all false).
    expect(screen.getByTestId("visible-issue").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-diagrams").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-icds").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-metrics").textContent).toBe("hidden");
  });

  it("setFeatureVisible updates local state and calls preferencesApi.update", async () => {
    nextGetReturn = null;
    setListWorkspace("standard");

    function Harness(): JSX.Element {
      return (
        <>
          <VisibilityDisplay feature="adr" />
          <SetterButton feature="adr" value={false} />
        </>
      );
    }

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <Harness />
        </WorkspaceProvider>
      </AuthProvider>
    );

    // initial: standard preset → adr visible
    await waitFor(() => {
      expect(screen.getByTestId("visible-adr").textContent).toBe("visible");
    });

    // click → calls setFeatureVisible("adr", false)
    await act(async () => {
      screen.getByTestId("set-adr-false").click();
    });

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith("ws-test", {
        adr: false,
      });
    });
    // Optimistic local update
    expect(screen.getByTestId("visible-adr").textContent).toBe("hidden");
  });

  it("hideAllOptional master toggle hides all 6 optional features regardless of preset", async () => {
    nextGetReturn = wrapPref({ _hide_all_optional: true });
    setListWorkspace("standard");

    function Harness(): JSX.Element {
      return (
        <>
          <ControlledWorkspace preset="standard" />
          <MasterToggle />
        </>
      );
    }

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <Harness />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("hide-all-state").textContent).toBe("hidden");
    });
    // all 6 must be hidden even though standard preset says true
    expect(screen.getByTestId("visible-adr").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-risk").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-issue").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-diagrams").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-icds").textContent).toBe("hidden");
    expect(screen.getByTestId("visible-metrics").textContent).toBe("hidden");
  });

  it("setHideAllOptional persists via preferencesApi.update", async () => {
    nextGetReturn = null;
    setListWorkspace("standard");

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <MasterToggle />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });

    await act(async () => {
      screen.getByTestId("toggle-hide-all").click();
    });

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith("ws-test", {
        _hide_all_optional: true,
      });
    });
    expect(screen.getByTestId("hide-all-state").textContent).toBe("hidden");
  });
});
