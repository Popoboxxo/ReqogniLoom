/**
 * FE-001 regression — queryClient query retry policy.
 *
 * The policy must be *status-aware*: 4xx responses are deterministic client
 * errors and must never be retried, except 408 (Request Timeout) and 429
 * (Too Many Requests), which are transient. Network failures and 5xx
 * responses are retried up to three attempts. The old implementation only
 * excluded the legacy `AUTHENTICATION_REQUIRED` envelope, so a 403
 * `ForbiddenError` was retried three times — this test is red until the
 * policy switches to `instanceof ApiRequestError` + `status`.
 */
import { describe, it, expect } from "vitest";
import { ApiRequestError, ForbiddenError } from "../api/errors";
import { queryClient } from "../queries/queryClient";

type RetryFn = (failureCount: number, error: unknown) => boolean;

function retryPolicy(): RetryFn {
  const retry = queryClient.getDefaultOptions().queries?.retry;
  if (typeof retry !== "function") {
    throw new Error("queryClient must configure a functional query retry policy");
  }
  return retry as RetryFn;
}

function httpError(status: number): ApiRequestError {
  return new ApiRequestError({ status, code: `HTTP_${status}`, message: `HTTP ${status}` });
}

describe("queryClient query retry policy (FE-001)", () => {
  it("does NOT retry a 403 ForbiddenError (RED: old policy returns true)", () => {
    expect(retryPolicy()(0, new ForbiddenError())).toBe(false);
  });

  it("never retries 4xx except 408/429", () => {
    for (const status of [400, 401, 403, 404, 409, 422]) {
      expect(retryPolicy()(0, httpError(status)), `status ${status}`).toBe(false);
    }
  });

  it("retries 408 and 429 but respects the three-attempt cap", () => {
    for (const status of [408, 429]) {
      expect(retryPolicy()(0, httpError(status)), `${status} @0`).toBe(true);
      expect(retryPolicy()(2, httpError(status)), `${status} @2`).toBe(true);
      expect(retryPolicy()(3, httpError(status)), `${status} @3`).toBe(false);
    }
  });

  it("retries network errors and 5xx up to three attempts", () => {
    const network = new Error("Network down");
    expect(retryPolicy()(0, network), "network @0").toBe(true);
    expect(retryPolicy()(2, network), "network @2").toBe(true);
    expect(retryPolicy()(3, network), "network @3").toBe(false);
    for (const status of [500, 502, 503, 504]) {
      expect(retryPolicy()(0, httpError(status)), `${status} @0`).toBe(true);
      expect(retryPolicy()(3, httpError(status)), `${status} @3`).toBe(false);
    }
  });

  it("still excludes a legacy AUTHENTICATION_REQUIRED envelope", () => {
    const legacy = { error: { code: "AUTHENTICATION_REQUIRED" } };
    expect(retryPolicy()(0, legacy)).toBe(false);
  });
});
