/**
 * ARCH-L1-001 ReactFrontend — ImpactView tests.
 *
 * NOTE ON REQ-ID: The task brief references REQ-006, but REQ-006 in
 * docs/REQUIREMENTS.md is "Soft-Delete-Statusmodell". No registered REQ-ID
 * for impact-tree visualization exists yet — tests use the placeholder
 * REQ-006 as supplied by the orchestrator and flag this for the
 * `requirements` agent to resolve before the commit lands.
 *
 * Tests:
 * 1. [REQ-006] renders search input — component mounts without crash,
 *    search input and button are visible.
 * 2. [REQ-006] loads and displays artifact on search — mocked searchApi
 *    returns one hit; user clicks the result; artifact title appears in the
 *    tree panel.
 * 3. [REQ-006] tree node expands on click — mocked tracelinksApi returns one
 *    outgoing link; after clicking the expand toggle children are rendered.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImpactView } from "./ImpactView";
import * as searchModule from "../../api/search";
import * as tracelinksModule from "../../api/tracelinks";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/search");
vi.mock("../../api/tracelinks");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t }) };
});

const WORKSPACE_ID = "ws-impact-001";
const mockWorkspace = { id: WORKSPACE_ID, name: "Impact WS", preset: "standard" };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
    activeWorkspace: mockWorkspace,
  } as ReturnType<typeof workspaceContext.useWorkspace>);
});

describe("ImpactView", () => {
  it("[REQ-006] renders search input and button without crashing", () => {
    render(<ImpactView />);

    expect(screen.getByTestId("impact-view")).toBeInTheDocument();
    expect(screen.getByTestId("impact-search-input")).toBeInTheDocument();
    expect(screen.getByTestId("impact-search-btn")).toBeInTheDocument();
  });

  it("[REQ-006] loads and displays artifact on search", async () => {
    const searchHit = {
      id: "art-sys-001",
      artifact_type: "Requirement" as const,
      title: "System shall authenticate users via JWT",
      description: "JWT-based auth requirement.",
      relevance_score: 0.97,
      workspace_id: WORKSPACE_ID,
    };
    vi.mocked(searchModule.searchApi.search).mockResolvedValue({
      results: [searchHit],
      total_count: 1,
      page: 1,
      limit: 10,
      query: "authenticate",
    });

    const user = userEvent.setup();
    render(<ImpactView />);

    const input = screen.getByTestId("impact-search-input");
    await user.type(input, "authenticate");
    await user.click(screen.getByTestId("impact-search-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("impact-search-results")).toBeInTheDocument();
    });

    const resultBtn = screen.getByTestId("impact-search-result");
    expect(resultBtn).toHaveTextContent("System shall authenticate users via JWT");

    await user.click(resultBtn);

    await waitFor(() => {
      expect(screen.getByTestId("impact-tree-panel")).toBeInTheDocument();
    });
    // Root node displays the selected artifact title
    expect(screen.getByTestId("impact-tree-panel")).toHaveTextContent(
      "System shall authenticate users via JWT"
    );
  });

  it("[REQ-006] tree node expands on click and shows children", async () => {
    const rootArtifactId = "art-req-042";
    const childArtifactId = "art-arch-007";

    const searchHit = {
      id: rootArtifactId,
      artifact_type: "Requirement" as const,
      title: "REQ-042 Login flow",
      description: "Root requirement for the test.",
      relevance_score: 0.99,
      workspace_id: WORKSPACE_ID,
    };
    vi.mocked(searchModule.searchApi.search).mockResolvedValue({
      results: [searchHit],
      total_count: 1,
      page: 1,
      limit: 10,
      query: "login",
    });

    // One outgoing trace link: root -> child
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [
        {
          id: "tl-9001",
          workspace_id: WORKSPACE_ID,
          source_id: rootArtifactId,
          source_title: "REQ-042 Login flow",
          source_type: "Requirement",
          target_id: childArtifactId,
          target_title: "ARCH-007 AuthModule",
          target_type: "ArchitectureElement",
          link_type: "derives_from",
          version: 1,
          created_at: "2026-01-15T10:00:00Z",
          updated_at: "2026-01-15T10:00:00Z",
        },
      ],
      count: 1,
      next: null,
      previous: null,
    } as any);

    const user = userEvent.setup();
    render(<ImpactView />);

    // Search and select the root artifact
    await user.type(screen.getByTestId("impact-search-input"), "login");
    await user.click(screen.getByTestId("impact-search-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("impact-search-result")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("impact-search-result"));

    await waitFor(() => {
      expect(screen.getByTestId("impact-tree-panel")).toBeInTheDocument();
    });

    // The root node toggle button exists at depth 0
    const toggleBtn = screen.getByTestId("impact-node-toggle");
    await user.click(toggleBtn);

    await waitFor(() => {
      expect(tracelinksModule.tracelinksApi.listForArtifact).toHaveBeenCalledWith(
        WORKSPACE_ID,
        rootArtifactId
      );
    });

    // After expansion the child artifact title is visible
    await waitFor(() => {
      expect(screen.getByTestId("impact-tree-panel")).toHaveTextContent("ARCH-007 AuthModule");
    });

    // A link-group with derives_from direction arrow should appear
    const linkGroups = screen.getAllByTestId("impact-link-group");
    expect(linkGroups.length).toBeGreaterThan(0);
  });
});
