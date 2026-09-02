/**
 * REQ-L2-AI-001 / REQ-L2-AI-002: NeedForm — AI derive Draft/Accept flow.
 *
 * "Ableiten" on a Stakeholder Need must propose system requirement drafts and
 * let the user persist the selected ones. Previously the button dispatched a
 * fire-and-forget Celery task whose result was never persisted, so no
 * requirement ever appeared.
 *
 * Covered here:
 * - Drafts returned by the backend are rendered for review.
 * - Accepting persists each selected draft via requirementsApi.create and
 *   links it back to the need with a 'derives-from' TraceLink.
 * - Deselected drafts are not persisted.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        "needs.deriveStarting": "KI-Ableitung wird gestartet...",
        "needs.deriveFailed": "Ableitung fehlgeschlagen.",
        "needs.deriveEmpty": "Keine Vorschläge erhalten.",
        "actions.derive": "Ableiten",
        "actions.deriving": "Leitet ab...",
        "deriveRequirements.title": "Systemanforderungen (Entwurf)",
        "deriveRequirements.accept": "Ausgewählte anlegen",
        "deriveRequirements.accepting": "Wird angelegt...",
        "deriveRequirements.discard": "Verwerfen",
        "deriveRequirements.created": `${opts?.count ?? 0} Anforderungen angelegt.`,
      };
      return map[key] ?? key;
    },
    i18n: { language: "de" },
  }),
}));

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
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../api/stakeholder-need", () => ({
  stakeholderNeedApi: {
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
    deriveRequirements: vi.fn(),
  },
}));

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    create: vi.fn(),
  },
}));

vi.mock("../../api/architecture", () => ({
  architectureApi: { listAll: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    create: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../api/artifactRefs", () => ({
  resolveArtifactRefs: vi.fn().mockResolvedValue({}),
}));

vi.mock("../../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    get: vi.fn().mockResolvedValue(null),
  },
}));

vi.mock("../../api/attribute-visibility", () => ({
  attributeVisibilityApi: { list: vi.fn().mockResolvedValue([]) },
}));

// Must import AFTER vi.mock
import { NeedForm } from "./NeedForm";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import { AuthProvider } from "../../context/AuthContext";
import { WorkspaceProvider } from "../../context/WorkspaceContext";
import { ThemeProvider } from "../../context/ThemeContext";
import type { StakeholderNeed } from "../../types";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
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

const MOCK_NEED: StakeholderNeed = {
  id: "need-001",
  workspace_id: "ws-001",
  artifact_id: "art-001",
  title: "Als Nutzer möchte ich ...",
  description: "",
  category: "",
  status: "draft",
  moscow_priority: undefined,
  uid: "SN-001",
  suspect: false,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
};

const DRAFTS = [
  {
    title: "SysReq A",
    description: "Beschreibung A",
    rationale: "weil A",
    suggested_parent_id: "need-001",
  },
  {
    title: "SysReq B",
    description: "Beschreibung B",
    rationale: "weil B",
    suggested_parent_id: "need-001",
  },
];

const renderForm = (onNeedsChanged?: () => void) => {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <NeedForm
                need={MOCK_NEED}
                onSaved={vi.fn()}
                onDeleted={vi.fn()}
                onNeedsChanged={onNeedsChanged}
              />
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

const clickDerive = async () => {
  const btn = await screen.findByRole("button", { name: /Ableiten/i });
  await userEvent.click(btn);
};

describe("NeedForm — AI derive Draft/Accept (REQ-L2-AI-002)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("renders the returned drafts for review instead of a fake success message", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({
      drafts: DRAFTS,
    });

    renderForm();
    await clickDerive();

    expect(await screen.findByTestId("derive-requirements-panel")).toBeInTheDocument();
    expect(screen.getByTestId("derive-requirements-title-0")).toHaveValue("SysReq A");
    expect(screen.getByTestId("derive-requirements-title-1")).toHaveValue("SysReq B");
  });

  it("persists accepted drafts and links them back to the need", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({
      drafts: DRAFTS,
    });
    vi.mocked(requirementsApi.create)
      .mockResolvedValueOnce({ id: "req-a" } as never)
      .mockResolvedValueOnce({ id: "req-b" } as never);

    const onNeedsChanged = vi.fn();
    renderForm(onNeedsChanged);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    expect(requirementsApi.create).toHaveBeenCalledTimes(2);
    expect(requirementsApi.create).toHaveBeenCalledWith({
      workspace_id: "ws-001",
      title: "SysReq A",
      description: "Beschreibung A",
    });
    expect(tracelinksApi.create).toHaveBeenCalledWith({
      source_id: "req-a",
      target_id: "art-001",
      link_type: "derives-from",
    });
    expect(tracelinksApi.create).toHaveBeenCalledWith({
      source_id: "req-b",
      target_id: "art-001",
      link_type: "derives-from",
    });
    expect(onNeedsChanged).toHaveBeenCalled();
  });

  it("skips drafts the user deselected", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({
      drafts: DRAFTS,
    });
    vi.mocked(requirementsApi.create).mockResolvedValue({ id: "req-b" } as never);

    renderForm();
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-select-0"));
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    expect(requirementsApi.create).toHaveBeenCalledTimes(1);
    expect(requirementsApi.create).toHaveBeenCalledWith({
      workspace_id: "ws-001",
      title: "SysReq B",
      description: "Beschreibung B",
    });
  });

  it("reports an empty proposal set instead of claiming success", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({
      drafts: [],
    });

    renderForm();
    await clickDerive();

    const status = await screen.findByTestId("need-derive-status");
    expect(status.textContent).toContain("Keine Vorschläge");
    expect(screen.queryByTestId("derive-requirements-panel")).not.toBeInTheDocument();
  });
});
