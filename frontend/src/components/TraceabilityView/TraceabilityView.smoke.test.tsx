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
 * TraceabilityView does not use TanStack Query — it fires parallel fetch
 * calls inside useEffect. All API modules are mocked so no real network
 * calls are made. #425: endpoints now navigate via useNavigate(), mocked
 * below so tests don't need a real <Router>.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

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
// Minimal i18next stand-in: honours the `t(key, defaultValue, options)`
// signature *including* `{{placeholder}}` interpolation, so tests can assert
// on rendered counts instead of on raw template strings.
vi.mock("react-i18next", () => {
  const interpolate = (template: string, opts?: Record<string, unknown>): string =>
    opts
      ? template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
          opts[name] === undefined ? match : String(opts[name])
        )
      : template;
  const t = (key: string, second?: unknown, third?: unknown): string => {
    const fallback = typeof second === "string" ? second : undefined;
    const opts = (typeof second === "object" && second !== null ? second : third) as
      | Record<string, unknown>
      | undefined;
    return interpolate(fallback ?? key, opts);
  };
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
  vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue(EMPTY_LIST as any);
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
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue([
      { id: "req-001", title: "Navigation accuracy <= 1m CEP", workspace_id: "ws-trace-001" },
    ] as any);
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

// ---------------------------------------------------------------------------
// Issue #413 — readable endpoints + coverage
// ---------------------------------------------------------------------------

/**
 * Artifact ids differ from entity ids on purpose: that mismatch is the whole
 * bug. `req-001` is the Requirement id, `art-req-001` its backing Artifact —
 * and only the latter ever appears in a TraceLink.
 */
const COVERAGE_LINKS = [
  {
    id: "tl-100",
    source_id: "art-tc-001",
    source_title: "TC-1 Login smoke test",
    source_type: "TestCase",
    target_id: "art-req-001",
    target_title: "Login must be possible",
    target_type: "Requirement",
    link_type: "verifies",
    version: 1,
    created_at: "2026-02-01T08:00:00Z",
  },
  {
    id: "tl-101",
    source_id: "art-req-002",
    source_title: "Password rotation",
    source_type: "Requirement",
    target_id: "art-arch-001",
    target_title: "AuthModule",
    target_type: "ArchitectureElement",
    link_type: "allocated-to",
    version: 1,
    created_at: "2026-02-01T09:00:00Z",
  },
];

const COVERAGE_REQUIREMENTS = [
  {
    id: "req-001",
    artifact_id: "art-req-001",
    uid: "REQ-1",
    title: "Login must be possible",
    workspace_id: "ws-trace-001",
  },
  {
    id: "req-002",
    artifact_id: "art-req-002",
    uid: "REQ-2",
    title: "Password rotation",
    workspace_id: "ws-trace-001",
  },
];

describe("TraceabilityView — readable endpoints and coverage (#413)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
    vi.mocked(tracelinksModule.tracelinksApi.listAll).mockResolvedValue(COVERAGE_LINKS as any);
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue(
      COVERAGE_REQUIREMENTS as any
    );
  });

  it("[#413] renders endpoint titles and artifact types instead of bare UUID pairs", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getAllByTestId("tracelink-item").length).toBe(2);
    });

    const sources = screen.getAllByTestId("tracelink-source");
    const targets = screen.getAllByTestId("tracelink-target");
    expect(sources[0]).toHaveTextContent("TC-1 Login smoke test");
    expect(targets[0]).toHaveTextContent("Login must be possible");
    // Artifact type badge accompanies each endpoint
    expect(screen.getAllByTestId("tracelink-source-type")[0]).toHaveTextContent("TestCase");
    expect(screen.getAllByTestId("tracelink-target-type")[0]).toHaveTextContent("Requirement");
  });

  it("[#425] endpoint entries are keyboard-operable buttons that open the right entity route", async () => {
    const user = userEvent.setup();
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getAllByTestId("tracelink-item").length).toBe(2);
    });

    const target = screen.getAllByTestId("tracelink-target")[0];
    // A real <button>, not inert text — reachable via Tab, operable via Enter/click.
    expect(target.tagName).toBe("BUTTON");

    await user.click(target);

    // target_id "art-req-001" (Artifact.id) resolves via COVERAGE_REQUIREMENTS
    // to Requirement.id "req-001" (#414's artifact-id vs entity-id gap) — the
    // route must use the entity id, not the artifact id.
    expect(mockNavigate).toHaveBeenCalledWith("/requirements/req-001");
  });

  it("[#413] marks requirement endpoints as verified / not verified", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getAllByTestId("tracelink-coverage-badge").length).toBeGreaterThan(0);
    });

    const badges = screen.getAllByTestId("tracelink-coverage-badge");
    const covered = badges.map((b) => b.getAttribute("data-covered"));
    // req-001 is verified by TC-1, req-002 has no verifying test
    expect(covered).toContain("true");
    expect(covered).toContain("false");
  });

  it("[#413] summarises coverage over all requirements", async () => {
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getByTestId("traceability-coverage-summary")).toBeInTheDocument();
    });
    const summary = screen.getByTestId("traceability-coverage-summary").textContent ?? "";
    expect(summary).toContain("1");
    expect(summary).toContain("2");
  });

  it("[#413] 'not covered' filter lists requirements without a verifying test", async () => {
    const user = userEvent.setup();
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getByTestId("traceability-uncovered-toggle")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("traceability-uncovered-toggle"));

    const items = await screen.findAllByTestId("uncovered-requirement-item");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("Password rotation");
    // The covered requirement must not be listed
    expect(screen.queryByText(/Login must be possible/)).not.toBeInTheDocument();
  });

  it("[#413] counts a requirement without any trace link as uncovered", async () => {
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue([
      ...COVERAGE_REQUIREMENTS,
      {
        id: "req-003",
        artifact_id: "art-req-003",
        uid: "REQ-3",
        title: "Orphan requirement",
        workspace_id: "ws-trace-001",
      },
    ] as any);

    const user = userEvent.setup();
    render(<TraceabilityView />);

    await waitFor(() => {
      expect(screen.getByTestId("traceability-uncovered-toggle")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("traceability-uncovered-toggle"));

    const items = await screen.findAllByTestId("uncovered-requirement-item");
    expect(items.map((i) => i.textContent ?? "").join(" ")).toContain("Orphan requirement");
  });
});
