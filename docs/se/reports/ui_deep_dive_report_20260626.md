# Deep-Dive Analyse: Frontend & UI-Mängel

Dieses Dokument enthält eine detaillierte technische Analyse der gemeldeten Frontend-Probleme ("UI sieht schlecht aus" und "Requirements anlegen schlägt fehl"). Die Prüfung des Quellcodes in `frontend/src/` offenbart signifikante Lücken zwischen den Architektur-Vorgaben und der tatsächlichen Implementierung.

## 1. Funktionaler Blocker: Warum "Requirements anlegen" fehlschlägt

Das Anlegen von Requirements ist aktuell **funktional unmöglich** aufgrund einer fehlenden Backend-Integration, die im Frontend durch einen fehlerhaften Mock überbrückt wird.

**Root Cause Analyse:**
- **Der Fehler:** In `WorkspaceContext.tsx` (Zeile 44) wird ein `DEFAULT_WORKSPACE` mit einer Mock-UUID (`00000000-0000-0000-0000-000000000000`) verwendet.
- **Der Grund:** Der Kommentar im Code verrät: *"NOTE: /api/v1/workspaces/ is not implemented in backend yet — see Escalations. This context works with a mock workspace until the endpoint is added."*
- **Die Auswirkung:** Wenn in `RequirementEditors.tsx` die `handleCreate`-Funktion aufgerufen wird, sendet das Frontend diesen Mock-Workspace-ID an das Backend (`POST /api/v1/requirements/`). Da in der Backend-PostgreSQL-Datenbank kein Workspace mit dieser ID existiert, schlägt der Foreign-Key-Constraint (`workspace_id`) fehl, was zu einem `500 Internal Server Error` oder `400 Bad Request` führt.

**Fehlende Anforderung (Gap):**
Es fehlt die Implementierung des **Workspace-Managements** (`WorkspaceService` und entsprechende REST-API-Endpunkte `/api/v1/workspaces/`). Solange das Frontend keinen echten, in der Datenbank existierenden Workspace laden und dessen ID verwenden kann, ist die gesamte Artifact-Erstellung blockiert.

## 2. Visuelle & UX-Mängel: Warum die UI "wie ein Haufen Scheiße" aussieht

Eine Überprüfung der React-Komponenten (insbesondere `RequirementEditors.tsx` und `NavigationShell.tsx`) zeigt ein komplettes Fehlen moderner Web-Aesthetics und Design-Systeme.

**Technische Befunde:**
1. **Ausschließliche Nutzung von Inline-Styles:** Die gesamte UI ist mit statischen Inline-Styles (z.B. `style={{ width: "100%", padding: "0.4rem", borderRight: "1px solid #ddd" }}`) zusammengebaut. Es gibt keine ausgelagerten CSS-Dateien, keine CSS-Modules und kein Utility-CSS.
2. **Fehlendes Design-System:** Es existieren keine zentralen Design-Tokens (Farben, Typografie, Spacing). Statt strukturierter Themes werden hartcodierte Farben (wie `#e8eef8`, `red` oder `#ddd`) verwendet.
3. **Mangelhafte UX & Interaktivität:** Es fehlen Hover-Effekte, Transitions, Loading-Spinner oder visuelle Feedbacks (Mikro-Animationen), die eine moderne Web-Applikation lebendig wirken lassen.
4. **Fehlende UI-Komponentenbibliothek:** Statt robuster, barrierefreier Komponenten (wie Material-UI, Radix, Tailwind UI) werden native HTML-Elemente (`<input>`, `<select>`, `<button>`) ohne tiefere Gestaltung genutzt.

**Verletzte Design-Anforderungen:**
Gemäß den generellen Web-App-Aesthetics-Vorgaben muss ein "Dynamic Design" mit reichen Aesthetics (Gradients, saubere Typografie, Glassmorphismus) umgesetzt werden. Die aktuelle Implementierung liefert lediglich ein reines "Minimal Viable Product" (MVP) Layout für Entwickler, ohne jeglichen UX-Anspruch.

## 3. Zusammenfassung der fehlenden Anforderungen (Gaps)

Um das System lauffähig und visuell ansprechend zu machen, fehlen folgende essenzielle Bausteine:

1. **Backend:** REST-Endpunkte für Workspace-CRUD (`GET /api/v1/workspaces/`) müssen im `RestApiAdapterSystem` nachgerüstet werden.
2. **Frontend-Logik:** Die `NavigationShell` muss den aktiven Workspace vom Backend laden und im `WorkspaceContext` speichern, anstatt den Mock zu verwenden.
3. **Frontend-UI/UX:** Die komplette Präsentationsschicht muss neugeschrieben werden. Einführung einer modernen Styling-Lösung (Vanilla CSS Tokens oder ein CSS-Framework), Etablierung eines Design-Systems (Farben, Typografie, Layouts) und Implementierung responsiver, interaktiver Komponenten.

---
*Fazit: Die Architektur der UI-Komponenten (Trennung von Context, API und Views) ist zwar konzeptionell sauber, die Ausführung ist jedoch auf dem Stand eines rudimentären Prototyps stehen geblieben. Der fehlende Workspace-Endpoint macht das System aktuell unbenutzbar.*
