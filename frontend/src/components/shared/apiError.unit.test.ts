/**
 * Unit tests for the shared error-envelope readers.
 *
 * Two defects motivate this file, both from the #1081 envelope change:
 *
 * 1. `WorkspaceSettings/PermissionsSection` compared an *object* (`error` is an
 *    object in the canonical envelope) against the string `"LAST_ADMIN"`, so its
 *    last-admin branch was dead code with no failing test anywhere.
 * 2. `Settings/UserManagement` carried a private copy of the same helpers with
 *    `(\S+)` for the identifier capture. A workspace NAME routinely contains a
 *    space ("Team Alpha"), so the regex stopped at the first space, the fixed
 *    tail no longer matched, and the localized copy silently degraded to the
 *    raw English backend sentence.
 *
 * Both call sites now import from this module; these tests pin the shared
 * behaviour once instead of per consumer.
 */

import { describe, it, expect } from "vitest";

import {
  errorCode,
  extractMessage,
  extractErrorMessage,
  isLastAdminError,
  parseLastAdminMessage,
} from "./apiError";

const CANONICAL = {
  error: { code: "LAST_ADMIN", message: "leave workspace Team Alpha", details: [] },
};
const FLAT = { error: "LAST_ADMIN", message: "leave workspace Team Alpha" };

describe("errorCode", () => {
  it("reads the code from the canonical nested envelope", () => {
    expect(errorCode(CANONICAL)).toBe("LAST_ADMIN");
  });

  it("still reads the code from the legacy flat envelope", () => {
    expect(errorCode(FLAT)).toBe("LAST_ADMIN");
  });

  it("returns null for anything that is not an error body", () => {
    expect(errorCode(null)).toBeNull();
    expect(errorCode(undefined)).toBeNull();
    expect(errorCode("LAST_ADMIN")).toBeNull();
    expect(errorCode({})).toBeNull();
    expect(errorCode({ error: { message: "no code" } })).toBeNull();
  });
});

describe("extractMessage", () => {
  it("reads the top-level message of the nested envelope verbatim", () => {
    expect(extractMessage(CANONICAL)).toBe("leave workspace Team Alpha");
  });

  it("reads the top-level message of the flat envelope", () => {
    expect(extractMessage(FLAT)).toBe("leave workspace Team Alpha");
  });

  it("returns null when there is no message at all", () => {
    expect(extractMessage({ error: { code: "X" } })).toBeNull();
    expect(extractMessage(null)).toBeNull();
  });

  it("does not prefer details[0].errors[0] over the top-level message", () => {
    // The field-level serializer rejection lives in `details`; the LAST_ADMIN
    // sentence `parseLastAdminMessage` needs verbatim must stay in `message`.
    const body = {
      error: {
        code: "VALIDATION_ERROR",
        message: "the sentence the parser needs",
        details: [{ field: "title", errors: ["this may not be blank"] }],
      },
    };
    expect(extractMessage(body)).toBe("the sentence the parser needs");
  });
});

describe("extractErrorMessage", () => {
  it("falls back to String(err) so generic error paths stay one line", () => {
    expect(extractErrorMessage(FLAT)).toBe("leave workspace Team Alpha");
  });

  it("uses the message of a thrown Error, since an Error is an object too", () => {
    expect(extractErrorMessage(new Error("boom"))).toBe("boom");
  });

  it("stringifies whatever has no message at all", () => {
    expect(extractErrorMessage("plain string failure")).toBe("plain string failure");
  });
});

describe("isLastAdminError", () => {
  it("recognises the refusal in both envelope shapes", () => {
    expect(isLastAdminError(CANONICAL)).toBe(true);
    expect(isLastAdminError(FLAT)).toBe(true);
  });

  it("does not mistake another refusal for the last-admin one", () => {
    expect(isLastAdminError({ error: { code: "PERMISSION_DENIED", message: "no" } })).toBe(false);
  });

  it("does not accept a code without a message", () => {
    expect(isLastAdminError({ error: { code: "LAST_ADMIN" } })).toBe(false);
  });
});

describe("parseLastAdminMessage", () => {
  // The backend sentence is "Cannot complete this action: it would leave
  // {scope} {identifier} with no active admin." (LastAdminError in
  // backend/auth_tenancy/services/authorization.py).
  const sentence = (scope: string, identifier: string) =>
    `Cannot complete this action: it would leave ${scope} ${identifier} with no active admin.`;

  it("extracts scope and identifier", () => {
    expect(parseLastAdminMessage(sentence("workspace", "Acme"))).toEqual({
      scope: "Workspace",
      identifier: "Acme",
    });
  });

  it("keeps a multi-word identifier intact", () => {
    // The `\S+` bug: this returned null, so the UI fell back to echoing the
    // raw English sentence into a German interface.
    expect(parseLastAdminMessage(sentence("tenant", "Team Alpha"))).toEqual({
      scope: "Tenant",
      identifier: "Team Alpha",
    });
    expect(parseLastAdminMessage(sentence("workspace", "R&D Group North"))).toEqual({
      scope: "Workspace",
      identifier: "R&D Group North",
    });
  });

  it("returns null for a sentence it cannot parse", () => {
    expect(parseLastAdminMessage("something else entirely")).toBeNull();
  });
});
