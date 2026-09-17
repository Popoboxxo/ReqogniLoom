/**
 * Regression test for BUG-10 (SYSTEMAUDIT_2026-08-18 §4, finding 1 of N).
 *
 * The metric tiles' "Show help" card descriptions were rendered directly
 * from the `METRIC_HELP` constant (`helpText={METRIC_HELP[spec.name]}`),
 * bypassing `t()` entirely. The text was always German, even with the UI
 * language set to English.
 *
 * Same technique as `IcdView.i18n.test.tsx` / `DiagramView.i18n.test.tsx`
 * (BUG-06/BUG-07): a *real* i18next instance loaded with the actual locale
 * resources (cf. `frontend/src/test/ProfileSection.test.tsx`), language
 * switched between tests. `MetricsDashboard.test.tsx` mocks `react-i18next`
 * with a fallback-only stub and therefore cannot catch a bypassed-`t()`
 * bug like this one.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../i18n/locales/de.json";
import en from "../../i18n/locales/en.json";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "test-workspace-id", name: "Test Workspace" },
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

import MetricsDashboard from "./MetricsDashboard";

const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    de: { translation: de },
  },
  lng: "de",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

function renderDashboard(): ReturnType<typeof render> {
  return render(
    <I18nextProvider i18n={i18n}>
      <MetricsDashboard />
    </I18nextProvider>,
  );
}

// The five `MetricTileSpec["name"]` values (mirrors MetricsDashboard.tsx's
// `TILES` order). Read the expected text straight from the real locale
// files instead of duplicating literal strings here, so this test can't
// silently drift out of sync with the translations it's supposed to guard.
const METRIC_NAMES = [
  "coverage",
  "volatility",
  "workflowGap",
  "openRisks",
  "openRisksCritical",
] as const;

describe("MetricsDashboard i18n (BUG-10 regression: metric tile help texts)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(METRIC_NAMES)(
    "[BUG-10] shows the German '%s' help text when language is de",
    async (name) => {
      await i18n.changeLanguage("de");
      const user = userEvent.setup();
      renderDashboard();

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      await user.click(helpBtn);

      await waitFor(() => {
        expect(screen.getByTestId(`metric-help-${name}`)).toHaveTextContent(
          de.metrics.help[name],
        );
      });
    },
  );

  it.each(METRIC_NAMES)(
    "[BUG-10] shows the English '%s' help text when language is en",
    async (name) => {
      await i18n.changeLanguage("en");
      const user = userEvent.setup();
      renderDashboard();

      const helpBtn = await screen.findByTestId("metrics-help-toggle-btn");
      await user.click(helpBtn);

      await waitFor(() => {
        expect(screen.getByTestId(`metric-help-${name}`)).toHaveTextContent(
          en.metrics.help[name],
        );
      });
      // The English tile must not still show the German text — the actual
      // regression BUG-10 caused (always-German help text regardless of
      // the active UI language).
      expect(screen.getByTestId(`metric-help-${name}`)).not.toHaveTextContent(
        de.metrics.help[name],
      );
    },
  );
});
