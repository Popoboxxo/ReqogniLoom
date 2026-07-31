/**
 * Co-located tests for the central API client (REQ-051).
 *
 * Focus: the response handling must distinguish HTTP 401 (clear auth state
 * and redirect to login) from HTTP 403 (throw ForbiddenError, no logout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, resetUnauthorizedGuard, setUnauthorizedHandler } from "./client";
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
    resetUnauthorizedGuard();
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

  it("on 403 passes through the server detail message (REQ-138)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(403, {
        detail: "CSRF Failed: Origin checking failed.",
      })
    );

    await expect(apiClient.get("/requirements")).rejects.toThrow(
      "CSRF Failed: Origin checking failed."
    );
  });

  it("on 403 without JSON detail falls back to the default message (REQ-138)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => {
        throw new Error("no body");
      },
    } as unknown as Response);

    await expect(apiClient.get("/requirements")).rejects.toThrow(
      /permission/i
    );
  });

  it("ForbiddenError carries status 403 and a permission message", () => {
    const err = new ForbiddenError();
    expect(err.status).toBe(403);
    expect(err.name).toBe("ForbiddenError");
    expect(err.message).toMatch(/permission/i);
  });
});

// ---------------------------------------------------------------------------
// GitHub #135 — silent token refresh + single-flight retry
// ---------------------------------------------------------------------------

describe("apiClient — silent token refresh on 401 (GitHub #135)", () => {
  const unauthorizedHandler = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    setUnauthorizedHandler(unauthorizedHandler);
    resetUnauthorizedGuard();
    document.documentElement.lang = "en";
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function isRefreshUrl(url: unknown): boolean {
    return typeof url === "string" && url.includes("/auth/refresh/");
  }

  it("on 401 refreshes silently and retries the original request once", async () => {
    let originalCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) return mockResponse(200, {});
      originalCalls += 1;
      return originalCalls === 1 ? mockResponse(401) : mockResponse(200, { id: "1" });
    });

    const result = await apiClient.get("/requirements/1");

    expect(result).toEqual({ id: "1" });
    expect(originalCalls).toBe(2); // 401 then a successful retry
    expect(unauthorizedHandler).not.toHaveBeenCalled();
  });

  it("does not retry more than once (no infinite loop if the retry also 401s)", async () => {
    let refreshCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) {
        refreshCalls += 1;
        return mockResponse(200, {});
      }
      return mockResponse(401);
    });

    await expect(apiClient.get("/requirements")).rejects.toBeDefined();

    // Exactly one refresh attempt for the one original 401 (the retry's own
    // 401 must NOT trigger a second refresh — that would loop forever).
    expect(refreshCalls).toBe(1);
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });

  it("when refresh also fails, clears auth state exactly once", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(401));

    await expect(apiClient.get("/requirements")).rejects.toBeDefined();
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });

  it("single-flight: concurrent 401s share exactly one refresh call", async () => {
    let refreshCalls = 0;
    let originalCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) {
        refreshCalls += 1;
        // Delay the refresh so both concurrent 401s are in flight together.
        await new Promise((resolve) => setTimeout(resolve, 5));
        return mockResponse(200, {});
      }
      originalCalls += 1;
      return originalCalls <= 2 ? mockResponse(401) : mockResponse(200, { ok: true });
    });

    await Promise.all([
      apiClient.get("/requirements"),
      apiClient.get("/architecture"),
    ]);

    expect(refreshCalls).toBe(1);
    expect(unauthorizedHandler).not.toHaveBeenCalled();
  });

  it("does not attempt a refresh for a 401 from /auth/login/ itself", async () => {
    let refreshCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) refreshCalls += 1;
      return mockResponse(401);
    });

    await expect(
      apiClient.post("/auth/login/", { username: "x", password: "y" })
    ).rejects.toBeDefined();

    expect(refreshCalls).toBe(0);
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });

  it("does not attempt a second refresh for a 401 from /auth/refresh/ itself", async () => {
    let refreshCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) refreshCalls += 1;
      return mockResponse(401);
    });

    await expect(apiClient.post("/auth/refresh/", {})).rejects.toBeDefined();

    // The call itself counts once; no nested refresh-of-the-refresh.
    expect(refreshCalls).toBe(1);
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });

  it("a successful refresh re-arms the unauthorized notification for a later expiry", async () => {
    let phase: "first-refresh-ok" | "second-refresh-fails" = "first-refresh-ok";
    let originalCallsInPhase = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) {
        return phase === "first-refresh-ok" ? mockResponse(200, {}) : mockResponse(401);
      }
      originalCallsInPhase += 1;
      // The very first original call in phase 1 401s (triggering the
      // refresh); its retry, and every call in phase 2, succeed at the HTTP
      // level down to the point where the (failing) refresh takes over.
      return phase === "first-refresh-ok" && originalCallsInPhase === 1
        ? mockResponse(401)
        : mockResponse(200, {});
    });

    // First expiry: refresh succeeds, the retry goes through -> no notification.
    await apiClient.get("/requirements");
    expect(unauthorizedHandler).not.toHaveBeenCalled();

    // Second expiry, later: the original call itself now 401s again, but this
    // time the refresh fails -> the (re-armed) guard must fire again.
    phase = "second-refresh-fails";
    originalCallsInPhase = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) return mockResponse(401);
      return mockResponse(401);
    });

    await expect(apiClient.get("/requirements")).rejects.toBeDefined();
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });
});
