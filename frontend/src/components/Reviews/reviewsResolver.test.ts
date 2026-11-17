/**
 * B1 (consumer level) — the review queue must receive EVERY in_review item,
 * not only the backend's first page.
 *
 * ``useReviewsData`` reads the queue through ``getReviewsResolver(type).list``,
 * which for requirements delegates to ``requirementsApi.list``. Before the fix
 * that call returned the backend's default first page (25 rows), so the queue
 * faced fewer items than actually matched and an intentionally submitted item
 * could never be selected for approval (e2e/tests/review-workflow.spec.ts).
 *
 * This test drives the real resolver against a mocked HTTP client that serves
 * two pages, and asserts the full 28 items arrive — it fails against the
 * pre-fix single-page implementation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetList = vi.fn();
const mockClientGet = vi.fn();

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockClientGet(...a),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...a: unknown[]) => mockGetList(...a),
  // R2A-005: requirements.ts delegates the walk to this helper. Mirror the
  // real helper here: first page via getList, following pages via apiClient.get
  // (with the URL normalised), so the B1 pagination assertion stays meaningful.
  getAllPagesWithCount: async (
    path: string,
    params: Record<string, string>
  ) => {
    type MockPage = {
      count: number;
      next: string | null;
      results: Array<{ id: string }>;
    };
    const seen = new Set<string>();
    const all: Array<{ id: string }> = [];
    const collect = (p: MockPage) => {
      for (const item of p.results) {
        if (!seen.has(item.id)) {
          seen.add(item.id);
          all.push(item);
        }
      }
    };
    const first: MockPage = await mockGetList(path, {
      ...params,
      page_size: params.page_size ?? "100",
    });
    const count = first.count;
    collect(first);
    let next: string | null = first.next;
    while (next) {
      const relative = next.replace(/^(https?:\/\/[^/]+)?(\/api\/v1)?/, "");
      const page: MockPage = await mockClientGet(
        relative.startsWith("/") ? relative : `/${relative}`
      );
      collect(page);
      next = page.next;
    }
    return { count, results: all };
  },
  extractErrorMessage: (err: unknown) => String(err),
}));

import { getReviewsResolver } from "./reviewsResolver";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";

function requirement(n: number) {
  return {
    id: `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`,
    title: `Requirement ${n}`,
    description: `Description ${n}`,
    status: "in_review",
  };
}

describe("reviewsResolver requirement queue pagination (B1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns all in_review items across pages, not just the first page", async () => {
    const page1 = Array.from({ length: 25 }, (_, i) => requirement(i + 1));
    const page2 = Array.from({ length: 3 }, (_, i) => requirement(i + 26));

    mockGetList.mockResolvedValue({
      count: 28,
      next: "/api/v1/requirements/?page=2&page_size=100&status=in_review",
      previous: null,
      results: page1,
    });
    mockClientGet.mockResolvedValue({
      count: 28,
      next: null,
      previous: null,
      results: page2,
    });

    const items = await getReviewsResolver("requirement").list(
      WORKSPACE,
      "in_review"
    );

    expect(items).toHaveLength(28);
    expect(mockGetList).toHaveBeenCalledWith(
      "/requirements/",
      expect.objectContaining({
        workspace_id: WORKSPACE,
        status: "in_review",
        page_size: "100",
      })
    );
    expect(mockClientGet).toHaveBeenCalledTimes(1);
  });
});
