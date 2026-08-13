/**
 * Co-located tests for the central API client (REQ-051).
 *
 * Focus: the response handling must distinguish HTTP 401 (clear auth state
 * and redirect to login) from HTTP 403 (throw ForbiddenError, no logout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  apiClient,
  extractApiErrorMessage,
  extractErrorMessage,
  resetUnauthorizedGuard,
  setUnauthorizedHandler,
  RequestTimeoutError,
} from "./client";
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

describe("apiClient — request timeout (GitHub #450)", () => {
  // A hung fetch() must eventually reject instead of leaving the caller's
  // Promise pending forever — otherwise a `try { } finally { setIsLoading(false) }`
  // caller (MetricsDashboard, AuditDashboard) never resets its loading flag,
  // leaving the Refresh button/filter controls stuck disabled indefinitely.
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("aborts and rejects with RequestTimeoutError once the request hangs past the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          // Mirror real fetch()'s abort behaviour: never settle on its own,
          // only reject once the AbortSignal fires.
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        })
    );

    const pending = apiClient.get("/metrics/");
    const assertion = expect(pending).rejects.toBeInstanceOf(RequestTimeoutError);

    await vi.advanceTimersByTimeAsync(30_000);

    await assertion;
  });

  it("does not touch fetch's own AbortSignal wiring for a request that resolves before the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(200, { ok: true }));

    await expect(apiClient.get("/metrics/")).resolves.toEqual({ ok: true });
  });

  // GitHub #445: real LLM calls (compressed bundle export, AI decomposition,
  // ...) legitimately take far longer than 30s. Requests to these paths must
  // survive the normal 30s window instead of being killed mid-response.
  it("does not abort a known long-running LLM path at the normal 30s timeout", async () => {
    let aborted = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init?: RequestInit) =>
        new Promise((resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted = true;
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
          // Resolves well past 30s but comfortably inside the 180s grace
          // period for long-running paths.
          setTimeout(() => resolve(mockResponse(200, { drafts: [] })), 90_000);
        })
    );

    const pending = apiClient.post(
      "/requirements/11111111-1111-1111-1111-111111111111/decompose-next-level/",
      {}
    );

    await vi.advanceTimersByTimeAsync(30_000);
    expect(aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(60_000);
    await expect(pending).resolves.toEqual({ drafts: [] });
    expect(aborted).toBe(false);
  });

  it("aborts a known long-running LLM path once it exceeds the 180s grace period", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        })
    );

    const pending = apiClient.get(
      "/architecture/22222222-2222-2222-2222-222222222222/requirement-bundle/?mode=compressed"
    );
    const assertion = expect(pending).rejects.toBeInstanceOf(RequestTimeoutError);

    await vi.advanceTimersByTimeAsync(180_000);

    await assertion;
  });

  it("an explicit timeoutMs overrides both the 30s default and the long-running-path default", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        })
    );

    // A plain CRUD path, but called with a short explicit override — must
    // abort well before the 30s default.
    const pending = apiClient.get("/requirements/1", 5_000);
    const assertion = expect(pending).rejects.toBeInstanceOf(RequestTimeoutError);

    await vi.advanceTimersByTimeAsync(5_000);

    await assertion;
  });
});

/**
 * GitHub #339 / #340 — the SPA swallowed server validation errors on save.
 *
 * `extractApiErrorMessage` is the seam every save/create handler now uses to
 * decide *what* to show: the server's own reason when there is one, otherwise
 * `null` so the caller can fall back to its own localised copy instead of
 * rendering `[object Object]`.
 */
describe("extractApiErrorMessage (#339/#340)", () => {
  it("prefers the field-level detail over the generic top-level message", () => {
    // Shape produced by build_error_response() for a serializer rejection —
    // see backend/rest_api/tests/test_security_hardening_269.py
    // ::test_rejection_uses_the_standard_error_envelope.
    expect(
      extractApiErrorMessage({
        error: {
          code: "VALIDATION_ERROR",
          message: "Validation failed.",
          details: [
            {
              field: "title",
              errors: [
                "contains disallowed content: HTML markup is not permitted in free-text fields.",
              ],
            },
          ],
        },
      })
    ).toBe(
      "contains disallowed content: HTML markup is not permitted in free-text fields."
    );
  });

  it("falls back to the top-level message when there are no field details", () => {
    // Shape produced by _service_error_response() for an application-layer
    // ValidationError, e.g. the extended preset's change_reason policy.
    expect(
      extractApiErrorMessage({
        error: {
          code: "VALIDATION_ERROR",
          message: "change_reason required by workspace preset policy",
          details: [],
        },
      })
    ).toBe("change_reason required by workspace preset policy");
  });

  it("returns the message of the typed errors apiFetch itself throws", () => {
    expect(extractApiErrorMessage(new ForbiddenError())).toBe(
      "You do not have permission to perform this action."
    );
  });

  it("returns null for an opaque value so the caller's own copy wins", () => {
    expect(extractApiErrorMessage({ something: "unexpected" })).toBeNull();
    expect(extractApiErrorMessage(undefined)).toBeNull();
  });

  it("extractErrorMessage still always yields a string", () => {
    expect(extractErrorMessage({ nope: true })).toBe("[object Object]");
    expect(
      extractErrorMessage({ error: { code: "X", message: "boom", details: [] } })
    ).toBe("boom");
  });
});
