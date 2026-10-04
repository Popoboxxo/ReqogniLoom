---
type: REVIEW
scope: "WP-3/WP-3b (UI) — adversarial second review"
status: final
date: 2026-10-01
author_agent: frontend-reviewer
branch: chore/audit-review-2026-09
head: 636de7d4 (kein frontend-/e2e-Delta seit Audit-Baseline abd61aed)
method: "Statische Gegenprüfung aus Quelltext (Read/Grep/eigene Read-only-Scans); Browser nur optional, nicht benötigt. AUDIT_EVIDENCE/* wurde nicht als Beweis verwendet."
targets:
  wp3: [001,002,003,004,005,006,008,016,017,009,014,015,018,020,021,022]
  wp3b: [300,301,302,303,305,310,311,312,319,320,321]
---

# REVIEW_WP3 — Adversariale Zweitprüfung WP-3 (UI-Browser) & WP-3b (Frontend statisch)

## 1. Scope & Methodik

Gegenprüfer-Rolle (`frontend-reviewer`), read-only. Geprüft wurden die Registereinträge
`docs/audit/2026-09/AUDIT_FINDINGS.md` §3 sowie die Reports `AUDIT_UI_BROWSER.md` (WP-3) und
`AUDIT_FRONTEND_STATIC.md` (WP-3b). Jede Aussage wurde **neu aus dem Quelltext** abgeleitet;
`docs/audit/2026-09/AUDIT_EVIDENCE/*` diente ausdrücklich nicht als Beweis.

Werkzeuge: `Read`/`Grep` sowie drei eigene **Read-only**-Zählskripte (nach Gebrauch gelöscht),
deren Ergebnisse unten als reproduzierbare Gegenbeweise zitiert sind. Verifiziert wurde gegen
HEAD `636de7d4`; `git diff --stat abd61aed HEAD -- frontend e2e` ist **leer**, d. h. Frontend und
E2E sind identisch zur Audit-Baseline — die Verifikation ist 1:1 übertragbar. Die im Auftrag
genannte HEAD-Angabe `10dc620f` ist ein Vorfahr von HEAD (nur Audit-Dokumente seither).

Verdikt-Sprache: `BESTAETIGT | TEILWEISE | FALSCH | UEBERZOGEN | UNTERSCHAETZT |
NICHT VERIFIKABAR | KEIN REQOGNILOOM-BEZUG`. „Gegenbeweis" = Fundstelle, die die Aussage stützt
oder widerlegt; jede zitierte Zeile wurde gelesen.

## 2. Gegenbeweis-Tabelle

| ID | Register-Claim | Verdikt | Gegenbeweis (Pfad:Zeile + Zitat) | Korrektur |
|---|---|---|---|---|
| **001** | 453 Requests = „401 Workspaces × 1 `/requirements/` + 5 Paginierungsseiten" | **TEILWEISE** (Mechanik ja, Zahl nein) | `frontend/src/components/DashboardViews/useDashboardData.ts:47-53`: `useQueries({ queries: source.map((ws) => ({ queryKey: requirementKeys.list(ws.id), queryFn: () => requirementsApi.listAll(ws.id) …` → pro Workspace ein Call, keine Pagination/Virtualisierung. `AUDIT_UI_BROWSER.md:413` nennt selbst „401 + 5" — Summe **406 ≠ 453**. | Rechnerisch **nicht** rekonstruierbar; die 47 Restrequests sind unbelegt. N+1-Mechanik = BESTAETIGT; Zahl = NICHT VERIFIKABAR. |
| **002** | „112 `t()`-Keys fehlen in beiden Locales, 41 Dateien" | **TEILWEISE / UNTERSCHAETZT** | Eigener Scan (Repo-Scanner-Nachbau, nur `.test.*` ausgeschlossen): **116** fehlende Keys — identisch mit `MISSING_KEY_BASELINE` (`frontend/src/test/i18n-parity.test.ts:186`). Dateien mit ≥1 fehlendem Key: **34** (prod-only). | Zahl **112 → 116**; „41 Dateien" nicht reproduzierbar (**34**). |
| **003** | Kein Skip-Link; 25 Sidebar-Einträge | **BESTAETIGT** | `frontend/src/components/NavigationShell/NavigationShell.tsx:122-127`: `<div className={styles.contentRow}><SidebarNavigation /><main … role="main">` — kein Skip-Link davor; repo-weit 0 Treffer für Skip-Link-Muster. `SidebarNavigation.tsx:74-138`: **26** `NAV_ITEMS`, davon 1 (`/reviews`) preset-gegated ⇒ im Standard-Preset 25 sichtbar. | Zahl 25 plausibel; statisch sind 26 deklariert. |
| **004** | Rohe i18n-Keys als sichtbare LLM-Abschnittstitel | **BESTAETIGT** (Mechanik) | `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx:69-73`: `return SLOT_LABELS[name] ?? name;` und `:304-308`: `t(\`settings.promptTemplates.slot.${slot.name}\`, labelForSlot(slot.name))`. Unbekannte Slot-Namen ⇒ sichtbarer Fallback = Rohname. | Die Strings selbst kommen aus Backend-Slots (nicht in `frontend/src` literal). Mechanik bestätigt. |
| **005** | 2 `combobox` ohne accessible name (`/system-settings`) | **BESTAETIGT** | `frontend/src/components/SystemSettings/ThemeManagementSection.tsx:275-295`: beide `<select data-testid="tenant-default-palette-select" …>` / `…mode-select …>` haben **kein** `aria-label` und **kein** zugeordnetes `<label htmlFor>` (das davorstehende `<span>` ist nicht verknüpft). | Der Test `ThemeManagementSection.test.tsx:58-77` prüft die `aria-label` nur am **Löschen-Button**, nicht an den Selects — Lücke ungetestet. |
| **006** | ~190 API-Keys ungepaginiert; Widerruf **ohne** Bestätigungsdialog | **TEILWEISE** (Widerruf-Teil FALSCH) | `ApiKeysSection.tsx:224`: `{keys.map((key) => (` → volle Liste, kein Filter/Page/Virtualizer. Gegenbeweis zum Widerruf-Teil: `ApiKeysSection.tsx:276-288`: `{pendingRevokeId && (<ConfirmDialog … testId="api-key-revoke-confirm" …)}`. | „ohne Bestätigungsdialog" = **FALSCH** (WP-3b hat das in §11 korrekt widerlegt). Ungepaginiert = BESTAETIGT. |
| **008** | Bei Deep-Link startet Sidebar mittig; aktiver Eintrag offscreen | **BESTAETIGT** | `SidebarNavigation.tsx:570-576` rendert `NavLink` ohne jede `scrollIntoView`-Logik; `grep scrollIntoView` in der Datei = 0. Die Nav-Liste ist scrollbar (`:502` `data-testid="sidebar-nav-scroll-content"`), ein aktives Item unterhalb der Falte wird nicht hereingeholt. | Kein Auto-Scroll zum aktiven Item ⇒ plausibel und reproduzierbar. |
| **016** | „Ratchet prüft Key-Menge, nicht Code→Locale-Nutzung" | **TEILWEISE** (Mechanik falsch) | `i18n-parity.test.ts:202-222` enthält sehr wohl einen Code→Locale-Check: `missing = [...referenced].filter((key) => !deKeys.has(key) && !enKeys.has(key))` mit `expect(missing.length).toBeLessThanOrEqual(MISSING_KEY_BASELINE)`. | Nicht „falsche Dimension", sondern **eingefrorene Obergrenze 116** (kann nie rot werden). Kern (Maskierung) bestätigt; Beschreibung korrigiert. |
| **017** | Abdeckungslücken (`/attributes` 0, div. nur generisch, i18n 1/54) | **BESTAETIGT** | 54 Specs (`glob e2e/tests/*.spec.ts`). `/attributes` = 0 Treffer in `e2e/`. `/goals,/workflows,/audit,/impact,/glossary` nur in `ui-konzept-gates.spec.ts:65-82` (Routenliste) und `visual-regression.spec.ts:22-42`. `/interviews` nur `visual-regression`. `lang-switch` in genau **1** Spec (`stakeholder-needs.spec.ts:302`). | Alle Teilzahlen bestätigt. |
| **009** | Datum visuell auf „27.9.202" abgeschnitten (DOM korrekt) | **NICHT VERIFIKABAR** | `RequirementList.tsx:124`: `return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();` — DOM-Wert korrekt. Clipping ist ein reiner Render-Effekt (Spaltenbreite/Overflow). | Fehlender Prüfschritt: Browser-Messung der Spaltenbreite. Die zitierte Datei `RequirementTreeNode.module.css` enthält **keine** Datums-Regel (kein Gegenbeweis möglich). |
| **014** | `/test-runs` hängt ~10 s; Ursache Workspace-Pagination (5 Seiten) | **TEILWEISE** | Mechanik: `frontend/src/context/WorkspaceContext.tsx:232-234`: `// switcher (no pagination, no search there). listAll() follows next across all pages via the shared getAllPages helper.` / `const all = await workspacesApi.listAll();` ⇒ 401 Workspaces = 5 Seiten blockieren den Kontext. | Mechanik BESTAETIGT; „~10 s" ist eine Live-Messung (statisch nicht bestätigbar). |
| **015** | Loading-Stall >10 s deterministisch, skaliert mit Workspace-Anzahl | **TEILWEISE** | Siehe 014: `workspacesApi.listAll()` ist unabhängig von der Route und skaliert linear mit der Workspace-Anzahl. Reproduzierbar ist die lineare Skalierung, nicht die konkrete Sekundenzahl. | Dauer NICHT VERIFIKABAR; Skalierungsmechanik BESTAETIGT. |
| **018** | `/workflows` React-Flow-Attribution ohne Pro-Abo entfernt | **BESTAETIGT** | `components/DiagramGraphEditor/GraphCanvas.tsx:183` und `components/WorkflowEditor/WorkflowCanvas.tsx:246`: `proOptions={{ hideAttribution: true }}`. | Attribution ist deaktiviert; Lizenz-/Compliance-Bewertung bleibt Eigentümerentscheidung. |
| **020** | „Lesbare IDs" nur lokal persistiert; UI nennt die Lücke selbst | **BESTAETIGT** | `UserProfileSettings/IdentifiersSection.tsx:25` (`localStorage`, „why there is no server round trip"), `:94-96` Hint-Key `identifiers.persistenceNote`. | BESTAETIGT (Konsistenz mit offenem #1096). |
| **021** | WIDERLEGT: 0 Hex, 0 Inline-Styles | **TEILWEISE / UEBERZOGEN** | Inline-Styles: eigener Scan `style={{` prod = **0** (BESTAETIGT). Hex: eigener Scan (Kommentare gestrippt) = **37** in **5** Prod-Dateien (`utils/asilUtils.ts` 18, `CanvasEditor.tsx` 15, `diagram-view-shared.ts` 2, `GraphEdge.tsx` 1, `canvas-geometry.ts` 1). | Die absolute Aussage „0 harte Hex-Werte" ist **FALSCH**; korrekt ist nur „0 im Komponenten-CSS / 0 inline". |
| **022** | WIDERLEGT: Auth- und Dialog-Fokuspfade konform | **BESTAETIGT** (statisch) | `shared/Dialog/Dialog.tsx` zentraler Trap; `AuthGate`/`AuthContext` (httpOnly-Cookie) unverändert; `ConfirmDialog` mit Cancel-Initialfokus. Live-Aussagen (#991/#985) bleiben Laufzeit-belegt. | Statisch konform; Laufzeit-Feinheiten bleiben e2e-Domäne. |
| **300** | 116 Keys fehlen in beiden Locales (41 Dateien) | **TEILWEISE** | 116 Keys reproduziert (eigener Scan = `MISSING_KEY_BASELINE`). Dateien: **34** prod. | „41 Dateien" nicht reproduzierbar. |
| **301** | `MISSING_KEY_BASELINE = 116` macht Lücke unsichtbar | **BESTAETIGT** | `i18n-parity.test.ts:186`: `const MISSING_KEY_BASELINE = 116;`; `:214-219`: `expect(missing.length, …).toBeLessThanOrEqual(MISSING_KEY_BASELINE);`. | Ceiling-Ratchet kann nie rot werden — bestätigt. |
| **302** | 27 Count-Keys ohne Pluralform | **BESTAETIGT (±1)** | Eigener Scan (`t("key", { …count… })` + kein `key_one`/`key_other`): **26** ohne Pluralform bei **53** Count-Calls (Report: 27/55). Beispiel belegt: `NeedsEditors.tsx:264` `t('needs.deriveCreated', { count })`; `de.json:637`/`en.json:637` haben nur `deriveCreated`, kein `_one`/`_other`. | ±1 Messtoleranz; Zitatzeile **263 → 264**. |
| **303** | 536 tote Locale-Keys (25,3 %) | **BESTAETIGT (±1)** | Eigener Scan: **535** tot (T_CALL+`<Trans>` prod-only) bzw. **537** (T_CALL-only); 2120 Locale-Keys. 536/2120 = 25,3 %; 535/2120 = 25,2 %. | Zahl im Rundungsbereich bestätigt; exakt 535 (bzw. 537 je Scanner). Caveat Dynamik gilt. |
| **305** | 100-Seiten-Paginierungsschleife im Client | **BESTAETIGT** | `frontend/src/api/requirements.ts:156`: `while (nextUrl && pageCount < 100) {` (mit `page_size:"100"` ab `:143`). | Bestätigt. |
| **310** | ≥6 verifiziert stale E2E-Selektoren | **TEILWEISE / UEBERZOGEN** | Reproduzierbar stale: `e2e/tests/user-profile.spec.ts:23,24,31,41` nutzen `visibility-row/checkbox/reset-diagrams`; in `frontend/src` = **0** Treffer. Die ebenfalls gelisteten `login-form`, `main-header`, `todo-item` existieren **nirgends** in `e2e/` (und nicht in `frontend/src`) — keine „stale E2E-Selektoren". | ≥6 → **3** reproduzierbar. Neue Namen sind Phantom-Zitate. |
| **311** | 52 interaktive Elemente ohne TID (93,5 %) | **TEILWEISE** | Lücke existiert: eigener engerer Tag-Scan (`<button/input/select/textarea/a`) = 759 Elemente, 615 mit TID (**81 %**), 144 ohne. `ArtifactForm.tsx` ist auffällig (viele Feld-Widgets ohne TID). | Lücke BESTAETIGT; die exakte Quote 93,5 %/52 ist methodenabhängig und mit dem engeren Scan **nicht** reproduziert. |
| **312** | 4 datei-lokale TID-Dubletten | **BESTAETIGT** | Genau die 4 genannten Literale doppelt in derselben Datei: `GlossaryView.tsx:598,607` (`glossary-form`), `ReqTraceLinkPanel.tsx:649,713`, `CustomFieldsEditor.tsx:154,166`, `TransitionDialog.tsx:143,151`. | Bestätigt. (Eigener Scan findet zusätzlich 25 weitere Literal-Dubletten in bedingten Render-Zweigen — nicht zwingend Strict-Mode-Risiko.) |
| **319** | 324 Buttons ohne `btn-*`-Klasse eingefroren | **BESTAETIGT** | `frontend/src/test/design-system-ratchet.baseline.json:6-7`: `"button-missing-design-system-class": { "maxViolations": 324, … }`. | Bestätigt. |
| **320** | React 18 vs. `^19.2.8` im Manifest | **BESTAETIGT** | `frontend/package.json:34`: `"react": "^19.2.8"`, `:35` `"react-dom": "^19.3.0"`; `AGENTS.md`/Projektkontext sagen „React 18". | Bestätigt (Doku-Drift). |
| **321** | 44 `console.*` in Produktion | **BESTAETIGT** | Eigener Scan (Prod, Tests ausgeschlossen): **44** `console.`-Vorkommen in **26** Dateien, `console.log`-Calls = **1**. | Zahl + `console.log`-Anteil exakt bestätigt. |

## 3. Register-Quercheck: 112 vs. 116

| Artefakt | Wert | Reproduziert? |
|---|---|---|
| Repo-Ratchet-Scanner (`i18n-parity.test.ts`, T_CALL only, nur `*.test.tsx?` ausgeschlossen) | **116** | **ja** |
| WP-3b-Scanner (T_CALL + `<Trans i18nKey>`, prod-only) | **116** | **ja** (identische Missing-Menge) |
| Register `AUD-002` / `AUDIT_UI_BROWSER.md` | **112** | nein — **Unterzählung** |
| Register `AUD-300` / `AUDIT_FRONTEND_STATIC.md` | **116** | ja |

**Auflösung:** `116` ist korrekt und identisch mit der eingefrorenen Baseline. WP-3b behauptet in
§1.2, die Differenz 112→116 erkläre sich aus „Testdatei-Ausschluss + Ergänzung von
`<Trans i18nKey>`". Das ist **widerlegt**: Der Testdatei-Ausschluss ändert den Zähler nicht
(die `src/test/*.ts`-Hilfsdateien enthalten keine fehlenden Prod-Keys), und die beiden
`<Trans>`-Keys (`actions.newLink`, `actions.showAll`) sind ohnehin über
`TraceLinkPanel.tsx:237,244` als `t()`-Literale erfasst — `<Trans>` trägt also **+0** bei.
Die reale Ursache ist schlicht eine ungenaue 112er-Zählung in WP-3.

**Zusätzlicher Befund:** Der Zähler 116 enthält mindestens einen **Phantom-Key**:
`permissionMatrix.capability.` stammt aus `components/PermissionMatrix/PermissionMatrixEditor.tsx:103`
`{t("permissionMatrix.capability." + cap)}`. Die T_CALL-Regex liest nur das String-Literal vor
dem `+` und behandelt den Präfix als vollen Key. Echter Lückenstand = **115** (bzw. 114 ohne
dynamic-getarnte). Die „grüne" 116er-Baseline ist damit auch ein Artefakt der Scanner-Naivität.

## 4. Verdikt-Zählung

| Verdikt | Anzahl | IDs |
|---|---:|---|
| BESTAETIGT | 14 | 003, 004, 005, 008, 017, 018, 020, 022, 301, 305, 312, 319, 320, 321 |
| TEILWEISE | 12 | 001, 002, 006, 014, 015, 016, 021, 300, 302, 303, 310, 311 |
| NICHT VERIFIKABAR | 1 | 009 |
| KEIN REQOGNILOOM-BEZUG | 0 | — |

Zusätzliche Verdikt-Attribute auf TEILWEISE-Findings: **UEBERZOGEN** 310, 021 · **UNTERSCHAETZT**
002. Teilaspekte mit Verdikt **FALSCH**: 006 (ConfirmDialog existiert), 016 (Mechanik-Beschreibung),
021 („0 Hex"). 302/303 sind inhaltlich BESTAETIGT und nur wegen ±1 Zahlabweichung als TEILWEISE
geführt. Gezählt wurden **27** geprüfte Findings (WP-3: 16 · WP-3b: 11).

**Gesamturteil:** Die beiden Berichte sind substanziell belastbar. Die High-Findings 003/300/301
sind sauber. Die häufigsten Defekte sind **Zahlungenauigkeit** (001, 002, 300, 310) und
**Mechanik-Fehlbeschreibung** (016), nicht erfundene Sachverhalte. Ein Registereintrag (021)
überzeichnet einen korrekten Messfehler-Nachtrag als absolute Null-Aussage.

## 5. Key-Verdikte (Kurzform)

- **High bestätigt:** 003 (kein Skip-Link), 300/301 (116 Keys + Ceiling-Ratchet), 305, 320, 321.
- **High eingeschränkt:** 001 (Mechanik bestätigt, 453 nicht rekonstruierbar), 002 (Kern bestätigt, Zahl 112 falsch).
- **Präzisiert:** 016 (Code→Locale existiert; Problem ist die Obergrenze, nicht die Dimension).
- **Widerlegt im Teilaspekt:** 006 (ConfirmDialog existiert), 021 (37 Hex-Literale trotz „0").
- **Zahl überzogen:** 310 (3 statt ≥6 reproduzierbar), 311 (81 % im engeren Scan statt 93,5 %).
- **Nicht statisch prüfbar:** 009 (Rendering-Clipping).
- **Kontrollen 021/022:** 022 sauber bestätigt; 021 nur als „0 Inline-Styles / 0 Komponenten-CSS-Hex" bestätigt.

## 6. NEU-AUDIT-LUECKE (nicht im Audit erfasst bzw. falsch abgebildet)

1. **Phantom-Key im i18n-Ratchet:** `permissionMatrix.capability.` (Konkatenations-Präfix,
   `PermissionMatrixEditor.tsx:103`) zählt als fehlender Key. Die Baseline 116 ist um ≥1 zu hoch
   und der Ratchet kann diesen Präfix-Fehlalarm nie auflösen. → Der Scanner sollte
   `t("…" + …)` ausschließen oder dynamischen Keys separat behandeln.
2. **Register-Doppelzählung:** `AUD-002` (112) und `AUD-300` (116) beschreiben denselben i18n-Defekt,
   werden in §3 aber als zwei P1-Findings geführt (plus `AUD-016` als dritter Verweis). Eine
   Deduplizierung/Verweisregel fehlt.
3. **Zahl-Inkonsistenz im Register:** §3 nennt für AUD-002 „112", für AUD-300 „116" — beide „P1/High".
   Der Fehlerstand ist damit widersprüchlich dokumentiert; zusätzlich enthält die AUD-002-Zeile
   ein defektes Markdown-Backtick.
4. **„41 Dateien" nicht reproduzierbar** (tatsächlich 34 Produktionsdateien mit ≥1 fehlendem Key) —
   in beiden Reports wiederholt, ohne Scanbeleg.
5. **E2E-Selektor-Liste teils phantomhaft:** `login-form`, `main-header`, `todo-item` existieren
   in keiner Revision unter `e2e/` (Diff seit Baseline leer). Nur die drei
   `visibility-*-diagrams`-Selektoren sind nachweislich stale. Es fehlt weiterhin ein
   TID↔e2e-Drift-Wächter (bereits als AUD-318 bekannt, hier erneut belegt).
6. **Ungetestete a11y-Lücke aus AUD-005:** `ThemeManagementSection.test.tsx:232-244` erzwingt nur
   Design-System-Klassen, prüft aber **keine** accessible names der beiden Selects — genau die
   Lücke, die AUD-005 beschreibt, ist damit dauerhaft unentdeckt.
7. **`/settings`-Abdeckungsaussage unpräzise:** WP-3 §11 sagt, `/settings` habe keinen Spec;
   `workspace-settings.spec.ts` trifft die Seite über den Alias `/workspace-settings`
   (`NavigationShell.tsx:173-176` navigiert auf `/settings`), also existiert mittelbare Abdeckung.

---

*Erstellt von `frontend-reviewer` (adversariale Zweitprüfung WP-3/WP-3b). Read-only; kein
Produktcode verändert. Analyse-Hilfsskripte wurden nach Gebrauch entfernt.*
