/**
 * Co-located tests for the central API client (REQ-051).
 *
 * Focus: the response handling must distinguish HTTP 401 (clear auth state
 * and redirect to login) from HTTP 403 (throw ForbiddenError, no logout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, setUnauthorizedHandler } from "./client";
import { ForbiddenError } from "./errors";

function mockResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("apiClient — 401 vs 403 handling (REQ-051)", () => {
  const unauthorizedHandler = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    setUnauthorizedHandler(unauthorizedHandler);
    document.documentElement.lang = "en";
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("on 401 invokes the unauthorized handler (logout/redirect)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(401));

    await expect(apiClient.get("/requirements")).rejects.toBeDefined();
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });

  it("on 403 throws ForbiddenError and does NOT log the user out", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(403));

    await expect(apiClient.get("/requirements")).rejects.toBeInstanceOf(
      ForbiddenError
    );
    expect(unauthorizedHandler).not.toHaveBeenCalled();
  });

  it("ForbiddenError carries status 403 and a permission message", () => {
    const err = new ForbiddenError();
    expect(err.status).toBe(403);
    expect(err.name).toBe("ForbiddenError");
    expect(err.message).toMatch(/permission/i);
  });
});
