/**
 * R5.1 — inline document field editing (plan
 * 2026-11-15-document-view-on-document.md).
 *
 * Covers the write contract of the reading surface: only fields the server
 * reports as editable get a writable control, a single-field save carries the
 * strong `If-Match` precondition, a lost precondition marks exactly that field
 * and offers a reload, a frozen field is disabled with its reason, a successful
 * save advances the rendered version, and a 400 with `details[].field` shows
 * the server message at the field.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../i18n/index";

const { DOCUMENT, READING } = vi.hoisted(() => ({
  DOCUMENT: {
    id: "doc-1",
    workspace_id: "ws-001",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Overview\n\nFirst chapter.",
    doc_date: "2026-11-02",
    frozen_at: null as string | null,
    frozen_fields: [] as string[],
    status: "Entwurf",
    version: 4,
    created_at: "2026-11-02T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
  },
  READING: {
    id: "doc-1",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Overview\n\nFirst chapter.",
    doc_date: "2026-11-02",
    version: 4,
    status: "Entwurf",
    frozen_at: null as string | null,
    frozen_fields: [] as string[],
    editable_fields: ["title", "description", "body"],
    fields: [] as Array<{
      name: string;
      value: unknown;
      editable: boolean;
      locked: { code: string; detail: string } | null;
    }>,
    capabilities: { can_write: true, read_only_reason: null as string | null },
    chapters: [
      {
        number: "1",
        level: 1,
        title: "Overview",
        anchor: "overview",
        body: "First chapter.",
      },
    ],
    projection: {
      projection_mode: "none",
      source_path: "",
      projected_sha256: "",
    },
  },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: undefined,
    isLoadingWorkspace: false,
  }),
}));

vi.mock("../api/documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/documents")>();
  return {
    ...actual,
    documentsApi: { ...actual.documentsApi, updateField: vi.fn() },
  };
});

vi.mock("../api/artifacts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/artifacts")>();
  return {
    ...actual,
    artifactsApi: { ...actual.artifactsApi, bulkUpdate: vi.fn() },
  };
});

import { DocumentReadingView } from "../components/Documents/DocumentReadingView";
import { documentsApi } from "../api/documents";
import type { DocumentReading } from "../types";

const updateField = documentsApi.updateField as ReturnType<typeof vi.fn>;

const EDITABLE_FIELDS = [
  { name: "title", value: "Architecture guide", editable: true, locked: null },
  {
    name: "description",
    value: "How the system is put together.",
    editable: true,
    locked: null,
  },
  { name: "body", value: "# Overview", editable: true, locked: null },
  {
    name: "doc_date",
    value: "2026-11-02",
    editable: false,
    locked: { code: "PERMISSION", detail: "Only an editor may set the date." },
  },
];

function makeReading(
  overrides: Partial<DocumentReading> = {}
): DocumentReading {
  return {
    ...READING,
    fields: EDITABLE_FIELDS,
    ...overrides,
  } as DocumentReading;
}

function renderView(
  reading: DocumentReading,
  onReload: () => void = vi.fn()
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }
  return render(
    <Wrapper>
      <DocumentReadingView
        document={DOCUMENT}
        reading={reading}
        onEdit={vi.fn()}
        onReload={onReload}
      />
    </Wrapper>
  );
}

describe("DocumentFieldEditor (R5.1)", () => {
  beforeEach(() => {
    updateField.mockReset();
  });

  it("edit_enabled_only_for_editable_fields", () => {
    renderView(makeReading());

    expect(
      screen.getByTestId("document-field-input-title")
    ).not.toHaveAttribute("readonly");
    expect(
      screen.getByTestId("document-field-input-description")
    ).not.toHaveAttribute("readonly");
    // The server reports `doc_date` as not editable: the control stays
    // readable but never accepts a write.
    expect(screen.getByTestId("document-field-input-doc_date")).toHaveAttribute(
      "readonly"
    );
  });

  it("patch_sends_if_match_header", async () => {
    // This case asserts the wire contract, not the React wiring: the real
    // `documentsApi` runs (unmocked through `importActual`) against a stubbed
    // fetch, so the header string itself is under test.
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...DOCUMENT, version: 5 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    try {
      const { documentsApi: realApi } = await vi.importActual<
        typeof import("../api/documents")
      >("../api/documents");

      await realApi.updateField("doc-1", "title", "New title", 4);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as [
        string,
        RequestInit & { headers: Record<string, string> },
      ];
      expect(url).toBe("/api/v1/documents/doc-1/");
      expect(init.method).toBe("PATCH");
      expect(init.headers["If-Match"]).toBe('"4"');
      expect(JSON.parse(init.body as string)).toEqual({ title: "New title" });
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("successful_save_updates_version", async () => {
    updateField.mockResolvedValue({ ...DOCUMENT, version: 5 });
    const user = userEvent.setup();
    renderView(makeReading());

    const input = screen.getByTestId("document-field-input-title");
    await user.clear(input);
    await user.type(input, "Renamed guide");
    await user.click(screen.getByTestId("document-field-save-title"));

    await waitFor(() => {
      expect(updateField).toHaveBeenCalledWith(
        "doc-1",
        "title",
        "Renamed guide",
        4
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("document-detail-version")).toHaveTextContent(
        "v5"
      );
    });
  });

  it("conflict_marks_field_orange_and_offers_reload", async () => {
    updateField.mockRejectedValue({
      error: {
        code: "PRECONDITION_FAILED",
        message: "The document changed in the meantime.",
        details: [],
      },
    });
    const onReload = vi.fn();
    const user = userEvent.setup();
    renderView(makeReading(), onReload);

    const input = screen.getByTestId("document-field-input-title");
    await user.type(input, "Renamed guide");
    await user.click(screen.getByTestId("document-field-save-title"));

    // Exactly this field is marked — the untouched description is not.
    const conflict = await screen.findByTestId("document-field-conflict-title");
    expect(conflict).toHaveTextContent(/changed in the meantime/i);
    expect(screen.getByTestId("document-field-input-title")).toHaveAttribute(
      "aria-invalid",
      "true"
    );
    expect(
      screen.queryByTestId("document-field-conflict-description")
    ).not.toBeInTheDocument();

    await user.click(screen.getByTestId("document-field-reload-title"));
    expect(onReload).toHaveBeenCalled();
  });

  it("frozen_field_is_disabled_with_reason", () => {
    renderView(
      makeReading({
        frozen_at: "2026-11-02T10:00:00Z",
        frozen_fields: ["title"],
        fields: [
          {
            name: "title",
            value: "Architecture guide",
            editable: false,
            locked: {
              code: "FIELD_FROZEN",
              detail: "The title is frozen after release.",
            },
          },
        ],
      })
    );

    const input = screen.getByTestId("document-field-input-title");
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute("title", "The title is frozen after release.");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      "The title is frozen after release."
    );
    // A frozen field offers no save affordance at all.
    expect(
      screen.queryByTestId("document-field-save-title")
    ).not.toBeInTheDocument();
  });

  it("validation_error_is_shown_at_the_field", async () => {
    updateField.mockRejectedValue({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed",
        details: [{ field: "title", errors: ["This title is too long."] }],
      },
    });
    const user = userEvent.setup();
    renderView(makeReading());

    const input = screen.getByTestId("document-field-input-title");
    await user.type(input, "A very long title");
    await user.click(screen.getByTestId("document-field-save-title"));

    expect(await screen.findByTestId("document-field-error-title")).toHaveTextContent(
      "This title is too long."
    );
    expect(screen.getByTestId("document-field-input-title")).toHaveAttribute(
      "aria-invalid",
      "true"
    );
  });
});

afterEach(() => {
  vi.clearAllMocks();
});
