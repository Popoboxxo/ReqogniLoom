---
type: STRATEGY
scope: Issue-Backlog (67 offene Issues), Cluster A–G
status: proposed
date: 2026-10-21
author_agent: claude-main-chat
---

# Backlog-Umsetzungspläne — Cluster, Entscheidungen, Reihenfolge

Grundlage: 67 offene Issues (alle von Popoboxxo), gegen Repo-Stand `origin/main`
und QS-System (v1.8.0-beta.22) geprüft. Jede Entscheidung unten
hat der Nutzer in der Planungssitzung vom 2026-10-21 getroffen.
Dieses Dokument ist die **Planbasis**. Umsetzungsstand, Links und Faktenkorrekturen: §6. Je Plan folgt ein eigener Spec
(`docs/superpowers/specs/`) und danach ein Umsetzungsplan (`writing-plans`).

## 1. Querschnittsentscheidungen

| # | Entscheidung | Wirkung |
|---|---|---|
| Q1 | Ein generischer **3-Ebenen-Präferenzdienst** (global → Workspace → User, serverseitig, REST+MCP) | Nutzer: #1094 IDs, #1287 Markdown-Toolbar, #1257 Nav-Baum, A1 Memory-Schalter |
| Q2 | **Promptfoo vor A1** (#587) | Regressionsnetz für Prompt-Variablen |
| Q3 | **Port statt neuer Schicht** für Memory | `MemoryBackend`+Registry existiert; wird gehärtet (A0b) |
| Q4 | Key-Prinzipale folgen **MCP-Semantik** (Workspace-Fence statt RBAC) | #1444, #1443, #1439 |

## 2. Pläne

### Plan A — Memory & Suche

Entscheidungen: Qdrant **Option B** (Vollbetrieb, additiv + pgvector-Fallback; ADR-022 auf `accepted`
setzen, Empfehlungstext des Entwurfs wird überstimmt). Honcho **Option A** (Vollausbau jetzt;
ADR-023 `accepted`). Memory-Injektion **3 Ebenen, Minimum gewinnt, User-Schalter wirkt auf die
Aktivitäten des Users** (ADR-024 `accepted`). Artefakt-Vektor-Backend wird von `MEMORY_BACKEND`
**entkoppelt**. Memory-Inhalt ist im Prompt-Manager per benannten Variablen steuerbar.

| WP | Inhalt | Issues | Abhängig von |
|---|---|---|---|
| A0 | Honcho-Pin v3.3.0 (#1414), `memory.ask` live beweisen (T1; QS meldet `ask_available:true` — *Korrektur §6 K2: Klassenkonstante, kein Beweis*), Embedding-Quelle vereinheitlichen, Embedding-Modellname neben Vektoren persistieren | #1317, #1336 | – |
| A0b | **Memory-Port härten:** backend-neutrale Settings (Schema je Backend aus der Registry statt `honcho_*`-Spalten in `SystemMemorySettings`), Capability-Flags (`dialectic`, `search`, `consolidation`, `scopes`), Limits vom Backend (`MAX_ASK_QUERY_CHARS` raus aus dem Service), Conformance-Testsuite für jedes Backend. Honcho-Extras nur als optionale Port-Capabilities. Ziel: Honcho später entkoppeln oder anderes System anbinden. | neu (aus #1337) | – |
| A1 | Injektion: `HARD_OFF` (Verdichtung + Selbstreferenz), `slot_name` durchreichen, `disabled_slots`, `allow_user_opt_out`, `UserMemorySettings` (über Q1), `memory_injected` in Antworten, `bundle_compression` ohne Memory. Prompt-Manager: `config`-Variablen `memory_top_k`, `memory_scopes`, `memory_max_chars`, `memory_format`, `memory_include_dates`, `memory_query_fields`, `memory_section_heading`; Platzhalter je Scope. `{memory_context}` bleibt unverändert. | #1339 | Q1, Q2, A0b |
| A2 | Qdrant-Ausbau: eigener Schalter `ARTIFACT_VECTOR_BACKEND` (*Korrektur §6 K4: existiert, zu entfernen ist die Kopplung*) ohne Kopplung an `MEMORY_BACKEND`, Payload-Indizes, generischer Artefakt-Indexer (14 Typen, Hooks inkl. Löschen, idempotent), Backfill-Command, BM25-Sparse + RRF, Quantization, Snapshot-Doku, Fallback auf pgvector mit `degraded:true` | #1314, #1334 | A0 |
| A3 | pgvector-Hybrid (*Korrektur §6 K5: RRF existiert seit #746*): `mode`-Parameter (`vector\|keyword\|hybrid`), TraceLink/Icd verdrahten, Recall-Messset (20 Anfragen inkl. ID-Suchen) | #1316 (neu formulieren) | – |
| A4 | Honcho-Vollausbau über den Port: Dream periodisch, Peer-/Workspace-Suche, Context-Sammelabruf, Session-Summaries, Scopes (löst #1248 — *Korrektur §6 K3: #1248 bereits behoben*), Webhooks | #1336, #1337 | A0, A0b, T1 |

Weitere Schritte: #18 schließen (RRF-Suche existiert, #746 — *bestätigt, §6 K5*). #1378 (Projection) in Bugfix-Session
(Sampling vor Embedding; auf QS bei wenigen Einträgen nicht reproduzierbar: 0,9 s).

### Plan B — SE-Modell, Attribute, Qualität

Entscheidungen: NASA-SE-Ebene **gestaffelt**; Qualitätsbewertung **nur advisory in v1**.

| WP | Inhalt | Issues |
|---|---|---|
| B1 | Seed füllt `acceptance_criteria`, `verification_method`, `owner`, `priority` (QS: 0/100 Stichprobe). Interview fragt AC/VM/Rationale ab (`ai_elicit`). #272 schließen (4/5 gebaut, Rest hier) | #272 |
| B2 | Link-Typ `validates` (TestCase→StakeholderNeed), Validierungs-Coverage, `verification_method` im VCRM | #878 |
| B3 | `ArchitectureElement.element_type='function'`, Link `performs`, `satisfies`→function | #877 |
| B4 | Attribut-v3-Rest: WS3 Display-Engine, WS4 Layout-Engine, WS7 AWMS-Wertemigration; ADR-004 auf `accepted` (*Korrektur §6 K7: WS3/WS4/WS7 umgesetzt; ENT-B1*) | #934, #941 |
| B5 | Qualitätsbewertung: Slots `quality_*` (Prompt-Override je Workspace), `quality.assess` (MCP+REST), Score-Historie, UI-Badge, `QUAL-*` als Auditor-Warnung (nie Blocker). Slots **ohne** Memory-Injektion (HARD_OFF). Aufwand laut Scoping 8–11 Tage | #378 |
| B6 | Später: `Milestone` + `Measure` als ein Plan „Technical Planning" (*Konflikt §6 K8: `Measure` vs. ADR-008; ENT-B2*) | #879, #393 |

### Plan C — UI/UX

| WP | Inhalt | Issues |
|---|---|---|
| C0 | `ErrorBoundary` rendert `error.message` roh (Sicherheitsbefund W4a) → neutrale Meldung + Referenz-ID | #598 |
| C1 | Button-Standard: ≤3 Höhen, ≤2 Radien je Route (QS: 19 Höhen, 7 Radien — *Korrektur §6 K14: Gesamtwert, je Route 3–6*), Ratchet-Deckel senken | #1258, #186 |
| C2 | Präferenzdienst Q1 + Verbraucher: IdChip-Sichtbarkeit serverseitig, Markdown-Toolbar (`MarkdownField`-Wrapper), Nav-Baum (*Korrektur §6 K12: #1257 geschlossen und live*) | #1094, #1287, #1257 |
| C3 | Inspector (Version/History/Diff) für ADR, Risk, Issue, TestCase, Need, Glossary + Trace-Links-Widget (*Korrektur §6 K11: Inspector vorhanden, nur Trace-Links fehlen*) | #801 |
| C4 | Formular-/A11y-Härtung aus Plan G4 | siehe G |

Schließen/umformulieren: #186 neu schneiden (Epic abgearbeitet), #946 durch BluePencil ersetzt
(Rest nur falls BluePencil zentrale Löschung/Audit nicht kann), #85 veraltet, #1094 Rest über C2.

### Plan D — Deployment, DX, Onboarding

| WP | Inhalt | Issues |
|---|---|---|
| D1 | BluePencil **B+C:** Hub als Image (`ghcr.io/popoboxxo/bluepencil`), `server.js` entfällt; Layer-Artefakte als Read-only-Mount, Health-Check bei fehlendem Mount | #1418 |
| D2 | Promptfoo (`export_promptfoo_configs`, `cases/*.yaml`, CI-Job, Mock-Provider — *Konflikt §6 K18: ENT-D8*) — **vor A1** | #587 |
| D3 | #792 neu schreiben (≈9/18 erledigt, 4 verworfen, 5 offen), nur Offenes weiterverfolgen | #792 |
| D4 | Client-Doku je Harness DE/EN (12 kaputte Anweisungen, 16 Lücken) | #1171 |
| D5 | Externe Publikation W1–W5 (Accounts, npm, MCP-Registry) — Handarbeit des Nutzers | #1230 |
| D6 | #92 verifizieren (Workspace-Fence laut CR-03 vorhanden — *Korrektur §6 K21: Fence = ADR-011 SEC-03*) und schließen; #89 Rest (`seed_demo` gegen `DEBUG=False` absichern) prüfen | #92, #89 |

### Plan E — Security, API-Vertrag

| WP | Inhalt | Issues |
|---|---|---|
| E1 | Key-Prinzipale: REST-Fence wie MCP, `GET /workspaces/` liefert eigene Workspaces, sprechende Fehler, Matrix-Test REST+MCP je Key; Fehlersammlung in `api-keys` (alle Fehler in einer 400, OpenAPI-Body); Plugin-Dashboard zeigt 403-Grund | #1444, #1443, #1439 |
| E2 | API-Vertrag ehrlich: `baselines/`-Routenreihenfolge (*Korrektur §6 K22: #1380-Ursache ist der Preset-Gate-Fallback*), 124 beschnittene View-Klassen im Schema, If-Match strikt (nur starke Validatoren, sonst 400/412), ETag für alle mutablen Typen oder Zusage einschränken, `If-Match` im OpenAPI deklarieren | #1380, #1388, #1396, #1397 |
| E3 | 2FA/TOTP für Staff mit `pyotp` (Sign-off + `dependency-check` vor Merge), Recovery-Codes, ADR-021 O5 Nachtrag | #1308 |

### Plan F — Dokument-Artefakte & Baselines

| WP | Inhalt | Issues |
|---|---|---|
| F1 | Stufe 1 (Voraussetzungen): Issue-/Risk-Linkvokabeln in zentrale Validierung (F1-Befund), GlossaryTerm/Diagram/Icd bekommen `artifact_id` und sind verlinkbar (F9), native Ingestion statt CSV (F5) | #1374 |
| F2 | Stufe 2: `Document` + Workflow auf vorhandener Maschinerie + `documented-in`, `evidences`, `depends-on`; Freigabe = Feld-Freeze | #1374 |
| F3 | Stufe 3: `WorkItem`, `work_item.resume`, Checkpoints, Inline-Verweise `[[Term]]`. Abgrenzung: Memory = „was war", Loom = „wo steht das Vorhaben" | #1374 |
| F4 | Baselines: Rollback **additiv** (neue Version aus Snapshot, Immutability-Trigger unberührt, mit CR-Freigabe), Tags/Labels | #50 |

Jede Stufe F1–F3 bekommt einen eigenen Spec.

### Plan G — QA-Härtung (aus Befund-Runde `qa-beta22`)

| Bündel | Issues |
|---|---|
| G1 Datenintegrität: Soft-Delete-Vertrag, ReqIF-Import mit `uid`+Embedding, `uid`-Eindeutigkeit für alle Typen, 323 hängende `workspace_id` ohne FK (*Konflikt §6 K29: 91 Outbox-Zeilen unter O-2, ENT-G3*) | #1381, #1386, #1402, #1403 |
| G2 Performance: HNSW-Index-Nutzung, `(workspace_id, created_at)`-Index, Schreibpfad-Kaltstart | #1399, #1400, #1401 |
| G3 Betrieb: Compose-Projektname, Celery-Logflut (51k Zeilen), Image-Digest-Pins | #1387, #1389, #1391 |
| G4 Formulare/A11y: Kontrast `/reviews` (1,18:1 — *Korrektur §6 K15: in beta.22 behoben*), `maxlength`, Pflichtfelder (`required`/`aria-required`), Treffergröße ≥24 px | #1379, #1392–#1395 |
| G5 Sammel-Lows | #1404–#1412 |

## 3. Reihenfolge

1. **Welle 0 (klein, parallel):** C0, D2 (Promptfoo), G1, E2, E1.
2. **Welle 1 (Fundament):** A0, A0b, Q1 (Präferenzdienst), C1.
3. **Welle 2:** A1, A2, A3, C2, C3, G2–G4, D1.
4. **Welle 3:** A4 (nach T1-Beweis), B1–B5, E3, F1, F4.
5. **Welle 4:** F2, F3, B6, D3–D5 und Rest.

Begründung: Welle 0 behebt Vertrags- und Sicherheitslücken ohne Abhängigkeiten. A1 braucht Q1, Q2 und A0b. A4 braucht
funktionierende Dialektik. B5 nutzt `HARD_OFF` aus A1.

## 4. Offene Punkte

- **O1:** `ADR-022/023/024` sind `proposed`. Statuswechsel (`accepted`) und Superseding von ADR-020 liegt bei `se-architect` + Nutzer.
- **O2:** Ob BluePencil zentrale Löschung, Audit-Log und RBAC (F9–F11 aus #946) abdeckt, ist ungeprüft.
- **O3:** Wirkung des Präferenzdienstes Q1 auf bestehende Endpunkte (`users/me/preferences/` ist workspace-scoped, `notification-preferences` hat geschlossenes Vokabular) — Migrationspfad klären.
- **O4:** Interaktion A2 und Honcho: Entscheidung 7a (getrennt halten) bleibt gültig; Entkopplung des Selektors ist Voraussetzung.
- **O5:** Aufwandszahlen je WP stehen noch aus (`effort-estimator`).
- **O6:** Backfill-Last von A2 (2.338 Artefakte, 11 Typen ohne Embedding) auf Produktionsgröße abschätzen.

## 5. QS-Messungen (2026-10-21, v1.8.0-beta.22)

- Memory: Backend `honcho`, `ask_available:true`, `degraded:false`; Projection 0,9 s; 3 Workspace-Einträge.
- Requirements (Zahnbürste-Workspace, 880): `acceptance_criteria`, `verification_method`, `owner`, `priority` je 0/100 in der Stichprobe; `uid` 100/100 (*Korrektur §6 K32: nur Requirements; Needs 0/20*).
- Qdrant-Backend inaktiv; Qdrant-Felder in den Settings vorhanden (*Korrektur §6 K6: angefordert `qdrant`, aktiv `pgvector` wegen Kopplung*).
- Requirements: zusätzlich `rationale` 0/880 in der Vollerhebung (*Korrektur §6 K9: 0/880 statt Stichprobe 0/100*).

## 6. Status der Umsetzungspläne (Nachtrag 2026-10-22)

Status dieses Dokuments bleibt `proposed`. Die Nutzerentscheidungen in §1–§3 gelten unverändert; dieser Abschnitt
ergänzt nur Verweise und markiert Fakten, die die Live-Checks und Code-Prüfungen korrigiert haben.

**Dokumente:**

| Dokument | Zweck |
|---|---|
| [Plan-Index](../../plans/2026-10-21-backlog-umsetzung-index.md) | verbindlich: Wellen, Abhängigkeiten, Merge-Queues, Migrationsvergabe, CI-Jobs, Rollen |
| [Entscheidungsliste](../../plans/2026-10-21-entscheidungen-offen.md) | 54 offene Nutzerentscheidungen `ENT-*` (21 Konflikte), Nutzer-Gates |
| [Korrekturaufträge](../../plans/2026-10-21-korrekturauftraege.md) | Stufe-2-Arbeitsliste nach den Querreviews |
| [Review-Bericht](../../reviews/PLAN_REVIEW_2026-10-21_BACKLOG_UMSETZUNG.md) | Abschlussbericht: Befunde, Live-Check-Matrix, widerlegte Annahmen |
| [Plan A](../../plans/2026-10-21-plan-a-memory-und-suche.md) · [B](../../plans/2026-10-21-plan-b-se-modell.md) · [C](../../plans/2026-10-21-plan-c-ui-ux.md) · [D](../../plans/2026-10-21-plan-d-deployment-dx.md) · [E](../../plans/2026-10-21-plan-e-security-api.md) · [F](../../plans/2026-10-21-plan-f-dokumente-baselines.md) · [G](../../plans/2026-10-21-plan-g-qa-haertung.md) | Umsetzungspläne, je Plan Stufe 2 integriert, Status `proposed` |

**Abweichung von §2 (nur Form, keine Entscheidung):** Die Pläne sind direkt als Umsetzungspläne unter `docs/plans/`
entstanden. Eigene Specs je Plan entstehen nur für F1–F3 (ENT-F0) und vor Welle 4.

**Faktenkorrekturen (K-Nummern = Review-Bericht §5):**

| K | Stelle hier | Korrektur | Beleg |
|---|---|---|---|
| K2 | A0 „QS meldet `ask_available:true`“ | Klassenkonstante, kein Funktionsbeweis für T1 | A-L03 |
| K3 | A4 „löst #1248“ | #1248 geschlossen (PR #1304), live behoben | A-L08 |
| K4 | A2 „eigener Schalter `ARTIFACT_VECTOR_BACKEND`“ | Schalter existiert; neu ist nur die Entkopplung (Gate 3) | A-L02b |
| K5 | A3 / #18 | RRF (Semantik + Lexik) existiert seit #746 — #18 schließen bleibt richtig; #1316 „nie kombiniert“ ist widerlegt, offen ist der Ranking-Fehler bei exakten IDs | A-L21 |
| K6 | §5 „Qdrant-Backend inaktiv“ | angefordert `qdrant`, aktiv `pgvector` wegen Kopplung an `MEMORY_BACKEND` | A-L02b |
| K7 | B4 | WS3/WS4/WS7 sind umgesetzt; B4 reduziert sich auf Test + Doku + ADR-004 (ENT-B1) | B-L11 |
| K8 | B6 `Measure` | widerspricht ADR-008 (accepted) und geschlossenem #393 — Entscheidungs-Konflikt ENT-B2 | ADR-008 |
| K9 | B1 / §5 „0/100 Stichprobe“ | Vollerhebung 0/880, `rationale` ebenfalls 0/880 | B-L1 |
| K11 | C3 Inspector | Version/History/Diff vorhanden auf allen 7 Routen; es fehlt nur das Trace-Links-Widget | C-L2 |
| K12 | C2 Nav-Baum #1257 | geschlossen, eigener 3-Ebenen-Store live (ENT-C2) | C-L13 |
| K14 | C1 „19 Höhen, 7 Radien“ | Gesamtwert; je Route 3–6 Höhen/Radien | C-L1 |
| K15 | G4 / #1379 Kontrast | in beta.22 behoben, nicht reproduzierbar | G-L10, C-L7 |
| K18 | D2 „Mock-Provider“ | Projekt-Mock ignoriert den Prompt; Promptfoo braucht `echo` — Konflikt ENT-D8 | Plan D (xi) 4 |
| K21 | D6 „Workspace-Fence laut CR-03“ | Fence = ADR-011 SEC-03; CR-03 = Key-Inventur | Plan D (xi) 15 |
| K22 | E2 / #1380 Routenreihenfolge | Ursache ist der Tenant-ID-Fallback im Preset-Gate; Routen bleiben (ENT-E3) | E-L3 |
| K29 | G1 „323 hängende `workspace_id`“ | 91 davon Outbox-Zeilen unter O-2 („kein Delete“) — Konflikt ENT-G3 | Plan G §12 |
| K32 | §5 „`uid` 100/100“ | gilt nur für Requirements; StakeholderNeeds 0/20 | G-L4 |

Weitere Korrekturen (u. a. D2 23 statt ~19 Slots, D3-Zählung, E2 „124 Views“, F1/F9 `artifact_id`, G1 Soft-Delete-Vertrag
existiert): Review-Bericht §5. Offene Punkte §4: O1 → ENT-X2/ENT-X4, O2 → C-L21 + ENT-C4, O3 → ENT-C5, O4 → ENT-A2,
O5 → Index §a (Schätzung der Planautoren, `effort-estimator` offen), O6 → Plan A WP A2.
