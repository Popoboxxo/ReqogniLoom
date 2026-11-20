import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { ApiRequestError } from "../api/errors";
import { RequestTimeoutError } from "../api/client";
import { classifyUserError, toUserErrorMessage } from "./userErrorMessage";

const t = ((key: string) => key) as unknown as TFunction;

describe("classifyUserError", () => {
  it("treats fetch rejections as network, not as raw TypeError text", () => {
    expect(classifyUserError(new TypeError("Failed to fetch"))).toBe("network");
    expect(classifyUserError(new Error("Load failed"))).toBe("network");
  });

  it("classifies timeouts, statuses and unknown values", () => {
    expect(classifyUserError(new RequestTimeoutError("/x", 1000))).toBe("timeout");
    expect(
      classifyUserError(new ApiRequestError({ status: 429, message: "slow down" }))
    ).toBe("rate_limited");
    expect(
      classifyUserError(new ApiRequestError({ status: 403, message: "no" }))
    ).toBe("unauthorized");
    expect(
      classifyUserError(new ApiRequestError({ status: 404, message: "gone" }))
    ).toBe("not_found");
    expect(
      classifyUserError(new ApiRequestError({ status: 502, message: "bad gateway" }))
    ).toBe("server");
    expect(classifyUserError(new Error("weird"))).toBe("generic");
  });
});

describe("toUserErrorMessage", () => {
  it("never leaks a browser transport string into the alert", () => {
    expect(toUserErrorMessage(new TypeError("Failed to fetch"), t)).toBe(
      "errors.network"
    );
  });

  it("uses the server message for validation errors", () => {
    const err = new ApiRequestError({
      status: 400,
      message: "Validation failed",
      details: [{ field: "base_url", errors: ["must be a URL"] }],
    });
    expect(toUserErrorMessage(err, t)).toBe("base_url: must be a URL");
  });

  it("keeps a localised operation context in front of the cause", () => {
    expect(
      toUserErrorMessage(new TypeError("Failed to fetch"), t, "Speichern fehlgeschlagen.")
    ).toBe("Speichern fehlgeschlagen. errors.network");
  });
});
