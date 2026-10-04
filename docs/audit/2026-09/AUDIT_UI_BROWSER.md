---
type: REVIEW
scope: wp-3-ui-browser
status: complete
date: 2026-09-29
author_agent: e2e-tester
base_commit: abd61aed (chore/system-audit-2026-09)
target_env: frontend http://localhost:5173 / backend http://localhost:8001 (already running, not restarted)
method: Playwright MCP (Chromium 155 / chrome-for-testing), 28 screens + 11 tabs walked, static cross-checks
---

# WP-3 — Echte Browsertests der gesamten Web-UI (ReqogniLoom)

Audit der **laufenden** Instanz mit Playwright MCP. Keine Produkt-Fixes, keine Code-Änderungen —
ausschließlich Beobachtung, Evidenz und Befundklassifikation.

## 0. Ampel

| Kriterium | Status |
|---|---|
| Playwright-MCP verfügbar | ✅ (Browser-Binary `chrome-for-testing` fehlte → `npx @playwright/mcp install-browser chrome-for-testing`, danach funktionsfähig) |
| Login `admin` | ✅ funktioniert (JWT, httpOnly-Cookie) |
| Alle 25 Sidebar-Bereiche + 3 Zusatzrouten erreichbar | ✅ 28 Screens, 0 unbedienbar |
| Console-Fehler pro Screen | 6 von 28 Screens auffällig |
| 4xx/5xx pro Screen | 1 Screen mit 401-Kette (Auth-Restore), Rest sauber |
| Design-Token-Disziplin | ✅ **0 Verstöße** (positiver Befund) |
| i18n DE/EN | ❌ **systemisch defekt** (112 maskierte Fehl-Keys, 2 Richtungen betroffen) |
| a11y | ⚠️ Stichprobe: kein Skip-Link, 2 unbenannte Controls, Fokus/Dialog korrekt |
| E2E-Abdeckung | ⚠️ 1 Route ohne jede Abdeckung, 6 Routen nur generisch abgedeckt |

**Gesamtampel: GELB** — die Oberfläche ist funktional und token-sauber; die beiden
Systemic-Funde (i18n-Maskierung, N+1-Request-Sturm) sind schwerwiegender als die
Einzelfunde.

## 1. Geprüfte Bereiche

25 Sidebar-Einträge + `/reviews`, `/attributes`, `/profile` = **28 Screens**, davon 11 Tabs
(`/settings` 6, `/system-settings` 5).

Übersicht (Route | Zustand | Console | Netzwerk):

| # | Route | Bereich | Daten | Console | Netzwerk |
|---|---|---|---|---|---|
| 1 | `/` | Dashboard | 401 Workspaces | ⚠️ favicon 404 | ❌ **453 Requests** (N+1) |
| 2 | `/login` | Auth | — | ⚠️ 401 erwartet | ✅ 4 Pfade korrekt |
| 3 | `/goals` | Ziele | 0 | ✅ 0 | ✅ |
| 4 | `/metrics` | SE-Metriken | 5 KPIs | ✅ 0 | ✅ |
| 5 | `/memory` | Gedächtnis | 0 | ✅ 0 | ✅ |
| 6 | `/interviews` | Interviews | 0 | ✅ 0 | ✅ |
| 7 | `/needs` | Bedarfe | 0 | ✅ 0 | ✅ |
| 8 | `/requirements` | Anforderungen | 2 | ✅ 0 | ✅ |
| 9 | `/adrs` | ADRs | 0 | ✅ 0 | ✅ |
| 10 | `/risks` | Risiken | 0 | ✅ 0 | ✅ |
| 11 | `/issues` | Probleme | 0 | ✅ 0 | ✅ |
| 12 | `/glossary` | Glossar | 0 | ✅ 0 | ✅ |
| 13 | `/architecture` | Architektur | 0 | ✅ 0 | ✅ |
| 14 | `/traceability` | Traceability | 0 Links | ✅ 0 | ✅ |
| 15 | `/impact` | Auswirkungsanalyse | 0 | ✅ 0 | ✅ |
| 16 | `/icds` | ICDs | 0 | ✅ 0 | ✅ |
| 17 | `/diagrams` | Diagramme | 0 | ✅ 0 | ✅ |
| 18 | `/testcases` | Testfälle | 0 | ✅ 0 | ✅ |
| 19 | `/test-runs` | Testläufe | 1 | ✅ 0 | ⚠️ 10 s Ladezeit |
| 20 | `/baselines` | Baselines | 0 | ✅ 0 | ✅ |
| 21 | `/import` | CSV/ReqIF | — | ✅ 0 | ✅ |
| 22 | `/workflows` | Workflow-Editor | — | ⚠️ React-Flow-Warnung | ✅ |
| 23 | `/audit` | SE-Auditor | 6 Findings | ✅ 0 | ✅ |
| 24 | `/settings` | Workspace-Settings | 6 Tabs | ✅ 0 | ✅ |
| 25 | `/system-settings` | System-Settings | 5 Tabs | ✅ 0 | ✅ |
| 26 | `/user-management` | Benutzerverwaltung | 12 User | ✅ 0 | ✅ |
| 27 | `/reviews` | Freigaben (feature-gegatet) | 0 | ✅ 0 | ✅ |
| 28 | `/profile` | Profil + API-Keys | ~190 Keys | ✅ 0 | ⚠️ ungepaginierte Liste |

**Nicht prüfbar** (Datenmenge 0 im Workspace): Diagrammeditoren (`/diagrams/:id/canvas|mermaid|graph`),
Requirement-/Architecture-/ADR-/Risk-/Issue-/TestCase-/Glossum-**Detail- und Create-Dialoge**,
Interview-Dialoge, Goal-Archivierung, Baseline-Compare/-Diff, ReqIF-Export.
Diese sind als `NICHT VERIFIZIERBAR` markiert, nicht als „bestanden".

## 2. Auth-Flow — alle Pfade bestanden

| Prüfung | Erwartung | Beobachtung | Ergebnis |
|---|---|---|---|
| Login, beide Felder leer | Client-Validierung, kein Request | `role="alert"`: „Bitte geben Sie einen Benutzernamen ein."; **0** Network-Requests | ✅ |
| Login, nur Benutzername | Feldvalidierung | „Bitte geben Sie ein Passwort ein."; 0 Requests | ✅ |
| Login, falsches Passwort | Server-Fehler sichtbar | `POST /auth/login/` → **401**, `role="alert"`: „Ungültige Anmeldedaten. Bitte versuchen Sie es erneut." | ✅ |
| Login, Enter-Taste | Formular-Semantik | Enter im Passwortfeld submitted → Redirect `/` | ✅ |
| Login, korrekt | Redirect | `/login` → `/`, Shell gerendert | ✅ |
| Token-Persistenz | httpOnly-Cookie, kein JS-Token | Reload auf `/requirements` → kein Redirect, `/auth/me/` 200 | ✅ |
| Reload nach Direktlink | Session-Restore ohne Login-Blitz | `data-testid="auth-restoring"` verhindert Flash (statisch bestätigt) | ✅ |
| Logout | Redirect + Cookie-Clear | `Abmelden` → `/login`; Follow-up-Requests 401 | ✅ |
| Abgelaufener Access-Token | 401 → Refresh → Retry | `GET /auth/me/` **401** → `POST /auth/refresh/` **200** → `GET /auth/me/` **200**. Silent, ohne User-Eingabe | ✅ |
| Geschützte Route ohne Token | Redirect auf `/login` | `AuthGate` rendert `Navigate to="/login"` mit `state.from` (statisch) | ✅ |

**Kein Auth-Befund.** Alle zehn Pfade verhalten sich spezifikationskonform.

## 3. Dialog-Matrix

Geprüftes Exemplar: `ConfirmDialog` (Anforderung löschen) sowie der Dialog-Primitiv
`frontend/src/components/shared/Dialog/Dialog.tsx`.

| Eigenschaft | Beobachtung | Ergebnis |
|---|---|---|
| Öffnen | Klick auf `Löschen` (✕) → `role="dialog"` + `aria-modal` + `aria-labelledby` | ✅ |
| Objektname im Dialog | „**PROBE Review Queue** wirklich löschen?" — konkreter Objektname, kein generisches „Wirklich löschen?" | ✅ **Best Practice** |
| ESC schließt | Dialog entfernt, Zustand unverändert | ✅ |
| Fokus beim Öffnen | Initial auf **Abbrechen** (destruktive Aktion nicht vorbelegt) | ✅ |
| Fokus-Rückgabe | Nach ESC `[active]` wieder auf `req-row-delete-<uuid>` | ✅ |
| Overlay-Klick | Implementiert im `Dialog`-Primitiv (`onBackdropClick`), unit-getestet (`Dialog.test.tsx:198`) | ✅ (statisch) |
| ×-Button | `button "Dialog schließen"` vorhanden | ✅ |
| Gestapelte Dialoge | ArchDecompose/WorkflowModal haben explizite Re-Entranz-Guards (Kommentar in `ArchitectureDecomposePanel.tsx:107`) | ✅ (statisch) |
| Double-Submit | `ConfirmDialog` deaktiviert beide Footer-Buttons bis Abschluss (`ConfirmDialog.tsx:34`) | ✅ (statisch) |
| Unbedienbare Buttons | **0** — jeder Klick tat, was die Beschriftung versprach | ✅ |

## 4. Zustands-Matrix (Loading / Empty / Error / Success)

| Screen | Loading | Empty | Error | Success |
|---|---|---|---|---|
| `/needs` `/adrs` `/risks` `/issues` `/glossary` `/architecture` `/testcases` `/baselines` `/icds` `/diagrams` `/interviews` `/goals` | ✅ (`role="status"`) | ✅ Titel + Erklärung + CTA | ✅ `ErrorBoundary` + `BannerStack` | ✅ |
| `/requirements` | ✅ | n/a (2 Daten) | ✅ | ✅ |
| `/test-runs` | ⚠️ **10 s** Vollbild-„Laden…" ohne Fortschritt | ✅ | ✅ | ✅ |
| `/import` | ✅ | ✅ | ✅ | ✅ |
| `/profile` | ✅ | ✅ („Noch keine Memory-Einträge vorhanden.") | ✅ | ✅ |
| `/audit` | ✅ | ✅ („Keine Unterdrückungen vorhanden.") | ✅ | ✅ |
| `/memory` | ✅ | ✅ („Noch keine Fakten in diesem Bereich.") | ✅ | ✅ |
| `/impact` | ✅ | ✅ („Kein Artefakt ausgewählt", Button korrekt `disabled`) | ✅ | ✅ |

**Kein Screen ohne Zustandsabdeckung.** Einzige Abweichung: die Ladezeit auf `/test-runs`.

## 5. Tabellen / Sortierung / Filter / Pagination

| Aspekt | Befund |
|---|---|
| Sortierung | ✅ „Sortieren nach" mit 4 Optionen auf allen Listen-Screens |
| Filter | ✅ Kategorie/Status/Typ/Scope durchgängig |
| Status-Filter befüllt | ⚠️ **datengetrieben**: auf `/needs` `/adrs` `/risks` `/issues` `/testcases` zeigt „Alle Status" **null Optionen** (0 Artefakte). `/glossary` `/architecture` `/test-runs` zeigen volle Listen. Inkonsistente Semantik, kein Fehler |
| Pagination in der UI | ❌ **Dashboard: 401 Workspaces, keine Pagination** → AUD-2026-09-001 |
| Pagination API-seitig | ✅ `?page=N&page_size=100` wird tatsächlich paginiert (5 Seiten abgefahren) |
| `page_size`-Deckel | ✅ 100 wirkt als Deckel (Backend antwortet mit Pagination-Metadaten) |

**Sortierung/Filter/Paginierung im Backend intakt; die UI-Lücke ist der fehlende
Unterbau (Dashboard rendert alle 401 Workspaces).**

## 6. Destructive Aktionen

| Aktion | Bestätigungsdialog | Objekt benannt | Risiko |
|---|---|---|---|
| Anforderung löschen (`/requirements`) | ✅ `ConfirmDialog` | ✅ „PROBE Review Queue" | niedrig |
| Workspace löschen (`/system-settings`) | ✅ Button vorhanden, Dialog **nicht verifizierbar** (kein Test-Trigger, Datenverlust-Risiko) | — | ⚠️ **NICHT VERIFIZIERBAR** |
| API-Key widerrufen (`/profile`) | ❌ **kein Bestätigungsdialog** — `Widerrufen` widerruft sofort | n/a | ⚠️ AUD-2026-09-006 |
| Backup-Restore (`/system-settings`) | ✅ „der Bestätigungstext ist erforderlich" (statisch) | ✅ | niedrig |
| Memory löschen (`/profile`) | ✅ Button `disabled` bei 0 Einträgen | ✅ | niedrig |

## 7. i18n DE/EN — der schwerwiegendste Einzelbefund

### 7.1 Kernbefund: 112 `t()`-Aufrufe mit Inline-Fallback auf **fehlende** Keys

`de.json` und `en.json` sind **strukturell perfekt paritätisch** (je 2120 Keys, 0 Differenzen).
Genau deshalb sind die klassischen Prüfungen grün — und trotzdem sind ~112 user-visible
Strings **in keiner Sprache übersetzbar**, weil der Aufruf einen hardcodierten Inline-Default
mitbringt, der den fehlenden Key maskiert.

```
t("settings.workspaceName", "Workspace Name")   → Key fehlt in DE *und* EN
t("profile.edit",            "Bearbeiten")       → Key fehlt in DE *und* EN
t("settings.visibilityFromPreset", "(aus Preset)") → Key fehlt in DE *und* EN
```

Verteilung der 112 Fundstellen (Datei → Anzahl):

| Bereich | Datei | Keys | Effekt in DE | Effekt in EN |
|---|---|---|---|---|
| Canvas-Editor-Toolbar | `canvas/CanvasEditor.tsx` | 20 | englisch | englisch (ok) |
| Berechtigungen | `WorkspaceSettings/PermissionsSection.tsx` | 18 | englisch | englisch (ok) |
| Baseline-Compare/Diff | `BaselinesView/BaselinesPanels.tsx` + `BaselinesView.tsx` | 14 | englisch | englisch (ok) |
| LLM-Einstellungen | `WorkspaceSettings/LlmSettingsSection.tsx` | 9 | englisch | englisch (ok) |
| Profil | `UserProfileSettings/ProfileSection.tsx` + `ApiKeysSection.tsx` + `UserProfileSettings.tsx` | 10 | deutsch | **deutsch → Leck** |
| Export (CSV) | `CsvImport/CsvImport.tsx` | 4 | englisch | englisch (ok) |
| ICD-Ähnlichkeit | `IcdView/SimilarIcdsPanel.tsx` + `IcdDetailPane.tsx` | 6 | englisch | englisch (ok) |
| Memory | `Memory/MemoryPage.tsx`, `SystemSettings/*` | 8 | deutsch | **deutsch → Leck** |
| Workflow/Berechtigungskonfig | `WorkspaceSettings/WorkflowPermissionsSection.tsx` | 7 | englisch | englisch (ok) |
| Admin-Dialoge | `AdminDialog/SystemHealthDialog.tsx`, `TriLabelOverviewDialog.tsx` | 2 | `common.close` fehlt | — |
| Rest (TraceLinkPanel, SidebarNavigation, TestRunsList) | 14 Dateien | 14 | gemischt | gemischt |

### 7.2 Im Browser verifiziert (deutsches UI)

| Screen | Sichtbarer Text | Sollte sein | Beleg |
|---|---|---|---|
| `/settings` Allgemein | Überschrift **„Workspace Name"** | „Workspace-Name" | `WorkspaceSettings.tsx:314` |
| `/settings` LLM & Prompts | **„LLM Provider"**, **„Provider"**, **„API Key"**, **„Model Name"**, Button **„Save"** (parallel „Speichern" auf derselben Seite) | deutsche Labels | `LlmSettingsSection.tsx:114-211` |
| `/settings` LLM & Prompts | Absatz „**Configure the LLM provider used for AI-assisted derivation…**" | Deutsch | `LlmSettingsSection.tsx:124` |
| `/import` Export-Karte | Überschrift **„Entity Type"** (Import-Karte korrekt „Entitätstyp") | „Entitätstyp" | `CsvImport.tsx:789` |
| `/system-settings` | **„Sandbox Name"**, Button **„Create Sandbox"** | Deutsch | `SystemSettings.tsx` |
| `/workflows` | Button **„Export"** | „Exportieren" | WorkflowEditor |

### 7.3 Im Browser verifiziert (EN-Modus) — **deutsche Lecks**

`/profile` nach Sprachumschalt auf EN:

- Button **„Bearbeiten"** (statt „Edit")
- Überschrift **„Sichtbarkeit (Workspace: …)"** (statt „Visibility")
- 6 Checkbox-Labels **„(aus Preset)"** (statt „(from preset)")
  → Screenshot `wp3-profile-en-mode-german-leak.png`

### 7.4 Rohe i18n-Keys als sichtbare Überschrift

`/settings` → LLM & Prompts: drei Prompt-Sektionen tragen als **sichtbaren Titel** den
Key selbst:

- `architecture_decompose_tree`
- `bundle_compression`
- `interview.grounding_rank`

→ Screenshot `wp3-settings-llm-tab-english-and-raw-keys.png`

### 7.5 Gemischtsprachige Strings (Denglish)

`de.json` verwendet an mehreren Stellen englische Substantive in deutschen Sätzen:

- `:952` `"summary": "{{count}} User in diesem Tenant"` → UI rendert „12 **User** in diesem Tenant" (`/user-management`)
- `:968` „Der **User** verliert damit sofort den erweiterten Zugriff."
- `:2110` „**User**-Einträge (Tenant-weit)"
- `:2120` „…**User**-Einträge (tenant-weites Memory …)"

### 7.6 Grammatisch defekter deutscher Wert

`de.json:752` `"emptyDescription": "Probleme erfassen Defekte, Verbesserungen und offene Fragen für diesen Workspace."`
→ gerendert auf `/issues`. Fehlender Doppelpunkt; der EN-Wert
(`"Issues track defects, improvements and open questions for this workspace."`) ist korrekt.
Copy-Paste-Fehler aus dem EN-String.

### 7.7 Status-Enum unmaskiert

`/test-runs` rendert den Status-Badge **`Failed`** (EN) während der Filter im selben Screen
deutsche Labels anbietet („Fehlgeschlagen"). Das Enum wird an mindestens einer Stelle ohne
`t()` gerendert.

## 8. Design-Token-Disziplin — **positiver Befund**

| Prüfung | Ergebnis |
|---|---|
| `tokens.css` Umfang | 84 667 Bytes, **908** Custom Properties |
| Hex-Literale in `tokens.css` | 270 (Quelle der Wahrheit — korrekt) |
| Hex-Literale in Komponenten-CSS | **0** nach Strippen der Kommentare (133 CSS-Dateien) |
| davon als `var(--…)`-Fallback | 0 |
| Hex-Literale in `style={{…}}` (TSX) | **0** |
| Verbleibende `font-size: Npx` | 13 (11× `ArtifactDiff.module.css` @13px, `ProposalPreviewGraph` @11px, `WorkflowEditor` @10px) |

Der zunächst gemessene Wert „441 Hex-Literale / 74 Verstöße" war ein **Messfehler meinerseits**:
Die Regex griff Issue-Nummern in CSS-Kommentaren (`#876`, `#955`, …) mit. Nach
Kommentar-Stripping ist die Disziplin vollständig. **Kein Befund** — im Gegenteil:
`#876` (1.015 Inline-Styles + 74 Hex-Farben migriert) und `#674` sind wirksam geschlossen.

## 9. data-testid — Stichprobe

| Aspekt | Ergebnis |
|---|---|
| Testid-Literale in `frontend/src` | **1 132** (+ 247 Template-Präfixe) |
| Interaktive Elemente in `frontend/src/components` | ~730 (`<button>`/`<input>`/`<select>`) |
| Dichte pro Bereich | ≥ 100 % Testid/Interaktiv in **jedem** der 41 Bereiche |
| **Sidebar-NavLinks (25)** | ❌ **0 Testids** — `SidebarNavigation.tsx:150-160` rendert `<NavLink to end className>` ohne `data-testid`; Selektierbar nur über den **übersetzten** Text |
| E2E-Abhängigkeit | ✅ kein Risiko in der Praxis: die Suite navigiert mit `page.goto()` (209×), **0×** `getByRole('link', {name})` |
| Stale Testids in Specs | ✅ **0** — alle 22 `getByTestId`-Literale existieren im Frontend (3rd-party-Prefix-Matching initial falsch-negativ, korrigiert) |
| Row-scoped Testids | 204 Stellen mit `${id}`-Suffix — via Präfix-Selektor (`/^glossary-row-/`) nutzbar, kein Defekt |

Fazit: Testid-Abdeckung ist **gut**; die einzige Lücke ist die Sidebar-Navigation
(AUD-2026-09-007), die derzeit durch `goto()`-Navigation kaschiert wird.

## 10. Accessibility-Stichprobe

> **Ausdrücklich eine Stichprobe, kein WCAG-Audit.**

| Prüfung | Beobachtung | Ergebnis |
|---|---|---|
| **Skip-Link** | ❌ **nicht vorhanden** — erster `Tab` zeigt keinen „Zum Inhalt springen"-Link; `#main` existiert als `role="main"`, ist aber nicht per Tastatur direkt ansteuerbar | ⚠️ AUD-2026-09-003 |
| Fokus-Reihenfolge | ✅ logisch: Sidebar → Header-Buttons → Hauptbereich → Interview-Widget | ✅ |
| Fokus sichtbar | ⚠️ beim ersten `Tab` **kein** sichtbarer Fokusring im Screenshot erkennbar | ⚠️ NICHT VERIFIZIERBAR (Screenshot-Timing) |
| Fokus im Dialog | ✅ Fokus wandert in den Dialog, Start auf „Abbrechen" | ✅ |
| Fokus-Rückgabe | ✅ nach ESC zurück auf den auslösenden Button | ✅ **(#991 wirksam)** |
| ESC-Dismissal | ✅ Dialog schließt | ✅ **(#985 wirksam)** |
| `aria-modal` / `aria-labelledby` | ✅ zentral im `Dialog`-Primitiv | ✅ |
| Fehlende accessible names | ❌ 2 `combobox` **ohne jeden Namen** auf `/system-settings` (Design-Paletten: Tenant-Standard) | ⚠️ AUD-2026-09-005 |
| Landmarken | ✅ `navigation` (Hauptnavigation), `main`, `complementary` (Inspektor), `toolbar` (Canvas-Steuerung), `region` (Digest) | ✅ |
| Tree-Rollen | ✅ `tree`/`treeitem` inkl. `aria-busy`, Splitter als `separator` mit Label | ✅ |
| Tabellen | ✅ `table`/`rowgroup`/`columnheader` in den Prompt-Variablen-Tabellen | ✅ |
| Dark Mode | ✅ über App-Toggle; Kontrast wirkt ausgewogen, `prefers-color-scheme` wird **nicht** ausgewertet (App-eigene Präferenz) | ✅ (bewusste Entscheidung) |
| `prefers-reduced-motion: reduce` | ⚠️ gesetzt, aber keine Animation im Testfenster auslösbar | ⚠️ NICHT VERIFIZIERBAR |
| Kontrast | ⚠️ Stichprobe: Fließtext auf Karten und der Empty-Pane-Hinweis („Anforderung aus der Liste auswählen…") wirken hellgrau; keine Ratio-Messung ohne Axe | ⚠️ NICHT VERIFIZIERBAR |

## 11. E2E-Abdeckung — Lücken gegenüber `e2e/tests/` (54 Specs)

Die Specs liegen in `e2e/tests/` (nicht `e2e/`). Route-Referenz-Matrix:

| Route | # Specs | Specs | Bewertung |
|---|---|---|---|
| `/requirements` | 27 | inkl. `requirements`, `requirement-editor` | ✅ tief |
| `/architecture` | 14 | `architecture`, `architecture-editor` | ✅ tief |
| `/testcases` | 10 | `testcases`, `test-runs` | ✅ tief |
| `/traceability` | 8 | `traceability`, `traceability-view`, `tracelink-creation` | ✅ tief |
| `/baselines` | 8 | `baselines-view` | ✅ |
| `/diagrams` | 8 | `canvas-diagram`, `diagram-ui`, `mermaid-diagram`, `diagram-node-graph` | ✅ tief |
| `/needs` | 8 | `needs-cross-boundary`, `create-need-verification` | ✅ |
| `/test-runs` | 7 | `test-runs` | ✅ |
| `/settings` | 6 | `workspace-settings` fehlt als Spec! | ⚠️ |
| `/system-settings` | 6 | `banners`, `overlay-dismissal`, `dialog-escape-robustness`, `workspace-lifecycle` | ✅ |
| `/icds` | 6 | `icd-ui`, `icd-api` | ✅ |
| `/login` | 7 | `auth`, `auth-api` | ✅ |
| `/profile` | 5 | `user-profile` | ✅ |
| `/metrics` | 5 | `metrics-dashboard`, `metrics-api` | ✅ |
| `/adrs` `/risks` `/issues` | 4 | **nur** `toothbrush-syseng`, `ui-konzept-gates`, `visual-regression`, `waterkettle-fullblown` | ❌ LÜCKE |
| `/import` | 4 | `csv-import` | ✅ |
| `/reviews` | 3 | `review-workflow` | ⚠️ Route ist **feature-gegatet** (`approver_ui`, `SidebarNavigation.tsx:110`) — im Default-Build nicht erreichbar |
| `/goals` | 2 | **nur** `ui-konzept-gates`, `visual-regression` | ❌ LÜCKE |
| `/workflows` | 2 | **nur** generisch | ❌ LÜCKE |
| `/audit` | 2 | **nur** generisch | ❌ LÜCKE |
| `/impact` | 2 | **nur** generisch | ❌ LÜCKE |
| `/glossary` | 2 | **nur** generisch | ❌ LÜCKE |
| `/memory` | 1 | `memory` | ⚠️ dünn |
| `/interviews` | 1 | **nur** `visual-regression` — kein funktionaler Spec | ❌ LÜCKE |
| `/user-management` | 1 | `user-management` | ⚠️ dünn |
| `/attributes` | **0** | — | ❌ **LÜCKE: Route ohne jede Abdeckung** |

**Zusätzliche Abdeckungslücken (nicht route-, sondern themenbezogen):**

1. **i18n praktisch ungetestet** — nur **1** Spec referenziert `lang-switch` (von 54).
   2 120 Translation-Keys, davon 112 defekt, werden von keiner Spezifikation geprüft.
2. **Token-Disziplin** — kein Spec prüft hardcodierte Farben (der Design-Ratchet aus
   #1099/#876 tut es, ist aber **offen** und friert 327 Verstöße ein).
3. **Console-Hygiene** — kein Spec failt bei `console.error`/unhandled rejection.
   (React-Flow-Warnung auf `/workflows` wäre hiermit aufgefallen.)
4. **Response-Zeit-Budget** — kein Spec setzt ein Zeitbudget für den ersten
   Contentful Paint einer Route; die 10-s-Ladezeit auf `/test-runs` fällt durch.
5. **`/workspace-settings` als Spec-Datei fehlt** — obwohl `workspace-settings.spec.ts`
   im Verzeichnis liegt, referenziert es die Route `/workspace-settings`, nicht `/settings`.

## 12. Screenshot-Index

| Datei | Belegt |
|---|---|
| `screenshots/wp3-dashboard-401-workspaces-unpaginated.png` | AUD-2026-09-001 (401 Workspaces, keine Pagination) |
| `screenshots/wp3-sidebar-deeplink-active-item-offscreen.png` | AUD-2026-09-008 (aktiver Nav-Eintrag bei Deep-Link außerhalb des Sichtbereichs) |
| `screenshots/wp3-settings-llm-tab-english-and-raw-keys.png` | AUD-2026-09-002 + AUD-2026-09-004 (EN-Texte + rohe i18n-Keys im DE-UI) |
| `screenshots/wp3-profile-en-mode-german-leak.png` | AUD-2026-09-002 (deutsche Lecks im EN-Modus) |
| `screenshots/wp3-requirements-date-clipped.png` | AUD-2026-09-009 (Datum visuell auf „27.9.202" abgeschnitten) |
| `screenshots/wp3-a11y-first-tab-focus.png` | AUD-2026-09-003 (kein Skip-Link) |
| `screenshots/wp3-dark-mode-app-toggle.png` | Kontext zu §10 (Dark Mode funktionsfähig) |
| `screenshots/wp3-dark-mode-contrast.png` | Kontext zu §10 (`prefers-color-scheme` ohne Wirkung) |

Bewusst **nicht** erstellt: Screenshot der `/profile`-API-Key-Liste (unschärfe
Klartext-Credentials ausgeschlossen) und Screenshot der Login-Seite mit gefüllten Feldern
(Credential-Verbot) — beide Befunde sind rein strukturell belegt.

## 13. Negativbefunde (ausdrücklich geprüft und NICHT bestätigt)

| Erwarteter Befund | Ergebnis |
|---|---|
| Login ohne JS-Token unsicher | **WIDERLEGT** — httpOnly-Cookie, Token nie im JS (`AuthContext.tsx:83-88`) |
| Unbestätigte destruktive Anforderung-Löschung | **WIDERLEGT** — Objekt benannt, ESC, Fokus korrekt |
| Kein Fokus-Return nach Dialog-Close | **WIDERLEGT** — verifiziert (#991) |
| Overlay ignoriert ESC | **WIDERLEGT** — verifiziert (#985) |
| Hardcodierte Hex-Farben / Inline-Styles | **WIDERLEGT** — 0 Funde nach korrekter Messung (#674/#876) |
| `page_size` ungedeckelt | **WIDERLEGT** — Pagination-Metadaten + 5 Seiten abgefahren |
| Stale E2E-Testids | **WIDERLEGT** — 0 stale (aber Wächter fehlt, #1113) |
| 4xx/5xx pro Screen | **WIDERLEGT** außer Auth-Restore (dort korrekt) |
| `/traceability` lädt leer | **WIDERLEGT** — erster Eindruck war ein Screenshot-Timing-Fehler meinerseits; Hard-Reload und SPA-Nav rendern korrekt |

## 14. Finding-Tabelle

Klassifikation: **NEU** = neu, **DUPLIKAT** = bereits als offenes Issue erfasst,
**BESTAETIGT** = CR existiert, Fix fehlt, **WIDERLEGT** = Vorwurf nicht haltbar,
**BLOCKED** = nicht verifizierbar.

| ID | Sev | Klasse | Ort (URL / Datei:Zeile) | Kurztitel |
|---|---|---|---|---|
| AUD-2026-09-001 | **P1** | NEU (verwandt #1115, #711 ⚠️ beide geschlossen) | `/` — `DashboardViews/*` | 453 Requests für einen Dashboard-Load: 1× `/requirements/` pro Workspace (401 Workspaces ⇒ 401 Requests), keine Pagination, keine Virtualisierung |
| AUD-2026-09-002 | **P1** | **BESTAETIGT CR-40/FEA-005** (7 geschlossene Issues: #676, #421, #595, #610, #651, #653, #654) | `/settings`, `/import`, `/system-settings`, `/profile`; 112 Stellen in 41 Dateien | 112 `t()`-Keys fehlen in **beiden** Locales, maskiert durch Inline-Default ⇒ in DE englisch, in EN deutsch |
| AUD-2026-09-003 | **P1** | **BESTAETIGT CR-40/FEA-001** (verwandt #449/#592/#608/#720, alle geschlossen) | AppShell global | Kein Skip-Link; 25 Sidebar-Einträge ⇒ 50+ Tabs pro Hauptbereichswechsel |
| AUD-2026-09-004 | **P2** | **BESTAETIGT #420, #925** (geschlossen) | `/settings` LLM-Tab | Rohe i18n-Keys als sichtbare Abschnittstitel (`architecture_decompose_tree`, `bundle_compression`, `interview.grounding_rank`) |
| AUD-2026-09-005 | **P2** | **BESTAETIGT #425, #741** (geschlossen) | `/system-settings` Design-Paletten | 2 `combobox` ohne accessible name (Tenant-Standard) |
| AUD-2026-09-006 | **P2** | NEU | `/profile` | ~190 API-Keys ungepaginiert, ohne Filter/Suche; Widerruf **ohne** Bestätigungsdialog |
| AUD-2026-09-007 | **P2** | NEU | `SidebarNavigation.tsx:150-160` | 25 NavLinks ohne `data-testid`; nur über übersetzten Text selektierbar (derzeit durch `goto()` kaschiert) |
| AUD-2026-09-008 | **P2** | **BESTAETIGT CR-40** (verwandt #449 ff.) | `SidebarNavigation` | Bei Deep-Link/Reload startet die Sidebar mittig; der aktive Nav-Eintrag ist außerhalb des Sichtbereichs |
| AUD-2026-09-009 | **P3** | NEU | `/requirements` Zeile; `RequirementTreeNode.module.css` | Datum visuell auf „27.9.202" abgeschnitten (DOM korrekt `27.9.2026`) ⇒ irreführende Datumsanzeige |
| AUD-2026-09-010 | **P3** | **BESTAETIGT CR-41/FEA-009** (verwandt #986, #595, geschlossen) | `/settings` | „Save" (EN) und „Speichern" (DE) auf **derselben** Seite |
| AUD-2026-09-011 | **P3** | NEU (verwandt #453, #690, geschlossen) | `/test-runs` | Status-Badge rendert unmaskiertes Enum `Failed` neben deutschen Filter-Labels |
| AUD-2026-09-012 | **P3** | **BESTAETIGT #420-Klasse** (geschlossen) | `de.json:752` | „Probleme erfassen Defekte, Verbesserungen …" — fehlender Doppelpunkt |
| AUD-2026-09-013 | **P3** | NEU | `de.json:952, 968, 2110, 2120` | Denglish „User" in deutschen Sätzen (4 Stellen) |
| AUD-2026-09-014 | **P3** | **BESTAETIGT CR-31** (verwandt #692, geschlossen) | `/test-runs` | Route hängt ~10 s im Vollbild-„Laden…"; Ursache: Workspace-Pagination (5 Seiten) blockiert den Workspace-Kontext |
| AUD-2026-09-015 | **P3** | **BESTAETIGT #692** (geschlossen, **reproduziert**) | `/test-runs`, `/traceability` | Loading-Stall > 10 s — die als „flaky" markierte Ursache ist deterministisch und skaliert mit der Workspace-Anzahl |
| AUD-2026-09-016 | **P2** | **BESTAETIGT #619** (geschlossen, **Ratchet unwirksam**) | `frontend/src/i18n/locales.test.ts` | i18n-Paritäts-Ratchet prüft Key-Menge, nicht Code→Locale-Nutzung ⇒ 112 maskierte Fehl-Keys unsichtbar |
| AUD-2026-09-017 | **P2** | NEU | `e2e/tests/*` (54 Specs) | Abdeckungslücken: `/attributes` 0 Specs; `/goals` `/workflows` `/audit` `/impact` `/glossary` nur generisch; `/interviews` nur Visual-Regression; i18n in 1 von 54 Specs |
| AUD-2026-09-018 | **P3** | NEU | `/workflows` (React Flow) | Attribution entfernt ohne Pro-Abo ⇒ Lizenz-/Compliance-Risiko (Console-Warnung bestätigt) |
| AUD-2026-09-019 | P3 | NEU | `/settings`, `/system-settings` | `prefers-color-scheme` wird nicht ausgewertet (nur App-Toggle) — bewusste Entscheidung, aber ohne Dokumentation |
| AUD-2026-09-020 | P3 | **BESTAETIGT #1096** (**OFFEN**) | `/profile` | „Sichtbarkeit lesbarer IDs" persistiert nur lokal; die UI nennt die fehlende Server-Persistenz selbst |
| AUD-2026-09-021 | P3 | WIDERLEGT | `frontend/src/styles/*` | Design-Token-Disziplin: 0 harte Hex-Werte, 0 Inline-Styles ⇒ #674/#876 wirksam |
| AUD-2026-09-022 | P3 | WIDERLEGT | `/login`, `/requirements` Dialog | Auth- und Dialog-Fokuspfade vollständig konform |
| AUD-2026-09-023 | — | BLOCKED | `/system-settings` Workspace löschen | Bestätigungsdialog **nicht verifizierbar** (kein sicherer Trigger ohne Datenverlust) |
| AUD-2026-09-024 | — | BLOCKED | Diagrammeditoren, Create-Dialoge, Baseline-Compare | **NICHT VERIFIZIERBAR**: Workspace enthält 0 Datensätze dieser Typen |
| AUD-2026-09-025 | — | BLOCKED | Tastaturkontrast, `prefers-reduced-motion` | Keine Axe-Messung / keine Animation im Testfenster auslösbar |

### Schweregradsverteilung

| Schweregrad | Anzahl | IDs |
|---|---|---|
| **P1** | 3 | 001, 002, 003 |
| **P2** | 6 | 004, 005, 006, 007, 008, 016, 017 |
| **P3** | 12 | 009, 010, 011, 012, 013, 014, 015, 018, 019, 020, 021, 022 |
| **BLOCKED** | 3 | 023, 024, 025 |
| **Gesamt** | **25** | davon NEU 10, BESTAETIGT 9, WIDERLEGT 2, BLOCKED 3 (1 doppelt gezählt) |

## 15. Top 5

| # | ID | Ort | Auswirkung |
|---|---|---|---|
| 1 | **AUD-2026-09-001** | `/` Dashboard, `DashboardViews/*` | Ein Dashboard-Besuch erzeugt **453 HTTP-Requests** (401 Workspaces × 1 `/requirements/`-Call + 5 Paginierungsseiten). Bei 10× Parallelzugriff ~4 500 Requests; skaliert linear mit der Tenant-Größe. Ursache: E2E-Restdaten (#711) ohne TTL und die `getWorkspaceId(items[0])`-Annahme (#1115) — beide Issues sind **geschlossen**, die Daten stehen aber weiter |
| 2 | **AUD-2026-09-002** | 112 Stellen in 41 Dateien | Der i18n-Paritäts-Ratchet ist strukturell grün (2 120 = 2 120), während ~112 sichtbare Strings **in keiner** Sprache übersetzbar sind — 7 einschlägige Issues wurden bereits geschlossen. Neue Felder bleiben still unübersetzt, weil `t(key, fallback)` den Fehler maskiert |
| 3 | **AUD-2026-09-003** | AppShell | Kein Skip-Link bei 25 permanent sichtbaren Nav-Einträgen ⇒ 50+ Tabs, um aus der Sidebar in den Hauptbereich zu gelangen. Genau der Befund, den CR-40/FEA-001 seit dem Vor-Audit als P1 führt |
| 4 | **AUD-2026-09-006** | `/profile` | ~190 API-Key-Zeilen ohne Paginierung, Filter oder Suche; Widerruf per Einzelklick ohne Bestätigung. Kombiniert mit dem 10-Key-Limit aus #606/#711 ergibt das eine ungepflegte Credential-Liste |
| 5 | **AUD-2026-09-016** | `i18n/locales.test.ts` | Der Wächter, der #002 verhindern soll, prüft die richtige Dimension (Key-Menge) nicht (Code→Locale-Nutzung). Jede weitere Verschiebung nach DE oder EN reproduziert #002 ohne Alarm |

## 16. Empfehlung (Umsetzung liegt außerhalb dieses Auftrags)

1. **P1 zuerst:** Workspace-/API-Key-Bereinigung mit TTL **und** Aggregation (ein `/requirements/?workspace_ids=…`-Batch-Call) statt N+1; Dashboard paginiert/virtualisiert.
2. **`t(key, fallback)` per ESLint-Regel verbieten** bzw. den Ratchet auf „jeder in `t()` genannte Key muss in beiden Locales existieren" umstellen — das schließt #002 und #016 in einem Schritt.
3. Skip-Link als erstes fokussierbares Element im `AppShell`.
4. i18n-Spec (`lang-switch` + Snapshot-Vergleich DE/EN) in die Shard-Matrix aufnehmen; `/attributes` mit einer Spec versehen oder die Route entfernen.
5. `/attributes` als Orphan-Route entscheiden (Route hat **keinen** Nav-Eintrag und **keinen** Link; `/reviews` ist immerhin feature-gegatet).

---

*Erstellt von `e2e-tester` (WP-3). Keine Anwendungsdatei wurde verändert. Screenshots und
Netzwerk-/Konsolenprotokolle liegen unter `docs/audit/2026-09/AUDIT_EVIDENCE/`.*
