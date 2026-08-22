// [Multi-user management] Tenant-admin full flow (Task 14): create user,
// assign a workspace role, deactivate, reactivate — through the real UI.
//
// Route: `/user-management` (NavigationShell.tsx registers `UserManagement`
// at that path, NOT `/settings/users`), gated on `useAuth().isTenantAdmin`.
// The seeded demo admin (helpers/auth.ts `loginAsAdmin`/`TEST_USER`)
// qualifies: `provision_admin` (backend/auth_tenancy/provisioning.py)
// creates a `TenantRole(role=admin)` for it via `_ensure_tenant_admin_role`,
// on top of the pre-existing workspace-level `admin` role that already lets
// it reach `/settings` (see csv-import.spec.ts / review-workflow.spec.ts).
//
// IMPORTANT finding, not fixed here (test-only scope): there is no UI button
// anywhere in this repo that calls `workspaceMembersApi.assignRole`
// (frontend/src/api/workspace-members.ts) — grep confirms the only call
// site is the API wrapper's own definition. `PermissionsSection.tsx`
// (WorkspaceSettings, Task 13) renders a "Workspace Members" roster with
// Suspend/Reactivate actions for *existing* roles, but no "assign a new
// role" control. So "assign workspace role" in this flow is done via a
// direct API call (the only way it is reachable at all today), and the
// UI-driven part of that step is verified by asserting the assigned role
// then appears in, and can be suspended/reactivated through, the real
// Workspace Members roster.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

interface ManagedUserDto {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  is_tenant_admin: boolean;
}

test.describe('[Multi-user management] Tenant-admin full flow', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('create user, assign workspace role, deactivate, reactivate', async ({ page, request }) => {
    const token = await getAuthToken();
    const uniqueSuffix = Date.now().toString();
    const username = `e2e-user-${uniqueSuffix}`;
    const email = `${username}@e2e.test`;

    // --- Step 1: create the user through the real UserManagement UI (Task 12) ---
    await page.goto(`${FRONTEND_URL}/user-management`);
    await expect(page.locator('[data-testid="user-management"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="user-management-table"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="user-management-create-btn"]').click();
    const createDialog = page.locator('[data-testid="user-management-create-dialog"]');
    await expect(createDialog).toBeVisible({ timeout: 10000 });

    await createDialog.locator('[data-testid="user-management-create-username"]').fill(username);
    await createDialog.locator('[data-testid="user-management-create-email"]').fill(email);
    await createDialog
      .locator('[data-testid="user-management-create-password"]')
      .fill('a-real-password-123');
    await createDialog.locator('[data-testid="user-management-create-submit"]').click();

    await expect(createDialog).not.toBeVisible({ timeout: 10000 });

    // The new row's data-testid is keyed by the server-assigned user id,
    // which the browser side does not know yet — locate it by its rendered
    // username text first (mirrors the `hasText` row-lookup convention used
    // across this suite, e.g. review-workflow.spec.ts).
    const rowByText = page.locator('[data-testid^="user-management-row-"]', { hasText: username });
    await expect(rowByText).toBeVisible({ timeout: 10000 });

    // Resolve the created user's id via the same tenant-admin-guarded list
    // endpoint the table above just rendered from, so later steps can
    // address it by a stable data-testid instead of free text.
    const listResp = await request.get(`${BACKEND_URL}/api/v1/users/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listResp.ok()).toBeTruthy();
    const users: ManagedUserDto[] = await listResp.json();
    const created = users.find((u) => u.username === username);
    expect(created, `created user '${username}' not found in GET /api/v1/users/`).toBeTruthy();
    const userId = (created as ManagedUserDto).id;
    expect(created?.is_active).toBe(true);
    expect(created?.is_tenant_admin).toBe(false);

    const row = page.locator(`[data-testid="user-management-row-${userId}"]`);
    await expect(row).toBeVisible({ timeout: 10000 });
    await expect(row.getByText(/^active$|^aktiv$/i)).toBeVisible();

    // --- Step 2: assign a workspace role. No UI path exists for this (see
    // file header) — done via the real REST endpoint the dead
    // `workspaceMembersApi.assignRole` wrapper targets, then verified
    // through the real Workspace Members roster UI below. ---
    const assignResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/members/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { user_id: userId, role: 'editor' },
      }
    );
    expect(assignResp.ok()).toBeTruthy();

    // C-3 fix round 3: WorkspaceSettings defaults to the "general" tab;
    // the workspace-member-* testids only render under "workflows-permissions"
    // (PermissionsSection). Deep-link via ?tab= (see #609 / isSettingsTabId
    // in WorkspaceSettings.tsx) instead of landing on the wrong tab.
    await page.goto(`${FRONTEND_URL}/settings?tab=workflows-permissions`);
    const memberRow = page.locator(`[data-testid="workspace-member-row-${userId}"]`);
    await expect(memberRow).toBeVisible({ timeout: 10000 });
    const roleChip = page.locator(`[data-testid="workspace-member-role-${userId}-editor"]`);
    await expect(roleChip).toBeVisible({ timeout: 10000 });
    await expect(roleChip).toContainText('editor');

    // Exercise the one workspace-role lifecycle action that IS wired to a
    // real button: suspend, then reactivate.
    const suspendBtn = page.locator(`[data-testid="workspace-member-suspend-${userId}-editor"]`);
    const reactivateBtn = page.locator(`[data-testid="workspace-member-reactivate-${userId}-editor"]`);

    await suspendBtn.click();
    await expect(reactivateBtn).toBeVisible({ timeout: 10000 });

    await reactivateBtn.click();
    await expect(suspendBtn).toBeVisible({ timeout: 10000 });

    // --- Step 3: deactivate / reactivate the tenant user through the real
    // UserManagement UI (Task 12) ---
    await page.goto(`${FRONTEND_URL}/user-management`);
    await expect(row).toBeVisible({ timeout: 10000 });
    await expect(row.getByText(/^active$|^aktiv$/i)).toBeVisible();

    const toggleActiveBtn = page.locator(`[data-testid="user-management-toggle-active-${userId}"]`);

    await toggleActiveBtn.click();
    await expect(row.getByText(/^inactive$|^inaktiv$/i)).toBeVisible({ timeout: 10000 });

    await toggleActiveBtn.click();
    await expect(row.getByText(/^active$|^aktiv$/i)).toBeVisible({ timeout: 10000 });

    // No cleanup possible: this REST surface (Tasks 7-9) exposes
    // create/activate/deactivate/tenant-admin only — there is no
    // DELETE /api/v1/users/{id}/. The created user is intentionally left
    // active (this flow's own final state) and is identifiable by its
    // `e2e-user-` username prefix for any future manual cleanup.
  });
});
