/**
 * ARCH-L1-001 ReactFrontend — RiskEditors Task 2.2 concept remodel test.
 *
 * Mirrors AdrEditors.test.tsx (Task 2.1 reference): PageHeader / ArtifactRow
 * / Dialog / EmptyState conventions, plus the Task 2.2-specific relocation of
 * the "Neue Verknüpfung" ("new link") button out of RiskEditors and into
 * TraceLinkPanel's own header.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../i18n/index";
import { i18n } from "../i18n/index";

// ---------------------------------------------------------------------------
// Mock API modules (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  getAllPages: vi.fn().mockResolvedValue([]),
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  apiClient: {
    get: vi.fn((path?: string) =>
      Promise.resolve(
        path === "/auth/me/"
          ? {
              user: {
                id: "u-1",
                username: "tester",
                email: "t@x.test",
                first_name: "",
                last_name: "",
                is_active: true,
                tenant_id: "t-1",
                roles: ["admin"],
              },
              tenant_id: "t-1",
              roles: ["admin"],
            }
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

// vi.hoisted so this is available inside the hoisted vi.mock factories below.
const { RISK } = vi.hoisted(() => ({
  RISK: {
    id: "risk-001",
    workspace_id: "ws-001",
    title: "Third-party outage",
    description: "Vendor API downtime.",
    probability: "medium" as const,
    impact: "high" as const,
    risk_score: 6,
    severity: "high" as const,
    category: "technical" as const,
    owner: "",
    mitigation_strategy: "",
    status: "Identified" as const,
    version: 1,
    // #1762/M2: identity (head) + the backing Artifact id (comments tab).
    uid: "RISK-1",
    artifact_id: "art-risk-001",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/risks", () => ({
  risksApi: {
    list: vi.fn().mockResolvedValue({ results: [RISK], count: 1, next: null, previous: null }),
    listAll: vi.fn().mockResolvedValue([RISK]),
    get: vi.fn().mockResolvedValue(RISK),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
    // Task 3.3: <TraceSpine>'s useDerivationChain calls impact() on mount.
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/artifacts", () => ({
  artifactsApi: {
    get: vi.fn(),
  },
}));

// Isolate from the ArtifactInspector's own data fetching, but keep the mount
// contract observable (#1762/M2): the stub records the two id spaces the shell
// receives and — when `renderRealComments` is set — renders the REAL
// CommentPanel so the comments request URL becomes assertable.
const inspectorProbe = vi.hoisted(() => ({
  renderRealComments: false,
  lastShell: undefined as
    | {
        kind?: string;
        entityId?: string | number;
        artifactPk?: string | null;
        hasCoveredRef?: boolean;
        hasOnShowInSpine?: boolean;
        unknownProps?: string[];
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
        // #1762/M8: no prop outside the documented shell contract — a
        // removed route-level switch would show up here as an unknown key.
        unknownProps: Object.keys(props).filter(
          (key) =>
            ![
              "kind",
              "entityId",
              "artifactPk",
              "currentVersion",
              "initialTab",
              "coveredRef",
              "onShowInSpine",
            ].includes(key),
        ),
      };
      return inspectorProbe.renderRealComments ? (
        <CommentPanel kind={props.kind} artifactId={props.artifactPk ?? undefined} />
      ) : (
        <div data-testid="artifact-inspector" />
      );
    },
  };
});

// Provide a fixed active workspace instead of the real fetch-driven provider.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" }, isLoadingWorkspace: false }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" }, isLoadingWorkspace: false }),
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
import RiskEditors from "../components/RiskEditors/RiskEditors";
import { tracelinksApi } from "../api/tracelinks";
import { risksApi } from "../api/risks";
import { commentsApi } from "../api/comments";
import type { Risk } from "../types";

function renderEditor(initialPath = `/risks/${RISK.id}`): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/risks" element={<RiskEditors />} />
          <Route path="/risks/:id" element={<RiskEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("RiskEditors Task 2.2 concept remodel (PageHeader / ArtifactRow / Dialog / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
    vi.mocked(risksApi.list).mockResolvedValue({ results: [RISK], count: 1, next: null, previous: null });
    vi.mocked(risksApi.listAll).mockResolvedValue([RISK]);
    vi.mocked(risksApi.get).mockResolvedValue(RISK);
  });

  it("renders exactly one <h1> with an always-visible summary (12.1)", async () => {
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Risks");
    // Summary is visible without any active search/filter.
    expect(screen.getByTestId("page-header-count")).toHaveTextContent("1 risk");
  });

  it("moves the primary create action into the PageHeader, named after the result", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId("page-header")).toBeInTheDocument();
    });
    const createButton = screen.getByTestId("create-risk-btn");
    expect(screen.getByTestId("page-header")).toContainElement(createButton);
    expect(createButton).toHaveTextContent("New Risk");
    // No inline create form in the list anymore — creation only happens
    // through the Dialog, not yet open.
    expect(screen.queryByTestId("risk-new-title-input")).not.toBeInTheDocument();
  });

  it("renders each risk as an ArtifactRow with id, status and title", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId(`risk-row-${RISK.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`risk-row-${RISK.id}`);
    expect(row).toHaveTextContent(RISK.title);
    expect(screen.getByTestId(`risk-row-${RISK.id}-status`)).toHaveTextContent(RISK.status);
  });

  it("shows the empty variant with a create action when there are no risks at all", async () => {
    vi.mocked(risksApi.listAll).mockResolvedValue([]);
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("risk-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("risk-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId(`risk-row-${RISK.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("risk-list-search-input"), "no such risk title");

    await waitFor(() => {
      expect(screen.getByTestId("risk-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("risk-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-list-empty")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header action, titled after the button label, and creates via shared/Dialog", async () => {
    vi.mocked(risksApi.create).mockResolvedValue({ ...RISK, id: "risk-new-1" });
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-risk-btn"));

    const dialog = await screen.findByTestId("risk-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // Dialog title repeats the button's label (ch. 12.8).
    expect(screen.getByRole("heading", { name: "New Risk" })).toBeInTheDocument();

    await user.type(screen.getByTestId("risk-new-title-input"), "Key supplier lock-in");
    await user.click(screen.getByTestId("risk-new-save-btn"));

    await waitFor(() => {
      expect(risksApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-001",
        title: "Key supplier lock-in",
      });
    });
  });

  /**
   * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — description/category are
   * ordinary risksApi.create() fields the backend already accepts but had
   * no editor in this dialog.
   */
  it("sends the typed description and category alongside the title on create (BUG-11)", async () => {
    vi.mocked(risksApi.create).mockResolvedValue({ ...RISK, id: "risk-new-2" });
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-risk-btn"));
    await screen.findByTestId("risk-create-dialog");

    await user.type(screen.getByTestId("risk-new-title-input"), "Key supplier lock-in");
    await user.type(screen.getByTestId("risk-new-description-input"), "Single-source dependency");
    await user.selectOptions(screen.getByTestId("risk-new-category-select"), "operational");
    await user.click(screen.getByTestId("risk-new-save-btn"));

    await waitFor(() => {
      expect(risksApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Key supplier lock-in",
          description: "Single-source dependency",
          category: "operational",
        })
      );
    });
  });

  it("relocates the trace-link creation action into TraceLinkPanel's own header, not a freestanding button under the form (Task 2.2)", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText("Trace Links")).toBeInTheDocument();
    });

    // The old freestanding "Neue Verknüpfung" button no longer exists.
    expect(screen.queryByTestId("risk-create-link-button")).not.toBeInTheDocument();
    // TraceLinkPanel owns the new-link action in its own header instead.
    expect(screen.getByTestId("trace-link-panel-open-dialog")).toBeInTheDocument();
  });

  it("uses the unified + New Risk trigger label instead of bare Erstellen", async () => {
    const previousLanguage = i18n.language;
    void i18n.changeLanguage("de");

    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    expect(screen.getByTestId("create-risk-btn")).toHaveTextContent("+ Neues Risiko");
    expect(screen.queryByText("Erstellen")).not.toBeInTheDocument();

    void i18n.changeLanguage(previousLanguage);
  });
});

// ---------------------------------------------------------------------------
// #1762 / M2 — the tabbed inspector replaces the stacked sidebar on this route
// ---------------------------------------------------------------------------

describe("RiskEditors — inspector shell mount (#1762 M2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(risksApi.list).mockResolvedValue({ results: [RISK], count: 1, next: null, previous: null } as any);
    vi.mocked(risksApi.listAll).mockResolvedValue([RISK] as any);
    vi.mocked(risksApi.get).mockResolvedValue(RISK as any);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
  });

  it("mounts InspectorShell with both id spaces and only the documented props", async () => {
    renderEditor(`/risks/${RISK.id}`);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-inspector")).toBeInTheDocument();
    });

    expect(screen.getAllByTestId("artifact-inspector")).toHaveLength(1);
    expect(inspectorProbe.lastShell).toMatchObject({
      kind: "risk",
      entityId: RISK.id,
      artifactPk: RISK.artifact_id,
      hasCoveredRef: true,
      hasOnShowInSpine: true,
    });
    // The old route switch existed only because the stacked sidebar showed the
    // same links twice; the tabbed shell derives the matrix from `kind`.
    expect(inspectorProbe.lastShell?.unknownProps).toEqual([]);
  });

  it("requests comments for the backing Artifact UUID, never the entity id", async () => {
    inspectorProbe.renderRealComments = true;
    try {
      renderEditor(`/risks/${RISK.id}`);

      await waitFor(() => expect(commentsApi.list).toHaveBeenCalledWith(RISK.artifact_id));
      expect(commentsApi.list).not.toHaveBeenCalledWith(RISK.id);
    } finally {
      inspectorProbe.renderRealComments = false;
    }
  });

  it("shows the artifact id and workflow status in the detail head (DoD 2)", async () => {
    renderEditor(`/risks/${RISK.id}`);

    const head = await screen.findByTestId("risk-artifact-head");
    expect(head).toHaveTextContent(RISK.uid);
    expect(screen.getByTestId("risk-detail-status")).toHaveTextContent(RISK.status);
  });

  it("uses the concept split layout with the spine in its own slot (DoD 6)", async () => {
    renderEditor(`/risks/${RISK.id}`);

    await waitFor(() => {
      expect(screen.getByTestId("splitview-list")).toBeInTheDocument();
      expect(screen.getByTestId("splitview-detail")).toBeInTheDocument();
      expect(screen.getByTestId("splitview-spine")).toBeInTheDocument();
    });
    // The legacy drag divider is gone — fixed 40/60 ratio per ch. 12.6.
    expect(screen.queryByTestId("splitview-divider")).not.toBeInTheDocument();
  });
});

describe("RiskEditors — include_deleted reveals outdated risks (D6)", () => {
  const OUTDATED_RISK = { ...RISK, id: "risk-outdated-1", title: "Retired risk", status: "Closed" } as unknown as Risk;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
    vi.mocked(risksApi.get).mockResolvedValue(RISK as unknown as Risk);
    vi.mocked(risksApi.listAll).mockImplementation(async (_ws: string, includeDeleted?: boolean) =>
      (includeDeleted ? [RISK, OUTDATED_RISK] : [RISK]) as never,
    );
  });

  it("reveals and badges the outdated risk only after the toggle is on", async () => {
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId(`risk-row-${RISK.id}`)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("risk-row-risk-outdated-1")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("risk-list-include-deleted"));

    await waitFor(() => {
      expect(risksApi.listAll).toHaveBeenCalledWith("ws-001", true);
    });
    await waitFor(() => {
      expect(screen.getByTestId("risk-row-risk-outdated-1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("risk-row-risk-outdated-1-outdated")).toBeInTheDocument();
  });
});
