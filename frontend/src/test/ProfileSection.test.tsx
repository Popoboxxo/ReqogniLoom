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
import { render, screen, waitFor, act } from "@testing-library/react";
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

/**
 * The profile is now hydrated from GET /auth/me/ (httpOnly cookie session,
 * REQ-052) instead of a sessionStorage snapshot. ``seedUser`` installs a fetch
 * mock whose /auth/me/ GET returns the seeded identity; PATCH updates are
 * driven per-test via ``patchResponse``.
 */
function seedUser(
  first: string,
  last: string,
  patchResponse?: () => Promise<unknown>
): ReturnType<typeof vi.fn> {
  const meUser = {
    id: "u-1",
    username: "tester",
    email: "t@x.test",
    first_name: first,
    last_name: last,
    is_active: true,
    tenant_id: null,
    roles: [],
  };
  const fetchMock = vi.fn(async (_url: string, opts?: RequestInit) => {
    if ((opts?.method ?? "GET").toUpperCase() === "PATCH" && patchResponse) {
      return { ok: true, status: 200, json: patchResponse } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ user: meUser, tenant_id: null, roles: [] }),
    } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

  it("renders the stored display name in read mode", async () => {
    seedUser("Ada", "Lovelace");
    renderProfile();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("saves edited name via PATCH and shows the updated value", async () => {
    const fetchMock = seedUser("Ada", "Lovelace", async () => ({
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
    }));

    renderProfile();
    const user = userEvent.setup();

    // Wait for the /auth/me/ hydration before entering edit mode.
    await screen.findByText("Ada Lovelace");
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
    // (calls also include the initial GET /auth/me/ hydration.)
    const patchCall = fetchMock.mock.calls.find(
      ([, options]) => (options as RequestInit | undefined)?.method === "PATCH"
    );
    expect(patchCall).toBeDefined();
    const [url, options] = patchCall as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/me/");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body as string)).toEqual({ first_name: "Grace", last_name: "Hopper" });
  });
});

/**
 * Issue #1087 — `Ctrl`/`Cmd`+`S` on the profile name form.
 *
 * Covered because the saving mechanism is the same shape as the artifact form's
 * (an async PATCH behind one primary button with an in-flight state), so the
 * same hook and the same three rules apply. The behaviour rules themselves are
 * covered once, in `test/ArtifactFormSaveShortcut.test.tsx`; what is unique
 * here is that the hook is gated on edit mode and that the same-tick guard
 * exists in this component too.
 */
describe("ProfileSection Ctrl/Cmd+S (#1087)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** Dispatch a real keydown on `document` and return it for `defaultPrevented`. */
  function pressSave(init: KeyboardEventInit = {}): KeyboardEvent {
    const event = new KeyboardEvent("keydown", {
      key: "s",
      code: "KeyS",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
      ...init,
    });
    act(() => {
      document.dispatchEvent(event);
    });
    return event;
  }

  async function enterEditMode(): Promise<void> {
    const user = userEvent.setup();
    renderProfile();
    await screen.findByText("Ada Lovelace");
    await user.click(screen.getByTestId("profile-edit-button"));
  }

  it("saves while the name is being edited, and prevents the browser default", async () => {
    const fetchMock = seedUser("Ada", "Lovelace", async () => ({
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
    }));
    await enterEditMode();

    const event = pressSave();

    expect(event.defaultPrevented).toBe(true);
    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        ([, options]) => (options as RequestInit | undefined)?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
    });
  });

  it("leaves the key alone in read mode, where there is nothing to save", async () => {
    seedUser("Ada", "Lovelace");
    renderProfile();
    await screen.findByText("Ada Lovelace");

    const event = pressSave();

    expect(event.defaultPrevented).toBe(false);
  });

  it("advertises the binding on the save control", async () => {
    seedUser("Ada", "Lovelace");
    await enterEditMode();

    const save = screen.getByTestId("profile-save-button");
    expect(save).toHaveAttribute("aria-keyshortcuts", "Control+S Meta+S");
  });

  it("does not double-submit when the chord is held down during a save", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = seedUser("Ada", "Lovelace", async () => {
      await gate;
      return { user: { id: "u-1", username: "tester", email: "t@x.test", first_name: "Ada", last_name: "Lovelace", is_active: true, tenant_id: null, roles: [] } };
    });
    await enterEditMode();

    pressSave();
    pressSave();

    const patchCalls = () =>
      fetchMock.mock.calls.filter(
        ([, options]) => (options as RequestInit | undefined)?.method === "PATCH"
      );
    expect(patchCalls()).toHaveLength(1);
    expect(screen.getByTestId("profile-save-button")).toBeDisabled();

    await act(async () => {
      release();
    });
    // A successful save leaves edit mode (the component's existing contract),
    // so the confirmation replaces the button.
    await waitFor(() => expect(screen.getByTestId("profile-saved")).toBeInTheDocument());
    expect(patchCalls()).toHaveLength(1);
  });
});
