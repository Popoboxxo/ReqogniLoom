/**
 * TracePanel.test.tsx (REQ-L2-RF-037)
 *
 * Tests for TracePanel component:
 * - Fetches trace links from real API endpoint via tracelinksApi.listForArtifact()
 * - Renders loading state while data is in-flight
 * - Displays fetched trace links grouped by direction (inbound/outbound)
 * - Shows empty state when no links exist after successful fetch
 * - Displays error message on API failure
 * - Resolves artifact titles and kinds for linked artifacts
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TracePanel } from "./TracePanel";
import * as tracelinksModule from "../../../api/tracelinks";
import * as workspaceModule from "../../../context/WorkspaceContext";
import * as linkTypeModule from "../../../context/LinkTypeContext";

// Mock API modules
vi.mock("../../../api/tracelinks");
vi.mock("../../../context/WorkspaceContext");
vi.mock("../../../context/LinkTypeContext");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

describe("TracePanel (REQ-L2-RF-037)", () => {
  const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };
  const mockArtifactId = "artifact-001";

  const mockTraceLinksData = [
    {
      id: "link-1",
      source_id: "artifact-001",
      target_id: "req-1",
      link_type: "allocated-to",
      source_title: "Test Artifact",
      source_type: "Requirement",
      target_title: "Requirement A",
      target_type: "Requirement",
      created_at: "2026-01-15T08:00:00Z",
    },
    {
      id: "link-2",
      source_id: "arch-1",
      target_id: "artifact-001",
      link_type: "verifies",
      source_title: "Architecture B",
      source_type: "ArchitectureElement",
      target_title: "Test Artifact",
      target_type: "Requirement",
      created_at: "2026-01-16T08:00:00Z",
    },
  ];

  /** A minimal workspace catalog — two of the eight built-in keys. */
  function mockCatalog(keys: string[]): void {
    vi.mocked(linkTypeModule.useLinkTypes).mockReturnValue({
      linkTypes: keys.map((key) => ({
        key,
        definition: { label: {}, allowed_pairs: [] },
      })),
      isLoading: false,
      error: null,
      reload: vi.fn(),
      creatableLinkTypes: [],
      definitionFor: () => undefined,
      isAllowedPair: () => true,
      labelFor: (key: string) => key,
    } as any);
  }

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup default mocks
    vi.mocked(workspaceModule.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);

    mockCatalog(["allocated-to", "verifies"]);

    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: mockTraceLinksData,
    } as any);
  });

  it("should render loading indicator while fetching trace links", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    // Should show loading indicator with aria-busy
    await waitFor(() => {
      const loadingDiv = screen.getByLabelText("loading");
      expect(loadingDiv).toHaveAttribute("aria-busy", "true");
    });
  });

  it("should fetch trace links from API using listForArtifact", async () => {
    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      expect(
        tracelinksModule.tracelinksApi.listForArtifact
      ).toHaveBeenCalledWith(mockWorkspace.id, mockArtifactId);
    });
  });

  it("should display fetched trace links with artifact titles", async () => {
    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // Check that artifact titles are displayed
      expect(screen.getByText("Requirement A")).toBeInTheDocument();
      expect(screen.getByText("Architecture B")).toBeInTheDocument();
    });
  });

  it("should show empty state when no trace links exist", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [],
    } as any);

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // Should show empty state message
      expect(screen.getByText(/sidebar.trace.empty/i)).toBeInTheDocument();
    });
  });

  it("should display error state when API fetch fails", async () => {
    const errorMessage = "Failed to fetch trace links";
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockRejectedValue(
      new Error(errorMessage)
    );

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // Should show error message
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/sidebar.trace.error/i)).toBeInTheDocument();
    });
  });

  it("should distinguish outbound links (artifact is source)", async () => {
    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // The first mock link has artifact-001 as source, so it's outbound
      const outboundSection = screen.getByText(/outbound/i);
      expect(outboundSection).toBeInTheDocument();
    });
  });

  it("should distinguish inbound links (artifact is target)", async () => {
    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // The second mock link has artifact-001 as target, so it's inbound
      const inboundSection = screen.getByText(/inbound/i);
      expect(inboundSection).toBeInTheDocument();
    });
  });

  it("should display multiple sections for inbound and outbound links", async () => {
    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      // Should have sections for both directions
      const sections = screen.getAllByRole("heading", { level: 4 });
      expect(sections.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("should handle empty workspace gracefully", async () => {
    vi.mocked(workspaceModule.useWorkspace).mockReturnValue({
      activeWorkspace: null,
    } as any);

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    // Component should render empty state
    await waitFor(() => {
      expect(screen.getByText(/sidebar.trace.empty/i)).toBeInTheDocument();
    });
  });

  it("renders a chip per catalog link type, not a hardcoded list", async () => {
    mockCatalog(["allocated-to", "verifies", "decides", "mitigates"]);

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      expect(screen.getByTestId("trace-filter-chip-decides")).toBeInTheDocument();
    });
    expect(screen.getByTestId("trace-filter-chip-mitigates")).toBeInTheDocument();
    // The retired types this panel used to hardcode are gone from the chips.
    expect(screen.queryByTestId("trace-filter-chip-satisfies")).toBeNull();
  });

  it("still renders a link whose type the catalog does not know", async () => {
    // The regression this test exists for: the panel used to filter every
    // link through a static 8-value list and *drop* the rest with no error,
    // no empty state and no visible sign. An unknown key must stay visible
    // and get its own chip, labelled with the raw key.
    mockCatalog(["verifies"]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [
        {
          id: "link-x",
          source_id: mockArtifactId,
          target_id: "arch-9",
          link_type: "conflicts-with",
          source_title: "Test Artifact",
          source_type: "Requirement",
          target_title: "Tenant Invented Target",
          target_type: "ArchitectureElement",
          created_at: "2026-01-17T08:00:00Z",
        },
      ],
    } as any);

    render(<TracePanel kind="requirement" artifactId={mockArtifactId} />);

    await waitFor(() => {
      expect(screen.getByText("Tenant Invented Target")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("trace-filter-chip-conflicts-with")
    ).toBeInTheDocument();
  });

  it("should reload links when artifact ID changes", async () => {
    const { rerender } = render(
      <TracePanel kind="requirement" artifactId={mockArtifactId} />
    );

    await waitFor(() => {
      expect(
        tracelinksModule.tracelinksApi.listForArtifact
      ).toHaveBeenCalledWith(mockWorkspace.id, mockArtifactId);
    });

    const callCountBefore = vi.mocked(
      tracelinksModule.tracelinksApi.listForArtifact
    ).mock.calls.length;

    // Rerender with new artifact ID
    const newArtifactId = "artifact-002";
    rerender(<TracePanel kind="requirement" artifactId={newArtifactId} />);

    await waitFor(() => {
      const callCountAfter = vi.mocked(
        tracelinksModule.tracelinksApi.listForArtifact
      ).mock.calls.length;
      expect(callCountAfter).toBeGreaterThan(callCountBefore);
    });
  });
});
