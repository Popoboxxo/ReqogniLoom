---
type: REVIEW
scope: "Abschlussbericht Planreview Backlog-Umsetzung A–G (2026-10-21/22)"
status: closed
date: 2026-10-22
author_agent: senior-developer
language: de
base_head: b175c970
basis:
  - docs/superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md
  - docs/plans/2026-10-21-backlog-umsetzung-index.md
  - docs/plans/2026-10-21-entscheidungen-offen.md
  - docs/plans/2026-10-21-korrekturauftraege.md
  - docs/reviews/PLAN_QUERREVIEW_2026-10-21_TECHNISCH.md
  - docs/reviews/PLAN_QUERREVIEW_2026-10-21_SICHERHEIT.md
  - docs/plans/2026-10-21-plan-{a-memory-und-suche,b-se-modell,c-ui-ux,d-deployment-dx,e-security-api,f-dokumente-baselines,g-qa-haertung}.md
---

# Planreview Backlog-Umsetzung A–G — Abschlussbericht

## 1. Zusammenfassung

- Sieben Umsetzungspläne (A–G) zu 67 offenen Issues liegen vor. Alle haben Stufe 1 (Worker-Entwurf mit Live-Check)
  und Stufe 2 (Integration der Korrekturaufträge) durchlaufen. Status bleibt `proposed`: 54 Nutzerentscheidungen
  sind offen, davon 21 als Entscheidungs-Konflikt markiert ([Entscheidungsliste](../plans/2026-10-21-entscheidungen-offen.md)).
- Der [Plan-Index](../plans/2026-10-21-backlog-umsetzung-index.md) ist verbindlich. Er regelt Wellen, Merge-Queues,
  Migrationsvergabe, reale CI-Jobs und Rollen. Die Abschluss-Integration hat dort **28 Widersprüche** aufgelöst
  (Index §i).
- Befundlage: 2 Querreviews mit **53 Befunden** (technisch 30, Sicherheit 23) und **128 plan-eigene Review-Befunde**.
  Kritisch: 3 (QR-T01, QR-T02, Plan D RB-D01). Alle kritischen und hohen Befunde sind in den Plänen korrigiert
  oder an eine `ENT-*`-Entscheidung gebunden. Kein Befund wurde abgelehnt.
- Live-Checks: **121 Prüfungen** gegen das QS-System (v1.8.0-beta.22). Sie haben die Planbasis an vielen Stellen
  korrigiert: 16 Behauptungen sind ganz widerlegt, 6 teilweise. 19 waren nicht prüfbar.
- Aufwand nach Stufe 2: ≈ 176–215 PT (Index §a). Eine Schärfung durch `effort-estimator` steht aus.
- Vor Welle 0 bleibt die Sofortmaßnahme QR-S03: drei `.env.bak-*`-Dateien im Repo-Root, nicht ignoriert.
  Der Nutzer entscheidet (ENT-X1).

## 2. Vorgehen

| Phase | Inhalt | Ergebnis |
|---|---|---|
| 0 Planbasis | Planungssitzung mit dem Nutzer, 67 Issues in Cluster A–G, Querschnittsentscheidungen Q1–Q4, Wellen 0–4 | [Planbasis](../superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md) |
| 1 Worker je Plan | ein Planer-Worker je Plan, Code-Verifikation `datei:zeile` gegen `b175c970`, lesende API-Live-Checks gegen QS | 7 Pläne, Abschnitte „Ist-Stand“, „Review-Befunde“, „Widerlegte Annahmen“, Belege `docs/test-reports/plan-review-2026-10-21/plan-*/` |
| 1b UI-Live-Checks | `e2e-tester` (headless Chromium, nur Navigation/Screenshots) für Plan C | `plan-c/ui-live-checks.md` (C-L1…C-L9), 25 Screenshots |
| 2 Querreview technisch | `code-reviewer`: Migrationen, Promptfoo-Kopplung, Tool-Zähler, Konfliktdateien, 60 Stichproben (55 korrekt, 5 Fehlbelege) | [QUERREVIEW_TECHNISCH](PLAN_QUERREVIEW_2026-10-21_TECHNISCH.md) |
| 2 Querreview Sicherheit | `security-auditor`: Threat-Model je Plan, Token-Grep über Belege, 23 Befunde | [QUERREVIEW_SICHERHEIT](PLAN_QUERREVIEW_2026-10-21_SICHERHEIT.md) |
| 3 Integration Stufe 1 | Index, Entscheidungsliste, Korrekturaufträge (112 plan-spezifisch + 11 KA-ALL) | Index, [Entscheidungen](../plans/2026-10-21-entscheidungen-offen.md), [Korrekturaufträge](../plans/2026-10-21-korrekturauftraege.md) |
| 4 Integration Stufe 2 | ein Integrator je Plan, Änderungsprotokoll je Plan | 176 Aufträge (KA-ALL je Plan mitgezählt): 148 erledigt, 28 vorläufig (mit ENT-Empfehlung), 0 abgelehnt |
| 5 Abschluss-Integration | Index-Widersprüche aus den Änderungsprotokollen, Plan E (E2.9, R3-08), dieser Bericht, Planbasis-Verweise, Hygiene | Index §i, Plan E Änderungsprotokoll |

Stufe-2-Bilanz je Plan (aus den Änderungsprotokollen):

| Plan | Aufträge | erledigt | vorläufig | abgelehnt | Abschnitt |
|---|---|---|---|---|---|
| A | 36 | 30 | 6 | 0 | [§16](../plans/2026-10-21-plan-a-memory-und-suche.md#16-änderungsprotokoll-stufe-2) |
| B | 26 | 22 | 4 | 0 | [Änderungsprotokoll](../plans/2026-10-21-plan-b-se-modell.md#änderungsprotokoll-stufe-2) |
| C | 26 | 22 | 4 | 0 | [§15](../plans/2026-10-21-plan-c-ui-ux.md#15-änderungsprotokoll-stufe-2) |
| D | 18 | 15 | 3 | 0 | [Änderungsprotokoll](../plans/2026-10-21-plan-d-deployment-dx.md#änderungsprotokoll-stufe-2) |
| E | 22 (+2 Abschluss) | 18 (+2) | 4 | 0 | [Änderungsprotokoll](../plans/2026-10-21-plan-e-security-api.md#änderungsprotokoll-stufe-2) |
| F | 25 | 21 | 4 | 0 | [Änderungsprotokoll](../plans/2026-10-21-plan-f-dokumente-baselines.md#änderungsprotokoll-stufe-2) |
| G | 23 (+5 Integrator) | 20 (+3) | 3 (+1) | 0 | [Änderungsprotokoll](../plans/2026-10-21-plan-g-qa-haertung.md#änderungsprotokoll-stufe-2) |

## 3. Befunde nach Schwere

Konsolidiert aus den Befundtabellen der Pläne („Review-Befunde“) und den beiden Querreviews. Spalte „korrigiert in“
nennt die Task-ID nach Stufe 2.

### 3.1 Kritisch (ausführlich)

**QR-T01 — `persistence 0116–0118` dreifach belegt (A, B, G).** Drei Pläne hätten dieselben Migrationsnamen erzeugt.
Folge: zwei Leaf-Nodes, `migrate` bricht ab. Zusätzlich verwiesen fünf Pläne auf einen Index, den es nicht gab.
*Korrigiert:* Index §e (bindende Reihenfolge, Nummer = max+1 beim Merge). G G1.3 `0116`/`0117`, A T-A0-5
`0118_embedding_model_columns`, G G2.2 `0119_requirement_list_index`, B B5-T1 `0120`/`0121`, F F2/F3 `0122–0127`,
B B6-T1 `0128`/`0129`. KA-ALL-01, KA-A-01, KA-B-01, KA-F-01, KA-G-01.

**QR-T02 — `link_types 0010` und `attribute_definitions 0010` doppelt (B, G), F-Kette falsch gezählt.**
*Korrigiert:* G G1.4 behält `0010` (Welle 0). B nimmt `attribute_definitions 0011`, `link_types 0011/0012`.
F nimmt `link_types 0013–0015`. Seed-Migrationstests legen echte `Workspace`-Zeilen an (KA-G-10).

**RB-D01 (Plan D) — 1:1-Tausch `server.js` → Hub-Image bricht BluePencil.** Das Image hat ein anderes Auth-Secret,
eine andere Basis, einen anderen Store und einen root-eigenen Store. Der Layer fällt still aus, Notizen sind „weg“.
*Korrigiert:* D1.1 (Image-Defaults explizit gesetzt, Store-Migration). Der Hub-Auth-Konflikt bleibt bei ENT-D2.

### 3.2 Hoch (ausführlich)

| ID | Plan | Kern | korrigiert in |
|---|---|---|---|
| QR-T03 | C ↔ E | `auth_tenancy`-Reihenfolge gegen die Wellen (E `0028` vor C) | C T-C2-1 `0028–0030`, E E3.1 `0031_user_mfa` (KA-C-01, KA-E-01) |
| QR-T04 | A, C, E, F, G | Rollback- und Testbefehle mit nackten Nummern | alle PR-Tabellen: Migrationsnamen, `leaf_nodes()` (KA-ALL-02) |
| QR-T05 | A ↔ D | A legt D-Case-Dateien „neu“ an; Top-k-Assertion im Promptfoo-Harness nicht herstellbar | A T-A1-8 erweitert D-Dateien; Top-k in `test_prompt_resolver.py` (KA-A-02) |
| QR-T06 | A ↔ D | roter Baseline-Case in PR-A9 gegen Required Check | Szenario in PR-A10 mit T-A1-1 (KA-A-03) |
| QR-T07 | D ↔ B | feste Slot-Zahl 23; B fügt 4 Slots ohne Case-Datei hinzu | D D2.1/D2.2 `len(get_prompt_slots())`; B B5-T2 vier `quality_*.yaml` (KA-D-01, KA-B-02) |
| QR-T08 | A, B, C, E, F | `export_tool_manifest` schreibt nur das Manifest; Doku-Zähler und Absolutzahlen | Tool-DoD Index §f.1, Deltas statt Absolutzahlen (KA-ALL-03) |
| QR-T09 | C ↔ G | C1-Geometrie-Gate vs. G4.3-Trefferflächen (24 px) | Token `--btn-h-xs` (vorläufig ENT-C6 = B); C T-C1-1, G G4.3 (KA-C-05, KA-G-05) |
| QR-S01 | E | Selbst-Enrollment mit gestohlenem Passwort unter `required` | E3.4/E3.6 Enrollment-Grant (vorläufig ENT-E7 = A; Umsetzung erst nach Entscheidung) |
| QR-S02 | D | BluePencil-Hub ohne Auth hinter öffentlichem nginx | D1.1 Secret + `auth_request` (vorläufig ENT-D2 = B; Start D1 erst nach Entscheidung) |
| QR-S03 | alle | `.env.bak-*` mit Geheimnissen ungeschützt; `secret-scan` nur `reqlo_` | Index §h (Sofortmaßnahme), D D2.6/P1-4, KA-ALL-09 |
| QR-S04 | A | Honcho-Workspace-Suche überschreitet Workspace-/User-Grenzen | A T-A4-3, T-A4-5, T-A0b-4 (KA-A-15) |
| RB1–RB4 | A | Honcho-Felder still verworfen; zwei Memory-Konsumenten umgehen den Resolver; exakte UID nicht sicher Rang 1; Sparse-Neuanlage löscht Memory-Punkte | T-A0b-3, T-A1-2, T-A3-2/T-A3-4, T-A2-2 |
| R-B1-1, R-B1-2 | B | `rationale` wird im Interview still verworfen; Seed erreicht Bestandsdaten nie | B1-T1, B1-T3 (`--backfill-se-attributes`) |
| R-B3-2 | B | Paarprüfung ohne Subtypen | B3-T2 (generisches Subtyp-Register, KA-B-08) |
| R-B4-1 | B | WP B4 beschreibt erledigte Arbeit | B4 reduziert; ENT-B1 |
| R-B5-3 | B | werfende Regel kippt Audit und Baseline-Gate | B5-T0 |
| R-B6-1 | B | `Measure` widerspricht ADR-008 | B6 nur `Milestone`; ENT-B2 |
| R1–R3 | C | ID-Sichtbarkeit nur nach `/profile` geladen; `crypto.randomUUID` crasht auf HTTP; rohe Fehlermeldung live | T-C2-7, T-C0-1 |
| RB-D02–RB-D04 | D | SPA ohne CSP/XFO/nosniff (#155-Regression); QS-Layer nicht aus Upstream reproduzierbar; Layer 1 Jahr `immutable` gecacht | D1.0, D1.2 (ENT-D3) |
| RB-01–RB-03, RB-11 | E | #1380-Ursache falsch; „REST-Fence fehlt“ falsch; #1443-Pfad ist MCP; Key-Anlage per Passwort-Session umgeht 2FA | E2.1, E1.1/E1.2, E1.3/E1.6, E3.3/E3.6 |
| R-F1-2, R-F9-2, R-F5-1, R-F4-1, R-F4-3 | F | Mock-Tests bestätigen Fehlverhalten; Diagramme ohne Workspace unverlinkbar; `#`-Defekt auch im REST-CSV-Import; Rollback verliert nicht erfasste Felder; Tags am Snapshot unmöglich (Trigger) | F1.1-T1, F1.2-T2, F1.3-T1, F4.1, F4.2 |
| R1, R2 | G | Liste ohne `ORDER BY` (Paginierung doppelt/lückenhaft); 91 Outbox-Zeilen in den „323 ohne FK“ gegen O-2 | G2.1, G1.4 (ENT-G3) |

### 3.3 Mittel und niedrig (tabellarisch)

| Quelle | Befunde (Schwere) | Kern | korrigiert in |
|---|---|---|---|
| QR-T10 | mittel | Subtyp-Mechanismus B3-T2 ↔ F2 | B3-T2 generisch, F2 `Document → kind` (KA-B-08, KA-F-02) |
| QR-T11 | mittel | Workspace-Memory-Ebene außerhalb Q1, ohne MCP | A T-A1-2…T-A1-4, C Q1-Register (vorläufig ENT-A5 = A) |
| QR-T12 | mittel | OpenAPI-Ratchet blockiert REST-PRs aller Pläne | E E2.7 Regel, Index §f.5, KA-ALL-04 |
| QR-T13 | mittel | Milestone ohne `version` → jedes If-Match 412 | B B6-T1, E E2.5 Regel (KA-B-06, KA-E-12) |
| QR-T14 | mittel | `views.py`-Merge E ↔ G | Index §d.2 W0-Queue (KA-E-02, KA-G-03) |
| QR-T15, QR-T16 | mittel | kein Dual-Write vor Contract; Rollout-Regel nennt falsche PRs | A T-A0b-3, T-A2-1 (KA-A-06, KA-A-07) |
| QR-T17 | mittel | Phantom-CI-Jobs `build`, `dependency-check` | Index §f.2, KA-ALL-06 |
| QR-T18 | mittel | Belege unter gitignored `docs/test-reports/` | KA-ALL-07 (vorläufig ENT-X3 = C) |
| QR-T19, QR-T20, QR-T21 | mittel | `seed_demo` D↔E; Compose-Reihenfolge; Ratchet-Baseline als Konfliktdatei | Index §d.2 (KA-D-10, KA-E-03, KA-D-11, KA-C-06, KA-G-06) |
| QR-T22–QR-T30 | niedrig | Fehlpfade, Passwort-Makro, Entscheidungen vorweggenommen, feste Zählungen, Tenant-Rücksetzung, PR-Größe, Kopfzeile G, A1-Eintritt, application `0036` bedingt | siehe [Querreview §1](PLAN_QUERREVIEW_2026-10-21_TECHNISCH.md#1-befundtabelle), KA-ALL-05/-08, KA-A-04/-08/-09, KA-C-08/-09, KA-G-08 |
| QR-S05–QR-S13, QR-S16 | mittel | Prompt-Injection über Memory, `slot_name` fail-open, Qdrant-Hydrierung, Cross-Workspace B5/F4, Cutover-Altsitzungen, Promptfoo-Lieferkette, Secret-Routing A0b, Waisen-Löschung G1.4 | KA-A-16/-17/-18/-19, KA-B-10, KA-F-04, KA-E-05/-07, KA-D-04, KA-G-09 |
| QR-S11, QR-S14, QR-S15, QR-S17–QR-S23 | niedrig | Recovery-Lookup, Tenant-Rücksetzung, `seed_demo`-Passwort, CSP-Gate, `mcp-remote`-Pin, RLS im selben PR, Link-Ziel-Titel, Settings-Leak, Backup-Prüfung, Qdrant ohne Key | siehe [Sicherheits-Querreview](PLAN_QUERREVIEW_2026-10-21_SICHERHEIT.md#befundtabelle) |
| Plan A RB5–RB16 | 9 mittel, 3 niedrig | ADR-020 §4, Domain-Events, `ask_available`, Limits, SDK-Lock u. a. | [Plan A §12](../plans/2026-10-21-plan-a-memory-und-suche.md#12-review-befunde-x) |
| Plan B (13 weitere) | mittel/niedrig | siehe Plan | [Plan B (x)](../plans/2026-10-21-plan-b-se-modell.md#x-review-befunde) |
| Plan C (17 weitere) | mittel/niedrig | siehe Plan | [Plan C §12](../plans/2026-10-21-plan-c-ui-ux.md#12-review-befunde-x) |
| Plan D (20 weitere) | mittel/niedrig | u. a. RB-D18 `scripts/test_*.py` laufen in CI nicht | [Plan D (x)](../plans/2026-10-21-plan-d-deployment-dx.md#x-review-befunde) |
| Plan E RB-04–RB-10, RB-12–RB-16 | 8 mittel, 4 niedrig | Detail-404-Stub, Comments-405, If-Match-Semantik, ETag-Zeitstempel, `decrypt_secret` fail-open u. a. | [Plan E (x)](../plans/2026-10-21-plan-e-security-api.md#x-review-befunde) |
| Plan F (14 weitere) | mittel/niedrig | siehe Plan | [Plan F (x)](../plans/2026-10-21-plan-f-dokumente-baselines.md#x-review-befunde) |
| Plan G R3–R14 | mittel/niedrig | u. a. R9 Listen-Parameter → Plan E E2.9 | [Plan G §11](../plans/2026-10-21-plan-g-qa-haertung.md#11-review-befunde) |

## 4. Live-Check-Matrix

Quelle: `docs/test-reports/plan-review-2026-10-21/plan-*/live-checks.md` und `plan-c/ui-live-checks.md`
(Details, Befehle, Rohbefunde dort). Alle Prüfungen lesend gegen QS (v1.8.0-beta.22, `dc7ee14`).
Hinweis: `docs/test-reports/` ist gitignored (`.gitignore:91`); die Belege sind nicht versioniert (ENT-X3).

Bilanz: 121 Prüfungen — bestätigt 76, widerlegt 16, teilweise widerlegt 6, nicht prüfbar/nicht reproduziert 19,
Referenz/ohne Verdikt 4.

| ID | Plan | Behauptung (kurz) | Verdikt |
|---|---|---|---|
| A-L01 | A | Qdrant- und Honcho-Felder in System-Settings einstellbar | Qdrant bestätigt; Honcho widerlegt (nur Env-Fallback) |
| A-L02 / A-L02b | A | `/health/` zeigt effektives Vektor-Backend | über Frontend-Port nicht prüfbar; am Backend-Port bestätigt (Kopplung blockiert Qdrant) |
| A-L03 | A | `ask_available:true` | Messwert bestätigt; Aussagekraft widerlegt (Klassenkonstante) |
| A-L04 | A | Projection 0,9 s, nicht reproduzierbar | bestätigt; Code-Ursache besteht |
| A-L05 | A | 3 Workspace-Einträge | bestätigt |
| A-L06 | A | Workspace-Schalter kennt nur `enabled` | bestätigt |
| A-L07 | A | Honcho-Derivation liefert | Digest bestätigt; Dialektik nicht prüfbar (POST) |
| A-L08 | A | Lesepfad = Schreibpfad (#1248) | bestätigt — #1248 behoben |
| A-L09 | A | ID-Suche findet die ID | Befund: 50 semantische Fremdtreffer |
| A-L10 | A | Referenz Freitextsuche | Referenz |
| A-L11 | A | kein `mode`-Parameter | bestätigt (still ignoriert) |
| A-L12 | A | OpenAPI-Vertrag Suche/Memory | bestätigt |
| A-L13 | A | kein User-Schalter | bestätigt (404) |
| A-L14 | A | Memory-Suche auf Honcho | bestätigt |
| A-L15 | A | leerer Workspace nicht degradiert | bestätigt |
| A-L16 | A | Methodenumfang `/memory/me/` | bestätigt |
| A-L17 | A | `REQ-L1-058` existiert | Referenz: UID existiert nicht |
| A-L18 | A | UID-Schema, 880 Requirements | bestätigt (`REQ-NNN`) |
| A-L19 | A | Needs ohne semantischen Pass | bestätigt (indirekt) |
| A-L21 | A | exakter UID-Treffer vor Semantik | widerlegt (RRF-Gleichstand) |
| B-L1 | B | AC/VM/Owner/Priority leer (0/100) | bestätigt und verschärft (0/880) |
| B-L1b | B | Demo-Workspace als Zweitmesspunkt | nicht prüfbar (keine Requirements) |
| B-L2 | B | `validates`/`performs` fehlen, 11 Built-ins | bestätigt |
| B-L3 | B | `element_type` ohne `function` | bestätigt (Daten) |
| B-L3b | B | `element_type` geschlossenes Enum | widerlegt (Freitext) |
| B-L4 | B | Validierungslücke messbar | bestätigt |
| B-L5 | B | 20 Needs | bestätigt |
| B-L6 | B | 30 TestCases | bestätigt |
| B-L7 | B | Workflow-Definitionen nicht initialisiert (#272) | teilweise widerlegt (globale Defaults aktiv) |
| B-L8 | B | Interview fragt nur Titel/Beschreibung | bestätigt |
| B-L9 | B | Interview, Slots, Audit-Regeln | bestätigt |
| B-L10 | B | Factory-Protokoll, Coverage, OpenAPI | bestätigt (Verifikationsabdeckung 3,4 %) |
| B-L11 | B | B4 WS3/WS4/WS7 offen | widerlegt (umgesetzt) |
| C-L1 | C | Button-Streuung je Route | bestätigt (19/7 ist Gesamtwert, je Route 3–6) |
| C-L2 | C | Inspector fehlt bei 6 Typen | widerlegt für Version/Diff; bestätigt nur für Trace-Links-Widget |
| C-L3 | C | ErrorBoundary rendert `error.message` (UI) | nicht prüfbar (ohne Fehlerinjektion) |
| C-L4 | C | IdChip-Sichtbarkeit serverseitig | bestätigt (bereits serverseitig) |
| C-L5 | C | Markdown-Toolbar fehlt | bestätigt |
| C-L6 | C | Nav-Baum bei 1366×768 | bestätigt (scrollt, schwacher Hinweis) |
| C-L7 | C | Kontrast `/reviews` 1,18:1 | widerlegt (nicht reproduzierbar) |
| C-L8 | C | Theme-Screenshots | bestätigt |
| C-L9 | C | weitere Auffälligkeiten | Sammelbefund (i18n-Mix, unbeschrifteter Button) |
| C-L10 | C | ErrorBoundary roh im Bundle | bestätigt |
| C-L11 | C | kein generischer Präferenzdienst | bestätigt |
| C-L12 | C | Präferenz-Endpunkte im OpenAPI | bestätigt (6 Stores) |
| C-L13 | C | #1257 live | bestätigt (geschlossen) |
| C-L14 | C | `show_readable_ids` nur User-Ebene | bestätigt |
| C-L15 | C | Planbasis O3 Präferenz-Endpunkte | bestätigt |
| C-L16 | C | TestCase-Detail ohne Trace-Link-Liste | bestätigt |
| C-L17 | C | #85 keine Pagination | widerlegt |
| C-L18 | C | #85 Dashboard-Zähler veraltet | widerlegt (Code-Beleg) |
| C-L19 | C | Button-Geometrie außerhalb Tokens | bestätigt (78 Regeln/39 Dateien) |
| C-L20 | C | Theme-Toggle wird weiß | bestätigt (Ursache gefunden) |
| C-L21 | C | BluePencil deckt zentrale Löschung ab | F9 bestätigt, F11 teilweise, F10 nein |
| D-L1 | D | QS auf beta.22 | bestätigt |
| D-L2 | D | QS-Layer 0.5.0 vs. `origin/main` 0.1.0-alpha.2 | bestätigt |
| D-L3 | D | Hub 0.5.0 | bestätigt |
| D-L4 | D | Layer 1 Jahr `immutable`, ohne Security-Header | bestätigt (neu) |
| D-L5 | D | SPA ohne CSP/XFO/nosniff | bestätigt (neu) |
| D-L6 | D | `Referrer-Policy` ungültig | bestätigt (neu) |
| D-L7 | D | `/health/` am Frontend-Port nicht proxied | bestätigt |
| D-L8 | D | Hub-Image öffentlich, Tags/Digests | bestätigt |
| D-L9 | D | QS-Layer = Release v0.5.0 | widerlegt |
| D-L10 | D | ~19 Prompt-Slots | widerlegt (23) |
| D-L11 | D | Prompt-Variablen | bestätigt |
| D-L12 | D | #792 Pkt. 16 Healthcheck | bestätigt |
| D-L13 | D | #792 Pkt. 17 Backup-Aktion | bestätigt |
| D-L14 | D | Keys mit Fence-Feldern | bestätigt |
| D-L15 | D | README-Beispiele `/mcp/stdio/` | widerlegt (404) |
| D-L16 | D | #1230 npm/Registry fehlen | npm bestätigt; Registry nicht prüfbar |
| D-L17 | D | Client-CLIs | bestätigt; #1171-Aussage Codex widerlegt |
| D-L18 | D | `seed_demo` bei `DEBUG=False` | nicht prüfbar (schreibend) |
| D-L19 | D | MCP-Toolzahl live | nicht prüfbar (POST) |
| E-L1 | E | `GET /baselines/` → 404 | bestätigt (Symptom) |
| E-L2 | E | OPTIONS bewirbt GET/POST | bestätigt |
| E-L3 | E | Ursache Routenreihenfolge | widerlegt (Preset-Gate-Fallback) |
| E-L4 | E | OpenAPI Pfade/Ops | bestätigt (gewachsen) |
| E-L5 | E | `/comments/` → 405 | bestätigt |
| E-L6 | E | `GET /tracelinks/{id}/` → 404 | bestätigt (neu) |
| E-L7 | E | If-Match in 0 Pfaden | bestätigt |
| E-L8 | E | ETag nur bei 3 Typen | bestätigt und erweitert |
| E-L9 | E | If-Match-Wertematrix | nicht prüfbar (PATCH) |
| E-L10 | E | Human-Token sieht Workspaces | bestätigt |
| E-L11 | E | gefencter Key → 403 | nicht prüfbar (POST) |
| E-L12 | E | Plugin nutzt REST | teilweise widerlegt (MCP) |
| E-L13 | E | `api-keys` POST ohne Body-Schema | bestätigt |
| E-L14 | E | 124 beschnittene Views | Größenordnung bestätigt; Zahl nicht prüfbar |
| E-L15 | E | `WorkspaceViewSet` Pfadparameter-Typ | bestätigt |
| E-L16 | E | kein 2FA | bestätigt |
| F-L1 | F | QS auf beta.22 | bestätigt |
| F-L2 | F | Issue-/Risk-Vokabeln fehlen | bestätigt; `uses-term` als Typ abgelöst |
| F-L3 | F | GlossaryTerm ohne `artifact_id` | widerlegt |
| F-L4 | F | `uses-term` tot, Glossar unverlinkbar | widerlegt |
| F-L5 | F | Icd ohne `artifact_id` | widerlegt |
| F-L6 | F | Diagram nicht verlinkbar | nicht prüfbar (keine Diagramme) |
| F-L7 | F | kein `Document`/`WorkItem`-Schema | bestätigt |
| F-L8 | F | Workflow-Maschinerie vorhanden | bestätigt (+ Zusatzbefund 200 statt 404) |
| F-L9 | F | Baselines ungenutzt | bestätigt |
| F-L10 | F | ChangeRequests ungenutzt | bestätigt |
| F-L11 | F | Trace-Link-Filter `link_type`/`target_id` | widerlegt (still ignoriert) |
| F-L12 | F | Snapshot erfasst Felder nicht | bestätigt |
| F-L13 | F | Glossar-Token-Modus | bestätigt |
| F-L14 | F | CSV-Import `#`-Defekt | nicht prüfbar live; Code eindeutig |
| G-L1 | G | QS auf beta.22 | bestätigt |
| G-L2 | G | GET nach DELETE → 200 | nicht prüfbar (DELETE verboten) |
| G-L3 | G | Soft-Delete-Vertrag im OpenAPI | bestätigt; `change_reason` fehlt |
| G-L4 | G | `uid`-Abdeckung | bestätigt; neu: Needs 0/20 ohne `uid` |
| G-L5 | G | Waisen ohne FK | nicht prüfbar (SQL) |
| G-L6 | G | Liste sortiert | widerlegt (kein deterministisches `ORDER BY`) |
| G-L7 | G | Listen-Latenz | bestätigt |
| G-L8 | G | Kaltstart Schreibpfad | nicht prüfbar (POST) |
| G-L9 | G | Embedding-Provider Ollama | bestätigt |
| G-L10 | G | `/reviews`-Titel ohne Theme-Farbe (#1379) | widerlegt für beta.22 |
| G-L11 | G | Server-Limits je Typ | bestätigt (+ Modell 255 vs. Serializer 200) |
| G-L12 | G | Attributdefinition mit Länge/Pflicht | bestätigt — Länge fehlt |
| G-L13 | G | `offset` ignoriert, `page_size`-Grenzen | bestätigt |
| G-L14 | G | `/traceability/` 404 | bestätigt |
| G-L15 | G | Workspace-Projektion mit User-Punkten | nicht reproduziert |
| G-L16 | G | TestCase-Liste ignoriert `?status=` | bestätigt → Plan E E2.9 |
| G-L17 | G | `katex`-Advisory | bestätigt (Lockfile) |

## 5. Widerlegte Annahmen der Planbasis (konsolidiert)

| # | Planbasis-Aussage | Befund | Beleg |
|---|---|---|---|
| 1 | A0 „Honcho-Pin v3.3.0 (#1414)“ ist Arbeit | Pin ist gemergt; offen nur der SDK-Lock | Plan A W1 |
| 2 | A0 „QS meldet `ask_available:true`“ belegt T1 | statische Klassenkonstante | A-L03, Plan A W2 |
| 3 | A4 „Scopes (löst #1248)“ | #1248 geschlossen (PR #1304), live behoben | A-L08 |
| 4 | A2 „eigener Schalter `ARTIFACT_VECTOR_BACKEND`“ neu | Schalter existiert; zu entfernen ist Gate 3 | Plan A W8, A-L02b |
| 5 | A3 / #1316 „HNSW und FTS nie kombiniert“; #18 „nur FTS“ | RRF existiert seit #746; neu ist der Ranking-Fehler bei exakten IDs | Plan A W12, W16, A-L21 |
| 6 | §5 „Qdrant-Backend inaktiv“ | angefordert `qdrant`, aktiv `pgvector` wegen Kopplung | A-L02b |
| 7 | B4 WS3/WS4/WS7 offen | umgesetzt, Sub-Issues geschlossen | B-L11, ENT-B1 |
| 8 | B6 `Milestone` + `Measure` als ein Plan | widerspricht ADR-008 (accepted) und geschlossenem #393 | Plan B (xi) 2, ENT-B2 |
| 9 | B1 „0/100 Stichprobe“ | verschärft: 0/880, zusätzlich `rationale` 0/880 | B-L1 |
| 10 | #877 implizit `element_type` geschlossenes Enum | Freitext | B-L3b |
| 11 | C3 Inspector fehlt bei 6 Typen | vorhanden auf allen 7 Routen; nur Trace-Links fehlen | C-L2 |
| 12 | Q1/C2 #1257 ist Q1-Verbraucher | #1257 geschlossen, eigener 3-Ebenen-Store live | C-L13 |
| 13 | C2 IdChip muss serverseitig werden | seit #1096 serverseitig | C-L4, C-L14 |
| 14 | C1 „19 Höhen, 7 Radien“ je Route | Gesamtwert; je Route 3–6 | C-L1 |
| 15 | G4 Kontrast `/reviews` 1,18:1 (#1379) | in beta.22 behoben | G-L10, C-L7 |
| 16 | O2 BluePencil-Fähigkeit ungeprüft | F9 ja, F11 teilweise, F10/Retention nein | C-L21 |
| 17 | D2 „~19 Slots“ | 23 | D-L10 |
| 18 | D2 „Mock-Provider“ für Promptfoo | Projekt-Mock ignoriert den Prompt → `echo` (ENT-D8) | Plan D (xi) 4 |
| 19 | D1 „QS-Stand = Release 0.5.0“ | Bytes weichen ab | D-L9 |
| 20 | D3 „4 verworfen, 5 offen“ | 6 verworfen, 4 offen | Plan D (xi) 14 |
| 21 | D6 „Workspace-Fence laut CR-03“ | Fence = ADR-011 SEC-03; CR-03 = Key-Inventur | Plan D (xi) 15 |
| 22 | E2 / #1380 „`baselines/`-Routenreihenfolge“ | Ursache ist der Tenant-ID-Fallback im Preset-Gate | E-L3, ENT-E3 |
| 23 | E1 „REST-Fence wie MCP“ fehlt | Fence existiert; Problem sind Reihenfolge, Meldung, Liste | Plan E (xi) 2 |
| 24 | E2 „124 beschnittene View-Klassen“ | Views erscheinen ohne Body; Größenordnung bestätigt (107 statisch) | E-L14 |
| 25 | F1 / F9 GlossaryTerm/Icd ohne `artifact_id` | Spalten seit `0072`; nur Diagram offen | F-L3, F-L5 |
| 26 | F1 `uses-term` „tot“ | in `references` aufgegangen | F-L4 |
| 27 | F5 „All-or-Nothing pro Batch“ | zeilenweise Teilerfolg; `#`-Defekt bestätigt | Plan F (xi) 6 |
| 28 | G1 Soft-Delete-Vertrag fehlt | existiert (GH-443); offen nur ArchitectureElement + `change_reason` | G-L3 |
| 29 | G1 „323 hängende `workspace_id`“ als ein Fix | 91 Outbox-Zeilen unter O-2 („kein Delete“) | ENT-G3 |
| 30 | G2 `(workspace_id, created_at)`-Index als Kern | Kernproblem fehlendes `ORDER BY` | G-L6 |
| 31 | G3 Digest-Pins für alle Images | Honcho/Qdrant bereits gepinnt | Plan G §12 6 |
| 32 | §5 „`uid` 100/100“ | gilt nur für Requirements; Needs 0/20 | G-L4 |

Die Planbasis ist mit diesen Markierungen versehen (Abschnitt „Status der Umsetzungspläne“); keine Nutzerentscheidung
wurde geändert.

## 6. Entscheidungs-Konflikte

Alle Konflikte zwischen Planbasis, ADRs, Reviews und Code stehen in der
[Entscheidungsliste](../plans/2026-10-21-entscheidungen-offen.md): 54 `ENT-*`-Einträge, 21 davon als ⚠ KONFLIKT.
Sortiert nach der Welle, die sie blockieren (§1–§5), plus Nutzer-Gates U-1…U-W* (§6). Vor Welle 0 nötig:
ENT-X1, ENT-G1, ENT-G2, ENT-G3, ENT-D8, ENT-E1…E4, ENT-X3. Die Pläne arbeiten bis zur Entscheidung nur dort mit der
Empfehlung, wo die Liste „vorläufig“ erlaubt (28 vorläufige Aufträge in Stufe 2). Sicherheitskritisch und ohne
Vorläufigkeit: ENT-E7 (Enrollment-Grant), ENT-D2 (Hub-Auth), ENT-G2 (Waisen-Löschung).

## 7. Nicht prüfbar

| Bereich | Was | Grund | Ersatz |
|---|---|---|---|
| Schreibende Pfade | `memory.ask` (A-L07), If-Match-Matrix (E-L9), gefencter Key (E-L11), DELETE-Vertrag (G-L2), Kaltstart Schreibpfad (G-L8), `seed_demo` (D-L18), CSV-Import (F-L14) | Auftrag erlaubte nur lesende QS-Zugriffe | Code-Beleg im Plan; DoD verlangt Live-Nachweis nach Umsetzung |
| JSON-RPC-POST | MCP-Toolzahl live (D-L19) | POST verboten | Manifest-Wert |
| Logs/SQL | 124 beschnittene Views (E-L14), Waisen ohne FK (G-L5) | kein Docker/SSH-Zugriff | statischer AST-Scan, Code |
| Daten fehlen | Demo-Workspace (B-L1b), Diagramme (F-L6), Projektion mit User-Punkten (G-L15) | keine Daten auf QS | Code-Beleg |
| Proxy | `/health/` am Frontend-Port (A-L02) | Vite-Proxy leitet nicht weiter | Backend-Port (A-L02b) |
| UI ohne Fehlerinjektion | ErrorBoundary im UI (C-L3), Fokus-Rückgabe (C-L9) | nur lesend | Bundle-Check C-L10 |
| Extern | MCP-Registry (D-L16) | Upstream-500 | Nachprüfung bei D5 |
| Nutzerentscheidungen | 54 `ENT-*` | nicht Aufgabe der Agenten | Entscheidungsliste |

## 8. Prozess-Beobachtungen

1. **Orchestrator-Lauf endete vor Worker-Ende.** Der Orchestrator meldete Abschluss, während Worker noch liefen.
   Integration und Querreviews mussten nachgezogen werden. Ergebnisse von Workern ohne aktiven Empfänger sind
   nur über die Dateien auffindbar.
2. **Usage-Limit-Unterbrechungen.** Mehrere Läufe brachen am Nutzungslimit ab und wurden neu gestartet.
   Folge: Doppelarbeit und Reste unter `.tmp/` (Abschnitt Hygiene im Abschlusslauf).
3. **UI-Tester hat das Theme umgeschaltet.** Der `e2e-tester` hat für Plan C den Theme-Toggle betätigt. Das Theme
   ist account-persistent; er hat es auf Hell zurückgestellt (`plan-c/ui-live-checks.md`, Kopf). Das war eine
   Schreibaktion gegen den lesenden Auftrag. Kein dauerhafter Schaden.
4. **Planer ohne Bash.** Die Rolle `planner` hat kein Bash. Sie kann weder `ls`-Prüfungen (Migrationsstände) noch
   lesende `curl`-Live-Checks selbst ausführen; diese Prüfungen hingen an anderen Rollen.
5. **Belege nicht versioniert.** `docs/test-reports/` ist gitignored; die Live-Belege sind ohne ENT-X3 für spätere
   Reviewer nicht nachprüfbar.

Die Punkte 1, 2 und 4 betreffen das Agenten-Framework und sind dort gemeldet: **agent-meta Issue #1004**.

## 9. Nächste Schritte

1. Nutzer: Sofortmaßnahme Index §h (`.env.bak-*`), danach ENT-X1, ENT-G1…G3, ENT-D8, ENT-E1…E4, ENT-X3.
2. Welle 0 starten (C0, D2/D2.6/D1.0, E1/E2, G1) nach Index §d.1, max. 4 Agenten.
3. Nach Entscheidungen: vorläufige Stellen in den Plänen auf „entschieden“ umstellen, Index §e bei ENT-A5/ENT-G3 nachziehen.
4. `effort-estimator` für die Aufwandsschärfung (Planbasis O5).
