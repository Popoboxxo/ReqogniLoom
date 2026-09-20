import { describe, it, expect, vi, beforeEach } from "vitest";
import { memoryApi } from "./memory";
import { apiClient } from "./client";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const WS = "ws-1";
const ART = "art-1";
const ENTRY = "entry-1";

describe("memoryApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists workspace entries with scope + pagination params", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({});
    await memoryApi.listWorkspaceEntries(WS, {
      scope: "workspace",
      page: 2,
      page_size: 25,
      q: "dark",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${WS}/memory/entries/?scope=workspace&q=dark&page=2&page_size=25`
    );
  });

  it("omits undefined/empty list params", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({});
    await memoryApi.listWorkspaceEntries(WS, { scope: "artifact", q: "" });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${WS}/memory/entries/?scope=artifact`
    );
  });

  it("creates a workspace-scoped fact", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    await memoryApi.createWorkspaceEntry(WS, { content: "fact" });
    expect(apiClient.post).toHaveBeenCalledWith(
      `/workspaces/${WS}/memory/entries/`,
      { content: "fact" }
    );
  });

  it("searches with q, scope and top_k", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({});
    await memoryApi.searchWorkspaceMemory(WS, {
      q: "dark",
      scope: "user",
      top_k: 20,
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${WS}/memory/search/?q=dark&scope=user&top_k=20`
    );
  });

  it("forgets an entry and forwards the change reason", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ deleted: true });
    await memoryApi.forgetEntry(ENTRY, "cleanup");
    expect(apiClient.delete).toHaveBeenCalledWith(
      `/memory/entries/${ENTRY}/?change_reason=cleanup`
    );
  });

  it("promotes an entry into the target workspace", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    await memoryApi.promoteEntry(ENTRY, { workspace_id: WS });
    expect(apiClient.post).toHaveBeenCalledWith(
      `/memory/entries/${ENTRY}/promote/`,
      { workspace_id: WS }
    );
  });

  it("lists and creates artifact-scoped facts", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({});
    vi.mocked(apiClient.post).mockResolvedValue({});
    await memoryApi.listArtifactMemory(ART, { page_size: 25 });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/artifacts/${ART}/memory/?page_size=25`
    );
    await memoryApi.createArtifactMemory(ART, { content: "fact" });
    expect(apiClient.post).toHaveBeenCalledWith(`/artifacts/${ART}/memory/`, {
      content: "fact",
    });
  });

  it("reads the self overview with include_entries=true", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({});
    await memoryApi.getSelfOverview({ includeEntries: true, pageSize: 100 });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/memory/me/?include_entries=true&page_size=100"
    );
  });

  it("purges the caller's own memory", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ deleted: 3 });
    await memoryApi.deleteSelfMemory();
    expect(apiClient.delete).toHaveBeenCalledWith("/memory/me/");
  });

  it("extracts the memory component from the system health snapshot", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      components: [
        { name: "database", status: "ok", detail: "connected" },
        {
          name: "memory",
          status: "degraded",
          detail: "mem_memory_entry slow",
          backend: "pgvector",
          ok: true,
          degraded: true,
        },
      ],
    });
    const health = await memoryApi.getMemoryHealth();
    expect(health).toEqual({
      backend: "pgvector",
      ok: true,
      degraded: true,
      detail: "mem_memory_entry slow",
      status: "degraded",
    });
  });

  it("fails loudly when the health snapshot has no memory component", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ components: [] });
    await expect(memoryApi.getMemoryHealth()).rejects.toThrow(/memory/);
  });

  it("lists the system workspace overview", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ results: [] });
    await memoryApi.listSystemWorkspaceOverview();
    expect(apiClient.get).toHaveBeenCalledWith("/system/memory/workspaces/");
  });

  it("deletes a workspace's memory through the system endpoint", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({});
    await memoryApi.deleteSystemWorkspaceMemory(WS);
    expect(apiClient.delete).toHaveBeenCalledWith(
      `/system/memory/workspaces/${WS}/`
    );
  });

  it("lists system entries with scope, workspace_id and filter", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ results: [] });
    await memoryApi.listSystemEntries({
      scope: "workspace",
      workspaceId: WS,
      page: 1,
      pageSize: 25,
      q: "x",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/system/memory/entries/?scope=workspace&workspace_id=${WS}&page=1&page_size=25&q=x`
    );
  });

  it("fetches the system projection", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ points: [] });
    await memoryApi.getSystemProjection({ scope: "global" });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/system/memory/projection/?scope=global"
    );
  });
});
