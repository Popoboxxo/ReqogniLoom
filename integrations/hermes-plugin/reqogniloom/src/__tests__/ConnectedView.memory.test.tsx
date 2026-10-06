import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ConnectedView } from "../ConnectedView";
import { makeAppState } from "./testHelpers";

// The view calls the state actions directly; mock them so each interaction is
// observed without touching the module-singleton state.
vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return {
    ...actual,
    loadMemoryContext: vi.fn(),
    askMemory: vi.fn(),
    requestCapture: vi.fn(),
    confirmCapture: vi.fn(),
    cancelCapture: vi.fn(),
    setCaptureEnabled: vi.fn(),
  };
});

import {
  askMemory,
  cancelCapture,
  confirmCapture,
  loadMemoryContext,
  requestCapture,
  setCaptureEnabled,
} from "../state";

const entry = { entry_id: "e-1", content: "SSO is required", scope: "workspace" as const, workspace_id: "ws-1" };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ConnectedView — memory read", () => {
  it("loads memory context for the connected workspace", () => {
    render(<ConnectedView state={makeAppState({ view: "connected" })} />);

    fireEvent.click(screen.getByTestId("memory-load-button"));

    expect(loadMemoryContext).toHaveBeenCalledWith("ws-1");
  });

  it("renders entries and the digest when present", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", memoryEntries: [entry], memoryDigest: "Workspace summary" })}
      />
    );

    expect(screen.getByTestId("memory-entry-e-1")).toHaveTextContent("SSO is required");
    expect(screen.getByTestId("memory-digest")).toHaveTextContent("Workspace summary");
    expect(screen.queryByTestId("memory-empty")).not.toBeInTheDocument();
  });

  it("shows a degraded backend distinctly from an empty result", () => {
    render(
      <ConnectedView
        state={makeAppState({
          view: "connected",
          memoryEntries: [],
          memoryDegraded: true,
          memoryDetail: "engine_error:TimeoutError",
          memoryLoaded: true,
        })}
      />
    );

    expect(screen.getByTestId("memory-degraded")).toHaveTextContent("engine_error:TimeoutError");
    // A degraded read is NOT the same as "nothing remembered".
    expect(screen.queryByTestId("memory-empty")).not.toBeInTheDocument();
  });

  it("shows the empty state only after a load has completed", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", memoryEntries: [], memoryDegraded: false, memoryLoaded: true })}
      />
    );

    expect(screen.getByTestId("memory-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("memory-degraded")).not.toBeInTheDocument();
  });

  it("does NOT assert 'no memory entries' before any read has run", () => {
    // Initial paint: memoryEntries=[] + degraded=false + loading=false, but
    // memoryLoaded is still false -- the panel must not claim the workspace
    // remembers nothing before a query ever ran.
    render(<ConnectedView state={makeAppState({ view: "connected", memoryLoaded: false })} />);

    expect(screen.queryByTestId("memory-empty")).not.toBeInTheDocument();
  });

  it("asks the workspace memory and disables Ask for a blank query", () => {
    render(<ConnectedView state={makeAppState({ view: "connected" })} />);

    const askButton = screen.getByTestId("memory-ask-button");
    expect(askButton).toBeDisabled();

    fireEvent.change(screen.getByTestId("memory-ask-input"), { target: { value: "is SSO required?" } });
    fireEvent.click(askButton);

    expect(askMemory).toHaveBeenCalledWith("ws-1", "is SSO required?");
  });

  it("renders the answer when present", () => {
    render(<ConnectedView state={makeAppState({ view: "connected", memoryAnswer: "Yes." })} />);

    expect(screen.getByTestId("memory-answer")).toHaveTextContent("Yes.");
  });
});

describe("ConnectedView — gated capture", () => {
  it("marks capture unavailable while disabled and hides the input", () => {
    render(<ConnectedView state={makeAppState({ view: "connected", captureEnabled: false })} />);

    expect(screen.getByTestId("capture-disabled")).toBeInTheDocument();
    expect(screen.queryByTestId("capture-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("capture-review-button")).not.toBeInTheDocument();
  });

  it("toggling the gate calls setCaptureEnabled", () => {
    render(<ConnectedView state={makeAppState({ view: "connected", captureEnabled: false })} />);

    fireEvent.click(screen.getByTestId("capture-toggle"));

    expect(setCaptureEnabled).toHaveBeenCalledWith(true);
  });

  it("Review only requests a capture draft (no auto-submit)", () => {
    render(<ConnectedView state={makeAppState({ view: "connected", captureEnabled: true })} />);

    fireEvent.change(screen.getByTestId("capture-input"), { target: { value: "Use PostgreSQL 16" } });
    fireEvent.click(screen.getByTestId("capture-review-button"));

    expect(requestCapture).toHaveBeenCalledWith("Use PostgreSQL 16");
    expect(confirmCapture).not.toHaveBeenCalled();
  });

  it("shows the pending draft with Confirm/Cancel, which call their actions", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", captureEnabled: true, pendingCapture: "Use PostgreSQL 16" })}
      />
    );

    expect(screen.getByTestId("capture-pending")).toHaveTextContent("Use PostgreSQL 16");

    fireEvent.click(screen.getByTestId("capture-confirm-button"));
    expect(confirmCapture).toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("capture-cancel-button"));
    expect(cancelCapture).toHaveBeenCalled();
  });

  it("renders a capture failure inside the Capture section, not the read section", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", captureEnabled: true, pendingCapture: "fact", captureError: "rate limited" })}
      />
    );

    expect(screen.getByTestId("capture-error-banner")).toHaveTextContent("rate limited");
  });

  it("disables Confirm while a capture write is in flight", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", captureEnabled: true, pendingCapture: "fact", captureBusy: true })}
      />
    );

    expect(screen.getByTestId("capture-confirm-button")).toBeDisabled();
  });
});
