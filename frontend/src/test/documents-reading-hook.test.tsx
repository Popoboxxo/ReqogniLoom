/**
 * R4.1 — document reading query hook (plan
 * 2026-11-15-document-view-on-document.md).
 *
 * Covers the three contracts the reading surface depends on: the hook fetches
 * `GET /documents/{id}/view/`, stays idle without a document id, and surfaces a
 * backend 404 as a query error (the view renders the error state, not a blank
 * document).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { READING } = vi.hoisted(() => ({
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
    frozen_at: null,
    frozen_fields: [] as string[],
    editable_fields: ["title", "description", "body", "doc_date"],
    fields: [
      { name: "title", value: "Architecture guide", editable: true, locked: null },
    ],
    capabilities: { can_write: true, read_only_reason: null },
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

vi.mock("../api/documents", () => ({
  documentsApi: {
    readingView: vi.fn(),
  },
}));

import { documentKeys, useDocumentReading } from "../queries/documents";
import { documentsApi } from "../api/documents";

const readingView = documentsApi.readingView as ReturnType<typeof vi.fn>;

function makeClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe("useDocumentReading (R4.1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readingView.mockResolvedValue(READING);
  });

  it("test_hook_fetches_reading_object", async () => {
    const client = makeClient();
    const { result } = renderHook(
      () => useDocumentReading("doc-1", "ws-001"),
      { wrapper: makeWrapper(client) }
    );

    await waitFor(() => expect(result.current.data).toEqual(READING));

    expect(readingView).toHaveBeenCalledWith("doc-1");
    const cached = client
      .getQueryCache()
      .find({ queryKey: documentKeys.reading("ws-001", "doc-1") });
    expect(cached).toBeDefined();
    // The surface shows the current state, never a cache snapshot.
    expect(cached?.options.staleTime).toBe(0);
  });

  it("test_hook_is_disabled_without_document_id", () => {
    const client = makeClient();
    const { result } = renderHook(
      () => useDocumentReading(undefined, "ws-001"),
      { wrapper: makeWrapper(client) }
    );

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toBeUndefined();
    expect(readingView).not.toHaveBeenCalled();
  });

  it("test_hook_surfaces_404_as_error", async () => {
    readingView.mockRejectedValue(new Error("Not found."));
    const client = makeClient();
    const { result } = renderHook(
      () => useDocumentReading("missing", "ws-001"),
      { wrapper: makeWrapper(client) }
    );

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect(result.current.error?.message).toBe("Not found.");
    expect(result.current.data).toBeUndefined();
  });
});
