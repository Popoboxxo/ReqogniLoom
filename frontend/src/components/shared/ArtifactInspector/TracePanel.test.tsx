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
import userEvent from "@testing-library/user-event";
import { TracePanel } from "./TracePanel";
import * as tracelinksModule from "../../../api/tracelinks";
import * as requirementsModule from "../../../api/requirements";
import * as workspaceModule from "../../../context/WorkspaceContext";
import * as linkTypeModule from "../../../context/LinkTypeContext";

// Mock API modules
vi.mock("../../../api/tracelinks");
vi.mock("../../../context/WorkspaceContext");
vi.mock("../../../context/LinkTypeContext");
// The Links tab mounts the shared `CreateTraceLinkDialog` (REQ-005), which
// loads its target list from six list endpoints. Stub them so the panel stays
// unit-testable without a network layer.
vi.mock("../../../api/requirements", () => ({
  requirementsApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/architecture", () => ({
  architectureApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/testcases", () => ({
  testcasesApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/adrs", () => ({
  adrsApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/risks", () => ({
  risksApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/issues", () => ({
  issuesApi: { listAll: vi.fn().mockResolvedValue([]) },
}));
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
      // Creatable types feed the create dialog's link-type listbuilder.
      creatableLinkTypes: keys.map((key) => ({
        key,
        definition: { label: {}, allowed_pairs: [] },
      })),
      isLoading: false,
      error: null,
      reload: vi.fn(),
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

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    // Should show loading indicator with aria-busy
    await waitFor(() => {
      const loadingDiv = screen.getByLabelText("loading");
      expect(loadingDiv).toHaveAttribute("aria-busy", "true");
    });
  });

  it("should fetch trace links from API using listForArtifact", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      expect(
        tracelinksModule.tracelinksApi.listForArtifact
      ).toHaveBeenCalledWith(mockWorkspace.id, mockArtifactId);
    });
  });

  it("should display fetched trace links with artifact titles", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

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

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

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

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      // Should show error message
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/sidebar.trace.error/i)).toBeInTheDocument();
    });
  });

  it("should distinguish outbound links (artifact is source)", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      // The first mock link has artifact-001 as source, so it's outbound
      const outboundSection = screen.getByText(/outbound/i);
      expect(outboundSection).toBeInTheDocument();
    });
  });

  it("should distinguish inbound links (artifact is target)", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      // The second mock link has artifact-001 as target, so it's inbound
      const inboundSection = screen.getByText(/inbound/i);
      expect(inboundSection).toBeInTheDocument();
    });
  });

  it("should display multiple sections for inbound and outbound links", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

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

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    // Component should render empty state
    await waitFor(() => {
      expect(screen.getByText(/sidebar.trace.empty/i)).toBeInTheDocument();
    });
  });

  it("renders a chip per catalog link type, not a hardcoded list", async () => {
    mockCatalog(["allocated-to", "verifies", "decides", "mitigates"]);

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

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

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      expect(screen.getByText("Tenant Invented Target")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("trace-filter-chip-conflicts-with")
    ).toBeInTheDocument();
  });

  it("should reload links when artifact ID changes", async () => {
    const { rerender } = render(
      <TracePanel kind="requirement" entityId={mockArtifactId} />
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
    rerender(<TracePanel kind="requirement" entityId={newArtifactId} />);

    await waitFor(() => {
      const callCountAfter = vi.mocked(
        tracelinksModule.tracelinksApi.listForArtifact
      ).mock.calls.length;
      expect(callCountAfter).toBeGreaterThan(callCountBefore);
    });
  });
});

/**
 * #1827: the Links tab replaced the stacked `TraceLinkPanel`, which owned the
 * "new link" entry in its header. The tab has no header of its own, so the
 * entry has to be part of the panel — including (and especially) when the
 * artifact has no links at all. Without it the empty state was a dead end.
 */
describe("TracePanel — Links-tab create entry (#1827)", () => {
  const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };
  const mockArtifactId = "artifact-001";

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceModule.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(linkTypeModule.useLinkTypes).mockReturnValue({
      linkTypes: [{ key: "allocated-to", definition: { label: {}, allowed_pairs: [] } }],
      creatableLinkTypes: [
        { key: "allocated-to", definition: { label: {}, allowed_pairs: [] } },
      ],
      isLoading: false,
      error: null,
      reload: vi.fn(),
      definitionFor: () => undefined,
      isAllowedPair: () => true,
      labelFor: (key: string) => key,
    } as any);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue([] as any);
  });

  it("renders the create entry in the empty state", async () => {
    render(<TracePanel kind="requirement" entityId={mockArtifactId} variant="tab" />);

    await waitFor(() => {
      expect(screen.getByTestId("links-empty")).toBeInTheDocument();
    });
    // Same testid as the stacked panel's header button: the E2E flow and the
    // routes that never mounted `TraceLinkPanel` both rely on it.
    expect(screen.getByTestId("trace-link-panel-open-dialog")).toBeInTheDocument();
  });

  it("opens the shared create dialog from the empty state", async () => {
    const user = userEvent.setup();
    render(<TracePanel kind="requirement" entityId={mockArtifactId} variant="tab" />);

    const openButton = await screen.findByTestId("trace-link-panel-open-dialog");
    await user.click(openButton);

    expect(await screen.findByTestId("create-trace-link-dialog")).toBeInTheDocument();
  });

  it("refetches the list once after a link was created", async () => {
    const user = userEvent.setup();
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue([
      { id: "req-1", title: "Requirement A" },
    ] as any);

    render(<TracePanel kind="requirement" entityId={mockArtifactId} variant="tab" />);

    await user.click(await screen.findByTestId("trace-link-panel-open-dialog"));
    await user.click(await screen.findByTestId("create-trace-link-target-element-req-1"));

    const callsBeforeCreate = vi.mocked(tracelinksModule.tracelinksApi.listForArtifact)
      .mock.calls.length;
    await user.click(screen.getByTestId("create-trace-link-submit"));

    await waitFor(() => {
      expect(
        vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mock.calls.length
      ).toBe(callsBeforeCreate + 1);
    });
    // The dialog closes itself once the link exists.
    await waitFor(() => {
      expect(screen.queryByTestId("create-trace-link-dialog")).toBeNull();
    });
  });

  it("does not add the entry to the stacked panel form", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [
        {
          id: "link-1",
          source_id: mockArtifactId,
          target_id: "req-1",
          link_type: "allocated-to",
          source_title: "Test Artifact",
          source_type: "Requirement",
          target_title: "Requirement A",
          target_type: "Requirement",
          created_at: "2026-01-15T08:00:00Z",
        },
      ],
    } as any);

    render(<TracePanel kind="requirement" entityId={mockArtifactId} />);

    await waitFor(() => {
      expect(screen.getByText("Requirement A")).toBeInTheDocument();
    });
    // The stacked form is hosted next to a `TraceLinkPanel`, which owns the
    // one and only create button for that surface.
    expect(screen.queryByTestId("trace-link-panel-open-dialog")).toBeNull();
  });
});

