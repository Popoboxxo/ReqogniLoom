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
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RightSidebar } from "./RightSidebar";

// Prop spied per panel, hoisted because vi.mock factories run before imports.
// #1763: the shell carries two id spaces — `entityId` for versions/diff/trace,
// `artifactId` (backing Artifact UUID) for comments. Both must be forwarded to
// the panel that owns them, never swapped.
const versionPanelProps = vi.hoisted(() => vi.fn());
const diffPanelProps = vi.hoisted(() => vi.fn());
const tracePanelProps = vi.hoisted(() => vi.fn());
const commentPanelProps = vi.hoisted(() => vi.fn());

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
  }),
}));

vi.mock("./VersionPanel", () => ({
  VersionPanel: (props: unknown) => {
    versionPanelProps(props);
    return <div data-testid="stub-version-panel" />;
  },
}));
vi.mock("./DiffPanel", () => ({
  DiffPanel: (props: unknown) => {
    diffPanelProps(props);
    return <div data-testid="stub-diff-panel" />;
  },
}));
vi.mock("./TracePanel", () => ({
  TracePanel: (props: unknown) => {
    tracePanelProps(props);
    return <div data-testid="stub-trace-panel" />;
  },
}));
// CommentPanel is stubbed for the same isolation reason as the three panels
// above: the shell test exercises layout/collapse and prop plumbing only, and
// the real panel would fetch comments from the API. Its props are captured so
// the id-space assertions below (#1763) see exactly what the shell forwards.
vi.mock("./CommentPanel", () => ({
  CommentPanel: (props: unknown) => {
    commentPanelProps(props);
    return <div data-testid="stub-comment-panel" />;
  },
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
    render(<RightSidebar kind="requirement" entityId="req-1" artifactId="artifact-1" />);

    expect(screen.getByTestId("artifact-inspector-collapsed")).toBeInTheDocument();
    expect(screen.queryByTestId("stub-version-panel")).not.toBeInTheDocument();
  });

  it("defaults to expanded on a wide viewport (1920px) with no stored preference", () => {
    setViewportWidth(1920);
    render(<RightSidebar kind="requirement" entityId="req-1" artifactId="artifact-1" />);

    expect(screen.queryByTestId("artifact-inspector-collapsed")).not.toBeInTheDocument();
    expect(screen.getByTestId("stub-version-panel")).toBeInTheDocument();
  });

  it("honours an explicit stored 'expanded' preference even on a narrow viewport", () => {
    setViewportWidth(1366);
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "false");
    render(<RightSidebar kind="requirement" entityId="req-1" artifactId="artifact-1" />);

    expect(screen.queryByTestId("artifact-inspector-collapsed")).not.toBeInTheDocument();
    expect(screen.getByTestId("stub-version-panel")).toBeInTheDocument();
  });

  it("honours an explicit stored 'collapsed' preference even on a wide viewport", () => {
    setViewportWidth(1920);
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "true");
    render(<RightSidebar kind="requirement" entityId="req-1" artifactId="artifact-1" />);

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
        <RightSidebar kind="requirement" entityId="req-1" artifactId="artifact-1" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByTestId("interview-provenance-badge"),
    ).toBeInTheDocument();
  });
});

describe("RightSidebar id spaces (#1763)", () => {
  const ENTITY_ID = "req-entity-001";
  const ARTIFACT_UUID = "8f14e45f-ceea-467a-9e4b-3a1c1f0d9b77";

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    // These tests do not render inside a Router, so the provenance badge must
    // resolve to "no provenance" (its <Link> branch needs one).
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({ session_id: null });
    // Expanded, or the panels never mount and nothing can be observed.
    window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "false");
    window.localStorage.setItem("reqflow_inspector_collapsed_adr", "false");
  });

  function lastProps(spy: ReturnType<typeof vi.fn>): Record<string, unknown> {
    const calls = spy.mock.calls;
    return (calls[calls.length - 1]?.[0] ?? {}) as Record<string, unknown>;
  }

  it("hands the backing Artifact UUID — never the entity id — to CommentPanel", async () => {
    render(<RightSidebar kind="requirement" entityId={ENTITY_ID} artifactId={ARTIFACT_UUID} />);
    // Flush the badge's provenance promise so React does not warn about an
    // act()-less update; the panels themselves render synchronously.
    await waitFor(() => expect(commentPanelProps).toHaveBeenCalled());

    expect(lastProps(commentPanelProps).artifactId).toBe(ARTIFACT_UUID);
    // The entity id must not leak into the comments panel: that swap was
    // exactly the 404 this regression test pins.
    expect(lastProps(commentPanelProps).artifactId).not.toBe(ENTITY_ID);
  });

  it("keeps the entity id for the versions / diff / trace panels", async () => {
    render(<RightSidebar kind="requirement" entityId={ENTITY_ID} artifactId={ARTIFACT_UUID} />);
    await waitFor(() => expect(versionPanelProps).toHaveBeenCalled());

    expect(lastProps(versionPanelProps).entityId).toBe(ENTITY_ID);
    expect(lastProps(diffPanelProps).entityId).toBe(ENTITY_ID);
    expect(lastProps(tracePanelProps).entityId).toBe(ENTITY_ID);
    // And none of them is handed the Artifact UUID under a different name.
    expect(lastProps(versionPanelProps).artifactId).toBeUndefined();
  });

  it("passes an absent Artifact UUID through as undefined instead of falling back", async () => {
    render(<RightSidebar kind="adr" entityId={ENTITY_ID} artifactId={undefined} />);
    await waitFor(() => expect(commentPanelProps).toHaveBeenCalled());

    expect(lastProps(commentPanelProps).artifactId).toBeUndefined();
  });
});
