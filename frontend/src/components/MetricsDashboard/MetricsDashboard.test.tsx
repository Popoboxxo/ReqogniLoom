/**
 * MetricsDashboard Tests
 *
 * Covers: Help mode toggle, help text visibility, component rendering.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { ReactNode } from "react";
import MetricsDashboard from "./MetricsDashboard";

// Mock dependencies
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: {
      id: "test-workspace-id",
      name: "Test Workspace",
    },
  }),
}));

vi.mock("../../api/metrics", () => ({
  metricsApi: {
    list: vi.fn().mockResolvedValue({
      computed_at: new Date().toISOString(),
      timeframe: "Last 7 days",
      workspace_id: "test-workspace-id",
      traceability_coverage: { coverage_percent: 85.5 },
      volatility: { avg_changes_per_req: 1.2 },
      workflow_gaps: { total_incomplete: 3 },
      open_risks: { total: 4, by_severity: { critical: 1 } },
      warnings: [],
    }),
  },
}));

// Mock i18n provider wrapper (minimal)
const MockWrapper = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);

describe("MetricsDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Help Mode Toggle", () => {
    it("renders help toggle button", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      expect(helpBtn).toBeInTheDocument();
      expect(helpBtn.textContent).toBe("?");
    });

    it("toggles help mode when button is clicked", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");

      // Initially, help texts should not be visible
      let helpTexts = screen.queryAllByTestId(/metric-help-/);
      expect(helpTexts.length).toBe(0);

      // Click to enable help mode
      fireEvent.click(helpBtn);

      // After click, help texts should appear
      helpTexts = await screen.findAllByTestId(/metric-help-/);
      expect(helpTexts.length).toBeGreaterThan(0);

      // Click again to disable
      fireEvent.click(helpBtn);

      // Help texts should disappear
      helpTexts = screen.queryAllByTestId(/metric-help-/);
      expect(helpTexts.length).toBe(0);
    });

    it("changes button background color when help mode is active", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");

      // Initial state: transparent background
      expect(helpBtn).toHaveStyle("background: transparent");

      // Click to enable help mode
      fireEvent.click(helpBtn);

      // After click: primary background color
      expect(helpBtn).toHaveStyle("background: var(--color-primary)");
    });
  });

  describe("Help Text Display", () => {
    it("displays help texts when help mode is enabled", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      fireEvent.click(helpBtn);

      // Verify that help texts are visible for all metrics
      const coverageHelp = await screen.findByTestId("metric-help-coverage");
      const volatilityHelp = screen.getByTestId("metric-help-volatility");
      const workflowGapHelp = screen.getByTestId("metric-help-workflowGap");
      const openRisksHelp = screen.getByTestId("metric-help-openRisks");
      const openRisksCriticalHelp = screen.getByTestId("metric-help-openRisksCritical");

      expect(coverageHelp).toBeInTheDocument();
      expect(volatilityHelp).toBeInTheDocument();
      expect(workflowGapHelp).toBeInTheDocument();
      expect(openRisksHelp).toBeInTheDocument();
      expect(openRisksCriticalHelp).toBeInTheDocument();
    });

    it("hides help texts when help mode is disabled", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");

      // Enable help mode
      fireEvent.click(helpBtn);
      expect(await screen.findByTestId("metric-help-coverage")).toBeInTheDocument();

      // Disable help mode
      fireEvent.click(helpBtn);

      // Help texts should be gone
      expect(screen.queryByTestId("metric-help-coverage")).not.toBeInTheDocument();
      expect(screen.queryByTestId("metric-help-volatility")).not.toBeInTheDocument();
    });

    it("displays correct help text content for coverage metric", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      fireEvent.click(helpBtn);

      const coverageHelp = await screen.findByTestId("metric-help-coverage");
      expect(coverageHelp.textContent).toContain("Trace-Verbindung");
    });

    it("displays correct help text content for volatility metric", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      fireEvent.click(helpBtn);

      const volatilityHelp = await screen.findByTestId("metric-help-volatility");
      expect(volatilityHelp.textContent).toContain("Änderungen");
    });
  });

  describe("Component Rendering", () => {
    it("renders metrics dashboard successfully", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      expect(await screen.findByTestId("metrics-dashboard")).toBeInTheDocument();
    });

    it("renders all metric tiles", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const coverageTile = await screen.findByTestId("metric-tile-coverage");
      const volatilityTile = screen.getByTestId("metric-tile-volatility");
      const workflowGapTile = screen.getByTestId("metric-tile-workflowGap");
      const openRisksTile = screen.getByTestId("metric-tile-openRisks");
      const openRisksCriticalTile = screen.getByTestId("metric-tile-openRisksCritical");

      expect(coverageTile).toBeInTheDocument();
      expect(volatilityTile).toBeInTheDocument();
      expect(workflowGapTile).toBeInTheDocument();
      expect(openRisksTile).toBeInTheDocument();
      expect(openRisksCriticalTile).toBeInTheDocument();
    });

    it("renders filter select and refresh button", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const filterSelect = await screen.findByTestId("metrics-filter-select");
      const refreshBtn = screen.getByTestId("metrics-refresh-btn");

      expect(filterSelect).toBeInTheDocument();
      expect(refreshBtn).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------
  // GESAMTTEST_BERICHT_2026-08-21.md §5 finding 7: the 5 `metric-status-*`
  // spans carried `aria-label` with no `role`, which some screen readers do
  // not reliably expose. Each must now carry both role="img" AND a non-empty
  // accessible name (the previous aria-label content, unchanged).
  // ---------------------------------------------------------------------
  describe("Status-dot accessibility (§5 finding 7)", () => {
    const TILE_NAMES = [
      "coverage",
      "volatility",
      "workflowGap",
      "openRisks",
      "openRisksCritical",
    ];

    it("gives all 5 metric-status-* spans role=img and a non-empty accessible name", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-status-coverage");

      for (const name of TILE_NAMES) {
        const span = screen.getByTestId(`metric-status-${name}`);
        expect(span).toHaveAttribute("role", "img");
        expect(span.getAttribute("aria-label")).toBeTruthy();
      }
    });
  });

  // ---------------------------------------------------------------------
  // GitHub #450: filter dropdown must not be disabled (mirrors ListToolbar's
  // list pages, which never gate filters on a loading flag), and the Refresh
  // button must re-enable ("Refresh", not stuck on "Refreshing...") once its
  // own request settles.
  // ---------------------------------------------------------------------
  describe("Filter/Refresh availability (GitHub #450)", () => {
    it("never disables the filter select, even while a request is in flight", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const filterSelect = await screen.findByTestId("metrics-filter-select");
      expect(filterSelect).not.toBeDisabled();

      fireEvent.click(screen.getByTestId("metrics-refresh-btn"));
      // Still not disabled while the refresh request is in flight.
      expect(filterSelect).not.toBeDisabled();

      await waitFor(() =>
        expect(screen.getByTestId("metrics-refresh-btn")).not.toBeDisabled()
      );
      expect(filterSelect).not.toBeDisabled();
    });

    it("re-enables the Refresh button and restores its label after a refresh completes", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      const refreshBtn = await screen.findByTestId("metrics-refresh-btn");
      await waitFor(() => expect(refreshBtn).not.toBeDisabled());
      expect(refreshBtn.textContent).toBe("Refresh");

      fireEvent.click(refreshBtn);

      await waitFor(() => expect(refreshBtn).not.toBeDisabled());
      expect(refreshBtn.textContent).toBe("Refresh");
    });
  });
});
