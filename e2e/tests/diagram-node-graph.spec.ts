// GH-353 Task 8 — DiagramGraphEditor (payload_format=node_graph) E2E User Journey Tests
//
// WRITTEN BUT NOT EXECUTED by the implementer (Task 8 brief, Global
// Constraints) — hand off to a human/CI runner with a live dev stack.
//
// Validates the node/edge diagram editor end-to-end:
// - Editor loads with toolbar and canvas
// - Edit mode: add node, rename inline, edit node/edge properties via the
//   inspector (including the artifact-ref picker)
// - Save persists the payload; positions round-trip through the SAVED
//   PAYLOAD (not localStorage/dagre-on-load) — reloading shows the same
//   hand-set positions rather than a re-flowed layout (the Task 8 brief's
//   single most important design decision)
// - Auto layout is an explicit toolbar action, never applied automatically
// - Code/Visual toggle shows the live in-editor payload and preserves edits
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Matches backend/diagram/node_graph.py's v1 schema exactly. */
function nodeGraphPayload(overrides?: { nodes?: unknown[]; edges?: unknown[] }) {
  return {
    schema_version: 1,
    nodes: overrides?.nodes ?? [],
    edges: overrides?.edges ?? [],
  };
}

test.describe('[GH-353 Task 8] DiagramGraphEditor (node_graph)', () => {
  let emptyDiagramId: string;
  let seededDiagramId: string;

  test.beforeAll(async ({ request }) => {
    const token = await getAuthToken();

    const emptyResp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Node Graph — Empty',
        diagram_type: 'block',
        payload_format: 'node_graph',
        content: JSON.stringify(nodeGraphPayload()),
        description: 'Created by E2E diagram-node-graph test suite',
      },
    });
    if (!emptyResp.ok()) {
      throw new Error(`Failed to create empty node_graph diagram: ${emptyResp.status()} ${await emptyResp.text()}`);
    }
    emptyDiagramId = (await emptyResp.json()).id;

    // A second diagram pre-seeded with two nodes at known, deliberately
    // "hand-arranged" (non-dagre) positions, to verify the position
    // round-trip / no-auto-layout-on-load behavior.
    const seededResp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Node Graph — Seeded',
        diagram_type: 'block',
        payload_format: 'node_graph',
        content: JSON.stringify(
          nodeGraphPayload({
            nodes: [
              { id: 'n1', type: 'box', label: 'Alpha', position: { x: 40, y: 260 } },
              { id: 'n2', type: 'rounded', label: 'Beta', position: { x: 520, y: 40 } },
            ],
            edges: [{ id: 'e1', source: 'n1', target: 'n2', type: 'flow' }],
          }),
        ),
        description: 'Created by E2E diagram-node-graph test suite',
      },
    });
    if (!seededResp.ok()) {
      throw new Error(`Failed to create seeded node_graph diagram: ${seededResp.status()} ${await seededResp.text()}`);
    }
    seededDiagramId = (await seededResp.json()).id;
  });

  test.afterAll(async ({ request }) => {
    const token = await getAuthToken();
    for (const id of [emptyDiagramId, seededDiagramId]) {
      if (!id) continue;
      await request
        .delete(`${BACKEND_URL}/api/v1/diagrams/${id}/`, { headers: { Authorization: `Bearer ${token}` } })
        .catch(() => {});
    }
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  // -------------------------------------------------------------------------
  // Test 1 — Editor loads with canvas and toolbar (smoke)
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_editor_loads_with_canvas_and_toolbar @smoke', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${emptyDiagramId}/graph`);

    await expect(page.locator('[data-testid="graph-editor-page"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="graph-editor-header"]')).toBeVisible();
    await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible({ timeout: 10000 });

    // Read-only by default — edit affordances (add node) are hidden.
    await expect(page.locator('[data-testid="graph-edit-toggle"]')).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('[data-testid="graph-toolbar-add-node"]')).toHaveCount(0);

    // Empty-state hint shows for the freshly-created diagram.
    await expect(page.getByText('No nodes yet')).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 2 — Enabling edit mode reveals the Add Node toolbar action; adding a
  // node selects it and shows it in the inspector
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_edit_mode_add_node_and_rename', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${emptyDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="graph-edit-toggle"]').click();
    await expect(page.locator('[data-testid="graph-edit-toggle"]')).toHaveAttribute('aria-checked', 'true');

    await expect(page.locator('[data-testid="graph-toolbar-add-node"]')).toBeVisible();
    await page.locator('[data-testid="graph-toolbar-add-node"]').click();

    // A new node renders and the inspector shows it selected.
    await expect(page.locator('[data-testid="graph-inspector-node"]')).toBeVisible({ timeout: 5000 });
    const labelInput = page.locator('[data-testid="graph-inspector-node-label"]');
    await expect(labelInput).toBeVisible();

    // Rename via the inspector label field.
    await labelInput.fill('Renamed Node');
    await expect(labelInput).toHaveValue('Renamed Node');
    await expect(page.getByText('Renamed Node')).toBeVisible({ timeout: 3000 });
  });

  // -------------------------------------------------------------------------
  // Test 3 — Artifact-ref picker: linking and clearing a node's artifact_ref
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_artifact_ref_picker_link_and_clear', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${seededDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="graph-edit-toggle"]').click();
    await page.locator('[data-testid="graph-node-n1"]').click();
    await expect(page.locator('[data-testid="graph-inspector-node"]')).toBeVisible();

    await page.locator('[data-testid="graph-inspector-artifact-entity-type"]').selectOption('Requirement');
    await page.locator('[data-testid="graph-inspector-artifact-id"]').fill('3fa85f64-5717-4562-b3fc-2c963f66afa6');
    await expect(page.locator('[data-testid="graph-inspector-artifact-clear"]')).toBeVisible();

    // The linked-artifact indicator renders on the node itself.
    await expect(page.locator('[data-testid="graph-node-n1"]')).toBeVisible();

    await page.locator('[data-testid="graph-inspector-artifact-clear"]').click();
    await expect(page.locator('[data-testid="graph-inspector-artifact-clear"]')).toHaveCount(0);
  });

  // -------------------------------------------------------------------------
  // Test 4 — Positions load from the SAVED PAYLOAD (no auto-layout-on-load):
  // the seeded, hand-set positions render as-is, not dagre-recomputed
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_loads_saved_positions_without_auto_layout', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${seededDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-node-n1"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="graph-node-n2"]')).toBeVisible();

    // n1 was seeded at (40, 260) and n2 at (520, 40) — a TB dagre auto-layout
    // of a single edge n1->n2 would place n1 ABOVE n2 (n1 is the source, TB
    // ranks it in the top row) and roughly x-aligned; the seeded, deliberately
    // "wrong-looking" arrangement (n1 lower-left, n2 upper-right) must survive
    // untouched on load.
    const n1Box = await page.locator('[data-testid="graph-node-n1"]').boundingBox();
    const n2Box = await page.locator('[data-testid="graph-node-n2"]').boundingBox();
    expect(n1Box).not.toBeNull();
    expect(n2Box).not.toBeNull();
    // n1 renders below n2 on screen (seeded y=260 vs y=40), the opposite of
    // what a fresh TB dagre layout would produce for an n1->n2 edge.
    expect(n1Box!.y).toBeGreaterThan(n2Box!.y);
  });

  // -------------------------------------------------------------------------
  // Test 5 — Auto layout is an EXPLICIT action: node positions only change
  // after clicking the toolbar button, never on load
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_auto_layout_is_explicit_toolbar_action', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${seededDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-node-n1"]')).toBeVisible({ timeout: 10000 });

    const beforeBox = await page.locator('[data-testid="graph-node-n1"]').boundingBox();

    await page.locator('[data-testid="graph-edit-toggle"]').click();
    await expect(page.locator('[data-testid="graph-toolbar-auto-layout"]')).toBeVisible();
    await page.locator('[data-testid="graph-toolbar-auto-layout"]').click();

    // After the explicit auto-layout click, n1's position has moved (dagre
    // ranks it into the standard TB arrangement instead of the seeded one).
    await expect(async () => {
      const afterBox = await page.locator('[data-testid="graph-node-n1"]').boundingBox();
      expect(afterBox).not.toBeNull();
      expect(beforeBox).not.toBeNull();
      expect(
        Math.abs(afterBox!.x - beforeBox!.x) > 5 || Math.abs(afterBox!.y - beforeBox!.y) > 5,
      ).toBe(true);
    }).toPass({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 6 — Save sends a PATCH with payload_format=node_graph, and the saved
  // positions survive a full page reload (the SAVED PAYLOAD round-trip)
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_save_persists_and_positions_survive_reload', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${emptyDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="graph-edit-toggle"]').click();
    await page.locator('[data-testid="graph-toolbar-add-node"]').click();
    await expect(page.locator('[data-testid="graph-inspector-node"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="graph-inspector-node-label"]').fill('Persisted Node');

    const patchPromise = page.waitForResponse(
      (resp) => resp.url().includes(`/diagrams/${emptyDiagramId}/`) && resp.request().method() === 'PATCH',
      { timeout: 10000 },
    );
    await page.locator('[data-testid="graph-editor-save"]').click();
    const response = await patchPromise;
    expect(response.status()).toBeLessThan(300);

    const nodeSelector = '[data-testid="graph-canvas"] [data-testid^="graph-node-"]';
    // React Flow writes each node's GRAPH-SPACE position onto its wrapper as a
    // `transform: translate(Xpx, Ypx)`, independent of the viewport's own
    // pan/zoom. That is the value ADR-DS-02 promises round-trips through the
    // saved payload, so assert it directly — a screen bounding box alone
    // cannot tell "the position was lost" apart from "the viewport was
    // re-framed", and conflating the two is what made this test's original
    // failure hard to read.
    const graphNodeWrapper = page.locator('.react-flow__node');
    const savedTransform = await graphNodeWrapper.first().evaluate((el) => el.style.transform);
    const savedNodeBox = await page.locator(nodeSelector).boundingBox();

    await page.reload();
    await expect(page.locator(nodeSelector)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Persisted Node')).toBeVisible({ timeout: 5000 });

    const reloadedTransform = await graphNodeWrapper.first().evaluate((el) => el.style.transform);
    const reloadedNodeBox = await page.locator(nodeSelector).boundingBox();

    // 1. The graph-space position itself survived the round-trip through the
    //    saved payload (no dagre re-layout on load).
    expect(savedTransform).toMatch(/translate\(/);
    expect(reloadedTransform).toBe(savedTransform);

    // 2. ...and the rendered view is not re-framed either. `fitView` derives
    //    its bounds from each node's declared/measured dimensions, so a node
    //    whose width/height differ between the add path and the load path
    //    shifts the whole viewport on reload even though (1) still holds —
    //    exactly the GH-353 defect this assertion guards (a 40px x-shift from
    //    `handleAddNode` omitting the width/height that `payloadToFlowNodes`
    //    declares).
    expect(savedNodeBox).not.toBeNull();
    expect(reloadedNodeBox).not.toBeNull();
    expect(Math.abs(reloadedNodeBox!.x - savedNodeBox!.x)).toBeLessThan(40);
    expect(Math.abs(reloadedNodeBox!.y - savedNodeBox!.y)).toBeLessThan(40);
  });

  // -------------------------------------------------------------------------
  // Test 7 — Code/Visual toggle shows the LIVE in-editor payload, and
  // toggling back to Visual never discards in-progress edits
  // -------------------------------------------------------------------------
  test('[GH-353] test_graph_code_view_shows_live_payload_and_preserves_edits_on_toggle_back', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${seededDiagramId}/graph`);
    await expect(page.locator('[data-testid="graph-node-n1"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="graph-edit-toggle"]').click();
    await page.locator('[data-testid="graph-node-n1"]').click();
    await page.locator('[data-testid="graph-inspector-node-label"]').fill('Live Edited Label');

    // Toggle to Code — the JSON reflects the unsaved in-editor edit, not a
    // stale server copy.
    await page.locator('[data-testid="graph-viewmode-code-btn"]').click();
    await expect(page.locator('[data-testid="graph-code-view-content"]')).toBeVisible({ timeout: 5000 });
    const codeText = await page.locator('[data-testid="graph-code-view-content"]').innerText();
    expect(codeText).toContain('Live Edited Label');
    const parsed = JSON.parse(codeText);
    expect(parsed.schema_version).toBe(1);
    expect(parsed.nodes.some((n: { label: string }) => n.label === 'Live Edited Label')).toBe(true);

    // Toggle back to Visual — the edit is still there (not discarded).
    await page.locator('[data-testid="graph-viewmode-visual-btn"]').click();
    await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible();
    await expect(page.getByText('Live Edited Label')).toBeVisible({ timeout: 5000 });
  });
});
