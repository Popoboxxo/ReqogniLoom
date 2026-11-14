/**
 * InspectorLiveRegions — exactly two regions, one announcement per
 * interaction (spec §5.3, M1-6).
 *
 * The two rules under test:
 *
 *  1. a `xxxLoaded` message supersedes the generic `tabChanged` message of
 *     the same task (one spoken sentence, not two), and
 *  2. a retry announces its own outcome — `retrySucceeded`, never an extra
 *     `versionLoaded` on top.
 *
 * Errors are the only assertive messages, and one per event.
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
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        const options = second as Record<string, unknown>;
        let text = String(options.defaultValue);
        for (const [name, value] of Object.entries(options)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      return key;
    },
  }),
}));

const CURRENT_VERSION = { version: 2, label: "v2", createdAt: null, baselineIds: [] };

const politeRegion = (): HTMLElement => screen.getByTestId("inspector-live");
const alertRegion = (): HTMLElement => screen.getByTestId("inspector-alert");

describe("InspectorLiveRegions (M1-6)", () => {
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

  it("keeps exactly two live regions at the end of the surface", async () => {
    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    expect(politeRegion()).toHaveAttribute("aria-live", "polite");
    expect(alertRegion()).toHaveAttribute("role", "alert");
    // Both sit inside the surface, after the tabpanel.
    const surface = screen.getByTestId("inspector-shell");
    const panel = screen.getByTestId("inspector-panel-version");
    expect(surface.contains(politeRegion())).toBe(true);
    expect(
      panel.compareDocumentPosition(politeRegion()) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("announces a tab switch exactly once — the loaded count supersedes tabChanged", async () => {
    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));

    await waitFor(() => {
      expect(politeRegion()).toHaveTextContent("0 comments, 0 open.");
    });
    // The weaker "area changed" message was cancelled by the load message.
    expect(politeRegion()).not.toHaveTextContent("Comments section");
  });

  it("announces a retry as retrySucceeded, without a second versionLoaded", async () => {
    vi.mocked(requirementsModule.requirementsApi.versions)
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue([]);

    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    const retry = await screen.findByTestId("version-retry");
    fireEvent.click(retry);

    await waitFor(() => {
      expect(politeRegion()).toHaveTextContent("Version loaded.");
    });
    expect(politeRegion()).not.toHaveTextContent("versions loaded");
  });

  it("puts a load failure in the alert region, once per event", async () => {
    vi.mocked(requirementsModule.requirementsApi.versions).mockRejectedValue(
      new Error("boom"),
    );

    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    await waitFor(() => {
      expect(alertRegion()).toHaveTextContent("Version could not be loaded.");
    });
    // Not a second time in the polite region — an error is assertive only.
    expect(politeRegion()).not.toHaveTextContent("could not be loaded");
  });

  it("does not stack a retry failure with the original error message", async () => {
    vi.mocked(requirementsModule.requirementsApi.versions).mockRejectedValue(
      new Error("boom"),
    );

    render(
      <InspectorShell
        kind="requirement"
        entityId="req-1"
        artifactPk="artifact-1"
        currentVersion={CURRENT_VERSION}
      />,
    );

    fireEvent.click(await screen.findByTestId("version-retry"));

    await waitFor(() => {
      expect(alertRegion()).toHaveTextContent("Version still unavailable.");
    });
    expect(alertRegion()).not.toHaveTextContent("could not be loaded");
  });
});
