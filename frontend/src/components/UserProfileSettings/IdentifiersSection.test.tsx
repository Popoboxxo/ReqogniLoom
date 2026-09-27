/**
 * Issue #1094 — IdentifiersSection unit tests.
 *
 * Covers the two things this section on the profile page owns: the display
 * preference for readable ids, and the profile placement of the copy template
 * (the `<IdChip>` the whole app shares).
 *
 * The persistence gap is asserted too, in the sense that matters: the choice
 * survives a remount through `localStorage`, and the hint tells the user that
 * this is browser-local rather than a server-side preference.
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

import { IdentifiersSection } from "./IdentifiersSection";
import {
  READABLE_IDS_STORAGE_KEY,
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

beforeEach(() => {
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({ user: signedInUser() });
  setReadableIdsVisible(READABLE_IDS_VISIBLE_DEFAULT);
});

afterEach(() => {
  window.localStorage?.removeItem?.(READABLE_IDS_STORAGE_KEY);
  setReadableIdsVisible(READABLE_IDS_VISIBLE_DEFAULT);
});

describe("IdentifiersSection (#1094)", () => {
  it("renders the heading, the hint and the toggle", () => {
    render(<IdentifiersSection />);

    expect(screen.getByTestId("identifiers-section")).toBeInTheDocument();
    expect(screen.getByText("Kennungen")).toBeInTheDocument();
    expect(screen.getByTestId("identifiers-show-readable")).toBeChecked();
  });

  it("states the persistence gap instead of hiding it", () => {
    // There is no display-preference endpoint in the repo (see the hook's
    // header), so the user is told the choice is browser-local.
    render(<IdentifiersSection />);
    expect(screen.getByText(/nur in diesem Browser gespeichert/)).toBeInTheDocument();
  });

  it("hides the readable identifier when the toggle is switched off", () => {
    render(<IdentifiersSection />);
    expect(screen.getByTestId("identifiers-account-chip-value")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    expect(screen.queryByTestId("identifiers-account-chip-value")).not.toBeInTheDocument();
    // The explanation follows the state.
    expect(screen.getByText(/Lesbare IDs sind ausgeblendet/)).toBeInTheDocument();
  });

  it("keeps the choice across a remount", () => {
    const { unmount } = render(<IdentifiersSection />);
    fireEvent.click(screen.getByTestId("identifiers-show-readable"));
    expect(window.localStorage.getItem(READABLE_IDS_STORAGE_KEY)).toBe("false");
    unmount();

    render(<IdentifiersSection />);
    expect(screen.getByTestId("identifiers-show-readable")).not.toBeChecked();
    expect(screen.queryByTestId("identifiers-account-chip-value")).not.toBeInTheDocument();
  });

  it("copies the account's system id and announces it", async () => {
    render(<IdentifiersSection />);

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

  it("keeps the copy control available while the identifier is hidden", () => {
    render(<IdentifiersSection />);
    fireEvent.click(screen.getByTestId("identifiers-show-readable"));

    expect(screen.getByTestId("identifiers-account-chip-copy")).toBeInTheDocument();
  });

  it("shows a status line instead of an empty chip while the session is unresolved", () => {
    // `AuthContext` resolves the session asynchronously; rendering a chip with
    // no identifier would read as "this account has no id".
    mockUseAuth.mockReturnValue({ user: null });

    render(<IdentifiersSection />);

    const status = screen.getByTestId("identifiers-account-loading");
    expect(status).toHaveAttribute("role", "status");
    expect(status).toHaveTextContent("Konto wird geladen…");
    expect(screen.queryByTestId("identifiers-account-chip")).not.toBeInTheDocument();
  });
});
