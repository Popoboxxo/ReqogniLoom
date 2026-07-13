/**
 * ARCH-L1-001 ReactFrontend — ProfileSection tests.
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings)
 * req_id:  REQ-006 (editable user profile — first_name / last_name)
 *
 * Tests:
 * 1. Read mode renders the stored display name.
 * 2. Edit → change fields → Save issues PATCH /auth/me/ and shows updated name.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import { ProfileSection } from "../components/UserProfileSettings/ProfileSection";
import { AuthProvider } from "../context/AuthContext";

const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  lng: "en",
  resources: { en: { translation: {} } },
});

function seedUser(first: string, last: string): void {
  sessionStorage.setItem("reqflow_token", "test-token");
  sessionStorage.setItem(
    "reqflow_user",
    JSON.stringify({
      id: "u-1",
      username: "tester",
      email: "t@x.test",
      first_name: first,
      last_name: last,
      is_active: true,
      tenant_id: null,
      roles: [],
    })
  );
}

function renderProfile(): ReturnType<typeof render> {
  return render(
    <I18nextProvider i18n={i18n}>
      <AuthProvider>
        <ProfileSection />
      </AuthProvider>
    </I18nextProvider>
  );
}

describe("ProfileSection", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the stored display name in read mode", () => {
    seedUser("Ada", "Lovelace");
    renderProfile();
    expect(screen.getByTestId("profile-display-name").textContent).toBe("Ada Lovelace");
  });

  it("saves edited name via PATCH and shows the updated value", async () => {
    seedUser("Ada", "Lovelace");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        user: {
          id: "u-1",
          username: "tester",
          email: "t@x.test",
          first_name: "Grace",
          last_name: "Hopper",
          is_active: true,
          tenant_id: null,
          roles: [],
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderProfile();
    const user = userEvent.setup();

    await user.click(screen.getByTestId("profile-edit-button"));

    const firstInput = screen.getByTestId("profile-first-name-input");
    const lastInput = screen.getByTestId("profile-last-name-input");
    await user.clear(firstInput);
    await user.type(firstInput, "Grace");
    await user.clear(lastInput);
    await user.type(lastInput, "Hopper");

    await user.click(screen.getByTestId("profile-save-button"));

    await waitFor(() => {
      expect(screen.getByTestId("profile-display-name").textContent).toBe("Grace Hopper");
    });

    // PATCH went to the correct endpoint with the correct method + body.
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/auth/me/");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ first_name: "Grace", last_name: "Hopper" });
  });
});
