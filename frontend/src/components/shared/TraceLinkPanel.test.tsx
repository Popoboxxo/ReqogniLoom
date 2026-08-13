/**
 * Regression coverage for #421 — the panel header ("Trace Links") and the
 * upstream/downstream column headings ("Incoming"/"Outgoing") stayed
 * English in the German UI because the `tracelinks.*` i18n namespace never
 * existed in de.json/en.json; `t(key, englishDefault)` silently fell back
 * to the (English) default on every render, in either language.
 *
 * Uses the real i18n resources (not a mocked `t`) so this actually
 * exercises the JSON translation files, not just the component's default
 * fallback strings.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { i18n } from "../../i18n/index";
import { TraceLinkPanel } from "./TraceLinkPanel";

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    create: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", default_link_type: "derives-from" } }),
}));

describe("TraceLinkPanel — i18n (#421)", () => {
  it("renders the German panel title and column headings, not the English defaults", async () => {
    await i18n.changeLanguage("de");

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId="art-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Trace-Links")).toBeInTheDocument();
    });
    expect(screen.getByText("Eingehend")).toBeInTheDocument();
    expect(screen.getByText("Ausgehend")).toBeInTheDocument();
    expect(screen.queryByText("Incoming")).not.toBeInTheDocument();
    expect(screen.queryByText("Outgoing")).not.toBeInTheDocument();
  });
});
