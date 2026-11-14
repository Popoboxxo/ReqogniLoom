/**
 * InspectorSheet — non-modal sheet and the `inert` bracket (spec §4.2, M1-5).
 *
 * The sheet is **not** a dialog: no scrim, no focus trap. What it must do is
 * take the covered detail area out of the tab order and the accessibility
 * tree while it is open (WCAG 2.2 SC 2.4.11), and put it back in the same
 * commit the sheet unmounts.
 *
 * The "detail area" is owned by the route, which hands a ref down; the "list"
 * next to it stays operable — that is the whole point of non-modal.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InspectorShell } from "./InspectorShell";
import * as requirementsModule from "../../../api/requirements";
import * as commentsModule from "../../../api/comments";
import * as tracelinksModule from "../../../api/tracelinks";

vi.mock("../../../api/requirements");
vi.mock("../../../api/comments");
vi.mock("../../../api/tracelinks");
vi.mock("../../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));
vi.mock("../../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({ linkTypes: [], labelFor: (key: string) => key }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string =>
      typeof second === "string"
        ? second
        : second && typeof second === "object" && "defaultValue" in second
          ? String((second as { defaultValue: unknown }).defaultValue)
          : key,
  }),
}));

const CURRENT_VERSION = { version: 1, label: "v1", createdAt: null, baselineIds: [] };

/** The route's half of the contract: list + covered detail area. */
function RouteHarness(): JSX.Element {
  const coveredRef = useRef<HTMLDivElement | null>(null);
  return (
    <div>
      <div data-testid="list-pane">
        <button type="button" className="btn-ghost">
          List action
        </button>
      </div>
      <div ref={coveredRef} data-testid="covered-detail">
        <p>Detail content</p>
      </div>
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
        coveredRef={coveredRef}
      />
    </div>
  );
}

describe("InspectorSheet — inert bracket (M1-5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, "", "/requirements/req-1");
    // 1280 px = R3 "sheet open by default" (spec §4.2).
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 1280,
    });
    vi.mocked(requirementsModule.requirementsApi.versions).mockResolvedValue([]);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("marks the covered detail area inert and leaves the list operable", async () => {
    render(<RouteHarness />);

    await waitFor(() => {
      expect(screen.getByTestId("covered-detail")).toHaveAttribute("inert");
    });
    expect(screen.getByTestId("list-pane")).not.toHaveAttribute("inert");
    // Non-modal: no dialog role, no scrim — the sheet is a region.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("removes inert again when the sheet closes, and focuses the rail opener", async () => {
    render(<RouteHarness />);
    await waitFor(() => {
      expect(screen.getByTestId("covered-detail")).toHaveAttribute("inert");
    });

    fireEvent.click(screen.getByTestId("inspector-close"));

    await waitFor(() => {
      expect(screen.getByTestId("covered-detail")).not.toHaveAttribute("inert");
    });
    expect(await screen.findByTestId("inspector-rail")).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByTestId("inspector-rail-open"));
  });

  it("closes on Escape from inside the sheet and returns focus to the opener", async () => {
    render(<RouteHarness />);

    const sheet = await screen.findByTestId("inspector-surface");
    fireEvent.keyDown(sheet, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByTestId("inspector-surface")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("covered-detail")).not.toHaveAttribute("inert");
    expect(document.activeElement).toBe(screen.getByTestId("inspector-rail-open"));
  });

  it("does not trap focus: the list button stays reachable while the sheet is open", async () => {
    render(<RouteHarness />);
    await waitFor(() => {
      expect(screen.getByTestId("covered-detail")).toHaveAttribute("inert");
    });

    const listButton = screen.getByRole("button", { name: "List action" });
    listButton.focus();
    expect(document.activeElement).toBe(listButton);
  });
});
