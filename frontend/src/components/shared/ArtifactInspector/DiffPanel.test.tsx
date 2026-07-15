/**
 * Tests for DiffPanel — diagram/glossary real endpoint wiring (REQ-142).
 *
 * req_id: REQ-142 (versions/diff endpoints for Diagram and GlossaryTerm),
 *         REQ-L2-RF-036 (DiffPanel)
 *
 * Prior to REQ-142 the `diagram` and `glossary` kinds always rendered the
 * "Diff is not yet available" empty state because they were absent from
 * DIFF_SUPPORTED_KINDS. These tests verify the panel now renders a real
 * field-level diff for both kinds, and that fetch errors surface via the
 * ArtifactDiff error element.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DiffPanel } from "./DiffPanel";
import * as diagramsModule from "../../../api/diagrams";
import * as glossaryModule from "../../../api/glossary";
import type { ArtifactDiffResult, ArtifactVersion } from "../../../types";

vi.mock("../../../api/diagrams");
vi.mock("../../../api/glossary");
vi.mock("../../../api/requirements");
vi.mock("../../../api/architecture");
vi.mock("../../../api/stakeholder-need");
vi.mock("../../../api/adrs");
vi.mock("../../../api/risks");
vi.mock("../../../api/issues");
vi.mock("../../../api/testcases");
vi.mock("../../../api/icds");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string | Record<string, unknown>): string =>
    typeof fallback === "string" ? fallback : _key;
  return { useTranslation: () => ({ t }) };
});

const ARTIFACT_ID = "44444444-4444-4444-4444-444444444444";

const MOCK_VERSIONS: ArtifactVersion[] = [
  { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  { version: 2, label: "v2", modified_at: "2026-01-02T00:00:00Z" },
];

const MOCK_DIAGRAM_DIFF: ArtifactDiffResult = {
  from_version: 1,
  to_version: 2,
  entity_type: "Diagram",
  fields: [
    {
      name: "payload",
      status: "modified",
      from: "graph TD;\nA-->B",
      to: "graph TD;\nA-->C",
      lines: ["-graph TD;", "-A-->B", "+A-->C"],
    },
  ],
};

const MOCK_GLOSSARY_DIFF: ArtifactDiffResult = {
  from_version: 1,
  to_version: 2,
  entity_type: "GlossaryTerm",
  fields: [
    { name: "definition", status: "modified", from: "Old def", to: "New def" },
  ],
};

describe("DiffPanel — diagram/glossary (REQ-142)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("[REQ-142] renders a field-level diagram diff instead of the unsupported empty state", async () => {
    vi.mocked(diagramsModule.diagramsApi.versions).mockResolvedValue(MOCK_VERSIONS);
    vi.mocked(diagramsModule.diagramsApi.diff).mockResolvedValue(MOCK_DIAGRAM_DIFF);

    render(
      <DiffPanel kind="diagram" artifactId={ARTIFACT_ID} leftVersion={1} rightVersion={2} />
    );

    // No longer the unsupported empty state.
    expect(screen.queryByTestId("diff-unsupported")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("diff-field-payload")).toBeInTheDocument();
    });
    expect(diagramsModule.diagramsApi.diff).toHaveBeenCalledWith(ARTIFACT_ID, 1, 2);
  });

  it("[REQ-142] renders a field-level glossary diff instead of the unsupported empty state", async () => {
    vi.mocked(glossaryModule.glossaryApi.versions).mockResolvedValue(MOCK_VERSIONS);
    vi.mocked(glossaryModule.glossaryApi.diff).mockResolvedValue(MOCK_GLOSSARY_DIFF);

    render(
      <DiffPanel kind="glossary" artifactId={ARTIFACT_ID} leftVersion={1} rightVersion={2} />
    );

    expect(screen.queryByTestId("diff-unsupported")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("diff-field-definition")).toBeInTheDocument();
    });
    expect(glossaryModule.glossaryApi.diff).toHaveBeenCalledWith(ARTIFACT_ID, 1, 2);
  });

  it("[REQ-142] surfaces an error when the diagram versions fetch rejects", async () => {
    vi.mocked(diagramsModule.diagramsApi.versions).mockRejectedValue(
      new Error("Diagram not found")
    );

    render(
      <DiffPanel kind="diagram" artifactId={ARTIFACT_ID} leftVersion={1} rightVersion={2} />
    );

    await waitFor(() => {
      expect(screen.getByTestId("diff-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-error")).toHaveTextContent("Diagram not found");
  });

  it("[REQ-142] surfaces an error when the glossary diff fetch rejects", async () => {
    vi.mocked(glossaryModule.glossaryApi.versions).mockResolvedValue(MOCK_VERSIONS);
    vi.mocked(glossaryModule.glossaryApi.diff).mockRejectedValue(
      new Error("GlossaryTerm not found")
    );

    render(
      <DiffPanel kind="glossary" artifactId={ARTIFACT_ID} leftVersion={1} rightVersion={2} />
    );

    await waitFor(() => {
      expect(screen.getByTestId("diff-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-error")).toHaveTextContent("GlossaryTerm not found");
  });
});
