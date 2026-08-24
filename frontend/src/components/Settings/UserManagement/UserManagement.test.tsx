/**
 * Tests for UserManagement (multi-user management design spec, Task 12).
 *
 * Verifies:
 * - the user list renders with active/inactive state
 * - a LAST_ADMIN 409 surfaces as a specific, localized inline error (not a
 *   generic failure) — the real `apiClient` throws the backend's flat
 *   `{error, message}` body directly (see `frontend/src/api/client.ts`
 *   `apiFetch`'s `!response.ok` branch), NOT an axios-style
 *   `{response: {status, data}}` wrapper, so that is what is mocked here
 * - the component is gated on `isTenantAdmin`, not the workspace `roles`
 * - the create-user dialog calls `usersApi.create`
 * - grant/revoke tenant-admin row actions call the right API method
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UserManagement } from "./UserManagement";
import { usersApi } from "../../../api/users";
import * as authModule from "../../../context/AuthContext";
import deLocale from "../../../i18n/locales/de.json";

vi.mock("../../../api/users");
vi.mock("../../../context/AuthContext");

/**
 * Look up a dot-path key in the real `de.json` — mirrors
 * `EmptyState.test.tsx`'s `resolveLocaleKey`: if the key exists in the real
 * locale file its real (interpolatable) value wins over the caller's
 * fallback, so a wrong i18n key surfaces as a failing assertion instead of
 * being silently masked by a fallback-only mock.
 */
function resolveLocaleKey(key: string): string | undefined {
  const value = key
    .split(".")
    .reduce<unknown>(
      (node, segment) =>
        node && typeof node === "object" ? (node as Record<string, unknown>)[segment] : undefined,
      deLocale
    );
  return typeof value === "string" ? value : undefined;
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown, options?: Record<string, string>) => {
      const fallbackStr = typeof fallback === "string" ? fallback : undefined;
      const params = typeof fallback === "object" && fallback !== null ? (fallback as Record<string, string>) : options;
      const resolved = resolveLocaleKey(key) ?? fallbackStr ?? key;
      if (!params) return resolved;
      return Object.entries(params).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
  }),
}));

function mockAuth(isTenantAdmin: boolean): void {
  vi.mocked(authModule.useAuth).mockReturnValue({
    isTenantAdmin,
  } as unknown as ReturnType<typeof authModule.useAuth>);
}

const USERS = [
  { id: "u1", username: "alice", email: "alice@t.test", is_active: true, is_tenant_admin: true },
  { id: "u2", username: "bob", email: "bob@t.test", is_active: false, is_tenant_admin: false },
];

describe("UserManagement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usersApi.list).mockResolvedValue(USERS);
    mockAuth(true);
  });

  it("renders the user list with active/inactive state", async () => {
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("hides the page and shows a gate message for non-tenant-admins", async () => {
    mockAuth(false);
    render(<UserManagement />);
    expect(await screen.findByTestId("user-management-tenant-admin-only")).toBeInTheDocument();
    expect(screen.queryByTestId("user-management-table")).not.toBeInTheDocument();
    // Never even calls the tenant-admin-guarded endpoint for a non-admin —
    // the real enforcement is server-side, but the UX-gate shouldn't fire a
    // request that is only going to 403 anyway.
    expect(usersApi.list).not.toHaveBeenCalled();
  });

  it("surfaces a LAST_ADMIN error inline, not as a generic failure", async () => {
    // Real production shape thrown by `apiClient` for a non-2xx JSON error
    // body (see `apiFetch`'s `throw body` in client.ts) — flat, not
    // axios-style `{response: {status, data}}`.
    vi.mocked(usersApi.deactivate).mockRejectedValue({
      error: "LAST_ADMIN",
      message: "Cannot complete this action: it would leave tenant abc123 with no active admin.",
    });
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByTestId("user-management-toggle-active-u1"));
    await waitFor(() =>
      expect(screen.getByTestId("user-management-error")).toHaveTextContent(
        /keinen aktiven Admin mehr/i
      )
    );
    // Names the blocking scope + identifier, not a generic message.
    expect(screen.getByTestId("user-management-error")).toHaveTextContent(/Tenant/);
    expect(screen.getByTestId("user-management-error")).toHaveTextContent(/abc123/);
  });

  it("opens the create-user dialog and calls usersApi.create", async () => {
    vi.mocked(usersApi.create).mockResolvedValue({
      id: "u3",
      username: "carol",
      email: "carol@t.test",
      is_active: true,
      is_tenant_admin: false,
    });
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    const user = userEvent.setup();

    await user.click(screen.getByTestId("user-management-create-btn"));
    expect(await screen.findByTestId("user-management-create-dialog")).toBeInTheDocument();

    await user.type(screen.getByTestId("user-management-create-username"), "carol");
    await user.type(screen.getByTestId("user-management-create-email"), "carol@t.test");
    await user.type(screen.getByTestId("user-management-create-password"), "s3cret-pass");
    await user.click(screen.getByTestId("user-management-create-submit"));

    await waitFor(() =>
      expect(usersApi.create).toHaveBeenCalledWith({
        username: "carol",
        email: "carol@t.test",
        password: "s3cret-pass",
      })
    );
    // Dialog closes and the list reloads after a successful create.
    await waitFor(() =>
      expect(screen.queryByTestId("user-management-create-dialog")).not.toBeInTheDocument()
    );
    expect(usersApi.list).toHaveBeenCalledTimes(2);
  });

  it("revokes tenant-admin for a current admin row", async () => {
    vi.mocked(usersApi.revokeTenantAdmin).mockResolvedValue(undefined);
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByTestId("user-management-toggle-admin-u1"));
    await waitFor(() => expect(usersApi.revokeTenantAdmin).toHaveBeenCalledWith("u1"));
  });

  it("grants tenant-admin for a non-admin row", async () => {
    vi.mocked(usersApi.grantTenantAdmin).mockResolvedValue(undefined);
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("bob")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByTestId("user-management-toggle-admin-u2"));
    await waitFor(() => expect(usersApi.grantTenantAdmin).toHaveBeenCalledWith("u2"));
  });

  it("uses the unified + New User trigger label instead of bare Erstellen", async () => {
    render(<UserManagement />);

    await waitFor(() => {
      expect(screen.getByTestId("user-management-create-btn")).toBeInTheDocument();
    });

    expect(screen.getByTestId("user-management-create-btn")).toHaveTextContent("+ Neuer Nutzer");
    expect(screen.queryByText("Erstellen")).not.toBeInTheDocument();
  });
});
