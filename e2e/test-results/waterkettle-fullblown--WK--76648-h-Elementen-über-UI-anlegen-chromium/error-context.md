# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: waterkettle-fullblown.spec.ts >> [WK-FULL-BLOWN] Wasserkocher SE über 4 Ebenen (UI-driven, Bug-Finding) >> Phase 3c: ICD zwischen Arch-Elementen über UI anlegen
- Location: tests\waterkettle-fullblown.spec.ts:477:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('[data-testid="icds-list"]')
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('[data-testid="icds-list"]')

```

```yaml
- navigation "Main navigation":
  - text: ReqFlow
  - searchbox "Suchen..."
  - list:
    - listitem:
      - link "Dashboard":
        - /url: /
    - listitem:
      - link "Requirements":
        - /url: /requirements
    - listitem:
      - link "Architecture":
        - /url: /architecture
    - listitem:
      - link "ADRs":
        - /url: /adrs
    - listitem:
      - link "Risks":
        - /url: /risks
    - listitem:
      - link "Issues":
        - /url: /issues
    - listitem:
      - link "Test Cases":
        - /url: /testcases
    - listitem:
      - link "Test Runs":
        - /url: /test-runs
    - listitem:
      - link "Traceability":
        - /url: /traceability
    - listitem:
      - link "Baselines":
        - /url: /baselines
    - listitem:
      - link "Import":
        - /url: /import
    - listitem:
      - link "ICDs":
        - /url: /icds
    - listitem:
      - link "Diagrams":
        - /url: /diagrams
    - listitem:
      - link "SE Metrics":
        - /url: /metrics
    - listitem:
      - link "Workspace Settings":
        - /url: /settings
  - switch "Optional-Artefakte" [checked]
  - button "Demo Workspace"
  - text: extended Requirement
  - button "+ Workspace"
  - button "DE"
  - button "Logout"
- main:
  - heading "Interface Control Documents" [level=2]
  - button "+ New ICD"
  - paragraph: No ICDs defined yet. Create one to capture the contract between two architecture elements.
```

# Test source

```ts
  393 |         logBug(
  394 |           'B-UI-001',
  395 |           'Lange REQ-Titel brechen das Sidebar-Layout',
  396 |           `overflow-wrap=${overflow.overflowWrap}, word-break=${overflow.wordBreak}, width=${overflow.width}`
  397 |         );
  398 |       }
  399 |     }
  400 |   });
  401 | 
  402 |   // ===========================================================================
  403 |   // PHASE 2 — Traceability über UI
  404 |   // ===========================================================================
  405 |   test('Phase 2a: derives-from Link zwischen Requirements über UI', async ({ page }) => {
  406 |     const fromId = ids.requirementIds['L1-FUNC'];
  407 |     const toId = ids.requirementIds['L2-CTRL-001'];
  408 |     if (!fromId || !toId) {
  409 |       test.skip(true, 'IDs fehlen — Phase 1b fehlgeschlagen');
  410 |       return;
  411 |     }
  412 |     await createTraceLinkViaUI(page, fromId, toId, 'derives-from');
  413 |     await page.goto(`${FRONTEND_URL}/requirements/${fromId}`);
  414 |     await expect(page.locator('[data-testid="req-tracelink-panel"]')).toBeVisible({ timeout: 8000 });
  415 |   });
  416 | 
  417 |   test('Phase 2b: Architektur → Requirement satisfies Links über UI', async ({ page }) => {
  418 |     const archId = ids.architectureIds['A-HEAT'];
  419 |     const reqId = ids.requirementIds['L1-PERF'];
  420 |     if (!archId || !reqId) {
  421 |       test.skip(true, 'IDs fehlen — Phase 1 fehlgeschlagen');
  422 |       return;
  423 |     }
  424 |     await createArchTraceLinkViaUI(page, archId, reqId, 'satisfies');
  425 |     await page.goto(`${FRONTEND_URL}/architecture/${archId}`);
  426 |     await expect(page.locator('[data-testid="arch-tracelink-panel"]')).toBeVisible({ timeout: 8000 });
  427 |     await expect(page.locator('[data-testid="arch-tracelink-item"]')).toBeVisible({ timeout: 8000 });
  428 |   });
  429 | 
  430 |   // ===========================================================================
  431 |   // PHASE 3 — ICDs mit Versionierung über UI
  432 |   // ===========================================================================
  433 |   test('Phase 3a: ICD-Create-Form hat source/target Selects mit Arch-Elementen', async ({ page }) => {
  434 |     test.setTimeout(15_000);
  435 |     const ctrlId = ids.architectureIds['A-CTRL'];
  436 |     if (!ctrlId) {
  437 |       test.skip(true, 'Architektur-IDs fehlen');
  438 |       return;
  439 |     }
  440 |     await page.goto(`${FRONTEND_URL}/icds`);
  441 |     await page.locator('[data-testid="create-icd-btn"]').click();
  442 |     await page.locator('[data-testid="create-icd-form"]').waitFor({ timeout: 6000 });
  443 |     const sourceOptions = await page.locator('[data-testid="icd-source-select"] option').count();
  444 |     if (sourceOptions < 2) {
  445 |       logBug(
  446 |         'B-ICD-003',
  447 |         'ICD source-select hat zu wenige Optionen',
  448 |         `Erwartet ≥ 2 (placeholder + ≥1 arch), gefunden: ${sourceOptions}`
  449 |       );
  450 |     }
  451 |     const trySource = await page.locator('[data-testid="icd-source-select"]')
  452 |       .selectOption(ctrlId, { timeout: 3000 })
  453 |       .then(() => true)
  454 |       .catch(() => false);
  455 |     if (!trySource) {
  456 |       const optionTexts = await page.locator('[data-testid="icd-source-select"] option')
  457 |         .allTextContents({ timeout: 2000 });
  458 |       logBug(
  459 |         'B-ICD-004',
  460 |         'ICD source-select enthält nicht die Arch-Element-IDs',
  461 |         `Versucht: ${ctrlId.slice(0, 8)}…, Optionen: ${optionTexts.slice(0, 5).join(', ')}`
  462 |       );
  463 |     }
  464 |     const list = page.locator('[data-testid="icds-list"], [data-testid="icds-empty"]');
  465 |     await expect(list.first()).toBeVisible({ timeout: 6000 });
  466 |   });
  467 | 
  468 |   test('Phase 3b: ICD-View rendert (Liste oder Empty-State)', async ({ page }) => {
  469 |     await page.goto(`${FRONTEND_URL}/icds`);
  470 |     await expect(page.locator('[data-testid="icd-view"]')).toBeVisible({ timeout: 10000 });
  471 |     await Promise.race([
  472 |       expect(page.locator('[data-testid="icds-list"]')).toBeVisible({ timeout: 6000 }).catch(() => null),
  473 |       expect(page.locator('[data-testid="icds-empty"]')).toBeVisible({ timeout: 6000 }).catch(() => null),
  474 |     ]);
  475 |   });
  476 | 
  477 |   test('Phase 3c: ICD zwischen Arch-Elementen über UI anlegen', async ({ page }) => {
  478 |     const sourceId = ids.architectureIds['A-CTRL'];
  479 |     const targetId = ids.architectureIds['A-SENSOR-T'];
  480 |     if (!sourceId || !targetId) {
  481 |       test.skip(true, 'Architektur-IDs fehlen');
  482 |       return;
  483 |     }
  484 |     await createIcdViaUI(page, {
  485 |       name: 'WK-ICD-001: MCU ↔ Temperatursensor',
  486 |       sourceArchId: sourceId,
  487 |       targetArchId: targetId,
  488 |       interfaceType: 'ADC + 3.3V',
  489 |       contract: 'ADC1_IN1 liest NTC-Spannung; Update-Rate ≥ 1 Hz.',
  490 |       direction: 'unidirectional',
  491 |     });
  492 |     await page.goto(`${FRONTEND_URL}/icds`);
> 493 |     await expect(page.locator('[data-testid="icds-list"]')).toBeVisible({ timeout: 10000 });
      |                                                             ^ Error: expect(locator).toBeVisible() failed
  494 |   });
  495 | 
  496 |   // ===========================================================================
  497 |   // PHASE 4 — Diagramme über UI
  498 |   // ===========================================================================
  499 |   test('Phase 4a: Block-Diagramm Wasserkessel über UI', async ({ page }) => {
  500 |     await createDiagramViaUI(page, {
  501 |       name: 'WK-Block-001: Wasserkessel Top-Level',
  502 |       diagramType: 'block',
  503 |       payloadFormat: 'mermaid',
  504 |       description: 'Übersicht der Hauptkomponenten',
  505 |       content: `graph LR
  506 |   A[Stromversorgung] --> B[Heizelement]
  507 |   B --> C[Wasserbehälter]
  508 |   D[Steuerung MCU] --> B
  509 |   D --> E[LED-Modul]
  510 |   D --> F[Safety-IF]
  511 |   F --> D`,
  512 |     });
  513 |     await expect(page.getByText('WK-Block-001: Wasserkessel Top-Level').first()).toBeVisible();
  514 |   });
  515 | 
  516 |   test('Phase 4b: Context-Diagramm Anwender-Wasserkasser über UI', async ({ page }) => {
  517 |     await createDiagramViaUI(page, {
  518 |       name: 'WK-Context-001: User-System',
  519 |       diagramType: 'context',
  520 |       payloadFormat: 'mermaid',
  521 |       description: 'Anwender im Kontext',
  522 |       content: `graph TD
  523 |   User((Anwender))
  524 |   WK[Wasserkessel]
  525 |   Power[Stromnetz]
  526 |   User -->|füllt Wasser ein| WK
  527 |   User -->|stellt an| WK
  528 |   WK -->|kocht| User
  529 |   Power -->|230 V| WK`,
  530 |     });
  531 |     await expect(page.getByText('WK-Context-001: User-System').first()).toBeVisible();
  532 |   });
  533 | 
  534 |   test('Phase 4c: Flow-Diagramm State-Machine über UI', async ({ page }) => {
  535 |     test.setTimeout(45_000);
  536 |     const name = 'WK-Flow-001: State Machine';
  537 |     await createDiagramViaUI(page, {
  538 |       name,
  539 |       diagramType: 'flow',
  540 |       payloadFormat: 'mermaid',
  541 |       description: 'Zustandsmaschine',
  542 |       content: `graph LR\n  A[Idle] --> B[Heating]\n  B --> C[Done]\n  B --> D[Error]\n  C --> A\n  D --> A`,
  543 |     });
  544 |     await page.waitForTimeout(1500);
  545 |     await page.goto(`${FRONTEND_URL}/diagrams`);
  546 |     await page.waitForLoadState('networkidle');
  547 |     await expect(page.getByText(name).first()).toBeVisible({ timeout: 10000 });
  548 |   });
  549 | 
  550 |   test('Phase 4d: Diagramm editieren — erzeugt das eine neue Version?', async ({ page }) => {
  551 |     await page.goto(`${FRONTEND_URL}/diagrams`);
  552 |     await page.getByText('WK-Block-001: Wasserkessel Top-Level').first().click();
  553 |     await expect(page.locator('[data-testid="diagram-edit-btn"]')).toBeVisible();
  554 |     await page.locator('[data-testid="diagram-edit-btn"]').click();
  555 |     await page.locator('[data-testid="diagram-source-textarea"]').waitFor({ timeout: 6000 });
  556 | 
  557 |     const detailContent = await page.content();
  558 |     const hasV1 = detailContent.includes('v1') || detailContent.includes('v—') || detailContent.includes('—');
  559 | 
  560 |     const newContent = `graph LR
  561 |   A[Stromversorgung] --> B[Heizelement v2]
  562 |   B --> C[Wasserbehälter v2]`;
  563 |     await page.locator('[data-testid="diagram-source-textarea"]').fill(newContent);
  564 |     await page.locator('[data-testid="diagram-save-btn"]').click();
  565 |     await page.waitForTimeout(1500);
  566 | 
  567 |     const afterContent = await page.content();
  568 |     const hasV2 = afterContent.includes('v2');
  569 |     if (!hasV2) {
  570 |       logBug(
  571 |         'B-DIAG-001',
  572 |         'Diagramm-Edit erzeugt KEINE neue Version (REQ-L1-029 Immutability Bruch)',
  573 |         'Nach dem Edit sollte eine v2 erzeugt werden, der Quellcode ist aber direkt überschrieben. ' +
  574 |           'Versions-Feld zeigt: ' + (hasV1 ? 'v1' : 'kein v-Label')
  575 |       );
  576 |     }
  577 |   });
  578 | 
  579 |   // ===========================================================================
  580 |   // PHASE 5 — Baselines über UI (mehrere)
  581 |   // ===========================================================================
  582 |   test('Phase 5a: Baseline RC1 (project scope) über UI', async ({ page }) => {
  583 |     await createBaselineViaUI(page, { scope: 'project' });
  584 |     await page.goto(`${FRONTEND_URL}/baselines`);
  585 |     await expect(page.locator('[data-testid="baseline-list"]')).toBeVisible({ timeout: 10000 });
  586 |   });
  587 | 
  588 |   test('Phase 5b: Baseline doc1 (document scope) über UI', async ({ page }) => {
  589 |     await page.goto(`${FRONTEND_URL}/baselines`);
  590 |     await page.locator('[data-testid="create-baseline-btn"]').click();
  591 |     await page.locator('[data-testid="create-baseline-form"]').waitFor({ timeout: 6000 });
  592 |     await page.locator('[data-testid="baseline-scope-document"]').check();
  593 |     const artifactSelect = page.locator('[data-testid="baseline-artifact-select"]');
```