/**
 * #1406 — SplitView divider: pointer target and separator semantics.
 *
 * WCAG 2.2 SC 2.5.8 (Target Size, Minimum) requires a pointer target of at
 * least 24×24 CSS px. The divider used to advertise a 12px box in its comment
 * while the rendered element already grew to 24px; this test pins the real
 * geometry so a future "make it look thinner" edit cannot shrink the target
 * again. It also pins the ARIA window-splitter triple: a separator with
 * `aria-valuenow`/`aria-valuemin`/`aria-valuemax` is announced as an
 * adjustable control; with only two of the three, assistive technology cannot
 * describe the range.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import React from "react";

import { SplitView } from "./SplitView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

function renderLegacy(leftMaxWidthPercent?: number) {
  return render(
    <SplitView
      leftPanel={<div data-testid="left">List</div>}
      rightPanel={<div data-testid="right">Detail</div>}
      leftMaxWidthPercent={leftMaxWidthPercent}
    />,
  );
}

describe("SplitView divider accessibility (#1406)", () => {
  it("is a vertical separator with a >= 24px pointer target", () => {
    renderLegacy();

    const divider = screen.getByTestId("splitview-divider");
    expect(divider).toHaveAttribute("role", "separator");
    expect(divider).toHaveAttribute("aria-orientation", "vertical");

    // `flex: 0 0 24px` is the hit area; the visible line stays 2px because the
    // gradient only paints the middle band.
    const basis = divider.style.flexBasis || divider.style.flex;
    expect(basis).toBe("24px");
    expect(divider.style.background).toContain("linear-gradient");
  });

  it("announces the full adjustment range", () => {
    renderLegacy(60);

    const divider = screen.getByTestId("splitview-divider");
    const now = Number(divider.getAttribute("aria-valuenow"));
    const min = Number(divider.getAttribute("aria-valuemin"));
    const max = Number(divider.getAttribute("aria-valuemax"));

    expect(Number.isFinite(now)).toBe(true);
    expect(Number.isFinite(min)).toBe(true);
    expect(Number.isFinite(max)).toBe(true);
    expect(min).toBeLessThan(max);
    expect(now).toBeGreaterThanOrEqual(min);
    expect(now).toBeLessThanOrEqual(max);
  });

  it("is keyboard reachable", () => {
    renderLegacy();

    const divider = screen.getByTestId("splitview-divider");
    expect(divider).toHaveAttribute("tabindex", "0");
  });
});
