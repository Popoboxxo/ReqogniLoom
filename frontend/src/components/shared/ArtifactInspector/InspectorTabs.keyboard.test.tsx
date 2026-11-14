/**
 * InspectorTabs — manual activation (spec §5.1/§5.2, M1-2).
 *
 * Each tab activates a fetch. APG *tabs* offers two models; this inspector
 * uses the **manual** one, so the distinguishing assertion is a fetch count:
 *
 *   four arrow presses  → 0 fetches
 *   one Enter           → exactly 1 fetch
 *   focus               → stays on the tab
 *
 * The shared `tablistKeyboardNav` helper implements the automatic model (it
 * calls `onChange` inside the arrow handler) and is deliberately not used
 * here.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const CURRENT_VERSION = { version: 2, label: "v2", createdAt: null, baselineIds: [] };

describe("InspectorTabs — manual activation (M1-2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, "", "/requirements/req-1");
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 1440,
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

  it("moves focus with arrows without fetching, and activates exactly one tab on Enter", async () => {
    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    // Mount = the active (version) tab's one fetch.
    await waitFor(() => {
      expect(requirementsModule.requirementsApi.versions).toHaveBeenCalledTimes(1);
    });

    const versionTab = screen.getByTestId("inspector-tab-version");
    versionTab.focus();

    // Four arrows: diff → links → comments → version. Focus only.
    for (const expected of [
      "inspector-tab-diff",
      "inspector-tab-links",
      "inspector-tab-comments",
      "inspector-tab-version",
    ]) {
      fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowRight" });
      expect(document.activeElement).toBe(screen.getByTestId(expected));
    }

    expect(requirementsModule.requirementsApi.versions).toHaveBeenCalledTimes(1);
    expect(tracelinksModule.tracelinksApi.listForArtifact).not.toHaveBeenCalled();
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();

    // One arrow to "diff", then Enter: the one fetch of the activation.
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowRight" });
    expect(document.activeElement).toBe(screen.getByTestId("inspector-tab-diff"));

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByTestId("inspector-panel-diff")).toBeInTheDocument();
    });
    // The Diff tab mounts the diff panel, which loads the version list once:
    // mount fetch (1) + this activation (1) — exactly one new request.
    await waitFor(() => {
      expect(requirementsModule.requirementsApi.versions).toHaveBeenCalledTimes(2);
    });
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();

    // Focus never leaves the tablist (spec §5.1).
    expect(document.activeElement).toBe(screen.getByTestId("inspector-tab-diff"));
  });

  it("supports Home and End as focus moves, still without activating", async () => {
    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );
    await waitFor(() => {
      expect(requirementsModule.requirementsApi.versions).toHaveBeenCalledTimes(1);
    });

    screen.getByTestId("inspector-tab-version").focus();

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "End" });
    expect(document.activeElement).toBe(screen.getByTestId("inspector-tab-comments"));

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Home" });
    expect(document.activeElement).toBe(screen.getByTestId("inspector-tab-version"));

    expect(screen.getByTestId("inspector-panel-version")).toBeInTheDocument();
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();
  });

  it("keeps exactly one tab in the tab order (roving tabindex)", async () => {
    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    const tabs = screen.getAllByRole("tab");
    expect(tabs.filter((tab) => tab.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(tabs.filter((tab) => tab.getAttribute("tabindex") === "-1")).toHaveLength(3);
  });
});
