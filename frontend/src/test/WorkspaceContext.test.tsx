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
import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { WorkspaceProvider, useWorkspace } from "../context/WorkspaceContext";
import type { Workspace } from "../types";

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
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  }, [preset, profile, setActiveWorkspace]);

  return <LabelDisplay />;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WorkspaceContext / Terminology Profile (REQ-L2-RF-008)", () => {
  it("SE-Modus: requirement label is 'Requirement'", () => {
    render(
      <WorkspaceProvider>
        <ControlledWorkspace preset="standard" profile="se_mode" />
      </WorkspaceProvider>
    );

    expect(screen.getByTestId("req-label").textContent).toBe("Requirement");
    expect(screen.getByTestId("reqs-label").textContent).toBe("Requirements");
  });

  it("Dev-Modus: requirement label is 'Story'", () => {
    render(
      <WorkspaceProvider>
        <ControlledWorkspace preset="standard" profile="dev_mode" />
      </WorkspaceProvider>
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
      created_at: "",
      updated_at: "",
    });
  }, [preset, setActiveWorkspace]);

  return <VisibilityDisplay feature={feature} />;
}

describe("WorkspaceContext / Preset visibility (REQ-L2-RF-007)", () => {
  it("Minimal preset: baselines are hidden", () => {
    render(
      <WorkspaceProvider>
        <ControlledPreset preset="minimal" feature="baselines" />
      </WorkspaceProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("hidden");
  });

  it("Extended preset: baselines are visible", () => {
    render(
      <WorkspaceProvider>
        <ControlledPreset preset="extended" feature="baselines" />
      </WorkspaceProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("visible");
  });

  it("Standard preset: requirements are visible", () => {
    render(
      <WorkspaceProvider>
        <ControlledPreset preset="standard" feature="requirements" />
      </WorkspaceProvider>
    );
    expect(screen.getByTestId("visible").textContent).toBe("visible");
  });
});
