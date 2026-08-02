/**
 * SplitView — concept contract tests (UI_KONZEPT.md ch. 12.6)
 *
 * Covers the acceptance criteria of Task 1.1 (additive `list`/`detail`/
 * `spine`/`ratio`/`minWidths` props). The legacy `leftPanel`/`rightPanel`
 * contract is covered by backward-compatibility smoke tests across the
 * twelve existing call sites (see task-1.1-report.md) plus
 * `src/test/SplitPaneResize.test.tsx`, which exercises an independent mock
 * and is unaffected by this change.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { SplitView } from "./SplitView";

describe("SplitView — concept contract", () => {
  it("AC1: renders the list full-width without a detail container when detail is null", () => {
    render(
      <SplitView
        list={<div data-testid="the-list">List content</div>}
        detail={null}
      />
    );

    expect(screen.getByTestId("the-list")).toBeInTheDocument();
    expect(screen.queryByTestId("splitview-detail")).not.toBeInTheDocument();

    const listContainer = screen.getByTestId("splitview-list");
    const computed = window.getComputedStyle(listContainer);
    // No width constraint — the list runs the full available width.
    expect(computed.maxWidth).toBe("100%");
    expect(listContainer).not.toHaveStyle({ minWidth: "380px" });
  });

  it("AC2: mounts the spine between list and detail, independent of detail's scroll container", () => {
    render(
      <SplitView
        list={<div data-testid="the-list">List content</div>}
        detail={<div data-testid="the-detail">Detail content</div>}
        spine={<div data-testid="the-spine">Spine content</div>}
      />
    );

    const list = screen.getByTestId("splitview-list");
    const spine = screen.getByTestId("splitview-spine");
    const detail = screen.getByTestId("splitview-detail");

    // Spine is a sibling of list/detail, not nested inside the detail
    // scroll container — so scrolling detail cannot move it.
    expect(spine.parentElement).toBe(detail.parentElement);
    expect(spine.contains(detail)).toBe(false);
    expect(detail.contains(spine)).toBe(false);

    // DOM order: list, spine, detail (spine sits between the two panes).
    const container = list.parentElement as HTMLElement;
    const children = Array.from(container.children);
    expect(children.indexOf(spine)).toBeGreaterThan(children.indexOf(list));
    expect(children.indexOf(detail)).toBeGreaterThan(children.indexOf(spine));
  });

  it("AC2b: omits the spine slot entirely when no spine prop is passed", () => {
    render(
      <SplitView
        list={<div>List</div>}
        detail={<div>Detail</div>}
      />
    );

    expect(screen.queryByTestId("splitview-spine")).not.toBeInTheDocument();
  });

  it("AC3: both scroll surfaces carry overscroll-behavior: contain and scrollbar-gutter: stable", () => {
    render(
      <SplitView
        list={<div>List</div>}
        detail={<div>Detail</div>}
      />
    );

    const list = screen.getByTestId("splitview-list");
    const detail = screen.getByTestId("splitview-detail");

    for (const surface of [list, detail]) {
      const computed = window.getComputedStyle(surface);
      expect(computed.overscrollBehavior).toBe("contain");
      expect(computed.scrollbarGutter).toBe("stable");
    }
  });

  it("AC3b: legacy contract scroll surfaces also carry the shared scroll model", () => {
    render(
      <SplitView
        leftPanel={<div>Left</div>}
        rightPanel={<div>Right</div>}
        responsiveMode={false}
      />
    );

    const divider = screen.getByTestId("splitview-divider");
    const left = divider.previousElementSibling as HTMLElement;
    const right = divider.nextElementSibling as HTMLElement;

    for (const surface of [left, right]) {
      const computed = window.getComputedStyle(surface);
      expect(computed.overscrollBehavior).toBe("contain");
      expect(computed.scrollbarGutter).toBe("stable");
    }
  });

  it("applies the configured ratio and minWidths to list/detail when both are present", () => {
    render(
      <SplitView
        list={<div>List</div>}
        detail={<div>Detail</div>}
        ratio={[30, 70]}
        minWidths={[300, 400]}
      />
    );

    const list = screen.getByTestId("splitview-list");
    const detail = screen.getByTestId("splitview-detail");

    expect(list).toHaveStyle({ flex: "0 0 30%", minWidth: "300px" });
    expect(detail).toHaveStyle({ minWidth: "400px" });
  });

  it("renders both leftPanel and rightPanel unchanged when list is not passed (legacy contract)", () => {
    render(
      <SplitView
        leftPanel={<div data-testid="legacy-left">Left</div>}
        rightPanel={<div data-testid="legacy-right">Right</div>}
        responsiveMode={false}
      />
    );

    expect(screen.getByTestId("legacy-left")).toBeInTheDocument();
    expect(screen.getByTestId("legacy-right")).toBeInTheDocument();
    expect(screen.getByTestId("splitview-divider")).toBeInTheDocument();
    expect(screen.queryByTestId("splitview-list")).not.toBeInTheDocument();
  });
});
