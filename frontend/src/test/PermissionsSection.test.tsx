/**
 * ARCH-L1-001 ReactFrontend — PermissionsSection user-picker tests.
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings scope)
 * req_id:  REQ-014 (Item-Permission user picker replaces UUID free-text),
 *          multi-user management design spec Task 13 (workspace members
 *          suspend/reactivate UI)
 *
 * Tests:
 * 1. The subject picker is a dropdown populated from the workspace member
 *    directory (display name + email), not a free-text UUID input.
 * 2. Granting a rule uses the selected member's user_id automatically.
 * 3. The workspace-members table (Task 13) renders a Suspend action per
 *    member role, calls `workspaceMembersApi.suspendRole` and reloads the
 *    roster; the just-suspended role then shows a Reactivate action (the
 *    live `GET /members/` roster is active-roles-only, so a suspended role
 *    — or an entirely suspended member — would otherwise vanish before it
 *    could be reactivated from this UI).
 * 4. A `LAST_ADMIN` 409 (flat `{error, message}` body — see
 *    `UserManagement.tsx`'s doc comment for the real `apiClient` error
 *    shape) surfaces as a specific inline error, not a generic failure.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

vi.mock("../api/workspace-members", () => ({
  workspaceMembersApi: { list: vi.fn(), suspendRole: vi.fn(), reactivateRole: vi.fn() },
}));
vi.mock("../api/item-permissions", () => ({
  itemPermissionsApi: { list: vi.fn(), grant: vi.fn(), revoke: vi.fn() },
}));
vi.mock("../api/artifacts", () => ({
  artifactsApi: { list: vi.fn() },
}));

import { PermissionsSection } from "../components/WorkspaceSettings/PermissionsSection";
import { workspaceMembersApi } from "../api/workspace-members";
import { itemPermissionsApi } from "../api/item-permissions";
import { artifactsApi } from "../api/artifacts";

const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  lng: "en",
  resources: { en: { translation: {} } },
});

const BOB_ID = "11111111-1111-1111-1111-111111111111";
const CAROL_ID = "22222222-2222-2222-2222-222222222222";

const MEMBERS = [
  {
    user_id: BOB_ID,
    username: "bob",
    email: "bob@a.test",
    display_name: "Bob Builder",
    roles: ["editor"],
  },
  {
    user_id: CAROL_ID,
    username: "carol",
    email: "carol@a.test",
    display_name: "Carol",
    roles: ["viewer"],
  },
];

function renderSection(): ReturnType<typeof render> {
  return render(
    <I18nextProvider i18n={i18n}>
      <PermissionsSection workspaceId="ws-1" />
    </I18nextProvider>
  );
}

describe("PermissionsSection user picker (REQ-014)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (artifactsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
    });
    (workspaceMembersApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(
      MEMBERS
    );
    (itemPermissionsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (itemPermissionsApi.grant as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (workspaceMembersApi.suspendRole as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    (workspaceMembersApi.reactivateRole as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  });

  it("populates the picker with workspace members from the directory", async () => {
    renderSection();

    await waitFor(() => {
      expect(workspaceMembersApi.list).toHaveBeenCalledWith("ws-1");
    });

    const select = await screen.findByTestId("permission-user-input");
    // The subject picker is a dropdown, not a free-text UUID field.
    expect(select.tagName).toBe("SELECT");
    // Options show name and email so members are searchable by both.
    expect(select).toHaveTextContent("Bob Builder");
    expect(select).toHaveTextContent("bob@a.test");
    expect(select).toHaveTextContent("Carol");
  });

  it("grants a permission using the selected member's user_id", async () => {
    renderSection();
    const user = userEvent.setup();

    const select = await screen.findByTestId("permission-user-input");
    await waitFor(() => expect(select).toHaveTextContent("Bob Builder"));

    await user.selectOptions(select, BOB_ID);
    await user.click(screen.getByTestId("permission-grant-btn"));

    await waitFor(() => {
      expect(itemPermissionsApi.grant).toHaveBeenCalledWith("ws-1", {
        user_id: BOB_ID,
        artifact_id: null,
        permission_level: "read",
      });
    });
  });

  it("loads a member's rules when selected in the filter picker", async () => {
    renderSection();
    const user = userEvent.setup();

    const filter = await screen.findByTestId("permission-filter-input");
    await waitFor(() =>
      expect(filter).toHaveTextContent("Carol")
    );

    await user.selectOptions(filter, CAROL_ID);

    await waitFor(() => {
      expect(itemPermissionsApi.list).toHaveBeenCalledWith("ws-1", CAROL_ID);
    });
  });
});

describe("PermissionsSection workspace members suspend/reactivate (Task 13)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (artifactsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
    });
    (itemPermissionsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (itemPermissionsApi.grant as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (workspaceMembersApi.suspendRole as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    (workspaceMembersApi.reactivateRole as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  });

  it("renders a Suspend action per member role and calls suspendRole, then reloads the roster", async () => {
    (workspaceMembersApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(MEMBERS);
    renderSection();
    const user = userEvent.setup();

    const suspendBtn = await screen.findByTestId(`workspace-member-suspend-${BOB_ID}-editor`);
    await user.click(suspendBtn);

    await waitFor(() => {
      expect(workspaceMembersApi.suspendRole).toHaveBeenCalledWith("ws-1", BOB_ID, "editor");
    });
    // Reloads the member list after a successful suspend (initial load + reload).
    await waitFor(() => {
      expect(workspaceMembersApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it("shows a Reactivate action for a just-suspended role and calls reactivateRole", async () => {
    // Bob holds only the "editor" role, so once it is suspended he drops out
    // of the active-only roster entirely on the next fetch — the row must
    // still render (via the session-local suspended-role memory) with a
    // Reactivate action.
    (workspaceMembersApi.list as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(MEMBERS)
      .mockResolvedValueOnce([MEMBERS[1]]);
    renderSection();
    const user = userEvent.setup();

    const suspendBtn = await screen.findByTestId(`workspace-member-suspend-${BOB_ID}-editor`);
    await user.click(suspendBtn);

    const reactivateBtn = await screen.findByTestId(
      `workspace-member-reactivate-${BOB_ID}-editor`
    );
    await user.click(reactivateBtn);

    await waitFor(() => {
      expect(workspaceMembersApi.reactivateRole).toHaveBeenCalledWith("ws-1", BOB_ID, "editor");
    });
    // Initial load + reload-after-suspend + reload-after-reactivate.
    await waitFor(() => {
      expect(workspaceMembersApi.list).toHaveBeenCalledTimes(3);
    });
  });

  it("surfaces a LAST_ADMIN error inline, naming the blocking scope", async () => {
    (workspaceMembersApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(MEMBERS);
    // Real production shape thrown by `apiClient` for a non-2xx JSON error
    // body (see `apiFetch`'s `throw body` in client.ts) — flat, not
    // axios-style `{response: {status, data}}`.
    (workspaceMembersApi.suspendRole as ReturnType<typeof vi.fn>).mockRejectedValue({
      error: "LAST_ADMIN",
      message: "Cannot complete this action: it would leave workspace ws-1 with no active admin.",
    });
    renderSection();
    const user = userEvent.setup();

    const suspendBtn = await screen.findByTestId(`workspace-member-suspend-${BOB_ID}-editor`);
    await user.click(suspendBtn);

    await waitFor(() => {
      expect(screen.getByTestId("workspace-members-error")).toHaveTextContent(
        /no active admin/i
      );
    });
    expect(screen.getByTestId("workspace-members-error")).toHaveTextContent(/Workspace/);
    expect(screen.getByTestId("workspace-members-error")).toHaveTextContent(/ws-1/);
  });
});
