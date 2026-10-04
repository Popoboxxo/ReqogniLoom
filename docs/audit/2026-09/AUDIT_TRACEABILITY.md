---
type: REVIEW
scope: wp5-traceability
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 — Anforderungs-Traceability-Audit

> **Reine Audit-Arbeit.** Keine Produkt-Fixes, keine Änderungen an REQ-Dokumenten,
> keine Änderungen unter `docs/se/**`. Alle Kommandos read-only gegen
> Branch `chore/system-audit-2026-09` @ `75beb750` (= main @ `abd61aed`).
> Der laufende Stack wurde nicht angefasst; die beiden Container-Abfragen in
> Evidenz 4 waren `SELECT`-Abfragen.

## 0. Ampel WP-5

| Kriterium | Status | Kennzahl |
|---|---|---|
| REQ-Inventar vorhanden und abgestimmt | 🔴 | 835 REQ-IDs in der Quelle, 511 in der Matrix, **0 Phantom / 324 fehlend** |
| Belegungsgrad der REQs ermittelt | 🟡 | 42.9 % mit Test-Bezug; Belegungsstichprobe n = 29 |
| Anteil aspirational beziffert | 🟡 | **10.3 % – 57.1 %** (belegte Unter-/Obergrenze) |
| REQ ↔ Code-Widersprüche systematisch gesucht | 🔴 | **7 belegte Widersprüche**, davon 4 Critical |
| ADR-Traceability regelkonform | 🔴 | `open_adrs` **0/835**, 14/15 `arch_impact:true` ohne ADR, 4/10 ohne Frontmatter |
| Tests entlang Traceability organisiert | 🔴 | 57.1 % der REQs ohne jeden Test-Bezug |
| Reale Testdefinitionszahlen ermittelt | ✅ | 10 052 Backend / 2 385 Frontend / 54 E2E-Specs |
| DoD-Abnahmen geprüft | 🔴 | 4 **ABNAHME-FALSCH**, 0 REQ-Bezug in 11 Release-/Testplan-Berichten |

**Gesamtbewertung: 🔴 ROT.** Die Traceability-Kette ist vorhanden, aber weder
zählbar noch gepflegt. Sie taugt derzeit **nicht als Nachweis für
Implementierungsstand oder Testabdeckung** — in beide Richtungen.

---

## 1. REQ-Inventar (Aufgabe 1)

### 1.1 Zahlen je Ebene

| Ebene | SOLL-Quelle `docs/se/L0`+`docs/se/L1` | `docs/se/traceability-matrix.md` | Matrix §4 behauptet |
|---|---|---|---|
| REQ-L0 (Stakeholder Needs) | **58** | 58 | 58 ✔ |
| REQ-L1 (System) | **94** | 94 | 94 ✔ |
| REQ-L2 (Subsystem) | **329** | 305 (290 in Tabellen + 15 tote Verweise) | 290 ✘ |
| REQ-L3 (Komponente) | **354** | **54** (nur Lückenlisten, keine Tabelle) | 369 ✘ |
| **Gesamt** | **835** | 511 | 811 |

Zusätzlich: 116 `COMP-*`-Komponenten, 10 ADRs.

### 1.2 Drift beide Richtungen

* **Phantom-REQs (nur Matrix, keine Quelle): 0.** Die Matrix erfindet nichts.
* **Fehlende REQs (Quelle, fehlen in Matrix): 324** — L2: 24, L3: 300, L0/L1: 0.

Die 24 fehlenden L2-IDs sind keine Randnotiz: 15 davon (`REQ-L2-AppSvc-001…025`)
werden von `traceability-matrix.md:721` aktiv als *„nicht existent"* gelistet,
obwohl `backend/application/import_service.py:5` und
`backend/application/tests/test_import_service.py:5` sie im Code führen.
Es existieren **drei REQ-ID-Räume parallel** (kanonisch `REQ-L2-AS-001`,
Legacy `REQ-L2-AppSvc-014`, alt `REQ-L3-EXP-001`).

**Nulllücke L0:** `REQ-L0-031` existiert nirgends; die Matrix springt 030 → 032.

**Strukturell:** Die Matrix publiziert **keine einzige `REQ-L3`-Zeile**
(`rg -c '^\| REQ-L3-'` → 0). 354 von 835 REQs (42 %) sind im SOLL-Artefakt
**nicht einzeln adressierbar**.

→ Detail: `AUDIT_EVIDENCE/wp5-01-req-inventar.md`

---

## 2. Belegungsgrad (Aufgabe 2)

### 2.1 Methodik

Drei Messungen mit ausgewiesener Stichprobengröße, keine Hochrechnung ohne
Grundlage:

| Messung | Umfang | Verfahren |
|---|---|---|
| **M1** Test-Referenz | **n = 835 (100 %)** | Mengenschnitt Quell-IDs × IDs in Testdateien |
| **M2** Selbst-Marker | **n = 783 (94 %)** | Parser über alle `### REQ-…`-Blöcke |
| **M3** Code-Beleg | **n = 29, stratifiziert** | 2 REQs je L2-System → **20/20 Subsysteme** |

### 2.2 Gesamtzahlen

| Kennzahl | Wert |
|---|---|
| REQ-IDs mit ≥1 Test-Referenz | **358 / 835 = 42.9 %** |
| REQ-IDs ohne jede Test-Referenz | **477 / 835 = 57.1 %** |
| L0 / L1 / L2 / L3 Test-Quote | 29.3 % / 37.2 % / 52.0 % / 38.1 % |
| Selbst-deklariert nicht umgesetzt | **307 / 835 = 36.8 %** |
| Stichprobe L2: aspirational | **3 / 29 = 10.3 %** |
| Stichprobe L2: aspirational + `nur_doku` | **5 / 29 = 17.2 %** |
| Stichprobe L2: **Marker invertiert** (Code+Tests da, REQ sagt nein) | **7 / 29 = 24.1 %** |

### 2.3 Anteil aspirational — die Antwort

**Belegte Untergrenze 10.3 %, belegte Obergrenze 57.1 %.**

* **10.3 %** = Anteil der REQs in der stratifizierten Stichprobe (n = 29, alle
  20 L2-Subsysteme), für die ein **negativer Symbol-Nachweis** vorliegt: weder
  Produktionscode noch Test.
* **57.1 %** = Anteil aller 835 REQs, für die **keinerlei Test-Bezug**
  nachweisbar ist. Das ist eine notwendige, nicht hinreichende Bedingung für
  „aspirational", aber eine belegte Obergrenze.
* Die Selbstauskunft der Dokumente (36.8 %) liegt dazwischen, ist aber als
  *dokumentierte Absicht* zu lesen: sie ist als *Ist-Stand* nachweislich zu
  niedrig, weil 24.1 % der Stichprobe **invertiert** markiert sind.

**Kernaussage:** Die Verteilung ist nicht „viel Aspirational", sondern
**„unzuverlässige Marker"**. Der gravierendere Befund ist nicht der
aspirational-Anteil, sondern dass die Matrix 7 von 29 geprüften REQs falsch
klassifiziert — 5 zu niedrig, 2 zu hoch.

→ Detail: `AUDIT_EVIDENCE/wp5-05-belegungsmatrix.md`

---

## 3. Widersprüche REQ ↔ Implementierung (Aufgabe 3)

**7 belegte Widersprüche**, 4 Critical, 3 High. Jeder mit REQ-Zitat + `datei:zeile`.

### Die 5 wichtigsten

| # | REQ-ID | REQ-Zitat (Kern) | Beleg | Schwere |
|---|---|---|---|---|
| **1** | **`REQ-L2-MC-014`** | *„Der MCP-Server MUSS ein Tool `semantic_search` bereitstellen …"*, Marker **Implemented / Covered**, Review Findings *„MCP-Server exportiert das Tool `semantic_search` standardkonform."* (`L2_McpServerSystem_Requirements.md:97-107`) | `rg 'semantic_search' backend frontend/src e2e` → **1 Treffer, ein Testmethodenname** (`application/tests/test_search_semantic_fusion.py:101`). Kein `search.py` in `backend/mcp_server/tools/` (29 Module). Konvention ist `<gruppe>.<verb>`; vorhanden ist `artifact.search` (`tool_registry.py:418`). Die Abhängigkeit `REQ-L2-VS-001` ist selbst `Not Implemented`. | **Critical** |
| **2** | **`REQ-L1-046`** | *„Das System MUSS vollständige, automatisierbare Instanz-Snapshots (Backup) aller …"* — Marker **Implemented / Covered** | Einziges Kind `REQ-L2-BL-011` = **Not Implemented** (`matrix:331`). `scripts/restore.sh` existiert, wird aber nie ins Image kopiert: `backend/Dockerfile:154` ist `COPY . .` mit Context `backend/`; `rg 'restore' backend/Dockerfile deploy/docker-compose.yml` → **0 Treffer**. | **Critical** |
| **3** | **`REQ-L1-013`** | *„… wobei der LLM-Anbieter und API-Key pro Deployment konfigurierbar sind und das System ohne LLM-Zugang vollständig funktionsfähig bleibt."* — Marker **Implemented / Covered** | `backend/llm_adapter/providers.py:1080 MODEL_NAME = "claude-3-opus-20240229"` — vom Provider am 2026-01-05 abgeschaltet. `LLM_MODEL` ist in allen Compose-Dateien leer (`.env.example:184` nur auskommentiert). Der Defekt ist als **Erwartungswert im Test fixiert**: `backend/rest_api/tests/test_llm_settings.py:248`. | **Critical** |
| **4** | **`REQ-L1-016`** | *„Das System muss alle UI-Texte und Backend-Fehlermeldungen in Deutsch und Englisch bereitstellen, **wobei fehlende Translation-Keys als Build-Fehler behandelt werden (Lint-Regel)** …"* — Marker **Implemented / Covered** | 112 `t()`-Keys fehlen in **beiden** Locale-Dateien. Die zugesagte Lint-Regel existiert nicht als wirksame Schranke; der Parity-Ratchet bleibt grün. 7 einschlägige Issues sind **geschlossen** (#676, #421, #595, #610, #651, #653, #654). | **High** |
| **5** | **`REQ-L1-021`** | *„… der **Validierung gegen das Datenmodell durchführt**, Fehler mit Zeilennummer zurückmeldet …"* — Marker **Implemented / Covered** | `backend/application/import_service.py:226-233` meldet unerkannte Spalten nur in `warnings`; `ImportResult.success: bool` (`:149`) bleibt `True`. Ein Import, der eine ganze Spalte verwirft, wird als Erfolg berichtet. Docstring `:136`: *„success: True if all valid rows were persisted"*. | **High** |

### Weitere

| # | REQ-ID | Kern | Beleg | Schwere |
|---|---|---|---|---|
| 6 | `REQ-L2-LA-007` | Azure-Provider „Implemented" | Python ja (`llm_adapter/providers.py:1674 PROVIDER_NAME = "azure"`), **nicht wählbar**: `frontend/src/api/llm-settings.ts:22` `LlmProvider = "anthropic" \| "openai" \| "ollama" \| "opencode_go" \| "mock"` | High |
| 7 | `REQ-L2-RO-001`/`AS-029`/`LA-008` | Asynchronie „Implemented/Covered" | Celery-Fanout 4× je Task (`AUD-2026-09-120`) | High |

### Dokument-intern: 17 REQ-L1 `Implemented` mit nicht-implementiertem Kind

Vollständig widersprüchlich: `REQ-L1-005` (8 von 12 Kindern nicht implementiert),
`REQ-L1-039` (2 von 3), `REQ-L1-046` (1 von 1). Dazu **4 `Implemented`-REQ-L1
ohne jede L2-Zerlegung**: `REQ-L1-042` (Workspace-Lifecycle mit transaktionaler
Kaskaden-Löschung + Captcha), `-043`, `-044`, `-100`, `-101`.

### Reconciliation: zwei Parallelbefunde — **Korrektur 2026-09-30**

> **Zurückgenommen (unabhängige Gegenprüfung, `AUDIT_EVIDENCE/verification-2026-09-30.md` §7.5).**
> Die folgende Tabelle führte `-121` und den Beat-Teil aus `-120` als *widerlegt*.
> Das war **falsch**: der Test `audit/tests/test_sa39_append_guard_` registriert die
> Task im **Testprozess** (er importiert `audit.archive`), und die
> `django_celery_beat_periodictask`-Zeile ist eine **Beat-Schedule**-Zeile — beides
> adressiert die Frage **„ist die Task im *Worker*-Task-Set registriert?"** nicht.
> Die Gegenprüfung hat die Gegenrichtung bestätigt: `-121` und `-270` **gelten**.

| Befund | Messung | Ergebnis |
|---|---|---|
| `AUD-2026-09-121` „Audit-Archivierung nie registriert" | `settings.py:822` ist ein Eintrag in **`CELERY_BEAT_SCHEDULE`** (`:817-830`), **nicht** die Worker-Registrierung. `audit/apps.py:36` importiert nur `audit.writer`; `backend/audit/tasks.py` existiert nicht; kein Nicht-Test-Code importiert `audit.archive` | **BESTÄTIGT** — die Task ist nie im Worker-registriert, die monatliche Retention läuft nie. (Früher hier „widerlegt" — **zurückgenommen**, siehe Kasten oben) |
| Beat-Teil aus `AUD-2026-09-120` / `-121` | Wie vor: die Beat-Schedule-Zeile beweist **nicht**, dass `celery-beat` die Task tatsächlich dispatcht | **BESTÄTIGT** — der Beat-Teil ist damit **nicht** widerlegt. Der 4×-Fanout aus `-120` bleibt davon unberührt. (Früher hier „widerlegt" — **zurückgenommen**) |
| `AUD-2026-09-129` „Health meldet ok bei Totalausfall" | Code kennt ein `down`-Vokabular (`admin_ops/health_rest.py:72,434,459-481`); Aggregationspfad statisch nicht entscheidbar | **BLOCKED** → Phase 2 |

### Gegenrichtung: Marker zu niedrig (ebenso relevant)

`REQ-L2-RQ-001/002` (ReqIF) markiert `Not Implemented` — Code
(`application/reqif_import_service.py`, `reqif_export_service.py`) und **9
Testdateien** existieren. Ebenso `REQ-L2-AT-018` (18 Prod-Dateien),
`REQ-L2-CM-001` (`CommentService`, `CommentViewSet`, MCP-`CommentToolGroup`),
`REQ-L2-RF-015` (`BaselineDiff`), `REQ-L2-PL-007` (`settings.py:347`),
`REQ-L2-AS-005`, `REQ-L2-LA-009`. Und `REQ-L1-033` ist `Not Implemented`,
obwohl **alle 6** Kinder (REQ-L2-AT-011…016) `Implemented/Covered` sind.

→ Detail: `AUDIT_EVIDENCE/wp5-04-widersprueche.md`

---

## 4. ADR-Traceability (Aufgabe 4)

| Kriterium (`AGENTS.md`) | erfüllt | verletzt |
|---|---|---|
| ADR hat ≥1 `affected_reqs` | 9/10 | 1 (ADR-004: `[REQ-147]`, fremder ID-Raum) |
| YAML-Frontmatter | 6/10 | **4** (ADR-001, -002, -003, -DS-02 ohne Frontmatter) |
| `status` im lowercase-Enum | 6/10 | **4** (`PROPOSED`/`ACCEPTED`) |
| Lifecycle `proposed → review → accepted` | 0/6 akzeptierte | **5** (ADR-005…009 mit Sprung) |
| Dateiname `ADR-NNN_kurztitel`, 3-stellig, snake_case | 6/10 | **4** (3× CamelCase, `ADR-DS-02` nicht 3-stellig) |
| Ablage `SE/ADR/` | 10/10 | 0 |

### Die drei gravierenden Regelsverstöße

1. **`open_adrs` existiert im gesamten Repository nicht** — `rg -o 'open_adrs' docs` → **0 Treffer**. Vier ADRs sind offen (001, 002, 003, 004) und betreffen **11 REQ-IDs**. Keine einzige dieser 11 REQs führt sie. Die Rückverfolgungsrichtung REQ → offene ADR ist **zu 0 % implementiert**.

2. **14 von 15 `arch_impact: true`-REQ-L1 haben keinen ADR-Bezug** (93 %). Betroffen: REQ-L1-001, -006, **-011 (Audit-Trail)**, **-015 (Mandantenfähigkeit)**, -017, -018, **-025 (ACID)**, -026, -029, -031, -032, **-033 (Auth)**, -056, -057. Nur REQ-L1-100 hat einen (ADR-DS-02). Zusätzlich: **kein einziges akzeptiertes ADR referenziert eine REQ-L1 oder REQ-L2** — die fünf akzeptierten ADRs decken ausschließlich REQ-L0-IDs ab.

3. **`arch_impact` wird bei der L2-Ableitung ohne ADR umgeschrieben.** `L1_clarifications_iter-1.md` setzt `true` für REQ-L1-034 (:40), -037 (:89), -038 (:106); die L2-Dokumente setzen für alle zugehörigen REQ-L2 `false` (`L2_ReqIFServiceSystem_Requirements.md:41,69`; `L2_CommentServiceSystem_Requirements.md:42,70,98`; `L2_VectorSearchServiceSystem_Requirements.md:52,80,108`). In `docs/se/L1/**` gibt es **null** `arch_impact: true` auf L2-Ebene.

**Ursache:** 104 von 121 Requirement-Dokumenten (**86 %**) haben kein
YAML-Frontmatter (`*Requirements*.md`: 121 Dokumente, davon 17 mit Frontmatter).
Sie verwenden stattdessen `> **Level:** … > **Status:** formalisiert`.
`open_adrs` und `arch_impact` haben im verwendeten Format **kein Feld**.

→ Detail: `AUDIT_EVIDENCE/wp5-03-adr-matrix.md`

---

## 5. Test-Abdeckung vs. Traceability (Aufgabe 5)

### 5.1 Sind Tests entlang Traceability organisiert? **Nein.**

| Messung | Wert |
|---|---|
| REQ-IDs mit ≥1 Referenz in einer Testdatei | **358 / 835 = 42.9 %** |
| Backend-Testdefinitionen mit REQ-L*-Bezug | **366 / 10 052 = 3.6 %** |
| Backend-Testdateien mit REQ-Bezug | 256 / 659 = 38.8 % |
| E2E-Spec-Dateien mit REQ-Bezug | 44 / 54 = 81.5 % |
| `REQ-<NNNN>`-IDs (anderer Namensraum) in Tests | **0** — die SE-Kaskade ist der einzige gelebte Namensraum |

Tests sind **modulorientiert** (Dateiname = Modul), nicht anforderungsorientiert.
Der Namespace-Split ist dabei sauber: es gibt keine `REQ-001`-Reste in Tests.

### 5.2 Reale Testdefinitionszahlen vs. Doku (`CR-43`)

| Quelle | Wert |
|---|---|
| `pytest --collect-only` (real) | **10 052** |
| davon von GitHub-CI ausgeführt (4 Pfad-Sets) | **9 541** |
| **in keinem CI-Job** | **511** (`memory` 344, `link_types` 141, `tests/` 26) = **5.1 %** |
| `vitest run` (real) | **2 385** Tests in **250** Testdateien |
| Playwright-Spec-Dateien | **54** |
| `AGENTS.md:16` | „111 Tests" (E2E-Fälle, nicht Dateien) |
| `README.md` / `AGENTS.md` Backend-Testzahl | **keine** — es gibt nichts zu vergleichen |
| `RELEASE beta.17 §6.2` | „10015 passed, 13 skipped, 1 xfailed" — ±37 neben der Collection, plausibel |
| `RELEASE beta.17 §6.3` | „250/250 Testdateien grün" — **korrekt** |

**`CR-30` ist zu korrigieren:** die 463 nicht ausgeführten Tests sind
`attribute_definitions` — die laufen in `set-2-api`. Tatsächlich fehlen 511
(`memory`, `link_types`, `tests/`).

**Zweiter CI-Pfad ohne Tests:** `.woodpecker.yml` (Trigger `push: main`)
enthält **kein `pytest`** — nur `python manage.py check`.

### 5.3 Kritische REQs ohne Testabdeckung — Kernliste für Phase 2

Filter: Security, Tenant-Isolation, Backup/Restore, State-Machine, Datenintegrität.
**84 REQ in der Teilmenge, davon 34 (40.5 %) ohne jede Test-Referenz.**

Die zehn mit dem höchsten Risiko (Marker „Implemented" oder sicherheitskritisch):

| REQ-ID | Thema | Marker | Warum kritisch |
|---|---|---|---|
| `REQ-L2-AT-002` | API Key Authentication | **Impl / Missing** | Einziger Schlüsselpfad für maschinellen Zugriff |
| `REQ-L2-AT-005` | Authentication Context Propagation | **Impl / Missing** | Fehlende Kontextweitergabe = Auth-Bypass-Risiko |
| `REQ-L2-AT-017` | Item-Level-RBAC Regelverwaltung | **Impl / Covered** | Granularste Zugriffskontrolle des Systems |
| `REQ-L2-AL-006` | Tenant-Isolation für Audit-Einträge | **Impl / Covered** | Mandantentrennung im Audit-Log |
| `REQ-L2-RA-007` | Audit-Log-Auslösung bei Schreiboperationen | **Impl / Untested** | Kern der Auditierbarkeit (REQ-L1-011) |
| `REQ-L2-AS-021` | Auth Context Propagation (Application) | **Impl / Missing** | Tenant-/User-Kontext in der Service-Schicht |
| `REQ-L1-025` | Transaktionale Konsistenz (ACID) | **Impl** | Datenintegrität |
| `REQ-L1-015` | Mandantenfähigkeit ohne spätere Datenmigration | **Impl** | Mandantentrennung |
| `REQ-L2-MC-017/018` | MCP Security / RBAC & Rate-Limiting | **Planned / Untested** | Rate-Limit + MCP-RBAC |
| `REQ-L2-PL-012` | Vollständige Tenant-Isolation (RLS) | **Planned / Untested** | RLS ist im Stack aktiv, getestet wird es nicht |

Weitere ohne Test-Bezug: `REQ-L1-096/-097/-098`, `REQ-L1-078`, `REQ-L0-034`
(Backup/DR), `REQ-L2-BL-011` (Backup/Restore), `REQ-L2-RA-020` (API State
Machine Enforcer), `REQ-L2-AS-012` (Workflow Transition Orchestration),
`REQ-L2-AL-008` (Table-Partitionierung), `REQ-L2-RA-025` (No DDL in Handlers).

→ Detail: `AUDIT_EVIDENCE/wp5-02-test-inventar.md`

---

## 6. Test-Qualität (Aufgabe 6)

### 6.1 `skip` / `xfail` — quantifiziert

```
Backend :  9 × @pytest.mark.skip, 3 × skipif, 1 × xfail  =  13 Marker
          → 13 / 10 052 = 0.13 %
          → ALLE 13 mit reason=   (Positivbefund, explizit geprüft)
          → 0 × unittest.skip / self.skipTest
Frontend:  0 × (it|test|describe).skip(If)     0 × it.todo
```

**Das Problem ist nicht die Quote, sondern wo sie sitzt:**

`backend/mcp_server/tests/test_e2e_sse_transport.py:349`
`@pytest.mark.skipif(bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")), reason="SSE live-Redis round trip requires a reachable Redis (skipped in CI)")`
→ Der MCP-SSE-Live-Transport ist in **jedem** CI-Lauf übersprungen.
`:353` skippt zusätzlich still, sobald Redis fehlt. Bei 1 661 MCP-Tests ist
das genau die von `CR-30` beschriebene Lücke.

### 6.2 Belegtes Anti-Pattern: umgebungsgekoppelte Fixtures (65 rote Tests)

```
rg -lP '(?<![\w.])localStorage\.' frontend/src -g '*.test.*'
  → 4 Dateien, 16 Referenzen auf den *baren* Node-Global
frontend/src/hooks/useNotificationFeed.test.ts:57
  beforeEach(() => { localStorage.clear();   // ← nicht window.localStorage
```

Unter Node ≥ 22.4 existiert ein globales `localStorage`, das ohne
`--localstorage-file` nicht initialisiert ist:
`TypeError: Cannot read properties of undefined (reading 'clear')` →
**65 Fehlschläge in 7 Testdateien** bei sonst 2 320 grünen.
Der Test ist an die Node-Version des Laufsystems gekoppelt, nicht an den Vertrag.
Das ist dieselbe Klasse wie `AUD-2026-09-114` (210 grüne Tests neben 2
Live-Bugs) — hier die Umkehrung: rote Tests neben korrektem Code.
Zusätzlich konserviert `backend/rest_api/tests/test_llm_settings.py:248` das
abgeschaltete Anthropic-Modell als Erwartungswert (`AUD-2026-09-052`).

### 6.3 Nicht automatisiert prüfbar

Assertions, die nie fehlschlagen können, AAA-Trennung und Snapshot-Tests ohne
Assertions lassen sich nur durch Ausführung bzw. manuelles Lesen bewerten.
Sicht-Stichprobe n = 12 Testdateien in Evidenz 2 §5.5 — ein **Positivmuster**
heraus: `audit/tests/test_sa39_append_guard_and_schedule.py:73` prüft
explizit, dass die Task im Beat-Schedule steht.
Vollprüfung → `tester` / `test-executor`.

---

## 7. DoD-Konformität — Falsch-Abnahmen (`ABNAHME-FALSCH`)

**Vorbefund: keine einzige REQ-ID in den Abnahmeberichten.**

```
rg -o 'REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}' docs/se/reports/RELEASE_v1.8.0-beta.*.md \
   docs/se/reports/TESTPLAN_v1.8.0-beta.*.md --no-filename | Sort-Object -Unique
  → (leer)
```

7 RELEASE-Berichte + 4 TESTPLAN-Berichte = **0 REQ-Referenzen**. Kein
Abnahmekriterium ist auf eine Anforderung rückführbar. Zusätzlich enthalten
die Berichte **keine Checkboxen** (`- [ ]` / `- [x]`): die Abnahme ist
Fließtext, nicht prüfbar.

### Vier belegte Falsch-Abnahmen

| ID | Checklistenpunkt (Fundstelle) | Widerlegt durch |
|---|---|---|
| `ABNAHME-FALSCH-1` | `RELEASE_v1.8.0-beta.17.md:12-13` — *„der Schnitt ist **grün**: die Regression-Suite ist **vollständig grün**"* | **511 von 10 052** Testdefinitionen laufen in keinem CI-Job (Evidenz 2 §1.2). Zusätzlich nennt derselbe Bericht in **§6.2** „sowie 4 Errors". Der Bericht widerspricht sich selbst. |
| `ABNAHME-FALSCH-2` | `RELEASE_v1.8.0-beta.17.md:17` — *„Was erfixt ist: W1–W4 sind implementiert, dokumentiert und **getestet**."* | W4 = Benachrichtigungs-Feed (`ADR-009`). `useNotificationFeed.test.ts` hat **8 der 65** roten Tests; die Fixture bildet den echten Contract nicht (Bare-Global, §6.2). „getestet" trifft zu, „abgenommen" nicht. |
| `ABNAHME-FALSCH-3` | `RELEASE_v1.8.0-beta.17.md:159` — Gate `backend-test set-1..set-4 \| pass` als Release-Bedingung | Dieselben 4 Sets decken **9 541** von 10 052 Definitionen ab. `memory` (344), `link_types` (141) und `tests/` (26) sind **außerhalb jeder Abnahme**. Der Trace-Link-Typ-Katalog (`backend/link_types`) ist damit unabgenommen. |
| `ABNAHME-FALSCH-4` | Implizit: jeder Release-Schnitt gilt als erfüllte **SE-Kaskade**, da die Matrix als SOLL gilt | Die Matrix listet **324 Quell-REQ-IDs nicht** und 354 L3-REQ gar nicht. Ein Schnitt, der gegen die Matrix abgenommen wird, prüft 59 % der Anforderungen nicht. |

**Fairness-Note:** `RELEASE_v1.8.0-beta.16.md` ist ausdrücklich `draft`, nennt
rote Suites (`9687 passed, … 4 errors`, `2201 passed, 3 failed`) und ist damit
**ehrlich**. Der Befund trifft `beta.17` und die Gate-Logik dahinter, nicht die
Berichterstattung von `beta.16`.

---

## 8. Empfehlungen (nur Ideen, keine Fixes)

### P0 — sofort, weil Abnahme und Security betroffen

1. **Die 10 sicherheitskritischen REQs ohne Testabdeckung bekommen Tests**
   (`REQ-L2-AT-002`, `-AT-005`, `-AT-017`, `-AL-006`, `-RA-007`, `-AS-021`,
   `REQ-L1-015`, `REQ-L1-025`, `REQ-L2-MC-017/-018`, `REQ-L2-PL-012`).
   Reihenfolge nach Risiko: Tenant-Isolation vor Auth-Propagation vor RBAC.
2. **511 nicht ausgeführte Testdefinitionen in CI aufnehmen** oder als bewusst
   ausgeklammert dokumentieren. Der Trace-Link-Typ-Katalog (`link_types`, 141
   Tests) gehört in den Traceability-Pfad.
3. **`REQ-L2-MC-014` zurücksetzen**: entweder `semantic_search` implementieren
   oder den Marker auf `Not Implemented` setzen und `REQ-L2-VS-001` als
   Blocker verlinken. Der derzeitige `Review Findings`-Satz ist eine
   Falschaussage im Anforderungsdokument.
4. **`REQ-L1-046` / `REQ-L2-BL-011` trennen**: Backup (evtl. real) und Restore
   (definitiv nicht) sind zwei Zusagen. Der Restore-Pfad braucht entweder ein
   im Image vorhandenes Skript oder eine ehrliche Nicht-Implementiert-Kennzeichnung.
5. **`REQ-L1-013`**: das tote Default-Modell muss entweder durch ein lebendes
   ersetzt oder als Pflicht-Config erzwungen werden — und der Test, der es als
   Erwartungswert fixiert, muss mitziehen.

### P1 — Traceability-Kette instand setzen

6. **Matrix-SSOL wiederherstellen**: `scripts/generate_traceability_matrix.py`
   muss `L2_ApplicationServiceSystem_Requirements.json` mitlesen (beseitigt die
   15 Phantom-Verweise) und **REQ-L3-Zeilen publizieren** (derzeit 0 von 354).
7. **Ein einziges ID-Schema**: `REQ-L2-AppSvc-*` aus Code und Doku entfernen
   oder in die Matrix aufnehmen. Derzeit existieren drei ID-Räume.
8. **`open_adrs` einführen** — aber nur, wenn zuerst das Frontmatter existiert.
   Reihenfolge: (a) YAML-Frontmatter für die 104 fehlenden Requirement-Dokumente,
   (b) `open_adrs` in `AGENTS.md` als optional herabstufen, wenn (a) zu teuer ist.
9. **Die 5 akzeptierten ADRs auf L1/L2 nachziehen** oder die Regel
   `arch_impact: true ⇒ ADR` für L0/L1 explizit aufheben. Der jetzige Zustand
   bestraft die 14 regelkonformen REQs und belohnt Verstöße.
10. **Marker neu erheben, nicht neu erfinden.** 24.1 % der Stichprobe sind
    invertiert; jede manuelle Korrektur ohne Collector-Lauf vergrößert die
    Drift.

### P2 — Tests an der Traceability ausrichten

11. **REQ-Referenz als Pflicht im Test-Header** (Docstring oder
    `pytest.mark.req("REQ-L2-…")`) für neue Tests. Heute tragen 3.6 % der
    Backend-Tests einen REQ-Bezug — mit Markern wäre die Abdeckungszahl
    überhaupt erst berechenbar.
12. **`test_status` in den REQ-Dokumenten aus dem Collector speisen** statt
    manuell zu pflegen. Solange `Covered` ein Handeintrag ist, ist es kein
    Nachweis (belegt an `REQ-L2-MC-014`).
13. **`skipif(not _REDIS_REACHABLE)` durch einen laufenden Redis-Dienst in CI
    ersetzen**, damit der MCP-SSE-Live-Pfad überhaupt geprüft wird.

### P3 — nachgelagert

14. **Release-Abnahme auf REQ-Bezug umstellen**: jede Abnahmezeile mit
    `REQ-ID | Test-Datei | Test-Output`. Ohne REQ-Bezug ist keine
    Abnahmeprüfung möglich — das ist die Ursache aller vier Falsch-Abnahmen.
15. **Bare-Global-`localStorage` in Tests ersetzen** (`window.localStorage`) —
    entkoppelt 65 Tests von der Node-Version.
16. **`.woodpecker.yml` entweder aufräumen oder die Testläufe dorthin
    spiegeln.** Zwei CI-Systeme, eines ohne Tests, ist eine stille
    Fehlerquelle.

---

## 9. Finding-Tabelle

| ID | Schwere | Klassifikation | REQ-ID | CR-Track/Issue | Ort | Kurztitel |
|---|---|---|---|---|---|---|
| AUD-2026-09-330 | High | TRACE-DRIFT | 324 REQ-IDs | CR-09, CR-47 | `docs/se/traceability-matrix.md` | 324 Quell-REQ-IDs fehlen in der SOLL-Matrix (24× L2, 300× L3) |
| AUD-2026-09-331 | High | TRACE-BLIND | 354 REQ-L3 | CR-09 | `traceability-matrix.md:649-655` | Matrix publiziert 0 von 354 REQ-L3-Zeilen; behauptete 369 vs. gemessene 354 |
| AUD-2026-09-332 | Medium | TRACE-INVARIANTE | `REQ-L2-AppSvc-*` | — | `traceability-matrix.md:721` | 15 als „nicht existent" gelistete IDs, die im Code referenziert werden |
| AUD-2026-09-333 | High | ADR-REGEL | 11 REQ-IDs | — | `docs/se/**` | `open_adrs` existiert repo-weit nicht (0/835 REQs) |
| AUD-2026-09-334 | High | ADR-KASKADE | 14 REQ-L1 | — | `L1_Gesamtsystem_Requirements.md:37…2522` | 14 von 15 `arch_impact:true` ohne ADR; kein akzeptiertes ADR deckt L1/L2 |
| AUD-2026-09-335 | Medium | ADR-SCHEMA | — | — | `ADR-001,-002,-003,-DS-02` | 4 von 10 ADRs ohne YAML-Frontmatter |
| AUD-2026-09-336 | Medium | ADR-NAMING | — | — | `docs/se/ADR/` | 4 Dateinamen nicht konform (3× CamelCase, `ADR-DS-02` nicht 3-stellig) |
| AUD-2026-09-337 | Medium | ADR-SCHEMA | — | — | ADR-001/-002/-003/-DS-02 | Statuswerte `PROPOSED`/`ACCEPTED` verlassen das lowercase-Enum |
| AUD-2026-09-338 | Medium | ADR-LIFECYCLE | — | — | ADR-005…009 | Lifecycle-Sprung `proposed → accepted` ohne `review` (5×) |
| AUD-2026-09-339 | High | ADR-KASKADE | REQ-L1-034/-037/-038 | — | `L2_{ReqIF,Comment,VectorSearch}…_Requirements.md` | `arch_impact` bei L2-Ableitung von `true` auf `false` umgeschrieben, ohne ADR |
| AUD-2026-09-340 | High | SOLL-INTERN | 17 REQ-L1 | — | `traceability-matrix.md` §2/§3 | 17 `Implemented`-REQ-L1 mit nicht-implementiertem Kind (3 vollständig) |
| AUD-2026-09-341 | Medium | SOLL-INTERN | REQ-L1-042/-100/-101 | — | `traceability-matrix.md:140,191,192` | 3 `Implemented`-REQ-L1 ohne jede L2-Zerlegung |
| AUD-2026-09-342 | High | SOLL-STALE | `REQ-L2-MC-014` | — | `L2_McpServerSystem_Requirements.md:97-107` | MCP-Tool `semantic_search` als `Implemented/Covered` dokumentiert, existiert nicht |
| AUD-2026-09-343 | High | SOLL-STALE | `REQ-L2-RQ-001/-002`, `REQ-L2-AT-018`, `REQ-L2-CM-001`, `REQ-L2-RF-015` | — | Matrix `:311,512,513,483` | 7/29 Stichproben-REQs als nicht umgesetzt markiert, obwohl Code + Tests existieren |
| AUD-2026-09-344 | High | SOLL-STALE | `REQ-L1-022/-033/-036` | — | Matrix `:120,131,134` | 3 REQ-L1 `Not Implemented` mit vollständig implementierten Kindern |
| AUD-2026-09-345 | Critical | **REQ-CODE-WIDERSPRUCH** | `REQ-L1-046` | AUD-2026-09-123 | `matrix:331`, `backend/Dockerfile:154` | Backup/Restore als `Implemented/Covered`, Restore-Skript nie im Image |
| AUD-2026-09-346 | Critical | **REQ-CODE-WIDERSPRUCH** | `REQ-L1-013` | AUD-2026-09-052 | `backend/llm_adapter/providers.py:1080` | Default-Modell `claude-3-opus-20240229` abgeschaltet; jeder Anthropic-Call scheitert |
| AUD-2026-09-347 | High | **REQ-CODE-WIDERSPRUCH** | `REQ-L2-LA-007` | AUD-2026-09-058 | `frontend/src/api/llm-settings.ts:22` | Azure implementiert und beworben, aber nicht wählbar |
| AUD-2026-09-348 | High | **REQ-CODE-WIDERSPRUCH** | `REQ-L1-016`, `REQ-L2-RF-001` | AUD-2026-09-002/-016 | `traceability-matrix.md:114` | i18n `Implemented/Covered`; 112 Keys fehlen in beiden Locales, Lint-Regel wirkungslos |
| AUD-2026-09-349 | High | **REQ-CODE-WIDERSPRUCH** | `REQ-L1-021`, `REQ-L2-AS-014` | AUD-2026-09-070 | `backend/application/import_service.py:149,226-233` | CSV-Import meldet Datenverlust als `success: true` |
| AUD-2026-09-350 | High | **REQ-CODE-WIDERSPRUCH** | `REQ-L2-RO-001/-AS-029/-LA-008` | AUD-2026-09-120 | `backend/resilience/dispatcher.py` | Asynchronie `Covered`, jede Celery-Task läuft 4× |
| AUD-2026-09-191 | High | **REQ-CODE-WIDERSPRUCH** | `REQ-L2-MC-019` | AUD-2026-09-030…043 | `protocol_handler.py:345` vs. `views.py:425` | stdio-Handler existiert, stdio-Transport nicht exponiert; Doku nennt 3 Transporte |
| AUD-2026-09-192 | High | TEST-TRACE | 477 REQ-IDs | CR-30 | `backend`, `frontend/src`, `e2e` | Nur 42.9 % der REQ-IDs haben einen Test-Bezug (3.6 % der Tests) |
| AUD-2026-09-193 | High | TEST-CI | — | CR-30 | `.github/workflows/ci.yml:44-55` | 511 von 10 052 Testdefinitionen laufen in keinem CI-Job (`memory`, `link_types`, `tests`) |
| AUD-2026-09-194 | Medium | TEST-CI | — | — | `.woodpecker.yml` | Zweites CI-System führt überhaupt kein `pytest` aus (nur `manage.py check`) |
| AUD-2026-09-195 | High | **ABNAHME-FALSCH** | — | CR-43 | `RELEASE_v1.8.0-beta.17.md:12` | „Regression-Suite ist vollständig grün" bei 511 nie ausgeführten Tests + 4 eigenen Errors |
| AUD-2026-09-196 | High | **ABNAHME-FALSCH** | — | — | `RELEASE_v1.8.0-beta.17.md:17` | „W1–W4 implementiert, dokumentiert und getestet" — W4-Tests sind rot (65 FE-Fehler) |
| AUD-2026-09-197 | Medium | **ABNAHME-FALSCH** | — | — | `docs/se/reports/RELEASE_*.md`, `TESTPLAN_*.md` | 0 REQ-IDs in 11 Abnahmeberichten; keine Checkbox-Struktur |
| AUD-2026-09-198 | Medium | TEST-QUALITÄT | `REQ-L2-MC-019` | CR-30 | `mcp_server/tests/test_e2e_sse_transport.py:349,353` | SSE-Live-Redis-Pfad in **jedem** CI-Lauf per `skipif` übersprungen |
| AUD-2026-09-199 | Medium | TEST-QUALITÄT | — | AUD-2026-09-114 | `useNotificationFeed.test.ts:57` u. a. | Bare-Global-`localStorage` in 4 FE-Testdateien → 65 umgebungsgekoppelte Fehlschläge |
| AUD-2026-09-200 | Medium | TEST-QUALITÄT | `REQ-L1-013` | AUD-2026-09-052 | `backend/rest_api/tests/test_llm_settings.py:248` | Test fixiert das abgeschaltete Anthropic-Modell als Erwartungswert |
| AUD-2026-09-201 | High | SOLL-TRACE | `REQ-L0-031` | — | `SN_Stakeholder_Needs.md` | Nummerierungslücke: 031 existiert nirgends; Matrix springt 030 → 032 |
| AUD-2026-09-202 | Medium | SE-TAXONOMIE | — | CR-09 | `docs/se/**/*Requirements*.md` | 104 von 121 Requirement-Dokumenten ohne YAML-Frontmatter (Pflichtverstoß) |
| AUD-2026-09-203 | Medium | SOLL-TRACE | 20 REQ-IDs | — | Matrix `:724,728` | 20 doppelt vergebene REQ-IDs; Marker „letzter gewinnt" = positionsabhängig |
| AUD-2026-09-204 | Medium | RECONCILE | `REQ-L2-AL-009` | AUD-2026-09-121 | `settings.py:822`, DB-Row live | Parallelbefund „Archivierung nie registriert" **nicht reproduzierbar** — **Korrektur 2026-09-30: diese Aussage ist zurückgenommen.** Die DB-Row belegt die Beat-Schedule, nicht die Worker-Registrierung. Die Richtung ist die umgekehrte: `-121`/`-270` gelten, der Parallelbefund aus der Matrix ist der unzutreffende. Klassifikation `NEU` (Reconciliation zur Matrix-Aussage), kein eigener Defekt. |
| AUD-2026-09-205 | Low | BLOCKED | `REQ-L1-026` | AUD-2026-09-129 | `admin_ops/health_rest.py:72,434,459` | Health-Aggregation statisch nicht entscheidbar → Messung an laufendem Stack nötig |
| AUD-2026-09-206 | Medium | DOKU-WIDERSPRUCH | — | AUD-2026-09-084 | `AGENTS.md` | APIView-/Tool-Zahlen im AGENTS.md weichen vom gemessenen Stand ab (durch WP-1 belegt) |

---

## 10. Was WP-5 **nicht** prüfen konnte

| Punkt | Grund | Status |
|---|---|---|
| Ob die 3.6 % REQ-referenzierten Tests den REQ **inhaltlich** prüfen oder nur ihn nennen | Statische Analyse; Testausführung nötig | **BLOCKED** → `tester` |
| `AGENTS.md:16` „111 E2E-Tests" | Kein Playwright-Lauf (Stack-Inviolat, Zeitbudget) | **BLOCKED** |
| Health-Aggregation bei Totalausfall (`AUD-2026-09-129`) | Erfordert Fehler-Injektion in den laufenden Stack | **BLOCKED** (AUD-2026-09-205) |
| Assertions, die nie fehlschlagen können; AAA-Trennung; Snapshot-Tests ohne Assertions | Erfordert Suite-Ausführung + manuelles Lesen aller Suites | **BLOCKED** → `tester`/`test-executor` |
| L0- und L3-Code-Belegung | 300 von 354 L3-IDs fehlen in der Matrix; L0 ist reines Stakeholder-Narrativ | bewusst nicht hochgerechnet |
| Ist `REQ-L2-MC-014` unter einem **anderen** Tool-Namen doch implementiert? | 29 Tool-Module geprüft, Namenskonvention `<gruppe>.<verb>`, kein Treffer — aber Registry-Ausgabe zur Laufzeit nicht abgerufen | Restunsicherheit, gering |
| Warum 112 i18n-Keys fehlen (Ursache) | Delegiert an `AUD-2026-09-002/-016` | übernommen, nicht neu ermittelt |
| Ob `.worktrees/`-Stände abweichende REQ-Stände haben | Außerhalb des Branches; nur `main`-Stand bewertet | bewusst ausgeschlossen |

---

## 11. Artefakte

| Datei | Inhalt |
|---|---|
| `docs/audit/2026-09/AUDIT_TRACEABILITY.md` | dieser Bericht |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp5-01-req-inventar.md` | REQ-Inventar, Drift beide Richtungen, Matrix-Selbstwidersprüche |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp5-02-test-inventar.md` | Test-Inventar-Zahlen, REQ-Test-Quote, Skip/Xfail-Statistik, Reconciliation |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp5-03-adr-matrix.md` | ADR-Prüfmatrix, `open_adrs`, `arch_impact`, Frontmatter |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp5-04-widersprueche.md` | Widerspruchsliste A–E mit REQ-Zitat und `datei.py:zeile` |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp5-05-belegungsmatrix.md` | Methodik + Belegungsgrad-Matrix (n = 29, 20/20 Subsysteme) |
