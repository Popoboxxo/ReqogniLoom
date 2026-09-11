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
import { MemoryRouter } from "react-router-dom";
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
// InterviewProvenanceBadge is NOT mocked -- it renders for real inside
// RightSidebar (Task 10 mount point). Default to no provenance so every
// pre-existing test in this file, which never renders inside a Router,
// keeps rendering the badge's null branch (no <Link> instantiated, so no
// "useHref outside a Router" error). A partial mock that omits this export
// would make every consumer test in this file throw -- mock the whole shape.
vi.mock("../../../api/interviews", () => ({
  interviewsApi: { getProvenance: vi.fn().mockResolvedValue({ session_id: null }) },
}));
import { interviewsApi } from "../../../api/interviews";

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

describe("RightSidebar interview provenance badge (Task 10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("mounts the interview provenance badge for the inspected artifact", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({
      session_id: "22222222-2222-2222-2222-222222222222",
    });
    // The aside defaults to collapsed below DEFAULT_COLLAPSE_BREAKPOINT_PX
    // (#419) unless an explicit prior preference says otherwise -- force
    // expanded so the panels div (and the badge inside it) actually mounts.
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "false");

    render(
      <MemoryRouter>
        <RightSidebar kind="requirement" artifactId="req-1" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByTestId("interview-provenance-badge"),
    ).toBeInTheDocument();
  });
});
