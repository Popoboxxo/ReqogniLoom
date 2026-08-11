/**
 * ARCH-L1-001 ReactFrontend — Requirement Bundle Export API.
 *
 * Wraps GET /api/v1/architecture/{element_id}/requirement-bundle/ (raw +
 * compressed modes) and GET /api/v1/bundle-compression-status/{task_id}/
 * (async compression polling).
 *
 * `output_format=json` (raw) and both compressed-mode responses
 * (`{text,...}` / `{task_id}`) are JSON and go through `apiClient.get<T>()`.
 * `output_format=markdown|csv` responses are NOT JSON
 * (`Content-Type: text/markdown` / `text/csv`), and `apiClient.get<T>()`
 * always calls `response.json()` (`client.ts`), so those two requests use a
 * raw `fetch()` instead, mirroring `exportApi`'s auth/credentials handling
 * (`credentials: "same-origin"`, `Accept-Language` header, no manual bearer
 * header — auth travels via the httpOnly cookie).
 */

import { apiClient } from "./client";

export type FilterMode = "all" | "visible" | "custom";
export type OutputFormat = "json" | "markdown" | "csv";

export interface BundleItem {
  requirement_id: string;
  found_under_element_id: string;
  depth: number;
  fields: Record<string, unknown>;
}
export interface BundleJsonResult {
  format: "json";
  items: BundleItem[];
  truncated_at_depth: boolean;
}
export interface BundleTextResult {
  format: "markdown" | "csv";
  content: string;
}
export type BundleRawResult = BundleJsonResult | BundleTextResult;

export interface CompressedResult {
  text: string;
  cache_hit: boolean;
  is_mock_fallback: boolean;
}
export interface CompressionDispatch {
  task_id: string;
}
export interface CompressionStatus {
  task_id: string;
  status: "pending" | "running" | "done" | "failed" | "not_found";
  result: { result: string } | null;
  error: string | null;
}

export interface RawExportOptions {
  depth?: number;
  filter_mode: FilterMode;
  fields?: string[];
  output_format: OutputFormat;
}
export interface CompressedExportOptions {
  depth?: number;
  filter_mode?: FilterMode;
  fields?: string[];
  async?: boolean;
}

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, value);
  }
  return search.toString();
}

export const requirementBundleApi = {
  async exportRaw(elementId: string, options: RawExportOptions): Promise<BundleRawResult> {
    const query = buildQuery({
      depth: options.depth !== undefined ? String(options.depth) : undefined,
      filter_mode: options.filter_mode,
      fields: options.fields && options.fields.length > 0 ? options.fields.join(",") : undefined,
      output_format: options.output_format,
    });
    const path = `/architecture/${elementId}/requirement-bundle/?${query}`;

    if (options.output_format === "json") {
      const data = await apiClient.get<{ items: BundleItem[]; truncated_at_depth: boolean }>(path);
      return { format: "json", ...data };
    }

    // markdown/csv: server responds with a non-JSON Content-Type, so this
    // cannot go through apiClient (client.ts always calls response.json()).
    const lang = document.documentElement.lang || "en";
    const resp = await fetch(`/api/v1${path}`, {
      method: "GET",
      headers: { "Accept-Language": lang },
      credentials: "same-origin",
    });
    if (!resp.ok) {
      let message = `Bundle export failed (HTTP ${resp.status})`;
      try {
        const body = (await resp.json()) as { error?: { message?: string } };
        message = body?.error?.message ?? message;
      } catch {
        // ignore — fall back to default message
      }
      throw new Error(message);
    }
    const content = await resp.text();
    return { format: options.output_format, content };
  },

  async exportCompressed(
    elementId: string,
    options: CompressedExportOptions = {}
  ): Promise<CompressedResult | CompressionDispatch> {
    const query = buildQuery({
      depth: options.depth !== undefined ? String(options.depth) : undefined,
      filter_mode: options.filter_mode ?? "all",
      fields: options.fields && options.fields.length > 0 ? options.fields.join(",") : undefined,
      mode: "compressed",
      async: options.async ? "true" : undefined,
    });
    return apiClient.get<CompressedResult | CompressionDispatch>(
      `/architecture/${elementId}/requirement-bundle/?${query}`
    );
  },

  async getCompressionStatus(taskId: string): Promise<CompressionStatus> {
    return apiClient.get<CompressionStatus>(`/bundle-compression-status/${taskId}/`);
  },
};
