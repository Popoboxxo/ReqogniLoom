/**
 * SplitView — accessibility baseline for the single concept contract.
 *
 * The old divider tests (ARIA window-splitter triple, 24px pointer target)
 * belonged to the deleted legacy `leftPanel`/`rightPanel` drag contract and
 * were removed with it in UI-001 / S3.2 WP-1. The concept contract has no
 * draggable separator; its accessibility baseline is instead the mobile
 * list/detail/back flow: a real button, a translated accessible name, focus
 * following the visible pane, and both panes staying mounted.
 *
 * This is a build-time baseline only — the binding WCAG verdict stays with
 * `accessibility-specialist`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SplitView } from "./SplitView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

const ORIGINAL_WIDTH = window.innerWidth;

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 390,
  });
});

afterEach(() => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: ORIGINAL_WIDTH,
  });
});

function renderMobile() {
  return render(
    <SplitView
      list={<div role="treeitem" aria-selected={false} tabIndex={0} data-testid="row">Zeile</div>}
      detail={<div data-testid="detail-body">Detail</div>}
    />
  );
}

describe("SplitView accessibility baseline", () => {
  it("has no draggable separator — the fixed-ratio contract owns no window-splitter role", () => {
    const { container } = renderMobile();
    expect(container.querySelector('[role="separator"]')).toBeNull();
    expect(container.querySelector('[data-testid="splitview-divider"]')).toBeNull();
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
