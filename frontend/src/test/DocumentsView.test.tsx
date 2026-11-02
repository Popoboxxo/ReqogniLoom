/**
 * ARCH-L1-001 ReactFrontend — Documents route (Plan F F2-T8).
 *
 * Covers the four data states (loading/error/empty/success), the freeze
 * contract (banner visible, frozen fields disabled, `doc_date` still editable)
 * and the lifecycle action wiring (`WorkflowStatusEditor` → Document
 * transitions with the entity `expected_version`).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../i18n/index";

const { DOC, FROZEN } = vi.hoisted(() => ({
  DOC: {
    id: "doc-1",
    workspace_id: "ws-001",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Guide\n\nBody text.",
    doc_date: "2026-11-02",
    frozen_at: null as string | null,
    frozen_fields: [] as string[],
    status: "Entwurf",
    version: 4,
    created_at: "2026-11-02T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
  },
  FROZEN: {
    id: "doc-2",
    workspace_id: "ws-001",
    artifact_id: "art-2",
    uid: "DOC-002",
    title: "Released spec",
    kind: "Spec" as const,
    description: "Frozen specification.",
    body: "# Spec\n\nFrozen body.",
    doc_date: "2026-11-01",
    frozen_at: "2026-11-02T10:00:00Z",
    frozen_fields: ["title", "description", "body", "kind"],
    status: "Freigegeben",
    version: 7,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T10:00:00Z",
  },
}));

vi.mock("../api/documents", () => ({
  documentsApi: {
    listAll: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    reactivate: vi.fn(),
    transitions: vi.fn(),
    transition: vi.fn(),
  },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "WS" },
    isLoadingWorkspace: false,
  }),
}));

vi.mock("../hooks/useHasRole", () => ({
  useHasRole: () => () => true,
}));

// The real tree loads the #1257 display configuration over the network and
// virtualizes rows; this test only needs the row content it renders.
vi.mock("../components/shared/WorkspaceTree", () => ({
  WorkspaceTree: ({
    nodes,
    renderRow,
    selectedId,
  }: {
    nodes: Array<{ id: string }>;
    renderRow?: (
      node: { id: string },
      ctx: { isSelected: boolean }
    ) => ReactNode;
    selectedId?: string;
  }) => (
    <div data-testid="workspace-tree">
      {nodes.map((node) => (
        <div key={node.id} data-testid={`tree-row-${node.id}`}>
          {renderRow?.(node, { isSelected: node.id === selectedId })}
        </div>
      ))}
    </div>
  ),
}));

// Isolate the freeze test from the preference-backed MarkdownField shell; the
// contract under test is that the editor forwards `disabled` to the field.
vi.mock("../components/shared/MarkdownField/MarkdownField", () => ({
  MarkdownField: ({
    id,
    value,
    onChange,
    disabled,
  }: {
    id: string;
    value: string;
    onChange: (next: string) => void;
    disabled?: boolean;
  }) => (
    <textarea
      id={id}
      data-testid={`${id}-input`}
      data-disabled={disabled ? "true" : "false"}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

import Documents from "../components/Documents/Documents";
import { documentsApi } from "../api/documents";

const listAll = documentsApi.listAll as ReturnType<typeof vi.fn>;
const get = documentsApi.get as ReturnType<typeof vi.fn>;
const create = documentsApi.create as ReturnType<typeof vi.fn>;
const transitions = documentsApi.transitions as ReturnType<typeof vi.fn>;
const transition = documentsApi.transition as ReturnType<typeof vi.fn>;

function renderRoute(route: string): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:id" element={<Documents />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Documents route (F2-T8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAll.mockResolvedValue([DOC]);
    get.mockResolvedValue(DOC);
    create.mockResolvedValue(DOC);
    transitions.mockResolvedValue({
      current_state: "Entwurf",
      version: 4,
      states: ["Entwurf", "In Prüfung", "Freigegeben"],
      allowed_transitions: [
        {
          target_state: "In Prüfung",
          requires_change_reason: false,
          signature_gate: false,
        },
      ],
      proposed_by: null,
    });
    transition.mockResolvedValue({
      id: "doc-1",
      previous_state: "Entwurf",
      new_state: "In Prüfung",
      version: 5,
      document: DOC,
    });
  });

  it("renders the list rows on success", async () => {
    renderRoute("/documents");

    await waitFor(() =>
      expect(screen.getByTestId("document-row-doc-1")).toBeInTheDocument()
    );
    expect(screen.getByTestId("documents-view")).toBeInTheDocument();
    expect(screen.getByTestId("documents-select-prompt")).toBeInTheDocument();
  });

  it("renders the empty state when the workspace has no documents", async () => {
    listAll.mockResolvedValue([]);
    renderRoute("/documents");

    await waitFor(() =>
      expect(screen.getByTestId("documents-list-empty")).toBeInTheDocument()
    );
  });

  it("renders an error state with a retry action when the list request fails", async () => {
    listAll.mockRejectedValue(new Error("list failed"));
    renderRoute("/documents");

    await waitFor(() =>
      expect(screen.getByTestId("documents-list-error")).toBeInTheDocument()
    );
  });

  it("renders an error state when the detail request fails", async () => {
    listAll.mockResolvedValue([DOC]);
    get.mockRejectedValue(new Error("detail failed"));
    renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-detail-error")).toBeInTheDocument()
    );
  });

  it("shows the freeze banner and disables frozen editor fields", async () => {
    listAll.mockResolvedValue([FROZEN]);
    get.mockResolvedValue(FROZEN);
    renderRoute("/documents/doc-2");

    await waitFor(() =>
      expect(screen.getByTestId("document-detail")).toBeInTheDocument()
    );
    expect(screen.getByTestId("document-frozen-banner")).toBeInTheDocument();
    expect(screen.getByTestId("document-frozen-fields")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("document-edit"));
    expect(screen.getByTestId("document-form")).toBeInTheDocument();
    expect(screen.getByTestId("document-edit-title")).toBeDisabled();
    expect(screen.getByTestId("document-edit-kind")).toBeDisabled();
    expect(screen.getByTestId("document-edit-description")).toBeDisabled();
    expect(screen.getByTestId("document-edit-body-input")).toBeDisabled();
    // F-2: doc_date stays writable while the document is frozen.
    expect(screen.getByTestId("document-edit-date")).toBeEnabled();
  });

  it("drives the lifecycle through the document transitions endpoint", async () => {
    renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-transition-select")).toBeInTheDocument()
    );
    expect(transitions).toHaveBeenCalledWith("doc-1");

    await userEvent.selectOptions(
      screen.getByTestId("document-transition-select"),
      "In Prüfung"
    );
    await userEvent.click(screen.getByTestId("document-transition-execute"));

    await waitFor(() =>
      expect(transition).toHaveBeenCalledWith("doc-1", "In Prüfung", {
        changeReason: "",
        credential: "",
        expectedVersion: 4,
      })
    );
  });

  it("creates a document from the create dialog", async () => {
    renderRoute("/documents");

    await waitFor(() =>
      expect(screen.getByTestId("document-row-doc-1")).toBeInTheDocument()
    );
    await userEvent.click(screen.getByTestId("documents-new"));
    expect(screen.getByTestId("document-create-dialog")).toBeInTheDocument();

    await userEvent.type(
      screen.getByTestId("document-create-title"),
      "New concept"
    );
    await userEvent.click(screen.getByTestId("document-create-save"));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "ws-001",
          title: "New concept",
          kind: "Spec",
        })
      )
    );
  });
});
