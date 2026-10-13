/**
 * Regression guard for issue #1256: after a successful Save on an artifact
 * detail page, `VersionPanel` must show the new version without a manual
 * reload — for both Requirement and Architecture.
 *
 * The save path already adopts the server response as truth (previous fix),
 * and the page's detail query is invalidated, so `currentVersion` changes.
 * `VersionPanel`, however, is not TanStack-Query bound: its version list is
 * fetched directly and was keyed only on `[kind, artifactId]`, so the list
 * stayed stale. These tests pin that the panel refetches once the artifact's
 * `currentVersion` moves and renders the newly created version row.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { i18n } from "../i18n/index";

vi.mock("../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../api/client")>()),
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
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    versions: vi.fn(),
    diff: vi.fn(),
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "draft",
      states: ["draft"],
      allowed_transitions: [],
      proposed_by: null,
    }),
    transition: vi.fn(),
    aiDecomposeNextLevel: vi.fn().mockResolvedValue({
      drafts: [],
      parent_requirement_id: "req-001",
    }),
  },
}));

vi.mock("../api/architecture", () => ({
  architectureApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    listAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    reparent: vi.fn(),
    versions: vi.fn(),
    diff: vi.fn(),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(),
    listAll: vi.fn().mockResolvedValue([]),
    downloadPdfReport: vi.fn(),
  },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: { list: vi.fn(), get: vi.fn() },
}));

vi.mock("../api/adrs", () => ({
  adrsApi: { get: vi.fn() },
}));

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn(), getSchema: vi.fn() },
}));

vi.mock("../api/memory", () => ({
  memoryApi: {
    listArtifactMemory: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      backend: "pgvector",
      degraded: false,
    }),
    createArtifactMemory: vi.fn(),
    forgetEntry: vi.fn(),
  },
}));

vi.mock("../api/interviews", () => ({
  interviewsApi: {
    getProvenance: vi.fn().mockResolvedValue({ session_id: null }),
  },
}));

vi.mock("../api/comments", () => ({
  commentsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    resolve: vi.fn(),
    remove: vi.fn(),
  },
}));

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

import RequirementEditors from "../components/RequirementEditors/RequirementEditors";
import ArchitectureEditors from "../components/ArchitectureEditors/ArchitectureEditors";
import { requirementsApi } from "../api/requirements";
import { architectureApi } from "../api/architecture";
import { tracelinksApi } from "../api/tracelinks";
import { testcasesApi } from "../api/testcases";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import type { ArtifactVersion } from "../types";

function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}
installLocalStorageStub();

function attr(over: Record<string, unknown>) {
  return {
    kind: "core", widget_key: null, fields: [], options: [], required: false,
    visible: true, locked: false, editable: true, section: "general", order: 1,
    label: { de: "", en: "" }, help_text: { de: "", en: "" }, default: null,
    validation: {}, ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

const REQUIREMENT_V1 = {
  id: "req-001",
  workspace_id: "00000000-0000-0000-0000-000000000000",
  title: "Login",
  description: "",
  category: "functional",
  status: "draft",
  change_reason: "",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const ARCH_V1 = {
  id: "arch-001",
  workspace_id: "00000000-0000-0000-0000-000000000000",
  title: "AuthService",
  description: "",
  element_type: "component",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const V1: ArtifactVersion = {
  version: 1,
  label: "v1",
  modified_at: "2026-01-01T00:00:00Z",
};
const V2: ArtifactVersion = {
  version: 2,
  label: "v2",
  modified_at: "2026-01-02T00:00:00Z",
};

function renderAt(path: string, element: JSX.Element): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <Routes>
                <Route path="/requirements/:id" element={element} />
                <Route path="/architecture/:id" element={element} />
              </Routes>
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  void i18n.changeLanguage("en");
  window.localStorage.setItem("reqflow_inspector_collapsed_requirement", "false");
  window.localStorage.setItem("reqflow_inspector_collapsed_architecture", "false");

  vi.mocked(attributeDefinitionsApi.getWorkspace).mockImplementation(
    async (itemType: string) => ({
      item_type: itemType,
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [attr({ name: "title", type: "text", required: true, order: 1 })],
    }) as never
  );
  vi.mocked(attributeDefinitionsApi.getSchema).mockResolvedValue([]);
  vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(testcasesApi.list).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
  vi.mocked(architectureApi.listAll).mockResolvedValue([]);
  vi.mocked(requirementsApi.diff).mockResolvedValue({
    from_version: 0,
    to_version: 1,
    entity_type: "requirement",
    fields: [],
  } as never);
  vi.mocked(architectureApi.diff).mockResolvedValue({
    from_version: 0,
    to_version: 1,
    entity_type: "architecture",
    fields: [],
  } as never);
});

describe("VersionPanel refresh after save (#1256)", () => {
  it("Requirement: shows the new version row after a successful save", async () => {
    let versionList: ArtifactVersion[] = [V1];
    vi.mocked(requirementsApi.versions).mockImplementation(async () => versionList);
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [REQUIREMENT_V1],
      count: 1,
    } as never);
    vi.mocked(requirementsApi.get)
      .mockResolvedValueOnce(REQUIREMENT_V1 as never)
      .mockResolvedValue({ ...REQUIREMENT_V1, version: 2 } as never);
    vi.mocked(requirementsApi.update).mockResolvedValue({
      ...REQUIREMENT_V1,
      version: 2,
    } as never);

    renderAt("/requirements/req-001", <RequirementEditors />);

    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(screen.getByTestId("version-row-1")).toBeInTheDocument()
    );

    versionList = [V1, V2];

    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() =>
      expect(requirementsApi.update).toHaveBeenCalledTimes(1)
    );
    await waitFor(() =>
      expect(screen.getByTestId("version-row-2")).toBeInTheDocument()
    );
  });

  it("Architecture: shows the new version row after a successful save", async () => {
    let versionList: ArtifactVersion[] = [V1];
    vi.mocked(architectureApi.versions).mockImplementation(async () => versionList);
    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [ARCH_V1],
      count: 1,
    } as never);
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    } as never);
    vi.mocked(architectureApi.get)
      .mockResolvedValueOnce(ARCH_V1 as never)
      .mockResolvedValue({ ...ARCH_V1, version: 2 } as never);
    vi.mocked(architectureApi.update).mockResolvedValue({
      ...ARCH_V1,
      version: 2,
    } as never);

    renderAt("/architecture/arch-001", <ArchitectureEditors />);

    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(screen.getByTestId("version-row-1")).toBeInTheDocument()
    );

    versionList = [V1, V2];

    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() =>
      expect(architectureApi.update).toHaveBeenCalledTimes(1)
    );
    await waitFor(() =>
      expect(screen.getByTestId("version-row-2")).toBeInTheDocument()
    );
  });
});
