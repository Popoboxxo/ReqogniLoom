/**
 * Mobile split-view state machine (plan M5, REQ-209).
 *
 * The regression this guards: one boolean used to mean both "mobile" and
 * "which pane", so opening a detail on a phone rendered the desktop
 * two-column layout, and the tabs were hardcoded English.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SplitView } from "../components/SplitView/SplitView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

describe("SplitView mobile", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
    Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 390 });
  });

  it("shows the list first and replaces it with the detail when a row opens", () => {
    const { rerender } = render(
      <SplitView leftPanel={<div>Liste</div>} rightPanel={null} />
    );
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
    expect(screen.queryByTestId("splitview-back")).toBeNull();

    rerender(
      <SplitView leftPanel={<div>Liste</div>} rightPanel={<div>Detail</div>} />
    );
    expect(screen.getByTestId("splitview-list").style.display).toBe("none");
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
    expect(screen.getByTestId("splitview-back")).toBeTruthy();
  });

  it("keeps both panes mounted and returns to the list without a desktop jump", () => {
    const { rerender } = render(
      <SplitView leftPanel={<div>Liste</div>} rightPanel={<div data-testid="detail-body">Detail</div>} />
    );
    expect(screen.getByTestId("detail-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("splitview-back"));
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    // A parent re-render with a new element identity must not reopen the detail.
    rerender(
      <SplitView leftPanel={<div>Liste</div>} rightPanel={<div data-testid="detail-body">Detail</div>} />
    );
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    // The desktop divider is never part of the mobile branch.
    expect(screen.queryByTestId("splitview-divider")).toBeNull();
  });

  it("uses the translated back label, not a hardcoded English tab", () => {
    render(<SplitView leftPanel={<div>Liste</div>} rightPanel={<div>Detail</div>} />);
    expect(screen.getByTestId("splitview-back").textContent).toContain("Zurück zur Liste");
    expect(screen.queryByText("Detail", { selector: "button" })).toBeNull();
  });

  it("opens the detail when a list row is clicked after going back", () => {
    render(
      <SplitView leftPanel={<div aria-pressed="false">Zeile</div>} rightPanel={<div>Detail</div>} />
    );
    fireEvent.click(screen.getByTestId("splitview-back"));
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    fireEvent.click(screen.getByText("Zeile"));
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
  });

  it("does not switch panes when responsiveMode is off", () => {
    render(<SplitView leftPanel={<div>Liste</div>} rightPanel={<div>Detail</div>} responsiveMode={false} />);
    expect(screen.queryByTestId("splitview-back")).toBeNull();
    expect(screen.getByTestId("splitview-divider")).toBeTruthy();
  });
});
