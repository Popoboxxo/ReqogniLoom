/**
 * Regression tests for the `LAST_ADMIN` UX in `PermissionsSection`.
 *
 * The defect (#1081 fallout): the component read ONLY the flat body
 * `{error: "LAST_ADMIN", message}` and branched on `candidate.error ===
 * "LAST_ADMIN"`. The backend now answers the canonical nested envelope
 * `{error: {code, message, details}}`, so that comparison tested an *object*
 * against a string and was `false` unconditionally — the last-admin branch was
 * dead code. Nothing failed, nothing was logged, and the user saw the raw
 * English backend sentence (or, for an unparseable message, a generic error)
 * instead of the localized copy.
 *
 * These tests pin the behaviour on BOTH shapes, because the flat read is
 * deliberately kept for a not-yet-migrated adapter (see `shared/apiError`).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PermissionsSection } from "./PermissionsSection";
import { workspaceMembersApi } from "../../api/workspace-members";
import { itemPermissionsApi } from "../../api/item-permissions";
import { artifactsApi } from "../../api/artifacts";

vi.mock("react-i18next", () => {
  // Interpolate `{{scope}}`/`{{identifier}}` so the assertion can prove the
  // backend's English sentence was PARSED rather than echoed back.
  const t = (
    key: string,
    fallback?: unknown,
    vars?: Record<string, string>,
  ): string => {
    let out = typeof fallback === "string" ? fallback : key;
    for (const [name, value] of Object.entries(vars ?? {})) {
      out = out.split(`{{${name}}}`).join(value);
    }
    return out;
  };
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../api/workspace-members", () => ({
  workspaceMembersApi: {
    list: vi.fn(),
    suspendRole: vi.fn(),
    reactivateRole: vi.fn(),
  },
}));

vi.mock("../../api/item-permissions", () => ({
  itemPermissionsApi: { list: vi.fn(), grant: vi.fn(), revoke: vi.fn() },
}));

vi.mock("../../api/artifacts", () => ({
  artifactsApi: { list: vi.fn() },
}));

const WS_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "22222222-2222-2222-2222-222222222222";

const MEMBER = {
  user_id: USER_ID,
  username: "ada",
  display_name: "Ada Admin",
  email: "ada@example.com",
  roles: ["admin"],
};

const LIST_OK = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

const LAST_ADMIN_MESSAGE =
  "Cannot complete this action: it would leave workspace Team Alpha with no active admin.";

/** The canonical nested envelope — what the backend sends since #1081. */
const NESTED_LAST_ADMIN = {
  error: {
    code: "LAST_ADMIN",
    message: LAST_ADMIN_MESSAGE,
    details: [],
  },
};

/** The legacy flat body, still accepted. */
const FLAT_LAST_ADMIN = { error: "LAST_ADMIN", message: LAST_ADMIN_MESSAGE };

describe("PermissionsSection — LAST_ADMIN handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(artifactsApi.list).mockResolvedValue(LIST_OK);
    vi.mocked(itemPermissionsApi.list).mockResolvedValue([]);
    vi.mocked(workspaceMembersApi.list).mockResolvedValue([MEMBER]);
    vi.mocked(workspaceMembersApi.suspendRole).mockResolvedValue(undefined);
  });

  async function suspendAndReadError(rejection: unknown): Promise<string> {
    vi.mocked(workspaceMembersApi.suspendRole).mockRejectedValue(rejection);

    render(<PermissionsSection workspaceId={WS_ID} />);

    // The members roster must have rendered before the suspend button exists.
    const suspendButton = await screen.findByTestId(
      `workspace-member-suspend-${USER_ID}-admin`,
    );
    await userEvent.click(suspendButton);
    await userEvent.click(
      await screen.findByTestId("workspace-member-suspend-confirm-confirm"),
    );

    const alert = await screen.findByTestId("workspace-members-error");
    await waitFor(() => expect(alert).not.toBeEmptyDOMElement());
    return alert.textContent ?? "";
  }

  it("shows the last-admin UX for the canonical nested error envelope", async () => {
    const text = await suspendAndReadError(NESTED_LAST_ADMIN);

    // The localized copy with the scope/identifier PARSED OUT of the backend's
    // English sentence — this is what was silently unreachable before.
    expect(text).toBe(
      "Cannot complete this action: Workspace Team Alpha would have no active admin left.",
    );
    expect(text).not.toContain("Cannot complete this action: it would leave");
  });

  it("still shows the last-admin UX for the legacy flat error body", async () => {
    const text = await suspendAndReadError(FLAT_LAST_ADMIN);

    expect(text).toBe(
      "Cannot complete this action: Workspace Team Alpha would have no active admin left.",
    );
  });

  it("falls back to the raw message when the sentence does not match", async () => {
    const unparseable = {
      error: { code: "LAST_ADMIN", message: "no admin would remain", details: [] },
    };

    const text = await suspendAndReadError(unparseable);

    expect(text).toBe("no admin would remain");
  });

  it("does not treat an unrelated nested error as LAST_ADMIN", async () => {
    const text = await suspendAndReadError({
      error: { code: "PERMISSION_DENIED", message: "nope", details: [] },
    });

    expect(text).toBe("nope");
  });
});
