/**
 * Mobile split-view state machine (plan M5, REQ-209).
 *
 * The regression this guards: one boolean used to mean both "mobile" and
 * "which pane", so opening a detail on a phone rendered the desktop
 * two-column layout, and the tabs were hardcoded English. The single concept
 * contract (list/detail/spine) owns the one back step; the state machine now
 * lives in the extracted `useSplitViewMobileState` hook.
 *
 * PR #1888 adds the mobile entry rule: a phone ALWAYS starts in the list pane,
 * even when a deep link / route selection already supplies a detail at mount.
 * Hiding the list at mount made every row invisible to the mobile E2E shards.
 *
 * The former legacy-contract cases (`leftPanel` / `rightPanel` /
 * `responsiveMode`) were removed in UI-001 / S3.2 WP-1 together with the
 * legacy render path.
 */
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SplitView } from "../components/SplitView/SplitView";
import { useSplitViewMobileState } from "../components/SplitView/useSplitViewMobileState";

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

const conceptList = (
  <div role="treeitem" aria-selected={false} data-testid="concept-row">Zeile</div>
);

describe("SplitView mobile — concept contract", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
    Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 390 });
  });

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

  it("uses the translated back label, not a hardcoded English tab", () => {
    render(<SplitView list={conceptList} detail={<div>Detail</div>} />);
    fireEvent.click(screen.getByTestId("concept-row"));
    expect(screen.getByTestId("splitview-back").textContent).toContain("Zurück zur Liste");
  });

  it("keeps the tree-width divider inert in the mobile zone", () => {
    const { container } = render(
      <SplitView list={conceptList} detail={<div data-testid="concept-detail">Detail</div>} />,
    );
    expect(screen.queryByTestId("tree-width-separator")).toBeNull();
    expect(container.querySelector('[role="separator"]')).toBeNull();
    expect(screen.getByTestId("splitview-list")).toHaveStyle({ flex: "1 1 100%" });
  });

  it("does not apply treeWidth to the stacked panes", () => {
    render(
      <SplitView
        list={conceptList}
        detail={<div data-testid="concept-detail">Detail</div>}
        treeWidth={520}
        moduleType="requirements"
      />,
    );
    const list = screen.getByTestId("splitview-list");
    expect(list.style.flex).toBe("1 1 100%");
    expect(list.style.minWidth).toBe("");
    expect(screen.queryByTestId("tree-width-separator")).toBeNull();
  });

  it("keeps the list pane (and its scroll position) mounted across back", () => {
    render(<SplitView list={conceptList} detail={<div data-testid="concept-detail">Detail</div>} />);
    const list = screen.getByTestId("splitview-list");
    list.scrollTop = 123;

    fireEvent.click(screen.getByTestId("concept-row"));
    fireEvent.click(screen.getByTestId("splitview-back"));

    expect(screen.getByTestId("splitview-list")).toBe(list);
    expect(list.scrollTop).toBe(123);
  });
});

describe("useSplitViewMobileState — extracted state machine", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 390 });
  });

  it("reports the mobile zone and only flips the pane on a genuine row action", () => {
    const detail = <div>Detail</div>;
    const { result } = renderHook(() => useSplitViewMobileState(detail));

    expect(result.current.zone).toBe("mobile");
    expect(result.current.mobilePane).toBe("list");
    expect(result.current.isMobileReplace).toBe(false);

    act(() => result.current.goBack());
    expect(result.current.mobilePane).toBe("list");
  });

  it("follows a resize into the desktop zone", () => {
    const { result } = renderHook(() => useSplitViewMobileState(null));
    expect(result.current.zone).toBe("mobile");

    act(() => {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        writable: true,
        value: 1440,
      });
      window.dispatchEvent(new Event("resize"));
    });
    expect(result.current.zone).toBe("desktop");
  });
});
