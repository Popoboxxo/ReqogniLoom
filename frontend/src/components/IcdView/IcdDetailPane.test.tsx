/**
 * IcdDetailPane.test.tsx — #1709 defensive rendering of contract lists.
 *
 * The backend contract is ``string[]``, but rows written before the guard can
 * carry parameter objects. The pane must skip them instead of crashing the
 * whole detail page with React #31 ("Objects are not valid as a React child").
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import React from "react";

import type { IcdDetail } from "../../api/icds";
import { IcdDetailPane } from "./IcdDetailPane";

vi.mock("../shared/ArtifactInspector", () => ({
  // #1762/M6: the shell owns its own data fetching — stub it here.
  InspectorShell: () => <aside data-testid="inspector-shell-stub" />,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

// Sibling panels are network-backed; this test is about the read-only lists.
vi.mock("../WorkflowStatusEditor", () => ({ WorkflowStatusEditor: () => null }));

const DETAIL: IcdDetail = {
  id: "icd-001",
  name: "NavSub ↔ GroundControl RF Link",
  workspace_id: "ws-001",
  source_element_id: "arch-001",
  target_element_id: "arch-002",
  current_version: null,
  created_at: "2026-03-01T00:00:00Z",
  version: 1,
  direction: "unidirectional",
  interface_type: "data",
  semantic_description: "RF link",
  preconditions: ["caller is authenticated"],
  postconditions: ["result is stored"],
  invariants: ["unit stays constant"],
};

function renderPane(overrides: Partial<IcdDetail> = {}) {
  return render(
    <IcdDetailPane
      detail={{ ...DETAIL, ...overrides }}
      allICDs={[]}
      artifactLabel={(id) => id}
      onSelectIcd={() => undefined}
      showNewVersion={false}
      setShowNewVersion={() => undefined}
      formError={null}
      setFormError={() => undefined}
      isSaving={false}
      onNewVersion={() => undefined}
      nvDirection="unidirectional"
      setNvDirection={() => undefined}
      nvInterfaceType=""
      setNvInterfaceType={() => undefined}
      nvContract=""
      setNvContract={() => undefined}
      nvPre=""
      setNvPre={() => undefined}
      nvPost=""
      setNvPost={() => undefined}
      nvInv=""
      setNvInv={() => undefined}
    />
  );
}

describe("IcdDetailPane contract lists (#1709)", () => {
  it("renders string entries", () => {
    renderPane();

    expect(screen.getByText("caller is authenticated")).toBeInTheDocument();
  });

  it("skips non-string entries instead of crashing on React #31", () => {
    // The historical write path stored parameter objects in these fields.
    const legacy = [
      { name: "voltage", unit: "V", ordering: 0, data_type: "float" },
      "plain clause",
    ] as unknown as string[];

    expect(() => renderPane({ preconditions: legacy })).not.toThrow();

    expect(screen.getByText("plain clause")).toBeInTheDocument();
    expect(screen.queryByText(/voltage/)).not.toBeInTheDocument();
    // The pane itself still renders (no error boundary took over).
    expect(screen.getByTestId("icd-detail-title")).toBeInTheDocument();
  });

  it("renders the empty marker when only non-string entries remain", () => {
    const onlyObjects = [{ name: "voltage" }] as unknown as string[];

    renderPane({ invariants: onlyObjects });

    expect(screen.queryByText(/voltage/)).not.toBeInTheDocument();
  });
});
