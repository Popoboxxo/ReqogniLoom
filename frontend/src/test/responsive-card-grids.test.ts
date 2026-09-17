/**
 * Responsive card-grid layout contract (#809, #806).
 *
 * Both grids are pure-CSS layout inside a co-located CSS Module, so — like
 * `ArtifactForm.test.tsx`'s CSS-contract test — this suite asserts the
 * stylesheet's declarations rather than a rendered box (jsdom has no layout
 * engine, so computed track sizes cannot be asserted here; the visual result
 * is covered by the Playwright snapshots instead).
 *
 * Why the column counts are asserted rather than just "is a grid":
 * - The SE-metrics KPI grid holds exactly five tiles. A 4-column template
 *   renders 4+1 and a 2-column one 2+2+1 — in both cases the last tile sits
 *   alone on a short row (#809). Only 1, 3 and 5 divide five evenly, so those
 *   are the only counts the stylesheet may contain.
 * - The dashboard workspace grid holds a variable number of cards, where a
 *   short row is unavoidable; there `auto-fit` + `1fr` is the contract, so a
 *   short list stretches across the row instead of leaving it empty (#806).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(__dirname, "..");

function readSource(relativePath: string): string {
  return readFileSync(join(SRC_DIR, relativePath), "utf-8");
}

const KPI_CSS = "components/MetricsDashboard/MetricsDashboard.module.css";
const KPI_TSX = "components/MetricsDashboard/MetricsDashboard.tsx";
const WORKSPACE_CSS = "components/DashboardViews/DashboardViews.module.css";
const WORKSPACE_TSX = "components/DashboardViews/DashboardViews.tsx";
const TOKENS_CSS = "styles/tokens.css";

describe("SE-metrics KPI grid columns (#809)", () => {
  const css = readSource(KPI_CSS);

  it("never declares a column count that orphans the fifth tile", () => {
    // 4 -> 4+1, 2 -> 2+2+1. Both leave a single tile alone on its own row.
    expect(css).not.toContain("repeat(4,");
    expect(css).not.toContain("repeat(2,");
    expect(css).not.toMatch(/grid-template-columns:\s*repeat\(auto-fit/);
  });

  it("lays five tiles out 1 / 3 / 5 across the documented breakpoints", () => {
    // Mobile: one tile per row, so the base rule has no repeat() at all.
    expect(css).toMatch(/\.tileGrid\s*\{[^}]*grid-template-columns:\s*1fr/);
    // --bp-md (768px): 3+2.
    expect(css).toContain("@media (min-width: 768px)");
    expect(css).toContain("grid-template-columns: repeat(3, minmax(0, 1fr));");
    // --bp-xl (1600px): 5 in one row.
    expect(css).toContain("@media (min-width: 1600px)");
    expect(css).toContain("grid-template-columns: repeat(5, minmax(0, 1fr));");
  });

  it("sizes tracks and gaps through design tokens", () => {
    expect(css).toContain("gap: var(--space-4)");
    // Both @media values must be the documented breakpoint tokens (CSS cannot
    // reference custom properties inside @media, so the literal is the
    // declaration — tokens.css is the single source of truth for it).
    const tokens = readSource(TOKENS_CSS);
    expect(tokens).toContain("--bp-md: 768px;");
    expect(tokens).toContain("--bp-xl: 1600px;");
  });

  it("is wired into the dashboard as a class, not an inline template", () => {
    const tsx = readSource(KPI_TSX);
    expect(tsx).toContain('className={styles.tileGrid}');
    expect(tsx).not.toContain("gridTemplateColumns");
  });
});

describe("dashboard workspace card grid (#806)", () => {
  const css = readSource(WORKSPACE_CSS);

  it("uses auto-fit with 1fr tracks so a short row fills the content width", () => {
    expect(css).toContain(
      "grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));",
    );
    // auto-fill would keep the empty tracks of a partially filled row and
    // re-create the empty-page gap #806 reports.
    expect(css).not.toMatch(/grid-template-columns:\s*[^;]*auto-fill/);
  });

  it("keeps the card grid's closing rule inside the testid the e2e spec masks", () => {
    expect(css).toContain("padding-bottom: var(--space-6)");
    expect(css).toContain("border-bottom: 1px solid var(--color-border)");
    const tsx = readSource(WORKSPACE_TSX);
    expect(tsx).toContain('data-testid="workspace-list" className={styles.workspaceGrid}');
  });
});
