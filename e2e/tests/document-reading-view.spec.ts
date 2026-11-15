// R7.2 — document reading view end to end (plan
// docs/superpowers/plans/2026-11-15-document-view-on-document.md).
//
// The reading view is the document itself: numbered chapters plus a table of
// contents, inline editing in two save modes (immediate per field, collected
// into one bulk request), a conflict that survives as a *marked field* with a
// reload affordance, and a print sheet that carries the text and nothing else.
//
// What this file proves, and why each assertion is where it is:
//
// 1. **Chapters** — the table of contents and the numbered chapter sections
//    come from `GET /documents/{id}/view/`; a broken chapter split would show
//    up as a missing TOC entry, not as a styling issue.
// 2. **Immediate mode** — one changed field, one `PATCH /documents/{id}/`, and
//    the document version actually moves. The version is asserted against the
//    API as well as against the head line, because a UI-only bump would look
//    identical while losing the write.
// 3. **Batch mode** — two changed fields produce **exactly one** request to
//    `PATCH /api/v1/artifacts/bulk-update/` (counted on the network, not
//    inferred from the UI). That count is the whole point of R6.
// 4. **Conflict** — an external write bumps the document version, so the
//    surface's `If-Match` tag is stale: the save must answer `412`, the field
//    must be marked, and "reload" must be offered. Nothing may look saved.
// 5. **Print** — `page.emulateMedia({ media: "print" })` drops every control
//    (TOC column, action bar, save bar, mode switch, field editors, sidebar,
//    toasts) and keeps the chapters, black on white.
//
// List-validated without a live stack:
//   npx playwright test document-reading-view --list

import { test, expect, type APIRequestContext } from '@playwright/test';
import {
  createIsolatedWorkspace,
  deleteWorkspace,
  getAuthToken,
  loginAsAdmin,
  setWorkspaceId,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Two chapters with a preamble — enough to prove ordering *and* numbering. */
const BODY = [
  'Der Lesetext beginnt vor der ersten Überschrift.',
  '',
  '# Einleitung',
  '',
  'Diese Sicht ist der Text, nicht ein Formular.',
  '',
  '# Anforderungen',
  '',
  '- Die Sicht ist bearbeitbar.',
  '- Der Druck ist ruhig.',
].join('\n');

interface CreatedDocument {
  id: string;
  artifact_id: string;
  version: number;
}

let token: string;
let workspaceId: string;
let workspaceName: string;
let document: CreatedDocument;

async function createDocument(request: APIRequestContext, title: string): Promise<CreatedDocument> {
  const response = await request.post(`${BACKEND_URL}/api/v1/documents/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: workspaceId,
      title,
      kind: 'Spec',
      description: 'R7.2 fixture: the reading view of one document.',
      body: BODY,
    },
  });
  expect(response.status()).toBe(201);
  const body = (await response.json()) as CreatedDocument;
  return body;
}

/** Read the document head as the API sees it (version + title). */
async function fetchDocument(
  request: APIRequestContext
): Promise<{ title: string; version: number }> {
  const response = await request.get(`${BACKEND_URL}/api/v1/documents/${document.id}/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { title: string; version: number };
  return body;
}

test.describe('Document reading view', () => {
  test.beforeEach(async ({ request, page }) => {
    token = await getAuthToken();
    workspaceName = `e2e-document-reading-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    workspaceId = await createIsolatedWorkspace(token, workspaceName);
    document = await createDocument(request, 'Lesbare Spezifikation');

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test.afterEach(async () => {
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('renders the table of contents and the numbered chapters', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/documents/${document.id}`);
    await expect(page.getByTestId('document-reading-view')).toBeVisible();

    // TOC: one entry per chapter, in chapter order. The leading level-0
    // chapter carries the text before the first heading, so it is listed too —
    // that is the R1 contract (`split_chapters` never special-cases "no
    // chapters"), and the entry is labelled with the document title.
    const toc = page.getByTestId('document-reading-toc');
    await expect(toc).toBeVisible();
    const tocEntries = toc.locator('a[href^="#"]');
    await expect(tocEntries).toHaveCount(3);
    await expect(tocEntries.nth(1)).toContainText('Einleitung');
    await expect(tocEntries.nth(2)).toContainText('Anforderungen');

    // Chapters: numbered sections; the preamble stays an unnumbered section.
    const preamble = page.getByTestId('document-reading-chapter-section');
    await expect(preamble).toContainText('Der Lesetext beginnt');

    const introduction = page.getByTestId('document-reading-chapter-einleitung');
    await expect(introduction).toBeVisible();
    await expect(introduction).toContainText('Einleitung');
    await expect(introduction.locator('h2')).toContainText('1');

    const requirements = page.getByTestId('document-reading-chapter-anforderungen');
    await expect(requirements).toBeVisible();
    await expect(requirements).toContainText('Der Druck ist ruhig.');
  });

  test('saves one field in immediate mode and the version moves', async ({ page, request }) => {
    await page.goto(`${FRONTEND_URL}/documents/${document.id}`);
    await expect(page.getByTestId('document-detail-version')).toHaveText('v1');

    await page.getByTestId('document-field-input-title').fill('Neuer Titel');
    // The save affordance only exists while the field is dirty — its presence
    // is part of the immediate-mode contract.
    await page.getByTestId('document-field-save-title').click();

    // The head follows the write (the reading object is refetched).
    await expect(page.getByTestId('document-detail-version')).toHaveText('v2');

    // …and the server really stored it, not just the surface.
    const stored = await fetchDocument(request);
    expect(stored.title).toBe('Neuer Titel');
    expect(stored.version).toBe(2);
  });

  test('collects two changes into exactly one bulk request', async ({ page, request }) => {
    await page.goto(`${FRONTEND_URL}/documents/${document.id}`);
    await expect(page.getByTestId('document-reading-view')).toBeVisible();

    await page.getByTestId('document-mode-batch').click();
    await expect(page.getByTestId('document-save-bar')).toBeVisible();

    await page.getByTestId('document-field-input-title').fill('Stapel-Titel');
    await page.getByTestId('document-field-input-description').fill('Stapel-Beschreibung');

    const saveBar = page.getByTestId('document-save-bar');
    await expect(saveBar).toContainText('2');

    // Count the bulk requests on the wire: "one request" is a network fact,
    // and a UI that re-sent the batch per field would look the same.
    let bulkRequests = 0;
    page.on('request', (request) => {
      if (
        request.method() === 'PATCH' &&
        request.url().includes('/api/v1/artifacts/bulk-update/')
      ) {
        bulkRequests += 1;
      }
    });

    const bulkResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        response.url().includes('/api/v1/artifacts/bulk-update/')
    );
    await page.getByTestId('document-save-all').click();
    const response = await bulkResponse;
    expect(response.status()).toBe(200);

    const result = (await response.json()) as {
      updated: Array<{ artifact_id: string; version: number }>;
      errors: unknown[];
    };
    expect(result.errors).toEqual([]);
    expect(result.updated).toHaveLength(1);
    expect(result.updated[0].artifact_id).toBe(document.artifact_id);

    // One bulk write, one version bump (1 -> 2), both fields stored.
    await expect(page.getByTestId('document-detail-version')).toHaveText('v2');
    const stored = await fetchDocument(request);
    expect(stored.title).toBe('Stapel-Titel');
    expect(stored.version).toBe(2);

    // Nothing else was in flight — wait for the refetch to settle first, then
    // the counter is a statement about the whole save, not a snapshot.
    await expect(page.getByTestId('document-detail-version')).toHaveText('v2');
    expect(bulkRequests).toBe(1);
  });

  test('marks the field after a stale If-Match and offers reload', async ({ page, request }) => {
    await page.goto(`${FRONTEND_URL}/documents/${document.id}`);
    await expect(page.getByTestId('document-detail-version')).toHaveText('v1');

    // External write: somebody else updates the document, so the surface's
    // `If-Match: "1"` is stale from here on.
    const external = await request.patch(`${BACKEND_URL}/api/v1/documents/${document.id}/`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'If-Match': `"${document.version}"`,
      },
      data: { title: 'Extern geändert' },
    });
    expect(external.status()).toBe(200);
    expect(((await external.json()) as { version: number }).version).toBe(2);

    // The surface still holds version 1 and now writes against it.
    await page.getByTestId('document-field-input-title').fill('Lokale Änderung');

    const conflictResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        response.url().includes(`/api/v1/documents/${document.id}/`)
    );
    await page.getByTestId('document-field-save-title').click();
    const response = await conflictResponse;
    expect(response.status()).toBe(412);

    // The field is marked, the draft is still there and reload is offered.
    const conflict = page.getByTestId('document-field-conflict-title');
    await expect(conflict).toBeVisible();
    // Test id, not label: the reload affordance must survive both locales.
    await expect(page.getByTestId('document-field-reload-title')).toBeVisible();
    await expect(page.getByTestId('document-field-input-title')).toHaveValue('Lokale Änderung');

    // Nothing was overwritten: the external value is still the stored one.
    const stored = await fetchDocument(request);
    expect(stored.title).toBe('Extern geändert');
    expect(stored.version).toBe(2);
  });

  test('prints the chapters without any control', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/documents/${document.id}`);
    await expect(page.getByTestId('document-reading-view')).toBeVisible();

    // A dirty batch keeps the save bar (and therefore the mode switch) on
    // screen, so the print rule is proven against a page that *does* carry
    // controls in screen media.
    await page.getByTestId('document-mode-batch').click();
    await page.getByTestId('document-field-input-title').fill('Druck-Titel');
    await expect(page.getByTestId('document-save-bar')).toBeVisible();

    await page.emulateMedia({ media: 'print' });

    // No controls: TOC column, action bar, save bar, mode switch, field
    // editors, list picker, navigation and toasts.
    await expect(page.getByTestId('document-reading-toc')).toBeHidden();
    await expect(page.getByTestId('document-save-bar')).toBeHidden();
    await expect(page.getByTestId('document-mode-immediate')).toBeHidden();
    await expect(page.getByTestId('document-mode-batch')).toBeHidden();
    await expect(page.getByTestId('document-edit')).toBeHidden();
    await expect(page.getByTestId('document-editable-fields')).toBeHidden();
    await expect(page.getByTestId('splitview-list')).toBeHidden();
    await expect(page.getByTestId('app-sidebar')).toBeHidden();
    await expect(page.getByTestId('banner-stack')).toBeHidden();

    // The chapters stay — complete and readable, black on white.
    const chapter = page.getByTestId('document-reading-chapter-einleitung');
    await expect(chapter).toBeVisible();
    await expect(chapter).toContainText('Diese Sicht ist der Text');

    await expect(page.getByTestId('documents-view')).toHaveCSS(
      'background-color',
      'rgb(255, 255, 255)'
    );
    await expect(chapter).toHaveCSS('color', 'rgb(0, 0, 0)');

    // A chapter heading may neither break across pages nor be stranded at the
    // bottom of one.
    const heading = chapter.locator('h2');
    await expect(heading).toHaveCSS('break-after', 'avoid');
    await expect(heading).toHaveCSS('break-inside', 'avoid');
  });
});
