---
type: PLAN
title: "Interview-Umbau und aktives Zuhören (Listen-Modus)"
status: proposed
date: 2026-11-26
author_agent: main_chat
language: de
branch_basis: "main 5219b0c0 (v1.9.0-beta.8)"
---

# Interview-Umbau und aktives Zuhören (Listen-Modus)

Stand: 2026-11-26 · Autor: main_chat · Status: Entwurf zur Freigabe
Vorgänger-Spec: [`../superpowers/specs/2026-11-21-listen-modus-alle-clients-design.md`](../superpowers/specs/2026-11-21-listen-modus-alle-clients-design.md)

## 1. Ziel

Zwei Kanäle, ein Vertrag:

1. **Interview (explizit):** Ein Interview zu einem Artefakt (Requirement, Risk, ADR,
   ArchitectureElement, TestCase, StakeholderNeed, Issue, Goal) fragt die Felder ab, die
   dieser Typ wirklich braucht. Der erzeugte Vorschlag ist **unverändert** übernehmbar und
   erzeugt ein Artefakt, das der eigene SE-Auditor nicht sofort als Blocker meldet.
2. **Zuhören (implizit, parallel):** Während eines normalen Chat-Verlaufs extrahiert der
   Server aus der Nutzernachricht Vorschläge — neu anlegen **und** bestehende Artefakte
   anpassen/erweitern/korrigieren. Kein stilles Schreiben: der Mensch bestätigt.

Beide Kanäle nutzen **denselben Feldvertrag** und **denselben Posteingang** (ADR-019).

### 1.1 Nicht-Ziele

- Architektur aus bestehendem Code/Repository ableiten (eigene Spec, D11 der Listen-Spec).
- Assistententext und Werkzeugausgaben mitschneiden (Version 1: nur Nutzernachrichten).
- Automatisches Anlegen ohne Bestätigung.

## 2. Live-Befund (Plugin-Test 2026-11-26) und Code-Beleg

| # | Befund | Ursache im Code | Schwere |
|---|---|---|---|
| B1 | `interview.formalize` lehnt einen Chat-Vorschlag ab: „invalid fields for 'Risk' … 'probability'" | Der Multi-Chat-Prompt nennt **keinen Feldervertrag** je Typ (`interview_multi_protocol.py:248-281`); die Prüfung prüft nur **erlaubte** Felder, nicht **Pflichtfelder** (`interview_multi_formalize_service.py:235-310`); erst der Adapter scheitert am fehlenden Pflichtfeld und wird als „invalid fields" umetikettiert (`:422-427`). | Blocker |
| B2 | `requirements-architecture-manager` kann `interview.chat` nicht aufrufen (#2081) | Weder Template noch verteiltes Plugin listen das Tool: `docs/agent-templates/requirements-architecture-manager.md:39-48`, `dist/plugins/claude-code/reqogniloom/agents/requirements-architecture-manager.md:37-46`. | hoch |
| B3 | Nichts startet von allein | Kein `hooks/` im Claude-Plugin (`dist/plugins/claude-code/reqogniloom/`); Matrix führt „Hooks / listen mode" als `✗` (`docs/clients/capabilities.md`). | hoch |
| B4 | Kein Server-Aufruf „Text rein, Vorschläge raus" | `artifact_create` ist registriert, aber **dormant** (`backend/application/suggestion_adapters.py:394-409`); aktive Arten nur `trace_link` und `requirement_level`; `grep capture` in `suggestion_service`/`suggestion_views`/`tools/suggestion.py` ohne Treffer. | Blocker |
| B5 | Nur „anlegen", nicht „anpassen/erweitern/korrigieren" | Die Suggestion-Arten und Adapter kennen keinen Update-Pfad; `artifact_create` ist der einzige geplante Schreibpfad. | hoch |
| B6 | `artifact.search` liefert veraltete Artefakte ohne Status/`include_outdated` | Filter existiert nur für ICD- und TraceLink-Treffer (`backend/application/search_service.py:1155,1213`); die Suche selbst (`:1607-1720`) hat kein `include_outdated` und kein Statusfeld. `requirement.query` und `workspace.get_context` schließen standardmäßig aus. | mittel |
| B7 | Titel-Präfix „PLUGIN-TEST" ging verloren | Modellverhalten, kein Defekt. Wird als Prompt-Hinweis („Titel unverändert übernehmen") mitgenommen, nicht als Bug geführt. | niedrig |

## 3. Zielarchitektur

```
 Interview (explizit)            Zuhören (implizit)
 ────────────────────            ──────────────────
 interview.start/chat            Client-Hook (UserPromptSubmit)
        │                                │  Relay (lokal, fail-open)
        ▼                                ▼
 ein Feldvertrag je Typ  ◄────  POST suggestion.capture / MCP suggestion.capture
 (Attribut-Definition +         (Filter, Schwärzung, Dedupe, LLM, Prüfung)
  create_X-Signatur)                     │
        │                                ▼
        └────────►  Suggestion-Posteingang (ADR-019)  ◄────────┘
                              │  Mensch bestätigt
                              ▼
                    Artefakt create / update
```

**Ein Vertrag:** `artifact_field_contract(workspace, type)` liefert je Feld
`name`, `type`, `choices`, `required`, `default`, `source`
(`attribute_definition` | `create_signature`). Interview-Protokoll, Multi-Prompt,
Proposal-Prüfung und Capture benutzen ihn. Damit kann kein Kanal ein Feld
vergessen, das ein anderer Kanal verlangt.

**Zwei Vorschlags-Operationen:** `artifact_create` und `artifact_update`
(inkl. `target_artifact_id` + `base_version`). „Anpassen/erweitern/korrigieren"
ist ein Update-Vorschlag, kein neues Artefakt.

## 4. Arbeitspakete

Aufwände sind grobe Tasks, kein Versprechen.

### P0 — Feldvertrag und übernehmbarer Vorschlag (Blocker B1)

- Create: `backend/application/attribute_contract_service.py` — eine Quelle für den Feldvertrag je Artefakttyp.

| Schritt | Inhalt | Dateien |
|---|---|---|
| P0.1 | `artifact_field_contract()` als eine Quelle bauen; Pflicht = `required` der Attribut-Definition **oder** Parameter ohne Default in `create_X()` | neue Datei (siehe unten), `interview_artifact_adapters.py` |
| P0.2 | Single-Mode-Protokoll daraus ableiten (ist vorhanden) und **Pflichtfelder markieren**; Risk muss `probability`/`impact` fragen | `backend/application/interview_protocol.py:448-470` |
| P0.3 | Multi-Prompt je Typ mit dem Vertrag füllen statt „fields for that type's create call"; Titel unverändert übernehmen | `backend/application/interview_multi_protocol.py:248-281` |
| P0.4 | `validate_confirmed_proposal_fields` um Pflichtfeld-Prüfung erweitern; maschinenlesbare Codes `MISSING_REQUIRED_FIELD` (mit Feldnamen) vs. `UNKNOWN_FIELD` | `backend/application/interview_multi_formalize_service.py:235-310` |
| P0.5 | `KeyError`/`TypeError` im Adapter nicht mehr als „invalid fields" verpacken, sondern als strukturierten Fehler mit Item-Index und Feldern | `:395-432` |
| P0.6 | `interview.propose` liefert `missing_fields` und der nächste Chat-Turn fragt sie ab; `formalize` verweigert mit demselben Code | `interview_formalize_service.py`, `interview_service.py` |
| P0.7 | Tests: Risk ohne `probability` → `propose` nennt das Feld, Chat fragt nach; vollständiger Vorschlag → `formalize` legt an; unbekanntes Feld → `UNKNOWN_FIELD`; Reihenfolge/Fehlertext | `backend/application/tests/test_interview_*` |

**Gate P0:** Ein Vorschlag aus `interview.propose` geht **unverändert** durch
`interview.formalize`; ein unvollständiger Vorschlag nennt die fehlenden Felder und
erzeugt kein Artefakt.

### P1 — Agenten-Zugriff (#2081)

- `interview.chat` in `docs/agent-templates/requirements-architecture-manager.md` und
  im verteilten Plugin ergänzen; Generator/Drift-Test mitziehen, damit Template und
  `dist/` nicht auseinanderlaufen.
- Drift-Test: jedes in einem Agenten gelistete Tool existiert im MCP-Registry-Manifest;
  `interview.chat` ist in beiden Listen.
- Prüfen, ob weitere Agenten (z. B. `concept-specifier`, `risk-derivation`) den Chat
  brauchen.

**Gate P1:** Der Agent kann einen Interview-Chat über MCP führen; CI-Drift-Test grün.

### P2 — Server-Kern `suggestion.capture` (Blocker B4)

- REST `POST /api/v1/suggestions/capture/` und MCP `suggestion.capture` mit identischem
  Verhalten (Spec §4).
- Eingabe: `workspace_id`, `text`, `client`, `source_session`, `message_id`,
  `idempotency_key`.
- Serverseitig: Workspace-Schalter `capture.enabled` (Standard aus), Schwärzung,
  Regel-Filter, Duplikatsschutz (Idempotenz → offene/verworfenene Vorschläge →
  Bestandsabgleich), ein zustandsloser LLM-Aufruf (kein wachsendes Transkript),
  Antwortprüfung, Ablage als `Suggestion`.
- `artifact_create`-Adapter aktivieren: Annehmen ruft denselben Produktions-`create_X()`
  wie `formalize` (kein zweiter Schreibpfad).
- Grenzen: Textlänge, offene Vorschläge je Workspace, Aufrufe/Stunde, `expires_at`.
- Audit + Token-Zählung mit Kennzeichnung „capture".

**Gate P2:** `suggestion.capture` erzeugt aus einem Satz genau einen Vorschlag im
Posteingang; Annehmen erzeugt ein Artefakt mit Herkunft; Schalter aus → kein Aufruf.

### P3 — Anpassen / Erweitern / Korrigieren (B5)

- Suggestion-Payload um `operation` (`create` | `update`), `target_artifact_id` und
  `base_version` erweitern; neuer Adapter `artifact_update`.
- Annehmen eines Update-Vorschlags ruft die normale Update-Fassade (Optimistic Lock,
  Workflow-Zustand, `change_reason`-Policy); veraltete `base_version` → Konflikt im
  Posteingang, kein Overwrite.
- Duplikatsschutz erkennt „bestehendes Artefakt wiederholt" und schlägt Update statt
  Create vor.
- Tests: „Erweitere REQ-X um Akzeptanzkriterium Y", „Korrigiere Titel Z", veraltete
  Version.

**Gate P3:** Ein Update-Vorschlag ändert nur das Zielartefakt, hinterlässt Version +
Audit und überschreibt keinen fremden Stand.

### P4 — Relay und Claude-Code-Anschluss (B3)

- Ein Relay-Vertrag (lokal, fail-open, Sperre, Bündeln statt Verwerfen, Statusdatei)
  gemäß Spec §5.1.
- Claude Code: `hooks/hooks.json` mit `UserPromptSubmit`, `async: true`; Filter für
  `/loop`, Kommandos, Kurznachrichten, Einfügungen.
- Skill `/reqogniloom:listen on|off|status|review`.
- AP0-Probelauf (R2 HTTP-Hook vs. R1 Skript) **vor** dem Bau; ohne belegten Lauf keine
  grüne Matrix-Zelle.
- Tests mit Attrappen-Server (S1–S12 der Spec), danach ein echter Lauf.

**Gate P4:** Live-Beleg in Claude Code: eine Nutzernachricht erzeugt ohne Modell-Zutun
einen Vorschlag; Server aus → Antwort unverändert, Status zeigt den Fehler.

### P5 — Weitere Clients

Hermes auf `suggestion.capture` umstellen (H1–H8 beheben), dann OpenCode (V1/V2),
Codex, Kimi, Antigravity — je Paket, Installer, Schalter, Doku. Stufe C (Skill-Anweisung)
nur als dokumentierte Notlösung.

### P6 — `artifact.search`: veraltete Treffer (B6)

- `include_outdated` (Default **false**) in Service, REST und MCP; jeder Treffer trägt
  `status`/`outdated`.
- Filter für **alle** Typen, nicht nur ICD/TraceLink.
- Bewusste Verhaltensänderung dokumentieren (vorher wurden veraltete Treffer geliefert);
  Übergangsfrist/Alias gemäß den bestehenden Deprecation-Regeln.
- Tests: veraltetes Requirement erscheint nicht im Default, mit `include_outdated=true`
  schon; `status` ist gesetzt.

### P7 — Doku, Matrix, Abnahme

- `docs/clients/capabilities.md`: Zeile „Hooks / listen mode" je Client mit belegtem
  Status; Interview-Zeilen auf den neuen Stand.
- Datenschutzseite: Datenfluss, Schwärzung, Aufbewahrung, Hinweis beim Einschalten.
- Abnahmeszenarien aus §5 als Testfälle.

## 5. Abnahme

Zusätzlich zu S1–S12 der Listen-Spec:

| ID | Szenario | Erwartung |
|---|---|---|
| A1 | Chat „Das Display muss bei Überdruck über 8 bar einen roten Alarm zeigen", Typ Risk | Vorschlag enthält `probability` und `impact`; `formalize` nimmt ihn unverändert an |
| A2 | Derselbe Vorschlag ohne `probability` | `propose` nennt `probability` als fehlend, Chat fragt nach, `formalize` legt nichts an und meldet `MISSING_REQUIRED_FIELD` |
| A3 | Agent `requirements-architecture-manager` | kann `interview.chat` aufrufen (#2081) |
| A4 | „Erweitere REQ-12 um ein Akzeptanzkriterium" | Update-Vorschlag mit Ziel + Basisversion; Annehmen erweitert, kein Duplikat |
| A5 | Titel mit Präfix „PLUGIN-TEST" | Präfix bleibt im Vorschlag und im Artefakt |
| A6 | `artifact.search "…"` mit veraltetem Treffer | Default: nicht enthalten; `include_outdated=true`: enthalten, mit Status |
| A7 | Schalter aus | kein Netzaufruf (Client) bzw. `CAPTURE_DISABLED` (Server) |

## 6. Offene Entscheidungen

| ID | Frage | Empfehlung |
|---|---|---|
| D1 | Neuer Aufruf `suggestion.capture` oder `interview.*` weiterverwenden? | **neu** (kein wachsendes Transkript, ein Vertrag) |
| D2 | Rechte: zwei Keys, Capture für Nutzer-Keys oder neues Recht `capture`? | **neues Recht `capture`**, neuer ADR als Ergänzung zu ADR-019 |
| D3 | Was wird erfasst? | nur Nutzernachrichten (v1) |
| D4 | Wo liegt der Schalter? | Client **und** Workspace, Standard aus |
| D5 | Rohtext speichern? | nein, normalisierter Auszug + Hash |
| D6 | Wo entscheidet der Mensch? | Web-Posteingang + MCP |
| D7 | Rauschkontrolle? | Regelfilter + Obergrenzen, kein zweiter Klassifikator in v1 |
| D8 | Arten in v1? | Requirement, ArchitectureElement, Adr, StakeholderNeed (+ Update auf alle acht) |
| D9 | Relay-Technik? | nach AP0 entscheiden (R1/R2) |
| D10 | Client-Reihenfolge? | Claude Code, Hermes, OpenCode, Codex, Kimi, Antigravity |
| D11 | Architektur aus Code ableiten? | nein, eigene Spec |
| D12 | Update-Vorschläge in v1? | **ja**, sonst fehlt „anpassen/erweitern/korrigieren" |
| D13 | `artifact.search`-Default `include_outdated=false`? | ja, mit dokumentierter Übergangsfrist |

## 7. Reihenfolge und erster PR

1. **PR 1: P0 + P1** — behebt B1/B2, kein neuer Endpunkt, keine Migration. Das ist der
   kleinste Schritt, der deinen Live-Test grün macht.
2. **PR 2: P6** — unabhängig, klein.
3. **Entscheidungen D1–D5, D9, D12/D13** klären; danach P2 + P3 (Server-Kern).
4. **AP0-Probelauf**, dann P4 (Claude Code), dann P5 (weitere Clients).
5. P7 zum Schluss, aber Matrix und Datenschutz parallel zu P2/P4.

Querschnitt: Feature-Branch, Conventional Commits, `python scripts/check_plan_refs.py`
vor jeder Phase, Migrationen nacheinander, Tool-Manifest/Zähler nachziehen
(`suggestion.capture` = neues MCP-Tool).

## 8. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Feldvertrag aus zwei Quellen driftet (Definition vs. `create_X`) | eine Funktion, ein Test, der beide gegeneinander prüft |
| Hook-Zuverlässigkeit unbelegt | AP0 vor dem Bau, Stufe C nur als Notlösung |
| Nachrichtentext verlässt den Rechner | Standard aus, Schwärzung, Hinweis, Gate G3 |
| Zu viele/zu schlechte Vorschläge | Filter, Obergrenze, Annahmequote als Rückmeldung |
| Update-Vorschlag überschreibt fremden Stand | `base_version` + Konflikt im Posteingang |
| Sechs Client-Anschlüsse pflegen | ein Relay-Vertrag, Konformitätsfolge als Gate |

## 9. Grenzen dieses Plans

- Kein Hook wurde ausgeführt; alle Client-Aussagen stammen aus Doku und Repo-Code.
- Die Hermes-Erfassung wurde nie live getestet.
- Aufwände sind Schätzungen in Tasks, keine Zusagen. Tasks je Paket entstehen nach
  Freigabe der offenen Entscheidungen.
