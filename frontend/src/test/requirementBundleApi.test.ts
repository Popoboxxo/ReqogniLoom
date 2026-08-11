import { describe, it, expect, vi, beforeEach } from "vitest";
import { requirementBundleApi } from "../api/requirementBundle";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn() },
}));
import { apiClient } from "../api/client";

describe("requirementBundleApi.exportRaw", () => {
  beforeEach(() => vi.resetAllMocks());

  it("calls apiClient.get with the query string for output_format=json", async () => {
    (apiClient.get as any).mockResolvedValue({ items: [], truncated_at_depth: false });
    await requirementBundleApi.exportRaw("elem-1", {
      depth: 2, filter_mode: "all", output_format: "json",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining("/architecture/elem-1/requirement-bundle/?")
    );
    const calledUrl = (apiClient.get as any).mock.calls[0][0] as string;
    expect(calledUrl).toContain("depth=2");
    expect(calledUrl).toContain("filter_mode=all");
    expect(calledUrl).toContain("output_format=json");
    // "filter_mode=all" itself contains the substring "mode=", so assert on
    // the actual query param via URLSearchParams instead of a raw substring
    // check (which would false-positive on "filter_mode").
    const params = new URLSearchParams(calledUrl.split("?")[1]);
    expect(params.has("mode")).toBe(false);
  });

  it("uses raw fetch (not apiClient) for output_format=markdown and returns text", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, text: () => Promise.resolve("# Bundle\n..."),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await requirementBundleApi.exportRaw("elem-1", {
      filter_mode: "all", output_format: "markdown",
    });
    expect(result).toEqual({ format: "markdown", content: "# Bundle\n..." });
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("output_format=markdown"),
      expect.objectContaining({ credentials: "same-origin" })
    );
    vi.unstubAllGlobals();
  });

  it("custom filter_mode requires fields and serializes them comma-joined", async () => {
    (apiClient.get as any).mockResolvedValue({ items: [], truncated_at_depth: false });
    await requirementBundleApi.exportRaw("elem-1", {
      filter_mode: "custom", fields: ["title", "status"], output_format: "json",
    });
    const calledUrl = (apiClient.get as any).mock.calls[0][0] as string;
    expect(calledUrl).toContain("fields=title%2Cstatus");
  });

  it("uses raw fetch (not apiClient) for output_format=csv and returns text", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, text: () => Promise.resolve("id,title\nr1,Req A\n"),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await requirementBundleApi.exportRaw("elem-1", {
      filter_mode: "all", output_format: "csv",
    });
    expect(result).toEqual({ format: "csv", content: "id,title\nr1,Req A\n" });
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("output_format=csv"),
      expect.objectContaining({ credentials: "same-origin" })
    );
    vi.unstubAllGlobals();
  });

  it("raw fetch error path: non-ok response with a JSON error body throws the server message", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 404,
      json: () => Promise.resolve({ error: { message: "Architecture element not found" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      requirementBundleApi.exportRaw("elem-missing", { filter_mode: "all", output_format: "markdown" })
    ).rejects.toThrow("Architecture element not found");
    vi.unstubAllGlobals();
  });

  it("raw fetch error path: non-ok response with an unparseable body falls back to a generic message", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 500,
      json: () => Promise.reject(new Error("not json")),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      requirementBundleApi.exportRaw("elem-1", { filter_mode: "all", output_format: "csv" })
    ).rejects.toThrow("Bundle export failed (HTTP 500)");
    vi.unstubAllGlobals();
  });
});

describe("requirementBundleApi.exportCompressed", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns the sync CompressedResult shape", async () => {
    (apiClient.get as any).mockResolvedValue({
      text: "compressed...", cache_hit: false, is_mock_fallback: true,
    });
    const result = await requirementBundleApi.exportCompressed("elem-1", { async: false });
    expect(result).toEqual({ text: "compressed...", cache_hit: false, is_mock_fallback: true });
    const calledUrl = (apiClient.get as any).mock.calls[0][0] as string;
    expect(calledUrl).toContain("mode=compressed");
  });

  it("returns the async {task_id} shape", async () => {
    (apiClient.get as any).mockResolvedValue({ task_id: "abc-123" });
    const result = await requirementBundleApi.exportCompressed("elem-1", { async: true });
    expect(result).toEqual({ task_id: "abc-123" });
  });
});

describe("requirementBundleApi.getCompressionStatus", () => {
  it("calls the status endpoint with the task_id", async () => {
    vi.resetAllMocks();
    (apiClient.get as any).mockResolvedValue({
      task_id: "abc-123", status: "pending", result: null, error: null,
    });
    const result = await requirementBundleApi.getCompressionStatus("abc-123");
    expect(apiClient.get).toHaveBeenCalledWith("/bundle-compression-status/abc-123/");
    expect(result.status).toBe("pending");
  });
});
