/**
 * RightSidebar.test.tsx
 *
 * #419: on first load (no stored collapse preference yet), the inspector
 * must default to collapsed on narrow viewports so it does not obscure the
 * editor (Save button, Classification & Properties fields, etc. became
 * unreachable at 1366x768). An explicit prior user choice — collapsed or
 * expanded — always wins over this viewport heuristic.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RightSidebar } from "./RightSidebar";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
  }),
}));

vi.mock("./VersionPanel", () => ({
  VersionPanel: () => <div data-testid="stub-version-panel" />,
}));
vi.mock("./DiffPanel", () => ({
  DiffPanel: () => <div data-testid="stub-diff-panel" />,
}));
vi.mock("./TracePanel", () => ({
  TracePanel: () => <div data-testid="stub-trace-panel" />,
}));

function setViewportWidth(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

describe("RightSidebar default collapse state (#419)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    setViewportWidth(1024);
  });

  it("defaults to collapsed on a narrow viewport (1366px) with no stored preference", () => {
    setViewportWidth(1366);
    render(<RightSidebar kind="requirement" artifactId="req-1" />);

    expect(screen.getByTestId("artifact-inspector-collapsed")).toBeInTheDocument();
    expect(screen.queryByTestId("stub-version-panel")).not.toBeInTheDocument();
  });

  it("defaults to expanded on a wide viewport (1920px) with no stored preference", () => {
    setViewportWidth(1920);
    render(<RightSidebar kind="requirement" artifactId="req-1" />);

    expect(screen.queryByTestId("artifact-inspector-collapsed")).not.toBeInTheDocument();
    expect(screen.getByTestId("stub-version-panel")).toBeInTheDocument();
  });

  it("honours an explicit stored 'expanded' preference even on a narrow viewport", () => {
    setViewportWidth(1366);
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "false");
    render(<RightSidebar kind="requirement" artifactId="req-1" />);

    expect(screen.queryByTestId("artifact-inspector-collapsed")).not.toBeInTheDocument();
    expect(screen.getByTestId("stub-version-panel")).toBeInTheDocument();
  });

  it("honours an explicit stored 'collapsed' preference even on a wide viewport", () => {
    setViewportWidth(1920);
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "true");
    render(<RightSidebar kind="requirement" artifactId="req-1" />);

    expect(screen.getByTestId("artifact-inspector-collapsed")).toBeInTheDocument();
  });
});
