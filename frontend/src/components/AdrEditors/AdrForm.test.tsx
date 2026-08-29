import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Regression coverage for systemaudit 2026-08-29 Bug 4 — the "Supersede
 * durch..." button was only gated on `candidateSuccessors.length === 0`, not
 * on the ADR's own workflow status. The only defined transition into
 * 'Superseded' is 'Approved' -> 'Superseded' (backend/workflow/
 * definition_store.py::_adr_transitions), so a Draft/In-Review ADR let the
 * user fill in the whole supersede form only to hit a generic
 * "Transition not allowed" error from the backend at submit time.
 */

vi.mock("../../api/adrs", () => ({
  adrsApi: {
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
    supersede: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

vi.mock("../WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor-stub" />,
}));

vi.mock("../RequirementEditors/MarkdownPreview", () => ({
  MarkdownPreview: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <textarea
      data-testid="adr-description-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

vi.mock("../shared/ArtifactCustomFields", () => ({
  ArtifactCustomFields: () => <div data-testid="artifact-custom-fields" />,
}));
vi.mock("../shared/VersionBadge", () => ({
  VersionBadge: () => <span data-testid="version-badge" />,
}));
vi.mock("../shared/StatusBadge", () => ({
  StatusBadge: () => <span data-testid="status-badge" />,
}));
vi.mock("../shared/ArtifactId", () => ({
  ArtifactId: () => <span data-testid="artifact-id" />,
}));

import { AdrForm } from "./AdrForm";
import type { Adr } from "../../types";

const baseAdr: Adr = {
  id: "adr-1",
  artifact_id: "art-adr-1",
  uid: "ADR-001",
  title: "Use PostgreSQL",
  description: "",
  context: "",
  consequences: "",
  status: "Approved",
  version: 1,
} as Adr;

const otherAdr: Adr = {
  ...baseAdr,
  id: "adr-2",
  uid: "ADR-002",
  title: "Use Redis",
};

describe("AdrForm — supersede button workflow-status gating (systemaudit Bug 4)", () => {
  it("enables the supersede button when the ADR is Approved and candidates exist", () => {
    render(
      <AdrForm
        adr={{ ...baseAdr, status: "Approved" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    expect(screen.getByTestId("adr-supersede-btn")).not.toBeDisabled();
  });

  it("disables the supersede button when the ADR is Draft, even with candidates", () => {
    render(
      <AdrForm
        adr={{ ...baseAdr, status: "Draft" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    const btn = screen.getByTestId("adr-supersede-btn");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute(
      "title",
      'Supersede ist nur für ADRs im Status "Approved" möglich.'
    );
  });

  it("disables the supersede button when the ADR is In Review", () => {
    render(
      <AdrForm
        adr={{ ...baseAdr, status: "In Review" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    expect(screen.getByTestId("adr-supersede-btn")).toBeDisabled();
  });
});
