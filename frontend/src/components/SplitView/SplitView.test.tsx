/**
 * SplitView — concept contract tests (UI_KONZEPT.md ch. 12.6)
 *
 * The component has exactly one contract: `list` / `detail` / `ratio` /
 * `minWidths`. The legacy `leftPanel` / `rightPanel` drag-divider contract was
 * removed in UI-001 / S3.2 WP-1 — its tests went with it. The derivation chain
 * slot was removed in Schnitt 2c: each host mounts the always-horizontal chain
 * footer as a sibling of this container instead. Mobile pane behaviour lives
 * in `SplitView.mobile.test.tsx` and the extracted `useSplitViewMobileState`
 * hook.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

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

  it("AC2: renders list and detail as sibling panes inside one container", () => {
    render(
      <SplitView
        list={<div data-testid="the-list">List content</div>}
        detail={<div data-testid="the-detail">Detail content</div>}
      />
    );

    const list = screen.getByTestId("splitview-list");
    const detail = screen.getByTestId("splitview-detail");

    // Both panes share one parent, and neither contains the other.
    expect(detail.parentElement).toBe(list.parentElement);
    expect(list.contains(detail)).toBe(false);
    expect(detail.contains(list)).toBe(false);

    // DOM order stays list, then detail.
    const children = Array.from(list.parentElement!.children);
    expect(children.indexOf(detail)).toBeGreaterThan(children.indexOf(list));
  });

  it("AC2c: keeps the list/detail row on one axis in the narrow zone (no horizontal chain bar)", () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 900, // between fallback --bp-md (768) and --bp-lg (1024)
    });

    try {
      render(
        <SplitView
          list={<div data-testid="the-list">List content</div>}
          detail={<div data-testid="the-detail">Detail content</div>}
        />
      );

      const root = screen.getByTestId("splitview-list").parentElement as HTMLElement;
      expect(root.style.flexDirection).toBe("row");
      // The ratio comes from the caller in every zone — no narrow override.
      expect(screen.getByTestId("splitview-list")).toHaveStyle({ flex: "0 0 40%" });
    } finally {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: originalWidth,
      });
    }
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

  it("#1252: the concept-contract list panel also scrolls on Y only", () => {
    render(
      <SplitView
        list={<div>List</div>}
        detail={<div>Detail</div>}
      />
    );

    const list = screen.getByTestId("splitview-list");
    const computed = window.getComputedStyle(list);
    expect(computed.overflowX).toBe("hidden");
    expect(computed.overflowY).toBe("auto");
  });

  it("UI-001: no drag divider is rendered — the fixed-ratio contract is the only one", () => {
    const { container } = render(
      <SplitView list={<div>List</div>} detail={<div>Detail</div>} />
    );
    expect(container.querySelector('[data-testid="splitview-divider"]')).toBeNull();
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

  it("#1421: position memory finds the aria-pressed row when the detail closes", () => {
    // The current row of a `role="button"` list is marked
    // `aria-pressed="true"` (ArtifactRow since #1421) — `aria-selected` is
    // invalid on buttons. Both conventions are covered by the hook.
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
      const { rerender } = render(
        <SplitView list={list} detail={<div>Detail</div>} />
      );

      // Detail closes (list visible again) -> scroll the current row into view.
      rerender(<SplitView list={list} detail={null} />);

      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect(scrollIntoView.mock.instances[0]).toBe(screen.getByTestId("row-b"));
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("does not follow a new inline detail identity after the user pressed back", () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 390,
    });

    try {
      const row = <div role="treeitem" aria-selected={false} data-testid="row">Zeile</div>;
      const { rerender } = render(<SplitView list={row} detail={<div>Detail</div>} />);
      fireEvent.click(screen.getByTestId("row"));
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
      fireEvent.click(screen.getByTestId("splitview-back"));
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");

      // Parent rerenders with a fresh inline detail element — must stay closed.
      rerender(<SplitView list={row} detail={<div>Detail</div>} />);
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
    } finally {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: originalWidth,
      });
    }
  });
});
