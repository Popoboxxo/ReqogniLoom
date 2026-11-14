/**
 * F-06 (code review, 2026-08-19) — NeedList.test.tsx only covered the
 * presentational layer (props forwarded to setters); nothing proved that
 * `stakeholderNeedApi.create` actually receives `description`/`category` in
 * its payload — exactly the class of bug BUG-11's other six editor tests
 * (RequirementEditors/ArchitectureEditors/TestCaseEditors/RiskEditors/
 * IssueEditors/AdrEditors) were written to catch. This closes that gap at
 * the NeedsEditors integration level, where the API call actually happens.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../i18n/index";

// ---------------------------------------------------------------------------
// Mock API modules (must precede component import)
// ---------------------------------------------------------------------------

const { NEED } = vi.hoisted(() => ({
  NEED: {
    id: "need-001",
    workspace_id: "ws-001",
    artifact_id: "art-001",
    uid: "SN-1",
    title: "As a user, I need SSO",
    description: "",
    category: "",
    status: "draft",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/stakeholder-need", () => ({
  stakeholderNeedApi: {
    listAll: vi.fn().mockResolvedValue([NEED]),
    get: vi.fn().mockResolvedValue(NEED),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    impact: vi.fn().mockResolvedValue([]),
    // #1762/M2: the detail's TraceLinkPanel reads this once a need is open.
    listForArtifact: vi
      .fn()
      .mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: {
    resolve: vi.fn().mockResolvedValue([]),
  },
}));

// #1762/M2 (reference mount): the route now mounts the tabbed shell. The stub
// keeps the mount contract observable (both id spaces, the `inert` bracket's
// `coveredRef`, the spine jump) and renders the REAL CommentPanel when
// `renderRealComments` is set, so the comments request URL is assertable.
const inspectorProbe = vi.hoisted(() => ({
  renderRealComments: false,
  lastShell: undefined as
    | {
        kind?: string;
        entityId?: string | number;
        artifactPk?: string | null;
        hasCoveredRef?: boolean;
        hasOnShowInSpine?: boolean;
        hasHideTraceLinks?: boolean;
      }
    | undefined,
}));

vi.mock("../api/comments", () => ({
  commentsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    resolve: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("../components/shared/ArtifactInspector", async (importActual) => {
  const actual =
    await importActual<typeof import("../components/shared/ArtifactInspector")>();
  const { CommentPanel } = await import(
    "../components/shared/ArtifactInspector/CommentPanel"
  );
  return {
    ...actual,
    RightSidebar: () => null,
    InspectorShell: (props: {
      kind: import("../components/shared/ArtifactInspector").ArtifactKind;
      entityId: string | number;
      artifactPk: string | null;
      coveredRef?: unknown;
      onShowInSpine?: unknown;
    }) => {
      inspectorProbe.lastShell = {
        kind: props.kind,
        entityId: props.entityId,
        artifactPk: props.artifactPk,
        hasCoveredRef: props.coveredRef !== undefined,
        hasOnShowInSpine: props.onShowInSpine !== undefined,
        hasHideTraceLinks: "hideTraceLinks" in (props as Record<string, unknown>),
      };
      return inspectorProbe.renderRealComments ? (
        <CommentPanel kind={props.kind} artifactId={props.artifactPk ?? undefined} />
      ) : (
        <div data-testid="artifact-inspector" />
      );
    },
  };
});

// Fixed active workspace + a non-empty `workspaces` list — NeedsEditors
// guards create against the placeholder DEFAULT_WORKSPACE id via
// `workspaces.length === 0`.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "WS" },
    workspaces: [{ id: "ws-001", name: "WS" }],
    isLoadingWorkspace: false,
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "WS" },
    workspaces: [{ id: "ws-001", name: "WS" }],
    isLoadingWorkspace: false,
  }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Task 23: CreateTraceLinkDialog (mounted inside TraceLinkPanel, which this
// tree pulls in transitively) now reads the link-type catalog via
// useLinkTypes() — needs a provider-free mock here, same as every other
// non-dialog-focused test that renders it incidentally.
vi.mock("../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    creatableLinkTypes: [],
    definitionFor: () => undefined,
    isAllowedPair: () => false,
    labelFor: (key: string) => key,
  }),
}));

// Must import AFTER vi.mock
import NeedsEditors from "../components/NeedsEditors/NeedsEditors";
import { stakeholderNeedApi } from "../api/stakeholder-need";
import { commentsApi } from "../api/comments";

function renderEditor(initialPath = "/needs"): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/needs" element={<NeedsEditors />} />
          <Route path="/needs/:id" element={<NeedsEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("NeedsEditors — create form sends description/category to the API (BUG-11 / F-06)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(stakeholderNeedApi.listAll).mockResolvedValue([NEED]);
    vi.mocked(stakeholderNeedApi.get).mockResolvedValue(NEED);
  });

  it("sends the typed description and category alongside the title on create", async () => {
    vi.mocked(stakeholderNeedApi.create).mockResolvedValueOnce({
      ...NEED,
      id: "need-new-1",
    });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-need-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-need-btn"));

    // NeedList's title input has no data-testid/id (pre-existing, out of
    // scope here — see F-05 for the two fields this changeset does own);
    // its placeholder falls back to the literal default (no
    // `editor.newNeedTitle` key exists in either locale) regardless of
    // active language, so it's a reliable, language-independent selector.
    const titleInput = await screen.findByPlaceholderText("e.g. As a user, I need...");
    await user.type(titleInput, "New Need");
    await user.type(
      screen.getByTestId("need-new-description-input"),
      "Some description"
    );
    await user.type(screen.getByTestId("need-new-category-input"), "security");

    // The submit button carries a distinct aria-label; use its test-id to
    // avoid ambiguity with the header trigger or interview CTA buttons.
    await user.click(screen.getByTestId("need-create-submit-btn"));

    await waitFor(() =>
      expect(stakeholderNeedApi.create).toHaveBeenCalledWith(
        "ws-001",
        expect.objectContaining({
          title: "New Need",
          description: "Some description",
          category: "security",
        })
      )
    );
  });

  // #1278: the create button is disabled while its dialog is open, so the
  // dialog cannot snapshot `document.activeElement` (the browser blurs a
  // trigger the moment it becomes unfocusable). Escape must return focus to
  // the button, not to `<body>`.
  it("returns focus to the create button after Escape closes the dialog (#1278)", async () => {
    const user = userEvent.setup();
    renderEditor();

    const trigger = await screen.findByTestId("create-need-btn");
    await user.click(trigger);
    expect(trigger).toBeDisabled();
    await screen.findByTestId("need-new-dialog");

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(screen.queryByTestId("need-new-dialog")).not.toBeInTheDocument()
    );
    expect(trigger).not.toBeDisabled();
    expect(document.activeElement).toBe(trigger);
  });
});

// ---------------------------------------------------------------------------
// #1762 / M2 — reference mount: the tabbed inspector replaces RightSidebar
// ---------------------------------------------------------------------------

describe("NeedsEditors — inspector shell mount (#1762 M2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(stakeholderNeedApi.listAll).mockResolvedValue([NEED] as never);
    vi.mocked(stakeholderNeedApi.get).mockResolvedValue(NEED as never);
  });

  it("mounts InspectorShell with both id spaces and no hideTraceLinks switch", async () => {
    renderEditor(`/needs/${NEED.id}`);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-inspector")).toBeInTheDocument();
    });

    expect(screen.getAllByTestId("artifact-inspector")).toHaveLength(1);
    expect(inspectorProbe.lastShell).toMatchObject({
      kind: "stakeholderNeed",
      entityId: NEED.id,
      artifactPk: NEED.artifact_id,
      hasCoveredRef: true,
      hasOnShowInSpine: true,
    });
    // `hideTraceLinks` was the route-level switch of the stacked sidebar; the
    // tabbed shell derives its tab matrix from `kind` instead.
    expect(inspectorProbe.lastShell?.hasHideTraceLinks).toBe(false);
  });

  it("requests comments for the backing Artifact UUID, never the entity id", async () => {
    inspectorProbe.renderRealComments = true;
    try {
      renderEditor(`/needs/${NEED.id}`);

      await waitFor(() => expect(commentsApi.list).toHaveBeenCalledWith(NEED.artifact_id));
      expect(commentsApi.list).not.toHaveBeenCalledWith(NEED.id);
    } finally {
      inspectorProbe.renderRealComments = false;
    }
  });

  it("shows the artifact id and workflow status in the detail head (DoD 2)", async () => {
    renderEditor(`/needs/${NEED.id}`);

    const head = await screen.findByTestId("need-artifact-head");
    expect(head).toHaveTextContent(NEED.uid);
    expect(screen.getByTestId("need-detail-status")).toHaveTextContent(NEED.status);
  });

  it("uses the concept split layout with the spine in its own slot (DoD 6)", async () => {
    renderEditor(`/needs/${NEED.id}`);

    await waitFor(() => {
      expect(screen.getByTestId("splitview-list")).toBeInTheDocument();
      expect(screen.getByTestId("splitview-detail")).toBeInTheDocument();
      expect(screen.getByTestId("splitview-spine")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("splitview-divider")).not.toBeInTheDocument();
  });
});

describe("NeedsEditors — include_deleted reveals outdated needs (D6)", () => {
  const OUTDATED_NEED = { ...NEED, id: "need-outdated-1", title: "Retired need", status: "deprecated" };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(stakeholderNeedApi.get).mockResolvedValue(NEED as never);
    vi.mocked(stakeholderNeedApi.listAll).mockImplementation(async (_ws: string, includeDeleted?: boolean) =>
      (includeDeleted ? [NEED, OUTDATED_NEED] : [NEED]) as never,
    );
  });

  it("reveals and badges the outdated need only after the toggle is on", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId(`need-list-tree-node-${NEED.id}`)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("need-list-tree-node-need-outdated-1")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("need-list-include-deleted"));

    await waitFor(() => {
      expect(stakeholderNeedApi.listAll).toHaveBeenCalledWith("ws-001", true);
    });
    await waitFor(() => {
      expect(screen.getByTestId("need-list-tree-node-need-outdated-1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("need-list-tree-outdated-need-outdated-1")).toBeInTheDocument();
  });
});
