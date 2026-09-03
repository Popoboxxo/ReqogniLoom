# UI-TIEFAUDIT — ReqogniLoom Frontend (jede Maske, jeder Dialog, jeder Button)

**Datum:** 27.08.2026
**Art:** UI-Exklusiv-Vollaudit (read-only, keine Code-Änderungen)
**Vorgänger:** SYSTEMAUDIT_2026-08-27.md (System-Gesamtaudit); dieses Dokument vertieft Bereich 4.4 (Frontend) auf Element-Ebene.
**Methodik:** 8 parallele Deep-Dive-Reviews über alle 41 Component-Areas; jede Quelldatei gelesen (nicht gesampelt); jeder Button/Dialog/Formular-Input enumeriert mit `Datei:Zeile`; Kreuzverifikation der Shared-Primitives (Dialog.tsx, use-focus-trap.ts, ConfirmDialog, EmptyState, PageHeader, ListToolbar) und der API-Schicht (client.ts, api/*).
**Grenze:** Statisches Code-Audit — die App lief nicht (Docker-Stack aus); visuelle/interaktive Laufzeitprüfung nicht möglich. Playwright-E2E liefert die Laufzeit-Dimension separat.

---

## 1. Executive Summary

**Gesamturteil:** Das UI ist architektonisch deutlich stärker als der Durchschnitt: Dialog-A11y-Infrastruktur auf Referenzniveau, ~86 % Testid-Abdeckung, ausgeprägte Empty-/Error-State-Differenzierung, Virtualisierung überall. Die kritischen Probleme sind **keine Design-Mängel, sondern Lücken im Bediensschutz**: 1 Blocker (Interview-Timeout), Editoren mit Datenverlust-Risiko (Graph-Editor), destruktive Aktionen ohne Bestätigung, tastatur-unbedienbare Listen und ein funktional nicht erreichbarer Requirement-Delete.

| Dimension | Note | Kernurteil |
|---|---|---|
| Dialog-/A11y-Infrastruktur | **A** | shared Dialog + Focus-Trap erfüllen vollständigen Kontrakt, unit-getestet (~20 Assertions); alle 33 Dialog-Instanzen erben davon |
| Testid-Kultur | **B+** | ~410 Button-Slots, ~55 ohne testid (~86 %); Lücken konzentriert in Shared-Primitives mit dynamischen Props |
| State-Disziplin (loading/error/empty) | **A−** | role=status/alert durchgängig, EmptyState mit 6 typsicheren Varianten; Ausnahmen: DashboardViews, Metrics ohne Empty-State |
| Datenverlust-Schutz (Dirty-Guards) | **D+** | nur Requirements + Architecture geschützt (#672); Needs, TestCase, Workflow-Dialoge, Graph-Editor, PermissionMatrix ungeschützt; 0× beforeunload repo-weit |
| Tastatur-/SR-Bedienbarkeit | **C** | WorkspaceTree/Canvas exzellent; aber 6 Listen/Autocomplete mouse-only, SplitView-Resize mouse-only |
| Destruktive Aktionen | **C−** | 3 Muster parallel (ConfirmDialog / Inline-2-Step / window.confirm) + **6 destruktive Aktionen ganz ohne Bestätigung** |
| i18n | **C+** | Parität DE/EN maschinell erzwungen, aber ~60 Hardcode-Zeilen + 3 fehlende Keys mit sichtbarem Roh-Output (`adrs.summary` etc.) |
| Konsistenz (Buttons/Toasts/Loading) | **C** | 5 Button-Stil-Systeme, 4 duplizierte Toast-Systeme, 4 Loading-Pattern — kein zentrales System |
| Funktionsvollständigkeit | **B−** | TestRun-Result-Erfassung existiert nicht im SPA; Requirement-Delete nicht erreichbar; ADR-Supersede-Flow fehlt im UI |

**Wichtigste Einzelbefunde (P0):** Interview-LLM-Calls brechen nach 30s (BLOCKER) · Graph-Editor verliert alle Edits bei Navigation (kein Autosave/Guard) · Canvas-Delete-Key löscht Objekte während man in anderen Feldern tippt · 6 destruktive Aktionen ohne Confirm (User-Deactivate, Tenant-Admin-Grant, Rollen-Suspend, Custom-Field-Delete, Theme-Delete, Trace-Link-Delete) · Requirement-Delete aus UI nicht erreichbar (Dead Code) · Architecture-Update sendet kein `expected_version` → 409-Conflict-Schutz in der UI wirkungslos.

---

## 2. Methodik, Scope und Korrektur zum Vorgänger-Audit

**Abgedeckte Masken (37 Routen + Overlay):** Dashboard, Needs, Requirements, Architecture, Traceability, Impact, Baselines, Reviews, ADRs, Risks, Issues, TestCases, TestRuns, Import (CSV/ReqIF/Export), ICDs, Diagramme (+Canvas/Mermaid/Graph-Editoren), Metrics, Audit, WorkspaceSettings (5 Tabs/14 Sektionen), SystemSettings (4 Tabs/22 Dateien), UserManagement, Goals, Interviews (Liste+Detail+Chat-Overlay), Glossary, Workflows (Editor + Status-Editor), Profile, Login, Workspace-Erstellung.

**Korrektur zum Vorgänger-Audit (SYSTEMAUDIT_2026-08-27.md, Abschnitt 4.4 / F-02-Liste):**
Die dort gemeldete Lücke „GraphToolbar.tsx:45–103 — 6 Buttons ohne data-testid" ist **falsch**. Die Nachprüfung ergab: **alle 6 Toolbar-Buttons haben Testids** (`graph-toolbar-add-node`, `graph-toolbar-auto-layout`, `graph-zoom-in`, `graph-zoom-out`, `graph-fit-view`, `graph-toggle-grid`, mit role=toolbar + aria-label am Container). Die realen Graph-Editor-Lücken sind: kein Unsaved-Guard, Inspector-Felder ohne Label-Assoziation, Edges nicht tab-reachabel.

---

## 3. Gesamtstatistik

| Metrik | Wert |
|---|---|
| Auditierte Masken/Views | ~40 (inkl. 4 Vollbild-Editoren + Chat-Overlay) |
| Dialog-Instanzen (auf shared Dialog) | **33** — alle mit vollem A11y-Vertrag |
| Non-Modale Overlays/Menüs | 8 (Sidebar-Switcher, Search-Dropdown, PageHeader-Overflow, VersionPanel-Menü, TraceSpine-Panel, Mobile-Drawer, Export-Dropdown, Chat-Panel) |
| Native `window.confirm()`-Stellen | **~15** (BaselinesView:170, GlossaryView:196, SystemSettings:68/103/107, UserProfileSettings:66/140, WorkspaceSettings ×3, DiagramView:41/268, PermissionsSection:335, WorkflowPermissionsSection:152/220, Memory-Reset) |
| Destruktive Aktionen **ohne jegliche** Bestätigung | **6** (User-Deactivate, Tenant-Admin-Grant/Revoke, Rollen-Suspend, Custom-Field-Definition-Delete, Theme-Palette-Delete, Trace-Link-Delete) |
| Button-Slots auditiert | ~410 statisch + dynamische Reihen |
| Buttons **ohne** data-testid | ~55 (~14 %), Konzentration: TracePanel (11), shared dynamische Props, 4 Save-Buttons (adr/risk/issue/glossary), Logout, NeedForm-Save |
| `beforeunload`-Guards repo-weit | **0** |
| i18n-Hardcode-Lücken | ~60 Zeilen über alle Bereiche (davon 3 mit sichtbarem Roh-Key-Output) |

---

## 4. Konsolidierte Prioritäten

### P0 — blockierend / Datenverlust / Sicherheit der Bedienung

| # | Befund | Ort |
|---|---|---|
| 1 | **[BLOCKER] Interview-LLM-Calls mit 30s-Timeout statt 180s** — `interviewsApi.chat/propose/formalize` übergeben kein `timeoutMs`; `/interviews/` fehlt in `_LONG_RUNNING_PATH_SEGMENTS` → reale LLM-Latenz >30s bricht Interviews mit generischer Fehlermeldung ab | InterviewChatPane.tsx:94–107 + api/client.ts:156–163 |
| 2 | **[HIGH] Graph-Editor: kompletter Edit-Verlust bei Navigation** — kein Autosave, kein Dirty-Indicator, kein `beforeunload`/`useBlocker`; Back-Button navigiert sofort. Gegensatz: CanvasEditor (Autosave 5s) und MermaidEditor (2s-Debounce) sind abgesichert | DiagramGraphEditorPage.tsx:309–317 |
| 3 | **[HIGH] CanvasEditor: globales Delete/Backspace-Keydown löscht selektierte Objekte während man in beliebigen anderen Feldern tippt** — document-Listener prüft nur `active?.isEditing`, nicht das Event-Target; GraphCanvas.tsx:137–138 macht es korrekt | CanvasEditor.tsx:1064–1078 |
| 4 | **[HIGH] TestRun-Result-Erfassung existiert nicht im SPA** — `addResult`/`addResultsBulk` (api/test-runs.ts:46/68) haben null Aufrufer; TestRunDetailEditor ist read-only. Results nur via REST/MCP/CI erfassbar | TestRunDetailEditor.tsx |
| 5 | **[HIGH] Requirement-Delete aus der UI nicht erreichbar (Dead Code)** — Confirm-Overlay existiert (`req-confirm-delete-btn`), aber `setConfirmDeleteId` wird nie ≠ null gesetzt; kein Row-Delete-Trigger | RequirementList.tsx:144/267–311 |
| 6 | **[HIGH] NeedForm: kein Dirty-Guard + CustomFields-Contamination-Bug** — Need-Wechsel verwirft Edits stumm; `CustomFieldsEditor` ohne `key={need.id}` spliced stale Rows des Vorgängers in den neuen Need (#673-Bugklasse, Fix-Muster existiert in RequirementForm.tsx:917) | NeedForm.tsx:38–160/413–417 |
| 7 | **[HIGH] TestCaseForm: Unsaved-Changes-Verlust beim Maskenwechsel** — kein Dirty-Check/Guard; Kontrast: RequirementEditors hat `req-unsaved-changes-dialog` exakt dafür | TestCaseForm.tsx:33–41 |
| 8 | **[HIGH] Architecture-Update sendet kein `expected_version`** — Optimistic-Locking-Schutz (Backend 409) in der UI nie auslösbar; VersionBadge zeigt Version nur an | api/architecture.ts:80–96 |
| 9 | **[HIGH] 6 destruktive Aktionen ohne Bestätigung:** User-Deactivate, Tenant-Admin-Grant/Revoke (UserManagement.tsx:267–284), Rollen-Suspend (PermissionsSection.tsx:541), Custom-Field-Definition-Delete (CustomFieldsSection.tsx:235), Theme-Palette-Delete (ThemeManagementSection.tsx:100–102), Trace-Link-Delete (TraceLinkPanel.tsx:180–194) |
| 10 | **[HIGH] Tastatur-unbedienbare Listen/Autocompletes:** BaselinesView-Liste (`li onClick`, BaselinesView.tsx:395–434), TestRunsList-Items (`li onClick`, :457–517), Glossary-Zeilen (:434–439), Risk-Owner-Autocomplete (`div onClick`, RiskForm.tsx:302–321), ICD-Similar-Items (IcdDetailPane.tsx:459–477), ImpactView-Baum ohne tree-Rolle |
| 11 | **[HIGH] Fehlende i18n-Keys `adrs.summary`/`risks.summary`/`issues.summary`** — PageHeader rendert die Roh-Keys als Seitensummary (Keys existieren in keinem Locale) | AdrEditors.tsx:137, RiskEditors.tsx:134, IssueEditors.tsx:134 |

### P1 — zeitnah (UX-Korrektheit)

- **Confirm-Pattern-Vereinheitlichung:** ~15 `window.confirm()`-Stellen vs. shared ConfirmDialog (das neue Themes-System und Baselines tangierend).
- **GH-513-Override ohne Rollen-Gating im UI** — Panel erscheint für alle; Nicht-Berechtigte erhalten erst nach Submit einen 403-Rohstring (BaselinesView.tsx:608–643).
- **Preset-Downgrade ohne Warnung** — Radio-Wechsel extended→minimal feuert sofort (WorkspaceSettings.tsx:397).
- **MermaidEditor persistiert syntaxfehlerhafte Quelle** — Autosave prüft `isDirtyRef`, aber nicht `validationError` (MermaidEditor.tsx:320–352).
- **CreateTraceLinkDialog: Escape schließt während isSubmitting** (create-trace-link-dialog.tsx:484–486) — analog ConfirmDialog ohne isSubmitting-Guard (ConfirmDialog.tsx:43–59).
- **Decompose-Draft-Verlust via Escape/Backdrop** — generierter AI-Draft wird kommentarlos verworfen (ArchitectureEditors.tsx:757–772).
- **MainGoal-Generate ohne Busy-State** — Doppelklicks feuern parallele LLM-Requests (MainGoalPanel.tsx:187–194); kein `is_mock_fallback`-Indikator.
- **Goals: `change_reason` als generierter String statt User-Prompt** — ArchiveConfirmDialog hat keine Textarea; Audit-Gate umgangen (GoalsPage.tsx:229–234).
- **Label-Assoziationen gebrochen** (Kluster): DeriveRequirementForm, CreateTraceLinkDialog (source/target), MarkdownPreview-Textarea (id fehlt trotz `htmlFor="req-description"`), ReqTraceLinkPanel-Selects, GraphInspectorPanel (alle Felder), Adr-/Risk-/IssueForm (mehrere), AttributeVisibilityAdmin (28 Checkboxen ohne accessible name), restore-confirmation-input (sicherheitskritisch, nur placeholder), prompt-variable-inputs.
- **Interview: Chat-Transcript ohne `role="log"`/`aria-live`**; Widget-Toggle ohne `aria-expanded`/`aria-controls`; Grounding-Kandidaten ohne confirm/ignore-UX (Backend-API existiert).
- **A11y-Detailverletzungen:** WorkspaceCard Enter-only (kein Space), Sidebar-Search placeholder-as-label, Mobile-Overlay nicht tastatur-schließbar, RightSidebar-Resize + SplitView-Resize + Workflow-Inspector-Resize mouse-only, TransitionEdge/GraphEdge `tabIndex=-1`, RightSidebar 3 tote Icon-Buttons (kein onClick), TraceSpine-Warnung ohne aria-label.
- **WorkflowEditorPage: Dialog-Drafts verloren bei Escape/Backdrop; Toast-Timer ohne Cleanup** (setState-after-unmount möglich).
- **CSV-Import: kein Partial-Success-Zustand, keine Row-Preview, kein Column-Mapping**; Fehlerliste auf 10 gekappt (CsvImport.tsx:341–375).
- **useRequirementData verschluckt Listen-Fehler** — Ladefehler sieht aus wie leere Liste (useRequirementData.ts:76; Kontrast useNeedData korrekt).
- **ADR-Supersede-Flow (REQ-150) im UI nicht vorhanden** — kein Button, keine superseded-by-Anzeige.
- **Manueller Derive (Need): partieller Fehler ohne Rollback/Nachricht** — Requirement ohne Link bleibt verwaist; AI-Accept analog (Fortschritt nicht getrackt).
- **ADR-Titel-Placeholder zeigt Need-Text** („e.g. As a user, I need…", AdrEditors.tsx:243) + „--"-Placeholder-Müll (3 Stellen).
- **Reviews: Ziel-State als Rohtext** (`toTitleCase("Freigegeben")`), Approver sieht nicht, warum Approve disabled ist.
- **MetricsDashboard: kein „nicht berechnet"-Empty-State, Thresholds nirgends angezeigt**, Help-Toggle ohne aria-label/aria-pressed, 5× duplizierter testid `metric-sparkline`, 4 rgba-Verstöße.
- **ImpactView: kein „0 Treffer"-State**; Suchinput placeholder-as-label.

### P2 — Hygiene/Konsistenz

- **5 Button-Stil-Systeme** (globale btn-Klassen, inline-styles, CSS-Module, EmptyState-eigene Klassen, Hybrid) → Konsolidierung auf `btn-primary/-secondary/-danger/-ghost`.
- **4 duplizierte Toast-Systeme** (WorkflowEditorPage, PermissionDefaultsTab, audit-dashboard, DiagramGraphEditorPage; 3–4s-Timings unterschiedlich) → zentrales Toast-Primitiv.
- **4 Loading-Patterns** (Spinner-Primitiv, Label-Swap, Skeleton, Text-p) — Spinner wird von genau den Komponenten nicht genutzt, die ihn definieren.
- **Dead Code:** TraceabilityPanel.tsx (ungenutzt), Testcases/TestcaseList.tsx (verwaist, falsches Status-Vokabular), TraceLinksForm.tsx (705 Zeilen, nur Selbsttest), SimilarIcdsPanel.tsx (toter Jaccard-Duplikat), toter Delete-Dialog in ArchitectureEditors.tsx:709–754.
- **Testid-Lücken** (~55): Logout, TracePanel-Chips (11), 4 Save-Buttons, NeedForm-Save, Dialog-Cancels (req/tc/icd/diagram), API-Key-Dismiss, VersionPanel-Retry, PNG/SVG-Export-Menuitems, Memory-Dialog-Cancels, AttributeVisibilityAdmin.
- **i18n-Backlog (~60 Zeilen):** MismatchReviewTable (10+), DefaultStatusBadge (4), ErrorBoundary (4), tag-input (2), WorkspaceTree (6), CanvasEditor-Swatches (4), CsvImport (3), ICD-Interface-Types (6), GraphInspectorPanel-Enums, InterviewWidget/ChatPane/ArtifactPane (6), WorkspaceAdminSection (2), UserProfileSettings-VISIBILITY_LABELS, StatusBadge-EN-Defaults, rohe Enum-Werte in Selects (risk/issue/graph/icd), Status-Darstellung Goal (3 Schreibweisen derselben Info).
- **statusBadge.ts:** gleiche Badge-Varianten für Run-/Result-/Workflow-Status; `blocked`/`skipped` fehlen → neutral-Fallback.
- **TestRunsList:** kein Select-All/Suche im TestCase-Picker; `ci_job_id` im Payload ohne UI-Feld; Close-Run-Confirm nennt Irreversibilität nicht.
- **Version-Restore fehlt** (VersionPanel nur switch/compare) — Produktentscheidung nötig.
- **Audit-„Adopt" ohne Bestätigung/Undo** (audit-dashboard.tsx:632–642).
- **SplitView `classList.add('dragging')` ohne wirksames CSS** (kein visuelles Feedback).
- **SystemHealthDialog doppelter Scroll-Lock** (Konflikt mit Dialog-Unlock).
- **Tabs ohne Arrow-Key-Navigation** (SystemSettings, PresetSegmentedControl, WorkspaceSettings).
- **RequirementTreeNode: kein Retry nach Child-Ladefehler**; `traceability.cycleNode`-Key fehlt in beiden Locales.
- **GlossaryView: keine Versions-/Diff-UI** (API vorhanden); window.confirm-Delete.

---

## 5. Detail-Sectionen je Maskengruppe

### 5.1 NavigationShell + Dashboard + Shared Primitives

**Inventar:** 13 Dialog-/Overlay-Instanzen, ~45 feste Button-Slots + ~10 dynamische Muster, 7 Formulare.

**Dialog-Vertrag `<Dialog>` (Referenzimplementierung, Dialog.tsx:114–160 + use-focus-trap.ts):** role=dialog + aria-modal + aria-labelledby (useId) + describedby optional, Portal → document.body, Scroll-Lock mit Restore, Backdrop-Mousedown-Guard, Escape mit stopPropagation (nested-safe), Fokus-Restore, initialFocusRef, focusin-Safety-Net. Gaps: kein `inert` hinter dem Overlay; z-index nur via CSS-Module.

**Wesentliche Befunde:** Logout ohne testid (HIGH) · TracePanel 11 Buttons ohne testid (HIGH) · Trace-Link-Delete ohne Bestätigung (HIGH) · WorkspaceCard Enter-only (MEDIUM) · RightSidebar 3 tote Icon-Buttons + Resize ohne Keyboard (MEDIUM) · CreateTraceLinkDialog Escape während Submit (MEDIUM) · DeriveRequirementForm Labels/Alert (MEDIUM) · ConfirmDialog ohne isSubmitting-Guard (MEDIUM) · ErrorBoundary zeigt rohes `error.message` (MEDIUM) · 15 i18n-Lücken (LOW).

**Stärken:** Dialog.test.tsx mit ~20 Assertions (Tab-Cycling beide Richtungen, focusin-Netz, Scroll-Lock, Fokus-Restore); WorkspaceTree = vollständige ARIA-Treeview (Roving Tabindex, ↑↓←→Home/End/`*`/Letter-Jump, virtualizer-aware Fokus, ~60 Keyboard/D&D-Assertions, D&D-Zyklus-Guard mit demselben Helper wie der Parent-Dropdown); EmptyState als typsichere Discriminated-Union über 6 Zustände inkl. 300ms-Skelettdelay; TraceSpine mit Dead-Link-Guard; BannerStack mit sessionStorage-Dismiss; Sidebar mit Scroll-Affordance (#168) und Sprach-Toggle-Gate (BUG-01/F-02/F-04/R-01).

### 5.2 Requirements + RequirementsList + Needs

**Inventar:** 3 SplitView-Masken, 5 Dialoge (Create/Unsaved/TestCase-Derive/TraceLinkCreate/Confirm), ~40 Buttons; ModalDialogBase (generisches Inline-Form-Primitive, 32 Tests) heißt „Modal", ist aber inline ohne role=dialog/Focus-Trap.

**Flow-Verdict Requirements vs. Needs:** Requirements-Flow robust (Dirty-Tracking #672/#700, Tree-Nav-Guard, Same-ID-Refetch-Race gefixt, Save-Fehler sichtbar #344, AI-Derive mit Zero-Draft-Fall #311); **Needs hinkt 2–3 Fix-Generationen hinterher** (kein Dirty-Tracking, kein Wechsel-Guard, kein CustomFields-#673-Fix, kein Submit-Lock beim Create). Requirements-Delete kaputt (P0-5). AI-Flows fehlen Feedback-Tiefe: **kein Mock-Fallback-Indikator, kein Cancel, kein Client-Timeout** (INFO —_backend liefert `is_mock_fallback`, kein UI-Konsument).

**Stärken:** Vorbildliche Dialog-/Feldlevel-Validierung mit „erst nach Save-Versuch alarmieren"-Disziplin (N-01/N-02); usePersistedListState workspace-scoped (Requirements); Filter-Reset-Unterscheidung empty vs. no-match; SimilarRequirementsPanel mit expliziten Degradations-States (no-embedding/unavailable/error/empty); Needs: Human-in-the-Loop-Derive mit editierbaren, selektierbaren Drafts (#678 Accessible Names), listAll-Pagination + Platzhalter-Workspace-Guard.

### 5.3 Architecture + Decompose + SplitView + ImpactView + PermissionMatrix

**Inventar:** 5 Dialoge (create/decompose/bundle-export/legend/unsaved) + toter Delete-Dialog; ~27 Buttons; DecomposePanel **ohne Unit-Tests**.

**Decompose-Verdict:** Sauberes Draft-Staging (Generate → Review-Liste mit Link-Schätzung n×3 → Commit → Success-Box mit counts + verified_rules; Commit-Fehler setzt Phase zurück, Draft bleibt erhalten). Löcher: Escape/Backdrop verliert Draft (MEDIUM), I1–I5-Invariant-Verstöße als unstrukturierter Rohstring statt Findings-Liste, breadth/depth können 0/NaN werden (Backend-Cap 10 nur serverseitig), 0 Tests.

**409-Conflict-UX: nicht vorhanden** — `architectureApi.update` sendet kein `expected_version`; fiktiver 409 würde nur als `role="alert"`-Rohstring erscheinen (P0-8).

**Stärken:** WorkspaceTree-ARIA-Referenz; Dirty-Machinery #672/#673 durchgetestet (entity-reset, same-id-refetch-sicher, stale-splice-Guard via `key={element.id}`); ImpactView #415 mit Pfad-Zykluserkennung (Badge + disabled Toggle + Tooltips für beide Disable-Gründe) und Root-Titel-Selbstheilung; Role-vs-ElementType-Verwechslung (#422) dreifach entschärft (Tooltip, Form-Hint, Legende + Test); PermissionMatrix mit geschlossener Form + Save nur bei dirty.

**Befunde:** SplitView-Divider mouse-only (HIGH) · toter Delete-Dialog (MEDIUM) · Type-Autocomplete nicht tastaturbedienbar (MEDIUM) · Description-Textarea ohne Label (MEDIUM) · ASIL/MoB/„— Not set —" hardcoded (MEDIUM) · Mobile-Tabs „List"/"Detail" hardcoded + No-op-Klick (MEDIUM) · ImpactView 0-Treffer-State + placeholder-label + Baum ohne tree-Rolle (MEDIUM) · PermissionMatrix ohne Unsaved-Schutz (MEDIUM).

### 5.4 TestCases + TestRuns + MetricsDashboard + AuditDashboard

**Inventar:** 36 direkte Buttons, 34 mit testid (94 %); 2 echte Dialoge; Inline-Confirms statt ConfirmDialog.

**Kernbefunde:** Keine Result-Entry-UI (P0-4) · TestRunsList-Items nicht tastaturbedienbar (P0-10) · verwaiste TestcaseList mit falschem Status-Vokabular `draft|active|deprecated` (echter Lifecycle: `draft|ready|approved|deprecated`) · TestCaseForm Unsaved-Verlust (P0-7) · Close-Run-Terminalität nicht kommuniziert (MEDIUM) · statusBadge-Varianten-Kollision Run/Result/Workflow (MEDIUM) · Audit-„Adopt" ohne Confirm (MEDIUM) · 2 fehlende Testids (Dialog-Cancel, Save).

**MetricsDashboard:** Help-Toggle a11y (MEDIUM), Sparkline `aria-label="trend"` identisch ×5 + `metric-sparkline` 5× dupliziert (MEDIUM), 4 rgba-Verstöße bestätigt (MEDIUM), **kein „nicht berechnet"-Empty-State** (MEDIUM), **Thresholds nirgends sichtbar** — Status nur über Farbpunkt (MEDIUM), Error-Banner ohne eigenen Retry (LOW).

**AuditDashboard (815 Zeilen):** Transparente Kap-Behandlung (Truncation-Banner + echte Vor-Cap-Totals, BUG-15/M3), Modify-Zielauflösung mit Batch-Limit + Caching + graceful degradation, keine i18n-Verstöße (Backend-Strings roh angezeigt).

**Stärken:** Dialog mit unit-getestetem Modal-Vertrag; EmptyState 6-Varianten konsequent; Regressionstests für Audit-Fixes (GH-453, GH-451, BUG-15, #450, BUG-10); MetricsDashboard.i18n.test gegen echte Locale-Dateien (BUG-10); TanStack-Migration TestRuns sauber; Pagination-Fix `listAll` + Workspace-Guard in beiden Hooks.

### 5.5 ADRs + Risks + Issues + Glossary + Goals

**Inventar:** 6 Dialoge (3 Create + 2 Archive-Confirms + TraceLink), ~45 Buttons, 4 Save-Buttons ohne testid (P0).

**ADR-Flow-Verdict:** Decides-Link nur als generischer Weg über CreateTraceLinkDialog (alle 14 Typen, Default `derives-from` statt `decides`-Vorschlag) — mittel; **Supersession (REQ-150) im ADR-UI faktisch nicht existent** (kein Button/Anzeige; nur Filterwert); Version-Anzeige konsistent (VersionBadge + RightSidebar v{version}); Review-States sauber (allowed_transitions server-getrieben, status bewusst nicht gesendet #263, Reason-Prompt funktioniert — Kontrast zur Goal-Route).

**Goals-Flow-Verdict:** Lineage gut gelöst („Bearbeiten" = createVersion, Immutable-Hint im Dialog, History über ArtifactInspector, sequence_number im Tree, defensiver MainGoal-Anker-Fallback); **MainGoal-Generate ohne Busy-State + kein Mock-Fallback-Indikator** (`mainGoalApi.generate` liest `is_mock_fallback` nicht — Mock-Drafts sehen wie echte AI-Output aus); Approve direkt ohne Confirm (getestete Erfolgs-/Fehlerpfade, Draft-Hydration implementiert); **State-Namen-Dreiklang** (Button „Approve" EN, Badge roh „Freigegeben", Tree kapitalisiert) inkonsistent für EN-Nutzer; **Archive bestätigt** (Danger-Dialog, „Version bleibt in Historie"-Body) aber **change_reason wird NICHT abgefragt** — generierter String (P1); Reactivate ohne Undo-Hinweis.

**RiskForm-Lücken:** kein detection-Feld (1–10) trotz Backend/MCP-Schema, keine Risk-Matrix (probability×impact), risk_score nirgends angezeigt.

**Stärken:** Dialog-Primitiv erbt überall; server-getriebene Workflows statt Hardcoding (allowed_transitions, resolveBadgeVariant statt String-Match, Statusfilter aus Ist-Daten GH-453); ausgeprägte Empty-State-Differenzierung inkl. Regressionstests; 34 Tests allein im Goals-Bereich (Doppel-Submit-Guard, Workspace-Switch-Leaks, Draft-Hydration, Custom-Workflow-Transitions, Badge-Regression); Virtualisierung überall (64px-Rows).

### 5.6 Baselines + Reviews + AdminDialog + WorkspaceSettings + UserManagement + Profile/API-Keys

**Inventar:** 5 Dialoge + ~15 window.confirm, ~63 statische Buttons (60 mit testid), 14 WorkspaceSettings-Sektionen.

**Baseline-Verdict:** Gut mit 2 Lücken — Scope-Radios mit Live-Count (aria-live ✓), document verlangt Artifact (client+server), Diff-Legende + Before/After-Tabelle ✓, Compare A/B mit Guards ✓; **Liste nicht tastaturbedienbar** (P0-10) und **GH-513-Override ohne Rollen-Gating** (P1). Override-Spiegelung sauber (MIN_OVERRIDE_REASON_LENGTH-42 als Konstante, Sticky-Panel nach Reject, „unevaluable auditor not waivable"). **Baseline-Delete-Button IST vorhanden** (window.confirm) — Widerspruch zur Immutabilitäts-Erwartung, Produktentscheidung nötig.

**Review-Verdict:** Solid — Type-Filter über 13 Entity-Types (REQ-168, Goal/MainGoal-Override #372), Reason nur verpflichtend wenn requires_change_reason (Client-Blocking + Server-Revalidierung), Role-Gating via Disabled-State, Signature-Gate öffnet SignatureDialog (Password/TOTP, credential nie geloggt), Empty-State ✓; Schwächen: **keine Pagination der Queue** (unbegrenzte Liste), Viewer erfährt nicht warum Approve disabled ist, Ziel-State als Rohtext.

**Kritische Bedienschutze:** User-Deactivate/Tenant-Admin-Grant/Rollen-Suspend **ohne Bestätigung** (P0-9) · Custom-Field-Delete ohne Confirm (MEDIUM) · Preset-Downgrade ohne Warnung (MEDIUM) · restore-confirmation-input ohne Label (MEDIUM) · **#274-Forward-Compatibility-Guard** in LlmSettingsSection (unbekannter Provider als eigene Option + kein Provider-Echo im PATCH — verhindert silent config destruction; API-Key write-only mit password-masking; **kein Test-Connection-Button**).

**Stärken:** State-Disziplin (loading role=status, error role=alert, optimistic-toggle mit Revert bei 403, LAST_ADMIN-Fehler geparst + lokalisiert in 2 Bereichen mit identischem Muster); MCP-CopyableValue mit aria-label + Clipboard-Fail-Silent; 18 Testdateien/~90 Tests inkl. a11y-Regressionstests und BUG-Regressions-Guards (BUG-05, BUG-16, #372, #609, #706).

### 5.7 Diagramme (Canvas/Mermaid/Graph) + ICDs + CsvImport + Traceability

**Inventar:** 81 Button-Slots, 78 mit testid (96 %); 3 Dialoge; 4 Vollbild-Editoren.

**⚠ Korrektur zum Vorgänger-Audit:** GraphToolbar-Buttons haben alle Testids (s. Abschnitt 2).

**Editor-Datenverlust-Matrix:**

| Editor | Autosave | Dirty-Indicator | Route-Guard | Risiko |
|---|---|---|---|---|
| CanvasEditor | ✅ 5s (Retry-Loop, isDirty bleibt true) | ✅ | ❌ | MITTEL (Verlustfenster ≤5s) |
| MermaidEditor | ✅ 2s-Debounce | ✅ | ❌ | MITTEL (+ persistiert invalide Quelle — MEDIUM) |
| GraphEditor | ❌ keins | ❌ | ❌ Back sofort | **HOCH (P0-2)** |

Zusätzlich: **CanvasEditor globales Delete/Backspace ohne Target-Check** (P0-3); Infrastruktur für Guards vorhanden (i18n-Keys `editor.unsavedChangesTitle/Message` genutzt von Requirement/Architecture-Editors) wird aber nicht verdrahtet.

**CsvImport:** 13/13 Testids ✓; aber kein Partial-Success-Zustand (imported_count + errors gleichzeitig nicht darstellbar — Backend-Semantik offene Frage), keine Row-Preview, kein Column-Mapping, Dropzones nicht keyboard-bedienbar, Fehlerliste auf 10 gekappt.

**ICD:** ICD-Create vorbildlich (14 Felder mit htmlFor, Submit-Disable mit sichtbarem `icd-needs-elements-hint`, Immutability-Hint `icds.immutableHint` — ADR-ICD-01: kein Delete, nur New-Version); New-Version-Form inline (kein Dialog) mit 3 fehlenden Testids; Similar-ICDs `li onClick` mouse-only (pgvector-Variante wäre korrekt, aber toter Code).

**TraceabilityView:** Endpoint-Buttons (#425) keyboard-operabel + getestet; Coverage-Panel über ALLE Requirements (listAll, kein Page-Size-Verlust); Cycles role=alert; EmptyState empty/no-match getrennt; „Export PDF" hardcoded + PDF-Fehler nur console.error (MEDIUM).

**Stärken:** DOMPurify-sanitizeSvg auf allen dangerouslySetInnerHTML-SVG-Slots + htmlLabels:false gegen mXSS (mit Roundtrip-Tests); CanvasEditor volles Keyboard-Shortcut-Set (Delete/Escape/Ctrl+Z/Y dokumentiert im Status-Hint) + Undo/Redo mit Disabled-States; GraphNode role=button tabIndex=0 + deutsches aria-label, Rename-Input Enter=commit/Escape=cancel; i18n-Regressionstests pro View (BUG-07, BUG-06).

### 5.8 WorkflowEditor + WorkflowStatusEditor + SystemSettings + Interviews

**Inventar:** ~64 Buttons (52 mit testid), 9 Dialog-Instanzen + 3 Non-Dialog-Overlays.

**WorkflowEditor-Verdict (REQ-176–179, SCR-205):** Solid — jede Mutation durch Dialoge mit Busy-/Error-Slot; State/Transition-Delete + alle Destruktiven über Danger-ConfirmDialog ✓; allowed_roles/requires_change_reason/signature_gate pro Transition editierbar; **Reset-to-global lebt im WorkspaceSettings** (window.confirm ×2, DefaultStatusBadge hardcoded EN); **kein workflow_json-Raw-Editor** (0 Treffer) → Sync-Problem existiert nicht; Validierung backend-getrieben (409/400 → Dialog-Error); Viewer read-only + Edit-Toggle disabled mit Admin-Hinweis; Entity-Selector 9 Typen (Docstring „7" — Drift).

**WorkflowStatusEditor (REQ-160/161/169):** Change-Reason-Pflicht im UI erzwungen (Inline-Panel statt Dialog, Confirm disabled bis Text, getestet) — **Kontrast: Goal-Route nutzt dieses Muster nicht** (P1); nur erlaubte Transitions gerendert; History wird hier NICHT angezeigt (nur Reviews/ReviewHistoryPanel REQ-144); Load-Fehler degradiert still read-only (MINOR).

**SystemSettings:** Enforcement-Flip mustergültig (Count-Re-Fetch bei Open, Ack-Checkbox, Count-Echo an Backend, 409-STALE → Re-Confirm statt Silent-Retry) · Rollback als Single-Step-Browser-Confirm (dokumentierte Asymmetrie) · Mismatch-Review **read-only** (append-only by design, Filter + Pagination) · Theme-Delete **ohne Confirm** (MAJOR) · Banner ohne Live-Preview · Theme ohne Palette-Editor/Farbvorschau.

**Interview-Overlay:** Always-mounted auf jeder authentifizierten Route (NavigationShell.tsx:206–209), z-index 100, 360px/60vh bottom-right — bewusstes Floating-Panel ohne Backdrop, kein Focus-Steal beim Mount (open aus localStorage, Issue-#679-Resilienz getestet). **BLOCKER: 30s-Timeout** (P0-1) · **MAJOR:** Chat ohne role=log/aria-live, Toggle ohne aria-expanded/aria-controls, **Grounding-Kandidaten ohne confirm/ignore-UX** (Backend set_target/Grounding-Confirm existiert, Frontend nur passive Hints) · Formalize: ArtifactPane single (disabled bei missing_fields ✓) + Multi-Modus mit ProposalPreviewGraph + Double-Submit-Guard ✓; Abandon 2-Step-Inline-Confirm im Detail-Header (kein Dialog).

**Stärken:** A11y-Regressionstests inhaltlich stark (WorkflowEditorCanvas-a11y: Enter/Space an StateNode+Edge, Read-only-No-Ops; TransitionDialog: WCAG 4.1.2/3.3.2 Label-Verkettung; WorkflowStatusEditor: 6 Fälle inkl. REQ-169-Reason-Prompt; InterviewWidget: localStorage-Resilienz #679); 44 benannte Fälle in SystemSettings-Tests.

---

## 6. Cross-Cutting-Verdicts

| Achse | Verdict | Evidenz |
|---|---|---|
| **Testid-Naming** | **B+** | Konvention dokumentiert (docs/architecture/UI_STYLE_GUIDE.md:153, kebab-case, `create-<entity>-*`); meist verfolgt, gute Präfix-Gruppen; Brüche: Logout, TracePanel (11), 4 Saves, `new-` vs `create-`-Mischung; Coverage ~86 % |
| **Button-Varianten** | **C** | Kanonisch 4 globale Klassen (global.css:96–167, ratchet-geschützt), aber 5 parallele Stilsysteme |
| **Toasts/Feedback** | **D** | Kein zentrales System; 4 seiten-lokale Nachbauten mit konvergierendem Pattern (role+testid+auto-dismiss) aber 3–4s-Timings; Timer teils ohne Cleanup |
| **Loading** | **C−** | 4 parallele Muster; Spinner-Primitiv wird von den Komponenten nicht genutzt, die es definieren |
| **h1-Pattern** | **A** | PageHeader rendert genau 1 h1 (kommentiert); Eigen-h1s nur in Vollbild-Editoren; Smoke-Tests prüfen „exactly one h1" |
| **Route-Struktur** | **A−** | 37 Routen alle lazy, 6 dokumentierte Legacy-Aliase (#575/#609), Catch-All → /, konsistentes :id-Wrapper-Muster |
| **Dirty-Guards** | **D+** | Nur Requirements + Architecture (#672/#700); 0× beforeunload repo-weit; Infrastruktur (i18n-Keys, ConfirmDialog, useFormDirty) vorhanden, aber ungenutzt in: Needs, TestCase, Workflow-Dialoge, Graph-Editor, PermissionMatrix, CreateTraceLinkDialog |
| **Confirm-Patterns** | **C−** | 3 Muster parallel (ConfirmDialog / Inline-2-Step / window.confirm ×15) + 6 destruktive Aktionen ganz ohne |
| **Label-Assoziation** | **C** | Kluster: DeriveRequirementForm, CreateTraceLinkDialog, MarkdownPreview, GraphInspectorPanel, Adr/Risk-Form (Teile), AttributeVisibilityAdmin, restore-confirmation-input, prompt-variable-inputs |
| **Keyboard-Bedienbarkeit** | **C** | Exzellent: WorkspaceTree, CanvasEditor, GraphNode, Trace-Endpoints; unbedienbar: 5 Listen/Autocompletes, 3 Resize-Handles, ImpactView-Baum, Edge-Elemente (tabIndex=-1) |
| **role=log/live** | **C** | Chat-Transcript ohne aria-live; diverses Feedback ohne role=status (Saved-States, api-key-copy ohne Feedback) |
| **Enums im UI** | **C** | Rohe Werte in Selects (risk/issue/graph/icd/status-badge-Kontext) vs. humanisierte Badges — zwei Vokabularquellen (zwei Vokabularquellen) |

---

## 7. Stärken (über alle Bereiche)

1. **Dialog-A11y-Infrastruktur auf Referenzniveau** — shared Dialog + use-focus-trap mit ~20-Assertion-Test; alle 33 Dialog-Instanzen erben den vollen Kontrakt (Portal, ARIA-Triade, Tab-Cycling, Nested-Safety, Escape, Focus-Restore, Scroll-Lock).
2. **Testid-Kultur** — ~86 % Abdeckung mit exakten, dokumentierten Naming-Convention; dynamische Reihen durchgängig stabile per-ID-Testids (`req-row-{id}`, `version-row-N`, `audit-finding-{index}` …).
3. **State-Disziplin** — role=status/alert konsequent, EmptyState als typsichere 6-Varianten-Diskriminierte-Union mit korrekter empty/no-match-Unterscheidung, letzte-Error-Surfaces mit Retry.
4. **Regressionstest-Kultur mit Ticket-Traceability** — Tests referenzieren konkrete Bugs/Audit-Tickets (BUG-05/07/10/15/16, #340, #344, #372, #415, #422, #450, #453, #584, #609, #672, #673, #679, #700, GH-353, GH-453, GH-513); i18n-Parity + Kontrast-Gate + Button-Klassen-Ratchet maschinell erzwungen.
5. **Sicherheitsbewusstsein im UI-Code** — DOMPurify-sanitizeSvg + htmlLabels:false (mXSS, Roundtrip-getestet), API-Key write-only + password-masking + one-time-plaintext-Box (role=alert), #274-Forward-Compatibility-Guard, credential nie geloggt (SignatureDialog).
6. **Server-getriebene Workflows statt Hardcoding** — allowed_transitions bestimmen die sichtbaren Transition-Buttons überall; Statusfilter aus Ist-Daten; resolveBadgeVariant statt String-Match.
7. **Human-in-the-Loop AI-Flows** — Derive-Panel mit editierbaren/selectierbaren Drafts vor Persistenz; Zero-Draft-Fälle explizit; Enforce-Stop an Approval-Gates (policy=auto).

---

## 8. Empfehlungs-Roadmap (UI)

### Sprint 1 — Bedienschutz & Datenverlust (P0)
1. Interview-Timeout auf 180s (`_LONG_RUNNING_PATH_SEGMENTS` oder timeoutMs) — 1-Zeiler-Familie
2. Graph-Editor: beforeunload/useBlocker + Dirty-Indicator + optionales Autosave (Muster: CanvasEditor)
3. CanvasEditor: Target-Tag-Check im Delete/Backspace-Handler (Muster: GraphCanvas.tsx:137–138)
4. 6 Destruktive Aktionen auf ConfirmDialog/Inline-Confirm (User-Deactivate, Tenant-Admin, Rollen-Suspend, Custom-Field-Delete, Theme-Delete, Trace-Link-Delete)
5. Requirement-Delete verdrahten (vor Klärung mit Product: bewusst entfernt oder Regression?)
6. NeedForm: useFormDirty + Wechsel-Guard + `key={need.id}` (Muster: RequirementForm.tsx:917)
7. TestCaseForm: Dirty-Guard + Unsaved-Dialog (Muster: RequirementEditors)
8. Architecture-Update: `expected_version` senden + 409-Handling-UX
9. 5 Listen/Autocompletes keyboard-betreibbar machen (Baseline-Liste, TestRunsList, Glossary, Risk-Owner, ICD-Similar)
10. 3 fehlende i18n-Keys (adrs/risks/issues.summary) ergänzen

### Sprint 2 — UX-Korrektheit (P1)
11. Confirm-Pattern vereinheitlichen (15 window.confirm → ConfirmDialog)
12. GH-513-Override mit Rollen-Gating; Preset-Downgrade-Warnung
13. Mermaid: Autosave-Guard auf validationError
14. Escape/Backdrop-Guards für Draft-Dialoge (CreateTraceLinkDialog, Decompose, Workflow-Dialoge) + ConfirmDialog isSubmitting-Guard
15. Label-Assoziationen reparieren (9-Kluster-Liste, inkl. restore-confirmation-input)
16. Interview: role=log/aria-live, aria-expanded/aria-controls, Grounding confirm/ignore-UX
17. MainGoal-Generate Busy-State + Mock-Fallback-Indikator (inkl. Derive-Panels — Backend-Feld vorhanden)
18. Goals: change_reason-Prompt (ArchiveConfirmDialog + Textarea)
19. CSV: Partial-Success-Anzeige (nach Backend-Semantik-Klärung) + Dropzone-Keyboard
20. A11y-Detailbatch: aria-labels (Help-Toggle, Icon-Buttons, TraceSpine-Warnung), Enter+Space (WorkspaceCard), resize-keyboards (3 Handles), aria-pressed (Diff-Toggle)

### Sprint 3 — Konsistenz & Hygiene (P2)
21. Zentrales Toast-Primitiv (4 Systeme konsolidieren) + Button-Stil-Konsolidierung (5 → 1)
22. Testid-Lücken schließen (~55 Slots, Priorität: Logout, TracePanel, 4 Saves, NeedForm-Save)
23. i18n-Backlog (~60 Zeilen) + rohe Enums humanisieren (statusBadge-Label-Map)
24. Dead Code entfernen (TraceabilityPanel, TestcaseList, TraceLinksForm+Test, SimilarIcdsPanel, toter Architecture-Delete-Dialog)
25. statusBadge: eigene Varianten blocked/skipped + Kontext-Präfix Run/Result/Workflow
26. MetricsDashboard: Empty-State „nicht berechnet" + Threshold-Anzeige + sparkline-Testids
27. Produktentscheidungen: Version-Restore (VersionPanel), ADR-Supersede-UI, Risk detection/Matrix, Baseline-Delete-Button (Immutabilität), TestRun-Result-Entry-Grid

---

## Anhang A: Bewertungsskala
- **BLOCKER:** Feature bricht unter realistischen Bedingungen (Interview-LLM-Latenz).
- **HIGH:** Datenverlust, Sicherheitsrelevanz der Bedienung, E2E-blockierende Lücken, sichtbar falsche Ausgabe.
- **MEDIUM:** UX-Korrektheit (Guards, Labels, States, fehlende Bestätigungen mit Repair-Pfad).
- **LOW:** i18n, Kosmetik, Konsistenz.
- **INFO:** Bewusste Trade-offs, dokumentierte Limitierungen, Dead-Code-Kandidaten.

## Anhang B: Audit-Scope je Agent
1. NavigationShell + Dashboard + shared (66 Dateien) · 2. Requirements/Needs (30) · 3. Architecture/Decompose/SplitView/Impact/PermissionMatrix (20) · 4. TestCase/TestRuns/Metrics/Audit (23) · 5. ADR/Risk/Issue/Glossary/Goals (32) · 6. Baselines/Reviews/AdminDialog/WorkspaceSettings/UserManagement/Profile (49) · 7. Diagramme/ICD/CsvImport/Traceability (57) · 8. WorkflowEditor/WorkflowStatusEditor/SystemSettings/Interviews (69)

*Ende des Berichts. Alle Pfadangaben relativ zu `frontend/src` sofern nicht anders angegeben. Stand des Codes: Arbeitsverzeichnis zum Audit-Zeitpunkt.*
