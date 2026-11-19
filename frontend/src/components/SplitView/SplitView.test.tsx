/**
 * SplitView — concept contract + per-module tree-width divider
 * (UI_KONZEPT.md ch. 12.6, ADR-030).
 *
 * One contract: `list` / `detail` / `ratio` / `minWidths` plus the optional
 * `moduleType` / `treeWidth` / `onTreeWidthChange` / `defaultTreeWidth` seam.
 * `ratio` is now the INITIAL width only, `minWidths` are the CLAMP bounds and
 * the divider is the authoritative width once the user has resized it.
 * The legacy `leftPanel` / `rightPanel` contract and the `spine` slot are gone;
 * mobile pane behaviour lives in `useSplitViewMobileState` and is covered in
 * `SplitView.mobile.test.tsx`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SplitView, type SplitViewProps } from "./SplitView";

const ORIGINAL_WIDTH = window.innerWidth;

/** Runtime content width for the `effMax` clamp (ADR-030), held constant. */
const CONTENT_WIDTH = 1200;
/** `min(0.7 * 1200, 1200 - 520 - 24)` = `min(840, 656)` = 656. */
const EFF_MAX = 656;
/** `0.4 * 1200` = 480 — the default `[40, 60]` ratio initial value. */
const RATIO_INITIAL = 480;

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

function renderSplit(props: Partial<SplitViewProps> = {}) {
  return render(
    <SplitView
      list={<div data-testid="the-list">List content</div>}
      detail={<div data-testid="the-detail">Detail content</div>}
      {...props}
    />,
  );
}

describe("SplitView — concept contract", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 1440,
    });
    stubContentWidth(CONTENT_WIDTH);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: ORIGINAL_WIDTH,
    });
  });

  it("AC1: renders the list full-width without a detail container or divider when detail is null", () => {
    render(<SplitView list={<div data-testid="the-list">List content</div>} detail={null} />);

    expect(screen.getByTestId("the-list")).toBeInTheDocument();
    expect(screen.queryByTestId("splitview-detail")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tree-width-separator")).not.toBeInTheDocument();

    const listContainer = screen.getByTestId("splitview-list");
    const computed = window.getComputedStyle(listContainer);
    expect(computed.maxWidth).toBe("100%");
    expect(listContainer).not.toHaveStyle({ minWidth: "380px" });
  });

  it("AC2: renders list, separator and detail as siblings inside one container", () => {
    renderSplit();

    const list = screen.getByTestId("splitview-list");
    const separator = screen.getByTestId("tree-width-separator");
    const detail = screen.getByTestId("splitview-detail");

    expect(separator.parentElement).toBe(list.parentElement);
    expect(detail.parentElement).toBe(list.parentElement);
    expect(list.contains(detail)).toBe(false);
    expect(detail.contains(list)).toBe(false);

    const children = Array.from(list.parentElement!.children);
    expect(children.indexOf(separator)).toBeGreaterThan(children.indexOf(list));
    expect(children.indexOf(detail)).toBeGreaterThan(children.indexOf(separator));
  });

  it("AC2c: keeps list/separator/detail on one axis in the narrow zone (no horizontal chain bar)", () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 900,
    });

    renderSplit();

    const root = screen.getByTestId("splitview-list").parentElement as HTMLElement;
    expect(root.style.flexDirection).toBe("row");
    // The authoritative px width comes from the ratio initial value — no narrow override.
    expect(screen.getByTestId("splitview-list")).toHaveStyle({ flex: "0 0 480px" });
  });

  it("AC3: both scroll surfaces carry overscroll-behavior: contain and scrollbar-gutter: stable", () => {
    renderSplit();

    for (const testId of ["splitview-list", "splitview-detail"]) {
      const computed = window.getComputedStyle(screen.getByTestId(testId));
      expect(computed.overscrollBehavior).toBe("contain");
      expect(computed.scrollbarGutter).toBe("stable");
    }
  });

  it("#1252: the concept-contract list panel scrolls on Y only", () => {
    renderSplit();
    const computed = window.getComputedStyle(screen.getByTestId("splitview-list"));
    expect(computed.overflowX).toBe("hidden");
    expect(computed.overflowY).toBe("auto");
  });

  it("exposes an accessible divider contract (ADR-030)", () => {
    renderSplit();

    const separator = screen.getByTestId("tree-width-separator");
    expect(separator).toHaveAttribute("role", "separator");
    expect(separator).toHaveAttribute("tabindex", "0");
    expect(separator).toHaveAttribute("aria-label");
    expect(separator.getAttribute("aria-valuemin")).toBe("380");
    expect(separator.getAttribute("aria-valuemax")).toBe(String(EFF_MAX));
    expect(separator.getAttribute("aria-valuenow")).toBe(String(RATIO_INITIAL));
    // 24x24 px hit target (ADR-030) while the visible hairline spans the row.
    expect(separator).toHaveStyle({ width: "24px", minHeight: "24px" });
  });

  it("moves the tree width by +/-16 px and +/-64 px with Shift", () => {
    renderSplit();
    const separator = screen.getByTestId("tree-width-separator");

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator.getAttribute("aria-valuenow")).toBe("496");
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(separator.getAttribute("aria-valuenow")).toBe("480");

    fireEvent.keyDown(separator, { key: "ArrowLeft", shiftKey: true });
    expect(separator.getAttribute("aria-valuenow")).toBe("416");
    fireEvent.keyDown(separator, { key: "ArrowRight", shiftKey: true });
    expect(separator.getAttribute("aria-valuenow")).toBe("480");
  });

  it("clamps Home to minWidths[0] (380) and End to the measured effMax (656)", () => {
    renderSplit();
    const separator = screen.getByTestId("tree-width-separator");

    fireEvent.keyDown(separator, { key: "Home" });
    expect(separator.getAttribute("aria-valuenow")).toBe("380");
    expect(screen.getByTestId("splitview-list")).toHaveStyle({ flex: "0 0 380px" });

    fireEvent.keyDown(separator, { key: "End" });
    expect(separator.getAttribute("aria-valuenow")).toBe(String(EFF_MAX));
    expect(screen.getByTestId("splitview-list")).toHaveStyle({ flex: `0 0 ${EFF_MAX}px` });
  });

  it("never lets repeated arrow presses cross the clamp bounds", () => {
    renderSplit();
    const separator = screen.getByTestId("tree-width-separator");

    for (let i = 0; i < 30; i += 1) {
      fireEvent.keyDown(separator, { key: "ArrowRight", shiftKey: true });
    }
    expect(separator.getAttribute("aria-valuenow")).toBe(String(EFF_MAX));

    for (let i = 0; i < 30; i += 1) {
      fireEvent.keyDown(separator, { key: "ArrowLeft", shiftKey: true });
    }
    expect(separator.getAttribute("aria-valuenow")).toBe("380");
  });

  it("Enter and double-click reset to the module default", () => {
    renderSplit({ moduleType: "requirements" });
    const separator = screen.getByTestId("tree-width-separator");

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator.getAttribute("aria-valuenow")).toBe("496");
    fireEvent.keyDown(separator, { key: "Enter" });
    expect(separator.getAttribute("aria-valuenow")).toBe("424");

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator.getAttribute("aria-valuenow")).toBe("440");
    fireEvent.doubleClick(separator);
    expect(separator.getAttribute("aria-valuenow")).toBe("424");
  });

  it("treats ratio as the initial value and minWidths as clamp bounds", () => {
    renderSplit({ ratio: [10, 90], minWidths: [420, 500] });
    const separator = screen.getByTestId("tree-width-separator");

    // 10% of 1200 = 120, below the 420 lower clamp — clamp wins.
    expect(separator.getAttribute("aria-valuenow")).toBe("420");
    expect(separator.getAttribute("aria-valuemin")).toBe("420");
    // min(840, 1200 - 500 - 24) = 676
    expect(separator.getAttribute("aria-valuemax")).toBe("676");
    expect(screen.getByTestId("splitview-list")).toHaveStyle({
      flex: "0 0 420px",
      minWidth: "420px",
    });
    expect(screen.getByTestId("splitview-detail")).toHaveStyle({ minWidth: "500px" });
  });

  it("exposes the controlled treeWidth / onTreeWidthChange seam for Task 9", () => {
    const onTreeWidthChange = vi.fn();
    renderSplit({ treeWidth: 500, onTreeWidthChange });
    const separator = screen.getByTestId("tree-width-separator");

    expect(separator.getAttribute("aria-valuenow")).toBe("500");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(onTreeWidthChange).toHaveBeenCalledWith(516);
    // Controlled: the parent owns the value, so it stays put until re-rendered.
    expect(separator.getAttribute("aria-valuenow")).toBe("500");
  });

  it("keeps the splitview-* E2E testids byte-identical and contains no spine slot", () => {
    renderSplit();

    expect(screen.getByTestId("splitview-list")).toBeInTheDocument();
    expect(screen.getByTestId("splitview-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("splitview-back")).toBeNull();
    expect(screen.queryByTestId("splitview-spine")).toBeNull();
    expect(readFileSync(join(__dirname, "SplitView.tsx"), "utf-8")).not.toContain(
      "splitview-spine",
    );
  });

  it("#1421: position memory finds the aria-pressed row when the detail closes", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      writable: true,
      value: scrollIntoView,
    });

    try {
      const list = (
        <div>
          <div role="button" aria-pressed="false" data-testid="row-a">A</div>
          <div role="button" aria-pressed="true" data-testid="row-b">B</div>
        </div>
      );
      const { rerender } = render(<SplitView list={list} detail={<div>Detail</div>} />);
      rerender(<SplitView list={list} detail={null} />);

      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect(scrollIntoView.mock.instances[0]).toBe(screen.getByTestId("row-b"));
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("does not follow a new inline detail identity after the user pressed back", () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 390,
    });

    try {
      const row = <div role="treeitem" aria-selected={false} data-testid="row">Zeile</div>;
      const { rerender } = render(<SplitView list={row} detail={<div>Detail</div>} />);
      fireEvent.click(screen.getByTestId("row"));
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
      fireEvent.click(screen.getByTestId("splitview-back"));
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");

      rerender(<SplitView list={row} detail={<div>Detail</div>} />);
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
    } finally {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        writable: true,
        value: ORIGINAL_WIDTH,
      });
    }
  });
});
