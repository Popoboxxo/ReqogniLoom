/**
 * Mobile split-view state machine (plan M5, REQ-209).
 *
 * The regression this guards: one boolean used to mean both "mobile" and
 * "which pane", so opening a detail on a phone rendered the desktop
 * two-column layout, and the tabs were hardcoded English. The concept
 * contract (list/detail/spine) gets the same single back step as the legacy
 * branch — without it, six artifact routes had no mobile return path.
 *
 * PR #1888 adds the mobile entry rule: a phone ALWAYS starts in the list pane,
 * even when a deep link / route selection already supplies a detail at mount.
 * Hiding the list at mount made every row invisible to the mobile E2E shards.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SplitView } from "../components/SplitView/SplitView";

// A tiny realistic dictionary: the production `fallbackLng` is `en`, so the
// German label must come from the key, not from a hardcoded t() fallback.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => {
      const labels: Record<string, string> = {
        "splitView.back": "Zurück zur Liste",
      };
      return labels[key] ?? fallback ?? key;
    },
  }),
}));

describe("SplitView mobile", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
    Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 390 });
  });

  it("starts in the list pane with a detail already provided, and opens the detail on a row click", () => {
    render(
      <SplitView
        leftPanel={<div aria-pressed="false" data-testid="legacy-row">Zeile</div>}
        rightPanel={<div>Detail</div>}
      />
    );
    // Deep link / route-selected artifact must not hide the list on mount.
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
    expect(screen.queryByTestId("splitview-back")).toBeNull();

    fireEvent.click(screen.getByTestId("legacy-row"));
    expect(screen.getByTestId("splitview-list").style.display).toBe("none");
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
    expect(screen.getByTestId("splitview-back")).toBeTruthy();
  });

  it("keeps both panes mounted and returns to the list without a desktop jump", () => {
    const { rerender } = render(
      <SplitView
        leftPanel={<div aria-pressed="false" data-testid="legacy-row">Zeile</div>}
        rightPanel={<div data-testid="detail-body">Detail</div>}
      />
    );
    expect(screen.getByTestId("detail-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("legacy-row"));
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
    fireEvent.click(screen.getByTestId("splitview-back"));
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    // A parent re-render with a new element identity must not reopen the detail.
    rerender(
      <SplitView
        leftPanel={<div aria-pressed="false" data-testid="legacy-row">Zeile</div>}
        rightPanel={<div data-testid="detail-body">Detail</div>}
      />
    );
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    // The desktop divider is never part of the mobile branch.
    expect(screen.queryByTestId("splitview-divider")).toBeNull();
  });

  it("uses the translated back label, not a hardcoded English tab", () => {
    render(
      <SplitView
        leftPanel={<div aria-pressed="false" data-testid="legacy-row">Zeile</div>}
        rightPanel={<div>Detail</div>}
      />
    );
    fireEvent.click(screen.getByTestId("legacy-row"));
    expect(screen.getByTestId("splitview-back").textContent).toContain("Zurück zur Liste");
    expect(screen.queryByText("Detail", { selector: "button" })).toBeNull();
  });

  it("opens the detail when a list row is clicked", () => {
    render(
      <SplitView leftPanel={<div aria-pressed="false">Zeile</div>} rightPanel={<div>Detail</div>} />
    );
    expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    fireEvent.click(screen.getByText("Zeile"));
    expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
  });

  it("does not switch panes when responsiveMode is off", () => {
    render(<SplitView leftPanel={<div>Liste</div>} rightPanel={<div>Detail</div>} responsiveMode={false} />);
    expect(screen.queryByTestId("splitview-back")).toBeNull();
    expect(screen.getByTestId("splitview-divider")).toBeTruthy();
  });

  it("moves focus to the back control and restores it to the originating row", () => {
    render(
      <SplitView
        leftPanel={<div aria-pressed="false" tabIndex={0} data-testid="focus-row">Zeile</div>}
        rightPanel={<div>Detail</div>}
      />
    );
    fireEvent.click(screen.getByTestId("focus-row"));
    expect(document.activeElement?.getAttribute("data-testid")).toBe("splitview-back");
    fireEvent.click(screen.getByTestId("splitview-back"));
    expect(document.activeElement?.getAttribute("data-testid")).toBe("focus-row");
  });

  describe("concept contract (list/detail/spine)", () => {
    const conceptList = (
      <div role="treeitem" aria-selected={false} data-testid="concept-row">Zeile</div>
    );

    it("starts in the list pane with a detail provided, and offers a back step after a row click", () => {
      render(<SplitView list={conceptList} detail={<div data-testid="concept-detail">Detail</div>} />);
      expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
      expect(screen.queryByTestId("splitview-back")).toBeNull();

      fireEvent.click(screen.getByTestId("concept-row"));
      expect(screen.getByTestId("splitview-back")).toBeTruthy();
      expect(screen.getByTestId("splitview-list").style.display).toBe("none");
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");

      fireEvent.click(screen.getByTestId("splitview-back"));
      expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
      expect(screen.queryByTestId("splitview-back")).toBeNull();
    });

    it("reopens the detail when a row is clicked after going back", () => {
      render(<SplitView list={conceptList} detail={<div data-testid="concept-detail">Detail</div>} />);
      fireEvent.click(screen.getByTestId("concept-row"));
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
      fireEvent.click(screen.getByTestId("splitview-back"));
      expect(screen.getByTestId("splitview-detail").style.display).toBe("none");
      fireEvent.click(screen.getByTestId("concept-row"));
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
      expect(screen.getByTestId("splitview-back")).toBeTruthy();
    });

    it("never opens the detail from a toolbar/view-toggle control", () => {
      render(
        <SplitView
          list={
            <>
              <button type="button" aria-pressed={false} data-testid="fake-toggle">List</button>
              {conceptList}
            </>
          }
          detail={<div data-testid="concept-detail">Detail</div>}
        />
      );
      fireEvent.click(screen.getByTestId("fake-toggle"));
      expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
      fireEvent.click(screen.getByTestId("concept-row"));
      expect(screen.getByTestId("splitview-detail").style.display).not.toBe("none");
    });

    it("has no back affordance at desktop width", () => {
      Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1440 });
      render(<SplitView list={conceptList} detail={<div>Detail</div>} />);
      expect(screen.queryByTestId("splitview-back")).toBeNull();
      expect(screen.getByTestId("splitview-list").style.display).not.toBe("none");
    });
  });
});
