/**
 * MetricsDashboard Tests
 *
 * Covers: Help mode toggle, help text visibility, component rendering,
 * and the configurable statistics widgets (#1265).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { ReactNode } from "react";
import MetricsDashboard from "./MetricsDashboard";
import { metricsApi } from "../../api/metrics";
import { displayPreferencesApi } from "../../api/display-preferences";
import { buildMetricCatalog } from "./metric-catalog.fixture";

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
  useOptionalWorkspace: () => ({
    activeWorkspace: {
      id: "test-workspace-id",
      name: "Test Workspace",
    },
  }),
}));

vi.mock("../../api/metrics", async () => {
  // #1265: catalogue mirrors `se_metrics.registry`; loaded inside the factory
  // because `vi.mock` is hoisted above the fixture import.
  const { buildMetricCatalog: build } = await import("./metric-catalog.fixture");
  return {
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
      catalog: vi.fn().mockResolvedValue(build()),
      values: vi.fn(),
    },
  };
});

vi.mock("../../api/display-preferences", () => ({
  displayPreferencesApi: {
    get: vi.fn(),
    update: vi.fn(),
  },
}));

const CATALOG = buildMetricCatalog();

// Mock i18n provider wrapper (minimal)
const MockWrapper = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);

describe("MetricsDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(metricsApi.catalog).mockResolvedValue(CATALOG);
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({
      show_readable_ids: true,
      visible_metrics: null,
    });
    vi.mocked(displayPreferencesApi.update).mockImplementation(async (changes) => ({
      show_readable_ids: true,
      visible_metrics: changes.visible_metrics ?? null,
    }));
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

      // Initial state: transparent background. Both states assert the inline
      // declaration: jsdom 30.1.3 no longer round-trips the background
      // shorthand (with or without a var()) through getComputedStyle.
      expect(helpBtn.getAttribute("style")).toContain("background: transparent");

      // Click to enable help mode
      fireEvent.click(helpBtn);

      // After click: primary background color. Assert the inline declaration
      // directly: jsdom 30.1.3 no longer round-trips a var() through the
      // background shorthand in getComputedStyle.
      expect(helpBtn.getAttribute("style")).toContain(
        "background: var(--color-primary)"
      );
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

  // ---------------------------------------------------------------------
  // #809/#806: the five tiles must render as children of the single,
  // CSS-Module-owned responsive grid — not into an inline, fixed-column
  // template (which laid the fifth tile out alone on a second row). The
  // column contract itself is asserted in
  // `src/test/responsive-card-grids.test.ts`.
  // ---------------------------------------------------------------------
  describe("KPI grid layout (#809)", () => {
    it("renders all five tiles into one class-based grid container without inline layout", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-tile-coverage");
      const tiles = screen.getAllByTestId(/^metric-tile-/);
      expect(tiles).toHaveLength(5);

      const grid = tiles[0].parentElement;
      expect(grid).not.toBeNull();
      expect(tiles.every((tile) => tile.parentElement === grid)).toBe(true);
      // Layout is owned by MetricsDashboard.module.css (`.tileGrid`), so the
      // container must carry that class and no inline grid template.
      expect(grid!.className).not.toBe("");
      expect(grid!.getAttribute("style")).toBeNull();
    });
  });

  // ---------------------------------------------------------------------
  // Issue #1265: the statistics widgets are catalog-driven and toggled
  // per user; the selection is persisted on the display preference.
  // ---------------------------------------------------------------------
  describe("Configurable statistics widgets (#1265)", () => {
    it("renders one toggle per catalogue entry, including opt-in metrics", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metrics-widget-config");

      for (const entry of CATALOG.metrics) {
        expect(
          screen.getByTestId(`metrics-widget-toggle-${entry.key}`),
        ).toBeInTheDocument();
      }
    });

    it("renders only the default-visible tiles when no explicit selection exists", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-tile-coverage");

      // verification_coverage is registered but opted out of the default set.
      expect(
        screen.queryByTestId("metric-tile-verificationCoverage"),
      ).not.toBeInTheDocument();
      expect(screen.getAllByTestId(/^metric-tile-/)).toHaveLength(5);
    });

    it("renders a tile the user has explicitly enabled", async () => {
      vi.mocked(displayPreferencesApi.get).mockResolvedValue({
        show_readable_ids: true,
        visible_metrics: ["traceability_coverage", "verification_coverage"],
      });

      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-tile-verificationCoverage");
      expect(screen.getAllByTestId(/^metric-tile-/)).toHaveLength(2);
    });

    it("persists a toggle and removes the tile from the grid", async () => {
      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-tile-volatility");

      fireEvent.click(screen.getByTestId("metrics-widget-toggle-volatility"));

      await waitFor(() =>
        expect(displayPreferencesApi.update).toHaveBeenCalledWith({
          visible_metrics: [
            "traceability_coverage",
            "workflow_gaps",
            "open_risks",
            "open_risks_critical",
          ],
        }),
      );
      await waitFor(() =>
        expect(screen.queryByTestId("metric-tile-volatility")).not.toBeInTheDocument(),
      );
    });

    it("rolls back and surfaces an error when the save is rejected", async () => {
      vi.mocked(displayPreferencesApi.update).mockRejectedValue(
        new Error("save failed"),
      );

      render(<MetricsDashboard />, { wrapper: MockWrapper });

      await screen.findByTestId("metric-tile-volatility");
      fireEvent.click(screen.getByTestId("metrics-widget-toggle-volatility"));

      // The tile comes back — the UI never keeps a change the server rejected.
      await waitFor(() =>
        expect(screen.getByTestId("metric-tile-volatility")).toBeInTheDocument(),
      );
    });
  });
});
