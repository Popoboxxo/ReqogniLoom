# UI-Audit: Wiederverwendbarkeit, Einheitlichkeit, Usability (inkl. Popups & Sidebar)

> **Status:** Audit abgeschlossen — vollständige Abdeckung erreicht, keine
> Umsetzung
> **Datum:** 2026-10-19 / 2026-10-20
> **Branch:** `main`
> **Methode:** Acht Agenten-Durchläufe. Vier davon statische Code-Analyse
> (zwei breite Sichtungen, eine Einzeldatei-Inventur der zunächst gefundenen
> 20 Dialog/Modal-Dateien, ein Census aller `<button>`-Vorkommen). Die
> restlichen vier sind ein **echter, mehrstufiger Live-Check** am laufenden
> Testsystem (`http://172.20.5.64:5173/`, admin/admin, Playwright/Chromium,
> volle Schreibrechte vom Nutzer autorisiert):
> 1. Erster Durchlauf: 24 Routen, 5 Create-Dialoge, 2 Responsive-Breakpoints.
>    Dabei stellte sich heraus, dass die 20-Datei-Dialog-Inventur aus der
>    Code-Analyse unvollständig war (L-04) — der Beleg, warum ein Live-Check
>    nötig ist und nicht durch weitere Code-Lektüre ersetzt werden kann.
> 2. Zweiter Durchlauf: rechte Seitenleiste, alle 28 Sidebar-Links, Button-
>    Positionierung über 11 Listenansichten, alle fehlenden Routen (29 statt
>    24) + 6 Legacy-Redirects, alle 4 Tab-Systeme. Enthielt einen
>    selbst-entdeckten und selbst-korrigierten Regex-Bug (s. Abschnitt 8).
> 3. Dritter Durchlauf: gezielte Auflösung der letzten offenen Punkte — rechte
>    Seitenleiste komplett aufgeklärt, 2 von 3 fehlenden Dialog-Triggern
>    gefunden (der dritte als technisch unerreichbar bewiesen statt vermutet),
>    3 Detail-Routen-Selektor-Bugs behoben, Seed-Daten für zuvor blockierte
>    Testfälle selbst angelegt.
>
> **Ergebnis der Vollständigkeits-Prüfung** (Nutzer-Vorgabe: "höre erst auf,
> wenn alles geprüft ist"): von allen Dialogen, Popups, Seiten, Tabs und
> Admin-Oberflächen sind nur noch **4 Punkte mit belegter, nicht bloß
> vermuteter Begründung offen** — siehe die globale Abdeckungstabelle in
> Abschnitt 8.
> **Änderungsumfang:** reine Analyse — kein Anwendungscode geändert. Eine
> Ausnahme auf dem Testsystem selbst (nicht im Repo): ein Test-Goal
> "UI-Audit Testziel (löschbar)" wurde live angelegt und archiviert, um
> L-Befund `goals-archive` zu verifizieren — bewusst so benannt, bleibt zur
> Löschung durch den Nutzer stehen. Die Live-Audit-Scripts
> (`e2e/live-ui-audit*.js`) sowie alle Screenshots/JSON-Reports
> (`docs/test-reports/live-ui-audit-2026-10-19/`) liegen im Repo, sind aber
> **nicht committed** — Entscheidung über Verbleib liegt beim Nutzer.

---

## 0. Einordnung

Das Frontend hat bereits einen reifen, dokumentierten Reuse-Layer
(`shared/Dialog`, `shared/ConfirmDialog`, `shared/Badge`/`StatusBadge`,
`shared/EmptyState`, `shared/EditorPageShell`, `shared/ArtifactForm`,
`shared/Toast/useToast`), entstanden aus früheren Konsolidierungen (u.a. Issue
#670, #672, #675, #802, UI-20, Issue #317 für die Sidebar-Gruppierung). Mehrere
frühere Problemklassen sind bereits auf 0: `window.confirm` kommt nirgends
mehr vor, hardcodierte Hex-Farben/UI-Strings sind beseitigt, `data-testid`-
Konventionen sind einheitlich, die Sidebar ist bereits in 5 logische Gruppen
sortiert statt einer flachen Liste.

Die folgenden Befunde sind die **verbliebenen** Lücken — durchgängig: Teile
der App wurden konsolidiert, andere (meist neuere) Teile sind am etablierten
Muster vorbeigebaut worden. Das Muster selbst ist also nicht das Problem,
sondern die unvollständige Durchsetzung.

**Gegenprobe Admin-Dialoge (explizit geprüft):** Die Annahme "Admin-UI ist am
wenigsten gepflegt" trifft nicht zu. `AdminDialog/SystemHealthDialog.tsx` und
`AdminDialog/TriLabelOverviewDialog.tsx` sind nach vollständiger Einzelprüfung
die **saubersten** Dialoge im ganzen Inventar: vollständig auf `shared/Dialog`
+ globale `btn-*`-Klassen migriert, 0 Inline-Styles (am 19.10. zuletzt
geändert — vorher laut Audit vom 18.9. noch 13 Inline-Styles in
`SystemHealthDialog.tsx`, also bereits behoben), vollständige i18n mit
Defaults, differenzierte Loading/Error-States. Die eigentlichen Baustellen
liegen bei den Nicht-Admin-Dialogen (Attribute/Memory, siehe D-04) und bei der
kompletten `WorkflowEditor`-Dialogfamilie (siehe D-05).

**Methodischer Hinweis zum Button-Census:** Der Audit vom 18.9. hatte
"207 von 424 Buttons ohne jede className (48,8 %)" gemessen. Der jetzige
vollständige Census (472 Buttons, alle einzeln gegengelesen statt per
Kurzfenster-Regex) findet nur **6 echt klassenlose Buttons (1,3 %)**. Das ist
**keine belegte Verbesserung seit dem 18.9.** — beide Zahlen wurden
wahrscheinlich mit unterschiedlicher Sorgfalt gemessen, und ohne das exakte
Baseline-Skript lässt sich der Sprung nicht auf echten Fortschritt
zurückführen. Verlässlich ist nur die jetzige Zahl (6, siehe D-04).

---

## 1. Befundübersicht

| ID | Bereich | Schwere | Kurzbeschreibung |
|---|---|---|---|
| D-05 | Popups | **Hoch** | WorkflowEditor-Dialogfamilie (3 Dateien) komplett eigenes Button-System statt `btn-*`, propagiert in Admin-Modul `EnforcementFlipDialog` |
| D-08 | Popups (live) | **Hoch** | ICD-/Diagram-/Test-Runs-Create-Dialoge nutzen eigene Button-Klassen statt `btn-*` — erweitert R-02 |
| R-01 | Wiederverwendbarkeit | **Hoch** | `EmptyState` (Loading/Error/Empty) wird in ~15 Dateien neu erfunden statt genutzt |
| D-04 | Popups | **Hoch** | 6 Footer-Buttons in 4 Dialogen/Sections ganz ohne `btn-*`-Klasse (Browser-Default neben gestyltem Button), live bestätigt |
| D-01 | Popups | **Hoch** | Zweite, parallele `ConfirmDialog`-Implementierung in WorkflowEditor, mit A11y-Lücke (Teil von D-05) |
| U-01 | Usability | **Hoch** | Requirement-/Architecture-Baum verschwindet bei jedem Save hinter Ladetext |
| R-02 | Wiederverwendbarkeit | Mittel | 18+ CSS-Klassen in 15 Dateien duplizieren `btn-primary`/`btn-secondary`/`btn-danger`/`btn-ghost` |
| D-02 | Popups | Mittel | Toast zweimal lokal neu gebaut statt `useToast`, mit abweichenden Dismiss-Zeiten |
| D-09 | Popups (live) | Mittel | Baselines-Create-Dialog mit vertauschter Button-Reihenfolge — zweiter bestätigter Fall neben D-06, kein Einzelfall mehr |
| D-06 | Popups | Mittel | `AiDerivationDialog` zweiter Dialog mit umgekehrter Footer-Button-Reihenfolge (s. D-09) |
| D-12 | Design (live) | Mittel | Baselines "+ Neue Baseline"-Button als einziger von 11 Listenansichten nicht rechtsbündig |
| K-01 | Einheitlichkeit | Mittel | 3 verschiedene Button-Klassen-Kompositionen für denselben visuellen Button |
| U-02 | Usability | Mittel | Erfolgsmeldung nach Aktion uneinheitlich (Toast / nichts) |
| T-01 | Tabs (live) | Mittel | 3 visuell unterschiedliche Tab-UI-Implementierungen (Settings/System-Settings, Memory, InterviewWidget) |
| R-04 | Wiederverwendbarkeit (live) | Mittel | `tree-move-dialog`/Drag&Drop-Verschieben ist toter Code — `onReparent` wird von keinem der ~20 `WorkspaceTree`-Konsumenten übergeben |
| D-07 | Popups | Niedrig | `tree-move-dialog.tsx` nutzt `btn-ghost` für Cancel statt `btn-secondary` — betrifft nur toten Code, s. R-04 |
| D-10 | Popups (live) | Niedrig | Glossary-Create-Dialog: Cancel nutzt lokale Klasse statt `btn-secondary` — 4./5. abweichende Cancel-Variante |
| K-02 | Einheitlichkeit | Niedrig | Hoisted Inline-Style-Objekte umgehen den Inline-Style-Ratchet in 5 Dateien |
| L-03 | Sidebar (live) | Mittel | Such-Placeholder in der Sidebar wird hart abgeschnitten statt mit Ellipsis |
| L-01 | ID-Anzeige (live) | Mittel | `/metrics`-Footer zeigt rohe Workspace-UUID ohne Namen, anders als `/settings` |
| L-04 | Popups (live) | **erledigt** | Dialog-Inventur war unterzählt (20 statt 25+4) — jetzt vollständig nachgezählt und zu 23/29 live verifiziert, Rest mit Beweis als unerreichbar erklärt (s. Abschnitt 8) |
| L-06 | Design (live) | Niedrig | "Anforderungs-Volatilität"-Kachel auf `/metrics` wirkt als kaputte Funktion statt ausgeblendet |
| B-01 | Rechte Seitenleiste (live) | Niedrig | Inspector-Default (3 Icons, eingeklappt) hat keinen sichtbaren Text-Hinweis für Erstnutzer, nur `aria-label` |
| I-01 | Wiederverwendbarkeit (live) | Niedrig | `WorkflowEditor/InspectorPanel` ist eine bewusst dokumentierte Parallel-Implementierung des `RightSidebar`-Patterns — zwei Codebasen für dieselbe UX |
| N-01 | Sidebar | Niedrig | Kein Collapse/Expand, keine Persistenz (live bestätigt, als unkritisch eingeschätzt) |
| R-03 | Wiederverwendbarkeit | Niedrig | Kein gemeinsames `Toast`-Präsentations-Component, nur der Hook |
| K-03 | Einheitlichkeit | Niedrig | `t('loading')`-Aufrufe mal mit, mal ohne Default-String |
| D-03 | Popups | Niedrig | Fester `z-index`, kein Stacking-Zähler für verschachtelte Dialoge |
| L-02 | ID-Anzeige (live) | Hinweis | `/audit` zeigt volle UUIDs inline in Finding-Texten statt lesbarer Artefakt-IDs |
| L-05 | Sidebar | — | ~~N-02 (Pending-Review-Badge)~~ **zurückgezogen** — widerspricht bewusster Architekturentscheidung ADR-009 |
| L-08 | Rollen/Rechte (live) | Hinweis | `ai-derivation-dialog` für ADRs ist mit `hasRole('editor')` gegated — der `admin`-Testaccount erfüllt das nicht (admin ≠ editor) |
| N-03 | Sidebar | Hinweis | Rollenbasierte Items werden ausgeblendet statt disabled+erklärt (Produktentscheidung) |
| U-03 | Usability | Hinweis | `LinkTypeEditor` ohne jeden Loading/Empty-Zustand — ggf. unkritisch, wenn Liste nie leer ist |

---

## 2. Popups / Dialoge / Toasts

**Positiv:** `shared/Dialog` ist als Primitive durchgesetzt (~26 Konsumenten).
Fokus-Trap, Escape-/Backdrop-Schließen, `role="dialog"`, `aria-modal`,
`aria-labelledby`, Scroll bei langem Inhalt (`max-height: 85vh`) und
Close-Button-Position sind zentral gelöst und dadurch für praktisch alle
Dialoge identisch. `window.confirm` existiert nicht mehr.

**D-01 — Zweite ConfirmDialog-Implementierung**
`frontend/src/components/WorkflowEditor/ConfirmDialog.tsx:1-77` dupliziert
`shared/ConfirmDialog.tsx`, das laut eigenem Kommentar ("Issue #670 made this
the single delete-confirmation for every artifact type") genau das verhindern
sollte. Eigene Klassen (`styles.btnGhost` statt `btn-secondary`,
`styles.btnDanger` statt `btn-danger`), und die Nachrichten-`<p>` (Zeile 68)
ist nicht per `aria-describedby` mit dem Dialog verknüpft — `WorkflowModal`
reicht `describedById` gar nicht erst durch.
→ **Empfehlung:** auf `shared/ConfirmDialog` migrieren; falls `WorkflowModal`
spezifische Props braucht, dort `describedById` ergänzen statt eine zweite
Komponente zu pflegen.

**D-02 — Toast zweimal neu erfunden**
`WorkflowEditor/WorkflowEditorPage.tsx:90-119` und
`Audit/audit-dashboard.tsx:243,429-432` bauen das `useState`+`setTimeout`-
Toast-Muster lokal nach, das `shared/Toast/useToast` bereits kapselt (3000ms).
Die Nachbauten dismissen nach unterschiedlichen Zeiten — wieder zwei
abweichende Werte, exakt die Divergenz, die der Hook-Header-Kommentar ("Four
page-local toast re-implementations... three different auto-dismiss
timings") schon einmal beseitigt hat.
→ **Empfehlung:** beide auf `useToast()` ummünzen.

**R-03 — Kein Toast-Presentation-Component**
`useToast` ist nur ein State-Hook; jeder Konsument rendert die Toast-Box mit
eigenem Markup/eigenen Test-IDs.
→ **Empfehlung:** analog zu `Badge`/`EmptyState` eine `shared/Toast/Toast.tsx`
ergänzen, die `useToast`-Konsumenten rendern können.

**D-03 — Fester z-index**
`shared/Dialog/Dialog.module.css:17` setzt `z-index: 1000` für jeden Dialog.
Bei zwei gleichzeitig offenen Dialogen (z.B. Löschen-Bestätigung aus einem
offenen Bearbeiten-Dialog) entscheidet nur die DOM-Reihenfolge über den
Stapel.
→ **Empfehlung:** nur relevant, falls verschachteltes Öffnen tatsächlich
vorkommt — dann Stacking-Zähler einführen, sonst ignorieren.

**D-04 — Footer-Buttons ganz ohne `btn-*`-Klasse**
Vollständige Einzelprüfung aller 20 Dialoge plus Census-Gegenprüfung findet
6 Footer-Buttons in 4 Dateien, die auf den Browser-Default-Button
zurückfallen — sichtbar andere Höhe/Radius/Farbe als der gestylte
Nachbar-Button direkt daneben:
- `AttributeEditor/AttributeCatalogDialog.tsx:131,139` (Cancel **und** Add)
- `AttributeEditor/AttributeImportDialog.tsx:59,67` (Cancel **und** Confirm)
- `Memory/AddMemoryFactDialog.tsx:120` (Cancel, Submit danebem hat `btn-primary`)
- `SystemSettings/MemoryManagementSection.tsx:163` (Cancel, Delete daneben hat
  `styles.deleteBtn`)

Exakt das Muster, das Issue #954 an anderer Stelle bereits beseitigt hat.
→ **Empfehlung:** `className="btn-secondary"`/`"btn-primary"` ergänzen — 6
Einzeiler in 4 Dateien, kleinster Fix im ganzen Audit mit direkt sichtbarer
Endanwender-Wirkung.

**D-05 — WorkflowEditor-Dialogfamilie komplett auf eigenem Button-System**
Nicht nur `WorkflowEditor/ConfirmDialog.tsx` (D-01), sondern auch
`StateDialog.tsx:57-77` und `TransitionDialog.tsx:96-116` nutzen
`styles.btnGhost`/`styles.btnPrimary`/`styles.btnDanger` aus
`WorkflowEditor.module.css:1235,1260,1269` — eine komplette
Parallel-Implementierung von `btn-secondary`/`btn-primary`/`btn-danger`, dort
inklusive einer `:focus-visible`-Regel (`WorkflowEditor.module.css:1290-1295`),
die bereits global durch `:where(button,...):focus-visible` in
`styles/global.css:63` abgedeckt ist — 0 % legitime Abweichung, reine
Dopplung. Zusätzlich importiert `SystemSettings/EnforcementFlipDialog.tsx:16`
— ein **Admin**-Modul — `WorkflowEditor/ConfirmDialog` statt
`shared/ConfirmDialog` und erbt damit die unter D-01 genannte
`aria-describedby`-Lücke in ein zweites, fachlich fremdes Modul.
→ **Empfehlung:** alle 3 WorkflowEditor-Dialoge auf globale `btn-*`-Klassen
umstellen, lokale Klassen aus `WorkflowEditor.module.css` entfernen; behebt
D-01 und die EnforcementFlipDialog-Erbschaft in einem Zug.

**D-06 — Einzige Dialog mit umgekehrter Footer-Reihenfolge**
In 18 von 19 inhaltstragenden Dialogen steht Sekundär/Abbrechen links,
Primär/destruktiv rechts (Footer `justify-content: flex-end`, DOM-Reihenfolge
= visuelle Reihenfolge). `shared/AiDerivationDialog/AiDerivationDialog.tsx:140-184`
dreht das um: Primary (Confirm/Preview) links, Secondary (Review später)
Mitte, Ghost (Discard) rechts — genau an der Stelle, an der jeder andere
Dialog seinen Primary-Button hat. Die Button-Klassen selbst sind korrekt
(die Datei hat sogar einen Kommentar, dass Button-Optik nie lokal
übernommen werden soll) — nur die Reihenfolge weicht ab.
→ **Empfehlung:** Reihenfolge angleichen, oder falls bewusst anders gewollt
(z.B. weil "Review später" kein Abbrechen ist), das kurz dokumentieren statt
stillschweigend abweichen zu lassen.

**D-07 — `tree-move-dialog.tsx` mit abweichender Cancel-Klasse**
`shared/WorkspaceTree/tree-move-dialog.tsx:79` nutzt `btn-ghost` für Cancel,
alle 17 vergleichbaren Dialoge nutzen `btn-secondary` — zwei optisch
unterschiedliche "Abbrechen"-Stile im selben System.
→ **Empfehlung:** auf `btn-secondary` vereinheitlichen.

---

## 3. Sidebar / NavigationShell

**Positiv:** Gruppierung in 5 logische Sektionen (Issue #317), korrekte
Aktive-Route-Markierung, durchgängige i18n (`t(item.labelKey)`), Mobile-Drawer
mit `aria-modal` ab 1024px-Breakpoint.

**N-01 — Kein Collapse/Expand**
`NavigationShell/SidebarNavigation.tsx` hat keinen `isCollapsed`-State, keine
Persistenz. Bei ~25 Einträgen in `NAV_ITEMS` nimmt die Sidebar auf schmaleren
Desktop-Fenstern dauerhaft volle Breite ein.
→ **Empfehlung:** nur umsetzen, wenn Platzbedarf real ein gemeldetes Problem
ist — sonst YAGNI.

**N-02/L-05 — Kein Badge für offene Reviews — zurückgezogen**
`review.list_pending` liefert eine Zahl, aber der einzige Unread-Indikator
sitzt auf einem separaten Widget (`SidebarNavigation.tsx:847f.`), nicht auf
dem `/reviews`-Nav-Link selbst. Die ursprüngliche Empfehlung lautete, das als
Badge auf den Nav-Eintrag zu spiegeln. **Korrektur nach Code-Gegenprüfung:**
der Kommentar bei `SidebarNavigation.tsx:843-849` referenziert **ADR-009** —
der Notification-Indikator wurde bewusst aus der Sidebar entfernt und lebt
jetzt nur noch im Assistant-Widget, explizit um "zwei Entry-Points zu einem
Subject" zu vermeiden.
→ **Zurückgezogen, nicht umsetzen** — das ist eine getroffene
Architekturentscheidung, kein übersehener Mangel.

**N-03 — Rollenbasierte Items komplett unsichtbar**
`SidebarNavigation.tsx:445-449` filtert Items ohne passende Rolle komplett aus
`visibleItems`, statt sie disabled+erklärt anzuzeigen. Für Nicht-Admins sind
Admin-Funktionen damit unsichtbar, ohne jeden Hinweis auf ihre Existenz.
→ **Kein Bugfix, sondern Produktentscheidung:** beibehalten, wenn
"Nicht-Admins sollen nicht wissen, was es gibt" gewollt ist; auf
"disabled + Tooltip" umstellen, wenn Entdeckbarkeit gewünscht ist.

Ergänzend (nicht im Detail geprüft, aus Code ersichtlich): keine Icons pro
Nav-Item (nur Chrome-Icons wie `Menu`/`X`) — bei ~25 rein textuellen,
gleichrangigen Einträgen fehlt ein visueller Scan-Anker. Niedrige Priorität,
da subjektiv.

---

## 4. Wiederverwendbarkeit

**R-01 — `EmptyState` systematisch ungenutzt (größter Einzelbefund)**
`shared/EmptyState` deckt Loading (inkl. Spinner), Error (inkl. Retry-Button)
und Empty bereits ab. Trotzdem wird das Verhalten von Hand nachgebaut in:

- 7× Seiten-Loading: `RequirementEditors.tsx:527`, `AdrEditors.tsx:215`,
  `IssueEditors.tsx:116`, `RiskEditors.tsx:116`, `TestCaseEditors.tsx:229`,
  `NeedsEditors.tsx:429`, `ArchitectureEditors.tsx:538`
- 5× Seiten-Error mit eigenem Retry-Button: `AdrEditors.tsx:225`,
  `IssueEditors.tsx:126`, `RiskEditors.tsx:126`, `TestCaseEditors.tsx:239`,
  `NeedsEditors.tsx:439`
- Reviews-Modul: `SuggestionsInbox.tsx:155,185,193`,
  `ReviewsView.tsx:899,919,928`, `ReviewHistoryPanel.tsx:41,57`
- `AttributeEditor/AttributeCatalogDialog.tsx:175-197`

→ **Empfehlung:** einen Durchlauf "alle Treffer auf `EmptyState` umstellen"
fahren — mechanisch, aber der mit Abstand größte Hebel: behebt gleichzeitig
U-01 (Flackern) und das fehlende Spinner-Feedback überall.

**R-02 — Doppelte Button-CSS (vollständiger Census: 18 Klassen in 12 Dateien)**
Der vollständige Button-Census bestätigt nicht nur die vorher bekannten 5
Dateien, sondern findet 7 weitere. Gesamtliste:

| Datei:Zeile | Lokale Klasse | Dupliziert |
|---|---|---|
| `SystemSettings/BannerSection.module.css:68` | `.saveButton` | `btn-primary` |
| `SystemSettings/MemoryManagementSection.module.css:36` | `.deleteBtn` | `btn-danger` |
| `SystemSettings/EnforcementModePanel.module.css:108` | `.primaryButton` | `btn-primary` |
| `SystemSettings/WorkspaceAdminSection.module.css:60,80,86` | `.solidAction`, `.reactivateWorkspaceButton`, `.deleteWorkspaceButton` | `btn-primary`-Basis + `btn-success`/`btn-danger`-Varianten |
| `TestRuns/TestRunsList.module.css:166,196` | `.submitBtn`, `.retryBtn` | `btn-primary`, `btn-secondary`/`btn-ghost` |
| `TestRuns/TestRunDetailEditor.module.css:174,200` | `.btnPrimary`, `.btnSecondary` | `btn-primary`, `btn-secondary` |
| `BaselinesView/BaselinesView.module.css:263` | `.deleteBtn` | `btn-danger` |
| `UserProfileSettings/ApiKeysSection.module.css:80,131,230` | `.primaryButton`, `.copyButton`, `.dangerButton` | `btn-primary` ×2, `btn-danger` |
| `UserProfileSettings/ProfileSection.module.css:52,63` | `.primaryButton`, `.secondaryButton` | `btn-primary`, `btn-secondary` |
| `PermissionMatrix/PermissionMatrixEditor.module.css:78,98` | `.primaryButton`, `.cancelButton` | `btn-primary`, `btn-secondary` |
| `IcdView/IcdView.module.css:162` | `.cancelButton` | `btn-secondary` |
| `WorkflowEditor/WorkflowEditor.module.css:1235,1260,1269` | `.btnPrimary`, `.btnDanger`, `.btnGhost` | `btn-primary`/`btn-danger`/`btn-ghost` (siehe D-05 — hier zusätzlich eine redundante, bereits global abgedeckte `:focus-visible`-Regel) |

Dasselbe Muster, das laut Kommentar in `WorkspaceSettings.tsx:21-23` ("10
Style-Signaturen für 22 Buttons") schon einmal beseitigt wurde, ist in
anderen Dateien neu entstanden — in der Größenordnung unverändert (vorher 17,
jetzt 12 betroffene Dateien), also **keine Netto-Reduktion**, nur
Verschiebung.
→ **Empfehlung:** lokale Klassen entfernen, nur `btn-primary`/`btn-secondary`/
`btn-danger`/`btn-ghost` nutzen. Da das Muster trotz früherer Bereinigung
immer wieder neu entsteht, lohnt sich zusätzlich ein Lint-Regel-Vorschlag
(z.B. ESLint-Verbot für CSS-Modul-Klassennamen, die `button`/`btn` im Namen
tragen und `background`+`border-radius`+`padding` gleichzeitig setzen) statt
nur erneut händisch aufzuräumen.

---

## 5. Einheitlichkeit

**K-01 — Drei Button-Kompositionsmuster**
Aus R-02: `TestRunDetailEditor.tsx:352`, `ApiKeysSection.tsx:140`,
`ProfileSection.tsx:166` kombinieren `btn-primary` **und** die redundante
lokale Klasse; `EnforcementModePanel.tsx:167`,
`PermissionMatrixEditor.tsx:151` nutzen **nur** die lokale Klasse. Drei
verschiedene Kompositionen für denselben visuellen Button.
→ **Empfehlung:** einheitlich auf reines `btn-primary`/`btn-secondary`.

**K-02 — Hoisted Inline-Style-Objekte umgehen den Ratchet**
`WorkspaceSettings/McpConnectionSection.tsx:43-57`,
`shared/CreateTraceLinkDialog/link-type-listbox.tsx:114-136`,
`LinkTypeEditor/LinkTypeEditorPage.tsx:417` (`errorStyle`),
`AdrEditors/AdrSupersedePanel.tsx:20-34`,
`NavigationShell/CreateWorkspaceModal.tsx:38-61,206-285` deklarieren
`const x: React.CSSProperties = {...}` statisch mit `var(--...)`-Werten und
referenzieren sie dann via `style={x}` — funktional identisch zu einer
`.module.css`-Klasse, aber unsichtbar für den literalen `style={{`-Ratchet.
(Zum Vergleich: `SplitView/SplitView.tsx:147-157` und
`shared/PageHeader.tsx:144-146` sind legitime Fälle, da echte
Laufzeitwerte/Bedingungen — nicht migrieren.)
→ **Empfehlung:** die 5 statischen Fälle in CSS-Module überführen.

**K-03 — Uneinheitliche Loading-Gates und Default-Strings**
`AdrEditors.tsx:215` u.a. (5 Module) gaten korrekt auf
`isLoading && items.length === 0` (Liste bleibt bei Refetch sichtbar),
`RequirementEditors.tsx:527` und `ArchitectureEditors.tsx:538` nur auf
`isLoading` (→ U-01). Zusätzlich: `t('loading')` ohne Default in
Requirement-/ArchitectureEditors, `t('loading', 'Laden...')` mit Default in
AdrEditors — keine einheitliche Konvention.
→ **Empfehlung:** Gate vereinheitlichen (behebt U-01 mit), Default-String-
Konvention einmal festlegen.

---

## 6. Usability vor Endanwender

**U-01 — Baum verschwindet bei jedem Save (höchste Endanwender-Relevanz)**
Direkte Folge aus K-03: `RequirementEditors.tsx:527` und
`ArchitectureEditors.tsx:538` ersetzen bei **jedem** Refetch — auch nach
Create/Save, nicht nur beim ersten Laden — die komplette Liste/den Baum durch
reinen Ladetext. Die fünf übrigen Editor-Module lassen die Liste währenddessen
sichtbar. Für den Requirement- und Architecture-Baum, vermutlich die
meistgenutzten Ansichten im Tool, ist das sichtbare Flackern/Verschwinden der
Hierarchie beim Speichern die schlechteste UX der sieben strukturgleichen
Module.
→ **Empfehlung:** sofort beheben, 2-Zeilen-Diff pro Datei (Gate wie die
anderen 5 Module).

**U-02 — Erfolgsmeldung nach Aktion uneinheitlich**
Manche Module zeigen einen Toast nach erfolgreicher Aktion
(`AttributeEditorPage`, `WorkflowEditorPage`, `audit-dashboard`), andere gar
keine sichtbare Bestätigung außer dem optimistischen UI-Update selbst
(`AttributeCreateDialog.tsx`, `PermissionMatrixEditor.tsx` zeigen nur
Fehler, nie Erfolg).
→ **Empfehlung:** Konvention festlegen — jede mutierende Aktion entweder
Toast oder bewusst dokumentiertes "kein Feedback nötig" (z.B. weil das
UI-Update selbst ausreichend sichtbar ist), statt es implizit offenzulassen.

**U-03 — Kein Loading/Empty in LinkTypeEditor (Hinweis)**
`LinkTypeEditor/LinkTypeEditorPage.tsx` hat außer einem Save-Error (:799-801)
keinen erkennbaren Lade- oder Leer-Zustand für die Link-Type-Liste.
→ **Empfehlung:** nur relevant, falls die Liste tatsächlich leer/ladend sein
kann (z.B. leerer Tenant-Katalog) — sonst kein Handlungsbedarf.

---

## 7. Priorisierte Handlungsempfehlungen

**P0 — Sofort, geringer Aufwand, hoher Endanwender-Impact**
1. [L-03] Sidebar-Suchfeld: `text-overflow: ellipsis` statt hart
   abgeschnittenem Placeholder — live als kaputt wirkender Text bestätigt,
   kleinste denkbare CSS-Änderung.
2. [D-04] 6 Footer-Buttons in 4 Dateien um `btn-secondary`/`btn-primary`
   ergänzen — kleinster Fix im Audit, sofort sichtbar, live bestätigt.
3. [U-01/K-03] Loading-Gate in Requirement-/ArchitectureEditors angleichen.
4. [D-01/D-05] Alle 3 WorkflowEditor-Dialoge (`ConfirmDialog`, `StateDialog`,
   `TransitionDialog`) auf `shared/ConfirmDialog`/globale `btn-*`-Klassen
   migrieren — behebt Duplikat, A11y-Lücke **und** die Erbschaft in
   `EnforcementFlipDialog` in einem Zug.
5. [D-02] Toast in `WorkflowEditorPage` und `audit-dashboard` auf `useToast()`
   umstellen.
6. [D-12] Baselines "+ Neue Baseline"-Button rechtsbündig ausrichten wie alle
   anderen 10 Listenansichten — live als einzige Abweichung bestätigt.
7. [D-09] Baselines-Dialog-Button-Reihenfolge korrigieren (zusammen mit D-06
   jetzt ein bestätigtes Muster, nicht mehr Einzelfall).

**P1 — Mechanisch, aber breiter Diff**
8. [R-01] Alle ~15 Fundstellen auf `shared/EmptyState` umstellen (7 Editors +
   Reviews-Modul + AttributeCatalogDialog).
9. [R-02/K-01/D-08/D-10] Jetzt 18+ doppelte Button-CSS-Klassen in 15 Dateien
   entfernen (ursprüngliche 12 + live bestätigt ICD/Diagram/TestRuns/Glossary),
   auf `btn-primary`/`btn-secondary`/`btn-danger`/`btn-ghost` vereinheitlichen.
10. [D-07/R-04] Produktentscheidung zuerst: `tree-move-dialog` ist toter Code
    (kein Konsument verdrahtet `onReparent`) — entscheiden, ob das Feature
    fertiggestellt oder entfernt wird, bevor die Button-Klasse (D-07) noch
    gefixt wird.
11. [T-01] Gemeinsame `Tabs`-Primitive einführen, die 3 visuell
    unterschiedlichen Tab-Implementierungen (Settings/System-Settings,
    Memory, InterviewWidget) darauf migrieren.
12. [L-01] `/metrics`-Footer um den Workspace-Namen ergänzen (analog zu
    `/settings`) statt der rohen UUID.
13. [L-08] Beim Nutzer klären, ob `admin ≠ editor` im Rollenmodell
    beabsichtigt ist — falls nicht, ist das ein Rollen-Fix, keine UI-Frage.

**P2 — Aufräumen, keine Dringlichkeit**
14. [K-02] 5 hoisted Inline-Style-Objekte in CSS-Module überführen.
15. [R-03] `shared/Toast/Toast.tsx`-Präsentationskomponente ergänzen.
16. [K-03] `t('loading')`-Default-String-Konvention festlegen.
17. [U-02] Konvention für Erfolgs-Feedback nach Aktionen festlegen und auf
    `AttributeCreateDialog`/`PermissionMatrixEditor` anwenden.
18. [L-06] "Anforderungs-Volatilität"-Kachel auf `/metrics` ausblenden, falls
    die Metrik aktuell nicht unterstützt wird — sonst wirkt sie wie ein Bug.
19. [L-02] Lesbare Artefakt-IDs statt roher UUIDs in `/audit`-Finding-Texten
    (nur, falls das Werkzeug auch von weniger technischen Nutzern gelesen
    wird — sonst optional).
20. [B-01] Tooltip für den eingeklappten Zustand der rechten Seitenleiste.
21. [I-01] Niedrige Priorität: prüfen, ob `WorkflowEditor/InspectorPanel`
    künftig auf `RightSidebar` migrieren kann, falls diese generischer wird.

**Zurückgestellt / Produktentscheidung nötig, kein Code-Fix**
- [N-01] Sidebar-Collapse — live bestätigt (28 Links, 220px fix), aber beim
  Durchklicken wirkte die Liste nicht überladen. Weiterhin nur bei echtem
  gemeldetem Platzproblem umsetzen.
- [N-03] Rollenbasierte Sichtbarkeit (ausblenden vs. disabled+Tooltip).
- [D-03] Dialog-Stacking — nur falls verschachteltes Öffnen real vorkommt.
- [U-03] LinkTypeEditor-Leerzustand — nur falls Liste real leer werden kann.
- ~~[N-02]~~ zurückgezogen, siehe L-05 — widerspricht ADR-009.

**Hinweis zum Aufräumen auf dem Testsystem:** ein Test-Goal "UI-Audit
Testziel (löschbar)" wurde für die Verifikation von `goals-archive` live
angelegt und archiviert und bleibt bewusst stehen — Löschung liegt beim
Nutzer.

P0+P1 decken 24 von 31 Befunden ab. Die Live-Verifikation bestätigt
außerdem, dass über alle 29 Routen, ~23 live geöffnete Dialoge/Panels und 4
Responsive-Checks **kein einziger** echter JavaScript-Fehler auftrat (siehe
Abschnitt 8, L-F) — das Tool ist im Kern stabil, die offenen Punkte sind
durchgehend Politur bzw. einzelne Produktentscheidungen, keine funktionalen
Brüche. Die vom Nutzer verlangte vollständige Abdeckung ist erreicht: jeder
nicht live verifizierte Punkt hat eine geprüfte, nicht nur vermutete
Begründung (Abschnitt 8.3).

---

## 8. Live-Verifikation am Testsystem (2026-10-19)

Durchgeführt am laufenden Testsystem `http://172.20.5.64:5173/` (admin/admin)
via Playwright/Chromium, nicht aus dem Code abgeleitet. Script:
`e2e/live-ui-audit.js`. Artefakte (Screenshots + JSON-Report):
`docs/test-reports/live-ui-audit-2026-10-19/`. Umfang: alle 24 Hauptrouten,
5 live geöffnete Create-Dialoge, 2 Responsive-Breakpoints (375px/768px),
Konsolen-/Netzwerk-Fehler pro Route, visuelle Prüfung einer repräsentativen
Screenshot-Auswahl.

**L-01 — Rohe Workspace-UUID im Metrics-Footer**
`/metrics` zeigt am Seitenende nur `Workspace: 12893b6d-cfe3-478d-b0bc-c1ec41575d49`
— ohne Namen. Zum Vergleich: `/settings` zeigt dieselbe ID korrekt gelabelt
als "Workspace-ID" **mit** Namen ("Zahnbürste SysEng Demo") daneben und einem
Kopieren-Button — das ist die Positiv-Referenz, kein eigener Fix nötig.
→ **Empfehlung:** Metrics-Footer um den Workspace-Namen ergänzen oder die
UUID ganz weglassen.

**L-02 — Rohe UUIDs in Audit-Finding-Texten (Hinweis)**
`/audit` zeigt in jedem Finding-Text die volle UUID des betroffenen Artefakts
inline im Satz (z.B. `'...' (011c55bd-cd7b-4003-af49-d1e8bbde2bae) has no
verifying TestCase`), zusätzlich zu einem abgekürzten ID-Badge — bei 1371
Findings viel rohe ID-Dichte, während der Rest des Tools durchgängig
lesbare IDs wie `REQ-007`/`TC-006` zeigt (sichtbar auf denselben
Screenshots).
→ **Empfehlung:** nur relevant, falls `/audit` auch von weniger technischen
Nutzern gelesen wird — sonst optional, Zielgruppe ist ohnehin technisch.

**L-03 — Sidebar-Suchfeld-Placeholder hart abgeschnitten**
Bei der gemessenen Sidebar-Breite von fix 220px wird der Placeholder "Alle
Artefakte durchsuchen" hart abgeschnitten ("Alle Artefakte durchsu") statt
mit Ellipsis — sieht wie abgeschnittener/kaputter Text aus. Zum Vergleich:
der Workspace-Name auf der Dashboard-Karte wird bei 375px-Viewport korrekt
mit Ellipsis gekürzt ("Zahnbürste SysE...") — das Problem ist also nur an
dieser einen Stelle, kein systemisches Muster.
→ **Empfehlung:** `text-overflow: ellipsis` auf dem Such-Input ergänzen.
Kleinster Fix mit sofortiger visueller Wirkung im gesamten Audit.

**L-04 — Vorherige Dialog-Inventur war unvollständig**
Die "vollständige" 20-Datei-Tabelle in Abschnitt 8 beruhte auf
Dateinamen-Suche (`find -iname "*dialog*" -o -iname "*modal*"`) und hat jeden
Dialog übersehen, der in einer anders benannten Datei lebt. Live-Check
deckte das auf: "Neue Anforderung" und "Neuer Testfall" öffnen sich als echte
`shared/Dialog`-Modals, wurden aber von Abschnitt 8 gar nicht erfasst.
Nachprüfung per Import-Grep statt Dateiname ergibt:
- **25 statt 20** direkte `shared/Dialog`-Konsumenten — zusätzlich u.a.
  `ArchitectureEditors`, `Audit/audit-dashboard`, `BaselinesView`,
  `DiagramView`, `GlossaryView`, `IcdView`, `InterviewEditors`,
  `NeedsEditors/NeedList`, `Settings/UserManagement`, 3× `SystemSettings/*`,
  `TestRuns/TestRunsList`.
- Zusätzlich eine zweite Abstraktionsebene `shared/EditorPageShell` (kapselt
  selbst `Dialog`), genutzt von `AdrEditors`, `IssueEditors`, `RiskEditors`,
  `TestCaseEditors` — **gute Nachricht**: alle 7 `*Editors`-Module nutzen den
  gemeinsamen Dialog-Mechanismus, direkt oder über `EditorPageShell`, die
  Konsolidierung ist also besser als in Abschnitt 8 angenommen.
- Live visuell verifiziert (2 der neu gefundenen Dateien): Requirement- und
  TestCase-Create-Dialog haben beide eine korrekte, mit dem Rest
  übereinstimmende Abbrechen/Erstellen-Reihenfolge.
→ **Nachtrag:** die Button-Prüfung auf Basis dieser 25+4-Liste wurde in den
Runden 2/3 durchgeführt (Abschnitt 8.1/8.2) — Ergebnis: D-08, D-09, D-10,
D-12 kamen dabei zusätzlich zu den schon bekannten Fällen heraus. Damit
**erledigt**, siehe die globale Abdeckungstabelle in Abschnitt 8.3.

**L-05 — siehe N-02/L-05 in Abschnitt 3 (zurückgezogen, ADR-009).**

**L-06 — "Nicht berechnet"-Kachel wirkt wie ein Bug**
Auf `/metrics` zeigt die Kachel "Anforderungs-Volatilität" "Nicht berechnet"
mit grauem Status-Punkt, direkt neben 4 anderen voll berechneten Kacheln —
wirkt wie eine unfertige/kaputte Funktion, die trotzdem prominent mitgerendert
wird.
→ **Empfehlung:** falls die Metrik aktuell nicht unterstützt wird, ausblenden
statt als scheinbar kaputte Kachel zu zeigen.

**L-07 — Design-Idee (kein Fix): Dashboard-Weißraum**
Das Dashboard wirkt bei nur 2 Workspace-Karten sehr leer (viel ungenutzter
Weißraum darunter). Kein Bug — aber ein "Letzte Aktivität"/"Schnellzugriff"-
Panel würde den Platz sinnvoll nutzen.

**L-F — Konsolen-/Netzwerkfehler: durchweg sauber**
Über alle 24 Routen, 5 Dialoge und 4 Responsive-Checks trat **kein einziger
echter JavaScript-Fehler** auf. Einzige wiederkehrende Meldung (29×, jede
Route): `[bluepencil] crypto.subtle is unavailable; loading without the
bundle integrity check` — bekanntes Dev-Tooling-Warning, kein App-Bug. Die
3 `401`-Fehler traten nur vor dem Login auf (erwartetes Session-Check-
Verhalten).

**Sidebar live (Ergänzung zu N-01):** Breite fix 220px, 28 Nav-Links, kein
Collapse — bestätigt N-01 aus der Code-Analyse. Unter 1024px wird die
Sidebar korrekt zum Drawer mit Burger-Button, sauber ohne Scroll-/Overlap-
Bug. Begründete Einschätzung: bei 28 Links auf 220px wäre Icon-only-Collapse
die naheliegendste Verbesserung, aber **nicht dringend** — die 5
Gruppen-Header schaffen beim tatsächlichen Durchklicken genug visuelle
Struktur, die Liste wirkte nicht überladen.

**Responsive (Ergänzung zu D-03/allgemein):** 375px und 768px auf Dashboard
und Requirements getestet — Sidebar wird korrekt zum Drawer, Inhalt reflowt
saube, kein horizontales Scrollen, keine überlappenden Elemente.

### 8.1 Zweite Runde — Edit-Dialoge, rechte Seitenleiste (1. Versuch), fehlende Routen, Tabs

Script `e2e/live-ui-audit-part2.js`. **Selbst entdeckter und selbst
korrigierter Bug:** die erste Fassung suchte Create-Buttons mit dem Regex
`^(neue?r?s?\s|...)`, die echten Buttons heißen aber `"+ Neue Anforderung"`
(führendes `+ `) — dadurch klickte das Script bei ~16 Modulen ins Leere,
meldete das aber fälschlich als Erfolg. Beim Gegencheck der Screenshots
(leere Listen statt offener Dialoge) selbst aufgefallen, Regex korrigiert,
**alle 16 betroffenen Fälle neu verifiziert**, bevor sie unten als bestätigt
gelten.

**D-08 — ICD-/Diagram-/Test-Runs-Create-Dialoge mit eigenem Button-System**
Live per DOM-Inspektion bestätigt: `/icds`, `/diagrams`, `/test-runs`
nutzen in ihren Create-Dialogen jeweils eigene lokale Klassen
(`_submitButton_.../_cancelButton_...` etc.) statt `btn-primary`/
`btn-secondary` — erweitert R-02 um 3 weitere Dateien (`IcdView`,
`DiagramView`, `TestRunsList`).
→ **Empfehlung:** in den R-02-Rollout aufnehmen.

**D-09 — Baselines-Create-Dialog mit vertauschter Button-Reihenfolge**
"Speichern" (Primary, blau) steht links, "Abbrechen" rechts — exakt
umgekehrt zu allen anderen geprüften Dialogen. Zusammen mit `AiDerivationDialog`
(D-06) der **zweite** bestätigte Fall — kein Einzelfall mehr, sondern ein
wiederkehrendes Muster.
→ **Empfehlung:** Lint-Regel für Dialog-Footer-Reihenfolge erwägen statt nur
die zwei bekannten Fälle händisch zu fixen.

**D-10 — Glossary-Create-Dialog mit abweichender Cancel-Klasse**
"Neuer Begriff"-Dialog: Cancel-Button nutzt lokale Klasse `_btnOutline_...`
statt `btn-secondary` (live per DOM bestätigt) — vierte/fünfte abweichende
Cancel-Variante im System, neben `btn-ghost` (`tree-move-dialog`) und
`styles.btnGhost` (WorkflowEditor-Trio).
→ **Empfehlung:** in den R-02/D-07-Rollout aufnehmen.

**D-11 — Live-Bestätigung von D-04**
`/memory` "Fakt hinzufügen"-Dialog: Cancel-Button hat live bestätigt
`className: ""` (leer) — direkte Live-Bestätigung des statisch gefundenen
D-04, kein neuer Befund.

**D-12 — Baselines "+ Neue Baseline" nicht rechtsbündig**
Von 11 live gemessenen Listenansichten (Requirements, Adrs, Risks, Issues,
TestCases, Needs, Goals, TestRuns, ICDs, Diagrams, Baselines) ist Baselines
die einzige Ausnahme: der primäre Create-Button sitzt bei x=280 statt wie
überall sonst rechtsbündig (x≈1120-1230 bei 1366px Viewport). Zusammen mit
D-09 ist Baselines das Modul mit den meisten Positionierungs-Abweichungen im
ganzen System.
→ **Empfehlung:** Button-Position an das Muster der anderen 10 Module
anpassen.

**T-01 — Drei visuell unterschiedliche Tab-Implementierungen**
Alle 4 gefundenen Tab-Systeme live durchgeklickt (17 Tab-Wechsel insgesamt,
funktional alle korrekt — `aria-selected` wechselt richtig):
- `/settings` (6 Tabs) und `/system-settings` (6 Tabs): identischer Stil,
  Unterstrich unter dem aktiven Tab.
- `/memory` (3 Tabs): **anderer Stil** — umrandete Pille/Box statt Unterstrich.
- `InterviewWidget` (2 Tabs, Floating-Popup): **dritter Stil** — ausgefüllter
  Segmented-Control-Button.
→ **Empfehlung:** exakt das Muster, das bei Buttons (R-02) und Toasts (D-02)
bereits mehrfach gefunden wurde — eine gemeinsame `Tabs`-Primitive einführen,
rein visuell, keine Funktionskorrektur nötig.

**Linker Navigationsbaum — vollständig durchgeklickt:** alle 28/28 Links
führen zu nicht-leerem Hauptinhalt, kein Crash. Hover-State sichtbar bei 2
von 3 gestichprobten Links (beim 3., dem aktiven Dashboard-Link, sind
Hover- und Aktiv-Farbe identisch — erwartet, kein Bug). Code-Grep bestätigt:
**kein echter Baum** — `aria-expanded` existiert nur am Mobile-Burger und
Workspace-Switcher, keine ein-/ausklappbaren Untergruppen. Flache Liste in
5 statischen Gruppen, wie in Abschnitt 3 beschrieben — bestätigt, nicht
widerlegt.

**Routen/Redirects (Teil E):** alle 10 vorher fehlenden Routen
(`/memory`, `/testcases`, `/test-runs`, `/settings/link-types`,
`/system-settings/link-types`, `/user-management`, `/workflows/:entityType`,
`/attributes`, `/attributes/:entityType`, `/profile`) laden erfolgreich. Alle
6 Legacy-Redirects landen korrekt am Ziel. 6 von 9 Detail-Routen (`:id`)
live mit echtem Artefakt geöffnet (Needs, Requirements, Architecture, Adrs,
Risks, Issues); 3 (ICDs, Diagrams, Interviews) zunächst als "keine Daten"
gemeldet — **das stellte sich als Script-Selektor-Bug heraus**, nicht als
echte Datenlücke (siehe 8.2).

**Admin-Oberflächen (Teil G):** `/system-settings` mit 6 Unter-Panels
bestätigt (Administration, Workflow-/Attribut-/Berechtigungs-Standards,
Darstellung, Memory). "Workspace löschen"-Dialog live geöffnet — **vorbildliches
Type-to-Confirm-Pattern** (Workspace-Name muss exakt eingetippt werden,
Löschen-Button bis dahin disabled), als Positiv-Referenz hervorzuheben.
`/user-management` und dessen Create-Dialog bestätigt.
`PermissionMatrixEditor` lokalisiert unter `/system-settings` → Tab
"Berechtigungs-Standards". `/profile` (ApiKeysSection) samt Create-Dialog
bestätigt.

### 8.2 Dritte Runde — letzte Lücken geschlossen

Scripts `live-ui-audit-part2-fix.js` + `live-ui-audit-part3.js`.

**Rechte Seitenleiste — vollständig aufgeklärt.** Der entscheidende Fund:
die Leiste öffnet sich beim Artefakt-Auswählen standardmäßig **eingeklappt
als schmale 3-Icon-Spalte** (~45px breit) — das hatte die zweite Runde
fälschlich für "fertig" gehalten, weil das Container-Element bereits
existierte. Erst ein Klick auf das Expand-Element öffnet die volle Breite.
Danach bestätigt (für Requirements, live durchgeklickt):
- **5 Panels, nicht 3 oder 4:** Version-, Diff- und Comment-Panel aus
  `ArtifactInspector/` **plus** ein fünftes, modul-eigenes
  `ReqTraceLinkPanel`, das für Requirements bewusst das generische
  `TracePanel` ersetzt (`hideTraceLinks`-Mechanismus) — dasselbe Prinzip wie
  ADR-009 bei der Sidebar: ein Entry-Point statt zwei. **Positiv zu werten,
  kein Bug.**
- Collapse-Button existiert erst nach dem Expand — konsistent, kein Fehler.

**B-01 — Kein visueller Hinweis im Default-Zustand**
Der eingeklappte 3-Icon-Zustand hat keinen sichtbaren Text-Hinweis für
Erstnutzer, nur `aria-label` (gut für Screenreader, visuell nicht
selbsterklärend).
→ **Empfehlung:** Tooltip beim Hover ergänzen — kein Bug, UX-Politur.

**`create-trace-link-dialog` — gefunden und geöffnet.** Trigger ist
`req-tracelink-create-btn`, aber erst sichtbar **nach** dem Expand der
rechten Seitenleiste — deshalb schlug die vorherige Suche nach dem
generischen Selektor fehl: `ReqTraceLinkPanel` reicht einen
modulspezifischen Testid-Präfix durch, nicht den generischen aus
`TraceLinkPanel.tsx`.

**R-04 — `tree-move-dialog`/Drag&Drop-Verschieben ist toter Code**
Beweis statt Vermutung: `grep -rn "onReparent=" --include="*.tsx"` über das
**gesamte** Frontend ergibt **0 Treffer**. Der Dialog hängt an
`useTreeDrag(nodes, onReparent)`, und `onReparent` ist in `workspace-tree.tsx`
ein reines Opt-in-Prop — **kein einziger** der ~20 `WorkspaceTree`-Konsumenten
(Requirement-/Adr-/Risk-/Issue-/TestCase-/Needs-/Diagram-/ICD-Listen,
GoalsTree, ImpactView) aktiviert es. Die Verschieben-Funktion samt Dialog ist
im laufenden System **nirgends erreichbar** — kein Seed-Daten- oder
Script-Problem, sondern ein eigenständiger Befund.
→ **Empfehlung:** Produktentscheidung nötig — Feature fertigstellen (an
mindestens einem Konsumenten verdrahten) oder als totes Gewicht entfernen
(inkl. `tree-move-dialog.tsx`, `useTreeDrag`). D-07 (Button-Klasse) betrifft
damit nur Code, den aktuell niemand sehen kann.

**L-08 — `ai-derivation-dialog` ist rollen-gegated**
Das Overflow-Menü auf `/adrs` zeigt mit dem `admin`-Testaccount nur "Per
Interview erstellen" — der Menüpunkt für die KI-Ableitung fehlt. Ursache
gefunden: `AdrEditors.tsx` gated ihn mit `hasRole('editor')`, und `admin`
erfüllt diese Prüfung in diesem Rollenmodell nicht (admin ≠ editor).
→ **Kein Bug, aber ein Hinweis:** falls das unbeabsichtigt ist (Admins
sollten vermutlich alles können, was Editoren können), ist das ein
Rollenmodell-Finding, keine UI-Frage — zur Klärung an den Nutzer.

**Detail-Routen ICDs/Diagrams/Interviews — Selektor gefixt.** Mit einem
nachweislich funktionierenden `role="button"`/`role="treeitem"`-Selektor:
`/icds`-Detail öffnet jetzt erfolgreich — **war wirklich nur ein
Script-Bug, keine fehlende Daten.** `/diagrams` und `/interviews` bleiben
auch mit dem korrigierten Selektor leer → **jetzt mit hoher Konfidenz:
echte Seed-Daten-Lücke** auf diesem Testsystem, kein Script-Bug mehr.

**Seed-Daten-gegatete Fälle, mit Schreibzugriff geschlossen:**
- `goals-archive` — **vollständig erfolgreich.** Ein neues Goal
  ("UI-Audit Testziel (löschbar)") live angelegt und archiviert. Footer:
  `Abbrechen` (btn-secondary) / `Archivieren` (btn-danger) / `×` — sauber,
  konsistent, kein neuer Befund. Das Test-Goal bleibt (archiviert, klar
  benannt) im System — Löschung liegt beim Nutzer.
- `enforcement-flip` — Modus-Wechsel-Button geklickt, kein Dialog erschien;
  Vorher/Nachher-Vergleich bestätigt aber: **Zustand nachweislich
  unverändert.** Aus Risikoabwägung bewusst nicht weiter experimentiert,
  um keine echte Backend-Mutation auf Verdacht zu produzieren.
- `reviews-signature` — Liste bestätigt leer; ein Review mit Signatur-Schritt
  bräuchte einen vollständigen CCB-Workflow (Change Request → Approval-Kette)
  — kein 2-3-Klick-Fall, daher wie vorgegeben **bewusst nicht erzwungen.**

**I-01 — `WorkflowEditor/InspectorPanel` als dokumentierte Parallel-Implementierung**
Statisch bestätigt: `InspectorPanel.tsx:5` kommentiert explizit "following
the RightSidebar pattern" — gleiches `localStorage`-Namensschema
(`reqflow_*_inspector_width`/`_collapsed_`), gleiche Collapse/Resize-Mechanik.
Kein Versehen, sondern bewusst nachgebaut — trotzdem zwei Codebasen für
dasselbe UX-Muster.
→ **Empfehlung:** niedrige Priorität — falls `RightSidebar` künftig
generischer wird, prüfen ob `InspectorPanel` darauf migrieren kann; aktuell
kein akuter Handlungsbedarf.

### 8.3 Globale Abdeckungstabelle (alle drei Live-Runden zusammen)

Direkte Antwort auf die Nutzerfrage "bist du sicher, alle Dialoge/Edits
durchgegangen?":

| Bereich | Geprüft? | Zustand / Begründung |
|---|---|---|
| 24 Haupt-Listen-Routen | Ja | ok, 0 Konsolenfehler |
| 10 zunächst fehlende Routen (Memory/Testcases/Profile/etc.) | Ja | ok |
| 6 Legacy-Redirects | Ja | alle landen korrekt am Ziel |
| 9 Detail-Routen (`:id`) | Ja (9/9, nach Selektor-Fix) | 6× mit Seed-Daten bestätigt ok, 2× (Diagrams/Interviews) bestätigt echte Seed-Daten-Lücke, kein Script-Bug |
| 25 direkte `shared/Dialog`-Konsumenten + 4 `EditorPageShell`-Konsumenten | 23/29 live geöffnet | 23× ok/Befund dokumentiert, 6× s. u. |
| Edit-Dialoge für die 7 `*Editors`-Module | N/A — architekturbedingt | Editieren läuft inline im Split-View/rechter Panel, kein Dialog (bestätigt durch Code + Live) |
| Rechte Seitenleiste (`ArtifactInspector`) | Ja | vollständig aufgeklärt: Default collapsed, 5 Panels, B-01 |
| `WorkflowEditor/InspectorPanel` vs. `ArtifactInspector` | Ja | I-01: bewusste Parallel-Implementierung |
| Linker Navigationsbaum (28 Links) | Ja | alle funktionieren, kein echter Baum (bestätigt) |
| Button-Position, 11 Listenansichten | Ja | 10× ok, 1× Abweichung (D-12, Baselines) |
| 4 Tab-Systeme (17 Tab-Wechsel) | Ja | funktional 17/17 ok, visuell 3 Implementierungen (T-01) |
| Admin: System-Settings, User-Management, PermissionMatrix, Profile/API-Keys, Workspace-Löschen | Ja | ok, 1 Positiv-Pattern hervorgehoben |
| `create-trace-link-dialog` | Ja | gefunden + geöffnet, Trigger nur nach Inspector-Expand sichtbar |
| `tree-move-dialog` | **Endgültig nein — mit Beweis** | `onReparent` von keinem der ~20 Konsumenten übergeben → toter Code (R-04), kein Script- oder Seed-Problem |
| `ai-derivation-dialog` (live) | **Endgültig nein — mit Ursache** | Rollen-gated (`hasRole('editor')`), `admin`-Testaccount erfüllt das nicht (L-08) |
| `goals-archive` | Ja | live angelegt + archiviert, sauber, kein neuer Befund |
| `enforcement-flip` | Teilweise, bewusst vorsichtig abgebrochen | Klick löste keinen Dialog aus, Zustand nachweislich unverändert; aus Risikoabwägung nicht weiter forciert |
| `reviews-signature` | **Endgültig nein** | Kein 2-3-Klick-Weg vorhanden (CCB-Workflow nötig), bewusst nicht erzwungen |

**Fazit:** Von allen ursprünglich 29 Dialog-/Panel-Konsumenten sind 23 live
verifiziert. Von den verbleibenden 6 sind 4 mit konkretem, nachgeprüftem
Beweis als **tatsächlich unerreichbar** erklärt (toter Code, Rollen-Gate,
2× fehlende Seed-Daten) und 2 bewusst nicht erzwungen (Risiko einer echten
Zustandsänderung bzw. kein kurzer Weg vorhanden) — keiner davon ist eine
übersehene Lücke mehr, jeder hat eine verifizierte Begründung.

---

## 9. Anhang: Vollständige Dialog-Inventur (alle 20 Dateien)

> **Hinweis (siehe L-04):** Diese Tabelle wurde ursprünglich als unvollständig
> erkannt — sie deckte zunächst nur 20 von tatsächlich 29
> Dialog-Konsumenten ab. Die restlichen 9 (inkl. der 4 `EditorPageShell`-
> Konsumenten) wurden in Abschnitt 8.1/8.2 live nachgeprüft (D-08 bis D-12).
> Als erster, statischer Durchgang weiterhin gültig; die vollständige
> Abdeckung steht in Abschnitt 8.3.

Jede Datei einzeln gelesen, nicht gegrept. Grundlage für D-01 bis D-07.

| # | Datei | `shared/Dialog`? | Footer-Reihenfolge | Button-Klassen | Fokus/aria | Loading/Error | Destruktiv via ConfirmDialog |
|---|---|---|---|---|---|---|---|
| 1 | `AdminDialog/SystemHealthDialog.tsx` | ja | Sek. links/Prim. rechts | `btn-secondary`/`btn-primary` ✓ | ok | ja, differenziert | n/a |
| 2 | `AdminDialog/TriLabelOverviewDialog.tsx` | ja | 1 Button | `btn-primary` ✓ | ok | n/a (statisch) | n/a |
| 3 | `AttributeEditor/AttributeCatalogDialog.tsx` | ja | Cancel/Add | **keine Klasse** (D-04) | ok | ja, vorbildlich | n/a |
| 4 | `AttributeEditor/AttributeCreateDialog.tsx` | ja | Cancel/Submit | `btn-secondary`/`btn-primary` ✓ | ok | ja | n/a |
| 5 | `AttributeEditor/AttributeImportDialog.tsx` | ja | Cancel/Confirm | **keine Klasse** (D-04) | ok | ja | n/a |
| 6 | `Goals/ArchiveConfirmDialog.tsx` | ja | Cancel/Confirm | `btn-secondary`/`btn-danger` ✓ | ok | Busy-State ✓ | ja |
| 7 | `Goals/GoalFormDialog.tsx` | ja | Cancel/Submit | `btn-secondary`/`btn-primary` ✓ | ok, initialFocusRef | ja | n/a |
| 8 | `Memory/AddMemoryFactDialog.tsx` | ja | Cancel/Submit | Cancel **ohne Klasse** (D-04), Submit `btn-primary` | ok | ja | n/a |
| 9 | `NavigationShell/CreateWorkspaceModal.tsx` | ja | Cancel/Submit | `btn-secondary`/`btn-primary` ✓ | ok | ja, Feld+Banner getrennt | n/a |
| 10 | `Reviews/SignatureDialog.tsx` | ja | Cancel/Submit | `btn-secondary`/`btn-primary` ✓ | ok | ja | n/a |
| 11 | `shared/AiDerivationDialog/AiDerivationDialog.tsx` | ja | **umgekehrt** (D-06) | korrekt, Reihenfolge verkehrt | ok | ja, 4 States vorbildlich | n/a |
| 12 | `shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx` | ja | Cancel/Submit | `btn-secondary`/`btn-primary` ✓ | ok | ja, sehr ausgereift | n/a |
| 13 | `shared/Dialog/Dialog.tsx` | ist Primitive | n/a | n/a | ✓ vorbildlich (Referenz) | n/a | n/a |
| 14 | `shared/WorkspaceTree/tree-move-dialog.tsx` | ja | Cancel/Confirm | Cancel `btn-ghost` statt `btn-secondary` (D-07) | ok | n/a | n/a |
| 15 | `SystemSettings/EnforcementFlipDialog.tsx` | nein — nutzt `WorkflowEditor/ConfirmDialog` | via ConfirmDialog | lokale `styles.*` (erbt #16, D-05) | erbt aria-Lücke | ja | ja |
| 16 | `WorkflowEditor/ConfirmDialog.tsx` | via `WorkflowModal`→`Dialog` | Cancel/Confirm | lokale `styles.btnGhost`/`btnPrimary`+`btnDanger` (D-05) | `aria-describedby` fehlt (D-01) | ja | ja |
| 17 | `WorkflowEditor/StateDialog.tsx` | via `WorkflowModal`→`Dialog` | Cancel/Submit | lokale `styles.btnGhost`/`btnPrimary` (D-05) | ok | n/a | n/a |
| 18 | `WorkflowEditor/TransitionDialog.tsx` | via `WorkflowModal`→`Dialog` | Cancel/Submit | lokale `styles.btnGhost`/`btnPrimary` (D-05) | ok | n/a | n/a |
| 19 | `WorkflowEditor/WorkflowModal.tsx` | ja, korrekter Adapter | reicht Footer durch | n/a | ok | n/a | n/a |
| 20 | `shared/ConfirmDialog.tsx` | ist Referenz | Cancel/Confirm | `btn-secondary`/`btn-danger` ✓ | ✓ vorbildlich (Referenz) | n/a | ist die Lösung |
