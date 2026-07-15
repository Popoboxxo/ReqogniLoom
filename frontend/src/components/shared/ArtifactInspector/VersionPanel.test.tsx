/**
 * Tests for VersionPanel — diagram/glossary real endpoint wiring (REQ-142).
 *
 * req_id: REQ-142 (versions/diff endpoints for Diagram and GlossaryTerm),
 *         REQ-L2-RF-035 (VersionPanel)
 *
 * Prior to REQ-142 the `diagram` and `glossary` kinds always rendered the
 * empty state because the backend had no `/versions/` endpoint for them.
 * These tests verify the panel now loads and renders real version lists
 * for both kinds via `diagramsApi.versions` / `glossaryApi.versions`, and
 * that the error path (rejected fetch) still surfaces the error banner.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { VersionPanel } from "./VersionPanel";
import * as diagramsModule from "../../../api/diagrams";
import * as glossaryModule from "../../../api/glossary";
import type { ArtifactVersion } from "../../../types";

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

const ARTIFACT_ID = "33333333-3333-3333-3333-333333333333";

const MOCK_VERSIONS: ArtifactVersion[] = [
  { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  { version: 2, label: "v2", modified_at: "2026-01-02T00:00:00Z" },
];

describe("VersionPanel — diagram/glossary (REQ-142)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("[REQ-142] loads real diagram versions via diagramsApi.versions", async () => {
    vi.mocked(diagramsModule.diagramsApi.versions).mockResolvedValue(MOCK_VERSIONS);

    render(
      <VersionPanel
        kind="diagram"
        artifactId={ARTIFACT_ID}
        currentVersion={{ version: 2, label: "v2", createdAt: null, baselineIds: [] }}
        onSwitch={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("version-row-1")).toBeInTheDocument();
      expect(screen.getByTestId("version-row-2")).toBeInTheDocument();
    });
    expect(diagramsModule.diagramsApi.versions).toHaveBeenCalledWith(ARTIFACT_ID);
  });

  it("[REQ-142] loads real glossary term versions via glossaryApi.versions", async () => {
    vi.mocked(glossaryModule.glossaryApi.versions).mockResolvedValue(MOCK_VERSIONS);

    render(
      <VersionPanel
        kind="glossary"
        artifactId={ARTIFACT_ID}
        currentVersion={{ version: 2, label: "v2", createdAt: null, baselineIds: [] }}
        onSwitch={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("version-row-1")).toBeInTheDocument();
      expect(screen.getByTestId("version-row-2")).toBeInTheDocument();
    });
    expect(glossaryModule.glossaryApi.versions).toHaveBeenCalledWith(ARTIFACT_ID);
  });

  it("[REQ-142] renders the error banner when diagramsApi.versions rejects", async () => {
    vi.mocked(diagramsModule.diagramsApi.versions).mockRejectedValue(
      new Error("Diagram not found")
    );

    render(
      <VersionPanel
        kind="diagram"
        artifactId={ARTIFACT_ID}
        currentVersion={undefined}
        onSwitch={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("version-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("version-error")).toHaveTextContent("Diagram not found");
  });

  it("[REQ-142] renders the error banner when glossaryApi.versions rejects", async () => {
    vi.mocked(glossaryModule.glossaryApi.versions).mockRejectedValue(
      new Error("GlossaryTerm not found")
    );

    render(
      <VersionPanel
        kind="glossary"
        artifactId={ARTIFACT_ID}
        currentVersion={undefined}
        onSwitch={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("version-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("version-error")).toHaveTextContent("GlossaryTerm not found");
  });
});
