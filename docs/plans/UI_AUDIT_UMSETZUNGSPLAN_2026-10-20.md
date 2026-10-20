# Umsetzungsplan: UI-Audit 2026-10-19 (Reuse, Konsistenz, Usability)

> **Status:** Plan, keine Umsetzung. **Datum:** 2026-10-20
> **Quelle:** `docs/reviews/UI_AUDIT_2026-10-19_REUSE_CONSISTENCY_USABILITY.md`
> **Arbeitsbaum:** Worktree `ui-audit-plan`, Branch `worktree-ui-audit-plan`
> **Umfang (Nutzerentscheid):** P0–P2 komplett. Tree-Move wird fertiggestellt, nicht entfernt.
> **Methode:** Live-Probe (Playwright, 27 Routen, 1366x800 und 1366x600, admin/admin, nur lesend)
> + Code-Verifikation am HEAD `2086d2af` + Opus-Analysen zu Rollen, Tree-Move, Tabs, Sidebar, Guard-Rails.

---

## 1. Ergebnis der Verifikation

### 1.1 Review-Befunde: Live bestätigt

| ID | Beleg |
|---|---|
| L-03 | Sidebar-Suche: `text-overflow: clip`, Placeholder bei 176px abgeschnitten (`SidebarNavigation.module.css:209-222`) |
| L-01 | `/metrics`-Footer zeigt `Workspace: 12893b6d-…` ohne Namen (`MetricsDashboard.tsx:677`, `activeWorkspace` liegt in :439 vor) |
| D-12 | `/baselines`: kein `primaryAction` im Header, Create nur im Overflow-Menü und im Empty-State (`BaselinesView.tsx:355-358`, :400-404) |
| D-09 | Baselines-Dialog: Save vor Cancel (`BaselinesView.tsx:694-709`) |
| D-06 | AiDerivationDialog: Primary links, Discard rechts (`AiDerivationDialog.tsx:136-182`) |
| D-04 | 4 Dateien bestätigt, Details siehe Phase 1 |
| U-01 | `RequirementEditors.tsx:527`, `ArchitectureEditors.tsx:538`: Gate nur `isLoading`. Live: Seite zeigt reinen Text "Laden…" ohne Spinner |
| R-01 | Handgebaute Loading/Error in **8** Editors (Review nannte 7: zusätzlich `InterviewEditors:95`) |
| i18n | `de.json:89` `groupRequirements: "Requirements Engineering"` bei deutscher UI |

### 1.2 Review-Befunde: korrigiert oder obsolet

- **L-06 obsolet:** Kachel "Anforderungs-Volatilität" zeigt jetzt Wert `1.00 changes/req`. Task entfällt.
- **T-01 größer:** Es gibt **6** Tablists, nicht 3 (zusätzlich `WorkflowEditor/PresetSegmentedControl`, `MarkdownTabGroup`, getrennt `WorkspaceSettings`).
- **R-02 größer:** Zusätzliche lokale Button-Klassen u.a. in `CsvImport.module.css:136,153`, `LoginPage.module.css:109`, `WorkspaceBannerSection.module.css:68`, `BackupRestoreSection.module.css:77`, `MemorySection.module.css:70`, `RequirementList.module.css:60`, `TraceLinkPanel.module.css:141`, `trace-link-display.module.css:62`, `CustomFieldsEditor.module.css:54`, `MermaidEditor/CanvasEditor.module.css`, `IcdDetailPane`, `DiagramCreateForm`, `DiagramList`. Gesamtzahl wird in Phase 3 per Skript ermittelt, nicht per Hand.
- **R-04 prüfen:** `ArchitectureEditors.tsx:395-408` verdrahtet laut Analyse bereits `onReparent`. Das widerspricht "0 Konsumenten". Im Review wurde nur `onReparent=` gegrept. Vor Phase 5 klären.
- **L-08 widerlegt (live belegt):** `GET /auth/me/` für `admin` liefert `roles: ["admin"]`, `is_tenant_admin: true`. `useHasRole.ts:22` lässt `admin` für `editor` durch. Die Rollen sind also korrekt. Der fehlende Menüpunkt kommt vom **veralteten Live-Build** (v1.8.0-beta.22, Build `dc7ee14`): das ausgelieferte `AdrEditors.tsx` enthält `adr-derive-btn` gar nicht (der Button kam mit #1358/#1360 später). Konsequenz: Alle Live-Belege dieses Plans gelten für Build `dc7ee14`, nicht für HEAD `2086d2af`. Siehe Phase 0 und Phase 7.
- **Ausgeschlossen:** Die Leiste "REVIEW-NOTIZEN" oben auf jeder Seite ist das Dev-Sidecar *bluepencil* (Build-Flag `VITE_BLUEPENCIL_ENABLED`). Kein Produktbefund.
- **Falschpositiv der Probe:** `h1`-Zähler 0 auf `/requirements` kam von zu kurzer Wartezeit. Mit 8 s ist die Seite korrekt.

### 1.3 Neue Befunde aus der Live-Probe

| ID | Schwere | Befund | Beleg |
|---|---|---|---|
| N-04 | **Hoch** | Sidebar-Platz: Der untere Block (EN, Dunkler Modus, Profil, Abmelden, Build) belegt ca. 250px fest. Bei 1366x800 sind nur ca. 11 von 28 Links sichtbar, bei Höhe 600 nur 4. Scroll-Hinweis ist ein 14px-Chevron. Das Review stufte N-01 als YAGNI ein. Das war falsch. | Screenshots `h600_requirements`, `w8_requirements` |
| A-01 | Mittel | 5 Inputs ohne Label/aria-label: `WorkspaceAdminSection.tsx:187,259`, `ThemeManagementSection.tsx:275,287`, `ApiKeysSection.tsx:126` (teils nur Placeholder) | Probe `/system-settings`: 4, `/profile`: 1 |
| A-02 | Niedrig | Memory-Tablist enthält Spacer und Button innerhalb `role=tablist`, keine Pfeiltasten, kein `aria-controls` | `MemoryPage.tsx:468-484` |
| U-04 | Niedrig | Listen zeigen eine nackte Zahl ("880", "0") unter den Filtern ohne Label, dazu Kopf "880 Anforderungen" | `/requirements`, `/baselines` |
| U-05 | Niedrig | Dauerhaft sichtbares "×" (Löschen) an jeder Listenzeile in Requirements | `w8_requirements` |
| U-06 | Niedrig | Metrik-Kacheln: großer Status-Punkt rechts oben plus winziger zweiter Punkt links unten, doppelte Information | `w8_metrics` |
| L-09 | Niedrig | `/metrics`: "Workflow-Lücken 1043" und "Traceability 3.4 %" ohne Link zur Ursache | `w8_metrics` |
| K-04 | Niedrig | Sidebar-Gruppe "Requirements Engineering" Anglizismus (i18n, siehe 1.1) | `de.json:89` |

Konsole: nur erwartete 401 vor dem Login. Keine JS-Fehler.

### 1.4 Vertiefte Analyse (Nutzerwunsch): Kopier-IDs, Hierarchiebäume, Attribut-Katalog, Inspektor

**A) Kopierbare IDs: tatsächlich defekt (3 Fehler, live belegt)**

| ID | Schwere | Befund | Beleg |
|---|---|---|---|
| CP-01 | **Hoch** | Kopieren schreibt auf HTTP-Origins nichts in die Zwischenablage (`navigator.clipboard` ist dort `undefined`), meldet aber Erfolg. `Promise.resolve(undefined).then(report success)`: der Fehlerpfad greift nie. Der Kommentar im Code behauptet das Gegenteil. Live: kein `copy`-Event, kein `execCommand`, trotzdem Toast "kopiert". | `IdChip.tsx:161-171` |
| CP-02 | **Hoch** | Derselbe Fehler an 4 weiteren Stellen, darunter **API-Key kopieren**: ein neu erzeugter Key lässt sich auf HTTP nicht kopieren, wird aber als kopiert bestätigt. Kein Fallback (`execCommand`/markierter Text). | `RevealValue.tsx`, `McpConnectionSection.tsx`, `WorkflowEditorPage.tsx`, `ApiKeysSection.tsx` |
| CP-03 | Mittel | Konzeptfehler: Der Chip zeigt die lesbare ID (`REQ-002`), kopiert aber die UUID, sobald eine `systemId` übergeben wird. Die Meldung "UID kopiert, weil keine System-ID vorhanden" ist unverständlich. Dazu Begriffskollision: Das Feld "System-ID" im Formular zeigt `REQ-002`, im IdChip heißt "System-ID" die UUID. | `IdChip.tsx:141-144,190-194`, Formular "System-ID" |
| CP-04 | Niedrig | Uneinheitlich: Requirements, ADRs, Risks, Issues, TestCases haben Kopier-Button, Architecture (ARCH-001), Needs, Goals nicht. 19–55 Buttons pro Liste, jeder mit UUID im testid. | Probe: `copyBtns` 0 bei Architecture/Needs/Goals |

**B) Hierarchiebäume: nur Architecture ist ein echter Baum**
- Architecture: echter Baum (ARCH-001 → 4 Kinder, 33 Elemente, `parent_id` 32/32 auflösbar). Mit Move-Button. Aber `treeitem` ohne `aria-level` (alle 7 Bäume, `levels: none`).
- Requirements (880), Needs, ADRs, Risks, Issues, TestCases: **flach**. Requirements haben in der API **kein** `parent_id` (0 von 100 gesetzt), Ebene wird abgeleitet (`level_source: derived`, alle Stichproben L1). Die Hierarchie existiert nur über `derives-from`-Links und die TraceSpine, nicht als Baum. Das erklärt die Erwartung "überall Hierarchie" und widerspricht der Annahme in Phase 8, Requirements hätten einen FK-Baum.
- Goals: Baum aus 4 Knoten (synthetisch).
- Folgen für Phase 8: Requirement-Move per FK ist kein Baum-Umhängen, sondern ändert das Datenmodell. Siehe neue Phase 10.

**C) Attribut-Katalog (`/attributes`): Position und Konzept falsch**
- **Drei Einstiege, ein Editor:** `/attributes` (Menü "Verwaltung" → "Attribut-Katalog"), Workspace-Einstellungen → Tab "Attribute", System-Einstellungen → Tab "Attribut-Standards". Gleiche Oberfläche, aber nicht erkennbar, welcher Geltungsbereich bearbeitet wird (tenant-weit, Workspace, Rigor-Preset). Nur das System-Panel hat Minimal/Standard/Extended.
- **Falscher Name:** "Attribut-Katalog" ist ein Layout-Editor (Sichtbarkeit, Pflicht, Sektionen pro Elementtyp). Der eigentliche *Katalog* ist der Dialog "Aus Katalog hinzufügen". Dieser zeigt zugleich "Keine passenden Katalog-Einträge gefunden." und "Wähle eine Vorlage aus." (Widerspruch), Abbrechen-Button ohne Stil (D-04).
- **Jede Zeile trägt das Badge "Global"**, auch im lokalen Editor: Scope nicht unterscheidbar. Auch in der Tabelle: Spalte "Herkunft" immer "Global".
- **Toolbar überladen:** 6 gleichrangige Aktionen (Layout, Exportieren, Importieren, Aus Katalog, Sektion, Speichern) brechen in zwei Zeilen um, "Speichern" steht allein auf Zeile 2 und wirkt deaktiviert. Primäre und seltene Aktionen nicht getrennt.
- **Listenansicht:** pro Zeile 2 Checkboxen ohne Spaltenüberschrift (Sichtbar? Pflicht?), natives `<select>` für Sektion, Sektions-Select zeigt Rohschlüssel. **Tabellenansicht:** technische Schlüssel (`acceptance_criteria`, `classification`, `basic`) statt lokalisierter Namen.
- **Layout-Inkonsistenz:** `/attributes` volle Breite, System-Einstellungen zentriert mit max-width. Tab "Memory" bricht dort in eine zweite Tab-Zeile.
- Weitere Menü-Dopplungen in "Verwaltung": Workflows, Link-Typen und Attribute sind auch Tabs in den Einstellungen.

**D) Inspektor (rechte Seitenleiste): 7 Befunde, einer kritisch**

| ID | Schwere | Befund | Beleg |
|---|---|---|---|
| IN-01 | **Kritisch** | **Kommentar-Panel kaputt:** `GET /api/v1/artifacts/<entity-id>/comments/` liefert **404** bei Requirements, Architecture, ADRs, TestCases. Panel zeigt gleichzeitig "Kommentare konnten nicht geladen werden." und "Noch keine Kommentare." Ursache: `CommentPanel` braucht die generische `artifact_id`, `RightSidebar` übergibt die Fach-ID (`RightSidebar.tsx:459`, `comment_service.py:107`). Kommentieren ist damit praktisch nicht möglich. | Live, 4/4 Typen |
| IN-02 | Hoch | Bei Breite 1366 und ausgeklapptem Inspektor (280 px) wird das Detailformular auf ca. 190 px gequetscht (Titel-Feld abgeschnitten, TraceSpine abgeschnitten). Drei Spalten (Liste, Detail, Inspektor) plus 220-px-Sidebar. | Screenshot `p6_expanded`, `p6_1024` |
| IN-03 | Hoch | Eingeklappt: nur "«", ⏱ (Version), ≅ (Diff) als Unicode-Zeichen, kein Hinweis auf Kommentare, alle Icons öffnen nur die Leiste, keine Badges. Ausgeklappt: Version, Diff, Kommentare als **gestapelte Karten ohne Tabs**, Diff-Panel abgeschnitten. | Live + `RightSidebar.tsx:314-368,443-460` |
| IN-04 | Mittel | Englische Reste in deutscher UI: "Requirement Diff", "Close", "From:", "To:", "Creation baseline"; `aria-label` "Inspektor für stakeholderNeed" (roher Typschlüssel); Datum als rohes ISO bzw. `toLocaleString()` ohne i18n-Sprache. | Live + `VersionPanel.tsx:305,320`, `DiffPanel.tsx:194` |
| IN-05 | Mittel | A11y: kein `aria-expanded`/`aria-controls`, kein Fokus nach Ein-/Ausklappen (Fokus fällt auf `body`), Escape ohne Wirkung, Versionsmenü `role=menu` ohne Pfeiltasten, feste IDs (Doppel-ID-Risiko). | Code + Live (Esc: Breite bleibt 280) |
| IN-06 | Mittel | Zustand nur **pro Artefakttyp** persistent (`reqflow_inspector_*_<kind>`): Aufklappen bei Requirements gilt nicht bei ADRs (live: 280 → 40). "Anheften" (Pin) hat keine Wirkung. Standard eingeklappt unter 1600 px. | Live + `RightSidebar.tsx:74-76,153` |
| IN-07 | Mittel | Datenfehler: Artefaktwechsel setzt `diffLeft`, Trace-Filter nicht zurück, kein Schutz gegen veraltete Antworten, Goals↔MainGoal überschreibt Speicherschlüssel. Jedes Aufklappen löst 5–6 Requests aus, `/versions/` doppelt. Baseline-Chips sind toter Code. | Code |
| IN-08 | Niedrig | Inspektor fehlt bei ICDs, Diagramme-Liste, Glossar (dort als Abschnitt "Verwendungen"), Interviews, Goals-Liste. Memory-Panel nicht in der Leiste. 4× kopiertes `.rightPane`-CSS. Eigener Parallel-Inspektor im WorkflowEditor und 2 weitere `<aside>`-Inspektoren. | Code |

---

## 2. Phasen

Branching: eine Phase = ein Branch `fix/ui-audit-pN-…` ab `main`, ein PR, Conventional Commits. Vor jedem Commit `npm test` (Frontend, enthält Ratchets), bei Backend `pytest` der betroffenen Apps. `graphify update .` nach Codeänderung.
Ratchet-Baselines (`design-system-ratchet.baseline.json`) nur **senken**, nie anheben.

Modellwahl: Opus für Design/Architektur und Sicherheits-Entscheide, Sonnet (`developer`) für mechanische Umsetzung, Haiku/Sonnet (`test-executor`) für Testläufe.

### Phase 0: Vorbereitung (0,5 h)
- Nutzer räumt Testsystem-Goal "UI-Audit Testziel (löschbar)" ab. Entscheid über unversionierte `e2e/live-ui-audit*.js` und `docs/test-reports/live-ui-audit-2026-10-19/` (committen unter `e2e/tools/` oder verwerfen).
- Live-Probe-Skripte (entschieden: Skripte behalten, Screenshots/JSON verwerfen) nach `e2e/tools/` committen, damit jede Phase gegen das Live-System nachgeprüft wird. Screenshots und Reports aus `docs/test-reports/live-ui-audit-2026-10-19/` nicht ins Repo.
- **Testsystem aktualisieren:** Live läuft Build `dc7ee14` (v1.8.0-beta.22), HEAD ist `2086d2af`. Vor Phase 1 neu deployen (`make up` bzw. Rebuild auf 172.20.5.64), sonst werden Fixes gegen veralteten Stand geprüft. Danach die Live-Probe einmal wiederholen und die Befund-Tabelle in 1.1/1.3 gegenprüfen (bisher keine Aussage, welche Befunde HEAD schon behebt). Deployment ist Sache des Nutzers.

### Phase 1: Quick Wins P0 (ca. 6 h, ein PR) — Sonnet
1. **L-03/K-04:** `.searchInput` `text-overflow: ellipsis` + `::placeholder`; Placeholder kürzen auf "Suchen …", Vollton in `aria-label`/`title`. `de.json:89` auf "Anforderungen". Grep nach Tests, die "Requirements Engineering" erwarten.
2. **D-04:** `btn-secondary`/`btn-primary` ergänzen: `AttributeCatalogDialog.tsx:129,137`, `AttributeImportDialog.tsx:57,65`, `AddMemoryFactDialog.tsx:117`, `MemoryManagementSection.tsx:161` (Delete :135/:164 zusätzlich auf `btn-danger`).
3. **U-01/K-03:** Gate `isLoading && items.length === 0` in `RequirementEditors.tsx:527` und `ArchitectureEditors.tsx:538`. Regressionstest: Liste bleibt bei Refetch sichtbar.
4. **D-12/D-09:** Baselines: `primaryAction` im PageHeader (testId `create-baseline-btn` beibehalten), Dialog-Footer Cancel links, Save rechts.
5. **D-06:** AiDerivationDialog-Footer: Reihenfolge Discard/Review-später links, Primary rechts. Falls bewusst anders: Kommentar im Code statt stillem Abweichen. Entscheid beim Reviewer, Standard = angleichen.
6. **L-01:** Metrics-Footer: Workspace-Name aus `activeWorkspace`, UUID nur als Tooltip/Copy.
7. **A-01:** `aria-label` oder `<label>` für die 5 Inputs.
8. **IN-01 (kritisch, 2 h):** Kommentar-Panel: `RightSidebar` übergibt `artifact_id` (generische Artifact-ID) an `CommentPanel`, Panel ausblenden, wenn keine vorhanden. Je Konsument die richtige ID durchreichen (Requirement, Need, ADR, Risk, Issue, TestCase, Architecture). Gegenprüfung live: `GET /artifacts/<id>/comments/` muss 200 liefern. E2E: Kommentar anlegen, neu laden, sichtbar. Dazu den Doppeltext "konnten nicht geladen werden" + "Noch keine Kommentare" entkoppeln (Fehler und Leer schließen sich aus).
9. **CP-01/CP-02 (kritisch, 4 h):** Gemeinsamer Helfer `shared/copyToClipboard.ts`: erst `navigator.clipboard.writeText`, bei fehlender API oder Ablehnung Fallback `textarea` + `document.execCommand('copy')`, sonst ehrlicher Fehlerzustand mit markiertem, selektierbarem Text. Der Rückgabewert (`ok|failed`) steuert Toast und `aria-live`. Alle 5 Stellen darauf umstellen (`IdChip`, `RevealValue`, `McpConnectionSection`, `WorkflowEditorPage`, `ApiKeysSection`). Tests: vitest mit fehlendem `navigator.clipboard` (Fehlerpfad muss `failed` melden), Fallback-Pfad mit gemocktem `execCommand`. Live-Abnahme ausdrücklich auf HTTP-Origin (Testsystem), nicht nur auf localhost.
10. **CP-03 (2 h, Entscheid):** Chip kopiert, was er zeigt (lesbare ID). UUID über zweite Aktion ("UUID kopieren") im Kontextmenü oder Long-Press. Meldung "ID REQ-002 kopiert". Das Formularfeld "System-ID" in "ID" bzw. "Kennung" umbenennen, damit der Begriff "System-ID" nur die UUID meint.
11. **CP-04 (1 h):** Architecture, Needs, Goals bekommen denselben IdChip wie die übrigen Listen. testid ohne UUID-Pflicht prüfen.
- E2E-Selektoren: `grep` auf geänderte testids, Specs `e2e/tests/*baseline*`, `*memory*`, `*attribute*` laufen lassen.
- **Abnahme live:** Probe zeigt `to: ellipsis`, 0 unlabeled Inputs, Baselines hat Header-Button.

### Phase 2: Workflow-Dialoge und Toasts (ca. 8 h) — Sonnet, Review Opus
1. **D-01/D-05:** `WorkflowEditor/ConfirmDialog` löschen. Aufrufer auf `shared/ConfirmDialog` migrieren. Falls `WorkflowModal` Props braucht: `describedById` durchreichen. `EnforcementFlipDialog.tsx:16` auf `shared/ConfirmDialog`.
2. `StateDialog.tsx:59,67`, `TransitionDialog.tsx:98,106` auf `btn-secondary`/`btn-primary`. `WorkflowEditor.module.css:1235-1295` (`btnPrimary`, `btnDanger`, `btnGhost`, redundante `:focus-visible`) entfernen.
3. **D-02:** `WorkflowEditorPage.tsx:90-120` und `audit-dashboard.tsx:378,597-602,1203` auf `useToast()`. Dismiss vereinheitlicht auf 3000 ms. Beide Dateien sind Bug-Magneten (Repowise): Tests vorher lesen, `audit-dashboard.test.tsx` anpassen.
4. **R-03:** `shared/Toast/Toast.tsx` als Präsentationskomponente, testids stabil halten (`workflow-toast` u.a. per Prop).

### Phase 3: Button-CSS-Konsolidierung und Guard-Rails (ca. 16 h) — Opus für Regel-Design, Sonnet für Rollout
1. **Guard-Rail zuerst** (neue `CheckId`s in `test/design-system-ratchet.test.ts`, Baseline-JSON):
   - `local-button-chrome-css`: `*.module.css`-Regelblock mit Selektor `/btn|button|action|tab/i`, der `background`, `border-radius` und `padding` zugleich setzt. Ceiling = gemessener Ist-Wert.
   - `dialog-footer-primary-first`: in `footer={…}` steht `btn-primary`/`btn-danger` vor `btn-secondary`/`btn-ghost`. Nicht auflösbare Variablen als "unresolved" mit eigenem Ceiling.
   - `button-missing-design-system-class` existiert (Ceiling 18): nur abbauen.
   - Optional: `DialogFooter`-Komponente, die die Reihenfolge erzwingt.
2. **Rollout R-02/K-01/D-08/D-10:** lokale Klassen entfernen, reine `btn-*`. Ein Commit pro Modul (Settings, TestRuns, Baselines, Profil, PermissionMatrix, ICD/Diagram/Glossary, CsvImport/Login, shared). Pro Modul Ratchet-Ceiling senken.
3. **D-07:** entfällt, wenn Phase 5 den Dialog ohnehin anfasst (dort `btn-secondary` setzen).
4. **K-02:** 5 hoisted Inline-Style-Objekte in CSS-Module (`McpConnectionSection`, `link-type-listbox`, `LinkTypeEditorPage:417`, `AdrSupersedePanel`, `CreateWorkspaceModal`). Danach Datei-Ausnahmeliste in `eslint.config.js:11-13` kürzen.
- **Visuelle Regression:** Vorher/Nachher-Screenshots der betroffenen Seiten per Live-Probe. Der gleiche Look wird erwartet, Abweichungen einzeln bewerten.

### Phase 4: EmptyState-Rollout (ca. 10 h) — Sonnet
- **R-01:** 8 Editors (`Requirement:527`, `Architecture:538`, `Interview:95`, `TestCase:229`, `Issue:116`, `Risk:116`, `Adr:215`, `Needs:429`), `Reviews/*` (`ReviewsView:901,935,1155`, `SuggestionsInbox`, `ReviewHistoryPanel`), `AttributeCatalogDialog:175-197`.
- Gate-Konvention aus Phase 1 behalten. Spinner sichtbar, Retry-Button für Fehler.
- `t('loading')`-Konvention (K-03): immer mit Default-String, per Lint/Test prüfen.
- **U-02:** Konvention "mutierende Aktion = Toast oder dokumentiert kein Feedback" in `docs/` festhalten. Anwenden auf `AttributeCreateDialog`, `PermissionMatrixEditor`.
- **U-03:** LinkTypeEditor Loading/Empty nur nachziehen, wenn ein leerer Katalog real vorkommt (Probe auf leerem Tenant prüfen).

### Phase 5: Tabs-Primitive (ca. 14 h) — Opus Design, Sonnet Migration
- API laut Opus-Vorschlag: `shared/Tabs/Tabs.tsx` + `TabPanel`. Props: `items`, `value`, `onChange`, `idPrefix`, `variant` (`underline|pill|segmented`), `size`, `fullWidth`, `aria-label`, `activation`, `orientation`, `trailing` (außerhalb von `role=tablist`). Intern `shared/tablistKeyboardNav.ts` erweitern (vertikal, deaktivierte überspringen).
- Per-Item `testId` 1:1 übernehmen: `system-settings-tab-*`, `settings-tab-*`, `memory-tab-*`, `interview-widget-tab-*`.
- Reihenfolge: WorkspaceSettings, SystemSettings (Baseline-Ausnahme `system-settings-tab-*` entfernen, `maxViolations` 18 → 17), Memory (löst A-02), InterviewWidget (lokalen Keydown-Handler löschen), PresetSegmentedControl, MarkdownTabGroup zuletzt.
- Neuer Ratchet `tablist-outside-shared-tabs`, Ceiling 6, sinkt pro Migration.
- Tests: `shared/Tabs/Tabs.test.tsx` (ARIA, roving tabindex, Pfeile/Home/End, manuelle Aktivierung, `trailing`).

### Phase 6: Sidebar-Neuaufbau (ca. 14 h) — Opus Design, Sonnet Umsetzung
Ziel (N-04): bei 1366x800 mindestens 20 Links, bei Höhe 600 mindestens 10 sichtbar.
1. **Footer kompakt:** eine Zeile Icon-Buttons (Sprache "EN"-Badge, Sonne/Mond, Profil, Abmelden), je `aria-label` + `title` (Ratchet `scanIconButtonsMissingAccessibleName` greift). Build-Version in Tooltip. Alle testids (`lang-switch` u.a.) bleiben direkt erreichbar. `lang-switch-notice` neu verankern.
2. **Einklappbare Gruppen:** Gruppenlabel als `<button aria-expanded aria-controls>`, Persistenz `localStorage rl.sidebar.collapsedGroups` (Muster `hideAllOptional`, `:408-420`). Aktive Gruppe immer offen. Default: alle offen, damit e2e-Specs per Text weiter klicken können.
3. **Scroll-Hinweis** sichtbarer (Fade-Verlauf am unteren Rand statt 14px-Chevron).
4. **Admin-Links** (entschieden): alle in einer einzigen, standardmäßig eingeklappten Gruppe "Administration".
5. **Suche als Command-Palette** (Strg+K): das Sidebar-Feld wird ein Button, der die Palette öffnet. Das erledigt L-03 endgültig. Palette nutzt `shared/Dialog` (Fokus-Trap, Escape) und die bestehende globale Suche (`global-search`-testid für e2e am Button erhalten).
6. **Optional, später:** Icon-Rail 220 → 56px. Eigener Schritt, braucht Icons für 28 Links. Nicht in diesem Paket.

### Phase 6b: Inspektor-Umbau (ca. 26–28 h, ersetzt die frühere Skizze; Quelle: Opus-Analyse) — Opus Design, Sonnet Umsetzung
Korrektur der früheren Annahmen: Zustand und Breite werden schon gespeichert (aber pro Typ), Memory ist kein Leistenpanel, `req-tracelink-create-btn` liegt im Formular. B-01 geht in IN-03 auf.

**Schritt 1: Reparaturen (Teil von Phase 1/2, ca. 9 h)**
- F1/IN-01 Kommentar-ID (siehe Phase 1, Punkt 8).
- F2 `key={kind:artifactId}` an `RightSidebar`: setzt `diffLeft`, Trace-Filter und Menüs beim Wechsel zurück, behebt den Goals↔MainGoal-Bug. 1 h.
- F3 Schutz gegen veraltete Antworten (Request-Zähler/AbortController) in Version, Trace, Comment, Ladezustand für Comment, ISO-Datum über i18n-Locale. 2 h.
- F4 A11y: `aria-expanded`/`aria-controls`, Fokus nach Ein-/Ausklappen auf Gegenbutton, Escape schließt Versionsmenü, Pfeiltasten im Menü, IDs per `useId`. 3 h.
- F5 Pin entfernen oder mit Verhalten belegen ("bleibt offen trotz 1600-px-Regel"). Empfehlung: entfernen. 1 h.
- IN-04 i18n: "Requirement Diff", "Close", "From/To", "Creation baseline", `aria-label` mit übersetztem Typnamen. 1 h.

**Schritt 2: Ziel-Architektur (ca. 14 h)**
- `<ArtifactInspector kind ids={{entityId, artifactId}}>` mit **Panel-Registry** `inspectorPanels: Record<ArtifactKind, PanelDef[]>`; `PanelDef = {id, labelKey, icon (lucide), useBadge(ids), render, visible(kind, pageCaps)}`. `pageCaps` ersetzt `hideTraceLinks`.
- **Tabs statt Stapel:** ausgeklappt `shared/Tabs` (Phase 5) mit Text-Labels, aktives Panel pro Typ gemerkt (`rl.inspector.activePanel.<kind>`). Eingeklappt: lucide-Icons (statt ⏱/≅) mit Tooltip und **Badge** (Kommentare, Versionen, Trace-Links). Klick öffnet die Leiste **und** aktiviert das Panel.
- **Lazy Mount:** nur das aktive Panel lädt. Gemeinsamer Versions-Hook mit Cache (Version + Diff laden `/versions/` heute doppelt). Badges über Count-Daten oder Cache.
- **Persistenz global:** `rl.inspector.{open,width}` für alle Typen (offen bleibt offen beim Typwechsel), Einmal-Migration der `reqflow_inspector_*`-Schlüssel.
- **Platz (IN-02):** unter 1500 px öffnet der Inspektor als **Overlay über dem Detailbereich** statt als dritte Spalte, darüber als Spalte. Zusätzlich Mindestbreite für das Detailformular (z. B. 420 px) als Regel: Reicht der Platz nicht, wird der Inspektor Overlay. Breakpoints als Tokens.
- Gemeinsames `EditorDetailLayout` ersetzt die 4× kopierte `.rightPane`.
- Fehlende Typen (ICD, Diagramm, Glossar) schrittweise auf den Inspektor umstellen. Glossar-Sonderfall zuletzt.
- testid-Schema `inspector`, `inspector-tab-<panel>`, `inspector-panel-<panel>`, `inspector-badge-<panel>`, alte IDs als Aliase bis die e2e-Specs umgezogen sind.
- WorkflowEditor-`InspectorPanel` und die 2 weiteren `<aside>`-Inspektoren: Entscheid I-01 bleibt vertagt, aber Resize-Logik als gemeinsamer Hook `useResizablePanel` extrahieren (Duplikat).
- Tastenkürzel zum Öffnen/Schließen, im "Tastenkürzel"-Dialog dokumentiert.
- Tests: vitest (key-Reset, Goals-Wechsel, Kommentar-ID, verworfene Antworten, Fokus, `aria-expanded`, Registry pro Typ, Lazy Mount, Badges, Persistenz inkl. Migration, bestehende `RightSidebar.test.tsx:65-105`), e2e (Kommentar anlegen und nach Reload sehen, Auf-/Zuklappen bei 1366/1920, Tab-Wechsel per Pfeiltasten, aktives Panel bleibt beim Artefaktwechsel, axe auf den 10 Routen).
- `ReqTraceLinkPanel`/`TracePanel`-Trennung (TraceSpine im Formular) bleibt bestehen.

### Phase 6c: Scrollbars und Scroll-Layout (ca. 10 h, entschieden: Layout + Styling) — Opus Inventur, Sonnet Umsetzung
1. **Inventur zuerst:** Live-Probe erweitern: pro Route alle Elemente mit `overflow(-y): auto|scroll` und tatsächlichem Überlauf auflisten, plus Seiten-Scroll (`document.scrollingElement`). Ergebnis in den Plan, bevor Code geändert wird. Zusätzlich statisch: `grep` auf `overflow` in `*.module.css`.
2. **Layout:** App-Shell auf `100dvh`, Seite scrollt nicht. Nur Panes scrollen (Liste, Detail, Sidebar-Nav, rechte Leiste). Ausnahmen (Dashboard, lange Berichte) einzeln festlegen.
3. **Styling:** globale Regeln in `styles/global.css` mit Tokens in `tokens.css`: `scrollbar-width: thin`, `scrollbar-color`, `::-webkit-scrollbar*`, Dark-Mode-Werte. `scrollbar-gutter: stable` auf Scroll-Panes gegen Layout-Sprünge.
4. **Guard-Rail:** Ratchet `overflow-auto-without-scroll-class`: `overflow: auto|scroll` in Modulen ohne gemeinsame Scroll-Klasse, Ceiling startet beim Ist-Wert und sinkt.
5. Prüfen: Mobile-Drawer, Dialog-Scroll (`max-height: 85vh`), `theme-contrast.test.ts` für die Scrollbar-Farben.
- Tests: `SidebarNavigation.test.tsx` erweitern (Collapse, Persistenz). E2E: `sidebar-scroll.spec.ts:25-52` (erwartet `nav-group-admin` bei 1280x437) anpassen, neue Specs für 1366x800 und 1366x600. Mobile-Drawer nicht brechen.

### Phase 7: Rollen-Hygiene (ca. 5 h, L-08 ist **kein Bug**) — Sonnet
Diagnose erledigt: `roles=["admin"]`, Hierarchie greift. Kein Seed-Fix, keine Policy-Änderung.
1. Die 5 Stellen mit `roles.includes("admin")` (`AttributeEditorPage:142`, `BaselinesView:95`, `WorkspaceSettings:157`, `SystemSettings:63`, `WorkflowEditorPage:74`) auf `useHasRole` vereinheitlichen. 1 h.
2. Rollen beim Workspace-Wechsel neu laden (`AuthContext.tsx:203-222`): `/auth/me` liefert heute Rollen über alle Workspaces, die Anzeige kann zwischen Workspaces abweichen. Erst prüfen, ob ein Workspace-bezogener Aufruf existiert. 3–4 h, optional.
3. **Nicht tun ohne ADR + Security-Review:** Tenant-Admin in der Rollenauflösung (`rest.py:276`) zu `admin` machen (weicht die Workspace-Isolation #103 auf).
- Tests: vitest `useHasRole` (admin ⇒ editor), pytest nur falls Punkt 2 das Backend berührt.

### Phase 8: Tree-Move fertigstellen (R-04) (ca. 24–28 h) — Opus Backend-Entscheide, Senior-Developer
Voraussetzung: Klärung, ob Architecture bereits verdrahtet ist (siehe 1.2).
1. **Architecture-Pilot:** Rollen-Gate `onReparent={hasRole('editor') ? … : undefined}`, Fehlermeldungen aus I1/I2/I5 anzeigen. **I2-Bug:** `check_i2` (`validators.py:233-253`) prüft das Level *vor* dem Move, gültige Moves werden bei Standard/Extended abgelehnt. Auf Zielzustand umstellen. 3 h.
2. **Requirements-Pilot (überholt durch Phase 10, hier nur zur Nachvollziehbarkeit):** Requirements haben keinen `parent_id`, der Baum entsteht über `allocated-to` (eine Zuordnung je Requirement). "Umhängen" heißt dort: die eine Zuordnung ersetzen, nur bei bearbeitbarem Zustand. Die folgenden FK-Punkte (ID-Mismatch, `derives-from`-Umhängen) entfallen oder gehen in Phase 10 auf. 
   - **ID-Mismatch:** Baumknoten-ID ist `req.id`, `parentId` ist eine Artifact-ID (`RequirementList.tsx:117-123`). Zuerst per vitest/API-Antwort klären, ob der Baum heute flach ist. Dann `toNode` korrigieren und `req.id` → `artifact_id` beim Reparent mappen. 6 h.
   - `requirementsApi.reparent`, `onReparent` in `RequirementList.tsx:483`, Fehler-Banner, Refresh. 3 h.
   - **TraceLink-Semantik (entschieden: Link automatisch umhängen):** FK-Umhängen ließ bisher den alten `derives-from`-Link stehen, das Level konnte widersprüchlich werden. Neu: der Move entfernt den alten `derives-from`-Link zum bisherigen Parent und legt einen zum neuen Parent an, in **einer** Transaktion mit Revision und Audit-Eintrag. ADR-005-Nachtrag nötig (Traceability ändert sich ohne Nutzerklick, deshalb im Dialog vorab sichtbar machen: "Verknüpfung X → Y wird auf Z umgehängt"). Randfälle: mehrere `derives-from`-Links, Baseline-gesperrte Elemente, Link-Typ-Katalog pro Tenant. 6–8 h.
3. `expected_version` beim Move mitsenden (Konfliktschutz).
4. A11y: Tastatur-Alternative existiert (`tree-move-dialog` + "Move…"-Button). Live-Region-Ansage und axe-Check ergänzen. 1 h.
5. D-07: Cancel im Dialog auf `btn-secondary`.
6. Tests: pytest (Level-Neuberechnung, Zyklus 400, fremder Workspace 400, Viewer 403, Revision), vitest (Verdrahtung, Viewer ohne Move), e2e (Tastatur und Drag, beide Konsumenten). Needs/Goals bleiben außen vor.

### Phase 10: Hierarchiebäume über alle Artefakte (ca. 20–24 h) — Opus Konzept (ADR), Senior-Developer
Ausgangslage siehe 1.4 B: nur Architecture ist ein Baum, Requirements/Needs/ADRs/Risks/Issues/TestCases sind flach, Requirements ohne `parent_id`.
1. **Konzept zuerst (ADR, 4 h):** Welche Beziehung bildet den Baum je Artefakt? Fachliche Vorgabe des Nutzers (2026-10-20): **Requirements strukturieren sich automatisch über die Architekturzuordnung** (`allocated-to`-Links). Die Architektur ist das Gerüst, die Requirements hängen darunter. Vorschlag:
   - **Requirements: "Nach Architektur"-Baum.** Gerüst = Architekturbaum (ARCH-001 → Handstück, Bürstenkopf …). Unter jedem Architekturelement stehen die ihm zugeordneten Requirements. Berechnet im Backend (Endpoint `…/requirements/tree-by-architecture/`), kein neuer FK. Bei 880 Requirements wird die Übersicht über Zähler pro Knoten ("Handstück · 42") und Lazy-Laden hergestellt.
   - **Filter mit Mehrfachauswahl:** Architekturelemente per Multiselect ein-/ausschalten (Baum mit Checkboxen, "Zweig komplett", "nur dieses Element", "Unterelemente einschließen"). Der Filter wirkt auf den Baum und die Liste, bleibt als Query-Parameter in der URL (teilbar) und wird gemerkt. Zusätzlich die vorhandenen Filter (Kategorie, Status, Veraltete) kombinierbar. Aktive Filter als entfernbare Chips über dem Baum.
   - **Regel (Nutzerentscheid): genau eine Architekturzuordnung pro Requirement.** Das Datenmodell erzwingt das heute nicht: in `link_types/builtin.py` und `traceability/` ist für `allocated-to` keine Kardinalitätsgrenze zu finden. Maßnahmen: (1) Datenprüfung vor allem anderen: wie viele Requirements haben 0, 1, >1 `allocated-to`-Links (Auswertung als Audit-Regel im SE-Auditor, nicht per Hand); (2) Validierung im Service: ein zweiter `allocated-to` an dasselbe Requirement wird abgelehnt (409 mit Hinweis "ersetzen statt hinzufügen"), MCP und REST gleichermaßen; (3) Migration/Bereinigung bestehender Mehrfachzuordnungen mit Bericht, keine stille Löschung; (4) UI: Zuordnung heißt "ersetzen", nicht "hinzufügen". Dadurch erscheint jedes Requirement genau einmal im Baum, Zähler stimmen, die Frage nach Mehrfachanzeige entfällt. Für Fälle, die fachlich mehrere Elemente betreffen, bleiben `derives-from`/`decomposes` (Requirement aufteilen) und `references`.
   - **Datenhinweis (live):** Bei REQ-002 zeigt der Abschnitt "Architekturelemente" genau eine Zuordnung (Allocation → *Smart Toothbrush System*, also das L0-Wurzelelement), obwohl es ein L1-System-Requirement ist. Die "7↓" in der TraceSpine ist ein Link-Zähler der Station, **nicht** 7 Allokationen (meine frühere Aussage "7 Architektur-Links" war eine Fehllesung; was die 7 zählt, ist offen). Folge: Hängen viele Requirements an der Wurzel, landet der Baum bei einem riesigen Wurzelknoten. Darum gehört eine Auswertung der Zuordnungstiefe (Wurzel vs. Blatt) in den Datencheck und als Auditor-Warnung ("zu grob zugeordnet").
   - **Zuordnung ändern aus dem Baum (Nutzerentscheid: nur wenn das Requirement noch bearbeitbar ist):** Menü "Zuordnung ändern" und Drag auf ein anderes Architekturelement ersetzen den einen `allocated-to`-Link (eine Transaktion, Audit, Revision). Nur aktiv, wenn Rolle `editor`/`admin` **und** der Workflow-Zustand des Requirements Bearbeitung erlaubt (nicht freigegeben/baselined/obsolet). Sonst Aktion ausgegraut mit Begründung ("Freigegeben, Änderung nur per Änderungsantrag"). Der Dialog zeigt vorab die Wirkung (alte → neue Zuordnung, betroffene Zähler). Ersetzt den bisherigen Tree-Move für Requirements (Phase 8).
   - **Gruppe "Nicht zugeordnet"** als eigener Wurzelknoten (zugleich Qualitätsanzeige: fehlende Allokation), mit Zähler.
   - **Ansichtswechsel** "Nach Architektur | Nach Ebene (derives-from) | Liste". `derives-from`/`decomposes` bleiben als zweite Struktur (V-Modell-Ebenen, TraceSpine), nicht als Standardbaum.
   - Needs: Gruppierung nach Ebene bzw. nach abgeleiteten Requirements (nur Verweis), kein Architekturbaum (Needs sind nicht allokiert).
   - ADRs: `supersedes`-Ketten, Risks/Issues/TestCases: Gruppierung statt Baum (nach Elementtyp/Status), Testfälle optional unter der verifizierten Requirement.
   - Architecture: bleibt FK-Baum.
2. **Umschalter "Baum | Liste"** pro Modul (Standard Liste bei > 200 Einträgen, Baum bei Hierarchie), Zustand gemerkt.
3. **Baum-Barrierefreiheit:** `aria-level`, `aria-setsize`, `aria-posinset` an allen `treeitem` (heute fehlen sie bei allen 7 Bäumen), Pfeiltasten Links/Rechts zum Auf-/Zuklappen. Reparatur in `workspace-tree.tsx` (Bug-Magnet, 2.5/10 Health): vorher Tests lesen, Refactor in kleinen Schritten.
4. Performance: 880 Requirements, Baum lazy (Kinder bei Aufklappen oder serverseitig paginiert).
- Folge für Phase 8: **Requirement-Move per FK entfällt**, Umhängen bedeutet dann `derives-from`-Link ändern (der Link ist die Quelle der Wahrheit, die Entscheidung "Link automatisch umhängen" gilt unverändert, jetzt ohne zusätzlichen FK). Phase 8 für Requirements erst nach dem ADR aus Punkt 1 starten. Der Architecture-Move ist bereits verdrahtet (`ArchitectureEditors.tsx:395-408`, live sichtbar als ⇅-Button): dort nur I2-Bug und Rollen-Gate.

### Phase 11: Attribut-Katalog neu ordnen (ca. 14–16 h) — Opus Konzept, Sonnet Umsetzung
Ziel: ein klarer Ort, klarer Geltungsbereich, aufgeräumte Bedienung (siehe 1.4 C).
1. **Informationsarchitektur (Konzept, 2 h):**
   - Der Menüpunkt "Attribut-Katalog" verschwindet aus "Verwaltung". Dort bleiben nur Workspace-Einstellungen und System-Einstellungen. Attribute leben als Tab "Attribute" (Workspace, lokal) und "Attribut-Standards" (System, global). Alte Route `/attributes` leitet auf den Workspace-Tab um (Legacy-Redirect wie die 6 vorhandenen).
   - Umbenennen: Editor heißt "Attribut-Layout" bzw. "Attribute & Formulare"; "Katalog" bleibt nur der Vorlagen-Dialog ("Attribut-Vorlagen").
2. **Geltungsbereich sichtbar machen:** Kopfband "Du bearbeitest: Workspace *Zahnbürste SysEng Demo* (überschreibt Systemstandard)" bzw. "System-Standard für alle Workspaces (Preset: Standard)". Zeilen-Badge statt "Global" überall: "Systemstandard", "Workspace-Override", "Eigenes Attribut"; Aktion "Auf Standard zurücksetzen" pro Zeile.
3. **Toolbar entflechten:** primär "Speichern" (dauerhaft rechts oben, mit Dirty-Hinweis "Ungespeicherte Änderungen"), "Attribut hinzufügen" als Split-Button (Neu / Aus Vorlage), Layout/Export/Import/Sektion in Overflow-Menü "Mehr". Eine Zeile bis 1024 px.
4. **Listenansicht:** Spaltenköpfe für die Checkboxen ("Sichtbar", "Pflicht"), Sektions-Auswahl lokalisiert, Drag-Handle statt Auf/Ab-Pfeilen (Tastatur-Alternative behalten), Sektionen einklappbar.
5. **Tabelle:** lokalisierte Namen/Sektionen/Audience statt Rohschlüsseln, technischer Schlüssel als zweite, graue Zeile.
6. **Vorlagen-Dialog:** Widerspruch entfernen (Leerzustand **oder** Hinweis), Buttons auf `btn-secondary`/`btn-primary` (D-04), `EmptyState` (R-01).
7. **Layout:** gleiche Breitenregel wie die übrigen Settings-Tabs, Tab "Memory" nicht auf zweiter Zeile (Tabs-Primitive mit Überlauf-Menü, Phase 5).
- Tests: Redirect `/attributes`, Scope-Band je Kontext, Reset-Aktion, Toolbar bei 1024/1366, vorhandene `AttributeEditorPage`-Tests (Bug-Magnet, CCN 92: **zuerst in Teilkomponenten zerlegen**, siehe Repowise "Break up AttributeEditorPage").

### Phase 9: P2-Politur und Hinweise (ca. 6 h) — Sonnet
- **B-01:** Tooltip für eingeklappte rechte Seitenleiste.
- **L-02:** `/audit`: UUIDs in Finding-Texten durch lesbare IDs ersetzen (Backend-Textbau oder Frontend-Mapping). Live in der Probe war `/audit` ohne UUID-Treffer (Seite evtl. ohne geladene Findings): vor Arbeit erneut prüfen.
- **U-04/U-05/U-06/L-09:** nackte Zählzahl labeln oder entfernen, Zeilen-"×" erst bei Hover/Fokus oder ins Kontextmenü, Doppel-Punkt in Kacheln entfernen, Kacheln mit Link zur Ursache.
- **I-01:** Entscheid vertagen (InspectorPanel auf RightSidebar), nur dokumentieren.

---

## 3. Zurückgestellt (Produktentscheid nötig, nicht im Umfang)
- N-03 rollenbasierte Sichtbarkeit (ausblenden vs. disabled).
- D-03 Dialog-Stacking, nur falls verschachteltes Öffnen real auftritt.
- N-02/L-05 bleibt zurückgezogen (ADR-009).
- L-07 Dashboard-Weißraum (Idee).
- Sidebar Icon-Rail (Phase 6, Schritt 4).

## 4. Offene Fragen an den Nutzer
Entschieden (2026-10-20): Phase 6 Gruppen einklappbar + Icon-Footer, Phase 6b rechte Leiste merken + Badges, Phase 6c Layout + Styling der Scrollbars, Phase 8 Link automatisch umhängen.

Ebenfalls entschieden: Live-Skripte behalten, Bilder verwerfen. Rollen-Diagnose durchgeführt (siehe 1.2, L-08).

Noch offen:
1. Wann wird das Testsystem auf HEAD aktualisiert (Phase 0)? Bis dahin sind alle Live-Belege auf Build `dc7ee14` bezogen. (Nutzer: "die Live-Analyse passt auf dem Testsystem", Stand der Gegenprobe am HEAD trotzdem nach dem nächsten Deploy wiederholen.)

Entschieden (2026-10-20, zweite Runde): Phase 10 Hierarchie aus Links berechnen (kein neuer FK). Phase 11 Attribut-Katalog nur in Einstellungen (Menüpunkt entfällt, `/attributes` leitet um). Phase 6b Inspektor unter 1500 px als Overlay. Phase 1 (CP-03) Kopieren der angezeigten ID, UUID als zweite Aktion.

## 5. Reihenfolge, Aufwand, Risiko

| Phase | Inhalt | Aufwand | Risiko |
|---|---|---|---|
| 0 | Vorbereitung | 0,5 h | niedrig |
| 1 | Quick Wins | 6 h | niedrig |
| 2 | Workflow-Dialoge, Toasts | 8 h | mittel (Bug-Magnet-Dateien) |
| 3 | Button-CSS + Guard-Rails | 16 h | mittel (breiter Diff, Optik) |
| 4 | EmptyState-Rollout | 10 h | niedrig |
| 5 | Tabs-Primitive | 14 h | mittel (e2e-testids) |
| 6 | Sidebar | 14 h | mittel (e2e-Specs) |
| 6b | Inspektor-Umbau (inkl. Reparaturen) | 26–28 h | mittel (e2e-testids, Layout) |
| 10 | Hierarchiebäume | 20–24 h | hoch (Datenmodell, ADR) |
| 11 | Attribut-Katalog neu ordnen | 14–16 h | mittel (Bug-Magnet-Datei) |
| 6c | Scrollbars/Scroll-Layout | 10 h | mittel (Layout-Regressionen) |
| 7 | Rollen-Hygiene | 1–5 h | niedrig |
| 8 | Tree-Move (inkl. Link-Umhängen) | 26–30 h | hoch (Datenmodell, TraceLinks) |
| 9 | Politur | 6 h | niedrig |
| Phase 1 erweitert | + Kommentar-ID, Kopier-Helper, IdChip | + 9 h | niedrig |
| **Summe** | | **ca. 185–205 h** | |

Reihenfolge-Empfehlung: **zuerst IN-01 (Kommentare 404) und CP-01/02 (Kopieren)**: beides sind echte Funktionsfehler, keine Politur. Danach Phase 1, 2, 4, dann 3 → 5 → 6/6b/6c, zuletzt 10/11 und 8.

Phasen 1, 2, 4, 7(Diagnose) laufen unabhängig. Phase 3 vor 5 (Ratchet-Muster). Phase 8 zuletzt, braucht Entscheide aus Abschnitt 4.

## 6. Definition of Done je Phase
- `npm test` grün (inkl. Ratchets, Ceilings nur gesenkt), `npx tsc --noEmit`, ESLint, bei Backend `pytest` der Apps.
- Live-Probe gegen `http://172.20.5.64:5173/` ohne neue Befunde, 0 JS-Fehler.
- `data-testid` auf allen neuen interaktiven Elementen, i18n DE/EN, nur Design-Tokens.
- Conventional Commit, PR-Beschreibung mit Verweis auf Befund-IDs.
