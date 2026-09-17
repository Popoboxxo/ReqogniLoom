/**
 * Tests for PageHeader (UI concept ch. 12.1, issue #718).
 *
 * Verifies:
 * - exactly one <h1> is always rendered
 * - the h1 uses the standard --font-size-3xl token (not a route-local override)
 * - the (empty) actions row is not rendered at all when no action is given —
 *   regression test for #718: an unconditionally-rendered empty flex item
 *   could wrap onto its own line in a narrow parent, adding dead header
 *   height to routes with no header actions (e.g. AuditDashboard, CsvImport)
 * - the actions row renders when at least one action is given
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageHeader } from "./PageHeader";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

describe("PageHeader (#718)", () => {
  it("renders exactly one h1 at the standard --font-size-3xl token", () => {
    render(<PageHeader title="Requirements" />);
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("Requirements");
    expect(headings[0]).toHaveStyle({ fontSize: "var(--font-size-3xl)" });
  });

  it("renders no actions row when no action is given (#718 regression)", () => {
    render(<PageHeader title="Audit" summary="No findings" />);
    // The header must contain nothing besides the title/summary block —
    // an empty second flex child used to survive in the DOM and could wrap
    // onto its own line, adding ~8px of dead height in narrow layouts.
    const header = screen.getByTestId("page-header");
    expect(header.children).toHaveLength(1);
  });

  it("renders the actions row when a primary action is given", () => {
    render(
      <PageHeader
        title="Requirements"
        primaryAction={{ label: "New requirement", onClick: () => {} }}
      />,
    );
    const header = screen.getByTestId("page-header");
    expect(header.children).toHaveLength(2);
    expect(
      screen.getByTestId("page-header-primary-action"),
    ).toHaveTextContent("New requirement");
  });
});
