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
import { render, screen } from "@testing-library/react";
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
