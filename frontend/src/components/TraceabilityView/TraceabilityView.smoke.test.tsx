/**
 * Smoke tests for TraceabilityView (REQ-053 coverage).
 *
 * req_id: REQ-053, REQ-L2-RF-006
 *
 * Verifies:
 *   - TraceabilityView renders loading indicator while data is in-flight
 *   - TraceabilityView renders the view container after data resolves
 *   - TraceabilityView renders trace links grouped by type
 *   - "Add Link" button is present
 *   - Error state renders when the API call fails
 *
 * TraceabilityView does not use react-router or TanStack Query — it fires
 * parallel fetch calls inside useEffect. All API modules are mocked so no
 * real network calls are made.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/tracelinks");
vi.mock("../../api/traceability");
vi.mock("../../api/requirements");
vi.mock("../../api/architecture");
vi.mock("../../api/artifacts");
vi.mock("../../api/testcases");
vi.mock("../../api/risks");
vi.mock("../../api/issues");
vi.mock("../../api/adrs");
vi.mock("../../api/stakeholder-need");
vi.mock("../../api/icds");
vi.mock("../../api/workspaces");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t }) };
});
// Stub CreateTraceLinkDialog so it does not pull in more dependencies
vi.mock("../shared/CreateTraceLinkDialog", () => ({
  CreateTraceLinkDialog: () => React.createElement("div", { "data-testid": "create-link-dialog-stub" }),
}));

import * as tracelinksModule from "../../api/tracelinks";
import * as traceabilityModule from "../../api/traceability";
import * as requirementsModule from "../../api/requirements";
import * as archModule from "../../api/architecture";
import * as artifactsModule from "../../api/artifacts";
import * as testcasesModule from "../../api/testcases";
import * as risksModule from "../../api/risks";
import * as issuesModule from "../../api/issues";
import * as adrsModule from "../../api/adrs";
import * as needsModule from "../../api/stakeholder-need";
import * as icdsModule from "../../api/icds";
import * as workspaceContext from "../../context/WorkspaceContext";

import TraceabilityView from "./TraceabilityView";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-trace-001", name: "Traceability WS", preset: "extended" };

const MOCK_LINKS = [
  {
    id: "tl-001",
    workspace_id: "ws-trace-001",
    source_id: "req-001",
    target_id: "arch-001",
    link_type: "implements",
    created_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "tl-002",
    workspace_id: "ws-trace-001",
    source_id: "req-001",
    target_id: "tc-001",
    link_type: "verifies",
    created_at: "2026-01-16T08:00:00Z",
  },
];

const EMPTY_PAGE = { results: [] };
// listAll()-backed APIs (issue C) return a plain array, not a paginated page.
const EMPTY_LIST: unknown[] = [];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupDefaultMocks(): void {
  vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
    activeWorkspace: MOCK_WORKSPACE,
  } as any);
  vi.mocked(tracelinksModule.tracelinksApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue(EMPTY_PAGE as any);
  vi.mocked(archModule.architectureApi.list).mockResolvedValue(EMPTY_PAGE as any);
  vi.mocked(testcasesModule.testcasesApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(artifactsModule.artifactsApi.list).mockResolvedValue(EMPTY_PAGE as any);
  vi.mocked(risksModule.risksApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(issuesModule.issuesApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(adrsModule.adrsApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(needsModule.stakeholderNeedApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(icdsModule.icdsApi.listAll).mockResolvedValue(EMPTY_LIST as any);
  vi.mocked(traceabilityModule.traceabilityApi.cycles).mockResolvedValue({
    cycles: [],
    count: 0,
  } as any);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TraceabilityView (REQ-053 smoke tests)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it("[REQ-053] shows loading indicator initially while fetching trace data", () => {
    // Make the primary list call never resolve so loading stays true
    vi.mocked(tracelinksModule.tracelinksApi.listAll).mockReturnValue(new Promise(() => {}));

    render(<TraceabilityView />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[REQ-053] renders traceability-view container after data resolves", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getByTestId("traceability-view")).toBeInTheDocument();
    });
    // Loading indicator gone after load
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("[REQ-053] renders Add TraceLink button when data has loaded", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    // Use the stable data-testid to avoid ambiguity with other buttons
    expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
  });

  it("[REQ-053] renders links grouped by type after data resolves", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listAll).mockResolvedValue(MOCK_LINKS as any);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      results: [
        { id: "req-001", title: "Navigation accuracy <= 1m CEP", workspace_id: "ws-trace-001" },
      ],
    } as any);
    vi.mocked(archModule.architectureApi.list).mockResolvedValue({
      results: [
        { id: "arch-001", title: "GPS Receiver Module", workspace_id: "ws-trace-001" },
      ],
    } as any);

    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    // Both link types should appear as section headings (data-testid="tracelink-type")
    const linkTypeBadges = screen.getAllByTestId("tracelink-type");
    const linkTypeTexts = linkTypeBadges.map((el) => el.textContent ?? "");
    expect(linkTypeTexts.some((t) => /implementation/i.test(t))).toBe(true);
    expect(linkTypeTexts.some((t) => /verification/i.test(t))).toBe(true);
  });

  it("[REQ-053] renders error alert when API fetch fails with a non-404 error", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listAll).mockRejectedValue(
      { error: { message: "internal server error" } }
    );

    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/internal server error/i)).toBeInTheDocument();
  });

  it("[REQ-053] renders empty state gracefully when no links exist", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("traceability-view")).toBeInTheDocument();
  });
});
