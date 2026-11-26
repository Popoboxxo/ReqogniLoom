import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import type { WorkspacePreset } from "../../types";
import { WorkflowEditorPage } from "./WorkflowEditorPage";
import { workflowKeys } from "./useWorkflowData";

const mocks = vi.hoisted(() => ({
  activeWorkspace: {
    id: "11111111-1111-1111-1111-111111111111",
    preset: "standard" as WorkspacePreset,
  },
  roles: ["admin"],
  useWorkflowData: vi.fn(),
  useWorkflowMutations: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (key === "workflow.invalidEntity.message") {
        return `Unknown workflow type: ${String(values?.slug ?? "")}`;
      }
      return key.replace(/\{\{(\w+)\}\}/g, (_match, name: string) =>
        String(values?.[name] ?? "")
      );
    },
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: mocks.activeWorkspace,
    isLoadingWorkspace: false,
  }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: mocks.roles }),
}));

vi.mock("./useWorkflowData", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./useWorkflowData")>();
  return { ...actual, useWorkflowData: mocks.useWorkflowData };
});

vi.mock("./useWorkflowMutations", () => ({
  useWorkflowMutations: mocks.useWorkflowMutations,
}));

const mutationMocks = {
  busy: false,
  error: null,
  clearError: vi.fn(),
  addState: vi.fn(),
  renameState: vi.fn(),
  deleteState: vi.fn(),
  setStateFreeze: vi.fn(),
  addTransition: vi.fn(),
  updateTransition: vi.fn(),
  deleteTransition: vi.fn(),
  initialize: vi.fn(),
};

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function renderPage(path: string, scope: "workspace" | "global" = "workspace") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const page = <WorkflowEditorPage scope={scope} />;
  const makeUi = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/workflows" element={page} />
          <Route path="/workflows/:entityType" element={page} />
          <Route path="/system-settings" element={page} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(makeUi());
  return {
    ...view,
    client,
    rerenderPage: () => view.rerender(makeUi()),
  };
}

describe("WorkflowEditorPage routing and scope", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.activeWorkspace.preset = "standard";
    mocks.roles = ["admin"];
    mocks.useWorkflowData.mockReturnValue({
      graph: null,
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });
    mocks.useWorkflowMutations.mockReturnValue(mutationMocks);
  });

  it("shows a validation error for an unknown workspace slug without querying Requirement", () => {
    renderPage("/workflows/not-a-real-type");

    expect(screen.getByTestId("workflow-invalid-entity")).toHaveAttribute(
      "role",
      "alert"
    );
    expect(screen.getByTestId("workflow-invalid-entity")).toHaveTextContent(
      "not-a-real-type"
    );
    expect(screen.getByTestId("workflow-invalid-entity-back")).toHaveAttribute(
      "href",
      "/workflows"
    );
    expect(mocks.useWorkflowData).not.toHaveBeenCalled();
    expect(mocks.useWorkflowMutations).not.toHaveBeenCalled();
  });

  it("shows a validation error for an unknown global entityType parameter", () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=not-a-real-type",
      "global"
    );

    expect(screen.getByTestId("workflow-invalid-entity")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-invalid-entity-back")).toHaveAttribute(
      "href",
      "/system-settings?tab=workflow-defaults"
    );
    expect(mocks.useWorkflowData).not.toHaveBeenCalled();
  });

  it("renders Document and WorkItem in the workspace selector", () => {
    renderPage("/workflows/Requirement");

    expect(screen.getByTestId("workflow-entity-Document")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-entity-WorkItem")).toBeInTheDocument();
  });

  it("falls back to the default entity when the workspace route carries no slug", () => {
    renderPage("/workflows");

    expect(screen.queryByTestId("workflow-invalid-entity")).not.toBeInTheDocument();
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("Requirement", {
      kind: "workspace",
      workspaceId: mocks.activeWorkspace.id,
      preset: "standard",
    });
  });

  it("canonicalises the resolved global preset in the address bar", async () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=Document&preset=minimal",
      "global"
    );

    await waitFor(() => {
      const search = screen.getByTestId("location-search").textContent ?? "";
      expect(search).toContain("entityType=Document");
      expect(search).toContain("preset=document_default");
      expect(search).not.toContain("preset=minimal");
    });
  });

  it("normalizes Document globals to document_default and offers no generic preset tabs", async () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=Document&preset=minimal",
      "global"
    );

    await waitFor(() =>
      expect(mocks.useWorkflowData).toHaveBeenCalledWith("Document", {
        kind: "global",
        preset: "document_default",
      })
    );
    expect(mocks.useWorkflowData).not.toHaveBeenCalledWith("Document", {
      kind: "global",
      preset: "minimal",
    });
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("Requirement", {
      kind: "global",
      preset: "standard",
    });
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("WorkItem", {
      kind: "global",
      preset: "work_item_standard",
    });
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("StakeholderNeed", {
      kind: "global",
      preset: "need_default",
    });
    expect(mocks.useWorkflowData).not.toHaveBeenCalledWith("Requirement", {
      kind: "global",
      preset: "document_default",
    });
    expect(screen.queryByTestId("workflow-preset-selector")).not.toBeInTheDocument();
    expect(screen.getByTestId("workflow-preset-badge")).toHaveTextContent(
      "document_default"
    );
  });

  it("offers only work_item_* tabs for WorkItem globals", () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=WorkItem&preset=work_item_extended",
      "global"
    );

    expect(screen.getByTestId("workflow-preset-option-work_item_minimal")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-preset-option-work_item_standard")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-preset-option-work_item_extended")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-preset-option-minimal")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-preset-option-standard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-preset-option-extended")).not.toBeInTheDocument();
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("Requirement", {
      kind: "global",
      preset: "extended",
    });
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("Document", {
      kind: "global",
      preset: "document_default",
    });
  });

  it("keeps the three rigor tabs for Requirement globals", () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=Requirement&preset=extended",
      "global"
    );

    expect(screen.getByTestId("workflow-preset-option-minimal")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-preset-option-standard")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-preset-option-extended")).toBeInTheDocument();
  });

  it("shows a visible link from workspace management to System Settings workflow defaults", () => {
    renderPage("/workflows/Requirement");

    expect(screen.getByTestId("workflow-scope-notice")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-global-defaults-link")).toHaveAttribute(
      "href",
      "/system-settings?tab=workflow-defaults"
    );
  });

  it("shows a visible link from global defaults back to workspace management", () => {
    renderPage(
      "/system-settings?tab=workflow-defaults&entityType=Requirement",
      "global"
    );

    expect(screen.getByTestId("workflow-scope-notice")).toBeInTheDocument();
    expect(
      screen.getByTestId("workflow-workspace-definitions-link")
    ).toHaveAttribute("href", "/workflows");
    expect(
      screen.queryByTestId("workflow-global-defaults-link")
    ).not.toBeInTheDocument();
  });

  it("invalidates the workspace workflow cache when the active preset changes", async () => {
    const { client, rerenderPage } = renderPage("/workflows/Requirement");
    const invalidate = vi.spyOn(client, "invalidateQueries");

    mocks.activeWorkspace.preset = "extended";
    rerenderPage();

    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: workflowKeys.workspace(mocks.activeWorkspace.id),
      })
    );
    expect(mocks.useWorkflowData).toHaveBeenCalledWith("Requirement", {
      kind: "workspace",
      workspaceId: mocks.activeWorkspace.id,
      preset: "extended",
    });
  });
});
