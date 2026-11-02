/**
 * ARCH-L1-001 ReactFrontend — Document query hooks (Plan F F2-T8).
 *
 * Covers the TanStack Query state machine the view consumes: list success,
 * list error, detail enable/disable and the optimistic-lock version the
 * update mutation forwards to the API.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { DOC, UPDATED } = vi.hoisted(() => ({
  DOC: {
    id: "doc-1",
    workspace_id: "ws-001",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Guide",
    doc_date: "2026-11-02",
    frozen_at: null,
    frozen_fields: [] as string[],
    status: "Entwurf",
    version: 2,
    created_at: "2026-11-02T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
  },
  UPDATED: {
    id: "doc-1",
    workspace_id: "ws-001",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide v2",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Guide",
    doc_date: "2026-11-02",
    frozen_at: null,
    frozen_fields: [] as string[],
    status: "Entwurf",
    version: 3,
    created_at: "2026-11-02T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
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
  },
}));

import { documentsApi } from "../api/documents";
import {
  documentKeys,
  useDocument,
  useDocuments,
  useUpdateDocument,
} from "../queries/documents";

const listAll = documentsApi.listAll as ReturnType<typeof vi.fn>;
const get = documentsApi.get as ReturnType<typeof vi.fn>;
const update = documentsApi.update as ReturnType<typeof vi.fn>;

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

describe("document query hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads the workspace list", async () => {
    listAll.mockResolvedValue([DOC]);

    const client = createClient();
    const { result } = renderHook(() => useDocuments("ws-001"), {
      wrapper: wrapper(client),
    });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([DOC]);
    expect(listAll).toHaveBeenCalledWith("ws-001", false);
  });

  it("passes include_deleted through to the list request", async () => {
    listAll.mockResolvedValue([DOC]);
    const client = createClient();
    const { result } = renderHook(() => useDocuments("ws-001", true), {
      wrapper: wrapper(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listAll).toHaveBeenCalledWith("ws-001", true);
  });

  it("surfaces a list error instead of rendering an empty success", async () => {
    listAll.mockRejectedValue(new Error("list failed"));
    const client = createClient();
    const { result } = renderHook(() => useDocuments("ws-001"), {
      wrapper: wrapper(client),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("list failed");
  });

  it("does not fetch a detail when no id is selected", () => {
    const client = createClient();
    renderHook(() => useDocument(undefined), { wrapper: wrapper(client) });
    expect(get).not.toHaveBeenCalled();
  });

  it("loads one document by id", async () => {
    get.mockResolvedValue(DOC);
    const client = createClient();
    const { result } = renderHook(() => useDocument("doc-1"), {
      wrapper: wrapper(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(DOC);
    expect(get).toHaveBeenCalledWith("doc-1");
  });

  it("forwards the rendered version as the update's optimistic-lock value", async () => {
    update.mockResolvedValue(UPDATED);
    const client = createClient();
    client.setQueryData(documentKeys.detail("doc-1"), DOC);
    client.setQueryData(documentKeys.list("ws-001", false), [DOC]);

    const { result } = renderHook(() => useUpdateDocument("ws-001"), {
      wrapper: wrapper(client),
    });

    result.current.mutate({
      id: "doc-1",
      payload: { title: "Architecture guide v2" },
      expectedVersion: 2,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(update).toHaveBeenCalledWith(
      "doc-1",
      { title: "Architecture guide v2" },
      2
    );
    expect(client.getQueryData(documentKeys.detail("doc-1"))).toEqual(UPDATED);
  });
});
