/**
 * InspectorShell — the tabbed shell of #1762 (M1).
 *
 * Covers the acceptance criteria that are structural rather than
 * announcement-specific:
 *
 *  - four tabs for a requirement, three when the Artifact UUID is missing
 *    (M1-7) or for `mainGoal` (spec §3),
 *  - the id contract `inspector-tab-<key>` ↔ `inspector-panel-<key>` (spec §7),
 *  - the rail as the collapsed form of the same node, with four named
 *    counter buttons whose accessible name never reads the `V/D/L/K` glyph
 *    (M1-3),
 *  - the Links tab's one summary line and its jump into the spine (M1-9),
 *  - `?inspector=` as the reproducible deep link, without navigation (M1-4),
 *  - heading levels and landmarks (M1-10).
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InspectorShell } from "./InspectorShell";
import type { InspectorTabKey } from "./inspectorContract";
import * as requirementsModule from "../../../api/requirements";
import * as commentsModule from "../../../api/comments";
import * as tracelinksModule from "../../../api/tracelinks";

vi.mock("../../../api/requirements");
vi.mock("../../../api/comments");
vi.mock("../../../api/tracelinks");
vi.mock("../../../api/architecture");
vi.mock("../../../api/main-goal");
vi.mock("../../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));
vi.mock("../../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [{ key: "verifies", definition: { label: {}, allowed_pairs: [] } }],
    isLoading: false,
    error: null,
    labelFor: (key: string) => key,
  }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        let text = String((second as { defaultValue: unknown }).defaultValue);
        for (const [name, value] of Object.entries(second)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      return key;
    },
  }),
}));

const CURRENT_VERSION = { version: 3, label: "v3", createdAt: null, baselineIds: [] };

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function renderShell(
  props: Partial<React.ComponentProps<typeof InspectorShell>> = {},
): ReturnType<typeof render> {
  return render(
    <InspectorShell
      kind="requirement"
      entityId="req-entity-1"
      artifactPk="artifact-1"
      currentVersion={CURRENT_VERSION}
      {...props}
    />,
  );
}

function activeTab(): HTMLElement | null {
  return document.activeElement instanceof HTMLElement ? document.activeElement : null;
}

describe("InspectorShell (#1762 M1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, "", "/requirements/req-entity-1");
    setViewport(1440);
    vi.mocked(requirementsModule.requirementsApi.versions).mockResolvedValue([]);
    vi.mocked(requirementsModule.requirementsApi.diff).mockResolvedValue({
      from_version: 0,
      to_version: 1,
      changes: [],
    } as never);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  afterEach(() => {
    setViewport(1024);
  });

  it("renders four tabs with the id contract and exactly one tabpanel", async () => {
    renderShell();

    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.id)).toEqual([
      "inspector-tab-version",
      "inspector-tab-diff",
      "inspector-tab-links",
      "inspector-tab-comments",
    ]);

    const selected = screen.getByRole("tab", { selected: true });
    expect(selected).toHaveAttribute("aria-controls", "inspector-panel-version");

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("id", "inspector-panel-version");
    expect(panel).toHaveAttribute("aria-labelledby", "inspector-tab-version");
    expect(panel).toHaveAttribute("tabindex", "0");

    // Only the active panel is mounted (its siblings exist but are empty and
    // hidden) — that is what keeps "one activation, one fetch" true.
    expect(screen.getByTestId("inspector-panel-diff")).toHaveAttribute("hidden");
    expect(screen.queryByTestId("artifact-diff-stub")).not.toBeInTheDocument();
  });

  it("labels the aside through its heading and does not add role=complementary (M1-10)", async () => {
    renderShell();

    const aside = screen.getByTestId("inspector-shell");
    expect(aside.tagName).toBe("ASIDE");
    expect(aside).toHaveAttribute("aria-labelledby", "inspector-heading");
    expect(document.getElementById("inspector-heading")).not.toBeNull();
    // Spec §7: `<aside>` already *is* the complementary landmark; an explicit
    // `role` attribute would only repeat it. What must not happen is a second
    // labelled landmark of the same kind.
    expect(aside).not.toHaveAttribute("role");
    expect(screen.getAllByRole("complementary")).toHaveLength(1);
  });

  it("uses h2 for the surface and h3 for area headings, never h4/h5 (M1-10)", async () => {
    renderShell();

    const headings = screen
      .getByTestId("inspector-shell")
      .querySelectorAll("h1, h2, h3, h4, h5, h6");
    const levels = [...headings].map((heading) => Number(heading.tagName.slice(1)));
    expect(levels).toContain(2);
    expect(levels.every((level) => level <= 3)).toBe(true);
  });

  it("omits the comments tab when artifactPk is null — no tab, no request, no banner (M1-7)", async () => {
    renderShell({ artifactPk: null });

    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.queryByTestId("inspector-tab-comments")).not.toBeInTheDocument();
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();
    expect(screen.queryByTestId("comment-panel-error")).not.toBeInTheDocument();
  });

  it("fetches comments exactly once with the Artifact UUID when the tab is activated (M1-7)", async () => {
    renderShell();

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));

    await waitFor(() => {
      expect(commentsModule.commentsApi.list).toHaveBeenCalledTimes(1);
    });
    expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("artifact-1");
    expect(screen.getByTestId("inspector-panel-comments")).toBeInTheDocument();
  });

  it("writes ?inspector= without navigating and keeps the pathname (M1-4)", async () => {
    renderShell();
    const before = window.location.pathname;

    fireEvent.click(screen.getByTestId("inspector-tab-links"));

    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get("inspector")).toBe("links");
    });
    expect(window.location.pathname).toBe(before);
    expect(sessionStorage.getItem("reqflow_inspector_tab_requirement_req-entity-1")).toBe(
      "links",
    );
  });

  it("restores the tab from ?inspector= on mount", async () => {
    window.history.replaceState({}, "", "/requirements/req-entity-1?inspector=comments");
    renderShell();

    expect(screen.getByTestId("inspector-panel-comments")).toBeInTheDocument();
  });

  it("collapses into the rail: four named counters, glyph hidden from the name (M1-3)", async () => {
    renderShell();

    fireEvent.click(screen.getByTestId("inspector-close"));

    const rail = await screen.findByTestId("inspector-rail");
    expect(rail).toBeInTheDocument();
    // Rail and sheet are ONE node: the panel content (and its tablist) is gone.
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();

    for (const key of ["version", "diff", "links", "comments"] as const) {
      const counter = screen.getByTestId(`inspector-rail-count-${key}`);
      expect(counter.tagName).toBe("BUTTON");
      const name = counter.getAttribute("aria-label") ?? "";
      expect(name.length).toBeGreaterThan(0);
      expect(name).not.toMatch(/^[VDLK]\b/);
      expect(counter).toHaveAttribute("aria-controls", "inspector-surface");
    }

    // Focus returns to the rail's open button (spec §5.1 fallback chain).
    expect(activeTab()).toBe(screen.getByTestId("inspector-rail-open"));
  });

  it("opens the rail's counter on its own tab", async () => {
    renderShell();
    fireEvent.click(screen.getByTestId("inspector-close"));

    fireEvent.click(await screen.findByTestId("inspector-rail-count-links"));

    expect(await screen.findByTestId("inspector-panel-links")).toBeInTheDocument();
    const openOnLinks = sessionStorage.getItem(
      "reqflow_inspector_tab_requirement_req-entity-1",
    ) as InspectorTabKey | null;
    expect(openOnLinks).toBe("links");
  });

  it("shows one spine summary line instead of rows for derivation links (M1-9)", async () => {
    const onShowInSpine = vi.fn();
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        {
          id: "link-1",
          source_id: "req-entity-1",
          target_id: "a-2",
          link_type: "derives_from",
          source_title: "Parent",
          source_type: "Requirement",
          target_title: "Child",
          target_type: "Requirement",
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "link-2",
          source_id: "req-entity-1",
          target_id: "a-3",
          link_type: "mitigates",
          source_title: "Risk",
          source_type: "Risk",
          target_title: "Child",
          target_type: "Requirement",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    renderShell({ onShowInSpine });
    fireEvent.click(screen.getByTestId("inspector-tab-links"));

    const summary = await screen.findByTestId("inspector-links-summary");
    expect(summary).toHaveTextContent("1 derivation and verification links");

    // No row for the derivation link; the mitigates link keeps its row.
    expect(screen.queryByTestId("trace-row-link-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("trace-row-link-2")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("inspector-links-show-in-spine"));
    expect(onShowInSpine).toHaveBeenCalledTimes(1);
  });

  it.each([
    [1920, "panel", "360px"],
    [1600, "panel", "360px"],
    [1440, "panel", "320px"],
    [1280, "sheet", "320px"],
    [1024, "rail", "320px"],
    [768, "rail", "320px"],
    [320, "rail", "320px"],
  ] as const)(
    "renders the %i px band as %s (M1-4)",
    async (width, expectedForm, expectedWidth) => {
      setViewport(width);
      const view = renderShell();

      const aside = screen.getByTestId("inspector-shell");
      expect(aside).toHaveAttribute("data-inspector-form", expectedForm);
      expect(aside).toHaveAttribute("data-inspector-width", expectedWidth.replace("px", ""));
      // The width reaches CSS through a custom property, not a style object.
      expect(aside.style.getPropertyValue("--inspector-width")).toBe(expectedWidth);

      view.unmount();
    },
  );

  it("resizes in 16 px steps with arrows and snaps with Home/End (M1-4)", async () => {
    renderShell();
    const splitter = screen.getByTestId("inspector-splitter");
    const aside = screen.getByTestId("inspector-shell");

    expect(splitter).toHaveAttribute("role", "separator");
    expect(splitter).toHaveAttribute("tabindex", "0");
    expect(splitter).toHaveAttribute("aria-valuenow", "320");
    expect(splitter).toHaveAttribute("aria-valuemin", "280");
    expect(splitter).toHaveAttribute("aria-valuemax", "520");

    // Wider by 16 px (the inspector sits on the right edge).
    fireEvent.keyDown(splitter, { key: "ArrowLeft" });
    expect(splitter).toHaveAttribute("aria-valuenow", "336");

    fireEvent.keyDown(splitter, { key: "ArrowRight" });
    fireEvent.keyDown(splitter, { key: "ArrowRight" });
    expect(splitter).toHaveAttribute("aria-valuenow", "304");

    fireEvent.keyDown(splitter, { key: "End" });
    expect(splitter).toHaveAttribute("aria-valuenow", "520");
    fireEvent.keyDown(splitter, { key: "Home" });
    expect(splitter).toHaveAttribute("aria-valuenow", "280");

    // The width reaches CSS through the custom property and is persisted.
    expect(aside.style.getPropertyValue("--inspector-width")).toBe("280px");
    expect(localStorage.getItem("reqflow_inspector_width_requirement")).toBe("280");
  });

  it("moves focus into the header when the rail expands (spec §5.1)", async () => {
    renderShell();
    fireEvent.click(screen.getByTestId("inspector-close"));
    await screen.findByTestId("inspector-rail");

    act(() => {
      screen.getByTestId("inspector-rail-open").click();
    });

    const header = await waitFor(() => {
      const heading = document.getElementById("inspector-heading");
      const container = heading?.parentElement;
      if (!container) throw new Error("header not rendered");
      return container;
    });
    expect(activeTab()).toBe(header);
  });
});
