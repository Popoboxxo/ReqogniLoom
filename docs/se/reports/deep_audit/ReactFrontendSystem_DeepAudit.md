# ReactFrontendSystem - Deep Test Coverage Audit

**Datum:** 2026-07-09
**System:** ReactFrontendSystem
**Pfad:** `frontend/src/`

Dieses Dokument enthält einen detaillierten Audit aller Testdateien im Abgleich mit den formalen Anforderungen aus `L2_ReactFrontendSystem_Requirements.md`. Das Ziel ist es, "Shallow Testing" (oberflächliches Testen, das nur Render-Befehle oder einfache Mocks prüft) zu identifizieren und konkrete Refactoring-Maßnahmen zu definieren.

---

## 1. `frontend/src/api/diagrams.test.ts`
* **Verknüpfte REQ-L2 ID:** Nicht explizit in L2, abgeleitet von REQ-L1-056 / REQ-L1-057
* **Name des Tests:** diagramsApi — Canvas Strokes / Mermaid Source
* **Aktueller Stand (Shallow?):** Ja. Es wird nur geprüft, ob die gemockten `apiClient`-Funktionen mit dem erwarteten Pfad aufgerufen werden. 
* **Akzeptanzkriterien:** (L1) Zuverlässiges Laden/Speichern von Diagrammen und Mermaid-Quellcode.
* **Exakter Refactoring-Bedarf:** Der Test muss um Fehlerbehandlungs-Szenarien (HTTP 400/500, Netzwerk-Timeouts) und Payload-Validierung erweitert werden. Reine "Mock wird mit X aufgerufen"-Tests verhindern keine Regressionsfehler im Datenmodell.

## 2. `frontend/src/components/canvas/CanvasEditor.test.tsx`
* **Verknüpfte REQ-L2 ID:** (Keine explizite L2-RF, abgeleitet von COMP-DS-006 / REQ-L1-056)
* **Name des Tests:** CanvasEditor & Stroke persistence
* **Aktueller Stand (Shallow?):** Sehr oberflächlich. Es wird nur getestet, ob Buttons im DOM existieren und ob das Klicken den internen State (Tool-Name im Status Bar) ändert. Die eigentliche Fabric.js-Canvas-Logik wird komplett durch Dummys ersetzt.
* **Akzeptanzkriterien:** Pinselstriche (Strokes) müssen auf der Canvas registriert, manipuliert (Undo/Redo) und persistiert werden können.
* **Exakter Refactoring-Bedarf:** Echte Drawing-Events auf einer Fabric.js-Instanz simulieren (Mousedown, Mousemove). Es muss verifiziert werden, dass die Canvas `isDirty` wird, dass `Undo`/`Redo` die tatsächliche Stroke-Historie verändert und dass das Auto-Save-Event mit echten Koordinaten gefeuert wird.

## 3. `frontend/src/components/mermaid/MermaidEditor.test.tsx`
* **Verknüpfte REQ-L2 ID:** (Keine explizite L2-RF, abgeleitet von COMP-DS-007 / REQ-L1-057)
* **Name des Tests:** MermaidEditor
* **Aktueller Stand (Shallow?):** Ja, reiner Component-Mount-Test. CodeMirror und Mermaid.js werden komplett gemockt. Es wird nur geprüft, ob Status Bars auftauchen und API-Mocks gerufen werden.
* **Akzeptanzkriterien:** Der Editor muss Code rendern, eine Vorschau generieren und bei fehlerhaftem Code Syntaxfehler anzeigen.
* **Exakter Refactoring-Bedarf:** Das Zusammenspiel zwischen Editor-Eingabe und Preview muss getestet werden. Anstatt CodeMirror komplett zu mocken, muss getestet werden, wie das System reagiert, wenn fehlerhafter Code eingetippt wird (Anzeige von `error_message` am richtigen DOM-Element).

## 4. `frontend/src/components/RequirementEditors/TraceabilityPanel.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-037 (TracePanel Component)
* **Name des Tests:** TraceabilityPanel
* **Aktueller Stand (Shallow?):** Extrem oberflächlich. Testet lediglich, ob hartcodierte Upstream/Downstream-Links im DOM auftauchen und Tooltips gesetzt werden.
* **Akzeptanzkriterien:** "A multi-select filter MUST let the user restrict both groups to one or more TraceLink types. Each link entry MUST show source/target artifact ID, type, direction, and suspect flag when applicable."
* **Exakter Refactoring-Bedarf:** 
  1. Tests für den **Multi-Select-Filter** hinzufügen (Filtern der Links nach Typ). 
  2. Rendering und Visualisierung des **`suspect` Flags** testen (fehlt komplett).
  3. Klick auf einen Link muss via `MemoryRouter` einen echten Navigationsevent (Routenwechsel) auslösen und geprüft werden.

## 5. `frontend/src/components/RequirementsList/ModalDialogBase.test.tsx`
* **Verknüpfte REQ-L2 ID:** L1-040 (Base Component für Listen)
* **Name des Tests:** ModalDialogBase (REQ-L1-040)
* **Aktueller Stand (Shallow?):** Moderat. Testet den React-Lifecycle und Error-States gut ab, vergisst aber wichtige non-visuelle Aspekte.
* **Akzeptanzkriterien:** Einheitliche UI/UX und funktionale Formularbedienung in Modals.
* **Exakter Refactoring-Bedarf:** Fokus auf Accessibility (A11y). Es fehlen Tests für Focus-Trapping innerhalb des Modals, das Schließen per `Escape`-Taste und das Absenden per `Enter`-Taste. 

## 6. `frontend/src/components/TestCases/TestcaseList.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L1-040 Phase 3 / REQ-L2-RF-019 (Listen-Pagination)
* **Name des Tests:** TestcaseList
* **Aktueller Stand (Shallow?):** Ja. Testet nur den simplen "Happy Path" (Laden, Neues Element erstellen, Error Mock). 
* **Akzeptanzkriterien:** Listen müssen skalierbar sein (REQ-L2-RF-019 fordert explizit Pagination und API-State in Listen).
* **Exakter Refactoring-Bedarf:** Der Test ignoriert Paginierung, Filterung und Sortierung. Refactoring: Steuerelemente für Pagination simulieren und testen, dass die API mit den korrekten Query-Parametern (`?page=2`) aufgerufen wird. 

## 7. `frontend/src/components/TestRuns/TestRunsList.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-AS-030 / REQ-L2-RF-019
* **Name des Tests:** TestRunsList
* **Aktueller Stand (Shallow?):** Ja, identisches Problem wie bei `TestcaseList.test.tsx`.
* **Akzeptanzkriterien:** Verwaltung von Test-Runs inkl. Listenansichten.
* **Exakter Refactoring-Bedarf:** Hinzufügen von Paginierungs-Tests. Zudem muss der UI-State-Wechsel getestet werden (z. B. wie die Liste reagiert, wenn ein TestRun den Status von `in-progress` auf `completed` wechselt).

## 8. `frontend/src/components/TraceabilityView/TraceLinksForm.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-006 (Traceability-Anzeige)
* **Name des Tests:** TraceLinksForm
* **Aktueller Stand (Shallow?):** Ja. Es wird primär die Validierung des Formulars (Source != Target) und der API-Call getestet.
* **Akzeptanzkriterien:** "Traceability-Anzeige visualisiert bidirektionale TraceLinks [...] Link-Typ als Label darstellen und per Klick navigieren".
* **Exakter Refactoring-Bedarf:** Der visuelle Aspekt der Liste (Gruppierung nach Link-Typ, Anzeige der Labels) wird nur über das Vorhandensein eines Test-IDs verifiziert. Es muss konkret verifiziert werden, dass die Labels korrekt übersetzt gerendert werden und die UI bei Klick tatsächlich navigiert (E2E-artiger Router-Test).

## 9. `frontend/src/test/ArchitectureEditors.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-004
* **Name des Tests:** ArchitectureEditors
* **Aktueller Stand (Shallow?):** Teilweise Shallow. Prüft Title und Type-Select, vergisst aber wesentliche Teile der Akzeptanzkriterien.
* **Akzeptanzkriterien:** "Description in Markdown editierbar. Verknüpfte Requirements in einer Seitenleiste sichtbar. Unit-Test: Render ArchitectureEditor [...] alle Felder sichtbar und editierbar".
* **Exakter Refactoring-Bedarf:** Der Test ignoriert das Markdown-Feld und die Traceability-Seitenleiste. Er muss so erweitert werden, dass Texteingaben in den Markdown-Editor simuliert werden und geprüft wird, ob die verknüpften Requirements im RightSidebar / TracePanel auftauchen.

## 10. `frontend/src/test/AuthGate.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-010 (REST-API-Kommunikation mit Bearer-Token-Authentifizierung)
* **Name des Tests:** AuthGate
* **Aktueller Stand (Shallow?):** Sehr oberflächlich. Prüft lediglich, ob die `AuthGate`-Komponente bei fehlendem Token auf `/login` umleitet.
* **Akzeptanzkriterien:** "Bei 401-Antworten MUSS das Frontend den Nutzer zur Login-Seite umleiten."
* **Exakter Refactoring-Bedarf:** Der Test muss die Interceptor-Logik prüfen. Es muss ein authentifizierter Zustand simuliert werden, in dem ein beliebiger API-Call einen `401 Unauthorized` Response wirft. Der Test muss sicherstellen, dass die globale Fehlerbehandlung den Nutzer daraufhin aktiv auf die Login-Seite zwingt.

## 11. `frontend/src/test/LoginPage.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-010
* **Name des Tests:** LoginPage
* **Aktueller Stand (Shallow?):** Moderat bis Gut, verlässt sich aber zu sehr auf interne Speicherdetails.
* **Akzeptanzkriterien:** Token-Management und Login-Redirects.
* **Exakter Refactoring-Bedarf:** Der Test liest manuell `sessionStorage.getItem("reqflow_token")` aus, anstatt das Verhalten der Applikation zu prüfen (Whitebox-Testing von internen Details). Refactoring: Verifizieren, dass der `AuthContext` korrekt aktualisiert wird und die App nach erfolgreichem Login den gesperrten Bereich (`/dashboard`) tatsächlich rendert.

## 12. `frontend/src/test/RequirementEditors.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-003 (Requirements-Editor mit Inline-Editing und Markdown)
* **Name des Tests:** RequirementEditors
* **Aktueller Stand (Shallow?):** **EXTREM SHALLOW**. Der Test verweist zwar in den Kommentaren auf REQ-L2-RF-003, der einzige ausgeführte Test prüft aber nur das Vorhandensein eines Split-Pane Dividers (`splitview-divider`) für REQ-L1-040! 
* **Akzeptanzkriterien:** "Nutzer kann ein Requirement anklicken und Title/Description inline bearbeiten. Markdown-Vorschau togglebar. WorkflowState-Dropdown sichtbar und funktional."
* **Exakter Refactoring-Bedarf:** Alle im Kommentar erwähnten Kriterien MÜSSEN im Test implementiert werden.
  1. Test für Inline-Editing des Titles und der Description.
  2. Test für den Toggle der Markdown-Vorschau.
  3. Test für das Öffnen des WorkflowState-Dropdowns und den API-Aufruf bei Status-Änderung.

## 13. `frontend/src/test/SplitPaneResize.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-030 (Split-View Layout Component)
* **Name des Tests:** Split-Pane Resize
* **Aktueller Stand (Shallow?):** Shallow. Testet eine im Testdatei-Scope erstellte Mock-Komponente (`MockSplitPane`), anstatt die tatsächliche produktive Komponente zu nutzen!
* **Akzeptanzkriterien:** "Breiten werden im LocalStorage des Browsers gespeichert und beim Reload wiederhergestellt."
* **Exakter Refactoring-Bedarf:** Die Produktiv-Komponente (z. B. `SplitView`) muss getestet werden. Es muss simuliert werden, dass nach dem Dragging die neue Breite via `localStorage.setItem` persistiert und bei einem Re-Mount exakt wiederhergestellt wird.

## 14. `frontend/src/test/UserPreferences.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-007 (Preset-basierte UI-Sichtbarkeit)
* **Name des Tests:** WorkspaceContext / User-preference overrides
* **Aktueller Stand (Shallow?):** Gut für die Logik, oberflächlich für die UI. Er testet die Provider-Logik anhand einer Dummy-Komponente (`AllOptionalDisplay`).
* **Akzeptanzkriterien:** "UI-Elemente, Felder und Funktionen basierend auf dem aktiven Workspace-Preset... ein- oder ausblenden."
* **Exakter Refactoring-Bedarf:** Der Test muss überprüfen, ob produktive UI-Elemente (z.B. der Button für den Architecture-Editor im Seitenmenü) physisch aus dem DOM verschwinden, wenn im Kontext das Preset entsprechend geändert wird. Das Testen gegen Dummys fängt keine Fehler in der Integration der eigentlichen UI-Komponenten ab.

## 15. `frontend/src/test/WorkspaceContext.test.tsx`
* **Verknüpfte REQ-L2 ID:** REQ-L2-RF-008 (Terminologie-Profil-Rendering)
* **Name des Tests:** WorkspaceContext / Terminology Profile
* **Aktueller Stand (Shallow?):** Shallow. Gleiches Problem wie bei den Preferences: Es wird gegen eine Dummy-Komponente (`LabelDisplay`) getestet.
* **Akzeptanzkriterien:** "Dev-Modus: UI zeigt Labels wie Epic... SE-Modus: UI zeigt System... Profilwechsel → alle Labels aktualisieren sich sofort".
* **Exakter Refactoring-Bedarf:** Der Test muss eine echte Ansicht (z. B. das `Dashboard` oder die List-Header) mounten und verifizieren, dass der Hook `terminologyLabel` dort korrekt eingebunden ist und sich z.B. Tabellenköpfe beim Profilwechsel von "Requirements" zu "Stories" ohne Page-Reload ändern.
