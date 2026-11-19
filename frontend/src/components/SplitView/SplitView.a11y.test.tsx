/**
 * SplitView — accessibility baseline for the single concept contract + the
 * ADR-030 tree-width separator (WAI-ARIA APG window-splitter pattern).
 *
 * The divider is a `role="separator"` with the full value triple and a real
 * tab stop on desktop. It is inert in the mobile zone (not rendered at all:
 * no tab stop, no `aria-valuenow`) because the panes are stacked there.
 * The mobile list/detail/back flow stays the other half of this baseline.
 *
 * This is a build-time baseline only — the binding WCAG verdict stays with
 * `accessibility-specialist`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SplitView } from "./SplitView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

const ORIGINAL_WIDTH = window.innerWidth;

function setWidth(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function stubContentWidth(width: number): void {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    width,
    height: 800,
    top: 0,
    left: 0,
    right: width,
    bottom: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

function renderMobile() {
  return render(
    <SplitView
      list={<div role="treeitem" aria-selected={false} tabIndex={0} data-testid="row">Zeile</div>}
      detail={<div data-testid="detail-body">Detail</div>}
    />,
  );
}

function renderDesktop(moduleType?: string) {
  return render(
    <SplitView
      list={<div data-testid="list-body">List</div>}
      detail={<div data-testid="detail-body">Detail</div>}
      moduleType={moduleType}
    />,
  );
}

describe("SplitView accessibility baseline — mobile zone", () => {
  beforeEach(() => setWidth(390));
  afterEach(() => {
    vi.restoreAllMocks();
    setWidth(ORIGINAL_WIDTH);
  });

  it("the tree-width divider is inert: no tab stop and no aria-valuenow in the stacked zone", () => {
    const { container } = renderMobile();
    expect(screen.queryByTestId("tree-width-separator")).toBeNull();
    expect(container.querySelector('[role="separator"]')).toBeNull();
  });

  it("exposes the back step as a real button with a type and an accessible name", () => {
    renderMobile();
    fireEvent.click(screen.getByTestId("row"));

    const back = screen.getByTestId("splitview-back");
    expect(back.tagName).toBe("BUTTON");
    expect(back).toHaveAttribute("type", "button");
    expect(back.textContent?.trim()).not.toBe("");
  });

  it("moves focus to the back button and restores it to the originating row", () => {
    renderMobile();
    const row = screen.getByTestId("row");
    fireEvent.click(row);
    expect(document.activeElement?.getAttribute("data-testid")).toBe("splitview-back");

    fireEvent.click(screen.getByTestId("splitview-back"));
    expect(document.activeElement?.getAttribute("data-testid")).toBe("row");
  });

  it("keeps both panes mounted while the detail visually replaces the list", () => {
    renderMobile();
    fireEvent.click(screen.getByTestId("row"));

    expect(screen.getByTestId("splitview-list")).toBeInTheDocument();
    expect(screen.getByTestId("splitview-detail")).toBeInTheDocument();
    expect(screen.getByTestId("splitview-list").style.display).toBe("none");
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
  });
});

describe("SplitView accessibility baseline — tree-width separator (ADR-030)", () => {
  beforeEach(() => {
    setWidth(1440);
    stubContentWidth(1200);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setWidth(ORIGINAL_WIDTH);
  });

  it("exposes role, tabindex and the full aria value triple", () => {
    renderDesktop();
    const separator = screen.getByTestId("tree-width-separator");

    expect(separator).toHaveAttribute("role", "separator");
    expect(separator).toHaveAttribute("tabindex", "0");
    expect(separator.getAttribute("aria-valuemin")).toBe("380");
    expect(separator.getAttribute("aria-valuemax")).toBe("656");
    expect(separator.getAttribute("aria-valuenow")).toBe("480");
    expect(separator.getAttribute("aria-label")?.trim()).not.toBe("");
  });

  it("offers a 24x24 px pointer target", () => {
    renderDesktop();
    const separator = screen.getByTestId("tree-width-separator");
    expect(separator).toHaveStyle({ width: "24px", minHeight: "24px" });
  });

  it("supports APG-style keyboard resizing: arrows, Shift, Home and End", () => {
    renderDesktop();
    const separator = screen.getByTestId("tree-width-separator");

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator.getAttribute("aria-valuenow")).toBe("496");
    fireEvent.keyDown(separator, { key: "ArrowLeft", shiftKey: true });
    expect(separator.getAttribute("aria-valuenow")).toBe("432");
    fireEvent.keyDown(separator, { key: "Home" });
    expect(separator.getAttribute("aria-valuenow")).toBe("380");
    fireEvent.keyDown(separator, { key: "End" });
    expect(separator.getAttribute("aria-valuenow")).toBe("656");
  });

  it("Enter and double-click reset to the module default (424px for requirements)", () => {
    renderDesktop("requirements");
    const separator = screen.getByTestId("tree-width-separator");

    fireEvent.keyDown(separator, { key: "End" });
    expect(separator.getAttribute("aria-valuenow")).toBe("656");
    fireEvent.keyDown(separator, { key: "Enter" });
    expect(separator.getAttribute("aria-valuenow")).toBe("424");

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    fireEvent.doubleClick(separator);
    expect(separator.getAttribute("aria-valuenow")).toBe("424");
  });

  it("respects prefers-reduced-motion via the stylesheet contract", () => {
    const scss = readFileSync(join(__dirname, "SplitView.module.scss"), "utf-8");
    const reduced = scss.slice(scss.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduced).toMatch(/\.divider/);
    expect(reduced).toMatch(/transition:\s*none|transition-duration:\s*0/);
  });

  it("keeps every splitview-* testid byte-identical and has zero spine occurrences", () => {
    renderDesktop();
    expect(screen.getByTestId("splitview-list")).toBeInTheDocument();
    expect(screen.getByTestId("splitview-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("splitview-back")).toBeNull();
    expect(screen.queryByTestId("splitview-spine")).toBeNull();

    const src = readFileSync(join(__dirname, "SplitView.tsx"), "utf-8");
    expect(src).not.toContain("splitview-spine");
    expect(src.toLowerCase()).not.toContain("spine");
  });
});
