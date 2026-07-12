/**
 * Tests for versioning/diff error-handling — REQ-001.
 *
 * req_id: REQ-001 (Versioning/Diff-Service — no "[object Object]" in UI)
 *
 * Verifies that `extractErrorMessage` correctly extracts a human-readable
 * string from the ApiError shape that `apiClient` throws on non-2xx
 * responses. This is the root-cause of "error [object Object]" in the
 * diff view before the fix in ArtifactDiff.tsx.
 */

import { describe, it, expect } from "vitest";
import { extractErrorMessage } from "./client";

// ---------------------------------------------------------------------------
// extractErrorMessage — handles every shape the API client can throw
// ---------------------------------------------------------------------------

describe("extractErrorMessage — REQ-001", () => {
  it("extracts message from a well-formed ApiError object", () => {
    const apiError = {
      error: {
        code: "NOT_FOUND",
        message: "Requirement not found",
        details: [],
      },
    };
    expect(extractErrorMessage(apiError)).toBe("Requirement not found");
  });

  it("prefers the first field-level detail error over the top-level message", () => {
    const apiError = {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed",
        details: [
          { field: "title", errors: ["This field is required."] },
        ],
      },
    };
    expect(extractErrorMessage(apiError)).toBe("This field is required.");
  });

  it("falls back to top-level message when details array is empty", () => {
    const apiError = {
      error: {
        code: "INTERNAL_SERVER_ERROR",
        message: "HTTP 500",
        details: [],
      },
    };
    expect(extractErrorMessage(apiError)).toBe("HTTP 500");
  });

  it("does NOT produce '[object Object]' for a plain ApiError object", () => {
    const apiError = {
      error: {
        code: "AUTHENTICATION_REQUIRED",
        message: "Authentication required",
        details: [],
      },
    };
    // String(apiError) would give "[object Object]" — extractErrorMessage must not do this
    const result = extractErrorMessage(apiError);
    expect(result).not.toBe("[object Object]");
    expect(result).toBe("Authentication required");
  });

  it("handles a real Error instance (message property present)", () => {
    const err = new Error("Network timeout");
    // extractErrorMessage falls back to String(err) for non-ApiError shapes
    // For an Error instance with no .error property, it falls through to String()
    const result = extractErrorMessage(err);
    // Should not be "[object Object]"
    expect(result).not.toBe("[object Object]");
  });

  it("handles null / undefined gracefully without throwing", () => {
    expect(() => extractErrorMessage(null)).not.toThrow();
    expect(() => extractErrorMessage(undefined)).not.toThrow();
  });

  it("handles a string thrown directly", () => {
    const result = extractErrorMessage("Something went wrong");
    expect(result).toBe("Something went wrong");
  });

  it("returns String(err) as final fallback for unrecognised shapes", () => {
    // A plain object with no .error key — not an ApiError, not an Error
    const weird = { foo: "bar" };
    const result = extractErrorMessage(weird);
    // Should be the String() representation, which for a plain object is "[object Object]"
    // This is acceptable only for truly unrecognised shapes (not API errors)
    expect(typeof result).toBe("string");
  });
});
