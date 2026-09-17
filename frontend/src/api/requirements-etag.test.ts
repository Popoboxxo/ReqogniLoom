/**
 * GH-868 / bundle #923 — the Requirement update must be able to send the
 * `If-Match` precondition.
 *
 * The backend answers `GET /requirements/{id}/` with `ETag: "<version>"` and
 * refuses a PATCH whose `If-Match` is stale with `412 PRECONDITION_FAILED`.
 * These tests pin the wire format of that header on the client side: a
 * silently dropped `If-Match` looks exactly like a successful save while the
 * concurrent edit is overwritten — the lost update the issue is about.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPatch = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: (...a: unknown[]) => mockPatch(...a),
    delete: vi.fn(),
  },
  getList: vi.fn(),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { requirementsApi } from "./requirements";

const REQUIREMENT = "22222222-2222-2222-2222-222222222222";

describe("requirementsApi optimistic locking (GH-868)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPatch.mockResolvedValue({ id: REQUIREMENT });
  });

  it("sends If-Match with the last-read version when one is supplied", async () => {
    await requirementsApi.update(REQUIREMENT, { title: "t" }, 7);

    const [path, body, , headers] = mockPatch.mock.calls[0];
    expect(path).toBe(`/requirements/${REQUIREMENT}/`);
    expect(body).toEqual({ title: "t" });
    // The tag format mirrors the backend's `ETag` (`"<version>"`).
    expect(headers).toEqual({ "If-Match": '"7"' });
  });

  it("sends no If-Match when no version is supplied (last-writer-wins)", async () => {
    await requirementsApi.update(REQUIREMENT, { title: "t" });

    const [, , , headers] = mockPatch.mock.calls[0];
    expect(headers).toBeUndefined();
  });

  it("sends If-Match even for a version of 0 (an assertion, never 'unset')", async () => {
    await requirementsApi.update(REQUIREMENT, { title: "t" }, 0);

    const [, , , headers] = mockPatch.mock.calls[0];
    expect(headers).toEqual({ "If-Match": '"0"' });
  });
});
