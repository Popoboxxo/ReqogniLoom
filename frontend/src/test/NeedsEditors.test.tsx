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

vi.mock("../api", () => ({
  attributeVisibilityApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: {
    resolve: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

// Fixed active workspace + a non-empty `workspaces` list — NeedsEditors
// guards create against the placeholder DEFAULT_WORKSPACE id via
// `workspaces.length === 0`.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "WS" },
    workspaces: [{ id: "ws-001", name: "WS" }],
    isLoadingWorkspace: false,
  }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Must import AFTER vi.mock
import NeedsEditors from "../components/NeedsEditors/NeedsEditors";
import { stakeholderNeedApi } from "../api/stakeholder-need";

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
});
