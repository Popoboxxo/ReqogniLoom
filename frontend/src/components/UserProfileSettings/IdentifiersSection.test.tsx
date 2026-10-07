/**
 * Issue #1094 / #1096 — IdentifiersSection unit tests.
 *
 * Covers the two things this section on the profile page owns: the display
 * preference for readable ids, and the profile placement of the copy template
 * (the `<IdChip>` the whole app shares).
 *
 * #1096 added persistence: the section is the writer for
 * `GET/PATCH /api/v1/users/me/display-preferences/`. The tests below pin the
 * server-backed lifecycle — load on mount, optimistic save, server value wins,
 * rollback + visible error on a rejected save, and an explicit loading state —
 * on top of the copy template from #1094.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

const mockUseAuth = vi.fn();
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../../api/display-preferences", () => ({
  displayPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

import { IdentifiersSection } from "./IdentifiersSection";
import { displayPreferencesApi } from "../../api/display-preferences";
import {
  READABLE_IDS_VISIBLE_DEFAULT,
  setReadableIdsVisible,
} from "../../hooks/useReadableIdsVisible";

const ACCOUNT_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

const writeText = vi.fn();

function signedInUser(): unknown {
  return {
    id: ACCOUNT_UUID,
    username: "daniel",
    email: "daniel@example.com",
    first_name: "Daniel",
    last_name: "Duchrow",
    is_active: true,
    tenant_id: null,
    roles: [],
  };
}

/** Render and wait until the initial GET has settled (no loading line). */
async function renderSettled(): Promise<void> {
  render(<IdentifiersSection />);
  await waitFor(() => {
    expect(screen.queryByTestId("identifiers-loading")).not.toBeInTheDocument();
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({ user: signedInUser() });
  // Server default: readable ids visible.
  vi.mocked(displayPreferencesApi.get).mockResolvedValue({ show_readable_ids: true });
  vi.mocked(displayPreferencesApi.update).mockImplementation(async (changes) => ({
    show_readable_ids: changes.show_readable_ids ?? true,
  }));
  setReadableIdsVisible(READABLE_IDS_VISIBLE_DEFAULT);
});

afterEach(() => {
  setReadableIdsVisible(READABLE_IDS_VISIBLE_DEFAULT);
});

describe("IdentifiersSection (#1094)", () => {
  it("renders the heading, the hint and the toggle", async () => {
    await renderSettled();

    expect(screen.getByTestId("identifiers-section")).toBeInTheDocument();
    expect(screen.getByText("Kennungen")).toBeInTheDocument();
    expect(screen.getByTestId("identifiers-show-readable")).toBeChecked();
  });

  it("tells the user the preference is account-scoped, not browser-local (#1096)", async () => {
    await renderSettled();

    expect(screen.getByText(/Benutzerkonto/)).toBeInTheDocument();
    // The old browser-local disclaimer must be gone now that the server persists it.
    expect(screen.queryByText(/nur in diesem Browser/)).not.toBeInTheDocument();
  });

  it("hides the readable identifier when the toggle is switched off", async () => {
    await renderSettled();
    expect(screen.getByTestId("identifiers-account-chip-value")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    await waitFor(() => {
      expect(screen.queryByTestId("identifiers-account-chip-value")).not.toBeInTheDocument();
    });
    // The explanation follows the state.
    expect(screen.getByText(/Lesbare IDs sind ausgeblendet/)).toBeInTheDocument();
  });

  it("loads the preference from the server on mount", async () => {
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({ show_readable_ids: false });

    await renderSettled();

    expect(displayPreferencesApi.get).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("identifiers-show-readable")).not.toBeChecked();
    expect(screen.queryByTestId("identifiers-account-chip-value")).not.toBeInTheDocument();
  });

  it("saves a toggle through the endpoint with the new value", async () => {
    await renderSettled();

    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    await waitFor(() => {
      expect(displayPreferencesApi.update).toHaveBeenCalledWith({ show_readable_ids: false });
    });
  });

  it("applies the server's returned value over the optimistic guess", async () => {
    await renderSettled();
    // The user hides it, but the server answers "still visible".
    vi.mocked(displayPreferencesApi.update).mockResolvedValue({ show_readable_ids: true });

    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    await waitFor(() => {
      expect(displayPreferencesApi.update).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByTestId("identifiers-show-readable")).toBeChecked();
    expect(screen.queryByTestId("identifiers-error")).not.toBeInTheDocument();
  });

  it("rolls back and shows an alert when the save is rejected", async () => {
    await renderSettled();
    vi.mocked(displayPreferencesApi.update).mockRejectedValue({
      error: { message: "nope" },
    });

    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    expect(await screen.findByTestId("identifiers-error")).toHaveTextContent("nope");
    // The failed write must not survive as a silent local change.
    expect(screen.getByTestId("identifiers-show-readable")).toBeChecked();
  });

  it("shows an alert when the initial load fails, without breaking the section", async () => {
    vi.mocked(displayPreferencesApi.get).mockRejectedValue({ error: { message: "boom" } });

    await renderSettled();

    expect(screen.getByTestId("identifiers-error")).toHaveTextContent("boom");
    // The section stays usable with the cached/default value.
    expect(screen.getByTestId("identifiers-show-readable")).toBeInTheDocument();
  });

  it("shows an explicit loading state and disables the toggle until the GET settles", async () => {
    let resolveGet: (value: { show_readable_ids: boolean }) => void = () => undefined;
    vi.mocked(displayPreferencesApi.get).mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve;
      }),
    );

    render(<IdentifiersSection />);

    expect(screen.getByTestId("identifiers-loading")).toBeInTheDocument();
    expect(screen.getByTestId("identifiers-show-readable")).toBeDisabled();

    resolveGet({ show_readable_ids: false });

    await waitFor(() => {
      expect(screen.queryByTestId("identifiers-loading")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("identifiers-show-readable")).not.toBeChecked();
  });

  it("copies the account's system id and announces it", async () => {
    await renderSettled();

    // The account's readable handle is its username — the same uid-vs-system-id
    // shape an artifact has, so the demonstration is the real behaviour.
    expect(screen.getByTestId("identifiers-account-chip-value")).toHaveTextContent("daniel");

    fireEvent.click(screen.getByTestId("identifiers-account-chip-copy"));

    expect(writeText).toHaveBeenCalledWith(ACCOUNT_UUID);
    await waitFor(() =>
      expect(screen.getByTestId("identifiers-account-chip-status")).toHaveTextContent(
        "UUID kopiert"
      )
    );
  });

  it("keeps the copy control available while the identifier is hidden", async () => {
    await renderSettled();
    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    await waitFor(() => {
      expect(screen.queryByTestId("identifiers-account-chip-value")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("identifiers-account-chip-copy")).toBeInTheDocument();
  });

  it("shows a status line instead of an empty chip while the session is unresolved", async () => {
    // `AuthContext` resolves the session asynchronously; rendering a chip with
    // no identifier would read as "this account has no id".
    mockUseAuth.mockReturnValue({ user: null });

    await renderSettled();

    const status = screen.getByTestId("identifiers-account-loading");
    expect(status).toHaveAttribute("role", "status");
    expect(status).toHaveTextContent("Konto wird geladen…");
    expect(screen.queryByTestId("identifiers-account-chip")).not.toBeInTheDocument();
  });
});
