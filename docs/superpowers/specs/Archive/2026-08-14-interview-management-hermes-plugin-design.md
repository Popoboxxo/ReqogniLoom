# Interview-Management — Hermes-IDE-Plugin-Integration — Design

**Status:** Draft, pending user review
**Scope:** Spec 2 von 3. Baut auf Spec 1
(`docs/superpowers/specs/2026-08-14-interview-management-engine-design.md`,
PR #530) auf. Spec 3 (natives ReqogniLoom-Web-UI-Widget + Artefakte-Panel)
folgt als eigener Brainstorming-Zyklus.

## 1. Zweck

Sinnvolle Integration der in Spec 1 entworfenen `interview.*`-MCP-Engine in
das bestehende Hermes-IDE-Plugin (`integrations/hermes-plugin/reqogniloom`).

**Ausgangslage:** Das Plugin ist heute rein REST-basiert (`X-API-Key`-Header,
`network.fetch` gegen `/api/v1/...`) und bietet nur eine minimale
Connect-/Workspace-Auswahl-UI (`ConnectScreen`, `ConnectedView` — Connect,
Open-in-Browser, Disconnect). Anders als Claude Code, Opencode und
Antigravity hat Hermes eine echte React-Panel-Fläche
(`HermesPluginAPI.ui.registerPanel`), keinen reinen Text-Skill-Zugang.

**Kern-Design-Entscheidung:** das Panel nutzt genau dieses
Alleinstellungsmerkmal aus — es rendert das Interview als **strukturiertes
Formular** direkt im Panel (ein Eingabefeld pro offenem Pflichtfeld aus
Spec 1s Protokoll-Konfiguration), statt einen Chat-Dialog zu simulieren.
Das ist möglich, weil Spec 1s Protokoll-Konfiguration die Pflichtfelder pro
Phase schon strukturiert vorhält und KI-gestütztes Grounding serverseitig
läuft — das Plugin braucht dafür keine eigene LLM-Anbindung.

## 2. Technische Machbarkeit: MCP über den bestehenden Plugin-Kanal

Spec 1 definiert `interview.*` als MCP-Toolgroup. Das Plugin hat keine
MCP-SSE-Verbindung, nur `network.fetch` (liefert ein einzelnes
`Promise<string | Response>`, kein Streaming).

**Geprüft und bestätigt:** Der MCP-Server exponiert neben
`POST /mcp/sse/` (Streaming) auch `POST /mcp/` als reinen
**JSON-RPC-2.0-Request/Response-HTTP-Transport**
(`backend/mcp_server/urls.py`, `McpHttpTransportView`) — kein
Server-Sent-Events, keine dauerhafte Verbindung nötig. Das passt exakt zu
`network.fetch`. Der Transport akzeptiert denselben `X-API-Key`-Header, den
die REST-Verbindung schon nutzt (verifiziert gegen
`dist/opencode/build_opencode_package.py`s Header-Konfiguration).

**Konsequenz:** keine Änderung an `HermesPluginAPI`/der Host-Plattform
nötig. Kein REST-Fassade-Bedarf für `interview.*` — das Plugin spricht die
identische MCP-Toolgroup wie Claude Code, Opencode und Antigravity.

## 3. Architektur

**Neues Modul** `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts`
— schlanker JSON-RPC-2.0-Client:
- POST gegen `${connection.baseUrl}/mcp/`, `X-API-Key: ${connection.apiKey}`.
- Eine Funktion pro benötigtem Tool: `interviewStart`, `interviewGetState`,
  `interviewAnswer`, `interviewGroundingContext`, `interviewFormalize`,
  `interviewList`, `interviewGet` — jeweils ein JSON-RPC-Request/Response-Paar.
- Wiederverwendet `api.ts`s Error-Envelope-Parsing-Logik (gleiches
  Nested-/Flat-Envelope-Problem gilt für MCP-Fehlerantworten genauso).

**Neue Views:**
- `InterviewListView` — listet aktive Sessions im Workspace via
  `interview.list(workspace_id, status="in_progress")`: Rolle
  (`artifact_type`), Fortschritt (Anzahl beantworteter vs. offener
  Pflichtfelder), Start-Button für eine neue Session pro Artefakt-Typ.
  Das macht Spec 1s Host-übergreifende Fortsetzbarkeit für Hermes-Nutzer
  sichtbar: eine in Claude Code begonnene Session taucht hier auf und lässt
  sich weiterführen.
- `InterviewFormView(session_id)` — lädt `interview.get_state`, rendert ein
  Eingabefeld pro offenem Pflichtfeld (Typ siehe Abschnitt 4). Submit ruft
  `interview.answer` sequenziell einmal pro geändertem Feld auf — Spec 1
  kennt keine Batch-Variante von `interview.answer`, ein Formular-weiter
  Submit-Button ist also mehrere Tool-Aufrufe hintereinander, nicht einer.
  Zeigt den
  Grounding-Snapshot (verwandte/mögliche Duplikat-Artefakte) als Hinweisliste
  über dem Formular. Ein "Formalisieren"-Button ruft `interview.formalize`,
  sobald alle Pflichtfelder beantwortet sind.
- Ergebnis-Anzeige nach `formalize`: Liste der erzeugten/angepassten
  Artefakt-IDs, mit Link zurück ins ReqogniLoom-Web-UI
  (wiederverwendet das `openInBrowser`-Pattern aus `state.ts`).

`AppState`/`state.ts` bekommt einen neuen `view`-Wert (`"interviews"`) plus
Zustand für die aktuell offene Session-ID.

## 4. Erweiterung von Spec 1: Feldtyp in der Protokoll-Konfiguration

Spec 1 (Abschnitt 3.1) definiert `required_fields` bisher als reine
Namensliste. Für sinnvolle Formularfelder reicht das nicht — additive,
rückwärtskompatible Ergänzung (bestätigt mit dem Nutzer):

```yaml
phases:
  - name: elicitation
    required_fields:
      - name: title
        type: text          # Default, wenn type fehlt
      - name: rationale
        type: textarea
      - name: element_type
        type: enum
        choices: [component, subsystem, system]
      - name: priority
        type: number
```

Diese Änderung wird in Spec 1s Dokument nachgetragen (Abschnitt 3.1), nicht
in einem separaten Dokument — es ist dieselbe Datenstruktur, nur präziser.

## 5. Fehlerbehandlung

- **MCP-Session abgelaufen** (JSON-RPC-Fehler beim `POST /mcp/`) — sobald
  Issue #427 (parallel in Arbeit) den generischen 401 durch einen
  spezifischen Code ersetzt, zeigt das Panel einen klaren
  Reconnect-Hinweis statt einer generischen Fehlermeldung. Bis dahin: der
  bestehende `ReqogniLoomApiError`-Pfad zeigt die rohe Server-Nachricht.
- **Veralteter Formular-Zustand** (ein anderer Host hat parallel
  geantwortet oder formalisiert): das Panel lädt `interview.get_state` vor
  jedem Submit neu, statt einen lokalen Snapshot als Wahrheit zu behandeln
  — Konfliktentscheidung bleibt serverseitig (Spec 1, Abschnitt 9), keine
  eigene Logik im Plugin.
- **Session wurde inzwischen `completed`/`abandoned`**: `InterviewFormView`
  erkennt den Status aus `get_state` und zeigt das Ergebnis bzw. einen
  Hinweis statt eines nicht mehr gültigen Formulars.

## 6. Teststrategie

- Vitest-Unit-Tests für `mcpClient.ts` — JSON-RPC-Envelope-Parsing,
  Fehlerfälle (invalid session, validation error), gleiches Muster wie das
  bestehende `api.test.ts` (`network.fetch`-Mock, beide Return-Shape-Varianten
  aus `parseNetworkResult` abdecken).
- Component-Tests für `InterviewListView`/`InterviewFormView` mit
  gemocktem `mcpClient` — Rendering der Feldtypen (Abschnitt 4), Submit-Flow,
  Fehlerdarstellung.
- Kein E2E nötig für dieses Spec (Playwright deckt die Hermes-Plugin-Umgebung
  nicht ab — reines Unit-/Component-Testing wie der Rest von
  `integrations/hermes-plugin`).

## 7. Explizit außerhalb dieses Specs

- **Änderungen an der Hermes-Host-Plattform** — nicht nötig (Abschnitt 2),
  aber falls doch: außerhalb der Reichweite dieses Repos.
- **Natives ReqogniLoom-Web-UI-Widget** — Spec 3.
- **KI-gestützte Grounding-Logik selbst** — liegt vollständig in Spec 1,
  hier nur konsumiert (Anzeige des `grounding_snapshot`).
