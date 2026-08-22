import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Ontology Simulation & Trace Link Config', () => {
  let testWorkspaceId: string;
  let authToken: string;

  test.beforeEach(async ({ request, page }) => {
    const token = await getAuthToken();
    authToken = token;

    // 1. Create a dedicated workspace for this ontology test
    const createResp = await request.post(`${BACKEND_URL}/api/v1/workspaces/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: `Ontology Test ${Date.now()}`,
        preset: 'extended',
        terminology_profile: 'se_mode',
        language: 'en'
      }
    });
    expect(createResp.ok()).toBeTruthy();
    const ws = await createResp.json();
    testWorkspaceId = ws.id;

    // 2. Set decomposition_link_type to 'derives-from'.
    // NOTE (see below, main test body): as of UMSETZUNGSPLAN_SYSENG_2.0.md
    // §1.4 (backend/application/requirement_service.py, decompose()),
    // Workspace.decomposition_link_type is documented as "functionally dead"
    // for the decompose/derive path — every derive always creates a
    // 'decomposes' link now, regardless of this setting. The PATCH call is
    // kept here to assert the setting itself still round-trips correctly
    // (workspace config API contract), even though it no longer influences
    // derive/decompose behavior.
    const patchResp = await request.patch(`${BACKEND_URL}/api/v1/workspaces/${testWorkspaceId}/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        decomposition_link_type: 'derives-from'
      }
    });
    expect(patchResp.ok()).toBeTruthy();
    const patchedWs = await patchResp.json();
    expect(patchedWs.decomposition_link_type).toBe('derives-from');

    // 3. Inject this workspace into the session so UI uses it
    await setWorkspaceId(page, testWorkspaceId);
    await loginAsAdmin(page);
  });

  test('simulate L1 to L2 decomposition creates decomposes links', async ({ page, request }) => {
    // ---------------------------------------------------------
    // 1. Create Level 1 Requirement (System Req)
    // ---------------------------------------------------------
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-new-title-input"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="req-new-title-input"]').fill('SYS-REQ-001: Main System Function');
    
    // There might not be a type selector in the quick create form, so we just save
    await page.locator('[data-testid="req-new-save-btn"]').click();
    
    // Now wait for the detail view to load
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue('SYS-REQ-001: Main System Function', { timeout: 8000 });
    
    // Choose SyReq (System Requirement) in the detail view
    // The type is SyReq by default, so we don't need to change it.


    const currentUrl = page.url();
    const l1ReqId = currentUrl.split('/').pop();
    expect(l1ReqId).toBeDefined();

    // ---------------------------------------------------------
    // 2. Create Level 1 Architecture Element (System Arch)
    // ---------------------------------------------------------
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-new-title-input"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="arch-new-title-input"]').fill('SYS-ARCH-001: Core System Component');
    await page.locator('[data-testid="arch-new-save-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('SYS-ARCH-001: Core System Component', { timeout: 8000 });

    const archUrl = page.url();
    const l1ArchId = archUrl.split('/').pop();
    expect(l1ArchId).toBeDefined();

    // ---------------------------------------------------------
    // 3. Link them via allocated-to
    // ---------------------------------------------------------
    // Go back to the Requirement
    await page.goto(`${FRONTEND_URL}/requirements/${l1ReqId}`);

    // ReqTraceLinkPanel always creates the link with the current requirement
    // as source_id. SE-mode ontology semantics (backend/traceability/types.py
    // SE_LINK_SEMANTICS) constrain "satisfies" to ArchitectureElement->Requirement
    // (or Requirement->StakeholderNeed) — never Requirement->ArchitectureElement
    // — so it can't be created from here. "allocated-to" permits
    // Requirement->ArchitectureElement and expresses the same intent (this
    // requirement is allocated to this architecture element).
    await page.locator('[data-testid="req-tracelink-create-btn"]').click();
    await page.locator('[data-testid="req-tracelink-target-select"]').selectOption(l1ArchId!);
    await page.locator('[data-testid="req-tracelink-type-select"]').selectOption('allocated-to');
    await page.locator('[data-testid="req-tracelink-submit-btn"]').click();

    // Verify link appears in the UI.
    // NOTE: ReqTraceLinkPanel groups links by target artifact type into
    // separate sections/testids (req-tracelink-requirements-section [tree],
    // req-tracelink-architecture-section [flat list], req-tracelink-other-section)
    // — the old flat "req-tracelink-item" testid no longer exists at all for
    // Requirement<->ArchitectureElement links; the correct one is
    // "req-tracelink-arch-item" (see ReqTraceLinkPanel.tsx). It also renders
    // the *neutral* Tri-Label form via getLinkTypeLabel()
    // (frontend/src/constants/traceLinkLabels.ts) — for 'allocated-to' that's
    // "Allocation", not "allocated".
    await expect(page.locator('[data-testid="req-tracelink-arch-item"]').filter({ hasText: /allocation/i })).toBeVisible({ timeout: 8000 });

    // ---------------------------------------------------------
    // 4. Derive L2 Requirement (Subsystem Req)
    // ---------------------------------------------------------
    // Use the derive functionality from the L1 requirement. The button and
    // its form fields come from the shared DeriveRequirementForm, mounted
    // here with testIdPrefix="req" (not "req-tracelink").
    await page.locator('[data-testid="req-derive-btn"]').click();

    // The inline form opens for derivation
    await expect(page.locator('[data-testid="req-derive-title-input"]')).toBeVisible({ timeout: 8000 });
    await page.locator('[data-testid="req-derive-title-input"]').fill('SUB-REQ-001: Subsystem Function');

    // Choose the architecture element for the derived requirement
    await page.locator('[data-testid="req-derive-arch-select"]').selectOption(l1ArchId!);

    // Submit the form
    await page.locator('[data-testid="req-derive-submit-btn"]').click();

    // Wait for the new child requirement to load
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue('SUB-REQ-001: Subsystem Function', { timeout: 10000 });

    // Check its traceability to confirm what link type the derive action
    // actually created.
    // NOTE — this assertion's premise changed since the test was written:
    // backend/application/requirement_service.py::decompose() is now
    // hardcoded to always create LinkType.DECOMPOSES links for every
    // workspace (see the "UMSETZUNGSPLAN_SYSENG_2.0.md §1.4" comment there),
    // regardless of Workspace.decomposition_link_type. So deriving a child
    // requirement here creates a 'decomposes' link, not 'derives-from' —
    // the workspace-level setting (patched above) no longer has any effect
    // on this path. This spec now documents/verifies that real, current
    // behavior instead of the old (deprecated) configurable-link-type
    // premise.
    //
    // For Requirement<->Requirement links, ReqTraceLinkPanel renders a
    // lazily-expanded RequirementTreeNode tree (frontend/src/components/
    // RequirementEditors/RequirementTreeNode.tsx) — not a flat
    // "req-tracelink-item" list (that testid doesn't exist for this link
    // type at all). Note also that RequirementTreeNode only recognizes
    // link_type 'derives-from'/'derived-by' when building its tree (see
    // RequirementTreeNode.tsx: `if (!['derives-from', 'derived-by']
    // .includes(link.link_type)) continue;`), so a 'decomposes' link (as
    // created here) is *not* surfaced by that tree UI at all — verify via
    // the API instead, which is the only current way to observe this link.
    const l2ReqId = page.url().split('/').pop();
    const tracelinksResp = await request.get(
      `${BACKEND_URL}/api/v1/tracelinks/?workspace_id=${testWorkspaceId}&artifact_id=${l2ReqId}`,
      { headers: { Authorization: `Bearer ${authToken}` } },
    );
    expect(tracelinksResp.status()).toBe(200);
    const tracelinksBody = await tracelinksResp.json();
    const decomposesLink = tracelinksBody.results.find(
      (l: { link_type: string; target_id: string; source_id: string }) =>
        l.link_type === 'decomposes' && (l.source_id === l2ReqId || l.target_id === l2ReqId),
    );
    expect(decomposesLink, 'expected a decomposes trace link for the derived L2 requirement').toBeDefined();
  });
});
