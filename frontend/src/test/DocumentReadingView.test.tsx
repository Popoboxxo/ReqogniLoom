/**
 * R4.2 — document reading view (plan 2026-11-15-document-view-on-document.md).
 *
 * Covers the read surface contract: numbered chapters in order with a matching
 * table of contents, no edit affordance for a read-only caller, the freeze /
 * repository read-only notices, the single-section empty body and the fact
 * that chapter Markdown is rendered by the shared renderer (raw HTML is never
 * injected).
 */

import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import {
  render,
  screen,
  within,
  type RenderResult,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../i18n/index";

import { DocumentReadingView } from "../components/Documents/DocumentReadingView";
import type { Document, DocumentReading, ReadingChapter } from "../types";

// MarkdownPreview reads the active workspace for glossary resolution; the
// reading view tests need no workspace (and therefore no network).
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: undefined,
    isLoadingWorkspace: false,
  }),
}));

const DOCUMENT: Document = {
  id: "doc-1",
  workspace_id: "ws-001",
  artifact_id: "art-1",
  uid: "DOC-001",
  title: "Architecture guide",
  kind: "Guide",
  description: "How the system is put together.",
  body: "# Overview\n\nFirst chapter.",
  doc_date: "2026-11-02",
  frozen_at: null,
  frozen_fields: [],
  status: "Entwurf",
  version: 4,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
};

const CHAPTERS: ReadingChapter[] = [
  {
    number: "1",
    level: 1,
    title: "Overview",
    anchor: "overview",
    body: "First chapter.",
  },
  {
    number: "1.1",
    level: 2,
    title: "Details",
    anchor: "details",
    body: "Second chapter.",
  },
];

function makeReading(
  overrides: Partial<DocumentReading> = {}
): DocumentReading {
  return {
    id: "doc-1",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide",
    description: "How the system is put together.",
    body: "# Overview\n\nFirst chapter.",
    doc_date: "2026-11-02",
    version: 4,
    status: "Entwurf",
    frozen_at: null,
    frozen_fields: [],
    editable_fields: ["title", "description", "body", "doc_date"],
    fields: [
      {
        name: "title",
        value: "Architecture guide",
        editable: true,
        locked: null,
      },
      { name: "body", value: "# Overview", editable: true, locked: null },
    ],
    capabilities: { can_write: true, read_only_reason: null },
    chapters: CHAPTERS,
    projection: {
      projection_mode: "none",
      source_path: "",
      projected_sha256: "",
    },
    ...overrides,
  };
}

function renderView(reading: DocumentReading): RenderResult {
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
      />
    </Wrapper>
  );
}

function chapterSections(container: HTMLElement): Element[] {
  return Array.from(
    container.querySelectorAll('[data-testid^="document-reading-chapter-"]')
  );
}

describe("DocumentReadingView (R4.2)", () => {
  it("renders_chapters_in_order_with_numbers", () => {
    const { container } = renderView(makeReading());

    const sections = chapterSections(container);
    expect(
      sections.map((section) => section.getAttribute("data-testid"))
    ).toEqual([
      "document-reading-chapter-overview",
      "document-reading-chapter-details",
    ]);

    const first = screen.getByTestId("document-reading-chapter-overview");
    expect(within(first).getByRole("heading", { level: 2 })).toHaveTextContent(
      /1\s*Overview/
    );
    const second = screen.getByTestId("document-reading-chapter-details");
    expect(within(second).getByRole("heading", { level: 3 })).toHaveTextContent(
      /1\.1\s*Details/
    );
  });

  it("renders_toc_entries_matching_chapters", () => {
    renderView(makeReading());

    const toc = screen.getByTestId("document-reading-toc");
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(CHAPTERS.length);
    expect(links[0]).toHaveTextContent(/1\s*Overview/);
    expect(links[1]).toHaveTextContent(/1\.1\s*Details/);
    expect(links[0]).toHaveAttribute("href", "#chapter-overview");
  });

  it("viewer_sees_no_edit_affordance", () => {
    renderView(
      makeReading({
        capabilities: { can_write: false, read_only_reason: "PERMISSION" },
        fields: [
          {
            name: "title",
            value: "Architecture guide",
            editable: false,
            locked: { code: "PERMISSION", detail: "Read access only." },
          },
        ],
      })
    );

    expect(screen.queryByTestId("document-edit")).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-delete")).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-reactivate")).not.toBeInTheDocument();
    expect(
      screen.getAllByTestId("markdown-read-only").length
    ).toBeGreaterThan(0);
    expect(
      screen.getByTestId("document-reading-capability-notice")
    ).toBeInTheDocument();
    // No editable control anywhere on the read surface.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("frozen_document_shows_lock_notice", () => {
    renderView(
      makeReading({
        status: "Freigegeben",
        frozen_at: "2026-11-02T10:00:00Z",
        frozen_fields: ["title", "description", "body"],
      })
    );

    const notice = screen.getByTestId("document-reading-capability-notice");
    expect(
      within(notice).getByTestId("document-frozen-banner")
    ).toBeInTheDocument();
    expect(
      within(notice).getByTestId("document-frozen-fields")
    ).toHaveTextContent("title, description, body");
  });

  it("repo_external_document_shows_read_only_notice", () => {
    renderView(
      makeReading({
        capabilities: { can_write: false, read_only_reason: "REPO_EXTERNAL" },
      })
    );

    expect(
      screen.getByTestId("document-reading-capability-notice")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("document-read-only-reason")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("document-edit")).not.toBeInTheDocument();
  });

  it("empty_body_renders_single_section", () => {
    const { container } = renderView(
      makeReading({
        chapters: [
          { number: "", level: 0, title: "", anchor: "section", body: "" },
        ],
      })
    );

    expect(chapterSections(container)).toHaveLength(1);
    expect(
      screen.getByTestId("document-reading-chapter-section")
    ).toBeInTheDocument();
    const toc = screen.getByTestId("document-reading-toc");
    expect(within(toc).getAllByRole("link")).toHaveLength(1);
    expect(within(toc).getByRole("link")).toHaveTextContent(
      "Architecture guide"
    );
  });

  it("markdown_links_render_as_text_not_html", () => {
    const { container } = renderView(
      makeReading({
        chapters: [
          {
            number: "1",
            level: 1,
            title: "Links",
            anchor: "links",
            body:
              'See [the spec](https://example.com/spec) for details.\n\n<img src=x onerror="alert(1)">',
          },
        ],
      })
    );

    const link = screen.getByRole("link", { name: "the spec" });
    expect(link).toHaveAttribute("href", "https://example.com/spec");
    // Raw HTML never becomes DOM: no image element, no injected markup.
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("<img");
  });
});
