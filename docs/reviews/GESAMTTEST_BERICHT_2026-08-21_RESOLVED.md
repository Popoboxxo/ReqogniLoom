> **STATUS: RESOLVED** — findings addressed via `docs/superpowers/plans/2026-08-22-review-findings-remediation.md`
> (Tasks 1-16), merged in PR(s) #<fill in after merge>. Deferred (not fixed, tracked separately):
> - §4.2–4.5 / consolidated-table items 12–15 (E2E test-helper gaps, DE/EN locale-assertion mismatches, stale
>   waterkettle fixtures, Frontend-Unit `localStorage` failures) — already fixed independently in PR #694
>   (issues #687–693) before this plan started, or (item 12) no longer reproduces on re-run; not part of
>   Tasks 1-16.
> - §6 item 7 / Glossary toolbar gaps (Task 16) — status filter + sort dropdown added; the "create in dialog"
>   toggle deliberately left unwired (`GlossaryTerm` has no backend interview-protocol support; would either
>   silently no-op or need out-of-scope backend work).
> - §6 item 9 / Admin backup-button loading state (Task 16) — fixed only for the named "+ Create Backup"
>   button; the restore-confirm button has the identical bug but wasn't named in the finding, left unfixed.
> - Finding 22 / §10.1 EnforcementFlipDialog i18n (Task 13) — the dialog itself is translated with a `lang`
>   attribute; the parent `EnforcementModePanel.tsx` remains fully English-hardcoded (out of scope for this
>   task); a genuine live-DOM verification of the dialog (vs. the jsdom-only test used) is still outstanding,
>   as already flagged by this review's own §10.1 ("echter Live-Test steht noch aus").
> - Finding 23 / dead "stakeholder" category filter (Task 16) — the filter option itself was removed; one
>   orphaned `categories.stakeholder` i18n key was left in `de.json`/`en.json` (dead, zero runtime impact).
> - Finding 7 / 6 create-forms migrated to the `Dialog` primitive (Task 12) — resolved as specified, with a
>   disclosed tradeoff: the ICD and Diagram forms shifted from an embedded `SplitView` side panel to a
>   full-screen `Dialog` overlay (loses side-by-side list visibility while creating), matching existing
>   Dialog-over-SplitView precedent elsewhere; not a defect, but worth noting for a future design pass.
>
> Resolved on 2026-08-22.

---

# Gesamttest-Bericht ReqogniLoom — 2026-08-21

> Vollständiger Applikationstest: Backend-Unit-/Integrationstests, Frontend-Unit-Tests, komplette E2E-Suite (Playwright), WCAG-2.1-AA-Accessibility-Audit und visueller Design-Konsistenz-Audit über alle 24 Haupt-Routen inkl. Dialoge. Koordiniert über 5 parallele/sequenzielle Subagenten (Backend/Frontend über günstiges Modell, E2E/Design/A11y über Standard-Modell wegen höherem Interpretationsbedarf).

**Stack-Stand:** Docker-Compose-Dev-Stack (postgres, redis, backend, celery, celery-beat, frontend) frisch gestartet, Backend healthy, Frontend (Vite) auf :5173 erreichbar.

---

## 1. Executive Summary

| Testebene | Ergebnis | Pass-Rate |
|---|---|---|
| Backend (pytest) | 5047 passed, 11 skipped, 4 errors | 99,9 % (Fehler = Umgebungsartefakt, kein Produktbug) |
| Frontend Unit (vitest) | 1135 passed, 8 failed (144 Dateien) | 99,3 % |
| E2E (Playwright, 45 Spec-Dateien, 310 Tests) | 279 passed, 28 failed, 3 skipped | 90,0 % |
| Accessibility (WCAG 2.1 AA, 41 Scans) | 9 gebundene Findings (3 critical, 4 serious, 2 major/minor) | — |
| Design-Konsistenz (24 Routen + Dialoge) | 10 Top-Inkonsistenzen, mehrere quer über die App wiederkehrend | — |

**Kernaussage:** Die Applikation ist funktional sehr stabil (Backend/Frontend-Unit-Ebene >99 % grün). Die meisten E2E-Fehlschläge sind Testskript-Probleme (fehlende Titel-Eingabe, harte englische Textassertions gegen eine standardmäßig deutschsprachige UI, ein veralteter Selektor), nicht Produktbugs — mit einer Ausnahme (Traceability-Seite, unklar, siehe 4.1). Der Accessibility- und Design-Audit fördern dagegen reale, bislang unentdeckte Probleme zutage: fehlende Formular-Labels (WCAG A, kritisch), sitewide zu geringer Kontrast bei zwei wiederkehrenden UI-Elementen, eine inkonsistente Primary-Button-Implementierung quer über alle Listen-Seiten, und ein systemischer Rest an unübersetzten englischen UI-Texten in einer sonst durchgängig deutschen Oberfläche.

**Nebeneffekt während des Audits:** Der Design-Audit-Agent hat unbeabsichtigt einen echten Backup-Job ausgelöst (Klick auf "+ Create Backup" im System-Settings-Sweep, non-destruktiv, aber ~58 MB Speicherverbrauch, ID `3938a530-…`). Nicht gelöscht (außerhalb des Agenten-Scopes als destruktive Admin-Aktion) — zur manuellen Prüfung/Bereinigung markiert.

---

## 2. Backend-Tests (pytest)

**Befehl:** `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test`
**Laufzeit:** 17:17 min
**Ergebnis:** `5047 passed, 11 skipped, 28 warnings, 4 errors`
**Rohlog:** `docs/test-reports/backend-pytest-raw.log`

### 4 Fehler — Umgebungsartefakt, kein Produktbug

Alle 4 Fehler in `mcp_server/tests/test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation` (Setup-Fixture `seeded_workspace_id`):

```
AssertionError: Seeded 'Demo Workspace' not found — is bootstrap_admin/seed_demo loaded?
Available workspaces: ['Test Workspace E2E', 'e2e-isolated-1787324187615-jmd51w', ... 24 weitere e2e-isolated-* Workspaces]
```

**Ursache:** `make test-backend` läuft laut Makefile-Kommentar bewusst gegen die **gleiche** postgres/redis-Instanz wie der laufende Dev-Stack (kein isoliertes Test-DB-Schema für diese Fixture). Der parallel/kurz zuvor gelaufene E2E-Lauf hat 25 `e2e-isolated-*`-Workspaces angelegt und die "Demo Workspace" durch neuere `-modified_at`-Sortierung verdrängt. Die Fixture ist explizit gegen genau dieses Szenario gehärtet (siehe Docstring in der Datei, REQ-127) — sie *erkennt* das Problem korrekt und bricht kontrolliert ab, statt einen falschen Regressions-Alarm zu erzeugen.

**Empfehlung:** Kein Code-Fix nötig. Vor dem nächsten Voll-Testlauf: `docker-compose down -v && up` + `seed_demo` frisch laden, um Testdaten-Drift zu vermeiden (siehe auch Finding E2E-Gruppe 5, Abschnitt 4.5).

### 11 Skipped
Nicht im Detail exportiert (Rohlog enthält vollständige Liste) — keine kritischen Marker (kein `xfail(strict)`/`SKIP: TODO` mit offenem Bug-Bezug in der Zusammenfassung).

---

## 3. Frontend-Unit-Tests (vitest)

**Befehl:** `make test-frontend`
**Laufzeit:** 23,52 s
**Ergebnis:** 144 Testdateien (2 fehlgeschlagen, 142 grün), 1143 Tests (8 fehlgeschlagen, 1135 grün) — **99,3 % Pass-Rate**
**Rohlog:** `docs/test-reports/frontend-vitest-raw.log`

### 8 Fehlschläge — 1 root cause, testinfrastrukturell

| Komponente | Tests | Root Cause |
|---|---|---|
| `InterviewWidget/InterviewWidget.test.tsx` | 4/4 | `TypeError: Cannot read properties of undefined (reading 'clear')` in `beforeEach()` — `localStorage` in jsdom-Umgebung undefined |
| `shared/ArtifactInspector/RightSidebar.test.tsx` | 4/4 | Gleiche Ursache: `window.localStorage` undefined |

**Ursache:** jsdom-Testumgebung wird ohne `--localstorage-file`-Flag gestartet (`ExperimentalWarning: localStorage is not available`). Beide Testdateien rufen `localStorage.clear()` in `beforeEach` auf, bevor die Umgebung es bereitstellt.

**Empfehlung:** Vitest-Config um `environmentOptions` bzw. Node-Flag `--localstorage-file` ergänzen, oder `localStorage` in `beforeEach` defensiv per `Object.defineProperty`/jsdom-Setup mocken (Projekt-Testsetup-Datei, nicht die einzelnen Testdateien).

### 2 flaky (nur im ersten Lauf, im zweiten Lauf grün)
- `src/test/mermaidSanitizeRoundtrip.test.ts` — Timeout bei 21,6 s (5 s Vitest-Default-Timeout)
- `src/components/DiagramView/DiagramDetailView.test.tsx` — Timeout bei 29,5 s

**Empfehlung:** Timeout für diese beiden (asynchron/rechenintensiven) Tests explizit erhöhen (`{ timeout: 30000 }`), statt auf den globalen 5 s-Default zu vertrauen.

---

## 4. E2E-Tests (Playwright — vollständige Suite)

**Befehl:** `cd e2e && npx playwright test` (nach Korrektur: `BACKEND_URL=http://localhost:8001`, Default im Repo ist `:8000` und passt nicht zu diesem Stack — siehe `e2e/README.md` Z. 477–501, bekannte lokale Stolperfalle)
**Umfang:** alle 45 Spec-Dateien, 310 Tests, sequenziell (`workers: 1`)
**Laufzeit:** 21,0 min
**Ergebnis:** 279 passed, 28 failed, 3 skipped (`test.skip()`, keine Config-Skips), 0 flaky
**Artefakte:** `docs/test-reports/e2e-raw.log`, `docs/test-reports/e2e/results-full.json`, `docs/test-reports/e2e/playwright-report-full/index.html`, Screenshots unter `e2e/test-results/*/test-failed-1.png`

### 4.1 Gruppe 1 — Traceability-Seite hängt im Ladezustand (1 Test, **unklar, nicht bestätigt als Produktbug**)

`tracelink-creation.spec.ts:150` — `[REQ-L2-RF-006] traceability page shows list or empty state`. Navigation zu `/traceability`, Seite bleibt über den 10 s-Timeout hinaus bei "Laden…", weder Liste noch Empty-State rendert. Screenshot zeigt hängenden Spinner, auch die Sidebar-Navigation "Traceability" fehlt.

**Einschätzung:** Könnte real sein (Endpoint langsam/fehlerhaft unter dem frisch reseedeten Toothbrush-Datensatz, ~880 Requirements) oder ein zu kurzes Timeout für dieses Datenvolumen. **Nicht als bestätigter Produktbug einstufen** — manueller Repro mit offenen DevTools gegen `/traceability` nötig, um die tatsächliche Netzwerk-Antwort zu sehen.

**Empfehlung:** Manuelle Nachprüfung vor Ticket-Erstellung.

### 4.2 Gruppe 2 — Fehlendes Titel-Ausfüllen im gemeinsamen Test-Helper (14 Tests, **Test-Infrastruktur, kein Produktbug**)

Betroffen: `requirement-editor.spec.ts` (7), `requirements.spec.ts` (2), `se-workflow.spec.ts` (3), `stakeholder-needs.spec.ts` (2).

Alle klicken `[data-testid="create-req-btn"]` → `[data-testid="req-new-save-btn"]`, ohne vorher `[data-testid="req-new-title-input"]` zu befüllen. Der Save-Button ist korrekt disabled (Titel-Pflichtfeld) und aktiviert sich nie → 60 s Timeout je Test. `artifact-diff.spec.ts` zeigt das korrekte Muster (füllt zuerst den Titel) und ist grün.

**Einschätzung:** Formularvalidierung funktioniert wie vorgesehen — Copy-Paste-Lücke in 4 Testdateien, **kein Produktbug**.

**Empfehlung:** Höchster Hebel im gesamten Fund-Katalog — eine 1-Zeilen-Ergänzung (`.fill('[data-testid="req-new-title-input"]', '…')`) in 4 Dateien behebt 14 von 28 Fehlschlägen.

### 4.3 Gruppe 3 — Deutsch/Englisch-Locale-Mismatch in Text-Assertions (7 Tests, **Test-Infrastruktur, kein Produktbug**)

Betroffen: `canvas-diagram.spec.ts` (4), `mermaid-diagram.spec.ts` (2), `diagram-node-graph.spec.ts` (1, `getByText('No nodes yet')`), `dashboard.spec.ts` `[REQ-L3-RF002-002]` (1, i18n-tolerante Regex greift trotzdem nicht, da "SE-Modus" fehlt).

**Ursache:** App rendert im Test-Environment standardmäßig Deutsch (bestätigt gegen `frontend/src/i18n/locales/de.json` vs. `en.json`), Tests erwarten hartcodiert Englisch, ohne Locale explizit zu setzen.

**Empfehlung:** Locale in `helpers/auth.ts` explizit setzen ODER Assertions i18n-tolerant machen (Pattern existiert bereits in `dashboard.spec.ts`, muss nur um die fehlenden deutschen Begriffe ergänzt werden).

### 4.4 Gruppe 4 — Brüchiger CSS-Selektor, Formular seither erweitert (1 Test, **Test-Infrastruktur**)

`needs-cross-boundary.spec.ts:97` — `locator('form input[type="text"]')` matcht jetzt 2 Elemente (Titel-Input + neu hinzugekommenes `need-new-category-input`) → Playwright-Strict-Mode-Fehler.

**Empfehlung:** Selektor auf konkretes `data-testid` umstellen.

### 4.5 Gruppe 5 — Veraltete/verbliebene Fixture-Daten über Testläufe hinweg (2 Tests, **Umgebungshygiene**)

`waterkettle-fullblown.spec.ts:721` und `waterkettle-scenario.spec.ts:392` erwarten einen frischen `open`/`in_progress`-TestRun, finden aber einen bereits `Passed`/`failed`-Status vor (Fixed-Name-Fixtures `WK-Run-Smoke` / `WK_TESTRUN_NAME`, kein Reset zwischen Läufen). Dashboard-Screenshot bestätigt zusätzlich 14 verbliebene `e2e-isolated-*`-Workspaces aus früheren Läufen (siehe auch Backend-Fehler, Abschnitt 2).

**Empfehlung:** Vor jedem vollständigen E2E-Lauf `docker-compose down -v && up` + frisches `seed_demo`/`seed_toothbrush`; mittelfristig Fixtures auf randomisierte Namen umstellen statt feste Strings.

### Auffälligkeiten
- 0 flaky Tests — jeder Fehlschlag war deterministisch reproduzierbar (konsistent mit den identifizierten Root Causes: kaputte Assertions/Selektoren, keine Timing-Races).
- Kein Setup-Crash — alle 45 Dateien liefen vollständig durch.
- Visuelle Regression und dedizierter A11y-Scan waren **nicht** Teil der E2E-Suite selbst (kein Referenz-Screenshot-Baseline im Repo) — dafür separat Abschnitt 5 und 6.

---

## 5. Accessibility-Audit (WCAG 2.1 AA)

**Methode:** Playwright + axe-core (`wcag2a`, `wcag2aa`, `wcag21aa`), 23 Routen + 18 Dialog-/Inline-Form-Zustände = 41 Scans, Login via echtem UI-Formular.
**Artefakte:** `docs/test-reports/design-audit-screenshots/a11y-*.json`, `a11y-summary.json`, `a11y-console-errors.json`

### Critical (WCAG A — 4.1.2 Name, Role, Value)

| # | Fund | Ort |
|---|---|---|
| 1 | 4 Formularfelder ohne Label im Glossar-Verknüpfungs-Dialog | `GlossaryView.tsx` (`create-link`-Dialog) |
| 2 | Namensfeld ohne Label im Workspace-Create-Dialog | `CreateWorkspaceModal.tsx` (`workspace-name-input`) |
| 3 | 2 `&lt;select&gt;`-Elemente ohne zugänglichen Namen | `custom-field-type-select` (/settings), `backup-type-select` (/system-settings) |

**Fix:** Natives `&lt;label htmlFor&gt;` je Feld — First Rule of ARIA, kein ARIA-Workaround nötig.

### Serious (WCAG AA/A)

| # | Fund | Ort | Messwert |
|---|---|---|---|
| 4 | Kontrast Build-Version-Anzeige (sitewide, alle 41 Scans) | `SidebarNavigation.module.css .buildVersion` | **1,69:1** statt gefordert 4,5:1 |
| 5 | Kontrast Preset-Badge | `.presetBadge`, Workspace-Switcher | **2,06:1** statt 4,5:1 |
| 6 | Verschachtelte interaktive Elemente (Dashboard, 25 Karten) | `WorkspaceCard.tsx:62-155` — `role="button"`-Div enthält echten `&lt;button&gt;` | — |
| 7 | `aria-label` auf rollenlosem `&lt;span&gt;` (Status-Punkte) | `/metrics` — 5 `metric-status-*`-Spans | — |

Finding 4/5: Bereits ein früherer Fix existiert für einen ähnlichen Fall ("darken dark theme's primary color", Commit `5fed3d0d`) — deckt diese beiden Stellen offenbar nicht ab.

### Major/Minor

| # | Fund | Ort |
|---|---|---|
| 8 | 6 "Neu anlegen"-Formulare (Requirements, Architecture, ICD, Diagram, TestRuns, TraceLinks) nutzen die im Projekt bereits vorhandene `Dialog`-Primitive (`shared/Dialog/Dialog.tsx`, korrekt mit `role="dialog"`, Fokus-Falle, Escape) **nicht**, sondern reine Inline-Toggles ohne Fokus-Management | 6 Call-Sites, Migration auf bestehende Primitive reicht |
| 9 | Fokus-Sichtbarkeit fehlt am globalen Such-Input als erstem Tab-Stop nach Dialog-Öffnung (3 von 16 Stichproben: `/glossary`, `/icds`, `/diagrams`) | `SidebarNavigation.module.css .searchInput` |

**Nicht abgedeckt (Folgeaudit empfohlen):** Canvas-/Tab-Panel-Dialoge (`WorkflowEditor/StateDialog.tsx`, `TransitionDialog.tsx`, `EnforcementFlipDialog.tsx`), die 4 weiteren Theme-Varianten (Light/Bauhaus/Nordic/Sepia), Live-Screenreader-Test (nur strukturelle axe-Konformität geprüft).

---

## 6. Visueller Design-Konsistenz-Audit

**Methode:** Eigenständiges Playwright-Skript (`e2e/design-audit.js`), 24 Routen × 2 Viewports (1366px/1920px) + primärer Dialog pro Route + Hover-/Disabled-Zustands-Stichproben + `getComputedStyle`-Abgleich gegen `frontend/src/styles/tokens.css`.
**Artefakte:** 87 Screenshots + `_computed-styles-report.json` unter `docs/test-reports/design-audit-screenshots/`

**Bekannte Lücke:** Audit lief gegen eine leere Demo-Workspace ("Test Workspace E2E", 0 Einträge) — Tabellen-/Zeilen-Styling mit echten Daten wurde **nicht** geprüft, Folgelauf gegen befüllten Workspace empfohlen.

### Top 10 App-weite Design-Inkonsistenzen (nach Reichweite/Schweregrad)

1. **Zwei divergierende Primary-Button-Implementierungen auf derselben Seite** — bestätigt auf Requirements, Needs, ADRs, Risks, Testcases, Goals: Header-"Neue X"-Button (Radius 12px, **kein** Hover-Verdunkeln) vs. Empty-State-CTA (Radius 6px, korrektes Hover-Verhalten) — gleiche Basisfarbe, unterschiedliche Radius-Tokens (`--radius-md` vs. `--radius-sm`) und inkonsistentes Hover-Feedback. Deutet auf zwei nicht vereinheitlichte Button-Komponenten hin.
2. **Sort-Dropdown-Text wird vom eigenen Caret-Icon abgeschnitten** — auf allen 2-Spalten-Filterleisten-Seiten (Needs, ADRs, Risks, Issues, Testcases, Goals), 3-Spalten-Seiten (Requirements) und Einzelfilter-Seiten (Diagrams, ICDs) nicht betroffen.
3. **Gemischt Deutsch/Englisch UI-Text**, 6 unabhängige Fundstellen in sonst durchgängig deutschen Screens: Traceability-Dialog "Derivation", ICD-Dialog "One per line", Testfall-Dialog "e.g. Test case title...", Baselines-Button "Compare", komplettes "ReqIF Import"-Panel, komplette "Backup & Restore"-Kartentexte. **Systemische i18n-Lücke**, keine Einzel-Typos.
4. **Dashboard-Workspace-Karte: Preset-Badge überlappt mit "Aktuell aktiv"-Pill** — reproduzierbar bei 1366px und 1920px.
5. **Workflow-Editor: Kanten-Label/Node-Kollision** — "deprecated"-Transition-Label überlappt den "APPROVED"-State-Node, Text zu "…ecated" abgeschnitten.
6. **Empty-State-Musterbruch auf Architecture** — jede andere Listen-Seite zeigt Headline + Erklärtext + farbigen CTA-Button, Architecture nur eine graue Zeile "Keine Einträge vorhanden." ohne CTA.
7. **Glossar-Toolbar-Lücke** — fehlender Status-Filter, Sort-Dropdown und "Lieber im Dialog erstellen?"-Toggle, die jede Schwester-Artefaktliste hat.
8. **Sidebar-Navigation ohne Scroll-Hinweis** — bei 1366×900 ist die Nav nach "Architektur" abgeschnitten (Traceability, Impact, ICDs, Diagrams, "Test & Qualität", "Verwaltung" unsichtbar), ohne sichtbaren Scrollbalken/Fade/Chevron-Hinweis.
9. **Layout-Sprung bei Admin-Ladezustand** — "+ Create Backup" kollabiert auf bloße "…" ohne Mindestbreite statt In-Place-Spinner.
10. **Verwaiste Zeile im Metric-Card-Grid** — 5. Karte auf SE-Metriken wandert allein in Zeile 2 eines 4-Spalten-Grids, große Lücke sichtbar auf jeder Ansicht.

### Weitere Einzelbefunde
- Impact-Seite: Subtitle-Farbton wirkt bläulicher als Dashboard-Subtitle — nicht abschließend bestätigt (Subtitles nicht im Computed-Style-Sample enthalten).

---

## 7. Konsolidierte Findings-Tabelle (nach Schweregrad, ohne Test-Infrastruktur-Rauschen)

| Prio | Bereich | Fund | Schwere | Typ |
|---|---|---|---|---|
| 1 | A11y | 3× fehlendes Formular-Label/Select-Name | Critical (WCAG A) | Produktbug |
| 2 | A11y | Sitewide Kontrast Build-Version-Anzeige 1,69:1 | Serious (WCAG AA) | Produktbug |
| 3 | A11y | Kontrast Preset-Badge 2,06:1 | Serious (WCAG AA) | Produktbug |
| 4 | A11y | Verschachtelte interaktive Elemente, Dashboard (25 Karten) | Serious | Produktbug |
| 5 | Design | Zwei divergierende Primary-Button-Styles quer über 6 Listen-Seiten | Major | Konsistenzbug |
| 6 | Design | i18n-Lücke: 6 unübersetzte englische UI-Textblöcke | Major | Konsistenzbug |
| 7 | A11y | 6 Create-Formulare ohne vorhandene Dialog-Primitive (kein Fokus-Management) | Major | Konsistenzbug |
| 8 | Design | Sort-Dropdown-Text-Clipping auf 6 Seiten | Minor-Major | Konsistenzbug |
| 9 | E2E | Traceability-Seite hängt im Ladezustand | Unklar | Zu verifizieren |
| 10 | Design | Workflow-Editor Edge-Label/Node-Kollision | Minor | Rendering-Bug |
| 11 | Design | Dashboard Badge/Pill-Überlappung | Minor | Rendering-Bug |
| 12 | Frontend Unit | localStorage undefined in 2 Testdateien (8 Tests) | — | Testinfrastruktur |
| 13 | E2E | 14 Tests: fehlendes Titel-Ausfüllen im Test-Helper | — | Testinfrastruktur |
| 14 | E2E | 7 Tests: DE/EN-Locale-Mismatch in Assertions | — | Testinfrastruktur |
| 15 | Backend | 4 Errors: Demo-Workspace durch E2E-Datenmüll verdrängt | — | Umgebungshygiene |
| 16 | A11y | **Blocker:** Workflow-Editor-Canvas (State-Nodes + Transition-Edges) komplett tastaturunerreichbar | Blocker (WCAG A) | Produktbug |
| 17 | Design | **Kritisch:** Workspace-Switcher hard-caps bei 25 Einträgen, keine Pagination — Workspaces jenseits Platz 25 nie über UI erreichbar | Critical | Produktbug |
| 18 | A11y | TransitionDialog "Von"-Feld ohne Label | Critical (WCAG A) | Produktbug |
| 19 | A11y | `.buildVersion`-Kontrast scheitert sitewide in ALLEN 5 Themes (1,69–3,80:1 statt 4,5:1) | Serious (WCAG AA) | Produktbug |
| 20 | A11y | Text-muted/surface-Kontrast scheitert zusätzlich in Bauhaus (4,21:1) und Sepia (3,80:1) | Serious (WCAG AA) | Produktbug |
| 21 | Design | Traceability: Ziel-Requirement-ID hart abgeschnitten ohne Ellipsis, ~1100px ungenutzter Platz daneben | Major | Rendering-Bug |
| 22 | A11y | EnforcementFlipDialog hartcodiert Englisch ohne `lang`-Attribut in deutschsprachigem Dokument | Serious (WCAG AA) | Konsistenzbug |
| 23 | Design | Requirements-Kategoriefilter bietet toten Filter "stakeholder" (0/792 Treffer) | Minor | Datenbug |

---

## 8. Bekannte Nebeneffekte / Aufräumbedarf

- **Echter Backup-Job ausgelöst** während des Design-Audits (Klick auf "+ Create Backup"): ID `3938a530-…`, ~58 MB, `completed_at: 2026-08-21T15:11:14Z`, sichtbar via `GET /api/v1/admin/backups/`. Nicht gelöscht (destruktive Admin-Aktion außerhalb Agenten-Scope) — bitte manuell prüfen/entfernen falls nicht gewünscht.
- **25 `e2e-isolated-*`-Workspaces** und diverse Test-Workspaces (`Ontology Test …`, `Needs-Cross-Boundary-Test-WS-…`) verbleiben im Dev-Stack aus vorherigen/aktuellen E2E-Läufen — verursachen die 4 Backend-Test-Fehler (Abschnitt 2) und die 2 Waterkettle-E2E-Fehler (Abschnitt 4.5). Empfehlung: `docker-compose down -v && up` + Reseed vor dem nächsten sauberen Testlauf.
- Design-Audit lief gegen leere Demo-Daten — Tabellen-/Zeilen-Rendering mit echten Daten unaudited.

---

## 9. Empfehlungen / Nächste Schritte

1. **Sofort behebbar, hoher Hebel:** E2E-Gruppe 2 (Titel-Fill in 4 Spec-Dateien) — 14 von 28 E2E-Fehlschlägen mit einer 1-Zeilen-Änderung je Datei behoben.
2. **A11y Critical (Findings 1-3):** Labels ergänzen — kleiner, klar umrissener Fix, 3 Dateien.
3. **A11y Serious Kontrast (Findings 4-5):** Farbwerte in `SidebarNavigation.module.css` gegen tatsächlichen Compositing-Hintergrund neu berechnen.
4. **Design Top 1 (Primary-Button-Divergenz):** Button-Komponenten auf den betroffenen 6 Seiten vereinheitlichen — höchste Reichweite aller Design-Findings.
5. **i18n-Lücke (Design Top 3):** 6 konkrete Textstellen identifiziert, direkt übersetzbar ohne strukturelle Änderung.
6. **Vor Verifizierung als Bug:** Traceability-Ladezustand (Abschnitt 4.1) manuell mit offenen DevTools reproduzieren.
7. **Umgebungshygiene:** Dev-Stack vor dem nächsten Voll-Testlauf zurücksetzen (Abschnitt 8).
8. **Folgeaudits — ✅ abgeschlossen, siehe Abschnitt 10.**

---

## 10. Folgeaudits (Nachtrag 2026-08-21, gleicher Tag)

Alle drei in Abschnitt 9 Punkt 8 offenen Folgeaudits wurden nachgeholt: A11y für Canvas-/Tab-Panel-Dialoge + Theme-Varianten, Design-Audit gegen befüllten Workspace, Aufbau einer echten Playwright-Visual-Regression-Baseline. Durchgeführt auf Branch `feat/e2e-visual-regression-baseline`.

### 10.1 A11y-Folgeaudit — Canvas-/Tab-Panel-Dialoge & 4 Theme-Varianten

**Methode:** axe-core, Dark-Theme (Teil A, 3 Dialoge inkl. Tastatur-Stichprobe) + Light/Bauhaus/Nordic/Sepia (Teil B, je 3 Ankerpunkte).
**Artefakte:** `docs/test-reports/design-audit-screenshots/a11y-followup-full.json`, 17 Screenshots, Skript `e2e/a11y-followup.js` (uncommitted).

**Neuer Blocker (schwerster Einzelfund des gesamten Gesamttests):** `WorkflowEditor/StateNode.tsx` und `TransitionEdge.tsx` tragen `role="button" tabIndex={0}`/`{-1}` OHNE `onKeyDown`-Handler — der komplette Workflow-Editor-Canvas ist für reine Tastaturnutzer nicht bedienbar (WCAG 2.1.1 A). Live per Fokus+Enter/Space verifiziert, kein Fixing, echter Produktbug.

Weitere Funde: TransitionDialog "Von"-Feld ohne Label (critical); `.buildVersion`-Kontrast scheitert in ALLEN 5 Themes (1,69:1–3,80:1, gefordert 4,5:1) — derselbe Root Cause wie der bereits im ersten Audit gefundene Fall, nur bisher nicht themenübergreifend gefixt; zusätzliche, themenspezifische Kontrast-Regression bei Bauhaus (4,21:1) und Sepia (3,80:1) für `--color-text-muted`-auf-Surface; verschachtelte interaktive Elemente (Dashboard) in allen 4 Themes reproduziert; EnforcementFlipDialog komplett hartcodiert Englisch ohne `lang`-Attribut. EnforcementFlipDialog selbst war live nicht erreichbar (App stand bereits im "Authoritative"-Modus) — stattdessen isolierter jsdom-Test (0 axe-Verstöße strukturell, Kontrast dort nicht zuverlässig prüfbar) — echter Live-Test steht noch aus.

### 10.2 Design-Audit gegen befüllten Workspace ("Zahnbürste SysEng Demo", ~880 Artefakte)

**Artefakte:** `docs/test-reports/design-audit-populated/` (68 Screenshots + `_report.json`), Skript `e2e/design-audit-populated.js` (uncommitted).

**Neuer kritischer Produktbug:** Der Workspace-Switcher lädt nur Seite 1 der paginierten `/api/v1/workspaces/`-Liste (`WorkspaceContext.tsx:229-230`, kein `next`-Following) und hat keine Suche. Bei mehr als 25 Workspaces im Tenant (dieser Dev-Stack hat 28) sind ältere Workspaces **über die UI schlicht nicht mehr erreichbar** — bestätigt genau an der Ziel-Workspace dieses Audits, die nur per direktem API-Call (`?page=2`) zu finden war. Kein Cosmetic-Bug, sondern ein Datenerreichbarkeits-Bug, der mit wachsender Tenant-Nutzung zwangsläufig auftritt.

Weiterer neuer Fund: Auf `/traceability` (1974 echte Trace-Links) wird die Ziel-Requirement-ID in jeder Zeile hart abgeschnitten (kein Ellipsis, anders als bei allen anderen Listen), während ~1100px Bildschirmbreite daneben ungenutzt bleiben — unabhängig vom Viewport. Requirements-Kategoriefilter bietet eine tote Option "stakeholder" (0 von 792 Treffern).

Bestätigt, unverändert mit echten Daten: Sort-Dropdown-Clipping (Needs/ADRs/Risks/Issues/Testcases), Sidebar-Nav-Cutoff ohne Scroll-Hinweis. Requirements-Liste selbst verträgt die Datenmenge gut (Virtualisierung via `@tanstack/react-virtual`, Ladezeit ~2,3s bei 792 Einträgen, keine Verzögerung).

### 10.3 Playwright-Visual-Regression-Baseline aufgebaut

**Ergebnis:** 29 echte Snapshot-Vergleichstests (`expect(page).toHaveScreenshot()`) — 24 Hauptrouten + 5 Schlüssel-Dialoge — committed auf `feat/e2e-visual-regression-baseline` (Commit `d060b8eb`). Baseline zweimal unabhängig gegen sich selbst verifiziert: 29/29 grün, 0 Pixel-Diffs. Volatile Elemente (Build-Version, workspace-abhängige Dashboard-Liste) werden maskiert, Motion reduziert — Determinismus damit hergestellt, wo vorher keine Baseline existierte.

**Committed:** `e2e/tests/visual-regression.spec.ts`, `e2e/tests/visual-regression.spec.ts-snapshots/` (29 PNGs), `e2e/playwright.config.ts` (`maxDiffPixelRatio: 0.02`).
**Bekannte Einschränkung:** Dashboard-Route ist nicht auf die isolierte Test-Workspace scopebar (`DashboardViews` listet alle Tenant-Workspaces) — dort ist nur die statische Chrome (Header/Sidebar) unter Regressionstest, die Workspace-Liste selbst ist maskiert.
**Noch nicht erledigt:** Branch ist nicht gemergt/gepusht — liegt lokal bereit zur Review.

---

*Erstellt per koordiniertem Multi-Agent-Testlauf (main-chat als Orchestrator, insgesamt 9 Subagenten über zwei Runden: `tester`×2 auf günstigem Modell für Backend/Frontend-Unit, `e2e-tester`×3 für E2E-Suite, populierten Design-Audit und Visual-Regression-Baseline, `accessibility-specialist`×2 für WCAG-Haupt- und -Folgeaudit, `git`×2 für Branch-Erstellung und Commit). Rohdaten und Screenshots vollständig unter `docs/test-reports/` archiviert (uncommitted, außer der Visual-Regression-Baseline selbst).*
