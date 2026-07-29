/**
 * REQ-L1-095: NeedsEditors — create guard against unloaded workspace.
 *
 * The active workspace is initialised with the DEFAULT_WORKSPACE placeholder
 * (null-UUID) before reloadWorkspaces() populates the real list. Triggering a
 * create in that window would POST against the null-UUID workspace. These tests
 * verify the create trigger stays inert until `workspaces` is non-empty.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { language: "de" },
  }),
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: undefined }),
  useNavigate: () => vi.fn(),
}));

const useWorkspaceMock = vi.fn();
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => useWorkspaceMock(),
}));

vi.mock("./useNeedData", () => ({
  useNeedData: () => ({
    needs: [],
    need: null,
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock("../../api", () => ({
  attributeVisibilityApi: { list: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../api/stakeholder-need", () => ({
  stakeholderNeedApi: { create: vi.fn().mockResolvedValue({ id: "new-1" }) },
}));

vi.mock("../SplitView/SplitView", () => ({
  SplitView: ({ leftPanel }: { leftPanel: React.ReactNode }) => <div>{leftPanel}</div>,
}));

vi.mock("../shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

vi.mock("./NeedForm", () => ({ NeedForm: () => null }));

// NeedList is mocked to expose only the resulting create-form state; the
// create trigger itself now lives in the (unmocked) shared PageHeader
// component rendered by NeedsEditors (issue #172), identified by the same
// "create-need-btn" testid it always used.
vi.mock("./NeedList", () => ({
  NeedList: (props: { showCreateForm?: boolean }) => (
    <div>{props.showCreateForm && <span data-testid="create-form-open" />}</div>
  ),
}));

// Must import AFTER vi.mock
import NeedsEditors from "./NeedsEditors";

const WS = { id: "11111111-1111-1111-1111-111111111111", name: "WS" };

describe("NeedsEditors — create guard (REQ-L1-095)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not open the create form while workspaces are unloaded", async () => {
    useWorkspaceMock.mockReturnValue({
      activeWorkspace: { id: "00000000-0000-0000-0000-000000000000" },
      workspaces: [],
    });

    render(<NeedsEditors />);
    await userEvent.click(screen.getByTestId("create-need-btn"));

    expect(screen.queryByTestId("create-form-open")).not.toBeInTheDocument();
  });

  it("opens the create form once workspaces are loaded", async () => {
    useWorkspaceMock.mockReturnValue({
      activeWorkspace: WS,
      workspaces: [WS],
    });

    render(<NeedsEditors />);
    await userEvent.click(screen.getByTestId("create-need-btn"));

    expect(screen.getByTestId("create-form-open")).toBeInTheDocument();
  });
});
