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
import { ThemeProvider } from "../context/ThemeContext";
import type { Workspace } from "../types";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
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

function OverrideHarness({
  feature,
}: {
  feature: "adr" | "risk" | "issue" | "diagrams" | "icds" | "metrics";
}): JSX.Element {
  const { setFeatureVisible, resetFeatureOverride, isFeatureOverridden } =
    useWorkspace();
  return (
    <div>
      <span data-testid={`overridden-${feature}`}>
        {isFeatureOverridden(feature) ? "overridden" : "from-preset"}
      </span>
      <button
        data-testid={`toggle-${feature}`}
        onClick={() => void setFeatureVisible(feature, false)}
      >
        toggle
      </button>
      <button
        data-testid={`reset-${feature}`}
        onClick={() => void resetFeatureOverride(feature)}
      >
        reset
      </button>
    </div>
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
  preset: _preset,
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
    installLocalStorageStub();
    // AuthProvider restores the session via GET /auth/me/ (httpOnly cookie,
    // REQ-052). Return a user so isAuthenticated becomes true and the
    // WorkspaceContext bootstrap/preference effects run. Non-auth API calls in
    // these tests go through mocked api modules, not fetch.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u-1", username: "tester", email: "t@x", first_name: "", last_name: "", is_active: true, tenant_id: null, roles: ["admin"] },
          tenant_id: null,
          roles: ["admin"],
        }),
      }) as unknown as Response)
    );
  });

  it("falls back to preset when no preference exists (404 → null)", async () => {
    nextGetReturn = null; // 404 → null
    setListWorkspace("standard");

    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
          <ControlledWorkspace preset="standard" />
          </WorkspaceProvider>
        </ThemeProvider>
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
        <ThemeProvider>
          <WorkspaceProvider>
          <ControlledWorkspace preset="standard" />
          </WorkspaceProvider>
        </ThemeProvider>
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
        <ThemeProvider>
          <WorkspaceProvider>
          <ControlledWorkspace preset="minimal" />
          </WorkspaceProvider>
        </ThemeProvider>
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
        <ThemeProvider>
          <WorkspaceProvider>
          <Harness />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    // initial: standard preset → adr visible
    await waitFor(() => {
      expect(screen.getByTestId("visible-adr").textContent).toBe("visible");
    });
    // Wait until the real workspace (ws-test) is active — the preference effect
    // only queries once the workspace list has loaded post-auth. Otherwise the
    // click would run against the DEFAULT_WORKSPACE placeholder.
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("ws-test");
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
        <ThemeProvider>
          <WorkspaceProvider>
          <Harness />
          </WorkspaceProvider>
        </ThemeProvider>
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
        <ThemeProvider>
          <WorkspaceProvider>
          <MasterToggle />
          </WorkspaceProvider>
        </ThemeProvider>
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

  // BUG-16 regression (docs/SYSTEMAUDIT_2026-08-18.md §4): resetFeatureOverride
  // used to call setFeatureVisible(feature, presetValue), which unconditionally
  // re-marked the feature as overridden — so isFeatureOverridden() stayed
  // true forever and the "reset" UI control could never become inactive
  // again. Verifies the override flag is actually cleared once the
  // effective value matches the preset again.
  it("resetFeatureOverride clears isFeatureOverridden (BUG-16)", async () => {
    nextGetReturn = null; // no pre-existing overrides
    setListWorkspace("standard"); // adr defaults to true under "standard"

    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
          <OverrideHarness feature="adr" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("ws-test");
    });
    expect(screen.getByTestId("overridden-adr").textContent).toBe(
      "from-preset"
    );

    // Toggle away from the preset default → must become overridden.
    await act(async () => {
      screen.getByTestId("toggle-adr").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("overridden-adr").textContent).toBe(
        "overridden"
      );
    });

    // Reset back to the preset default → override flag must clear, not
    // just re-persist the same value while staying "overridden".
    await act(async () => {
      screen.getByTestId("reset-adr").click();
    });
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenLastCalledWith("ws-test", { adr: true });
    });
    await waitFor(() => {
      expect(screen.getByTestId("overridden-adr").textContent).toBe(
        "from-preset"
      );
    });
  });

  // BUG-16 review finding F-01: the initial-load computation compared the
  // preset default against ``pref.overrides[f]`` without checking whether
  // the key was actually present. ``pref.overrides`` is sparse (only
  // explicitly-set keys), so an untouched feature is ``undefined`` — and
  // e.g. ``true !== undefined`` is true, wrongly marking every untouched
  // feature as "overridden" on every page load/reload. Verifies that only
  // the feature actually present in the stored overrides is marked
  // overridden; a sibling feature absent from the stored row must read as
  // "from-preset" even though its preset value is also `true`.
  it("only marks features present in the stored overrides row as overridden on load (F-01)", async () => {
    // adr is explicitly stored as false (standard preset default: true) →
    // overridden. risk is NOT present in the stored row at all, even
    // though the standard preset default for risk is also `true` — it
    // must NOT be marked overridden merely because it differs from
    // `undefined`.
    nextGetReturn = wrapPref({ adr: false });
    setListWorkspace("standard");

    render(
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
          <OverrideHarness feature="adr" />
          <OverrideHarness feature="risk" />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("overridden-adr").textContent).toBe(
        "overridden"
      );
    });
    // The bug: this used to also read "overridden" for every untouched
    // feature after a (re)load.
    expect(screen.getByTestId("overridden-risk").textContent).toBe(
      "from-preset"
    );
  });
});
