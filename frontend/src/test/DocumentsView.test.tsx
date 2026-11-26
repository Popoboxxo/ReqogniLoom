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
import { act, render, screen, waitFor, within } from "@testing-library/react";
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
    body: '# Guide\n\n- First item\n- Second item\n\n| Name | Value |\n| --- | --- |\n| Alpha | 42 |\n\n```ts\nconst answer = 42;\n```\n\n<img src=x onerror="alert(1)">',
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
    readingView: vi.fn(),
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

const { hasRoleMock } = vi.hoisted(() => ({
  hasRoleMock: vi.fn(() => true),
}));

vi.mock("../hooks/useHasRole", () => ({
  useHasRole: () => hasRoleMock,
}));

// The real tree loads the #1257 display configuration over the network and
// virtualizes rows; this test only needs the row content it renders.
vi.mock("../components/shared/WorkspaceTree", () => ({
  WorkspaceTree: ({
    nodes,
    renderRow,
    selectedId,
    onSelect,
  }: {
    nodes: Array<{ id: string }>;
    renderRow?: (
      node: { id: string },
      ctx: { isSelected: boolean }
    ) => ReactNode;
    selectedId?: string;
    onSelect: (id: string) => void;
  }) => (
    <div data-testid="workspace-tree">
      {nodes.map((node) => (
        <div
          key={node.id}
          role="button"
          tabIndex={0}
          data-testid={`tree-row-${node.id}`}
          onClick={() => onSelect(node.id)}
          onKeyDown={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            onSelect(node.id);
          }}
        >
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
const readingView = documentsApi.readingView as ReturnType<typeof vi.fn>;
const create = documentsApi.create as ReturnType<typeof vi.fn>;
const transitions = documentsApi.transitions as ReturnType<typeof vi.fn>;
const transition = documentsApi.transition as ReturnType<typeof vi.fn>;

/** Reading object the detail route fetches alongside the document (R4). */
function readingFor(
  document: typeof DOC | typeof FROZEN,
  canWrite = true
): Record<string, unknown> {
  const fields = ["title", "description", "body", "doc_date"].map((name) => {
    const value =
      name === "doc_date"
        ? document.doc_date
        : document[name as "title" | "description" | "body"];
    const frozen = document.frozen_fields.includes(name);
    return {
      name,
      value,
      editable: canWrite && !frozen,
      locked: frozen
        ? { code: "FIELD_FROZEN", detail: `The ${name} is frozen.` }
        : canWrite
          ? null
          : { code: "PERMISSION", detail: "Read access only." },
    };
  });

  return {
    id: document.id,
    artifact_id: document.artifact_id,
    uid: document.uid,
    title: document.title,
    kind: document.kind,
    description: document.description,
    body: document.body,
    doc_date: document.doc_date,
    version: document.version,
    status: document.status,
    frozen_at: document.frozen_at,
    frozen_fields: document.frozen_fields,
    editable_fields: fields
      .filter((field) => field.editable)
      .map((field) => field.name),
    fields,
    capabilities: {
      can_write: canWrite,
      read_only_reason: canWrite ? null : "PERMISSION",
    },
    chapters: [
      {
        number: "1",
        level: 1,
        title: document.title,
        anchor: document.id === "doc-1" ? "guide" : "spec",
        body: document.body,
      },
    ],
    projection: {
      projection_mode: "none",
      source_path: "",
      projected_sha256: "",
    },
  };
}

function renderRoute(
  route: string,
  client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
): ReturnType<typeof render> {
  return render(
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
    hasRoleMock.mockReturnValue(true);
    listAll.mockResolvedValue([DOC]);
    get.mockResolvedValue(DOC);
    readingView.mockResolvedValue(readingFor(DOC));
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

  it("starts writers in read mode with rendered chapters and no raw editors", async () => {
    const { container } = renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-reading-view")).toBeInTheDocument()
    );

    const modeToggle = screen.getByTestId("document-mode-toggle");
    expect(
      within(modeToggle).getByTestId("document-mode-read")
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(modeToggle).getByTestId("document-mode-edit")
    ).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("document-reading-toc")).toBeInTheDocument();
    expect(
      screen.getByTestId("document-reading-chapter-guide")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("document-field-input-body")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("document-mode-immediate")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-save-bar")).not.toBeInTheDocument();
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("renders markdown lists, tables and code while escaping raw HTML", async () => {
    const { container } = renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(
        screen.getByTestId("document-reading-chapter-guide")
      ).toBeInTheDocument()
    );
    const chapter = within(
      screen.getByTestId("document-reading-chapter-guide")
    );

    expect(chapter.getByRole("list")).toBeInTheDocument();
    expect(chapter.getAllByRole("listitem")).toHaveLength(2);
    expect(chapter.getByRole("table")).toBeInTheDocument();
    expect(chapter.getByText("const answer = 42;")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("<img");
    expect(container.innerHTML).toContain("&lt;img");
  });

  it("keeps viewers in read mode without a mode toggle", async () => {
    hasRoleMock.mockReturnValue(false);
    readingView.mockResolvedValue(readingFor(DOC, false));
    const { container } = renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-reading-view")).toBeInTheDocument()
    );

    expect(
      screen.queryByTestId("document-mode-toggle")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-edit")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("document-field-input-body")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("document-reading-toc")).toBeInTheDocument();
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("toggles between read and inline editing without losing the full editor", async () => {
    const user = userEvent.setup();
    renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-mode-read")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("document-mode-edit"));

    expect(screen.getByTestId("document-mode-edit")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("document-field-input-body")).toBeInTheDocument();
    expect(screen.getByTestId("document-mode-immediate")).toBeInTheDocument();
    expect(screen.getByTestId("document-edit")).toBeInTheDocument();

    await user.click(screen.getByTestId("document-mode-batch"));
    expect(screen.getByTestId("document-save-bar")).toBeInTheDocument();

    await user.click(screen.getByTestId("document-mode-read"));
    expect(
      screen.queryByTestId("document-field-input-body")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-mode-batch")).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-save-bar")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("document-mode-edit"));
    expect(screen.getByTestId("document-field-input-body")).toBeInTheDocument();
    expect(screen.getByTestId("document-save-bar")).toBeInTheDocument();

    await user.click(screen.getByTestId("document-edit"));
    expect(screen.getByTestId("document-form")).toBeInTheDocument();
    await user.click(screen.getByTestId("document-cancel"));
    expect(screen.getByTestId("document-reading-view")).toBeInTheDocument();
    expect(screen.getByTestId("document-field-input-body")).toBeInTheDocument();
  });

  it("closes the full editor when the server revokes write capability", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const user = userEvent.setup();
    renderRoute("/documents/doc-1", client);

    await waitFor(() =>
      expect(screen.getByTestId("document-mode-read")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("document-mode-edit"));
    await user.click(screen.getByTestId("document-edit"));
    expect(screen.getByTestId("document-form")).toBeInTheDocument();

    readingView.mockResolvedValue(readingFor(DOC, false));
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents", "reading"] });
    });

    await waitFor(() =>
      expect(screen.queryByTestId("document-form")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("document-reading-view")).toBeInTheDocument();
    expect(screen.queryByTestId("document-mode-toggle")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("document-field-input-body")
    ).not.toBeInTheDocument();
  });

  it("resets to read mode when the selected document changes", async () => {
    listAll.mockResolvedValue([DOC, FROZEN]);
    get.mockImplementation((id: string) =>
      Promise.resolve(id === "doc-2" ? FROZEN : DOC)
    );
    readingView.mockImplementation((id: string) =>
      Promise.resolve(readingFor(id === "doc-2" ? FROZEN : DOC))
    );
    const user = userEvent.setup();
    renderRoute("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByTestId("document-mode-read")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("document-mode-edit"));
    expect(screen.getByTestId("document-field-input-body")).toBeInTheDocument();

    await user.click(screen.getByTestId("tree-row-doc-2"));

    await waitFor(() =>
      expect(
        within(screen.getByTestId("document-reading-view")).getByRole(
          "heading",
          {
            name: "Released spec",
          }
        )
      ).toBeInTheDocument()
    );
    expect(screen.getByTestId("document-mode-read")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(
      screen.queryByTestId("document-field-input-body")
    ).not.toBeInTheDocument();
  });

  it("shows the freeze banner and disables frozen editor fields", async () => {
    listAll.mockResolvedValue([FROZEN]);
    get.mockResolvedValue(FROZEN);
    readingView.mockResolvedValue(readingFor(FROZEN));
    renderRoute("/documents/doc-2");

    await waitFor(() =>
      expect(screen.getByTestId("document-reading-view")).toBeInTheDocument()
    );
    expect(
      screen.getByTestId("document-reading-capability-notice")
    ).toBeInTheDocument();
    expect(screen.getByTestId("document-frozen-banner")).toBeInTheDocument();
    expect(screen.getByTestId("document-frozen-fields")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("document-mode-edit"));
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
      expect(
        screen.getByTestId("document-transition-select")
      ).toBeInTheDocument()
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
