/**
 * GH-443 — the "show deleted" opt-in in the requirements list panel.
 *
 * DELETE is a soft-delete, so a deleted requirement stays in the database with
 * `status: "outdated"` and the list endpoint hides it. The list's status filter
 * builds its options from the *loaded* items, so unless the outdated ones are
 * actually fetched the user has no way to reach them at all — the deletion
 * looks permanent even though it is not.
 *
 * These tests assert the wiring end-to-end at component level: the toggle must
 * reach the API layer, and the default must stay "hidden" so a plain delete
 * still visibly removes the row.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
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
          : {},
      ),
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    reactivate: vi.fn(),
    get: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "draft",
      states: ["draft"],
      allowed_transitions: [],
    }),
    transition: vi.fn().mockResolvedValue({}),
    aiDecomposeNextLevel: vi
      .fn()
      .mockResolvedValue({ drafts: [], parent_requirement_id: "req-live" }),
  },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn().mockResolvedValue({ results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../api/workspaces", () => ({
  workspacesApi: { list: vi.fn(), downloadPdfReport: vi.fn() },
}));

vi.mock("../../api/testcases", () => ({
  testcasesApi: { list: vi.fn().mockResolvedValue({ results: [], count: 0 }) },
}));

// Must be imported AFTER the vi.mock calls.
import RequirementEditors from "./RequirementEditors";
import { requirementsApi } from "../../api/requirements";
import { AuthProvider } from "../../context/AuthContext";
import { WorkspaceProvider } from "../../context/WorkspaceContext";

const LIVE = {
  id: "req-live",
  workspace_id: "ws-001",
  title: "Live requirement",
  description: "",
  category: "functional",
  status: "draft",
  change_reason: "",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const OUTDATED = {
  ...LIVE,
  id: "req-outdated",
  title: "Soft-deleted requirement",
  status: "outdated",
};

function renderEditor(): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/requirements"]}>
        <AuthProvider>
          <WorkspaceProvider>
            <Routes>
              <Route path="/requirements" element={<RequirementEditors />} />
            </Routes>
          </WorkspaceProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequirementEditors — show-deleted toggle (GH-443)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(requirementsApi.listAll).mockImplementation(
      async (_workspaceId: string, options?: { includeDeleted?: boolean }) =>
        options?.includeDeleted ? [LIVE, OUTDATED] : [LIVE],
    );
  });

  it("loads without soft-deleted requirements by default", async () => {
    renderEditor();

    await waitFor(() => {
      expect(requirementsApi.listAll).toHaveBeenCalled();
    });

    expect(requirementsApi.listAll).toHaveBeenCalledWith(expect.any(String), {
      includeDeleted: false,
    });
    await waitFor(() => {
      expect(screen.getByText("Live requirement")).toBeInTheDocument();
    });
    expect(screen.queryByText("Soft-deleted requirement")).not.toBeInTheDocument();
  });

  it("refetches with include_deleted and surfaces the outdated requirement", async () => {
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId("req-list-include-deleted")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("req-list-include-deleted"));

    await waitFor(() => {
      expect(requirementsApi.listAll).toHaveBeenCalledWith(expect.any(String), {
        includeDeleted: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByText("Soft-deleted requirement")).toBeInTheDocument();
    });
  });
});
