/**
 * R2A-005 / R2A-008 — pagination walker contract.
 *
 * Pins three properties of the centralised helpers in `client.ts`:
 *  - `getAllPages<T>()` keeps its non-breaking `T[]` return type;
 *  - `getAllPagesWithCount<T>()` returns the `{ count, results }` envelope;
 *  - `normalizeApiUrl()` is the single place that strips the backend's
 *    absolute `next` URL down to the path `apiClient.get` expects.
 *
 * Also guards that the wrapper modules no longer carry a local copy of the
 * normalisation regex (the duplication R2A-008 removes).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { getAllPages, getAllPagesWithCount, normalizeApiUrl } from "./client";
import { architectureApi } from "./architecture";

interface Row {
  id: string;
}

interface Page {
  count: number;
  next: string | null;
  previous: string | null;
  results: Row[];
}

function page(results: Row[], next: string | null, count = results.length): Page {
  return { count, next, previous: null, results };
}

function row(n: number): Row {
  return { id: `00000000-0000-0000-0000-${String(n).padStart(12, "0")}` };
}

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    headers: { get: () => null },
  } as unknown as Response;
}

/** Serve a fixed map of request URL -> page, failing loudly on an unexpected URL. */
function mockPages(pages: Record<string, Page>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const key = String(url);
    const body = pages[key];
    if (!body) throw new Error(`Unexpected fetch URL: ${key}`);
    return response(body);
  });
}

describe("R2A-008 — normalizeApiUrl", () => {
  it("strips an absolute next URL with a different host and keeps the query", () => {
    expect(
      normalizeApiUrl(
        "https://external.example.org:8443/api/v1/requirements/?page=2&page_size=100"
      )
    ).toBe("/requirements/?page=2&page_size=100");
  });

  it("strips a /api/v1-prefixed relative URL", () => {
    expect(normalizeApiUrl("/api/v1/architecture/?page=3")).toBe(
      "/architecture/?page=3"
    );
  });

  it("leaves an already-relative URL untouched", () => {
    expect(normalizeApiUrl("/requirements/?page=2")).toBe(
      "/requirements/?page=2"
    );
  });
});

describe("R2A-005 — getAllPages / getAllPagesWithCount", () => {
  const FIRST = "/api/v1/requirements/?page_size=100";
  const FIRST_WITH_STATUS =
    "/api/v1/requirements/?status=in_review&page_size=100";
  const SECOND =
    "/api/v1/requirements/?page=2&page_size=100&status=in_review";

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("getAllPages resolves to a plain array", async () => {
    const fetchSpy = mockPages({
      [FIRST]: page([row(1)], null, 1),
    });

    const result = await getAllPages<Row>("/requirements/");

    expect(Array.isArray(result)).toBe(true);
    expect(result).toEqual([row(1)]);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("follows an absolute next URL from a different host via apiClient.get", async () => {
    const fetchSpy = mockPages({
      [FIRST_WITH_STATUS]: page(
        [row(1)],
        "https://other.host.example/api/v1/requirements/?page=2&page_size=100&status=in_review",
        2
      ),
      [SECOND]: page([row(2)], null, 2),
    });

    const result = await getAllPagesWithCount<Row>("/requirements/", {
      status: "in_review",
    });

    expect(result).toEqual({ count: 2, results: [row(1), row(2)] });
    expect(fetchSpy).toHaveBeenCalledWith(SECOND, expect.any(Object));
  });

  it("getAllPagesWithCount keeps the first page's count", async () => {
    mockPages({
      [FIRST]: page([row(1)], null, 137),
    });

    const result = await getAllPagesWithCount<Row>("/requirements/");

    expect(result.count).toBe(137);
    expect(result.results).toEqual([row(1)]);
  });

  it("warns once when the 100-page cap is reached (getAllPages)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const next = "/requirements/?page=more";
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response(page([], next, 0)));

    await getAllPages<Row>("/requirements/");

    // First page + 100 `next` fetches.
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain("cap reached");
    warn.mockRestore();
  });
});

describe("architectureApi.listAll reuses the central walker (R2A-005)", () => {
  const WORKSPACE = "11111111-1111-1111-1111-111111111111";
  const FIRST = `/api/v1/architecture/?workspace_id=${WORKSPACE}&page_size=100`;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("still returns a de-duplicated plain array across pages", async () => {
    const next = `https://other.host.example/api/v1/architecture/?page=2&workspace_id=${WORKSPACE}`;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url) === FIRST) return response(page([row(1)], next, 2));
      return response(page([row(1), row(2)], null, 2));
    });

    const result = await architectureApi.listAll(WORKSPACE);

    expect(result).toEqual([row(1), row(2)]);
    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("emits the same cap warning as getAllPages beyond 100 pages", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response(page([], "/architecture/?page=more", 0))
    );

    const result = await architectureApi.listAll(WORKSPACE);

    expect(Array.isArray(result)).toBe(true);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain("cap reached");
    warn.mockRestore();
  });
});

describe("R2A-008 — no local URL-normalisation regex in API wrappers", () => {
  const wrappers = ["requirements.ts", "architecture.ts"];

  for (const file of wrappers) {
    it(`${file} delegates URL normalisation to client.ts`, () => {
      const source = readFileSync(resolve(process.cwd(), "src/api", file), "utf8");
      expect(source).not.toContain("nextUrl.match(");
      expect(source).not.toContain("(\\/api\\/v1)?");
    });
  }

  it("client.ts keeps exactly one copy of the normalisation regex", () => {
    const source = readFileSync(resolve(process.cwd(), "src/api/client.ts"), "utf8");
    const occurrences = source.split("(\\/api\\/v1)?").length - 1;
    expect(occurrences).toBe(1);
  });
});
