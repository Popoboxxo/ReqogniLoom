# Requirement Bundle Export — Plan 3: UI Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lazy-loaded "Requirement Bundle Export" panel to the Architecture View, letting a user fetch and view every Requirement under a selected `ArchitectureElement` — raw (JSON/Markdown/CSV) or AI-compressed (sync or async, with progress polling) — without leaving the view. This is the UI-side follow-on explicitly deferred by Plan 2 ("Follow-on work (not part of this plan): Requirement Bundle Export — Plan 3: UI Panel").

**Architecture:** One new API wrapper module (`requirementBundleApi`), one new polling hook (`useBundleCompressionStatus`, genuinely new frontend infrastructure — no async-dispatch-then-poll precedent exists anywhere in this frontend today, confirmed by repo-wide search), one new panel component (`RequirementBundleExportPanel`), wired into `ArchitectureEditors.tsx` via the existing `overflowActions` + local-`useState`-flag + conditional-`<Dialog>` pattern that `ArchitectureDecomposePanel` already established (same file, same convention — not a new pattern).

**Tech Stack:** React 18 + TypeScript (strict), `react-i18next` (DE/EN parity-enforced), `react-markdown` (already a dependency, already used by `MarkdownPreview.tsx` — reused as-is for compressed/markdown output), inline `CSSProperties` objects reading `var(--color-*)`/`var(--space-*)`/`var(--radius-*)` tokens (the `ArchitectureDecomposePanel` convention), `vitest` + `@testing-library/react` + `@testing-library/user-event` for the component test, Playwright for the one E2E invariant this feature requires.

**Design source:** `docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md` §7 (UI subsection) and §9 (Testing-Strategie, E2E bullet). Depends on Plan 1 (raw modes, merged via PR #435) and Plan 2 (compression, merged via PR #436 + the REQ-106 token-accounting fix in PR #462) — both already deployed on `main`. The design doc's REST sketch (`architecture-elements/{id}/...`, `?format=`) predates Plan 2's actual implementation (`architecture/{pk}/requirement-bundle/`, `?output_format=`) — this plan follows the *implemented* contract, not the original sketch.

**Backend contract this plan drives (already implemented, not part of this plan's scope):**
```
GET /api/v1/architecture/{element_id}/requirement-bundle/
    ?depth=<int>                         (omit for full hierarchy; server caps at 20)
    &filter_mode=<all|visible|custom>
    &fields=<comma-list>                 (required when filter_mode=custom)
    &output_format=<json|markdown|csv>   (ignored when mode=compressed)
    &mode=<raw|compressed>               (default raw)
    &async=<bool>                        (only meaningful when mode=compressed)

  mode=raw:        200, body is the format's native content-type
                    (application/json | text/markdown | text/csv)
  mode=compressed, sync:  200 JSON {"text": str, "cache_hit": bool, "is_mock_fallback": bool}
  mode=compressed, async (forced or bundle > 50 items):
                    202 JSON {"task_id": str}
                    503 JSON {"error": {"code": "BROKER_NOT_CONFIGURED", ...}} if no broker
  errors: 404 (unknown root), 400 VALIDATION_ERROR (bad mode/output_format/depth/custom fields)

GET /api/v1/bundle-compression-status/{task_id}/
    200 JSON {"task_id": str, "status": "pending"|"running"|"done"|"failed"|"not_found",
              "result": {"result": str} | null, "error": str | null}
    A task_id from a different tenant reports "not_found" (ADR-03) — not a distinguishable error.
```

## Global Constraints

- **No fetch on Architecture View mount.** The design doc (§7) makes this a hard requirement, independently re-asserted as an E2E acceptance criterion (§9): "kein Netzwerk-Request beim Öffnen der Architecture View selbst". The existing `showDecomposePanel`/`<Dialog>` pattern in `ArchitectureEditors.tsx` already satisfies this shape (component only mounts, and its `useEffect`s only run, once the dialog flag flips `true`) — this plan must not deviate from it.
- **`apiClient.get<T>()` always calls `response.json()`** (`frontend/src/api/client.ts:276`) — it cannot be used for `output_format=markdown`/`csv` raw requests, whose response `Content-Type` is `text/markdown`/`text/csv`, not JSON. Those two calls MUST use a raw `fetch()` reading `.text()`, mirroring `exportApi`'s auth/credentials handling (`credentials: "same-origin"`, `Accept-Language` header, no manual bearer header — auth travels via the httpOnly cookie) rather than going through `apiClient`. `output_format=json` (raw) and both compressed-mode responses (`{text,...}` / `{task_id}`) ARE JSON and go through `apiClient.get<T>()` normally.
- **This plan renders results in-panel; it does not add a file-download affordance.** `exportApi`'s blob/`<a download>` pattern exists and could be reused later, but the design doc's UI subsection only specifies "Controls für Tiefe, Filter-Modus, Format, Raw/Compressed" — no download button. Out of scope here; flag as a natural Plan 4 candidate if requested.
- **Polling is genuinely new infrastructure.** No `setInterval`-based REST-status-poll hook exists anywhere in this frontend today (confirmed by repo-wide search — the one `task_id`-returning wrapper, `stakeholder-need.ts`'s `derive()`, is explicitly fire-and-forget and never polled). `useBundleCompressionStatus` must: poll on a fixed interval while `status` is `pending`/`running`; stop polling (clear the interval) the moment `status` becomes `done`/`failed`/`not_found`; clear its interval on unmount and whenever `taskId` changes to a new value or `null`; never poll when `taskId` is `null`.
- **i18n parity is enforced by a test** (`frontend/src/test/i18n-parity.test.ts`) — every key added to `en.json` under a new `bundleExport` namespace MUST have an exact structural counterpart in `de.json`, and vice versa.
- **`data-testid` on every interactive element** (E2E convention, project-wide rule) — prefix `arch-bundle-export-*`, mirroring `arch-decompose-*`.
- Every new component/hook/API-wrapper file gets a component/unit test in `frontend/src/test/` (existing convention — no `__tests__` subfolders, flat `frontend/src/test/<ComponentName>.test.tsx`).

---

### Task 1: `requirementBundleApi` — API wrapper

**Files:**
- Create: `frontend/src/api/requirementBundle.ts`
- Test: `frontend/src/test/requirementBundleApi.test.ts` (new)

**Interfaces:**
- Produces: `requirementBundleApi.exportRaw(elementId, options): Promise<BundleRawResult>`, `requirementBundleApi.exportCompressed(elementId, options): Promise<CompressedResult | { task_id: string }>`, `requirementBundleApi.getCompressionStatus(taskId): Promise<CompressionStatus>`.
- Consumes: `apiClient` (`../api/client.ts`) for JSON calls; raw `fetch` (mirroring `exportApi`'s credentials/header handling in `../api/export.ts`) for `output_format=markdown|csv`.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/test/requirementBundleApi.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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
    expect(calledUrl).not.toContain("mode=");
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/requirementBundleApi.test.ts`
Expected: FAIL (module `../api/requirementBundle` does not exist yet)

- [ ] **Step 3: Implement**

```typescript
// frontend/src/api/requirementBundle.ts
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
    // cannot go through apiClient (client.ts:276 always calls response.json()).
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
```

Match `apiClient`'s real base-path handling (verify whether `apiClient.get` already prefixes `/api/v1` internally or expects the caller to include it — read `frontend/src/api/client.ts`'s `apiFetch` implementation and an existing caller like `search.ts` to confirm before trusting this sketch's exact path strings) and its real generic signature before trusting this sketch verbatim.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/requirementBundleApi.test.ts`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/requirementBundle.ts frontend/src/test/requirementBundleApi.test.ts
git commit -m "feat: add requirementBundleApi wrapper for raw/compressed bundle export"
```

---

### Task 2: `useBundleCompressionStatus` — polling hook

**Files:**
- Create: `frontend/src/hooks/useBundleCompressionStatus.ts`
- Test: `frontend/src/test/useBundleCompressionStatus.test.ts` (new)

**Interfaces:**
- Consumes: `requirementBundleApi.getCompressionStatus` (Task 1).
- Produces: `useBundleCompressionStatus(taskId: string | null, intervalMs = 2000): { status, result, error, isPolling }`.

Check first whether `frontend/src/hooks/` exists as a directory with an established custom-hook convention (naming, return-shape, test-file location) — if it does not exist yet, this is the first hook there and should still land under `frontend/src/hooks/<name>.ts` with its test under `frontend/src/test/` per the flat-test-directory convention confirmed for components; if an equivalent directory/convention already exists somewhere else in the tree (e.g. hooks colocated in `components/`), follow that instead of introducing a second convention.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/test/useBundleCompressionStatus.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useBundleCompressionStatus } from "../hooks/useBundleCompressionStatus";

vi.mock("../api/requirementBundle", () => ({
  requirementBundleApi: { getCompressionStatus: vi.fn() },
}));
import { requirementBundleApi } from "../api/requirementBundle";

describe("useBundleCompressionStatus", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not poll when taskId is null", () => {
    renderHook(() => useBundleCompressionStatus(null));
    expect(requirementBundleApi.getCompressionStatus).not.toHaveBeenCalled();
  });

  it("polls on an interval while status is pending/running, stops at done", async () => {
    (requirementBundleApi.getCompressionStatus as any)
      .mockResolvedValueOnce({ task_id: "t1", status: "pending", result: null, error: null })
      .mockResolvedValueOnce({ task_id: "t1", status: "running", result: null, error: null })
      .mockResolvedValueOnce({ task_id: "t1", status: "done", result: { result: "text" }, error: null });

    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));

    await waitFor(() => expect(result.current.status).toBe("pending"));
    await act(async () => { vi.advanceTimersByTime(1000); });
    await waitFor(() => expect(result.current.status).toBe("running"));
    await act(async () => { vi.advanceTimersByTime(1000); });
    await waitFor(() => expect(result.current.status).toBe("done"));

    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(3);

    // No further calls once "done" — advancing time must not poll again.
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(3);
  });

  it("stops polling and clears the interval on unmount", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1", status: "pending", result: null, error: null,
    });
    const { unmount } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await waitFor(() => expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1));
    unmount();
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1);
  });

  it("surfaces a failed status without throwing", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1", status: "failed", result: null, error: "LLM_TOKEN_LIMIT_EXCEEDED",
    });
    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.error).toBe("LLM_TOKEN_LIMIT_EXCEEDED");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/useBundleCompressionStatus.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement**

```typescript
// frontend/src/hooks/useBundleCompressionStatus.ts
import { useEffect, useRef, useState } from "react";
import { requirementBundleApi } from "../api/requirementBundle";
import type { CompressionStatus } from "../api/requirementBundle";

const TERMINAL_STATUSES = new Set<CompressionStatus["status"]>(["done", "failed", "not_found"]);

export interface BundleCompressionStatusState {
  status: CompressionStatus["status"] | null;
  result: string | null;
  error: string | null;
  isPolling: boolean;
}

export function useBundleCompressionStatus(
  taskId: string | null,
  intervalMs = 2000
): BundleCompressionStatusState {
  const [state, setState] = useState<BundleCompressionStatusState>({
    status: null, result: null, error: null, isPolling: false,
  });

  useEffect(() => {
    if (!taskId) {
      setState({ status: null, result: null, error: null, isPolling: false });
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const poll = async () => {
      try {
        const next = await requirementBundleApi.getCompressionStatus(taskId);
        if (cancelled) return;
        setState({
          status: next.status,
          result: next.result?.result ?? null,
          error: next.error,
          isPolling: !TERMINAL_STATUSES.has(next.status),
        });
        if (TERMINAL_STATUSES.has(next.status) && intervalId !== undefined) {
          clearInterval(intervalId);
        }
      } catch (err) {
        if (cancelled) return;
        setState({
          status: "failed", result: null,
          error: err instanceof Error ? err.message : "Status poll failed",
          isPolling: false,
        });
        if (intervalId !== undefined) clearInterval(intervalId);
      }
    };

    setState((prev) => ({ ...prev, isPolling: true }));
    poll();
    intervalId = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [taskId, intervalMs]);

  return state;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/useBundleCompressionStatus.test.ts`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useBundleCompressionStatus.ts frontend/src/test/useBundleCompressionStatus.test.ts
git commit -m "feat: add useBundleCompressionStatus polling hook"
```

---

### Task 3: i18n — `bundleExport` namespace

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/de.json`

**Interfaces:** No code interface — pure data. Task 4 (the panel) consumes these keys via `useTranslation()`'s `t()`, following the `t("bundleExport.<key>", "<fallback>")` convention used throughout `ArchitectureDecomposePanel.tsx`.

- [ ] **Step 1: Add the keys**

Add a `bundleExport` top-level object to both locale files, structurally identical (the parity test enforces this). Exact leaf keys are implementation's call once Task 4's UI copy is drafted, but MUST include at minimum: `trigger`, `title`, `depthLabel`, `filterModeLabel`, `filterModeAll`, `filterModeVisible`, `filterModeCustom`, `fieldsLabel`, `formatLabel`, `modeLabel`, `modeRaw`, `modeCompressed`, `asyncLabel`, `export`, `exporting`, `polling`, `error`, `cacheHit`, `mockFallback`, `empty`.

- [ ] **Step 2: Verify parity**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS (fails first if the two files' key sets diverge — write both files together, don't stage this as two separate half-done edits).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "feat: add bundleExport i18n namespace (DE/EN)"
```

---

### Task 4: `RequirementBundleExportPanel` component

**Files:**
- Create: `frontend/src/components/RequirementBundleExport/RequirementBundleExportPanel.tsx`
- Test: `frontend/src/test/RequirementBundleExportPanel.test.tsx` (new)

**Interfaces:**
- Consumes: `requirementBundleApi` (Task 1), `useBundleCompressionStatus` (Task 2), `bundleExport.*` i18n keys (Task 3), `react-markdown` (existing dependency, mirror `MarkdownPreview.tsx`'s import/usage for rendering `content`/`text`).
- Props (mirror `ArchitectureDecomposePanelProps`'s shape exactly): `{ elementId: string; elementTitle: string }`.
- Produces: no callback props needed (read-only feature, nothing to commit/refresh elsewhere — unlike `ArchitectureDecomposePanel`'s `onCommitted`).

Read `ArchitectureDecomposePanel.tsx` in full immediately before writing this component — reuse its `styles` object shape (`panel`/`controls`/`field`/`error`/`banner`/`muted`/`actions` keys, all `var(--...)` token values) verbatim where the same visual role applies, rather than inventing a parallel style vocabulary.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/test/RequirementBundleExportPanel.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequirementBundleExportPanel } from "../components/RequirementBundleExport/RequirementBundleExportPanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const exportRaw = vi.fn();
const exportCompressed = vi.fn();
const getCompressionStatus = vi.fn();
vi.mock("../api/requirementBundle", () => ({
  requirementBundleApi: {
    exportRaw: (...args: unknown[]) => exportRaw(...args),
    exportCompressed: (...args: unknown[]) => exportCompressed(...args),
    getCompressionStatus: (...args: unknown[]) => getCompressionStatus(...args),
  },
}));

function renderPanel() {
  return render(
    <RequirementBundleExportPanel elementId="elem-1" elementTitle="Payment Subsystem" />
  );
}

describe("RequirementBundleExportPanel", () => {
  beforeEach(() => {
    exportRaw.mockReset();
    exportCompressed.mockReset();
    getCompressionStatus.mockReset();
  });

  it("does not call any API on mount (lazy-load invariant)", () => {
    renderPanel();
    expect(exportRaw).not.toHaveBeenCalled();
    expect(exportCompressed).not.toHaveBeenCalled();
  });

  it("fetches and renders a raw JSON bundle on export", async () => {
    exportRaw.mockResolvedValue({
      format: "json",
      items: [{ requirement_id: "r1", found_under_element_id: "a1", depth: 0, fields: { title: "Req A" } }],
      truncated_at_depth: false,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toBeInTheDocument());
    expect(exportRaw).toHaveBeenCalledWith("elem-1", expect.objectContaining({ output_format: "json" }));
    expect(screen.getByTestId("arch-bundle-export-result")).toHaveTextContent("Req A");
  });

  it("renders compressed sync text via markdown", async () => {
    exportCompressed.mockResolvedValue({ text: "**compressed**", cache_hit: false, is_mock_fallback: true });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toBeInTheDocument());
    expect(screen.getByTestId("arch-bundle-export-mock-fallback")).toBeInTheDocument();
  });

  it("polls for an async dispatch and renders the result once done", async () => {
    exportCompressed.mockResolvedValue({ task_id: "task-1" });
    getCompressionStatus.mockResolvedValue({
      task_id: "task-1", status: "done", result: { result: "async compressed text" }, error: null,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toHaveTextContent("async compressed text"));
  });

  it("shows an error on failure and lets the user retry", async () => {
    exportRaw.mockRejectedValue(new Error("Element not found"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-error")).toHaveTextContent("Element not found"));
    expect(screen.getByTestId("arch-bundle-export-submit")).not.toBeDisabled();
  });
});
```

Match the real `useBundleCompressionStatus` mocking shape (this sketch mocks `getCompressionStatus` directly rather than the hook — pick whichever is more stable against the hook's real internal polling/interval mechanics once Task 2 is live; mocking the hook module directly may be simpler than driving fake timers through both the hook and the panel in the same test).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/RequirementBundleExportPanel.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement**

Build the component per the Interfaces above: controls row (depth number input, filter_mode select + conditional fields text input when `custom`, output_format select — disabled/hidden when mode is `compressed` per the backend's "ignored when mode=compressed" contract, mode radio/toggle raw|compressed, async checkbox visible only when mode=compressed), a submit button (`arch-bundle-export-submit`) dispatching either `exportRaw` or `exportCompressed` depending on mode, wiring the async branch's returned `task_id` into `useBundleCompressionStatus`, and a result area that renders:
- raw JSON → `<pre data-testid="arch-bundle-export-result">{JSON.stringify(data.items, null, 2)}</pre>` (no new syntax-highlighting dependency — none exists in this codebase today, confirmed).
- raw markdown / compressed text → `<ReactMarkdown>{content}</ReactMarkdown>` inside the `data-testid="arch-bundle-export-result"` wrapper, mirroring `MarkdownPreview.tsx`'s import (the glossary-tooltip link override there is specific to requirement descriptions — do not carry it over here, plain `ReactMarkdown` is enough).
- raw csv → `<pre data-testid="arch-bundle-export-result">{content}</pre>`.
- an `is_mock_fallback` banner (`arch-bundle-export-mock-fallback`, style mirroring `archDecompose.degraded`'s `styles.banner`) when the compressed result reports it.
- a `cache_hit` indicator (`arch-bundle-export-cache-hit`) when true.
- error state via `extractErrorMessage` + `styles.error`, `role="alert"`, `data-testid="arch-bundle-export-error"` — mirror `ArchitectureDecomposePanel`'s exact error-handling shape (catch, `setError`, return to a non-busy phase so the submit button re-enables for retry).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/RequirementBundleExportPanel.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RequirementBundleExport/ frontend/src/test/RequirementBundleExportPanel.test.tsx
git commit -m "feat: add RequirementBundleExportPanel component"
```

---

### Task 5: Wire into `ArchitectureEditors.tsx` + E2E lazy-load invariant

**Files:**
- Modify: `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx`
- Modify (new i18n key only, if `archDecompose.trigger`-style overflow label isn't already covered by Task 3): none expected beyond Task 3's `bundleExport.trigger`.
- Test: `e2e/tests/architecture-editor.spec.ts` (extend) — the design doc's §9 E2E requirement.

**Interfaces:**
- Consumes: `RequirementBundleExportPanel` (Task 4), the existing `Dialog` component, the existing `overflowActions`/`useState` pattern already in this file (lines ~108-112 for the flag declarations, ~569-586 for `showDecomposePanel`'s Dialog block, ~607-620 for its `overflowActions` entry).

- [ ] **Step 1: Write the failing E2E test**

```typescript
// append to e2e/tests/architecture-editor.spec.ts
test("bundle export panel does not fetch on view load, only on activation", async ({ page }) => {
  // ... navigate to Architecture view with a selected element (mirror this
  // file's existing setup/login/element-selection helpers — read the top of
  // this spec file for the real helper names before writing this test) ...

  const bundleRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/requirement-bundle/")) bundleRequests.push(req.url());
  });

  // View is open, element selected — no bundle request yet.
  await expect(page.getByTestId("arch-bundle-export-overflow-btn")).toBeVisible();
  expect(bundleRequests).toHaveLength(0);

  await page.getByTestId("arch-bundle-export-overflow-btn").click();
  await expect(page.getByTestId("arch-bundle-export-dialog")).toBeVisible();
  // Dialog open, but still no fetch until the user submits.
  expect(bundleRequests).toHaveLength(0);

  await page.getByTestId("arch-bundle-export-submit").click();
  await expect(page.getByTestId("arch-bundle-export-result")).toBeVisible({ timeout: 15000 });
  expect(bundleRequests.length).toBeGreaterThan(0);
});
```

Read the existing specs in `e2e/tests/architecture-editor.spec.ts` and `e2e/tests/architecture.spec.ts` first for this project's real login/navigation/element-selection helpers and fixtures — do not invent new ones.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e2e && npx playwright test architecture-editor.spec.ts -g "bundle export panel"`
Expected: FAIL (no `arch-bundle-export-overflow-btn` exists yet)

- [ ] **Step 3: Wire the panel in**

In `ArchitectureEditors.tsx`:
- Add `const [showBundleExportPanel, setShowBundleExportPanel] = useState(false);` alongside `showDecomposePanel`/`showLegend`.
- Add a third `overflowActions` entry:
  ```tsx
  {
    label: t("bundleExport.trigger", "Requirement-Bundle exportieren"),
    onClick: () => setShowBundleExportPanel(true),
    disabled: !element || !activeWorkspace,
    testId: "arch-bundle-export-overflow-btn",
  },
  ```
- Add a conditional `<Dialog>` block mirroring `showDecomposePanel`'s exactly (same `element && activeWorkspace` guard, `size="lg"`, `testId="arch-bundle-export-dialog"`), rendering `<RequirementBundleExportPanel elementId={element.id} elementTitle={element.title} />`.
- Import `RequirementBundleExportPanel` at the top of the file alongside the existing `ArchitectureDecomposePanel` import.

- [ ] **Step 4: Run tests, verify pass, run full frontend + e2e regression**

Run: `cd frontend && npx vitest run` (full unit suite — confirms the new files plus i18n parity plus nothing else broke)
Run: `cd e2e && npx playwright test architecture-editor.spec.ts` (full file, not just the new test — confirms no regression in the other 8+ specs this file's `create-arch-btn`/testids are referenced by)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx e2e/tests/architecture-editor.spec.ts
git commit -m "feat: wire RequirementBundleExportPanel into Architecture View overflow menu"
```

---

## Self-Review Notes

- **Spec coverage:** design spec §7 (UI subsection: lazy-load, no-fetch-on-mount, depth/filter/format/mode controls) → Tasks 4-5. §9 (E2E lazy-load invariant) → Task 5. §5 (sync/async compressed modes) → Tasks 1-2, surfaced in Task 4's panel logic.
- **Known scope boundary, not a gap:** no file-download affordance (raw fetch results only render in-panel). The design doc doesn't ask for one; `exportApi`'s blob-download pattern is available to reuse in a follow-on plan if requested.
- **Known scope boundary, not a gap:** no dedicated JSON/CSV syntax highlighting — plain `<pre>`. No such component exists anywhere in this codebase today (confirmed); introducing one is a separate, larger decision (new dependency) outside this plan's scope.
- **Deliberate new infrastructure, flagged, not hidden:** `useBundleCompressionStatus` has no precedent to mirror in this frontend (confirmed by repo-wide search before writing this plan) — Task 2's implementer should treat its interval/cleanup/error-handling design as new ground, not assume an existing convention to copy.
- **Drift from the original design doc, resolved in favor of reality:** the design doc's REST sketch (§7) uses `architecture-elements/{id}/...` and `?format=`; the actually-implemented, already-merged endpoint (Plan 2 Task 4) uses `architecture/{pk}/requirement-bundle/` and `?output_format=` (DRF's `?format=` is reserved for content negotiation). This plan's Backend Contract section and all Task sketches use the real, implemented path — do not "correct" them back toward the design doc's original sketch.
- Every task's code was sketched against real signatures read from the live codebase during planning (`apiClient.get<T>`, `ArchitectureDecomposePanel`'s exact prop/state/style shape, `exportApi`'s raw-fetch/credentials pattern, `MarkdownPreview.tsx`'s `react-markdown` usage, `ArchitectureEditors.tsx`'s real `overflowActions`/Dialog wiring at the cited line numbers) — not invented APIs. One thing flagged inline for the relevant task's implementer to verify live rather than trust verbatim: `apiClient`'s exact base-path handling (Task 1, Step 3) — confirm whether `/api/v1` is prepended internally before trusting this plan's path strings.

## Follow-on work (not part of this plan)

**Requirement Bundle Export — Plan 4: File download.** Reuse `exportApi`'s blob/`<a download>` pattern to let the panel's raw JSON/Markdown/CSV result also be downloaded as a file, not just viewed in-panel. Depends on this plan (Plan 3) being deployed.
