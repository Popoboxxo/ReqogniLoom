# Interview-Management — Natives ReqogniLoom-Web-UI-Widget — Design

**Status:** Draft, pending user review
**Scope:** Spec 3 von 3. Baut auf Spec 1
(`docs/superpowers/specs/2026-08-14-interview-management-engine-design.md`,
PR #530) und Spec 2
(`docs/superpowers/specs/Archive/2026-08-14-interview-management-hermes-plugin-design.md`,
PR #531) auf. Mit diesem Spec ist die Dekomposition des
Interview-Management-Features vollständig — alle drei Teilprojekte haben
eine geschriebene Spec, Umsetzung folgt danach separat je Teilprojekt.

## 1. Zweck

Ein- und ausblendbarer Help-Desk-Chat-Assistent im ReqogniLoom-Web-UI
(`frontend/`, React 18 SPA), der Interviews auf Basis der internen
KI-Anbindungen führt, plus eine begleitende Artefakte-UI, die zeigt, was
das Interview erzeugt oder anpasst.

**Wesentlicher Unterschied zu Spec 1+2:** Claude Code, Opencode, Antigravity
sind selbst KI-Agenten; Hermes wird von einem gehostet. Die Web-App hat
keine eigene KI. Für einen echten Chat-Dialog (nicht nur ein Formular wie
in Spec 2) muss der **Server** die Dialogführung übernehmen — eine Rolle,
die in Spec 1 explizit dem Host-Agenten zugewiesen war.

## 2. Auth-Realität der Web-App

Anders als das Hermes-Plugin (Spec 2, MCP-JSON-RPC mit `X-API-Key`)
authentifiziert sich die Web-App ausschließlich über einen httpOnly-Cookie
(`reqflow_access`) + CSRF-Token, rein REST, über `frontend/src/api/client.ts`.
Kein API-Key, keine MCP-Fähigkeit im Browser. Spec 1s `interview.*` ist nur
als MCP-Toolgroup entworfen — für diesen Client zwingend eine REST-Fassade
nötig (bestätigt mit dem Nutzer).

## 3. Ergänzungen zu Spec 1

Drei additive, rückwärtskompatible Ergänzungen zum bereits offenen PR #530:

1. **REST-Fassade** `/api/v1/interviews/...` — dünne REST-Endpoints
   (`start`, `get_state`, `answer`, `grounding_context`, `formalize`,
   `list`, `get`), die auf dieselbe Facade/Services aufsetzen wie die
   MCP-Tools. Gleiches Dual-Protokoll-Muster wie `requirement_bundle`.
2. **`InterviewSession.transcript`** — neues Feld, Liste aus
   `{role, text, timestamp}`. Nur der Chat-Client (dieser Spec) schreibt
   hinein; Hermes' Formular (Spec 2) lässt es leer. Nötig, damit ein
   wiedereröffnetes Widget die Konversation zeigt, statt bei Null
   anzufangen.
3. **Neues `llm_adapter`-Capability** für die Chat-Turn-Generierung (siehe
   Abschnitt 5) — verkabelt nach demselben Muster wie
   `suggest_related_artifacts` (Spec 1, Abschnitt 6).

## 4. Architektur

**Widget-Platzierung:** mountet innerhalb `NavigationShell`, unterhalb
`WorkspaceProvider`/`AuthProvider` (hat `activeWorkspace` + Auth verfügbar).
`position: fixed`-Overlay nach dem bestehenden Muster aus
`components/shared/Dialog/Dialog.module.css`. Auf-/Zu-Zustand persistiert in
`localStorage`, gleiches Prinzip wie `ThemeContext`.

**Layout beim Aufklappen — zwei Bereiche:**
- Chat-Transkript (aus `InterviewSession.transcript`).
- Live mitlaufende "Artefakte in dieser Session"-Liste (aus
  `resulting_artifact_ids`/`grounding_snapshot`) — die Artefakte-UI, direkt
  im Widget statt einer separaten Seite, weil sie während des Gesprächs
  wächst.

**Neuer API-Client** `frontend/src/api/interviews.ts` — dünner Wrapper über
`client.ts` (gleiche Konvention wie `api/prompt-templates.ts`,
`api/tracelinks.ts` etc.), keine neue Auth-Logik.

## 5. Chat-Turn-Generierung

**`POST /api/v1/interviews/{id}/chat/`** — nimmt Freitext + `session_id`.

Ablauf:
1. Lädt aktuellen State (`collected_fields`, `missing_fields`,
   `grounding_snapshot`, `transcript`).
2. Ruft das neue `llm_adapter`-Capability mit dem `interview.chat_turn`-Prompt
   auf (Variablen siehe Abschnitt 7), das Feldwerte aus der Nachricht
   extrahiert.
3. Ruft intern `interview.answer` für jedes erkannte Feld auf.
4. Bestimmt die nächste Frage aus dem verbleibenden `missing_fields` +
   dem aktuellen Phasen-`prompt_fragment` (Spec 1, Abschnitt 3.1).
5. Hängt Nutzer-Nachricht + generierte Antwort an `transcript` an, gibt
   beides zurück.

**Kein Streaming in v1** — konsistent mit dem Rest der Web-App, die
durchgängig einfaches Request/Response über `client.ts` nutzt.

**Nicht fail-open, anders als Grounding:** ohne funktionierenden
LLM-Provider kann die Dialogführung strukturell nicht arbeiten. Der
bestehende Mock-Provider-Fallback greift trotzdem — das Widget
"funktioniert" auch ohne echten Provider, nur die Extraktionsqualität
hängt vom konfigurierten Provider ab, wie überall sonst im System.

**Mehrdeutige Antworten:** die Extraktion rät nicht bei Unsicherheit,
sondern stellt eine Rückfrage — gleiches Prinzip wie der bestehende
`se-requirements`-Agent ("keine Annahmen").

## 6. Formalisierung, Abschluss, Fehlerbehandlung

**Formalisierung:** läuft wie in Spec 1, Session-Status → `completed`,
Chat zeigt eine Zusammenfassung, Artefakte-Panel wird zur finalen Ansicht
mit Links zu den erzeugten/angepassten Artefakten. Ein
"Neues Interview"-Button im Widget setzt zurück.

**Fehlerbehandlung:**
- 401/Session-Ablauf: läuft über den bestehenden `client.ts`-Silent-Refresh
  (Bibliothek behandelt es bereits) — kein Sonderfall für Interview-Endpoints.
- Race zwischen Chat-Turn und einem parallelen Host (z. B. Hermes hat
  gleichzeitig geantwortet): Widget lädt vor jeder neuen Chat-Nachricht
  `get_state` neu.
- LLM-Interpretation schlägt fehl (Provider-Fehler, Timeout): Chat zeigt
  eine Fehlermeldung mit Retry, Nutzereingabe bleibt im Eingabefeld
  erhalten statt verloren zu gehen.
- Widget geschlossen/Browser neu geladen während offener Session:
  `transcript` + `collected_fields` sind serverseitig persistent —
  Wiedereröffnen lädt den Stand über `get_state`, keine verlorene
  Konversation.

## 7. Prompt-Konfiguration (Admin-UI)

`frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx` ist
bereits generisch über alle vom Backend gemeldeten `PromptTemplate`-Slots
(`promptTemplatesApi.listSlots`). Die neuen Slots aus Spec 1
(`interview.protocol.<artifact_type>`, acht Stück für alle Typen außer
MainGoal) und der neue `interview.chat_turn`-Slot aus diesem Spec
erscheinen dort automatisch als Editoren — keine strukturelle UI-Änderung
nötig. Zwei gezielte Ergänzungen:

1. **Label-Generierung statt Hardcode:** `interview.protocol.<type>` bekommt
   sein Label über eine kleine Namenskonvention-Funktion
   (`"Interview: " + type`, `type` ist bereits PascalCase wie
   `Artifact.artifact_type` — z. B. `interview.protocol.Requirement` →
   "Interview: Requirement", siehe Spec 1 Abschnitt 3.1), statt
   `SLOT_LABELS` um acht Einträge zu erweitern — deckt automatisch künftige
   Artefakt-Typen ab. `interview.chat_turn` bekommt einen regulären
   `SLOT_LABELS`-Eintrag wie die bestehenden acht Slots.

2. **Eigener Variablen-Hinweisblock** für `interview.*`-Slots — der
   bestehende Hinweistext ist ein einzelner Absatz für alle Slots; für die
   Interview-Prompts wäre das unlesbar, weil die Variablenmengen sich
   wirklich unterscheiden. Substitution folgt der bestehenden Mechanik
   (`str.replace("{" + key + "}", ...)`, unbekannte/fehlende Platzhalter
   bleiben unverändert, `application/ai_derivation_service.py:1388`):

   - **`interview.protocol.<type>`** (Phasen-`prompt_fragment`):
     `{artifact_type}`, `{phase_name}`, `{collected_fields_json}`,
     `{missing_fields_json}`, `{grounding_snapshot_json}`
   - **`interview.chat_turn`**: `{transcript_json}`, `{user_message}`,
     `{current_phase_fragment}`, `{missing_fields_json}`,
     `{grounding_snapshot_json}`

## 8. Teststrategie

- Backend: neue REST-View-Tests (`rest_api/tests/`) nach bestehendem
  Muster; Tests für das neue `llm_adapter`-Chat-Turn-Capability
  (Mock-Provider-Pfad + Extraktions-Fälle inkl. Mehrdeutigkeit → Rückfrage
  statt Annahme).
- Frontend: Vitest/RTL-Component-Tests für das Widget (Toggle-Zustand,
  Chat-Rendering, Artefakte-Panel-Updates), gemockter `interviewsApi`
  nach dem etablierten `api/`-Wrapper-Muster; Tests für die
  `AiPromptsSection`-Erweiterung (Label-Generierung, neuer Hinweisblock).
- Kein E2E in diesem Spec — bewusst YAGNI für v1, wie schon in Spec 2
  begründet.

## 9. Explizit außerhalb dieses Specs

- **Streaming-Chat-Antworten** — v1 ist Request/Response, siehe Abschnitt 5.
- **Separate Interview-Seite/Route** — die Artefakte-UI lebt im Widget,
  keine eigene `/interviews`-Route in diesem Spec.
- **E2E-Testabdeckung** für den Assistenten — eigenes, späteres Vorhaben.
