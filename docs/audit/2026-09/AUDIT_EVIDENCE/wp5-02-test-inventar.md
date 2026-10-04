---
type: REVIEW
scope: wp5-evidence-test-inventar
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 Evidenz 2 — Test-Inventar, REQ-Referenz-Abdeckung, Skip/Xfail

> Alle Zahlen aus read-only Läufen gegen `chore/system-audit-2026-09` @ `75beb750`.
> Backend: `python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider -p no:homeassistant`
> (Workdir `backend/`). `-p no:homeassistant` blockiert das Fremd-Plugin
> `pytest_homeassistant_custom_component`, das unter Windows an `import fcntl`
> scheitert — ohne diesen Block bricht die Collection mit 90 Errors ab.

## 1. Backend (pytest) — real gemessene Testdefinitionen

```
10052 tests collected in 14.56s
```

### 1.1 Verteilung nach Top-Level-Paket

| Paket | Testdefinitionen | in GitHub-CI? |
|---|---|---|
| `application` | 2383 | ✔ set-1-core |
| `rest_api` | 2202 | ✔ set-2-api |
| `mcp_server` | 1661 | ✔ set-3-mcp |
| `attribute_definitions` | 463 | ✔ set-2-api |
| `auth_tenancy` | 429 | ✔ set-2-api |
| `diagram` | 368 | ✔ set-4-features |
| `persistence` | 352 | ✔ set-1-core |
| **`memory`** | **344** | ✘ **NICHT** |
| `llm_adapter` | 319 | ✔ set-4-features |
| `workflow` | 295 | ✔ set-4-features |
| `traceability` | 280 | ✔ set-4-features |
| `admin_ops` | 202 | ✔ set-4-features |
| **`link_types`** | **141** | ✘ **NICHT** |
| `baseline` | 127 | ✔ set-4-features |
| `presets` | 109 | ✔ set-2-api |
| `se_metrics` | 92 | ✔ set-4-features |
| `icd` | 78 | ✔ set-4-features |
| `audit` | 65 | ✔ set-4-features |
| `resilience` | 42 | ✔ set-4-features |
| `reqogniloom` | 35 | ✔ set-2-api |
| **`tests`** (Wurzel) | **26** | ✘ **NICHT** |
| `context_graph` | 26 | ✔ set-4-features |
| `test_runs` | 13 | ✔ set-2-api |
| **Summe** | **10052** | |

### 1.2 Was die CI tatsächlich ausführt

`.github/workflows/ci.yml:44-55` definiert 4 Pfad-Sets. Nachrechnen mit denselben
Pfaden:

```
pytest <die 20 CI-Pfade>      →  9541 tests collected
pytest memory/tests link_types/tests tests  →  511 tests collected
9541 + 511 = 10052   ✔
```

**511 Testdefinitionen (5.1 %) laufen in keinem CI-Job.**
Das sind `memory` (344), `link_types` (141), `tests/` (26) — genau die Pakete für
Memory/Context-Projektion, den Trace-Link-Typ-Katalog und die Root-Wiring-Tests.

### 1.3 Zweiter CI-Pfad ohne Tests

`.woodpecker.yml` (Branch-Trigger `push: main`) enthält **kein** `pytest`.
Der einzige Testschritt ist:

```yaml
test-backend:
  commands:
    - cd backend && pip install -q -r requirements.txt
    - python manage.py check
```

→ Zwei CI-Systeme; eines führt null Tests aus. Reconciliation zu `CR-30`
(„CI führt 463 Testdefinitionen nicht aus"): die 463 sind die
`attribute_definitions`-Tests — die **sind** in CI (set-2-api). Die tatsächlich
fehlenden 511 sind `memory` + `link_types` + `tests`. `CR-30` ist damit in der
Zahl zu korrigieren, in der Richtung (fehlende Suite) aber zu bestätigen.

## 2. Frontend (vitest)

```
npx vitest run --reporter=json
numTotalTestSuites = 727   (describe-Blöcke)
numTotalTests       = 2385
numPassedTests      = 2320
numFailedTests      = 65
Testdateien (*.test.ts|tsx) = 250
```

`250/250 Testdateien grün` (RELEASE beta.17 §6.3) ist damit **strukturell
korrekt** — 250 ist die Dateizahl, nicht die Blockzahl. Die 65 Fehlschläge sind
ein Node-Umgebungsproblem, siehe §5.

## 3. E2E (Playwright)

```
rg --files e2e -g '*.spec.ts'   →  54 Spec-Dateien
```
`AGENTS.md:16` nennt „111 Tests" (Test-Fälle, nicht Dateien) — nicht
unmittelbar prüfbar ohne Playwright-Lauf (→ BLOCKED, siehe Bericht §9).

## 4. REQ-IDs in Tests — die Kernzahl

```
$rx='REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}'
rg -o $rx backend frontend/src e2e -g 'test_*.py' -g '*_test.py' -g '*.test.*' -g '*.spec.ts' --no-filename | Sort-Object -Unique
  → 366 eindeutige REQ-L-IDs, die in mindestens einer Testdatei genannt werden

Schnittmenge mit den 835 Quell-REQ-IDs:
  → 358 / 835 = 42.9 % haben mindestens EINE Test-Referenz
  → 477 / 835 = 57.1 % haben KEINE
```

### 4.1 Nach Ebene

| Ebene | mit Test-Referenz | ohne | Quote |
|---|---|---|---|
| L0 | 17 | 41 | **29.3 %** |
| L1 | 35 | 59 | **37.2 %** |
| L2 | 171 | 158 | **52.0 %** |
| L3 | 135 | 219 | **38.1 %** |
| **Gesamt** | **358** | **477** | **42.9 %** |

### 4.2 Nach Backend-Subsystem (Top-Lücken)

| Namespace | REQs ohne Test-Referenz |
|---|---|
| `REQ-L2-AppSvc-*` | 25 (von 25 — **100 %**) |
| `REQ-L2-AS-*` | 21 |
| `REQ-L2-RF-*` | 20 |
| `REQ-L2-RA-*` | 18 |
| `REQ-L2-AT-*` | 16 |
| `REQ-L2-MC-*` | 10 |
| `REQ-L2-PL-*` | 10 |

Bemerkenswert: `REQ-L2-AT-*` (Auth/Tenancy) hat 16 Lücken bei existierendem Code
(`backend/auth_tenancy`, 89 py, 38 Testdateien, 429 Tests) → die Tests dort sind
modulorientiert, nicht anforderungsorientiert.

### 4.3 Kritische REQs ohne jede Testabdeckung

Filter: Titel-Matcher auf `tenant|isolation|RLS|RBAC|Berechtigung|Auth|Passwort|
Token|Secret|Backup|Restore|Disaster|State.Machine|Transition|Workflow|Audit|ACID|
Transaktion|Integrit|Circuit|Resilienz|Verschlüssel|Rate.Limit`.

```
Kritische Teilmenge:            84 REQs
davon ohne Test-Referenz:       34  (40.5 %)
```

| REQ-ID | Ebene | Marker (Matrix §2/§3) | Thema |
|---|---|---|---|
| `REQ-L1-096` | L1 | Planned | API Security & Secret Management |
| `REQ-L1-097` | L1 | Planned | Transactional Integrity & Concurrency |
| `REQ-L1-098` | L1 | Planned | Data Integrity & Tenant Isolation |
| `REQ-L1-011` | L1 | Implemented | Vollständiger Audit-Trail |
| `REQ-L1-015` | L1 | Implemented | Mandantenfähigkeit ohne spätere Datenmigration |
| `REQ-L1-025` | L1 | Implemented | Transaktionale Konsistenz (ACID) |
| `REQ-L1-005` | L1 | Implemented | MCP Read/Write-Zugriff auf alle Artefakttypen |
| `REQ-L1-007` | L1 | Implemented | Configurable-Rigor-Presets |
| `REQ-L1-026` | L1 | Implemented | Übergreifende Performance-Anforderung |
| `REQ-L1-078` | L1 | Backlog | Industriestandard Workflow-Status |
| `REQ-L0-034` | L0 | Not Implemented | Instanz-Backup, Disaster Recovery & Baseline-Vergleich |
| `REQ-L0-015` | L0 | Implemented | Audit-dokumentierbare Berichte und Traceability-Matrizen |
| `REQ-L0-048` / `-050` | L0 | — | Workflow-Status / PAT via UI |
| `REQ-L2-AT-002` | L2 | **Implemented / Missing** | API Key Authentication |
| `REQ-L2-AT-005` | L2 | **Implemented / Missing** | Authentication Context Propagation |
| `REQ-L2-AT-012` | L2 | **Implemented / Covered** | Token Issuance / BearerToken-Kompatibilität |
| `REQ-L2-AT-017` | L2 | **Implemented / Covered** | Item-Level-RBAC Regelverwaltung |
| `REQ-L2-AT-019` | L2 | Not Implemented / Missing | Item-Level-Berechtigungs-UI |
| `REQ-L2-AL-006` | L2 | **Implemented / Covered** | Tenant-Isolation für Audit-Einträge |
| `REQ-L2-AL-008` | L2 | **Implemented / Untested** | Table-Partitionierung der Audit-Tabelle |
| `REQ-L2-AS-012` | L2 | Not Implemented / Missing | Workflow Transition Orchestration |
| `REQ-L2-AS-021` | L2 | **Implemented / Missing** | Auth Context Propagation |
| `REQ-L2-AS-041` | L2 | Planned / Untested | Service-Level Autorisierung (RBAC & Tenant) |
| `REQ-L2-AS-043` | L2 | Planned / Untested | Resilienz bei Drittsystemen (LLM & Webhooks) |
| `REQ-L2-BL-011` | L2 | Not Implemented / Missing | Instanz-Backup, Full Restore & Baseline-Soft-Restore |
| `REQ-L2-MC-017` | L2 | Planned / Untested | MCP Security & Secret Management |
| `REQ-L2-MC-018` | L2 | Planned / Untested | MCP RBAC & Rate-Limiting |
| `REQ-L2-MC-021` | L2 | Planned / Untested | MCP Audit Logging für Needs |
| `REQ-L2-PL-012` | L2 | Planned / Untested | Vollständige Tenant-Isolation |
| `REQ-L2-RA-007` | L2 | **Implemented / Untested** | Audit-Log-Auslösung bei Schreiboperationen |
| `REQ-L2-RA-020` | L2 | Not Implemented / Missing | API State Machine & Guardrails Enforcer |
| `REQ-L2-RA-025` | L2 | Planned / Untested | REST API Data Integrity (No DDL in Handlers) |

**Das ist die Kernliste für Phase 2.** Vier der ungetesteten kritischen REQs
sind als `Implemented` markiert (`REQ-L2-AT-002`, `-AT-005`, `-AS-021`, `-RA-007`).

## 5. Test-Qualität — quantifizierte Anti-Patterns

### 5.1 `skip` / `xfail` (Backend)

```
rg -o '@pytest\.mark\.(skip|skipif|xfail)' backend --no-filename | Group-Object
  @pytest.mark.skip    9
  @pytest.mark.xfail   1
  @pytest.mark.skipif  3
rg 'unittest\.skip(If|Unless)?\(|self\.skipTest\('  → 0
```

Quote: **13 Marker / 10 052 Tests = 0.13 %**. Alle 13 tragen einen
`reason=` — **keine unkommentierten Skips** (Positivbefund, explizit geprüft).

Verteilung:

| Datei:Zeile | Marker | reason |
|---|---|---|
| `backend/workflow/tests/test_testcase_status_lowercase_453.py:348,379,404,426,440` | skip ×5 | Task 12 droppt `pl_testcase.status`, 0014 `_apply()` scheitert auf voll migrierter Test-DB |
| `backend/auth_tenancy/tests/test_api_key_cap_toctou_sa39.py:50` | skipif | `row locking is PostgreSQL-specific` |
| `backend/mcp_server/tests/test_e2e_sse_transport.py:349` | skipif | `skipped in CI` (explizit `os.environ.get("CI")`) |
| `backend/mcp_server/tests/test_e2e_sse_transport.py:353` | skipif | `_REDIS_REACHABLE` — fällt stillschweigend aus, wenn Redis fehlt |
| `backend/auth_tenancy/tests/test_inventory_api_keys_command.py:779` | xfail, `strict=True` | `workspace_ids NOT NULL` — Fall nicht erreichbar |

**Befund:** `test_e2e_sse_transport.py:349` skippt den Live-Redis-Roundtrip in
**jedem** CI-Lauf und `:353` zusätzlich still, sobald Redis fehlt. Der MCP-SSE-
Transport ist damit in CI **nie** end-to-end geprüft — bei 1661 MCP-Tests ein
spürbares Loch, und genau die Klasse, die `CR-30` („Live-MCP/Redis-Pfade
übersprungen") beschreibt.

### 5.2 Frontend

```
rg -o '(it|test|describe)\.skip(If)?\(' frontend/src   → 0
rg -o '\b(it|test)\.todo\(' frontend/src                → 0
```

### 5.3 Umgebungsgekoppelte Tests (belegte Ursache der 65 FE-Fehler)

```
rg -lP '(?<![\w.])localStorage\.' frontend/src -g '*.test.*'
  frontend/src/hooks/useReadableIdsVisible.test.ts
  frontend/src/hooks/useNotificationFeed.test.ts
  frontend/src/components/InterviewWidget/NotificationFeed.test.tsx
  frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
→ 16 Referenzen auf den *baren* Node-Global `localStorage`
```

Beispiel `frontend/src/hooks/useNotificationFeed.test.ts:57`:

```ts
beforeEach(() => {
  localStorage.clear();   // ← Node-Global, nicht window.localStorage
```

Unter Node ≥ 22.4 existiert ein globales `localStorage`, das ohne
`--localstorage-file` nicht initialisiert ist; der Vitest-Lauf bricht mit
`TypeError: Cannot read properties of undefined (reading 'clear')` ab
(`ExperimentalWarning: localStorage is not available because --localstorage-file
was not provided`). 65 Tests in 7 Dateien. Auf dem CI-Node-Setup tritt das nicht
auf → der Test ist an die Node-Version des Laufsystems gekoppelt, nicht an den
Vertrag. Das ist dieselbe Klasse wie `AUD-2026-09-114` (grüne Tests neben
Live-Bugs) — hier die Umkehrung: rote Tests neben korrektem Code.

### 5.4 Nicht prüfbare Testqualitäts-Kriterien

Ohne Ausführung einer Testsuite lassen sich Assertions, die nie fehlschlagen
können, und AAA-Trennung nicht automatisiert bewerten. Manuelle Sichtprüfung der
Stichprobe in §5.5, Vollprüfung → `tester`/`test-executor`.

### 5.5 Sicht-Stichprobe (n = 12 Testdateien)

| Datei | Auffälligkeit |
|---|---|
| `backend/application/tests/test_import_service.py` | Docstring `req_id: REQ-L1-021, REQ-L2-AppSvc-014, …` — veraltet ID-Schema |
| `backend/audit/tests/test_sa39_append_guard_and_schedule.py` | **Positivmuster**: assertiert explizit, dass die Task im Beat-Schedule steht |
| `backend/rest_api/tests/test_llm_settings.py:248` | Test-Fixture fixiert `claude-3-opus-20240229` — kodiert das abgeschaltete Modell als Erwartungswert |
| `frontend/src/components/shared/ArtifactInspector/DiffPanel.test.tsx` | REQ-Referenz vorhanden |
| `frontend/src/hooks/useNotificationFeed.test.ts` | Bare-Global-Problem (§5.3) |
| `e2e/tests/traceability.spec.ts` | REQ-Referenz vorhanden |
| `e2e/helpers/auth.ts` | `getWorkspaceId` nimmt `items[0]` — reihenfolgeabhängig (dokumentiert in RELEASE beta.17 §8.4) |

## 6. Reconciliation mit dem Vor-Audit

| Vor-Befund | Messung WP-5 | Ergebnis |
|---|---|---|
| `CR-33` Coverage-Baseline | keine versionierte Collection-Baseline im Repo gefunden; §1.2 zeigt 511 nicht ausgeführte Definitionen | **bestätigt + präzisiert** |
| `CR-34` Typecheck | `npx tsc --noEmit` Teil von CI (ci.yml:305, nur hermes-plugin) | **teilweise**: Frontend-`tsc` läuft nur im Plugin-Job, nicht für `frontend/` |
| `CR-43` historische Testzahlen | real: 10052 Backend / 2385 Frontend / 54 E2E-Spec-Dateien. `AGENTS.md:16` nennt 111 E2E-Tests; `README.md`/`AGENTS.md` nennen **keine** Backend-Testzahl | **bestätigt**: die Doku nennt keine Zahl, die man mit der Realität vergleichen könnte |
| `CR-30` CI führt 463 nicht aus | real: **511** (`memory` 344, `link_types` 141, `tests` 26). `attribute_definitions` (463) läuft in set-2-api | **korrigiert** |
| `CR-31` E2E-Laufzeit/Skip | 4 Playwright-Shards, 9m45–12m; kein `test.skip` in `frontend/src` | **nicht betroffen** |
| `CR-09`/`CR-47` SE-SSOT | siehe Bericht §4/§5 | **bestätigt** |

## 7. Roh-Kommandos

```powershell
# Backend
python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider -p no:homeassistant
python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider -p no:homeassistant `
  application/tests persistence/tests attribute_definitions/tests rest_api/tests `
  auth_tenancy/tests presets/tests reqogniloom/tests test_runs/tests mcp_server/tests `
  llm_adapter/tests diagram/tests traceability/tests workflow/tests context_graph/tests `
  se_metrics/tests baseline/tests admin_ops/tests icd/tests resilience/tests audit/tests   # 9541
python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider -p no:homeassistant `
  memory/tests link_types/tests tests                                                                  # 511

# Frontend
cd frontend; npx vitest run --reporter=json --outputFile=<tmp>/wp5_vitest.json
rg --files frontend/src -g '*.test.ts' -g '*.test.tsx'    # 250

# REQ-Referenzen
rg -o 'REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}' backend frontend/src e2e `
  -g 'test_*.py' -g '*_test.py' -g '*.test.*' -g '*.spec.ts' --no-filename | Sort-Object -Unique

# Skip/Xfail
rg -o '@pytest\.mark\.(skip|skipif|xfail)' backend --no-filename
rg -o '(it|test|describe)\.skip(If)?\(' frontend/src --no-filename
rg -lP '(?<![\w.])localStorage\.' frontend/src -g '*.test.*'
```
