/**
 * Interview-management web widget — widget shell (plan Task 5).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
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
});
