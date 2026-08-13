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
import { IMPACT_PRESET_STORAGE_KEY } from "./impact-preset";
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

// ---------------------------------------------------------------------------
// Issue #415 — cycle detection and root title
// ---------------------------------------------------------------------------

const ROOT_ID = "art-req-l1";
const CHILD_ID = "art-req-l2";

/** The single decomposition link between L1 and L2, as the API returns it. */
const DECOMPOSITION_LINK = {
  id: "tl-l1-l2",
  workspace_id: WORKSPACE_ID,
  source_id: ROOT_ID,
  source_title: "L1 System requirement",
  source_type: "Requirement",
  target_id: CHILD_ID,
  target_title: "L2 Subsystem requirement",
  target_type: "Requirement",
  link_type: "decomposes",
  version: 1,
  created_at: "2026-02-01T10:00:00Z",
};

function mockSearchHit(id: string, title: string, artifactType = "Requirement"): void {
  vi.mocked(searchModule.searchApi.search).mockResolvedValue({
    results: [
      {
        id,
        artifact_type: artifactType,
        title,
        description: "",
        relevance_score: 1,
        workspace_id: WORKSPACE_ID,
      },
    ],
    total_count: 1,
    page: 1,
    limit: 10,
    query: title,
  } as never);
}

describe("ImpactView — cycle detection (#415)", () => {
  it("[#415] does not re-expand an artifact already on the path", async () => {
    // Both artifacts see the same single link — the traversal used to walk it
    // back and forth forever (L1 -> L2 -> L1 -> ...).
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [DECOMPOSITION_LINK],
      count: 1,
      next: null,
      previous: null,
    } as never);
    mockSearchHit(ROOT_ID, "L1 System requirement");

    const user = userEvent.setup();
    render(<ImpactView />);

    await user.type(screen.getByTestId("impact-search-input"), "L1");
    await user.click(screen.getByTestId("impact-search-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("impact-search-result")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("impact-search-result"));

    // Expand the root: exactly one child (L2), marked as expandable.
    await user.click(screen.getAllByTestId("impact-node-toggle")[0]);
    await waitFor(() => {
      expect(screen.getAllByTestId("impact-tree-node")).toHaveLength(2);
    });

    // Expand the child: its only link points back at the root, which is
    // already on the path — it renders once, flagged, and cannot be expanded.
    await user.click(screen.getAllByTestId("impact-node-toggle")[1]);
    await waitFor(() => {
      expect(screen.getAllByTestId("impact-tree-node")).toHaveLength(3);
    });

    const cycleBadges = screen.getAllByTestId("impact-cycle-badge");
    expect(cycleBadges).toHaveLength(1);
    const nodes = screen.getAllByTestId("impact-tree-node");
    expect(nodes[2]).toHaveAttribute("data-cycle", "true");
    expect(screen.getAllByTestId("impact-node-toggle")[2]).toBeDisabled();
  });

  it("[#415] root node shows a title, never the raw UUID", async () => {
    // Hand-off from the traceability view without a resolved title (the exact
    // situation that rendered `Requirement 9c706550…` as the root).
    sessionStorage.setItem(
      IMPACT_PRESET_STORAGE_KEY,
      JSON.stringify({ id: ROOT_ID, title: "", artifactType: "" })
    );
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [DECOMPOSITION_LINK],
      count: 1,
      next: null,
      previous: null,
    } as never);

    const user = userEvent.setup();
    render(<ImpactView />);

    await waitFor(() => {
      expect(screen.getByTestId("impact-tree-panel")).toBeInTheDocument();
    });
    // Before expanding: shortened id, not the full UUID.
    expect(screen.getByTestId("impact-tree-panel")).not.toHaveTextContent(ROOT_ID);

    await user.click(screen.getAllByTestId("impact-node-toggle")[0]);

    // After the node loaded its own links it knows its title and type — the
    // same rendering path the child nodes use.
    await waitFor(() => {
      expect(screen.getAllByTestId("impact-tree-node")[0]).toHaveTextContent(
        "L1 System requirement"
      );
    });
    expect(screen.getAllByTestId("impact-node-type")[0]).toHaveTextContent("Requirement");
  });
});
