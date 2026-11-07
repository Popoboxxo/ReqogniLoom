/**
 * P1 Task 1.7 — wire contract of `artifactsApi.move`.
 *
 * The backend distinguishes an *absent* `after_id` (append at the end) from an
 * explicit `null` (insert first) — spec B8. `JSON.stringify` drops `undefined`
 * silently, so a body built with `after_id: undefined` would look correct in the
 * calling code and mean the wrong thing on the wire. These tests pin the three
 * cases against the actual request body.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPost = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn(),
}));

import { artifactsApi } from "./artifacts";

const ARTIFACT = "11111111-1111-1111-1111-111111111111";
const PARENT = "22222222-2222-2222-2222-222222222222";
const SIBLING = "33333333-3333-3333-3333-333333333333";

describe("artifactsApi.move (P1 Task 1.7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ id: ARTIFACT });
  });

  it("posts to the artifact's move route", async () => {
    await artifactsApi.move(ARTIFACT, { parent_id: PARENT });

    expect(mockPost.mock.calls[0][0]).toBe(`/artifacts/${ARTIFACT}/move/`);
  });

  it("omits after_id entirely for 'append at the end'", async () => {
    await artifactsApi.move(ARTIFACT, { parent_id: PARENT });

    const body = mockPost.mock.calls[0][1] as Record<string, unknown>;
    expect(body).toEqual({ parent_id: PARENT });
    expect(Object.prototype.hasOwnProperty.call(body, "after_id")).toBe(false);
  });

  it("keeps an explicit null for 'insert first'", async () => {
    await artifactsApi.move(ARTIFACT, { parent_id: PARENT, after_id: null });

    expect(mockPost.mock.calls[0][1]).toEqual({
      parent_id: PARENT,
      after_id: null,
    });
  });

  it("forwards a sibling id as after_id", async () => {
    await artifactsApi.move(ARTIFACT, { parent_id: PARENT, after_id: SIBLING });

    expect(mockPost.mock.calls[0][1]).toEqual({
      parent_id: PARENT,
      after_id: SIBLING,
    });
  });

  it("supports detaching to the top level", async () => {
    await artifactsApi.move(ARTIFACT, { parent_id: null });

    expect(mockPost.mock.calls[0][1]).toEqual({ parent_id: null });
  });
});
