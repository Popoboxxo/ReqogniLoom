/**
 * ARCH-L1-001 ReactFrontend — CsvImport entity-type i18n labels.
 *
 * leaf_id: COMP-RF-001 (CsvImport)
 * req_id:  REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * Issue #657: Entity-type radio labels render raw CamelCase enum values
 * instead of localized, readable text.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

import { CsvImport } from "../components/CsvImport/CsvImport";
import { i18n } from "../i18n/index";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "Test Workspace" },
  }),
}));

vi.mock("../api/import", () => ({
  importApi: {
    importCsv: vi.fn(),
    importReqif: vi.fn(),
  },
}));

vi.mock("../api/export", () => ({
  exportApi: {
    downloadCsv: vi.fn(),
    downloadReqif: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CsvImport entity-type i18n labels (#657)", () => {
  afterEach(() => {
    cleanup();
    void i18n.changeLanguage("en");
  });

  it("renders entity type labels as readable localized text in German, not raw CamelCase enum values", async () => {
    await i18n.changeLanguage("de");

    render(<CsvImport />);

    // CSV Import + Export both use "Requirement" → "Anforderung" label
    const anforderung = screen.getAllByText("Anforderung");
    expect(anforderung.length).toBeGreaterThanOrEqual(2);

    // "ArchitectureElement" → "Architekturelement" appears in both sections
    const archLabels = screen.getAllByText("Architekturelement");
    expect(archLabels.length).toBeGreaterThanOrEqual(2);

    expect(screen.getByText("Testfall")).toBeInTheDocument();
    expect(screen.getByText("Stakeholder-Bedarf")).toBeInTheDocument();

    // Raw CamelCase enum values must NOT appear as label text
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument();
    expect(screen.queryByText("StakeholderNeed")).not.toBeInTheDocument();
  });

  it("renders entity type labels as readable localized text in English, not raw CamelCase enum values", async () => {
    await i18n.changeLanguage("en");

    render(<CsvImport />);

    // "Requirement" appears in both CSV Import and CSV Export sections
    const requirementLabels = screen.getAllByText("Requirement");
    expect(requirementLabels.length).toBeGreaterThanOrEqual(2);

    // "Architecture Element" appears in both CSV Import and CSV Export sections
    const archLabels = screen.getAllByText("Architecture Element");
    expect(archLabels.length).toBeGreaterThanOrEqual(2);

    expect(screen.getByText("Test Case")).toBeInTheDocument();
    expect(screen.getByText("Stakeholder Need")).toBeInTheDocument();

    // Raw CamelCase enum values must NOT appear as label text
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument();
    expect(screen.queryByText("StakeholderNeed")).not.toBeInTheDocument();
  });
});
