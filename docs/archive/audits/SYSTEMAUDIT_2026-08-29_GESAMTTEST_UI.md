# Systemaudit 2026-08-29 — Gesamttest UI (Frontend, `localhost:5173`)

> Letzter Teil des Gesamtaudits ("die gesamte UI überprüfen"), nachgelagert zu
> `docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_MCP.md` und
> `docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_REST.md`. Live-Test gegen den
> laufenden Dev-Stack (Frontend `localhost:5173`, Backend `localhost:8001`),
> Branch `fix/systemaudit-p7-backend-konsistenz`. Fokus: visuelle/funktionale
> Sichtprüfung aller Haupt-Routen mit Vertiefung der in AP-3/AP-5 stark
> veränderten Bereiche (TestRun-Grid, CSV-Import-UX, Risk-Matrix,
> ADR-Supersede, ConfirmDialoge, Theme-Konsistenz, Tastaturbedienbarkeit).

## Testmethode

- Browser-Automation via **Playwright direkt scriptbar** (Chromium headless,
  `e2e/node_modules/@playwright/test`, Version 1.61.1) — die im
  `E2E-Tester`-Rollenprofil vorgesehenen `browser_*`-MCP-Tools waren in dieser
  Umgebung nicht als Funktionswerkzeuge verfügbar; stattdessen wurden
  eigenständige Node-Skripte gegen die echte Anwendung gefahren (kein Mock,
  keine Stubs — konsistent mit dem E2E-Scope).
- Login als `admin`/`admin12345` (Standard-Demo-Credentials aus
  `e2e/helpers/auth.ts`) auf dem seedierten Demo-Tenant.
- Aktiver Workspace zum Testzeitpunkt: `smoke-trace-baseline`
  (`6d20f0b9-...`), Extended-Rigor-Preset — enthält bereits 2 Requirements
  (`parent req`/`child req`) aus früheren Sitzungen.
- Test-Artefakte mit Namenspräfix `E2E Audit *` / `E2EAuditRun-*` /
  `e2eaudituser*` angelegt, um sie eindeutig identifizieren und aufräumen zu
  können.
- Scratch-Skripte (nicht Teil des Repos, in einem temporären
  Session-Scratchpad): `audit-part1-routes.js`, `part2a-testrun*.js`,
  `part2b-csvimport.js`, `part2c-risk.js`, `part2d-adr-supersede*.js`,
  `part2e-confirmdialogs*.js`, `part2f-themes.js`, `part2g-keyboard*.js`,
  `verify-*.js`, `cleanup.js`. Screenshots (88 PNGs) liegen im selben
  Scratchpad unter `.../scratchpad/screenshots/`.

## Aufräumen (Cleanup)

Am Ende der Sitzung erfolgreich über die UI entfernt (mit korrekten
ConfirmDialogen, siehe Befunde unten):

- 4 TestCases (`E2E Audit TestCase 1` ×3, `E2EAuditRun-...-TC` ×1) — gelöscht.
- 2 ADRs (`E2E Audit ADR OLD`, `E2E Audit ADR NEW`) — gelöscht (kaskadiert
  vermutlich auch die zugehörigen, per UI nicht löschbaren Trace-Links, siehe
  Befund 1).
- 1 Risk (`E2E Audit Risk 1`) — gelöscht.
- 1 Custom-Field (`E2E Audit Field`) — angelegt und wieder gelöscht.
- 1 Test-User (`e2eaudituser<timestamp>`) — angelegt und deaktiviert
  (Soft-Delete-Äquivalent; UserManagement kennt keine Hard-Delete-Aktion).
- Custom-Theme-Import ist an der Validierung gescheitert (siehe „Nicht
  abschließend testbar"), daher wurde nichts angelegt, das aufzuräumen wäre.

**Nicht entfernbar (kein Bug, sondern fehlende UI-Aktion):** 4 TestRuns
(`E2E Audit TestRun 1` ×3, `E2EAuditRun-<timestamp>` ×1) bleiben bestehen —
`TestRunsList`/`TestRunDetailEditor` bieten keine Lösch-Aktion für TestRuns
(nur Erstellen/Schließen), was für ein Audit-Trail von Testausführungen ein
bewusstes Design sein dürfte. Für einen sauberen Zustand müsste ein Mensch mit
DB-/Admin-Zugriff nachfassen.

**Nicht in dieser Sitzung verursacht, aber auffällig:** Der Dashboard zeigt
86 Workspaces und die Benutzerverwaltung 17 User, überwiegend erkennbar aus
früheren Test-/Audit-Sitzungen (`smoke-*`, `REST-Audit-*`, `audit-viewer-*`,
`e2e-user-*`, `mcp_audit_viewer_*`). Das ist außerhalb des Scopes dieses
Berichts, wird hier aber als allgemeiner Datenhygiene-Hinweis für die
Orchestrierung vermerkt.

## Abdeckung — Routen-Sweep (25 Routen)

Alle Routen einzeln besucht (volle Seitennavigation), Konsole auf
Fehler/Warnungen geprüft, Volltext-Screenshot erstellt, auf rohe i18n-Keys
(z. B. `settings.foo.bar` statt echtem Text) geprüft.

| Route | Status | Konsolenfehler | Rohe i18n-Keys | Screenshot |
|---|---|---|---|---|
| `/` (Dashboard) | Bug gefunden (Befund 2) | 0 | 0 | `screenshots/route_root.png` |
| `/needs` | OK | 0 | 0 | `screenshots/route_needs.png` |
| `/requirements` | OK | 0 | 0 | `screenshots/route_requirements.png` |
| `/architecture` | OK | 0 | 0 | `screenshots/route_architecture.png` |
| `/traceability` | OK | 0 | 0 | `screenshots/route_traceability.png` |
| `/impact` | OK | 0 | 0 | `screenshots/route_impact.png` |
| `/baselines` | OK | 0 | 0 | `screenshots/route_baselines.png` |
| `/reviews` | OK | 0 | 0 | `screenshots/route_reviews.png` |
| `/adrs` | OK | 0 | 0 | `screenshots/route_adrs.png` |
| `/risks` | OK | 0 | 0 | `screenshots/route_risks.png` |
| `/issues` | OK | 0 | 0 | `screenshots/route_issues.png` |
| `/testcases` | OK | 0 | 0 | `screenshots/route_testcases.png` |
| `/test-runs` | OK | 0 | 0 | `screenshots/route_test-runs.png` |
| `/import` | OK | 0 | 0 | `screenshots/route_import.png` |
| `/icds` | OK | 0 | 0 | `screenshots/route_icds.png` |
| `/glossary` | OK | 0 | 0 | `screenshots/route_glossary.png` |
| `/settings` | OK | 0 | 0 | `screenshots/route_settings.png` |
| `/profile` | OK | 0 | 0 | `screenshots/route_profile.png` |
| `/system-settings` | OK | 0 | 0 | `screenshots/route_system-settings.png` |
| `/user-management` | OK | 0 | 0 | `screenshots/route_user-management.png` |
| `/audit` | OK | 0 | 0 | `screenshots/route_audit.png` |
| `/metrics` | OK | 0 | 0 | `screenshots/route_metrics.png` |
| `/goals` | OK | 0 | 0 | `screenshots/route_goals.png` |
| `/interviews` | OK | 0 | 0 | `screenshots/route_interviews.png` |
| `/workflows` | OK | 0 | 0 | `screenshots/route_workflows.png` |

Anmerkung zur Konsolen-Spalte: Der Routen-Sweep selbst zeigte 0 Fehler pro
Route, weil die 401-Lawine aus Befund 3 ausschließlich in den ersten 1–2
Sekunden **direkt nach dem Login** auftritt (durch den zeitlichen Reset des
Konsolen-Puffers pro Route im Sweep-Skript nicht der jeweiligen Route
zugeordnet) — siehe Befund 3 für den isolierten, reproduzierten Nachweis.

Workspace-Settings-Unterseiten (Tabs `general`/`traceability`/
`visibility`/`llm`/`workflows-permissions`) wurden über `/settings`
mitgeprüft (Tab-Wechsel, Custom-Fields-Sektion, Theme-Picker — siehe
Befunde/Vertiefungen unten).

## Befunde

### HIGH — Trace-Link-Löschung über die geteilte `TraceLinkPanel`-Komponente vollständig defekt (kein Confirm, kein Erfolg)

Betroffen: `ADR`-, `Architecture`-, `Issue`-, `Needs`- und `Risk`-Editoren
(alle nutzen `frontend/src/components/shared/TraceLinkPanel.tsx`).

- **Kein ConfirmDialog:** Klick auf den „×"-Löschbutton
  (`trace-link-delete-{id}`, Zeile 182) ruft `handleDelete()`
  (Zeile 114–123) **direkt** auf — keine Bestätigung, kein
  `<ConfirmDialog>`-Import überhaupt in der Datei. Damit ist dieses Muster
  inkonsistent zu praktisch jeder anderen destruktiven Aktion im UI (User
  deaktivieren, Custom-Field löschen, ADR/Risk/TestCase löschen, Theme
  löschen — alle korrekt mit ConfirmDialog gegated, siehe „OK"-Abschnitt).
- **Löschung schlägt zusätzlich technisch fehl:** In 2 unabhängigen
  Reproduktionen (ein manuell über den Trace-Link-Dialog erstellter
  `derives-from`-Link zwischen `parent req` und einer ADR, sowie ein von der
  ADR-Supersede-Aktion automatisch erzeugter `Decision`-Link) lieferte der
  Löschversuch einen rohen, unübersetzten Fehlertext direkt im UI:
  `TraceLink <uuid> not found` — die Link-Anzahl blieb vor und nach dem Klick
  identisch, der Link wurde **nicht** entfernt.
- **Vergleich:** `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx`
  (exklusiv für den Requirements-Editor) importiert `ConfirmDialog` (Zeile 43)
  und verwendet es korrekt vor dem Löschen (ab Zeile 903) — der Fix für
  „Confirm vor Trace-Link-Löschung" existiert also bereits im Code, wurde
  aber nie auf die geteilte Komponente zurückportiert, die von 5 der 6
  Editoren verwendet wird.

**Screenshots:** `screenshots/deepdive_tracelink_before_delete.png`,
`screenshots/deepdive_tracelink_after_delete.png`,
`screenshots/deepdive_tracelink_normal_after_delete.png` (zeigt den Fehler
`TraceLink f78565cd-... not found`).

**Dateien:** `frontend/src/components/shared/TraceLinkPanel.tsx:114-123,182`
vs. `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx:43,903`.

**Schweregrad:** HIGH — Kernfunktion (Trace-Link entfernen) in 5 von 6
Artefakt-Editoren nicht nutzbar; zusätzlich fehlendes Bedienschutz-Pattern.
Root Cause der 404 nicht abschließend verifiziert (vermutlich ein
ID-Mismatch zwischen der von `listForArtifact()` gelieferten und der vom
Backend beim `DELETE` erwarteten ID — Empfehlung: `backend`-seitig prüfen,
ob der `artifact_id`-gefilterte List-Endpunkt evtl. synthetische/reverse
Einträge mit abweichender ID zurückgibt).

### HIGH — Dashboard-Workspace-Karten: Name überlappt mit Preset-Badge (Regression)

Auf der Haupt-Landingpage (`/`) überlappt bei einem Großteil der
Workspace-Karten der Workspace-Name mit dem absolut positionierten
Preset-Badge oben rechts auf der Karte. Per Bounding-Box-Vergleich
programmatisch verifiziert (nicht nur optischer Eindruck): 3 von 5
stichprobenartig geprüften Karten hatten eine echte Pixel-Überlappung
zwischen Namens-`<span>` und Badge-`<button>`.

```
card[2] name="smoke-goals-glossary"  nameBox.x+width=1062  badgeBox.x=1011  → Überlappung
card[3] name="REST-Audit-Smoke"      nameBox.x+width=1336  badgeBox.x=1308  → Überlappung
card[4] name="REST-Audit-B-baf087d0" nameBox.x+width=468   badgeBox.x=417   → Überlappung
```

Betrifft alle 5 Themes gleichermaßen (im Theme-Sweep in Bauhaus/Sepia erneut
bestätigt) — reines Layout-Problem, kein Theming-Bug.

Laut Code-Kommentar in `frontend/src/components/DashboardViews/WorkspaceCard.tsx:35-45`
wurde **exakt dieses Problem bereits einmal behoben**
(„GESAMTTEST_BERICHT_2026-08-21.md §6 Punkt 2"): Der Name-Span bekommt
`overflow: hidden`, `textOverflow: ellipsis`, `whiteSpace: nowrap` und
`minWidth: 0`, und die Titel-Zeile reserviert `paddingRight: var(--space-8)`
für das absolut positionierte Badge. Das Problem: Der Name-`<span>` selbst
hat **keine explizite Breitenbegrenzung** (`maxWidth`/`flex-shrink`
zusammen mit einem begrenzten Container) — Ellipsis-Truncation greift bei
`overflow: hidden` nur, wenn das Element tatsächlich kleiner ist als sein
Inhalt, was ohne eine harte Breitengrenze in diesem Flex-Layout nicht
zuverlässig eintritt. Die reservierte `paddingRight` verhindert die
Überlappung nur, wenn die Truncation tatsächlich greift — tut sie es nicht,
läuft der Name direkt unter das absolut positionierte Badge.

**Screenshots:** `screenshots/zoom_dashboard_cards.png`,
`screenshots/theme_bauhaus_light_root.png`.

**Datei:** `frontend/src/components/DashboardViews/WorkspaceCard.tsx:174-204`
(Titel-Zeile), `:274-298` (absolut positioniertes Preset-Badge).

**Schweregrad:** HIGH — Regression eines bereits dokumentiert gefixten Bugs,
betrifft die erste Seite, die praktisch jeder Nutzer mit mehr als 1-2
Workspaces sieht.

### MEDIUM — Transiente 401-Lawine unmittelbar nach jedem Login

Sofort nach erfolgreichem Login (SPA-Übergang von `/login` in die
Anwendung, **kein** vollständiger Seiten-Reload) schlagen reproduzierbar
9 Requests mit `401 Authentication credentials were not provided` fehl —
ohne jeglichen `Authorization`-Header:

```
GET /api/v1/auth/me/                        (401, kein Auth-Header)
GET /api/v1/users/me/theme-preference/      (401, kein Auth-Header)  × 2
GET /api/v1/admin/theme-palettes/           (401, kein Auth-Header)  × 2
GET /api/v1/system/theme-default/           (401, kein Auth-Header)  × 2
POST /api/v1/auth/refresh/                  (401, kein Auth-Header)
```

In 2 von 2 unabhängigen Testläufen reproduziert. Ein anschließender
vollständiger Seiten-Reload (oder eine erneute `page.goto()`-Navigation)
löst das Problem **nicht** erneut aus — der Token ist dann bereits aus
`sessionStorage` geladen und im Axios-Client als Default-Header gesetzt.

**Vermutete Ursache:** In `frontend/src/App.tsx:55-63` liegt der
`ThemeProvider` **außerhalb** von `AuthProvider` in der Provider-Hierarchie
(`ThemeProvider > QueryClientProvider > BrowserRouter > AuthProvider > ...`).
Komponenten/Hooks innerhalb von `ThemeProvider`, die beim ersten Mount
Requests feuern (Theme-Präferenz, Theme-Palette-Liste, Tenant-Default),
haben keine strukturelle Abhängigkeit vom Ladezustand des Auth-Tokens und
feuern daher exakt in dem kurzen Zeitfenster, bevor `AuthProvider` den
frisch erhaltenen Login-Token propagiert hat.

**Auswirkung in dieser Sitzung:** Kein sichtbarer Funktionsausfall — Theme
und Profildaten luden nach ca. 2-4 Sekunden korrekt nach. Potenzielles
Risiko: Der fehlgeschlagene `auth/refresh`-Call bedeutet, dass ein
*tatsächlich* abgelaufener Token in genau diesem Zeitfenster nicht erneuert
würde (in dieser Sitzung nicht verifizierbar, da der Token frisch war).
Unabhängig davon verschmutzt dies die Browser-Konsole bei **jedem** Login.

**Datei:** `frontend/src/App.tsx:55-63`, `frontend/src/context/ThemeContext.tsx`.

**Schweregrad:** MEDIUM.

### MEDIUM — ADR-Supersede: Status-Badge zeigt kurzzeitig veralteten Status

Nach erfolgreichem „Supersede bestätigen" zeigt der Status-Badge
(`WorkflowStatusEditor`, Testid `workflow-current-status`) weiterhin
„Approved" an, während der unmittelbar darunter gerenderte
„Abgelöst durch: [Titel]"-Text (der laut Code nur bei
`adr.status === 'Superseded'` überhaupt erscheint, siehe
`AdrForm.tsx:322-333`) bereits korrekt sichtbar ist — zwei Bereiche
derselben Detailseite zeigen also für einen Moment widersprüchliche
Statuswerte für dasselbe Artefakt. Nach einem vollständigen Reload/erneuter
Navigation zeigt der Badge korrekt „Superseded" (verifiziert). Reiner
Stale-State-Bug im UI nach der Mutation, keine Datenkorruption im Backend.

**Screenshot:** `screenshots/deepdive_adr_superseded_result_v2.png`
(Badge „Approved" oben, „Abgelöst durch" darunter) vs.
`screenshots/deepdive_adr_status_after_reload.png` (nach Reload: „Superseded").

**Schweregrad:** MEDIUM.

### MEDIUM — ADR-Supersede-Button nicht gegen ungültigen Workflow-Status abgesichert

Der „Supersede durch..."-Button (`adr-supersede-btn`,
`frontend/src/components/AdrEditors/AdrForm.tsx:337-350`) ist nur dann
deaktiviert, wenn keine anderen ADRs im Workspace existieren
(`disabled={candidateSuccessors.length === 0}`). Er prüft **nicht**, ob der
aktuelle Workflow-Status des ADRs den Übergang zu `Superseded` überhaupt
erlaubt. Laut `backend/workflow/definition_store.py:373-379` ist als
einzige Transition zu `Superseded` `Approved → Superseded` definiert (nicht
`Draft` oder `In Review`). In dieser Sitzung reproduziert: Ein ADR im
`Draft`-Status ließ sich anklicken, das komplette Formular (Ziel-ADR
auswählen, Begründung eintippen) ausfüllen — erst beim Absenden erschien
der generische Backend-Fehler „Transition not allowed: 'Draft' →
'Superseded' is not defined". Ein simples `disabled`-Kriterium analog zum
vorhandenen `candidateSuccessors.length === 0`-Pattern (z. B.
`adr.status !== 'Approved'`) würde den verschwendeten Bearbeitungsaufwand
vermeiden.

**Screenshot:** `screenshots/deepdive_adr_superseded_result.png` (zeigt den
Fehlertext).

**Schweregrad:** MEDIUM (reines UX-Problem, kein Datenverlust — der
Server-seitige Workflow-Gate greift korrekt und verhindert den ungültigen
Übergang).

### LOW — Sidebar-Nav-Item „Verknüpfungen" durch Scroll-Fade-Overlay schwer lesbar

Am unteren Rand der scrollbaren Sidebar-Navigationsliste überlagert der
laut Code bewusst eingebaute Scroll-Hint-Fade-Gradient
(`frontend/src/components/NavigationShell/SidebarNavigation.tsx:164-189`,
issue #168 — „a fade-out gradient... shown only while there is more content
to scroll to") das letzte sichtbare Nav-Label so stark, dass der Text
„Verknüpfungen" auf Screenshots wie durch ein „X" unterbrochen aussieht.
Tritt auf allen Routen mit ausreichend langer Nav-Liste auf (z. B.
Dashboard, Architektur, Risiken) und bei allen 5 Themes gleichermaßen. Der
Link bleibt funktional klickbar; es handelt sich um ein reines
Kontrast-/Lesbarkeitsproblem des Fade-Overlays.

**Screenshot:** `screenshots/zoom_sidebar_verknuepfungen.png`.

**Schweregrad:** LOW.

### LOW — Kein sichtbares Erfolgs-Feedback nach „Alle Änderungen speichern" im TestRun-Result-Grid

Der Speichervorgang selbst funktioniert korrekt (siehe „OK"-Abschnitt), aber
der `testrun-results-save-success`-Banner erschien in keinem der
Testdurchläufe sichtbar. Nutzer erhalten nur die implizite Bestätigung über
aktualisierte KPI-Zähler und Status-Badges, kein explizites
„Gespeichert"-Signal unmittelbar nach dem Klick.

**Schweregrad:** LOW.

## Vertiefte Prüfungen (AP-3/AP-5-Fokus)

### TestRun-Result-Entry-Grid (`/test-runs`, UI-04)

**Ergebnis: funktioniert korrekt.** Bulk-Status-Anwendung (Checkbox „Alle
auswählen" + Status-Dropdown + „Auf Auswahl anwenden"), Einzel-Zeilen-
Statusänderung inkl. Freitext-Notiz, Einzel-Zeilen-Speichern und „Alle
Änderungen speichern" wurden alle einzeln getestet und **persistieren
korrekt** — verifiziert durch einen vollständigen Seiten-Reload danach
(KPI-Kacheln `TOTAL/PASSED/FAILED/NOT RUN` sowie der Status-Badge des
TestRuns selbst spiegelten den neuen Zustand exakt wider,
inkl. automatisch gesetztem „Beendet"-Zeitstempel). Einziger Mangel: fehlendes
Erfolgs-Feedback (siehe LOW-Befund oben).

**Screenshots:** `screenshots/deepdive_testrun_v2_after_save.png`,
`screenshots/deepdive_testrun_v2_after_reload.png`.

### CSV-Import Partial-Success-UX (`/import`, UI-30)

**Ergebnis: funktioniert exakt wie spezifiziert.** Test-CSV mit 13
Datenzeilen (1 valide, 12 mit fehlendem Pflichtfeld `title`, 1 unbekannte
Spalte `foo_unknown`) hochgeladen:

- Client-seitige Vorschau zeigte korrekt: `13 Datenzeilen, 4 Spalten`,
  Blocking-Hinweis „12 Zeilen ohne „title" (u. a. Zeile 3, 4, 5, 6, 7) — der
  Import wird komplett abgelehnt.", sowie eine separate Warnung zu der
  unbekannten Spalte inkl. Liste der erwarteten Spalten.
- Nach tatsächlichem Upload (Button war trotz Blocking-Hinweis aktiv —
  by design, siehe Code-Kommentar zur All-or-Nothing-Transaktion):
  „Import abgelehnt — die Datei enthält Fehler.", Atomicity-Hinweis „Es
  wurde nichts gespeichert: der Import läuft in einer einzigen Transaktion,
  alle 13 Zeilen wurden verworfen.", eine Fehlerliste mit den ersten 10
  Zeilenfehlern und ein korrekt beschrifteter Toggle-Button
  „… und 2 weitere Fehler anzeigen" (bei `ERROR_PREVIEW_LIMIT = 10`), der
  nach Klick alle 12 Fehler anzeigte.

Da der Import komplett zurückgerollt wurde (All-or-Nothing-Transaktion),
war hier kein Cleanup nötig — es wurde nichts in die Datenbank geschrieben.

**Screenshot:** `screenshots/deepdive_csvimport_result.png`.

### Risk-Matrix (`/risks`, UI-39)

**Ergebnis: funktioniert korrekt, Verhalten präzisiert.** Detection-Feld
(`risk-detection-input`, Skala 1-10), eine 3×3 Wahrscheinlichkeit×Auswirkung-
Matrix (`risk-matrix`, farbkodiert grün/orange/rot je Score-Band) mit
Live-Hervorhebung der zur aktuellen Auswahl passenden Zelle, sowie
„Risiko-Score"- und „RPZ (FMEA)"-Anzeige inkl. Formel-Erklärungstext sind
vorhanden und korrekt gerendert. **Wichtige Klarstellung:** Die
Matrix-Zellen sind laut Quellcode (`RiskForm.tsx:333-362`) bewusst
**rein deklarativ** (keine `onClick`-Handler) — sie visualisieren nur die
aktuelle Auswahl aus den Wahrscheinlichkeit-/Auswirkung-Dropdowns, sind aber
selbst nicht klickbar. Ein initialer Testversuch, direkt auf eine Zelle zu
klicken, hatte daher erwartungsgemäß keinen Effekt — das ist kein Bug,
sondern dokumentiertes Design.

**Screenshot:** `screenshots/deepdive_risk_matrix_selected.png`.

### ConfirmDialoge vor destruktiven Aktionen (UI-09)

| Aktion | ConfirmDialog vorhanden? | Verifikationsmethode |
|---|---|---|
| User deaktivieren | **Ja** — korrekt getestet (Dialog erschien, „Abbrechen"/„Bestätigen" vorhanden) | Live (Browser) |
| Custom-Field löschen | **Ja** — korrekt getestet | Live (Browser) |
| ADR löschen | Ja (Inline-Confirm-Pattern statt `<ConfirmDialog>`, aber zweistufig) | Live (Browser, im Rahmen des Cleanups) |
| TestCase löschen | Ja (Inline-Confirm-Pattern) | Live (Browser, im Rahmen des Cleanups) |
| Risk löschen | Ja (Inline-Confirm-Pattern) | Live (Browser, im Rahmen des Cleanups) |
| Theme-Palette löschen | Ja (`ThemeManagementSection.tsx:104-112`, `<ConfirmDialog>` + `pendingDelete`-State) | **Nur Quellcode** — live nicht abschließend testbar (siehe unten) |
| **Trace-Link löschen** | **Nein — siehe HIGH-Befund oben** | Live (Browser), 2× reproduziert |

Trace-Link-Löschung ist damit die einzige der 7 stichprobenartig geprüften
destruktiven Aktionen ohne Bestätigungsschutz.

### ADR-Supersede-Flow (`/adrs`, UI-32)

**Happy Path (ADR im `Approved`-Status) funktioniert korrekt:**
„Supersede durch..." → Ziel-ADR auswählen → Begründung eintippen →
„Supersede bestätigen" → „Abgelöst durch: [Titel des Ziel-ADRs]" erscheint.
Zwei Abweichungen wurden dabei gefunden und oben als eigene Befunde
dokumentiert: fehlende Client-seitige Statusprüfung vor dem Öffnen des
Formulars (MEDIUM) und ein kurzzeitig veralteter Status-Badge nach
erfolgreicher Bestätigung (MEDIUM).

**Screenshots:** `screenshots/deepdive_adr_approved_before_supersede.png`,
`screenshots/deepdive_adr_superseded_result_v2.png`.

### MetricsDashboard-Empty-State (UI-35)

**Nicht getestet** — aus Zeitgründen wurde kein isolierter, komplett leerer
Workspace angelegt, um den „nicht berechnet"-Empty-State (siehe
Code-Kommentar in `MetricsDashboard.tsx:53`) gezielt zu erzwingen. Der
aktive Test-Workspace hatte durch vorbestehende Requirements bereits
berechnete Metriken. Empfehlung: separate Folge-Prüfung mit einem frisch
angelegten, leeren Workspace.

### Theme-Konsistenz (5 Themes × 2-3 Routen)

**Ergebnis: keine Kontrast-/Lesbarkeitsprobleme gefunden.** Alle 4
benannten Paletten (`default`, `bauhaus`, `nordic`, `sepia`) × beide Modi
(`dark`/`light`) = 8 Kombinationen wurden über die Routen `/`,
`/requirements`, `/risks` gesweept (24 Screenshots). Insbesondere Bauhaus
(früherer Kontrastbug aus AP-2) zeigte in beiden Modi klar lesbaren Text
und ausreichenden Kontrast auf allen geprüften Flächen (Sidebar, Karten,
Formulare, Badges). Die einzigen wiederkehrenden visuellen Probleme
(Dashboard-Karten-Überlappung, Sidebar-Scroll-Fade) sind themenunabhängige
Layout-Bugs, keine Theming-spezifischen Kontrastprobleme — bereits oben als
eigene Befunde dokumentiert.

**Screenshots:** `screenshots/theme_<palette>_<mode>_<route>.png` (24
Dateien, z. B. `theme_bauhaus_dark_root.png`, `theme_sepia_light_root.png`).

### Tastaturbedienbarkeit (UI-10/UI-27)

- **TestRunsList (`/test-runs`): funktioniert korrekt.** Zeilen sind
  `role="button" tabindex="0"`; `.focus()` + `Enter` öffnete zuverlässig die
  Detailansicht (Result-Entry-Grid wurde sichtbar).
  Screenshot: `screenshots/deepdive_keyboard_testrun_after_enter.png`.
- **BaselinesView (`/baselines`): nicht abschließend live testbar.** Der
  Workspace hatte 0 Baselines; eine Neuanlage wurde vom SE-Auditor-Gate mit
  8 blockierenden Traceability-Findings verhindert (**korrektes Verhalten,
  kein Bug** — Configurable-Rigor-Qualitätsgate greift wie vorgesehen; ein
  Override erfordert eine ≥10-Zeichen-Begründung durch Admin/Approver). Die
  automatisierte Eingabe der Override-Begründung ließ sich im verfügbaren
  Zeitfenster nicht zuverlässig reproduzieren. Per Quellcode-Review
  (`BaselinesView.tsx:415-422`) verwendet die Zeilen-Komponente exakt
  dasselbe `role="button" tabIndex={0} onKeyDown`-Pattern wie
  `TestRunsList` (dort live bestätigt) — hohe Wahrscheinlichkeit
  identischen Verhaltens, aber nicht selbst verifiziert.
  Screenshot (Gate-Meldung): `screenshots/deepdive_keyboard_baseline_created_v3.png`.

## Nicht abschließend testbar

- **Theme-Palette-Löschung (live):** Der Versuch, eine eigene Custom-Theme-
  JSON zu importieren (Voraussetzung für einen löschbaren, nicht-System-
  Eintrag), scheiterte an der strikten Validierung — der Import verlangt
  **~70 CSS-Custom-Properties pro Modus** (`dark_tokens` und `light_tokens`
  jeweils vollständig), meine Testdatei mit 4 Tokens/Modus wurde mit einer
  Liste von 68 fehlenden Pflicht-Tokens abgelehnt. Der Aufwand, eine
  vollständig gültige Testdatei zu bauen, überstieg das Zeitbudget dieser
  Prüfung. Quellcode-Review bestätigt aber korrekte `<ConfirmDialog>`-Nutzung
  (siehe Tabelle oben) — kein Hinweis auf denselben Fehler wie bei
  Trace-Links.
- **BaselinesView-Tastaturnavigation (live):** siehe oben.
- **MetricsDashboard-Empty-State:** siehe oben.

## Zusammenfassung

- **25 von 25 Haupt-Routen** geprüft — alle laden ohne Konsolenfehler
  (außerhalb des Login-Zeitfensters), ohne sichtbare rohe i18n-Keys, ohne
  kaputte Bilder/Icons.
- **2 neue HIGH-Befunde:** Trace-Link-Löschung in der geteilten
  `TraceLinkPanel`-Komponente komplett defekt (kein Confirm **und**
  technischer Fehlschlag mit 404), sowie eine Regression des bereits
  einmal gefixten Dashboard-Karten-Overlap-Bugs.
- **3 neue MEDIUM-Befunde:** transiente 401-Lawine nach jedem Login,
  ADR-Supersede-Status-Badge zeigt kurzzeitig veralteten Wert,
  ADR-Supersede-Button ohne Client-seitige Workflow-Status-Prüfung.
- **2 neue LOW-Befunde:** Sidebar-Scroll-Fade überlagert das letzte
  Nav-Label, fehlendes explizites Erfolgs-Feedback nach TestRun-Grid-Save.
- **Vertiefte AP-3/AP-5-Bereiche größtenteils sauber:** TestRun-Result-Grid
  (Bulk + Einzel-Save persistiert korrekt), CSV-Import-Partial-Success-UX
  (Preview + Fehlerliste + „… und N weitere" exakt wie spezifiziert),
  Risk-Matrix (korrekt, rein deklarativ), ADR-Supersede-Happy-Path
  (funktioniert, mit den zwei o. g. Medium-Abweichungen), Theme-Konsistenz
  über alle 5 Themes (keine Kontrastprobleme, auch nicht in Bauhaus),
  Tastaturbedienbarkeit TestRunsList (korrekt).
- **6 von 7 stichprobenartig geprüften destruktiven Aktionen** sind korrekt
  mit einem Bestätigungsdialog abgesichert — die einzige Ausnahme
  (Trace-Link-Löschung) ist der schwerwiegendste Einzelbefund dieses
  Berichts.
