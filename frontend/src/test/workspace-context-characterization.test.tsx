/**
 * ARCH-L1-001 ReactFrontend — WorkspaceContext value characterization.
 *
 * plan Phase 5a (docs/plans/2026-10-15-frontend-audit-fixes.md, §5 bullet 5a;
 * FE-01/F-03 "God-Components", FE-02/F-05 "doppelter State"):
 *
 *   "Charakterisierungs-Test des Context-Values […] VOR dem Refactor
 *    (kein Unit-Test für den Context gefunden)."
 *
 * This file is that characterization test. It pins the OBSERVABLE shape and
 * semantics of the object returned by `useWorkspace()` against the current,
 * un-refactored implementation (main @ 6d87b172) so the decomposition into
 * `useWorkspaceLanguage` + `useWorkspacePreferences` (behind an unchanged
 * public Context API) cannot silently change behaviour.
 *
 * Honest divergence from the plan wording: the claim "kein Unit-Test für den
 * Context gefunden" is inaccurate — `WorkspaceContext.test.tsx` already covers
 * the terminology profile, preset visibility, reloadWorkspaces pagination and
 * malformed-preset normalization. What was genuinely missing is a
 * characterization of the Context *value shape* (key set / types) and of the
 * override-derivation semantics (BUG-16 / F-05), which is what this file adds.
 *
 * req_id: REQ-L1-027 (per-user visibility overrides), REQ-L2-RF-007 (preset
 *         visibility), REQ-L2-RF-008 (terminology profile)
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AuthProvider } from "../context/AuthContext";
import {
  WorkspaceProvider,
  useWorkspace,
} from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { preferencesApi } from "../api/preferences";
import { workspacesApi } from "../api/workspaces";
import type { Workspace } from "../types";

// ---------------------------------------------------------------------------
// Module mocks — a representative mocked auth + workspace + preferences fetch.
// Mirrors the mocking strategy already used by
// workspace-language-persistence.test.tsx; the real OPTIONAL_FEATURES constant
// is reproduced verbatim (WorkspaceContext reads it at runtime).
// ---------------------------------------------------------------------------

vi.mock("../api/preferences", () => ({
  preferencesApi: { get: vi.fn(), update: vi.fn() },
  OPTIONAL_FEATURES: [
    "adr",
    "risk",
    "issue",
    "diagrams",
    "icds",
    "metrics",
  ] as const,
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: { listAll: vi.fn() },
}));

// jsdom in this runtime does not provide window.localStorage; ThemeProvider
// reads it synchronously on mount (see WorkspaceContext.test.tsx for
// precedent).
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

/** Authenticated session (admin) via the httpOnly-cookie restore endpoint. */
function stubAuthFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({
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
        }) as unknown as Response
    )
  );
}

function makeWorkspace(preset: Workspace["preset"] = "minimal"): Workspace {
  return {
    id: "ws-1",
    name: "Main",
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

/**
 * Probe rendering every facet of the Context value the characterization
 * assertions need: the raw key set, per-feature override/visibility
 * resolution and the mutator-presence types. Readings are exposed through
 * `data-testid` spans so a `waitFor` can observe settled state.
 */
function Harness(): JSX.Element {
  const w = useWorkspace();
  const [error, setError] = React.useState("");
  return (
    <div>
      <span data-testid="keys">{Object.keys(w).sort().join(",")}</span>
      <span data-testid="active-id">{w.activeWorkspace?.id ?? ""}</span>
      <span data-testid="user-overrides">{JSON.stringify(w.userOverrides)}</span>
      <span data-testid="hide-all">{String(w.hideAllOptional)}</span>

      <span data-testid="overridden-adr">{String(w.isFeatureOverridden("adr"))}</span>
      <span data-testid="overridden-risk">{String(w.isFeatureOverridden("risk"))}</span>
      <span data-testid="overridden-issue">{String(w.isFeatureOverridden("issue"))}</span>

      <span data-testid="visible-adr">{String(w.isFeatureVisible("adr"))}</span>
      <span data-testid="visible-risk">{String(w.isFeatureVisible("risk"))}</span>
      <span data-testid="visible-reqs">{String(w.isFeatureVisible("requirements"))}</span>
      <span data-testid="visible-unknown">{String(w.isFeatureVisible("nope"))}</span>

      <span data-testid="fn-isFeatureVisible">{typeof w.isFeatureVisible}</span>
      <span data-testid="fn-setFeatureVisible">{typeof w.setFeatureVisible}</span>
      <span data-testid="fn-setHideAllOptional">{typeof w.setHideAllOptional}</span>
      <span data-testid="fn-resetFeatureOverride">{typeof w.resetFeatureOverride}</span>
      <span data-testid="fn-setActiveWorkspace">{typeof w.setActiveWorkspace}</span>
      <span data-testid="fn-reloadWorkspaces">{typeof w.reloadWorkspaces}</span>
      <span data-testid="fn-terminologyLabel">{typeof w.terminologyLabel}</span>
      <span data-testid="fn-markLanguageOverrideActive">
        {typeof w.markLanguageOverrideActive}
      </span>
      <span data-testid="fn-clearLanguageOverride">
        {typeof w.clearLanguageOverride}
      </span>

      <button
        data-testid="show-risk"
        onClick={() =>
          void w.setFeatureVisible("risk", true).catch(() => setError("risk-error"))
        }
      >
        show risk
      </button>
      <button
        data-testid="hide-all-optional"
        onClick={() => void w.setHideAllOptional(true)}
      >
        hide all optional
      </button>
      <button
        data-testid="mark-language-override"
        onClick={() => w.markLanguageOverrideActive()}
      >
        mark language override
      </button>
      <button
        data-testid="clear-language-override"
        onClick={() => w.clearLanguageOverride()}
      >
        clear language override
      </button>
      <span data-testid="error">{error}</span>
    </div>
  );
}

function renderHarness(): ReturnType<typeof render> {
  return render(
    <AuthProvider>
      <ThemeProvider>
        <WorkspaceProvider>
          <Harness />
        </WorkspaceProvider>
      </ThemeProvider>
    </AuthProvider>
  );
}

/** Render and wait until the real workspace + its preference row are loaded. */
async function renderLoaded(): Promise<void> {
  renderHarness();
  await waitFor(() => {
    expect(screen.getByTestId("active-id").textContent).toBe("ws-1");
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  installLocalStorageStub();
  stubAuthFetch();
  vi.mocked(workspacesApi.listAll).mockResolvedValue([makeWorkspace()]);
  vi.mocked(preferencesApi.get).mockResolvedValue({
    overrides: {},
    hideAllOptional: false,
  });
  vi.mocked(preferencesApi.update).mockResolvedValue({
    overrides: {},
    hideAllOptional: false,
  });
});

describe("WorkspaceContext value characterization (Phase 5a)", () => {
  it("exposes exactly the 15 documented WorkspaceState keys", async () => {
    await renderLoaded();

    const expected = [
      "activeWorkspace",
      "clearLanguageOverride",
      "hideAllOptional",
      "isFeatureOverridden",
      "isFeatureVisible",
      "isLoadingWorkspace",
      "markLanguageOverrideActive",
      "reloadWorkspaces",
      "resetFeatureOverride",
      "setActiveWorkspace",
      "setFeatureVisible",
      "setHideAllOptional",
      "terminologyLabel",
      "userOverrides",
      "workspaces",
    ].sort().join(",");

    expect(screen.getByTestId("keys").textContent).toBe(expected);
  });

  it("exposes the mutators as functions (types pinned 1:1)", async () => {
    await renderLoaded();

    for (const id of [
      "fn-isFeatureVisible",
      "fn-setFeatureVisible",
      "fn-setHideAllOptional",
      "fn-resetFeatureOverride",
      "fn-setActiveWorkspace",
      "fn-reloadWorkspaces",
      "fn-terminologyLabel",
      "fn-markLanguageOverrideActive",
      "fn-clearLanguageOverride",
    ]) {
      expect(screen.getByTestId(id).textContent).toBe("function");
    }
  });

  it("isFeatureOverridden marks ONLY overrides that differ from the preset (BUG-16 class)", async () => {
    // `minimal` preset: every optional artifact feature defaults to `false`.
    // A sparse override of `adr: false` equals the preset → NOT overridden;
    // `risk: true` differs → overridden; an absent key is never overridden.
    vi.mocked(preferencesApi.get).mockResolvedValue({
      overrides: { adr: false, risk: true },
      hideAllOptional: false,
    });

    await renderLoaded();

    await waitFor(() => {
      expect(screen.getByTestId("overridden-risk").textContent).toBe("true");
    });
    expect(screen.getByTestId("overridden-adr").textContent).toBe("false");
    expect(screen.getByTestId("overridden-issue").textContent).toBe("false");
  });

  it("isFeatureVisible resolves hideAllOptional → override → preset → default", async () => {
    vi.mocked(preferencesApi.get).mockResolvedValue({
      overrides: { risk: true },
      hideAllOptional: false,
    });

    await renderLoaded();
    await waitFor(() => {
      expect(screen.getByTestId("visible-risk").textContent).toBe("true");
    });

    // override (risk) > preset default (adr = false under `minimal`)
    expect(screen.getByTestId("visible-adr").textContent).toBe("false");
    // non-optional feature → preset map says visible
    expect(screen.getByTestId("visible-reqs").textContent).toBe("true");
    // unknown feature → final default is visible
    expect(screen.getByTestId("visible-unknown").textContent).toBe("true");

    // hideAllOptional is the strongest switch for the 6 optional features and
    // beats an explicit override, but does not touch non-optional ones.
    fireEvent.click(screen.getByTestId("hide-all-optional"));
    await waitFor(() => {
      expect(screen.getByTestId("hide-all").textContent).toBe("true");
    });
    expect(screen.getByTestId("visible-risk").textContent).toBe("false");
    expect(screen.getByTestId("visible-adr").textContent).toBe("false");
    expect(screen.getByTestId("visible-reqs").textContent).toBe("true");
  });

  it("setFeatureVisible applies an optimistic update and rolls back on API error", async () => {
    vi.mocked(preferencesApi.get).mockResolvedValue({
      overrides: { adr: false },
      hideAllOptional: false,
    });
    // Keep the PATCH pending so the optimistic state is observable before the
    // rollback runs.
    let rejectUpdate: ((reason?: unknown) => void) | null = null;
    vi.mocked(preferencesApi.update).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectUpdate = reject;
        })
    );

    await renderLoaded();

    fireEvent.click(screen.getByTestId("show-risk"));

    // Optimistic: the ending is visible and marked overridden immediately.
    await waitFor(() => {
      expect(screen.getByTestId("visible-risk").textContent).toBe("true");
    });
    expect(screen.getByTestId("overridden-risk").textContent).toBe("true");

    // Failure → exact rollback to the previous override state.
    rejectUpdate!(new Error("boom"));
    await waitFor(() => {
      expect(screen.getByTestId("error").textContent).toBe("risk-error");
    });
    expect(screen.getByTestId("visible-risk").textContent).toBe("false");
    expect(screen.getByTestId("overridden-risk").textContent).toBe("false");
    expect(screen.getByTestId("user-overrides").textContent).toBe(
      JSON.stringify({ adr: false })
    );
  });

  it("exposes markLanguageOverrideActive / clearLanguageOverride as callable no-ops on the value", async () => {
    await renderLoaded();

    expect(screen.getByTestId("fn-markLanguageOverrideActive").textContent).toBe(
      "function"
    );
    expect(screen.getByTestId("fn-clearLanguageOverride").textContent).toBe(
      "function"
    );

    // Calling them must not throw and must not disturb the visible value.
    fireEvent.click(screen.getByTestId("mark-language-override"));
    fireEvent.click(screen.getByTestId("clear-language-override"));
    expect(screen.getByTestId("active-id").textContent).toBe("ws-1");
  });
});
