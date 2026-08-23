/**
 * Interview-management web widget — widget shell (plan Task 5).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewWidget } from "./InterviewWidget";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));

describe("InterviewWidget", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders collapsed by default", () => {
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("expands on toggle click and persists the open state", () => {
    render(<InterviewWidget />);
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("true");
  });

  it("renders expanded on mount when localStorage says open", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
  });

  it("collapses on a second toggle click", () => {
    render(<InterviewWidget />);
    const toggle = screen.getByTestId("interview-widget-toggle");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  // Issue #679: direct `window.localStorage` access threw an unhandled
  // TypeError/SecurityError in storage-restricted environments (private
  // browsing, third-party-cookie lockouts, some JSDOM setups) and froze the
  // widget. `safeLocalStorage` must absorb that instead of crashing.
  describe("when localStorage access throws (issue #679)", () => {
    let originalLocalStorage: Storage;

    beforeEach(() => {
      originalLocalStorage = window.localStorage;
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: {
          getItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
          setItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
        },
      });
    });

    afterEach(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: originalLocalStorage,
      });
    });

    it("mounts and renders the collapsed toggle without crashing", () => {
      expect(() => render(<InterviewWidget />)).not.toThrow();
      expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });

    it("still expands on toggle click even though persisting the state fails", () => {
      render(<InterviewWidget />);
      const toggle = screen.getByTestId("interview-widget-toggle");
      expect(() => fireEvent.click(toggle)).not.toThrow();
      expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    });
  });
});
