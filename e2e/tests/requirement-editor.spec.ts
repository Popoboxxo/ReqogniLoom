// REQ-L2-RF-003, REQ-L3-RF003-001/002/003: Requirements editor (inline, workflow, traceability)
// REQ-L2-RF-006: TraceLink creation in RequirementEditor
import { test, expect, type Page } from '@playwright/test';
import {
  getAuthToken,
  loginAsAdmin,
  setWorkspaceId,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';
import { collapseInspector } from '../helpers/inspector';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

// localStorage first-render cache of the readable-id preference (#1096).
const READABLE_IDS_STORAGE_KEY = 'reqflow-display-readable-ids';

// ADR-030 / Task 9: the ONLY persisted tree-width key (module-scoped, v2).
const TREE_WIDTH_KEY = 'reqflow.splitview.treeWidth.v2.requirements';

// "+ New" only opens an inline quick-create form (title input + Save/Cancel);
// the full editor (artifact-field-title etc.) only renders after Save navigates to the
// created requirement's detail route.
async function createRequirementViaQuickForm(page: Page, title = 'E2E Requirement'): Promise<void> {
  await page.locator('[data-testid="create-req-btn"]').click();
  await page.locator('[data-testid="req-new-title-input"]').fill(title);
  await page.locator('[data-testid="req-new-save-btn"]').click();
  await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({ timeout: 10000 });
  // #1762 (M1): the artifact inspector mounts as a sheet at the 1280 px E2E
  // viewport and marks the detail area it covers `inert` (spec §4.2). Every
  // editor interaction below happens in that area; without this the clicks are
  // intercepted and `fill()` silently keeps the old value.
  await collapseInspector(page);
}

test.describe('[COMP-RF-003] RequirementEditors', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF003-001] title is editable inline and markdown preview toggle works', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // Create a fresh requirement so the detail editor is shown
    await createRequirementViaQuickForm(page);

    // Inline edit title
    const title = page.locator('[data-testid="artifact-field-title"]');
    await title.fill('Inline Edit Title REQ-L3-RF003-001');
    await expect(title).toHaveValue('Inline Edit Title REQ-L3-RF003-001');

    // Markdown preview toggle is part of the description editor
    const previewBtn = page.locator('[data-testid="md-preview-btn"]').first();
    const editBtn = page.locator('[data-testid="md-edit-btn"]').first();
    await expect(previewBtn).toBeVisible();
    await expect(editBtn).toBeVisible();

    // Toggling to preview hides the textarea (which is sibling)
    await previewBtn.click();
    // After clicking preview, no description textarea should be visible
    // (the editor swaps textarea with the rendered markdown div)
    await editBtn.click();
    // Switching back to edit mode should reveal a textarea again.
    //
    // Issue #947: scoped to the description widget's own editor instead of
    // `page.locator('textarea').first()`. The form renders several textareas
    // (rationale, custom fields), so "the first one on the page" is not the
    // description field this test is about.
    await expect(
      page.locator('[data-testid="artifact-widget-description_editor"] textarea')
    ).toBeVisible({ timeout: 4000 });
  });

  // #1287 (Plan C T-C2-8): the optional markdown formatting toolbar. Default
  // preference is `auto`, so it appears once the description has three lines.
  // The toggle persists the USER level; the guard below re-enables it when a
  // previous run left it `off`, so the case is idempotent.
  test('[#1287] markdown formatting toolbar appears for multi-line descriptions', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page, 'Toolbar E2E Requirement');

    const editor = page.locator(
      '[data-testid="artifact-widget-description_editor"] textarea'
    );
    await editor.fill('line one\nline two\nline three');

    const toolbar = page.locator('[data-testid="md-toolbar"]');
    if (!(await toolbar.isVisible())) {
      await page.locator('[data-testid="md-toolbar-toggle"]').click();
    }
    await expect(toolbar).toBeVisible();

    // Empty selection at the end of the value → the markers are inserted there.
    await page.locator('[data-testid="md-toolbar-bold"]').click();
    await expect(editor).toHaveValue(/line three\*\*/);

    // The toggle hides the toolbar and persists the user-level preference.
    await page.locator('[data-testid="md-toolbar-toggle"]').click();
    await expect(toolbar).toBeHidden();
  });

  test('[REQ-L3-RF003-002] workflow-state dropdown is visible and selectable', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // REQ-161: the current state is shown read-only via WorkflowStatusEditor's
    // status badge; a "Change status" trigger + menu only renders when the
    // backend reports allowed transitions from the current state — otherwise
    // a "workflow-no-transitions" hint is shown instead. Fixed literal states
    // ('draft'/'review'/'approved') are no longer guaranteed as option text.
    await expect(page.locator('[data-testid="workflow-current-status"]')).toBeVisible({ timeout: 10000 });

    const trigger = page.locator('[data-testid="workflow-transition-trigger"]');
    const noTransitions = page.locator('[data-testid="workflow-no-transitions"]');
    await expect(trigger.or(noTransitions)).toBeVisible({ timeout: 6000 });

    if (await trigger.count()) {
      await trigger.click();
      const menu = page.locator('[data-testid="workflow-transition-menu"]');
      await expect(menu).toBeVisible();

      const option = menu.locator('[data-testid^="workflow-transition-option-"]').first();
      const targetState = await option.getAttribute('data-testid');
      if (targetState) {
        await option.click();
        await expect(page.locator('[data-testid="workflow-current-status"]')).toBeVisible();
      }
    }
  });

  test('[REQ-L3-RF003-003] traceability panel is visible in requirement editor', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // The old standalone TraceabilityPanel (upstream/downstream sections) is
    // dead code — linked-requirement traceability now lives in
    // ReqTraceLinkPanel, rendered as part of the detail editor.
    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });
    // req-tracelink-list only renders once links exist; a freshly-created
    // requirement has none, so the panel shows a "no links" message instead.
    await expect(panel).not.toBeEmpty({ timeout: 4000 });
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — TraceLink create panel visible in requirement editor
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-006] requirement editor shows tracelink panel with create button', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // ReqTraceLinkPanel must be rendered
    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });

    // Create button must be present
    const createBtn = page.locator('[data-testid="req-tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L2-RF-006] tracelink create form shows target and type selectors', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // Issue #926: the create button opens the unified CreateTraceLinkDialog
    // (REQ-005), same modal as every other artifact type — target picker with
    // search instead of the legacy inline <select> form.
    await page.locator('[data-testid="req-tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="create-trace-link-target-list"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="create-trace-link-target-search"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="create-trace-link-type-select"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="create-trace-link-submit"]')).toBeVisible({ timeout: 4000 });

    // The unified dialog offers only link types the backend allows for the
    // chosen endpoints (spec §4.1). The panel fixes the source to this
    // Requirement (`sourceId`) and no target is chosen yet, so the valid set
    // is the Requirement-sourced catalog pair table
    // (backend/link_types/builtin.py):
    //   derives-from  (Requirement -> Requirement/StakeholderNeed)
    //   decomposes    (Requirement -> Requirement)
    //   allocated-to  (Requirement -> ArchitectureElement)
    //   refines       (Requirement -> Requirement)
    //   satisfies     (Requirement -> Goal)
    //   realizes      (Requirement -> Goal)
    //   references    (any -> any)
    // `verifies` (TestCase -> ...), `decides` (Adr -> ...) and `mitigates`
    // (Risk -> ...) are sourced from *other* artifact types, so they must not
    // be offered from a Requirement. `diagram-ref` (Diagram -> ...) is absent
    // for the same reason — the legacy inline form's "all types regardless"
    // was what let a user pick a type the server would then reject.
    // Options keep the raw catalog key as `data-value` — assert against those.
    //
    // #318: the control is a non-native listbox. Its <ul role="listbox"> and
    // <li role="option"> rows stay attached in the DOM while collapsed (only
    // `hidden`), but BOTH the workspace link-type catalog AND the source
    // element's artifact type load asynchronously. Until the source type
    // resolves, the dialog queries the pair filter with a "*" wildcard and
    // transiently offers a superset (including `verifies`/`decides`/
    // `mitigates`). `evaluateAll` does NOT auto-retry, so wait for the resolved
    // set before reading it: `refines` is present in both the transient and the
    // resolved set, so it proves the catalog arrived; `verifies` is only valid
    // with a TestCase source, so its disappearance proves the Requirement
    // source type has resolved. Only then open the popup and read the values.
    const typeTrigger = page.locator('[data-testid="create-trace-link-type-select"]');
    await expect(
      page.locator('[data-testid="create-trace-link-type-option-refines"]')
    ).toBeAttached();
    await expect(
      page.locator('[data-testid="create-trace-link-type-option-verifies"]')
    ).toHaveCount(0);
    await typeTrigger.click();
    await expect(page.locator('[data-testid="create-trace-link-type-listbox"]')).toBeVisible();
    const typeValues = await page.locator('[data-testid^="create-trace-link-type-option-"]').evaluateAll(
      (opts) => opts.map((o) => o.getAttribute('data-value'))
    );
    const realTypes = typeValues.filter((o) => o && o.trim());
    expect(realTypes).toEqual(
      expect.arrayContaining([
        'derives-from',
        'decomposes',
        'allocated-to',
        'refines',
        'satisfies',
        'realizes',
        'references',
      ])
    );
    expect(realTypes).not.toContain('diagram-ref');
    // Types sourced from other artifact types must not leak in from a
    // Requirement source (guards against the transient wildcard superset).
    expect(realTypes).not.toContain('verifies');
    expect(realTypes).not.toContain('decides');
    expect(realTypes).not.toContain('mitigates');
  });

  test('[#928] requirement editor exposes the system-element allocation entry', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // Systemelement-Zuordnung (Requirement -> ArchitectureElement via
    // allocated-to) is a visible, one-click block — not a scroll inside a
    // native select behind the generic "new trace link" button.
    const section = page.locator('[data-testid="req-allocation-section"]');
    await expect(section).toBeVisible({ timeout: 8000 });
    await expect(page.locator('[data-testid="req-allocation-empty"]')).toBeVisible({ timeout: 4000 });

    await page.locator('[data-testid="req-allocation-assign-btn"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 6000 });
    // Architecture-only and allocated-to preselected.
    // #318: the link type lives on the trigger's `data-value`, not on a
    // native <select> value.
    await expect(page.locator('[data-testid="create-trace-link-type-select"]')).toHaveAttribute('data-value', 'allocated-to');
    await expect(page.locator('[data-testid="create-trace-link-target-type-architecture"]')).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // REQ-L1-040 / ADR-030 — one SplitView, per-module user-adjustable tree width.
  // Schnitt 2c removed the spine slot (the chain lives in the sibling footer);
  // Schnitt 3b made the divider authoritative and persisted it under a v2 key.
  // -------------------------------------------------------------------------
  test('[REQ-L1-040] requirements route renders list, trace footer and detail — no stale spine', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    const list = page.getByTestId('splitview-list');
    const footer = page.getByTestId('trace-footer');
    const detail = page.getByTestId('splitview-detail');

    await expect(list).toBeVisible();
    await expect(footer).toBeVisible();
    await expect(detail).toBeVisible();
    await expect(detail.locator('[data-testid="artifact-field-title"]')).toBeVisible();

    // Task 6: the old spine slot is gone; the footer is a SIBLING of SplitView.
    await expect(page.getByTestId('splitview-spine')).toHaveCount(0);
    await expect(page.getByTestId('splitview-divider')).toHaveCount(0);
    const footerHasListSibling = await footer.evaluate(
      (el) => !!el.parentElement?.querySelector('[data-testid="splitview-list"]'),
    );
    expect(footerHasListSibling).toBe(true);

    // The list keeps its own scroll surface (UI_KONZEPT ch. 7.1).
    await expect
      .poll(async () => list.evaluate((el) => window.getComputedStyle(el).overscrollBehaviorY))
      .toBe('contain');

    // ADR-030 upper clamp: End sets effMax (70% of the measured content width).
    const separator = page.getByTestId('tree-width-separator');
    await expect(separator).toBeVisible();
    await separator.focus();
    await page.keyboard.press('End');
    const max = Number(await separator.getAttribute('aria-valuemax'));
    await expect(separator).toHaveAttribute('aria-valuenow', String(max));
    // The footer stays sibling + usable at maximum tree width.
    await expect(footer).toBeVisible();
    const stations = page.getByTestId('trace-footer-station');
    if (await stations.count()) {
      await expect(stations.first()).toBeEnabled();
    }
  });

  test('[ADR-030] drag and keyboard resize persist across reload under the v2 key', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);
    const separator = page.getByTestId('tree-width-separator');
    await expect(separator).toBeVisible();

    // Reset first: Enter deletes the key and restores the module default (424).
    await separator.focus();
    await page.keyboard.press('Enter');
    await expect(separator).toHaveAttribute('aria-valuenow', '424');
    expect(await page.evaluate((key) => localStorage.getItem(key), TREE_WIDTH_KEY)).toBeNull();

    // Keyboard resize writes the SAME module key.
    await page.keyboard.press('ArrowRight');
    await expect(separator).toHaveAttribute('aria-valuenow', '440');
    expect(await page.evaluate((key) => localStorage.getItem(key), TREE_WIDTH_KEY)).toBe('440');

    // Pointer drag produces a new clamped width and persists it.
    const box = (await separator.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();
    await expect
      .poll(async () => page.evaluate((key) => localStorage.getItem(key), TREE_WIDTH_KEY))
      .not.toBe('440');
    const dragged = await separator.getAttribute('aria-valuenow');
    expect(dragged).not.toBe('440');
    expect(await page.evaluate((key) => localStorage.getItem(key), TREE_WIDTH_KEY)).toBe(dragged);

    // Reload → identical width (persistence, not an in-memory accident).
    await page.reload();
    await expect(page.getByTestId('splitview-detail')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('tree-width-separator')).toHaveAttribute('aria-valuenow', dragged!);
  });

  test('[ADR-030] module widths are independent — ADR never moves Requirements', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('reqflow.splitview.treeWidth.v2.requirements', '520');
    });
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page, 'Module independence REQ');
    await expect(page.getByTestId('tree-width-separator')).toHaveAttribute('aria-valuenow', '520');

    // No ADR key was written by the Requirements editor.
    expect(
      await page.evaluate(() => localStorage.getItem('reqflow.splitview.treeWidth.v2.adr')),
    ).toBeNull();

    // The ADR route reads its OWN default (350) — the two modules never share.
    await page.goto(`${FRONTEND_URL}/adrs`);
    await page.getByText('Verwendung von BLE 5.2 statt 5.0').first().click();
    await expect(page.getByTestId('tree-width-separator')).toHaveAttribute('aria-valuenow', '350');
    expect(
      await page.evaluate((key) => localStorage.getItem(key), TREE_WIDTH_KEY),
    ).toBe('520');
  });

  test('[ADR-030] mobile divider is inert and the tree width is not applied to stacked panes', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);
    await expect(page.getByTestId('tree-width-separator')).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    // zone === 'mobile' → no tab stop, no aria-valuenow, no separator at all.
    await expect(page.getByTestId('tree-width-separator')).toHaveCount(0);
    const flexBasis = await page
      .getByTestId('splitview-list')
      .evaluate((el) => window.getComputedStyle(el).flexBasis);
    expect(flexBasis).toBe('100%');
    await expect(page.getByTestId('trace-footer')).toBeVisible();

    // Restore the desktop viewport for the next test in this shard.
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  // -------------------------------------------------------------------------
  // #1094 (T-C2-7) — the server-backed readable-id preference is hydrated at
  // app start. Before T-C2-7 only the /profile section read the server value,
  // so a new device kept showing readable ids until that page was visited.
  // -------------------------------------------------------------------------
  test('[#1094] readable ids follow the server value on a fresh device', async ({ page, request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    const title = `E2E readable-ids ${Date.now()}`;

    // Server truth: readable ids hidden for this account. It must win over the
    // (empty) local cache without anyone opening /profile.
    const prefResp = await request.patch(
      `${BACKEND_URL}/api/v1/users/me/preference-values/`,
      { headers, data: { values: { 'ui.ids.show_readable': false } } }
    );
    expect(prefResp.ok()).toBeTruthy();

    // A row of our own, so the assertion never depends on whatever the seeded
    // database happens to contain.
    const createdResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title,
        description: 'Created by the #1094 hydration E2E test',
        category: 'Functional',
      },
    });
    expect(createdResp.ok()).toBeTruthy();
    const created = await createdResp.json();

    // A fresh device: no cached value before the app boots. addInitScript runs
    // in the new document ahead of the SPA, so the first paint starts from the
    // default and only the hydrator can hide the ids.
    await page.addInitScript((key) => {
      try {
        window.localStorage.removeItem(key);
      } catch {
        /* storage unavailable — the default already applies */
      }
    }, READABLE_IDS_STORAGE_KEY);

    try {
      await page.goto(`${FRONTEND_URL}/requirements`);

      // Filter to our row: the requirement list is virtualized, so the created
      // (and therefore last) row is not rendered without narrowing the list.
      await page.locator('[data-testid="req-list-search-input"]').fill(title);
      const row = page.locator(`[data-testid="req-row-${created.id}"]`);
      await expect(row).toBeVisible({ timeout: 10000 });

      const chip = row.locator(`[data-testid="req-row-${created.id}-id"]`);
      await expect(chip.locator(`[data-testid="req-row-${created.id}-id-copy"]`)).toBeVisible();

      // Hydration is asynchronous (query + effect), so this retries until the
      // server value has been written into the shared store: the readable value
      // span must be gone, while copying the system id stays available.
      await expect(
        chip.locator(`[data-testid="req-row-${created.id}-id-value"]`)
      ).toHaveCount(0, { timeout: 10000 });
    } finally {
      // The admin account is shared by every spec — leave it as we found it.
      await request.patch(`${BACKEND_URL}/api/v1/users/me/preference-values/`, {
        headers,
        data: { values: { 'ui.ids.show_readable': true } },
      });
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
        headers,
      });
    }
  });
});
