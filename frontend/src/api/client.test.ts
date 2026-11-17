/**
 * Co-located tests for the central API client (REQ-051).
 *
 * Focus: the response handling must distinguish HTTP 401 (clear auth state
 * and redirect to login) from HTTP 403 (throw ForbiddenError, no logout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  advanceAuthSessionGeneration,
  apiClient,
  asList,
  extractApiErrorMessage,
  extractErrorMessage,
  resetUnauthorizedGuard,
  setUnauthorizedHandler,
  RequestTimeoutError,
} from "./client";
import { ApiRequestError, ForbiddenError, UnprocessableEntityError } from "./errors";

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
    advanceAuthSessionGeneration();
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

  it("can suppress the global handler for a session-restore request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(401));

    await expect(
      apiClient.get("/auth/me/", { suppressUnauthorizedNotification: true }),
    ).rejects.toBeDefined();
    expect(unauthorizedHandler).not.toHaveBeenCalled();
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
    advanceAuthSessionGeneration();
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

  it("ignores a stale 401 after the auth session generation changes", async () => {
    let resolveOriginal!: (response: Response) => void;
    let markStarted!: () => void;
    const originalResponse = new Promise<Response>((resolve) => {
      resolveOriginal = resolve;
    });
    const started = new Promise<void>((resolve) => {
      markStarted = resolve;
    });
    let refreshCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (isRefreshUrl(url)) {
        refreshCalls += 1;
        return mockResponse(200, {});
      }
      markStarted();
      return originalResponse;
    });

    const pending = apiClient.get("/requirements/1");
    await started;
    advanceAuthSessionGeneration();
    resolveOriginal(mockResponse(401));

    await expect(pending).rejects.toMatchObject({
      error: { code: "AUTHENTICATION_REQUIRED" },
    });
    expect(refreshCalls).toBe(0);
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
      "title: contains disallowed content: HTML markup is not permitted in free-text fields."
    );
  });

  it("names the offending field, because the caller renders this detached from it", () => {
    // Regression: the attribute-definition create gate rejects a missing
    // field with the bare message "is required". Every caller shows this as a
    // dialog-level alert, so without the field name the user was told only
    // that *something* was required. `details[0].field` was already on the
    // wire and simply discarded.
    expect(
      extractApiErrorMessage({
        error: {
          code: "VALIDATION_ERROR",
          message: "acceptance_criteria: is required",
          details: [{ field: "acceptance_criteria", errors: ["is required"] }],
        },
      })
    ).toBe("acceptance_criteria: is required");
  });

  it("still returns a bare detail message when the server names no field", () => {
    expect(
      extractApiErrorMessage({
        error: {
          code: "VALIDATION_ERROR",
          message: "Validation failed.",
          details: [{ errors: ["is required"] }],
        },
      })
    ).toBe("is required");
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

// ---------------------------------------------------------------------------
// Keepalive writes — a preference change must survive the page that sent it
// (connection view V.5: toggle the edge switch, reload, the switch stayed on)
// ---------------------------------------------------------------------------

describe("apiClient.patchKeepalive — writes that outlive the document", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    advanceAuthSessionGeneration();
    setUnauthorizedHandler(vi.fn());
    resetUnauthorizedGuard();
    document.documentElement.lang = "en";
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the PATCH with keepalive: true", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(mockResponse(200, { values: { a: false } }));

    const result = await apiClient.patchKeepalive(
      "/users/me/preference-values/",
      { values: { a: false } }
    );

    expect(result).toEqual({ values: { a: false } });
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/v1/users/me/preference-values/");
    expect(init?.method).toBe("PATCH");
    // The whole point: without this flag the browser aborts the request when
    // the document unloads, and the reload shows the previous value again.
    expect(init?.keepalive).toBe(true);
    expect(init?.body).toBe(JSON.stringify({ values: { a: false } }));
  });

  it("keeps the shared response handling (a 403 stays a ForbiddenError)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(403, { detail: "CSRF Failed: Origin checking failed." })
    );

    await expect(
      apiClient.patchKeepalive("/users/me/preference-values/", { values: {} })
    ).rejects.toBeInstanceOf(ForbiddenError);
  });

  it("keeps the same handler/notification behaviour on 401 as apiClient.patch", async () => {
    const unauthorizedHandler = vi.fn();
    setUnauthorizedHandler(unauthorizedHandler);
    // Both the write and the refresh fail → one notification, then a typed error.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(401));

    await expect(
      apiClient.patchKeepalive("/users/me/preference-values/", { values: {} })
    ).rejects.toMatchObject({ error: { code: "AUTHENTICATION_REQUIRED" } });
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// R2A-006 — typed errors for every non-2xx status.
//
// The backend now emits a stable `error.{code,message,details}` envelope plus
// a `request_id` on every error. The client must surface all four fields on a
// common `ApiRequestError` base regardless of status, while keeping the
// existing `ForbiddenError` / `UnprocessableEntityError` subclasses (and their
// constructors) intact so no caller's `instanceof` check changes behaviour.
// ---------------------------------------------------------------------------

describe("apiClient — typed error envelope for every status (R2A-006)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    advanceAuthSessionGeneration();
    resetUnauthorizedGuard();
    document.documentElement.lang = "en";
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const statuses = [
    { status: 400, code: "VALIDATION_ERROR" },
    { status: 403, code: "PERMISSION_DENIED" },
    { status: 404, code: "NOT_FOUND" },
    { status: 422, code: "UNPROCESSABLE_ENTITY" },
    { status: 500, code: "INTERNAL_SERVER_ERROR" },
  ];

  for (const { status, code } of statuses) {
    it(`exposes status/code/details/requestId on ${status}`, async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        mockResponse(status, {
          error: {
            code,
            message: `failure ${status}`,
            details: [{ field: "title", errors: ["is required"] }],
          },
          request_id: `req-${status}`,
          ...(status === 422 ? { findings: [{ rule: "I1" }] } : {}),
        })
      );

      let caught: unknown;
      try {
        await apiClient.get("/things/");
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(ApiRequestError);
      const typed = caught as ApiRequestError;
      expect(typed.status).toBe(status);
      expect(typed.code).toBe(code);
      expect(typed.details).toEqual([{ field: "title", errors: ["is required"] }]);
      expect(typed.requestId).toBe(`req-${status}`);
      // The message extractor prefers the field-level detail from the base.
      expect(extractApiErrorMessage(typed)).toBe("title: is required");
      // The legacy raw envelope stays readable for existing callers.
      expect(typed.error.code).toBe(code);
    });
  }

  it("keeps 403 as a ForbiddenError (and an ApiRequestError)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(403, {
        detail: "CSRF Failed: Origin checking failed.",
        request_id: "req-403",
      })
    );

    let caught: unknown;
    try {
      await apiClient.get("/things/");
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ForbiddenError);
    expect(caught).toBeInstanceOf(ApiRequestError);
    expect((caught as ForbiddenError).status).toBe(403);
    expect((caught as ForbiddenError).requestId).toBe("req-403");
  });

  it("keeps 422 as an UnprocessableEntityError and preserves findings", async () => {
    const findings = [{ rule: "I1", message: "cycle detected" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(422, {
        error: { code: "AUDIT_REMEDIATION_FAILED", message: "audit failed", details: [] },
        findings,
        request_id: "req-422",
      })
    );

    let caught: unknown;
    try {
      await apiClient.post("/architecture/1/decompose/commit/", {});
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(UnprocessableEntityError);
    expect(caught).toBeInstanceOf(ApiRequestError);
    const typed = caught as UnprocessableEntityError;
    expect(typed.findings).toEqual(findings);
    expect(typed.requestId).toBe("req-422");
    expect(typed.status).toBe(422);
  });
});

describe("asList — pagination envelope tolerance (INT-05)", () => {
  it("returns a bare array unchanged", () => {
    expect(asList<number>([1, 2, 3])).toEqual([1, 2, 3]);
  });

  it("unwraps the StandardPagination envelope's results", () => {
    const envelope = {
      count: 2,
      next: null,
      previous: null,
      page_size: 25,
      max_page_size: 100,
      results: [{ id: "a" }, { id: "b" }],
    };
    expect(asList<{ id: string }>(envelope)).toEqual([{ id: "a" }, { id: "b" }]);
  });

  it("yields [] for anything that is neither array nor envelope", () => {
    expect(asList(undefined)).toEqual([]);
    expect(asList(null)).toEqual([]);
    expect(asList({ detail: "oops" })).toEqual([]);
    // An object with a non-array `results` must not be mistaken for an envelope.
    expect(asList({ results: "not-an-array" })).toEqual([]);
  });
});
