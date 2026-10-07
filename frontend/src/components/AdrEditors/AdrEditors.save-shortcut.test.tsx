/**
 * Issue #1100 — the hand-written ADR create dialog answers Ctrl/Cmd+S.
 *
 * The create dialogs of Adr/Risk/Issue/TestCase are structurally identical and
 * are NOT `ArtifactForm`s, so each opts into the shared `useSaveShortcut`
 * itself. This suite is the representative integration test for that pattern:
 * open the real dialog, type a title, press the chord, assert the create path
 * ran exactly like the Save button.
 */

import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
    i18n: { language: "de" },
  }),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: undefined }),
  useNavigate: () => navigateMock,
}));

const useWorkspaceMock = vi.fn();
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => useWorkspaceMock(),
}));

vi.mock("./useAdrData", () => ({
  useAdrData: () => ({
    items: [],
    item: null,
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

const createMock = vi.fn();
vi.mock("../../api/adrs", () => ({
  adrsApi: { create: (...args: unknown[]) => createMock(...args) },
}));

// Sibling panels are not under test; mocking them keeps the mount light.
vi.mock("./AdrList", () => ({ AdrList: () => null }));
vi.mock("./AdrArtifactForm", () => ({ AdrArtifactForm: () => null }));
vi.mock("./AdrSupersedePanel", () => ({ AdrSupersedePanel: () => null }));
vi.mock("../shared/ArtifactInspector", () => ({ RightSidebar: () => null }));
vi.mock("../shared/TraceLinkPanel", () => ({ TraceLinkPanel: () => null }));
vi.mock("../shared/useInterviewStartCta", () => ({
  useInterviewStartCta: () => ({ label: "Interview", onClick: () => {} }),
}));
vi.mock("../shared/TraceSpine", () => ({
  TraceSpine: () => null,
  useDerivationChain: () => ({
    stations: [],
    isLoading: false,
    error: null,
    isOpenable: () => false,
    resolveEntry: () => null,
  }),
}));

import AdrEditors from "./AdrEditors";

const WS = { id: "ws-1", name: "WS", preset: "standard" };

async function pressCtrlS(): Promise<KeyboardEvent> {
  await act(async () => {});
  const event = new KeyboardEvent("keydown", {
    key: "s",
    code: "KeyS",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  act(() => {
    document.dispatchEvent(event);
  });
  return event;
}

describe("AdrEditors create dialog Ctrl/Cmd+S (#1100)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createMock.mockResolvedValue({ id: "adr-1" });
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
  });

  it("saves the create draft through the shortcut", async () => {
    const user = userEvent.setup();
    render(<AdrEditors />);

    await user.click(screen.getByTestId("create-adr-btn"));
    await user.type(screen.getByTestId("adr-new-title-input"), "Neuer ADR");

    const event = await pressCtrlS();

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock.mock.calls[0][0]).toMatchObject({
      workspace_id: "ws-1",
      title: "Neuer ADR",
    });
    expect(event.defaultPrevented).toBe(true);
  });

  it("advertises the binding on the create save control", async () => {
    const user = userEvent.setup();
    render(<AdrEditors />);

    await user.click(screen.getByTestId("create-adr-btn"));

    expect(screen.getByTestId("adr-new-save-btn")).toHaveAttribute(
      "aria-keyshortcuts",
      "Control+S Meta+S",
    );
  });

  it("does not double-submit when two chords land in one tick (FR-U5-01)", async () => {
    // The `isCreating` state guard cannot see this: React has not re-rendered
    // between the two keydowns, so the second still reads `false`. Only the
    // synchronous `submittingRef` swallows it. Representative of all five
    // hand-written create dialogs (Adr/Risk/Issue/TestCase/Architecture).
    const user = userEvent.setup();
    render(<AdrEditors />);

    await user.click(screen.getByTestId("create-adr-btn"));
    await user.type(screen.getByTestId("adr-new-title-input"), "Neuer ADR");

    // Drain passive effects so the document-level listener is attached.
    await act(async () => {});
    const makeEvent = (): KeyboardEvent =>
      new KeyboardEvent("keydown", {
        key: "s",
        code: "KeyS",
        ctrlKey: true,
        bubbles: true,
        cancelable: true,
      });
    act(() => {
      document.dispatchEvent(makeEvent());
      document.dispatchEvent(makeEvent());
    });

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
  });
});
