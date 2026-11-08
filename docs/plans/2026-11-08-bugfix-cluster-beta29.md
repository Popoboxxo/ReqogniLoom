---
type: Plan
title: "Bugfix-Cluster beta.29 — Prod-Härtung, Passwortwechsel, API/UI-Verträge, Performance, Clients"
scope: "deploy/, .env.example, scripts/, .github/workflows/ci.yml, clients/, dist/opencode/, e2e/, backend/auth_tenancy, backend/rest_api, backend/mcp_server, backend/application, backend/attribute_definitions, backend/icd, frontend/src/{components,api,i18n}"
status: approved
date: 2026-11-08
branch_base: "origin/main @ 11db676a (v1.8.0-beta.28)"
author_agent: orchestrator
language: de
revision: "Stufe 2 — Repo-Scan vom 2026-11-08, Entscheidungen vom 2026-11-08, um Performance- und Clients-Cluster erweitert"
---

# Bugfix-Cluster beta.29

> **Reiner Umsetzungsplan.** Kein Code, keine Migration, keine Config-Änderung.
> Alle `datei:zeile`-Angaben sind gegen `origin/main @ 11db676a` (VERSION `1.8.0-beta.28`)
> geprüft. Aussagen aus Issues sind als „laut Issue" markiert, eigene Prüfung als
> „**verifiziert**".
>
> **Review-Status (konsolidiert):** Der Plan enthält das vollständige Review-Protokoll in
> **§13**. Drei Runden (Voll-Review → Delta → Kurz-Delta), Endergebnis
> **APPROVED with minor fixes**; alle Findings sind eingearbeitet. Die früher separaten
> Review-Dateien wurden in diesen Plan überführt.

---

## 0. Ausgangslage

### 0.1 Basis

| Aspekt | Wert |
|---|---|
| `origin/main` | `11db676a` (Merge PR #1734), `VERSION=1.8.0-beta.28` |
| Offene Issues | 68 |
| Issues ab #1731 | 14 (#1731–#1744) |
| Echt offen nach Prüfung | **21** (davon 4 Entscheidungs-/Verify-Fälle) |
| Zusätzlich beim Repo-Scan gefunden | **9** (N15–N23, §0.4) |
| Auf `main` bereits gefixt | **11** (schließen, §5) |
| Ziel-Release | `1.8.0-beta.29` |

### 0.2 Verifizierter Issue-Status

| Issue | Prio | Status auf `main` | Beleg |
|---|---|---|---|
| #1731 | high | **kein Defekt** — Liste ist strikt `user_id`-gescoped | `api_key_views.py:177-187`; `authentication.py:913-931` |
| #1732 | medium | offen | `GoalFormDialog.tsx:112` |
| #1735 | high | offen | `docker-compose.yml:645,950` |
| #1736 | medium | offen | `docker-compose.yml:164-197` (9× Literal) |
| #1737 | medium | **teilweise** — 4 Keys fehlen, nicht 11 | `.env.example` |
| #1738 | medium | offen | `mcp_server/throttling.py:130-132` |
| #1739 | high | offen | `bootstrap_admin.py:73-90`; keine `password/change`-Route |
| #1740 | medium | offen (4 von 15 Services) | `docker-compose.yml:1231,1247,1264,1330` |
| #1741 | medium | **bereits gefixt** — Digest-Pins vorhanden | `docker-compose.yml:295,590` |
| #1742 | low | offen | kein `shm_size` im Compose |
| #1743 | low | offen | kein `TZ` im Compose |
| #1744 | medium | offen | TLS-Flags sind dokumentiert (`.env.example:43`), aber es fehlt der Betriebsabschnitt mit Reverse-Proxy |
| #1716 | security | offen | `application/base.py:323-346` prüft nur RBAC |
| #1707 | high | offen | `serializers.py:2691` vs. `stage_matrix.py:678` |
| #1709 | high | offen | `IcdDetailPane.tsx:295-315` rendert Listenwerte ungeprüft |
| #1702 | high (clients) | offen | `scripts/clients/install.sh:218` + `dist/opencode/opencode.json.snippet:5` nutzen `/mcp/sse/` |
| #1705 | ci (clients) | offen | keine V2-Smoke-Stufe in `client-smoke.yml` |
| #1706 | chore (clients) | offen | `subagent_depth` im Root-`opencode.json`, Herkunft unbestätigt |
| #1401 | medium (perf) | **teilweise** — 3-s-Budget, aber weiterhin im Request-Thread | `requirement_service.py:87,1355-1380`; `trace_link_service.py:1096` ohne Budget |
| #1378 | medium (perf) | **bereits gefixt** — Sampling vor Embedding + Budget | `memory_admin_service.py:617-620` |
| #1399/#1411 | medium (perf) | offen, aber **nur per EXPLAIN** entscheidbar (FTS-Ausdruck stimmt mit Index überein) | `search_service.py:1206-1213` vs. `0002_fulltext_indexes.py:32-34` |
| #1410 | low (data) | **bereits gefixt** — Report + `--apply` | `audit_orphan_artifacts.py:9-14,47-55` |
| #1412 | low (data) | **weitgehend gefixt** — FK/`default=None`; Alt-`''` prüfen | `baseline/models.py:232-234`; `persistence/models.py:3354-3361` |
| #1404 | low (ops) | **teilweise** — mermaid 12.2.0, npm-audit neu messen | `frontend/package.json` |
| #1408 | low (mcp) | **kein Defekt** — reiner Zählbericht, Drift-Test existiert | `test_tool_manifest_drift.py` |
| #1418 | question | **moot** — BluePencil wurde entfernt (`1ad7ef17`) | — |
| #1247 | high | **nicht im Scope** (Upstream Honcho), siehe §12 | — |

### 0.3 Nutzerentscheidungen (fixiert 2026-11-08)

| Thema | Entscheidung |
|---|---|
| Umfang / PRs | **6 Cluster = 6 PRs** in `beta.29`: C1–C4 als Kern, C5/C6 eigenständig reviewbar |
| #1731 api-keys | **By design**: eigener Key-Zugriff bleibt, Cross-User/Tenant-Test + Doku, Issue mit Beleg schließen |
| #1739 Passwortwechsel | **Voll**: CLI `--reset-password` + `POST /auth/password/change/` + UI; **alle anderen Sessions werden invalidiert**, die aktuelle bleibt |
| #1707 severity | **Severity wird schreibbares Enum**; im Attribut-Kontext konfigurierbar (`editable: true|automation`) als **Vorstufe generischer Computed Fields** |
| #1716 ItemPermission | **Zentral im Write-Seam + alle 8 Artefakttypen**, Lesepfad separat |
| #1732 Dialoge | **Submit immer aktiv + Validierung beim Klick**, projektweit ein Muster |
| #1735/#1736 | **Parametrisieren** mit gemessenen Defaults |
| #1247 | **Separat**, nicht Teil dieses Releases |
| Login-Body-Token | **Default auf `False`** + E2E-Helper auf Cookie-Flow migrieren (Breaking Change, Release-Note) |

### 0.4 Neue Repo-Befunde (Stufe 2, verifiziert)

| # | Befund | Beleg | Cluster |
|---|---|---|---|
| N15 | In Minimal-Compose gelten dieselben zu kleinen Limits wie in der Base (backend 512 M bei `:123`, migrate 512 M bei `:183`), `TZ`/`shm_size` fehlen dort ebenfalls. `:84` ist **redis**, nicht backend | `docker-compose.minimal.yml:52,84,123,183,231` | C1-T1/T9 |
| N16 | 13 Settings-Keys haben keinen `.env.example`-Eintrag, u. a. `LLM_SYNC_TIMEOUT`, `AUTH_JWT_TTL_SECONDS`, `SECURE_HSTS_*`, `RLS_*`, `REDIS_HOST/PORT` (`SECURE_SSL_REDIRECT` ist bereits dokumentiert) | `settings.py:312-316,380-381,935-936,1094-1095,1480`; `.env.example:43` | C1-T3 |
| N17 | Create-Formulare deaktivieren den Submit in **18 Dateien / 17 Tabellenzeilen**, nicht nur in `/goals`; das gemeinsame `ArtifactFormActions` ist ebenfalls betroffen | `ArtifactFormActions.tsx:166`; Liste in C3-T3 | C3-T3 |
| N18 | `<th>`-Bestand: **77 `<th>`**-Elemente (dazu 17 `<thead>`), 62 mit `scope`; real ohne `scope` sind **11**: `UserManagement.tsx:267-271` (5) und `TriLabelOverviewDialog.tsx:80-85` (6) | `<th\b` vs. `<thead` getrennt zählen; `MatrixRenderer`/`CsvImport` haben `scope` auf der Folgezeile | C3-T5 |
| N19 | `create_requirement`/`update_requirement` und `trace_link.create` rufen den Embedding-Provider weiterhin im Request-Thread; nur Requirement hat ein 3-s-Budget, TraceLink gar keines | `requirement_service.py:87,481,888,1355-1380`; `trace_link_service.py:662,1096` | C5-T1 |
| N20 | `bump_version.py` kennt nur Base + Minimal. Eine neue **standalone** Compose-Datei mit `REQOGNILOOM_VERSION` müsste ergänzt werden; als **Overlay** (empfohlene TLS-Variante) braucht sie keinen Tag. Ein Glob über `deploy/docker-compose*.yml` ist falsch (override/offhost haben keinen Tag) | `scripts/bump_version.py:55-64,206-208` | C1-T10 |
| N21 | Benutzeranlage prüft nur Passwort-**Länge**, nie Djangos Validatoren (Common/Numeric/Similarity) | `user_account.py:95,113`; `settings.py:463-468` | C2-T4 |
| N22 | CI hat kein TypeScript-, `manage.py check`-, `makemigrations --check`- oder Compose-Config-Gate | `ci.yml:29-52`; kein Treffer für `tsc --noEmit`/`makemigrations --check` | C4-T4 |
| N23 | Fünf TODO-only-Stub-Module ohne Importeur suggerieren nicht existierende Komponenten | `rest_api/models.py`, `rest_api/services.py`, `mcp_server/models.py`, `mcp_server/services.py`, `llm_adapter/models.py` | C4-T5 |

**Bewusst nicht als Befund geführt:** `idx_scan=0` bei `idx_requirement_fts_gin` (#1411) ist bei ~1.900 Zeilen auch bei korrektem Ausdruck plausibel (Seq Scan ist billiger). Der Query-Ausdruck stimmt mit dem Index überein; eine Änderung ohne EXPLAIN wäre Spekulation.

### 0.5 Belastbarkeit der Angaben

Alle `datei:zeile`-Angaben wurden nach dem adversarialen Review (2026-11-08) erneut geprüft.
Die genannten Commit-SHAs (`b5dc889d`, `707b6c1b`, `1ad7ef17`, `f15e166`, `11db676a`) existieren
im Repo. Die Speicher-Messwerte (968 MiB/744 MiB) und die EXPLAIN-Aussagen stammen aus den
Issues bzw. aus C5-T4 und sind **hier nicht reproduziert** — sie werden in Phase 0 bzw. C5-T4
verifiziert.

---

## 1. Cluster-Übersicht

| Cluster | Titel | Issues | Prio | Aufwand | Branch |
|---|---|---|---|---|---|
| C1 | Deploy/Prod-Härtung | #1735, #1736, #1737, #1738, #1740, #1742, #1743, #1744, N15, N16, N20 | P1 | 1,5 d | `fix/c1-deploy-prod-hardening` |
| C2 | Auth & Permissions | #1739, #1716, #1731, Passwort-Policy (N21), Token-Default (C2-T5) | P0/P1 | 5,0 d | `fix/c2-auth-password-and-item-permissions` |
| C3 | API- & UI-Verträge | #1707, #1709, #1732, #1668 (UI-Rest), #1406 (A11y) | P1 | 2,5 d | `fix/c3-api-ui-contracts` |
| C4 | Verifizieren, Schließen, Release | #1660, #1661, #1663, #1381, #1386, #1662, #1741, #1378, #1410, #1408, #1418, #1400, #1402, #1403, #1409, CI-Gates (N22), Stubs (N23) | P2 | 1,5 d | `chore/c4-issue-hygiene-release` |
| C5 | Performance & Daten | #1401, #1399/#1411 (Messung), #1412, #1410 (Runbook) | P2 | 1,5 d | `perf/c5-embedding-async-and-indexes` |
| C6 | Clients/OpenCode 2 | #1702, #1705, #1706 | P2 | 1,5 d | `fix/c6-clients-opencode2` |
| Phase 0 | Reproduktion auf frischem Stack | alle | Gate | 0,5 d | — |

**Gesamt:** ~14,0 Tage inkl. Phase 0. **Alle sechs Cluster gehen in `beta.29`.** C1–C4 sind der
Kern (vier PRs); C5 und C6 sind eigenständige PRs, die unabhängig reviewt und notfalls ohne
Kern-Risiko auf `beta.30` verschoben werden können.

---

## 2. C1 — Deploy/Prod-Härtung

**Ziel:** Ein Deployment, das `.env.example` und dem Base-Compose folgt, läuft auf einer
6-GB-VM ohne OOM-Kill, ohne unbegrenzte Logs, mit gepinnten Images und dokumentiertem TLS.

### C1-T1 — #1735 Memory-Limits parametrisieren

**Ursache (verifiziert):** `backend` und `celery` stehen auf 512 M / 384 M, gemessener Ist-Wert
ist 968 MiB / 744 MiB (Faktor 1,9). Der Kernel killt sie unter Last (`Exited (137)`).

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.yml:645` | `memory: ${BACKEND_MEM_LIMIT:-1536M}` |
| `deploy/docker-compose.yml:950` | `memory: ${CELERY_MEM_LIMIT:-1024M}` |
| `deploy/docker-compose.yml:873` + `deploy/docker-compose.minimal.yml:183` | `memory: ${MIGRATE_MEM_LIMIT:-1024M}` — der Migrate-Container fährt laut eigenem Kommentar bewusst unbegrenzte Index-Builds (FTS-GIN, HNSW) und ist damit der eigentliche OOM-Kandidat auf einer 6-GB-VM |
| `deploy/docker-compose.minimal.yml:123` | derselbe `BACKEND_MEM_LIMIT`-Default (N15 — heute ebenfalls 512 M; `:84` ist **redis** und bleibt unverändert) |
| `.env.example` | alle drei Keys mit Messwert-Kommentar und Hinweis „kleine VM: bewusst niedriger" |
| `deploy/README.md` | Abschnitt „Ressourcenbedarf" mit Messwerten und Formel |

**Nicht ändern:** `celery-beat` (768 M), `postgres` (384 M), `frontend` (128 M),
`redis` (512 M) — Messwerte liegen deutlich unter den Limits bzw. sind unkritisch.

**Tests:** `backend/memory/tests/test_deploy_resource_limits.py` (neu): YAML parsen, Defaults
≥ Messwert, backend/celery/migrate verwenden die Env-Variable statt Literal.

**DoD:** `docker stats` unter Last bleibt unter dem Default; Override per `.env` getestet.

---

### C1-T2 — #1736 Honcho-Modell aus der Umgebung

**Ursache (verifiziert):** Neun Modulpins stehen literal auf `mimo-v2.5`
(`docker-compose.yml:164,167,170,173,176,179,190,194,197`), unabhängig von `LLM_MODEL`.
`mimo-v2.5` ist am Zen-Go-Endpunkt abgekündigt → Derivation/Summary läuft still leer.

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.yml:164-197` | alle neun Pins → `${HONCHO_LLM_MODEL:-${LLM_MODEL:-mimo-v2.5}}` |
| `deploy/docker-compose.yml:163-197` | Transport/Base-URL ebenfalls variabel: `${HONCHO_LLM_TRANSPORT:-openai}`, `${HONCHO_LLM_BASE_URL:-https://opencode.ai/zen/go/v1}` |
| Kommentarblock | „mimo-v2.5 ist verifiziert" → „Default, überschreibbar; abgekündigte Modelle werden sichtbar über `derivation_status`" |
| `.env.example` | `HONCHO_LLM_MODEL`, `HONCHO_LLM_TRANSPORT`, `HONCHO_LLM_BASE_URL` dokumentieren |
| `backend/memory/honcho_backend.py` (+ `health.py`) | Health-Advisory: `derivation_status ∈ {"failed","unknown"}` → `degraded` statt grün. Der Provider-Fehlertext („Model has been deprecated") ist im Client **nicht** sichtbar — `derivation_status` ist nur `ok/unknown/failed/none` (`honcho_backend.py:1492-1531`); deshalb kein Text-Matching |

**Nicht Teil dieses Tasks:** eine generische „Modell existiert"-Vorabprüfung. Der
`llm-preflight`-Service ist laut eigenem Kommentar eine reine Config-Assertion ohne Netzwerk;
ein Modell-Live-Check gehört in einen separaten Smoke-Test.

**Tests:** `backend/memory/tests/test_honcho_deploy_contract.py` erweitern: kein literaler
Modellname mehr im `x-honcho-env`-Anker; die neun Pins lösen auf denselben Env-Ausdruck auf;
Health-Mapping `derivation_status ∈ {"failed","unknown"}` → `degraded`.

**DoD:** `docker compose --profile honcho config` zeigt für alle neun Module den Wert aus
`HONCHO_LLM_MODEL`; ein Wechsel von `LLM_MODEL` ändert alle neun mit.

---

### C1-T3 — #1737 `.env.example` + CI-Drift-Gate

**Ursache (verifiziert, Abweichung zum Issue):** Von den 11 im Issue genannten Keys fehlen
real **4**: `SESSION_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`, `COMPOSE_PROFILES`,
`LLM_SYNC_TIMEOUT`. Die übrigen 7 sind vorhanden (`AUTH_COOKIE_SECURE:53`,
`CSRF_COOKIE_SECURE:60`, `BACKEND_PORT:113`, `FRONTEND_PORT:114`,
`HONCHO_EMBEDDING_MODEL:462`, `HONCHO_EMBEDDING_VECTOR_DIMENSIONS:463`,
`BACKUP_OFFHOST_DIR:867`). Aus `settings.py` fehlen insgesamt **13 Keys** (drei davon —
`SESSION_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`, `LLM_SYNC_TIMEOUT` — nennt bereits das
Issue; `COMPOSE_PROFILES` ist Compose-only und kommt separat dazu):
`LLM_SYNC_TIMEOUT`, `AUTH_JWT_TTL_SECONDS`, `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`,
`SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`,
`DB_STATEMENT_TIMEOUT_MS`, `RLS_AS_ENFORCED`, `RLS_PREAUTH_ENFORCED`,
`REDIS_HOST`, `REDIS_PORT`, `SELF_INIT_ON_MIGRATE`.
`SECURE_SSL_REDIRECT` ist bereits dokumentiert (`.env.example:43`) und gehört **nicht** in die
Liste; im TLS-Block wird nur darauf verwiesen (R-13).

| Datei | Änderung |
|---|---|
| `.env.example` | 4 fehlende Keys (auskommentiert, Default + Wirkung) plus die neuen C1-Keys (`BACKEND_MEM_LIMIT`, `CELERY_MEM_LIMIT`, `HONCHO_LLM_*`, `POSTGRES_SHM_SIZE`, `TZ`) |
| `.env.example` | die 13 Settings-Keys plus `COMPOSE_PROFILES` (Compose-only) als eigener „Advanced/Security"-Block; `RLS_*` und `SELF_INIT_ON_MIGRATE` mit Warnung (nur für kontrollierte Rollouts), `SECURE_HSTS_*` mit TLS-Verweis |
| `scripts/check_env_example_keys.py` (neu) | parst `${VAR…}`/`$VAR` in `deploy/docker-compose*.yml` **und** `config("…")` in `backend/reqogniloom/settings.py`, vergleicht gegen `.env.example` (aktiv **oder** auskommentiert), Allowlist mit Begründung für Compose-/Django-interne Variablen (u. a. `COMPOSE_PROFILES`, das Compose selbst liest); **Doppeldefinition** eines Keys ist ein Fehlerfall (R-13); Exit 1 mit Diff-Liste |
| `.github/workflows/ci.yml:346-362` | `scripts/test_check_env_example_keys.py` in die Skript-Testliste + eigener Run-Step |
| `scripts/test_check_env_example_keys.py` (neu) | Fixtures: fehlender Key, auskommentierter Key, doppelt definierter Key, `$${…}`-Shell-Escape darf **nicht** als Compose-Variable gelten, Allowlist greift |

**DoD:** Ein neuer Compose- oder Settings-Key ohne `.env.example`-Eintrag lässt CI rot werden.

---

### C1-T4 — #1738 Ungültige Rate = Konfigurationsfehler, kein 500

**Ursache (verifiziert):** `settings.py:533-535` (`_throttle_rate`) reicht den Rohstring durch;
`rest_api.throttling.py:129-145` (`get_rate`) gibt ihn ebenfalls nur zurück. Das `ValueError`
entsteht erst in DRFs `SimpleRateThrottle.__init__`/`parse_rate`
(`backend/mcp_server/throttling.py:130-132` ruft nur `super().__init__()`) und endet im
MCP-Request-Pfad als 500.

**Mechanik (ein Weg, nicht drei — R-09):** Der Settings-Import bleibt **tolerant** und wirft
nicht. Der Django-System-Check meldet den Fehler vor dem ersten Request; der Request-Pfad
übersetzt ihn defensiv in 503.

| Datei | Änderung |
|---|---|
| `backend/rest_api/checks.py` (neu) | Django-System-Check `rest_api.E001`: alle Rate-Settings (`API_RATE_LIMIT_*`, `LOGIN_*`, `REFRESH_*`, `MCP_RATE_LIMIT_*`) gegen DRFs `parse_rate` prüfen; Fehlermeldung nennt Variablenname **und** erwartetes Format, nie den Wert |
| `backend/rest_api/apps.py` | `ready()` importiert/registriert `rest_api.checks` (Muster wie `persistence/apps.py:31`, `application/apps.py:53`, `llm_adapter/apps.py:148`, `memory/apps.py:67`) |
| `backend/reqogniloom/settings.py:533-535` | `_throttle_rate` bleibt tolerant (kein `ImproperlyConfigured` beim Import — sonst crasht `manage.py check` mit Traceback statt `E001` zu melden) |
| `backend/rest_api/throttling.py:106-146` | `DynamicRateThrottle.__init__` fängt `ValueError` aus `SimpleRateThrottle.parse_rate` und wirft `ImproperlyConfigured` mit Scope-Namen |
| `backend/mcp_server/throttling.py:130-132` | `McpApiKeyRateThrottle.__init__` fängt `ValueError` und wirft `ImproperlyConfigured` |
| `backend/mcp_server/views.py:395` | `ImproperlyConfigured` um `check_mcp_key_rate_limit` → **503** im JSON-RPC-Fehlerumschlag mit `retry_after`-Hinweis |

**Tests:** `backend/rest_api/tests/test_throttle_rate_config.py` (neu): `MCP_RATE_LIMIT_KEY=abc`
→ `rest_api.E001` (kein Traceback); Request-Pfad → 503, kein 500; gültige Werte unverändert.

**DoD:** Ein Token statt einer Rate macht die MCP-Schnittstelle nicht mehr unbenutzbar, und
`manage.py check` meldet die Ursache vor dem ersten Request.

---

### C1-T5 — #1740 Log-Rotation für drei Honcho-Services

**Ursache (verifiziert):** Das Base-Compose hat **15** Services, davon **11** mit
`logging`-Block. Ohne Block sind **vier**: `honcho` (`:1330`), `honcho-postgres` (`:1231`),
`honcho-redis` (`:1247`) und `honcho-migrate` (`:1264`) — Letzterer ist ein One-Shot mit
Alembic-/`configure_embeddings`-Output, der bei Fehlschleifen unbegrenzt wachsen kann.

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.yml` | denselben `json-file`-Block (`max-size: 10m`, `max-file: "3"`) an allen vier Services, inkl. `honcho-migrate` |

**Tests:** `test_honcho_deploy_contract.py` erweitern: **jeder** Service der Datei
(profile-unabhängig, also auch die Honcho-Profile) hat einen `logging`-Block; die Prüfung
iteriert über alle 15 Service-Keys statt über eine Einzelfallliste.

**DoD:** `docker inspect` zeigt für alle 15 Services dieselbe Rotation; `honcho-migrate`
eingeschlossen.

---

### C1-T6 — #1742 `shm_size` für Postgres

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.yml:294` (`postgres`) und `:1231` (`honcho-postgres`) | `shm_size: ${POSTGRES_SHM_SIZE:-256mb}` |
| `.env.example` | `POSTGRES_SHM_SIZE` dokumentieren (große Installationen: `1gb`) |

**Tests:** YAML-Assertion in `test_deploy_resource_limits.py`; `docker inspect` im QA-Gate.

---

### C1-T7 — #1743 Zeitzone

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.yml` | `x-tz-env: &tz-env` mit `TZ: ${TZ:-Europe/Berlin}`, per `<<: *tz-env` in jedes `environment:` gemerged |
| `.env.example` | `TZ` dokumentieren |
| `deploy/README.md` | Klarstellung: `TZ` ändert **nur** Log-/Prozess-Darstellung; DB bleibt UTC (`USE_TZ=True`, `TIME_ZONE=UTC` in `settings.py:474-476`) |

**Risiko:** YAML-Merge-Anker können ein `environment:`-Mapping überschreiben. Absicherung:
`docker compose config` in CI/QA-Gate prüfen; Test parst die Datei und assertet `TZ` in allen
Services.

---

### C1-T8 — #1744 Dokumentierter TLS-Betrieb

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.tls.example.yml` (neu, **Overlay**) | nur der `caddy`-Service (Reverse-Proxy vor `backend:8000` und `frontend:80`, automatisches ACME, `X-Forwarded-Proto`); wird mit `-f docker-compose.yml -f docker-compose.tls.example.yml` genutzt, dupliziert keine App-Services und trägt keinen eigenen Versions-Tag |
| `deploy/README.md` | Abschnitt „Produktivbetrieb mit TLS": Caddy-Beispiel + nginx-Alternative, Flag-Matrix, `bool("False")`-Falle, Aussage „HTTP ist Testmodus" |
| `.env.example` | TLS-Block: **Verweis** auf den bereits vorhandenen `SECURE_SSL_REDIRECT` (`.env.example:43`), plus `AUTH_COOKIE_SECURE=true`, `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`, `CSRF_TRUSTED_ORIGINS=https://…` — keine Doppeldefinition (R-13) |

**Wichtig (verifiziert):** `SECURE_PROXY_SSL_HEADER` wird bereits korrekt aus
`SECURE_SSL_REDIRECT` abgeleitet (`settings.py:105-109`) — kein Code-Change nötig, nur Doku.
`CSRF_TRUSTED_ORIGINS` (`settings.py:185-193`) muss die HTTPS-Origin enthalten.

**Tests:** `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tls.example.yml config -q` mit Dummy-`.env` in CI; Doku-Review. Als Overlay ist die Datei kein Versions-Träger (N20 entfällt für sie, R-15).

---

### C1-T9 — Compose-Hygiene in Minimal/Base angleichen + Config-Gate (N15)

**Ursache (verifiziert):** `docker-compose.minimal.yml` hat zwar `logging` und `healthcheck`,
aber dieselben zu kleinen Backend-Limits wie die Base (`backend:123` 512 M, `migrate:183`
512 M), kein `TZ` und kein `shm_size`. `:84` ist **redis** (512 M) und bleibt unverändert.

| Datei | Änderung |
|---|---|
| `deploy/docker-compose.minimal.yml` | `BACKEND_MEM_LIMIT`/`MIGRATE_MEM_LIMIT`-Defaults, `TZ` via Anker, `shm_size` für Postgres |
| `backend/memory/tests/test_compose_consistency.py` (neu) | parst Base + Minimal: **jeder** Service hat `logging`; `postgres` hat `shm_size`; jeder Service hat `TZ`; Limits aus derselben Env-Variable — **pro Datei über die vorhandenen Langläufer** (Base: backend/celery/migrate; Minimal: backend/migrate, kein celery) |
| `.github/workflows/ci.yml` | neuer Schritt `docker compose -f deploy/docker-compose.yml config -q` (analog `.minimal.yml`, TLS-Beispiel) mit Dummy-`.env` — fängt YAML-Merge-/Anker-Fehler vor dem Deploy |

**DoD:** `docker compose config` ist für alle ausgelieferten Compose-Dateien grün; Minimal und
Base driften nicht auseinander.

---

### C1-T10 — Release-Bump-Guard für neue Compose-Träger (N20, R-11/R-15)

**Ursache (verifiziert):** `scripts/bump_version.py:55-64` listet die Träger explizit; ein Glob
über `deploy/docker-compose*.yml` wäre falsch, weil `override.yml`, `override.example.yml` und
`offhost.yml` keinen `REQOGNILOOM_VERSION`-Tag tragen (nur Base und Minimal tun das). Die neue
TLS-Datei ist ein **Overlay** ohne Image-Zeile und braucht daher keinen Bump.

| Datei | Änderung |
|---|---|
| `scripts/bump_version.py:55-64` | Trägerliste bleibt explizit; nur **falls** später eine standalone Compose mit Versions-Tag dazukommt, wird sie dort ergänzt |
| `scripts/test_bump_version.py` | neuer Guard-Test: jede `deploy/docker-compose*.yml`, die `REQOGNILOOM_VERSION` enthält, **muss** in `TEXT_CARRIERS` stehen; Overlays ohne Tag sind über eine begründete Allowlist ausgenommen |
| `scripts/check_plugin_packages.py --expect-version` | unverändert, im Release-Gate mitlaufen lassen (Dateiname mit Unterstrichen, R-11) |

**DoD:** Eine neue Compose-Datei mit Versions-Tag ohne Träger-Eintrag lässt den Test rot werden;
Overlays erzeugen kein False Positive.

---

## 3. C2 — Auth & Permissions

**Aufwand:** T1 1,0 · T2 1,5 · T3 0,1 · T4 0,25 · T5 2,0 ≈ **5,0 d** (Summe der Tasks).

### C2-T1 — #1739 Passwortwechsel (höchste Priorität)

**Ursache (verifiziert):** Kein `password/change`-Endpoint (`urls.py:337-382`), `PATCH /auth/me/`
erlaubt nur `first_name`/`last_name` (`serializers.py:3528-3548`), `bootstrap_admin` ist
create-only (`bootstrap_admin.py:73-90`) — obwohl `provision_admin(reset_password=True)`
existiert (`provisioning.py:79-123`).

**Backend:**

| Datei | Änderung |
|---|---|
| `backend/auth_tenancy/services/authentication.py:427-458` | neue Methode `read_refresh_session_id(token)`: ruft zuerst `validate_refresh_token(token)` (bzw. prüft `typ == "refresh"`) und liest dann den `sid`-Claim; `read_refresh_amr` allein validiert **nicht** (Docstring `:428-435`) |
| `backend/auth_tenancy/services/refresh_token_store.py:58-65,117` | neue Konstante + Wrapper `revoke_refresh_families_for_user(user_id, reason, except_session_id)` |
| `backend/auth_tenancy/migrations/00XX_revoke_sessions_for_user.py` (neu) | `SECURITY DEFINER`-Funktion `public.auth_revoke_refresh_families_for_user(uuid, text, uuid)` mit fixem `search_path`, ohne dynamisches SQL; **`ALTER FUNCTION … OWNER TO <DEFINER_DB_ROLE>`**, `REVOKE ALL … FROM PUBLIC`, `GRANT EXECUTE` (Vorbild `0021`/`0110`) |
| `backend/auth_tenancy/services/password_change.py` (neu) | `change_password(user_id, current, new, *, current_session_id)`: `check_password`, `validate_password` (`settings.py:463-468`), `set_password`, alle **anderen** Refresh-Familien widerrufen, Audit-Event |
| `backend/rest_api/auth_views.py` + `urls.py` | `POST /api/v1/auth/password/change/` (`PasswordChangeView`), 204; 400 bei falschem aktuellem Passwort oder Policy-Verstoß; **Gate: `auth_method != "api_key"` und `"pwd" in ctx.amr`**; per-User-Throttle wie Login; Audit |
| `backend/rest_api/serializers.py:3547` | `password` in `PROTECTED_FIELDS` bleibt, Fehlermeldung verweist auf den neuen Endpoint |
| `backend/auth_tenancy/management/commands/bootstrap_admin.py:60-90` | `--reset-password`: verlangt `SYSTEM_ADMIN_PASSWORD`, ruft `provision_admin(reset_password=True)`, widerruft danach **alle** Sessions des Users |

**`sid`-Herkunft (R-03, korrigiert):** Der Access-Token trägt **kein** `sid`
(`password_authentication.py:215-223`); nur der Refresh-Token hat es (`:282-291`). Der
`PasswordChangeView` liest deshalb den `reqogniloom_refresh`-Cookie
(`REFRESH_COOKIE_NAME`, `auth_views.py:49-50,818`), validiert ihn über die neue Methode und
reicht `except_session_id` weiter. Das ist derselbe Cookie, den `LogoutView` bereits liest.
Kein Token-Format-Change, kein Legacy-Fallback nötig.

**Fallback ohne Refresh-Cookie (reine Bearer-Aufrufer):** `except_session_id=None` → alle
Refresh-Familien werden widerrufen; der aktuell vorgelegte Access-Token bleibt bis zu seinem
Ablauf (≤ `AUTH_JWT_TTL_SECONDS`, 3600 s) gültig, es gibt nur kein Refresh mehr. Das wird im
Endpoint-Docstring und in der Release-Note dokumentiert.

**Wichtig:** Die aktuelle Cookie-Session bleibt gültig (ihre `sid` wird ausgenommen).
Access-Tokens anderer Sessions sterben spätestens mit `AUTH_JWT_TTL_SECONDS` (3600 s,
`settings.py:942`); Refresh-Tokens sofort. Der `sid`-Wert wird nie aus dem Request-Body
akzeptiert — sonst könnte ein Aufrufer eine fremde Session ausnehmen.

**Definer-Vertrag (R-03):** Die neue Funktion bricht sonst zwei CI-Guards. Zusätzlich zu
`test_refresh_token_rls_1182.py` müssen gepflegt werden:
`backend/persistence/tests/test_definer_owner_role_1180.py:59-70` (`DEFINER_SIGNATURES`),
`:73-81` (`DEFINER_TABLE_PRIVILEGES`), `:113-149` (Inventar/Owner) und die migrationsseitige
Signaturliste (`0110_security_definer_owner_role.py:22-58`).

**UI:**

| Datei | Änderung |
|---|---|
| `frontend/src/components/UserProfileSettings/SecuritySection.tsx` | Block „Passwort ändern" (aktuell/neu/wiederholen), Erfolgs-/Fehlermeldung, `data-testid` |
| `frontend/src/i18n/locales/{de,en}.json` | `security.password.*` |
| `frontend/src/context/AuthContext.tsx` (bzw. `frontend/src/api/mfa.ts` als Muster) | `changePassword()` — eine `frontend/src/api/auth.ts` existiert **nicht** (R-18) |

**Tests:** `backend/auth_tenancy/tests/test_password_change.py` (neu): Erfolg; falsches
aktuelles Passwort → 400 (kein Enumeration-Leak); Policy-Verstoß → 400; andere Sessions
widerrufen, aktuelle Cookie-Session bleibt (zweite Login-Session); Bearer ohne Refresh-Cookie
→ alle Familien widerrufen, Access-Token bleibt bis TTL; API-Key-Aufrufer → 403;
unauthentifiziert → 401; Throttle; CLI-Reset setzt Passwort und killt Sessions;
Definer-Owner-Guard grün; Frontend-Unit-Test für das Formular.

**Doku:** `deploy/README.md` Betreiber-Abschnitt „Admin-Passwort zurücksetzen"
(`SYSTEM_ADMIN_PASSWORD` ändern → `manage.py bootstrap_admin --reset-password` → `up -d`),
`.env.example`-Kommentar korrigieren (Variable wirkt nur bei Create/Reset).

**DoD:** Passwort ist über UI, REST und CLI änderbar; nach Änderung sind fremde Sessions tot.

---

### C2-T2 — #1716 ItemPermission auf Schreibpfaden

**Ursache (verifiziert):** `ServiceBase._assert_write_permission` (`application/base.py:323-346`)
prüft ausschließlich die RBAC-Rolle. `EffectivePermissionService` wird nur in Suche
(`search_service.py:1036`), Baseline-Rollback (`baseline_rollback_service.py:1715`) und
`permissions.check` aufgerufen.

**Design:**

| Datei | Änderung |
|---|---|
| `backend/application/base.py` | neuer Helper `_assert_item_write_permission(ctx, artifact_id, *, action)`: nutzt `ItemPermissionService.check_permission` **direkt** (statt des gemergten `resolve_effective_permission`), damit explizites `deny` von `read` unterscheidbar ist; `deny`/`none` → `NotFoundError`, `read` → `PermissionDeniedError`, keine Item-Regel → durchlassen. Kein zweiter RBAC-Check (der bleibt in `_assert_write_permission`) |
| `backend/application/requirement_service.py` | `update_requirement`, `delete_requirement` |
| `backend/application/architecture_service.py` | `update_architecture_element`, `delete_architecture_element` |
| `backend/application/risk_service.py` | `update_risk`, `delete_risk` |
| `backend/application/issue_service.py` | `update_issue`, `delete_issue` |
| `backend/application/adr_service.py` | `update_adr`, `delete_adr` |
| `backend/application/test_service.py` | `update_test_case`, **`update_test_status`** (:512), `delete_test_case` |
| `backend/application/glossary_service.py` | **`update`** (:265 — heißt nicht `update_glossary`), `delete` |
| `backend/application/change_request_service.py` | `update_change_request`, `delete_change_request` |
| `backend/auth_tenancy/services/item_permission_INTERFACES.md` | Schreibpfad-Sektion ergänzen; Lesepfad als offen markieren |
| Follow-up-Issue | „ItemPermission auf Retrieve/List (Lesepfad)" |

**Explizite Methodenliste, keine Präfix-Heuristik (R-10):** `glossary_service.update` und
`test_service.update_test_status` würden von „jedes `update_*`" nicht erfasst. `delete_*` und
der Soft-Delete-Pfad kommen mit in denselben Guard — sonst bleibt ein Umweg um eine
`read`/`none`-Sperre offen (Löschen statt Ändern). Scope-Aufschlag: +0,5 d.

**Bewusst nicht:** globale Basisklassen-Änderung für Create — dort ist die Semantik (noch)
nicht entschieden.

**Tests:** Matrix je Typ (item rule `read` → 403, `none` → 404, artefakt-scoped schlägt
workspace-scoped, keine Regel → unverändert) für Update **und** Delete, REST + MCP
`requirement.update`, Rollback-Pfad bleibt grün.

**Risiko:** Bestehende Workspaces mit workspace-weiten `read`-Regeln verlieren für Editoren
Schreib- und Löschrechte. Das ist gewollt (Defense-in-Depth), muss aber in die Release Notes.
Performance: ein zusätzlicher, gecachter Lookup pro Schreibvorgang.

**DoD:** Ein Editor kann ein per ItemPermission gesperrtes Artefakt weder per REST noch per MCP
ändern **noch löschen**.

---

### C2-T3 — #1731 api-keys: by design bestätigen

**Ursache (verifiziert):** `list()`/`retrieve()` rufen
`AuthenticationService.list_api_keys(user_id=<Aufrufer>)` (`api_key_views.py:180,240`), und der
Service filtert `ApiKey.unscoped.filter(user_id=user_id)` (`authentication.py:913-915`). Ein
Viewer sieht ausschließlich **seine eigenen** Key-Metadaten. Die Prämisse „Credential-Landschaft
eines Workspaces" trifft nicht zu; die Freigabe für eigene Keys ist die bewusste Entscheidung aus
#716.

| Datei | Änderung |
|---|---|
| `backend/rest_api/tests/test_api_keys_self_scoped.py` (neu) | User A sieht 0 Keys von User B; Viewer `GET` → 200 nur eigene; fremde `pk` → 404; Tenant-Isolation |
| `rest_api/api_key_views.py` | OpenAPI-Beschreibung: „returns only the caller's own keys" |
| `docs/` RBAC-Matrix | Zeile für `api-keys` mit Begründung (#716, self-service) |
| Issue #1731 | Kommentar mit Beleg + schließen |

**DoD:** Test beweist die Isolation; Issue geschlossen mit nachvollziehbarer Begründung.

---

### C2-T4 — Passwort-Policy bei Benutzeranlage (N21, neu)

**Ursache (verifiziert):** `UserAccountService.create` prüft nur eine Mindestlänge
(`user_account.py:95`), dann `set_password` (`:113`). Django-Validatoren
(`settings.py:463-468`) werden auf **keinem** nutzergetriebenen Anlagepfad aufgerufen; auch der
MCP-User-Admin prüft nur Länge (`mcp_server/tools/users.py:186-190,483-492`).
**Wichtig (R-08):** `provision_admin` schreibt das Passwort direkt über
`user.set_password` (`provisioning.py:121-122`) und läuft **nicht** über den Service — die
Betreiber-Passwörter aus `bootstrap_admin`/`self_init`/`seed_demo` bleiben also unberührt.

| Datei | Änderung |
|---|---|
| `backend/auth_tenancy/services/user_account.py:95` | Mindestlänge bleibt als Floor, zusätzlich `django.contrib.auth.password_validation.validate_password(password, user=<temporärer User mit username/email>)`; `ValidationError` → `ValueError` mit den Validator-Meldungen |
| `backend/auth_tenancy/services/password_change.py` (aus C2-T1) | derselbe Validator-Aufruf, eine gemeinsame Helper-Funktion statt zweier Kopien |
| `backend/mcp_server/tools/users.py:483-492` | Validator-Fehler strukturiert als `VALIDATION_ERROR` mit Feld `password` |
| `backend/auth_tenancy/provisioning.py:121-122` | **bewusst ausgenommen** mit Kommentar: Betreiber-Passwort wird out-of-band per ENV gesetzt; eine Validierung dort würde Bootstrap/Disaster-Recovery blockieren. Im Threat Model begründen |
| `backend/auth_tenancy/management/commands/seed_demo.py` | bleibt unberührt (läuft über `provision_admin`), Kommentar präzisieren |

**Tests:** `commonpassword`, rein numerisch, username-ähnlich → 400/ValueError; starkes Passwort
→ ok; bestehende Nutzer können sich unverändert anmelden (keine Rückschreibung); Bootstrap mit
kurzem ENV-Passwort funktioniert weiterhin (dokumentierte Ausnahme).

**DoD:** Jeder **nutzergetriebene** Anlage-/Änderungspfad (REST, MCP, Passwortwechsel) lehnt
Passwörter ab, die Djangos Validatoren verletzen. Die Betreiber-Provisionierung ist die
dokumentierte, begründete Ausnahme.

---

### C2-T5 — Login-Body-Token: Default auf `False` (entschieden)

**Status (verifiziert):** `AUTH_LOGIN_INCLUDE_BODY_TOKEN` steht auf `True`
(`settings.py:964-966`); der Body-Token ist seit #696 deprecated. Die E2E-Helper lesen ihn
massiv: `grep` findet **147 `getAuthToken`-Treffer in 42 Spec-Dateien** (u. a.
`api-completeness.spec.ts` 13×, `stakeholder-needs.spec.ts` 8×, `hermes-bugfix-campaign.spec.ts`
9×) plus ~25 `Authorization: Bearer`-Stellen in `e2e/helpers/auth.ts`. Der Cookie-Pfad erzwingt
für jede mutierende Anfrage ein `X-CSRFToken` (`backend/rest_api/tests/test_auth_cookie.py:183`);
`e2e/tests/bearer-token-role-resolution.spec.ts:44` testet `[REQ-126] getAuthToken` selbst.

**Entscheidung: Variante A — Default `False`.**

| Datei | Änderung |
|---|---|
| `backend/reqogniloom/settings.py:964-966` | Default auf `False`; Kommentar/Doku: `True` ist der Rückfall-Schalter |
| `e2e/helpers/auth.ts` | `getAuthToken()` → `loginViaCookie(ctx)`; `ctx.request` teilt den Cookie-Jar; **CSRF-Helper**: `csrftoken`-Cookie lesen und `X-CSRFToken` bei POST/PATCH/DELETE setzen; `setAuthToken`/`reqflow_token` entfernen, falls die SPA ihn nicht liest (prüfen) |
| `e2e/helpers/preconditions.ts:182` | Token-Rückgabe durch Cookie-Login ersetzen; alle `token`-Parameter der Helper entfallen |
| `e2e/tests/**` (42 Dateien) | `injectBearer`/Token-Plumbing auf `request`-Kontext umstellen — **kein händisches Durchzählen**: der Task endet erst, wenn `grep -rn "getAuthToken\|Authorization: Bearer" e2e` leer ist (Gate im PR) |
| `e2e/tests/bearer-token-role-resolution.spec.ts:44` | Spec **ersetzen** durch einen Cookie-Flow-Rollen-Test (kein Opt-in-Pfad im E2E — das kollidiert mit dem Grep-Gate und QA #21); die Opt-in-Assertion bleibt im Backend-Test `rest_api/tests/test_login_body_token_deprecation_696.py:83-94` und braucht dort nach dem Flip ein explizites `@override_settings(AUTH_LOGIN_INCLUDE_BODY_TOKEN=True)` |
| `deploy/README.md`, `docs/` | Login-Response-Beispiel ohne `token`; Weg zurück (`AUTH_LOGIN_INCLUDE_BODY_TOKEN=True`) und Migrationshinweis für API-Clients (Cookie oder `X-API-Key`) |

**Aufwand:** ~2,0 d (R-01: 147 Stellen in 42 Dateien + CSRF + ein Bearer-spezifischer Spec).
Externe API-Clients sind ein dokumentierter Breaking Change; der Opt-in bleibt.

**DoD:** Login-Response enthält keinen `token`; die E2E-Suite ist grün **ohne** Bearer- und
ohne `getAuthToken`-Fallback; CSRF wird im Cookie-Pfad korrekt gesendet; Release-Note nennt
den Weg zurück.

---

## 4. C3 — API- & UI-Verträge

### C3-T1 — #1707 Risk-Severity: ein Träger, ein Typ, konfigurierbar

**Ursache (verifiziert):** `RiskSerializer.severity` ist ein `ChoiceField`
(`serializers.py:2691-2693`), während die Attribut-Matrix für Risk einen **ext-Zwilling**
`severity` vom Typ `number` deklariert (`stage_matrix.py:673-685`). Der Gateway validiert den
Payload-Schlüssel `severity` gegen diesen Zwilling → `"high"` scheitert mit
„must be a number"; `7` scheitert am `ChoiceField` mit „not a valid choice". `create_risk`
(`risk_service.py:176-191`) und `update_risk` (`:305-317`) nehmen `severity` gar nicht an — das
Feld ist heute nur über die Datenbank setzbar.

**Entscheidung:** Severity wird ein **schreibbares Enum** (`low|medium|high`). Im
Attribut-Kontext ist die Schreibbarkeit konfigurierbar (`editable: true` = manuell,
`editable: "automation"` = serverseitig abgeleitet). Das ist die **Vorstufe generischer
Computed Fields**: die Semantik von `automation` wird erstmals zentral durchgesetzt, es gibt
aber noch keine generische Berechnungs-Engine.

| Datei | Änderung |
|---|---|
| `backend/rest_api/serializers.py:2691-2693` | `severity` bleibt `ChoiceField`, **`required=False`** und **kein `default`** (R-16: ohne `default` wäre das Feld `required=True` und „ohne Angabe → Ableitung" unmöglich; PATCH darf keinen Reset auslösen) |
| `backend/rest_api/views.py:9569-9589` (create) und `:9631-9657` (update) | `severity=data.get("severity")` an `create_risk`/`update_risk` durchreichen — heute fehlt der Parameter in beiden Aufrufen, deshalb bleibt das Feld wirkungslos (R-02). **Echo-Mechanismus:** Im PATCH den Ist-Wert über `_svc().get_risk(...)` laden und `severity` nur dann in den Payload geben, wenn er sich unterscheidet — Muster `_reject_derived_level` (`views.py:1836,2123`), weil der Gateway-`existing`-Marker (`field_validation.py:337-346`) keinen Wertvergleich erlaubt |
| `backend/application/attribute_definition_service.py:237-268` | `resolve(ctx, item_type, workspace_id)` liefert die Policy (`editable`) gecacht; der Service nutzt sie für die bedingte Ableitung |
| `backend/application/risk_service.py:176,305` + `:271,:415` | `severity: str \| None` akzeptieren und persistieren; die Ableitung `risk.severity = Risk.score_to_severity(score)` wird **bedingt**: nur wenn `severity is None` **und** die Workspace-Definition `editable="automation"` sagt; sonst bleibt der manuelle Wert stehen |
| `backend/mcp_server/tools/generic.py:75` | Feldmap für Risk gegenprüfen, damit `severity` auch über den MCP-Generic-Pfad ankommt |
| `backend/attribute_definitions/stage_matrix.py:673-685` | ext-Zwilling `severity` `number` **entfernen**; stattdessen den echten Träger als `enum` (Optionen `low|medium|high`) führen |
| `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py:244` | `severity` aus `PER_ITEM_TYPE_EXCLUDED_FIELDS["Risk"]` entfernen (Issue bleibt: es ist jetzt bewusst sichtbar) |
| `backend/attribute_definitions/field_validation.py:314-390` | `editable == "automation"`: Client-Wert wird abgelehnt (400 mit Erklärung). Das **Echo-Tolerieren passiert im View** (Ist-Wert-Vergleich), nicht in diesem Seam — der `existing`-Marker ist nur ein Präsenz-Marker (`:337-346`) |
| `backend/attribute_definitions/schema.py:177-181` | `automation`-Semantik dokumentieren (Vorstufe Computed Fields) |
| `backend/application/management/commands/repair_risk_severity_attribute.py` (neu) | Dry-Run: findet numerische `custom_fields["severity"]`-Werte, mappt sie auf das Enum, entfernt den Zwilling aus Workspace-Definitionen; `--apply` schreibt |

**Tests:** POST/PATCH `"high"` → 201/200 und beim Lesen `"high"`; `7` → 400 nur noch mit
Enum-Meldung; ohne Angabe → abgeleiteter Default **nur** bei `automation`, sonst `low|medium|high`
aus dem Score als Initialwert; `editable="automation"` → abweichender Wert 400, Echo 200;
PATCH ohne `severity` ändert den Wert nicht; Matrix über die drei Rigor-Presets (sichtbar in
Stufe 2/3).

**DoD:** Genau eine Fehlermeldung pro Fehlerfall, keine widersprüchlichen Validierungen; der
Wert ist über REST (Create **und** Update), MCP und UI schreibbar.

---

### C3-T2 — #1709 ICD-Detailseite stürzt bei Objekt-Listen ab

**Ursache (verifiziert):** `IcdDetailPane` rendert `detail.preconditions/postconditions/invariants`
über `ReadOnlyList` (`IcdDetailPane.tsx:295-315`) und gibt jeden Wert direkt als React-Kind aus
(`{v}`). Der Backend-Vertrag ist `string[]`, aber `ContractValidator.validate_syntax` prüft nur
„ist eine Liste", nicht die Elementtypen (`contract_validator.py:104-112`). Ein historischer
Schreibpfad hat Parameter-Objekte (`{name, unit, ordering, data_type}`) in diese Felder
geschrieben → React #31.

| Datei | Änderung |
|---|---|
| `frontend/src/components/IcdView/IcdDetailPane.tsx:309-312` | nur Strings rendern; Nicht-Strings defensiv überspringen (kein Crash), im Dev-Log warnen |
| `frontend/src/api/icds.ts:54-70` | Typ bleibt `string[]`; Kommentar zum Defensiv-Rendering |
| `backend/icd/contract_validator.py:104` | jedes Listenelement muss `str` sein → `syntax_errors` + 400 |
| `backend/icd/icd_manager.py:399,566` | DTO-Validierung nutzt denselben Check (Create **und** Update) |
| `backend/icd/management/commands/repair_icd_contract_lists.py` (neu) | Dry-Run-Report der betroffenen ICDs; `--apply` verschiebt Parameter-Objekte nach `parameters` bzw. stringifiziert mit Audit |

**Tests:** Frontend-Unit-Test mit einem Objekt in `preconditions` → rendert, keine
Error-Boundary; Backend-400-Test für Nicht-String-Elemente; Repair-Command idempotent.

**DoD:** `/icds/:id` rendert oder zeigt eine leere Liste — nie die Error-Boundary; neue
Nicht-String-Payloads werden mit 400 abgewiesen.

---

### C3-T3 — #1732 Submit-Validierung statt deaktiviertem Button

**Ursache (verifiziert):** `GoalFormDialog` deaktiviert den Submit bei leerem Titel
(`GoalFormDialog.tsx:112`: `disabled={isSubmitting || !title.trim()}`), die Validierungsmeldung
hängt aber am Klick-Pfad. Der Repo-Scan findet **18 Dateien** (17 Tabellenzeilen) mit demselben
Muster (N17), darunter das gemeinsame `ArtifactFormActions` (`:166`, `missingCreateValue`) — der
Defekt ist also nicht auf `/goals` beschränkt.

**Muster (projektweit):** Submit bleibt aktiv; beim Klick wird validiert, das erste ungültige
Feld bekommt `aria-invalid="true"`, `aria-describedby` auf eine `role="alert"`-Meldung, und der
Fokus springt dorthin. Das entspricht dem bereits korrekten `/glossary`-Verhalten.

**Umzustellen (Dialog-/Formular-Submit mit Pflichtfeld):**

| Datei | Stelle |
|---|---|
| `shared/ArtifactForm/ArtifactFormActions.tsx` | `:166` `missingCreateValue` (wirkt auf alle Artefakt-Formulare) |
| `Goals/GoalFormDialog.tsx` | `:112` |
| `TestRuns/TestRunsList.tsx` | `:422` |
| `ArchitectureEditors/ArchitectureEditors.tsx` | `:751` (ersetzt die #1595-Entscheidung „disabled + Hinweis") |
| `RequirementEditors/RequirementCreateFallbackForm.tsx` | `:193` |
| `RequirementEditors/GroupManager.tsx` | `:146` |
| `NeedsEditors/NeedList.tsx` | `:391` |
| `TestCaseEditors/DeriveTestCasePanel.tsx` | `:274` |
| `WorkItems/WorkItemCreateForm.tsx` / `WorkItemEditForm.tsx` | `:156` / `:310` |
| `WorkspaceSettings/WorkspaceSettings.tsx` | `:335` (Rename) |
| `WorkspaceSettings/PermissionsSection.tsx` | `:507` (Grant) |
| `SystemSettings/WorkspaceAdminSection.tsx` | `:206` (Clone) |
| `UserProfileSettings/ApiKeysSection.tsx` | `:177` |
| `BaselinesView/BaselineRollbackPanel.tsx` | `:484` (Begründung) |
| `WorkflowStatusEditor/WorkflowStatusEditor.tsx` | `:403` (Begründung) |
| `Audit/audit-dashboard.tsx` | `:1315` (Waiver-Begründung) |

**Bewusst nicht umgestellt** (kein Pflichtfeld-Dialog): Such-/Filter-Buttons
(`MemoryPage:619`, `ImpactView:463`, `FilterBar:293`), MFA-Code (`LoginPage:299`, `SecuritySection`),
Inline-Senden (`CommentPanel:169`) und der CSV-Import (`CsvImport.tsx:573,1091`, `disabled={!selectedFile}` —
der Datei-Picker ist die Aktion, ein Klick ohne Datei hat kein sinnvolles Ziel). Die Regel wird im
Plan dokumentiert, damit der nächste Scan nicht wieder 18 Treffer meldet.

| Datei | Änderung |
|---|---|
| `frontend/src/components/shared/useRequiredValidation.ts` (neu) | kleiner Hook: `validate(fields)`, `errors`, `focusFirstInvalid`, `clearError`; keine neue Form-Bibliothek |
| die 17 Dateien oben | `disabled` nur noch bei `isSubmitting`; Validierung beim Klick, `aria-invalid`/`aria-describedby`/`role=alert`, Fokus |
| `frontend/src/i18n/locales/{de,en}.json` | wiederverwendbare Pflichtfeld-Meldung |

**Tests:** Component-Tests für `/goals` und das gemeinsame ArtifactForm: leerer Pflichtwert →
Klick → genau eine `role=alert`, `aria-invalid="true"`, Fokus auf dem Feld; E2E-Spec analog.

**DoD:** Kein Anlege-Dialog ist im leeren Zustand gesperrt, ohne den Grund zu nennen.

**Scope-Hinweis (R-21):** Das ist der einzige Task mit Refactoring-Charakter. Bei engem
Release-Fenster zuerst die sechs Kern-Dialoge (`ArtifactFormActions`, `Goals`, `TestRuns`,
`ArchitectureEditors`, `RequirementCreateFallbackForm`, `NeedList`) und den Rest als Folge-PR —
der Bugfix-Kern bleibt dann unberührt.

---

### C3-T4 — #1668 Rest: UI-Filter „allokiert / nicht allokiert"

**Status (verifiziert):** REST (`views.py` `RequirementViewSet.list`, `extra=("allocated","level")`)
und MCP (`mcp_server/tools/requirements.py:223-232,634-644`) sind bereits umgesetzt; es fehlt die
UI-Sicht.

| Datei | Änderung |
|---|---|
| `frontend/src/components/RequirementEditors/RequirementList.tsx:325-405` | dritter persistierter Filter `allocation` (`all|allocated|unallocated`), durchgereicht als `?allocated=` |
| `frontend/src/components/RequirementEditors/useRequirementData.ts` | Query-Parameter `allocated` |
| `frontend/src/i18n/locales/{de,en}.json` | Filter-Labels |
| Toolbar | Kennzahl „unallokiert" (aus der bereits gefilterten Liste) |

**Tests:** Component-Test prüft den erzeugten Query-String; Persistenz über Workspace-Wechsel.

**DoD:** Allokationslücken sind in der UI filterbar; Issue #1668 kann geschlossen werden.

**Hinweis:** Die Umbenennung `level` → `specification_level` aus #1669 ist **nicht** Teil dieses
Plans (Datenmodell-/Design-Änderung, separater Release).

---

### C3-T5 — Accessibility-Runde aus #1406 (N18)

**Ursache (verifiziert, korrigiert nach R-07/N-01):** **77 `<th>`**-Elemente (dazu 17 `<thead>`),
davon 62 mit `scope`; real ohne `scope` sind **11**:
`Settings/UserManagement/UserManagement.tsx:267-271` (5) und
`AdminDialog/TriLabelOverviewDialog.tsx:80-85` (6). `MatrixRenderer.tsx:79` und
`CsvImport.tsx:292` sind **keine** Offender — dort steht `scope="col"` auf der Folgezeile.
Mehrere im ersten Entwurf genannte Tabellen (`AttributeTable`, `PermissionsSection`,
`PromptVariableTable`, `BaselinesPanels`, `MemoryManagementSection`) sind ebenfalls bereits
korrekt. Der SplitView-Divider ist 12 px breit (`role="separator"`, `tabindex="0"` vorhanden).
Die im Issue genannten BluePencil-Dialoge (`#bp-i1-*`) existieren nicht mehr (BluePencil
entfernt).

| Datei | Änderung |
|---|---|
| `Settings/UserManagement/UserManagement.tsx:267-271` | `scope="col"` ergänzen |
| `AdminDialog/TriLabelOverviewDialog.tsx:80-85` | `scope="col"` ergänzen |
| `SplitView.tsx:610-620` | Trefferfläche ≥ 24 px (Padding/Pseudo-Element), visuelle Breite bleibt 4–12 px; `aria-valuenow`/`aria-valuemin`/`aria-valuemax` am Separator |
| `frontend/src/components/**/*.test.tsx` | Regressions-Test mit **mehrzeilenfestem** Scan (`rg -U '<th[^>]*>'` bzw. JSX-Parse), nicht Zeilen-Grep; Divider-Hitbox ≥ 24 px |

**Tests:** Component-Tests + mehrzeilenfester DOM-Check; E2E optional.

**DoD:** Kein `<th>` ohne `scope` mehr (mehrzeilenfest geprüft); Divider per Maus und Tastatur
mit ≥ 24 px Trefferfläche bedienbar.

---

## 5. C4 — Verifizieren, Schließen, Release

### C4-T1 — Bereits gefixt: prüfen und schließen

| Issue | Beleg | Aktion |
|---|---|---|
| #1660 | Selbst-Parent-Guard `architecture_service.py:302-311` + Commit `b5dc889d` | Test nennen, schließen |
| #1661 | `icd_manager.py:493` + `test_icd_views.py:85` | schließen |
| #1663 | `mcp_server/tools/base.py:479-488` + `test_tool_error_mapping.py` | schließen |
| #1381 | `test_soft_delete_contract_1381.py` (200 + `outdated` über alle Typen) | schließen |
| #1386 | `application/local_uid.py:169-218` (pre_save-Signal) + Embedding-after-Commit | schließen, optional Backfill-Kommandos für Altbestand nennen |
| #1662 | `VERSION` und `frontend/package.json` = `1.8.0-beta.28` | schließen |
| #1741 | `docker-compose.yml:295,590` Digest-Pins | schließen |
| #1378 | Sampling **vor** Embedding + 25-s-Budget (`memory_admin_service.py:617-620`) | schließen |
| #1410 | `audit_orphan_artifacts` mit `--apply` (`:9-14,47-55`) | schließen, Runbook-Eintrag |
| #1408 | reiner Zählbericht; Drift-Test `test_tool_manifest_drift.py` existiert | als „kein Defekt" kommentieren und schließen |
| #1418 | BluePencil im Repo entfernt (`1ad7ef17`) | als moot schließen |

Jeder Kommentar enthält Datei:Zeile + Testname. Kein Issue wird ohne Beleg geschlossen.

### C4-T2 — Weitere Kandidaten (nur mit Nachweis)

`#1400`, `#1402`, `#1403` (Commit `707b6c1b` „cascade workspace deletes"), `#1409`
(by design, dokumentiert), `#1412` (`baseline/models.py:232-234` nutzt `NULL`, Interview-FK ist
CASCADE), `#1668` (nach C3-T4), `#1731` (nach C2-T3).
`#1399`/`#1411` erst nach der EXPLAIN-Messung aus C5-T4 schließen oder mit Befund öffnen.
`#1404`: `npm audit --omit=dev` mit dem aktuellen Lockfile neu messen (mermaid ist bereits
`^12.2.0`); danach schließen oder den verbleibenden Low-Befund präzisieren.
`#1247` bleibt offen, Kommentar mit Verweis auf §12.

### C4-T3 — Release

1. `python scripts/bump_version.py --version 1.8.0-beta.29`
2. `python scripts/check_plugin_packages.py --expect-version 1.8.0-beta.29` (Drift-Gate)
3. Release Notes mit den Breaking-/Verhaltensänderungen:
   - **#1707**: `severity` ist jetzt schreibbar; `automation`-Policy lehnt abweichende Werte ab.
   - **#1739**: neuer Endpoint; Passwortwechsel invalidiert fremde Sessions.
   - **C2-T4/N21**: Passwort-Policy gilt jetzt auch bei nutzergetriebener Benutzeranlage.
   - **C2-T5**: Login-Response enthält standardmäßig keinen `token` mehr; Rückfall
     `AUTH_LOGIN_INCLUDE_BODY_TOKEN=True`, API-Clients nutzen Cookie oder `X-API-Key`.
   - **Compose**: neue Env-Variablen (`BACKEND_MEM_LIMIT`, `CELERY_MEM_LIMIT`,
     `HONCHO_LLM_*`, `POSTGRES_SHM_SIZE`, `TZ`) mit Defaults; `TZ` ändert nur die Darstellung.
   - **C6**: OpenCode 2 nutzt jetzt `/mcp/` (Streamable HTTP) statt `/mcp/sse/`; V1 bleibt
     je nach belegtem Spike auf `/mcp/` oder `/mcp/sse/` — der konfigurierte URL-Wert kann sich
     ändern (bedingte Release-Note).
4. Labels nachziehen (`bug`, `deploy`, `security`, `clients`).

### C4-T4 — CI-Gates schließen (N22, neu)

**Ursache (verifiziert):** CI hat einen ESLint-Job, aber **keinen** TypeScript-, Django-Check-,
Migrations- oder Compose-Config-Gate: `npm run build`/`tsc --noEmit` laufen nicht, `manage.py
check` und `makemigrations --check` kommen in keiner Workflow-Datei vor.

| Datei | Änderung |
|---|---|
| `frontend/package.json` | Script `"typecheck": "tsc --noEmit -p tsconfig.json"` |
| `.github/workflows/ci.yml` (lint-Job) | `npm run typecheck` + `npm run format:check` (nur wenn der Bestand sauber ist; sonst als separater, nicht-blockierender Job starten und in C4-T5 aufräumen) |
| `.github/workflows/ci.yml` (backend-test) | `python manage.py check` und `python manage.py makemigrations --check --dry-run` als eigene Steps |
| `.github/workflows/ci.yml` | Compose-Config-Gate aus C1-T9 |

**Tests:** Der Workflow selbst ist der Test; ein absichtlich eingebauter Typfehler/Migrationsdrift
muss rot werden (im PR einmal lokal verifizieren).

### C4-T5 — Tote Stub-Module entfernen (N23, neu)

**Ursache (verifiziert):** Fünf Module enthalten ausschließlich TODO-Docstrings und werden
nirgends importiert: `backend/rest_api/models.py` (17 Z.), `backend/rest_api/services.py` (11 Z.),
`backend/mcp_server/models.py` (21 Z.), `backend/mcp_server/services.py` (10 Z.),
`backend/llm_adapter/models.py` (15 Z.). Sie suggerieren nicht existierende Komponenten.

| Datei | Änderung |
|---|---|
| die fünf Dateien | löschen (kein Import im Repo, `grep` belegt) |
| ggf. Architektur-Doku | Verweis auf „geplant" entfernen, falls vorhanden |

**DoD:** `manage.py check` und Testsuite unverändert grün; kein toter TODO-Stub mehr.

---

## 6. C5 — Performance & Daten (eigener PR, in beta.29)

**Ziel:** Kein Schreibpfad blockiert auf dem Embedding-Provider; offene Daten-/Index-Fragen
werden mit Messung statt Vermutung entschieden.

### C5-T1 — #1401 Embedding vollständig aus dem Request-Pfad (N19)

**Ursache (verifiziert):** `create_requirement`/`update_requirement` rufen
`_generate_and_store_embedding` synchron im Request (`requirement_service.py:481,888`); der
Provider-Aufruf läuft in einem Thread mit **3 s** Budget (`:87,1355-1380`). `trace_link.create`
ruft denselben Provider ohne jedes Budget (`trace_link_service.py:662,1096`). Ein Cold-Provider
kostet also weiterhin bis zu 3 s pro Create und unbegrenzt pro TraceLink.

**Vorbild im Repo:** Der ReqIF-Import nutzt bereits `transaction.on_commit` →
`embed_rows_task.delay(...)` mit Broker-Down-Fallback (`reqif_import_service.py:900-920`).

| Datei | Änderung |
|---|---|
| `backend/application/requirement_service.py:481,888` | synchronen Aufruf durch `transaction.on_commit` + `embed_rows_task.delay("requirement", [id], tenant_id)` ersetzen; Broker-Fehler → Warning + `backfill_embeddings`-Hinweis, Create bleibt erfolgreich |
| `backend/application/trace_link_service.py:662` | dito für `TraceLink` (Modell in `EMBEDDABLE_MODELS` prüfen) |
| `backend/application/requirement_service.py:1355-1380` | Thread-/3-s-Budget-Pfad entfernen; die lazy Read-Path-Erzeugung in `find_similar_requirements` bleibt (dort ist sie fachlich nötig) |
| `.env.example` / Doku | Hinweis: Embeddings sind nach dem Create kurz „pending"; `backfill_embeddings --model …` ist der Reparaturweg |

**Tests:** Create ruft den Provider nicht mehr im Request (Mock: `delay` statt
`generate_embedding_with_model`); Task wird erst nach Commit enqueued (kein Enqueue bei
`set_rollback(True)`); Broker down → 201 + Warnung; `find_similar` funktioniert für ein frisch
erstelltes Requirement (lazy).

**Risiko:** Kurzes Fenster ohne Embedding; Suche/Semantik sind bereits lazy-fähig (bestehender
Fallback). Release-Note.

---

### C5-T2 — #1412 Daten normalisieren: `''` → `NULL`

**Ursache (verifiziert):** `BaselineGateWaiver.scope_artifact_id` ist inzwischen
`null=True, default=None` (`baseline/models.py:232-234`); Altzeilen mit `''` können aber noch
existieren. `InterviewSession.artifact` ist ein nullable `OneToOneField` mit CASCADE
(`persistence/models.py:3354-3361`) — echte Orphans sind damit ausgeschlossen, „artifact-lose"
Multi-Mode-Sessions sind by design.

| Datei | Änderung |
|---|---|
| `backend/baseline/migrations/00XX_normalise_waiver_scope.py` (neu, falls Alt-`''` vorhanden) | `UPDATE … SET scope_artifact_id = NULL WHERE scope_artifact_id = ''` + CheckConstraint `scope_artifact_id IS NULL OR scope_artifact_id <> ''` |
| `backend/baseline/tests/` | Constraint-Test; Report-Query für den Altbestand |

**Vorgehen:** Erst `SELECT count(*) … WHERE scope_artifact_id = ''` im QA-Gate. Ist der Wert 0,
nur die Constraint-Migration (verhindert Rückfall); sonst Cleanup + Constraint in einer Migration.

**DoD:** Kein leerer String mehr in einer nullable Scope-Spalte; Issue #1412 belegbar schließen.

---

### C5-T3 — #1410 Orphan-Hygiene als dokumentierter Ops-Schritt

**Ursache (verifiziert):** `audit_orphan_artifacts` existiert bereits inklusive `--apply`
(Soft-Delete) — #1410 ist damit gefixt, aber der Report ist nirgends im Betriebs-Runbook
verlinkt, sodass die 105 Orphans aus dem QA-Lauf weiter auffallen.

| Datei | Änderung |
|---|---|
| `deploy/README.md` | Abschnitt „Datenhygiene": `manage.py audit_orphan_artifacts` (Dry-Run) → Review → `--apply`; Hinweis auf `repair_architecture_cycles` und `repair_icd_contract_lists` |
| optional: `audit_orphan_artifacts.py` | `--json` für automatisierte Auswertung |

**DoD:** Ein Betreiber findet den Bereinigungsweg ohne Code-Lesen; Issue #1410 geschlossen.

---

### C5-T4 — #1399/#1411 nur mit EXPLAIN entscheiden

**Status (verifiziert):** Der FTS-Query-Ausdruck stimmt mit dem Index-Ausdruck überein
(`search_service.py:1206-1213` vs. `0002_fulltext_indexes.py:32-34`); `idx_scan=0` bei ~1.900
Zeilen ist auch bei korrektem Index plausibel. Für HNSW gilt dasselbe (`enable_iterative_ann_scan`
setzt `ef_search`, `pgvector_ann.py:40-70`).

| Schritt | Aktion |
|---|---|
| 1 | Auf einer prod-nahen DB (`EXPLAIN (ANALYZE, BUFFERS)`) die FTS- und ANN-Query ausführen |
| 2 | Zeigt der Plan Seq Scan **und** die Laufzeit ist relevant → Index/Query anpassen (eigener Task) |
| 3 | Andernfalls: Befund als „kein Defekt bei aktueller Datenmenge" dokumentieren und Issue schließen |

**DoD:** Keine spekulative Index-Änderung; Entscheidung ist mit einem EXPLAIN-Plan belegt.

---

## 7. C6 — Clients/OpenCode 2 (eigener PR, in beta.29)

**Ziel:** Der ausgelieferte OpenCode-Client verbindet sich mit OpenCode 1 **und** 2, und die
Verteilung ist in CI abgedeckt.

### C6-T1 — #1702 Installer/Snippet auf `/mcp/` umstellen

**Ursache (verifiziert, korrigiert nach R-04):** Der Builder erzeugt für V2 bereits `/mcp/`
(`dist/opencode/build_opencode_package.py:77,100`), aber Installer und Snippet nutzen weiterhin
SSE: `scripts/clients/install.sh:218,336`, `dist/opencode/opencode.json.snippet:5`,
`dist/opencode/build_opencode_package.py:287` (V1-Block). Der Registry-Eintrag **opencode** ist
`clients/registry.yaml:314-320` (`transport: sse`, `url_path: /mcp/sse/`, `tested_version: 1.19.5`);
`:149-150` gehört zu **claude-code** und darf nicht angefasst werden.

**Beweislage:** Der in #1702 dokumentierte Spike (V1 1.18.35 verbindet auf `/mcp/`) liegt nicht
im Repo, und der Builder-Kommentar sagt heute „V1 spricht SSE"
(`build_opencode_package.py:101-104`). Deshalb wird die Umstellung mit einem reproduzierbaren
Nachweis im selben PR belegt (R-04).

| Datei | Änderung |
|---|---|
| `docs/clients/opencode-transport.md` (neu) | Spike-Matrix aus #1702 als Artefakt (V1/V2 × `/mcp/` vs. `/mcp/sse/`) + Aussage „V1 nutzt SSE nur als Fallback" |
| `scripts/clients/install.sh:218,336` | `opencode mcp add … --url "$URL/mcp/"` |
| `dist/opencode/opencode.json.snippet` | V1-Form `mcp.reqogniloom` mit `/mcp/` |
| `dist/opencode/build_opencode_package.py:101-104,287` | V1-Zweig ebenfalls `/mcp/`; den Kommentar „V1 spricht SSE" korrigieren |
| `clients/registry.yaml:314-320` (opencode) | `transport: streamable_http`, `url_path: /mcp/`; `tested_version` an den Spike anpassen (nicht frei erfinden) |
| `docs/clients/opencode*.md` | neu rendern (`scripts/clients/render.py`) |
| `dist/opencode/tests/test_build_opencode_package.py` | URL-Assertion auf `/mcp/` |

**Tests:** `python -m pytest dist/opencode/tests scripts/clients` + `bash -n` der Skripte;
`dist/test_mcp_convention_parity.py`; ein Verify-Schritt gegen den lokalen Mock-Server für
**beide** Binaries (`opencode`/`opencode2`).

**Fallback:** Lässt sich der V1-Betrieb auf `/mcp/` nicht reproduzieren, bleibt der V1-Zweig auf
`/mcp/sse/` und der Installer wählt den Transport versionsabhängig — der V2-Zweig geht in jedem
Fall auf `/mcp/`.

**DoD:** `opencode mcp add` schreibt für V2 `/mcp/`; V1 und V2 listen den Server als connected;
der Spike-Nachweis liegt im Repo.

---

### C6-T2 — #1706 `subagent_depth` sauber einordnen

**Ursache (laut Issue):** Das Root-`opencode.json` enthält `subagent_depth` (V1-only); V2
meldet „unsupported legacy setting". Die Datei stammt vermutlich aus `.agent-meta/opencode.json`
(Submodul — **nicht hier editieren**, siehe Submodule-Schutz).

| Schritt | Aktion |
|---|---|
| 1 | Herkunft bestätigen (Diff Root-Datei vs. `.agent-meta/opencode.json`) |
| 2 | Upstream-Issue in agent-meta anlegen/verlinken; `subagent_depth` dort entfernen lassen |
| 3 | Bis dahin: Warnung in `docs/clients/` als bekannt dokumentieren |
| 4 | Prüfen, ob weitere V1-only Keys betroffen sind (Permissions-Shape) |

**DoD:** Kein stiller „unsupported"-Warning mehr, oder ein verlinktes Upstream-Issue + Doku.

---

### C6-T3 — #1705 CI-/Doku-Abdeckung für OpenCode 2

**Ursache (verifiziert, korrigiert nach R-12):** `client-smoke.yml` ist ein **DRAFT**,
`workflow_dispatch`-only, und provisioniert **keine** Client-Binaries (Kommentar `:10-13`). Die
V2-Matrix-Leg existiert bereits (`:46-48`), läuft aber mit `continue-on-error: true` (`:37`).
Es fehlt also nicht die Stufe, sondern die Provisionierung und die blockierende Schaltung.

| Datei | Änderung |
|---|---|
| `.github/workflows/client-smoke.yml` | Node-Setup + `npm i -g @opencode/cli@<pin>` (und ggf. den V1-Pin); V2-Leg auf `continue-on-error: false` stellen, sobald der Lauf stabil ist; V2-Neustart-Quirk (`--standalone` oder Service-Restart) dokumentieren |
| `clients/registry.yaml` + gerenderte Docs | V2-Bins (`opencode`, `opencode2`), Hintergrund-Service, Windows nicht unterstützt |
| `.github/workflows/release-client-artifacts.yml` | Tarball-Inhalt gegen V2 prüfen (Config + Skills, kein Plugin-Code) |
| Issue #1705 | Kommentar: „Leg existiert, Provisionierung/Blockierung fehlt" — Beschreibung korrigieren |

**Nicht in diesem PR:** #1703 (Test gegen echten `/mcp/`-Endpunkt) und #1704 (Code-Mode-Messung)
brauchen eine laufende Instanz bzw. Messaufbau — bleiben als Follow-ups offen.

**DoD:** Smoke-Matrix grün für 1.18.x und 2.2.x, mit provisionierten Binaries und ohne
`continue-on-error` für V2; Registry/Docs nennen beide Versionen.

---

## 8. QA-/Abnahme-Matrix (frischer Stack aus `.env.example`, Vollausbau)

| # | Prüfung | Erwartung |
|---|---|---|
| 1 | Viewer `GET /api/v1/api-keys/` | 200, nur eigene Keys; fremde `pk` → 404 |
| 2 | `PATCH /architecture/<id>/` mit eigener `parent_id` | 400, Baum bleibt lesbar |
| 3 | Doppeltes ICD | 409 |
| 4 | `POST /risks/` mit `severity:"high"` | 201, Lesen liefert `high`; PATCH ohne `severity` ändert nichts |
| 5 | ICD mit Parameter-Objekt in `preconditions` | Detailseite rendert, keine Error-Boundary |
| 6 | `MCP_RATE_LIMIT_KEY=abc` | `manage.py check` meldet `rest_api.E001`; Request → 503, kein 500 |
| 7 | Passwortwechsel UI/REST/CLI | 204; andere Sessions 401; aktuelle bleibt; API-Key-Aufrufer → 403 |
| 8 | Editor ändert **oder löscht** Artefakt mit Item-Regel `read` | 403 (REST + MCP) |
| 9 | `docker stats` unter Migrations-/Derivation-Last | unter `BACKEND_MEM_LIMIT`/`CELERY_MEM_LIMIT`/`MIGRATE_MEM_LIMIT` |
| 10 | `docker inspect` | `shm_size=256MB`, `TZ` gesetzt, alle **15** Services mit Log-Rotation (4 zuvor ohne) |
| 11 | `docker compose --profile honcho config` | neun Pins = `HONCHO_LLM_MODEL` |
| 12 | Dialog `/goals` leer + Submit | `role=alert` + `aria-invalid`, Fokus auf Feld |
| 13 | Requirement-Liste Filter „nicht allokiert" | Query enthält `allocated=false`, Anzahl stimmt |
| 14 | `docker compose config -q` für Base, Minimal und Base+TLS-Overlay | alle drei Aufrufe grün |
| 15 | `.env.example`-Drift-Skript | exit 0; ein künstlich entfernter Key → exit 1 |
| 16 | `POST /users/` mit `password123` | 400 (Django-Validator), starkes Passwort → 201 |
| 17 | `POST /requirements/` mit kaltem Provider | Antwort < 1 s; Embedding-Task enqueued, nicht im Request |
| 18 | Alle Tabellen im UI | mehrzeilenfest geprüft: kein `<th>` ohne `scope`; Divider ≥ 24 px Trefferfläche |
| 19 | `opencode mcp add` mit dem Installer | V2 endet auf `/mcp/`; V1 je nach belegtem Spike `/mcp/` oder `/mcp/sse/`; beide „connected" |
| 20 | `manage.py audit_orphan_artifacts` (Dry-Run) | Report läuft, `--apply` nur nach Review |
| 21 | `POST /auth/login/` | Response ohne `token`; SPA-Login und E2E-Suite grün |

Zusätzlich: `make test-backend`, `make test-frontend`, `npx playwright test` (4 Shards),
`npm run typecheck`, `python manage.py check`, `makemigrations --check --dry-run`,
`python scripts/check_env_example_keys.py`.

---

## 9. Threat Model — die 4 Fragen (R-20)

### C2-T1 Passwortwechsel

1. **Was baust du?** Einen authentifizierten Endpoint, der das Account-Passwort ändert und
   Refresh-Sessions anderer Geräte widerruft. Fläche: jede Session (Cookie oder Bearer) sowie —
   ohne Gate — jeder API-Key.
2. **Was könnte schiefgehen?** (a) Ein gestohlener API-Key oder eine Read-Scope-Session setzt ein
   neues Passwort und übernimmt das Konto. (b) Ein Aufrufer nimmt eine fremde `sid` aus dem Body
   und verhindert deren Widerruf. (c) Brute-Force des aktuellen Passworts über eine gestohlene
   Session. (d) Die neue `SECURITY DEFINER`-Funktion läuft als Superuser oder mit offenem
   `search_path`.
3. **Was tust du dagegen?** Gate `auth_method != "api_key"` und `"pwd" in ctx.amr`; `sid`
   ausschließlich aus dem validierten `reqogniloom_refresh`-Cookie, nie aus dem Body;
   per-User-Throttle wie Login; `check_password` (konstantzeitig); Definer-Funktion mit fixem
   `search_path`, `OWNER TO DEFINER_DB_ROLE`, `REVOKE PUBLIC`, Owner-/Inventar-Guard (`#1180`).
4. **Konsequenzen bei Versagen:** Vollständige Account-Übernahme bzw. ein stiller
   Rechte-Eskalationspfad. Deshalb ist C2-T1 der höchste Prio-Task und braucht die
   Negativtests aus dem Testabschnitt.

### C2-T2 ItemPermission auf Schreibpfaden

1. **Was baust du?** Eine zweite Autorisierungsschicht auf Update- **und** Delete-Pfaden von acht
   Artefakttypen (REST + MCP).
2. **Was könnte schiefgehen?** (a) Ein `read`-Nutzer löscht das Artefakt, weil nur Update
   geschützt ist. (b) Ein 403 verrät die Existenz eines versteckten Artefakts. (c) Der Guard
   greift nicht bei `glossary.update`/`update_test_status` (Methodenname passt nicht zum Präfix).
   (d) Ein zusätzlicher Query pro Schreiben macht Bulk-Operationen langsam.
3. **Was tust du dagegen?** Explizite Methodenliste (kein Präfix-Matching); `deny`/`none` → 404,
   `read` → 403; `check_permission` direkt statt gemergtem Ergebnis; gecachter Lookup; Matrix-Test
   je Typ für Update **und** Delete.
4. **Konsequenzen bei Versagen:** Ein per Item-Regel gesperrtes Artefakt bleibt über einen
   Nebenweg änderbar/löschbar — die Defense-in-Depth-Zusage wäre unwahr.

### C2-T4 Passwort-Policy / C2-T5 Token-Default

1. **Was baust du?** Validator-Aufrufe bei nutzergetriebener Anlage/Änderung; Abschalten des
   Body-Tokens im Login-Response.
2. **Was könnte schiefgehen?** (a) Der Betreiber-Bootstrap bricht, weil ein Disaster-Recovery-
   Passwort die Validatoren nicht erfüllt. (b) Bestehende schwache Passwörter sperren Nutzer aus
   (passiert **nicht**, weil nur Anlage/Änderung geprüft wird). (c) Externe API-Clients brechen
   nach dem Token-Flip. (d) E2E-Helper umgehen CSRF und werden still falsch-grün.
3. **Was tust du dagegen?** `provision_admin` bewusst ausnehmen und begründen; Login unverändert;
   Opt-in `AUTH_LOGIN_INCLUDE_BODY_TOKEN=True` + Release-Note; E2E-Migration mit CSRF-Helper und
   Grep-Gate (kein `getAuthToken`/`Authorization: Bearer` mehr).
4. **Konsequenzen bei Versagen:** Entweder ein Lockout des Betreibers oder ein gebrochener
   API-Client — beides vermeidbar durch die dokumentierte Ausnahme bzw. den Rückfall-Schalter.

### C1-T8 TLS-Betrieb

1. **Was baust du?** Eine dokumentierte, overlay-basierte TLS-Terminierung vor API und Frontend.
2. **Was könnte schiefgehen?** Falsche Cookie-Flags (`Secure` über HTTP → Login-Loop),
   fehlende `CSRF_TRUSTED_ORIGINS` (403), oder `SECURE_SSL_REDIRECT` ohne Proxy
   (Redirect-Deadlock).
3. **Was tust du dagegen?** Flag-Matrix im README, `SECURE_PROXY_SSL_HEADER` nur bei
   `SECURE_SSL_REDIRECT` (bereits implementiert), `X-Forwarded-Proto` im Caddy-Beispiel,
   Compose-Config-Test. Semantik prüft Compose nicht — deshalb Doku + QA-Matrix.
4. **Konsequenzen bei Versagen:** Klartext-Credentials oder eine unbenutzbare UI. Beides ist ein
   Betriebs-, kein Codefehler — die Doku ist die Gegenmaßnahme.

---

## 10. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| #1716 zentraler Guard deny-t zu viel | Editoren verlieren Schreib- **und** Löschrechte | nur explizite Item-Regeln greifen; Matrix-Tests für Update + Delete; Release-Note |
| #1739 neue `SECURITY DEFINER`-Funktion | RLS-/Posture-/Owner-Regression | Definer-Owner-Guard `test_definer_owner_role_1180.py` **und** Posture-Test `test_refresh_token_rls_1182.py` erweitern; `OWNER TO` + `REVOKE PUBLIC` in der Migration |
| #1739 API-Key/Read-Scope | Kontoübernahme über gestohlenen Key | Gate `auth_method != "api_key"` + `"pwd" in ctx.amr`; `sid` nur aus dem Token |
| #1707 Attribut-Umzug | Verlust manueller Werte | Dry-Run-Command + Report vor `--apply`; Ableitung nur bei `severity is None` |
| #1735 höhere Limits | OOM auf kleinen VMs | parametrisiert, Defaults dokumentiert, kleine VM bewusst niedriger; `migrate` separat |
| #1738 Fehlkonfiguration | bestehende Instanz meldet `E001` statt zu booten | System-Check als Gate, kein Import-Crash; 503-Fallback im Request-Pfad |
| Compose-Anker (`TZ`) | `environment:` wird überschrieben | `docker compose config`-Test für Base/Minimal/TLS-Overlay |
| #1709 Datenreparatur | falsche Objekte in Altbestand | Dry-Run, Audit-Log, idempotent |
| C5-T1 asynchrones Embedding | kurzes Fenster ohne Vektor | lazy Read-Path bleibt; `backfill_embeddings` als Reparaturweg |
| C2-T4 Passwort-Policy | Betreiber-Bootstrap mit schwachem ENV-Passwort | `provision_admin` bewusst ausgenommen und begründet; Login unverändert |
| C6-T1 URL-Wechsel | bestehende OpenCode-Configs zeigen auf SSE | Spike-Nachweis im Repo; V2 sicher auf `/mcp/`, V1 mit belegtem Fallback |
| C2-T5 Token-Default | externe API-Clients brechen; E2E-Drift | Opt-in `AUTH_LOGIN_INCLUDE_BODY_TOKEN=True`; E2E-Migration mit CSRF + Grep-Gate; Release-Note |

---

## 11. Reihenfolge / Merge-Queue

1. **Phase 0** (0,5 d): frischen Stack aus `.env.example` starten, alle Befunde
   reproduzieren; Ergebnisse in die Issues als Kommentar (verhindert „schon gefixt"-Überraschungen).
2. **C1** (unabhängig) → merge.
3. **C2** (Auth zuerst, dann Permissions) → merge.
4. **C3** (nach C2, weil #1707 Attribut-Änderungen und C2 die Feldvalidierung anfasst) → merge.
5. **C5** und **C6** mergen (parallel zu C2/C3 entwickelbar).
6. **C4**: Issues schließen und QA-Matrix abarbeiten; **erst danach** Version bumpen/Tag setzen
   und Release Notes schreiben — der Bump ist der letzte Schritt, damit C5/C6 im selben
   Release-Artefakt sind.

Jeder Branch wird auf den vorherigen rebased; kein direkter Commit auf `main`.

---

## 12. Nicht im Scope

| Thema | Grund |
|---|---|
| #1247 Honcho `memory.ask` | Upstream-Pfad, nicht reproduzierbar ohne Live-Stack; separater Investigate-Task mit Timebox |
| #1669 / #1670 Spezifikationsebene & Allokation | Datenmodell-/Design-Änderung, eigenes Feature-Release |
| #1701, #1703, #1704 | Hermes-Plugin bzw. Messungen gegen eine echte Instanz — #1702/#1705/#1706 sind in C6 |
| #1564 Typed TestCase Steps | Feature |
| #1578 Auto-Assessment, #1374 Dokument-Workflow, #946 Debug-Layer, #801 Inspector, #1094 Workspace-ID-UI | Features, kein Bugfix |
| ItemPermission auf Retrieve/List | Follow-up-Issue aus C2-T2 |
| Generische Computed-Fields-Engine | #1707 liefert nur die `automation`-Vorstufe |
| #1399/#1411 Code-Fix | erst nach EXPLAIN-Messung (C5-T4); keine spekulative Index-Änderung |

---

## 13. Review-Protokoll (konsolidiert)

### 13.1 Ablauf

| Runde | Datum | Reviewer | Verdikt | Ergebnis |
|---|---|---|---|---|
| 1 — Voll-Review | 2026-11-08 | `concept-reviewer` | `CHANGES_REQUESTED` | 3 Blocker, 12 Major, 7 Minor, 3 Info |
| 2 — Delta | 2026-11-08 | `concept-reviewer` | `CHANGES_REQUESTED` | 17/22 behoben; R-01/R-02/R-03/R-07 offen, N-01…N-06 neu |
| 3 — Kurz-Delta | 2026-11-08 | `concept-reviewer` | **`APPROVED with minor fixes`** | Kein Blocker/Major; 4 Präzisierungen eingearbeitet |

Geprüft wurden alle `datei:zeile`-Angaben, die Cluster-Logik, Vollständigkeit (Tests/DoD/
Rollback/Migrationen), Feasibility, Widersprüche, Merge-Reihenfolge und das Threat Model.

### 13.2 Findings R-01…R-22 (alle eingearbeitet)

| ID | Sev. | Befund (geprüft) | Auflösung im Plan |
|---|---|---|---|
| R-01 | blocker | C2-T5 um Größenordnung unterschätzt: 147 `getAuthToken`-Stellen in 42 Spec-Dateien; CSRF im Cookie-Pfad fehlt | C2-T5: 2,0 d, CSRF-Helper, Grep-Gate, Bearer-Spec ersetzt, Opt-in-Assertion im Backend-Test |
| R-02 | blocker | C3-T1 ohne `rest_api/views.py` (dort wird `severity` verworfen) und ohne Bedingung in `risk_service.py:271/:415` | C3-T1: beide View-Aufrufe, Echo-Mechanismus über `get_risk`, bedingte Ableitung |
| R-03 | blocker | Keine Quelle für die aktuelle `sid`: Access-Token hat sie nicht, `AuthContext` auch nicht; Definer-Owner-Vertrag fehlt | C2-T1: `sid` aus dem `reqogniloom_refresh`-Cookie, `read_refresh_session_id()`, Bearer-Fallback, `OWNER TO`/`REVOKE`/Guards |
| R-04 | major | Registry-Referenz zeigt auf Claude Code; V1→`/mcp/` unbelegt | C6-T1: OpenCode `:314-320`, Beweis-Dokument, V1-Fallback |
| R-05 | major | `honcho-migrate` fehlt in der Log-Inventur; Zahlen falsch | C1-T5: 4 von 15 Services, Test über alle Services |
| R-06 | major | Minimal `:84` ist Redis, nicht Backend; `migrate` fehlt | C1-T1/T9: Backend `:123`, `MIGRATE_MEM_LIMIT` |
| R-07 | major | `<th>`-Bestand veraltet; genannte Tabellen sind bereits korrekt | C3-T5: 11 echte Offender, mehrzeilenfester Scan |
| R-08 | major | `provision_admin` umgeht den Validator; DoD falsch | C2-T4: bewusste Betreiber-Ausnahme, DoD präzisiert |
| R-09 | major | Fail-fast im Settings-Import widerspricht System-Check/503 | C1-T4: ein Mechanismus (tolerante Settings + `E001` + 503) |
| R-10 | major | „alle 8 Typen" verfehlt `glossary.update`/`update_test_status`; Delete offen | C2-T2: explizite Methodenliste, Delete im Guard |
| R-11 | major | Glob trifft Overlays; Release-Kommando existiert nicht | C1-T10: explizite Trägerliste + Guard-Test; `check_plugin_packages.py` |
| R-12 | major | `client-smoke` ist Draft; V2-Leg existiert bereits | C6-T3: Provisionierung/Blockierung statt „Leg fehlt" |
| R-13 | minor | `SECURE_SSL_REDIRECT` doppelt | C1-T3: 13 Keys + Verweis, Doppeldefinitions-Check |
| R-14 | minor | Zählung 20 vs. 17/18 | C3-T3: 18 Dateien, `CsvImport` als Ausnahme |
| R-15 | minor | TLS-Datei ohne definierte Rolle | C1-T8: Overlay + Zwei-Datei-Test |
| R-16 | minor | `default` entfernen macht Feld `required` | C3-T1: `required=False`, kein `default` |
| R-17 | minor | `derivation_status` kann keinen Provider-Text tragen | C1-T2: Status-Mapping statt Text-Matching |
| R-18 | minor | Zeilen-/Datei-Drift an mehreren Stellen | Korrigiert (u. a. `baseline/models.py:232-234`, `serializers.py:3547`, keine `api/auth.ts`) |
| R-19 | minor | Querverweise/Zählungen in C4 | `#1400/#1402/#1403`, Trace `C2-T4/N21`, 15 Services |
| R-20 | info | Threat Model fehlt | §9 mit den 4 Fragen je Sicherheits-Task |
| R-21 | info | C3-T3 ist Refactoring-Umfang | Scope-Hinweis: 6 Kern-Dialoge zuerst |
| R-22 | info | Mehrere Angaben UNVERIFIED | §0.5 trennt belegt/nicht reproduziert |

### 13.3 Delta-Findings N-01…N-06 (alle eingearbeitet)

| ID | Sev. | Befund | Auflösung |
|---|---|---|---|
| N-01 | minor | „94 `<th`" war ein Substring-Zähler | 77 `<th>` + 17 `<thead>`, 62 mit `scope`, 11 ohne |
| N-02 | minor | 13 vs. 14 Settings-Keys, `LLM_SYNC_TIMEOUT` doppelt | 13 Keys + `COMPOSE_PROFILES`, Duplikat entfernt |
| N-03 | minor | QA #14/#19 und Release-Note widersprechen Overlay/V1-Fallback | QA und Release-Note konditional formuliert |
| N-04 | minor | Test nennt `celery` in der Minimal-Compose | Test pro Datei über vorhandene Langläufer |
| N-05 | minor | C2-Summe nicht nachrechenbar | Task-Aufwände ausgewiesen (5,0 d), Gesamt 14,0 d |
| N-06 | info | Merge-Queue bumpt vor C5/C6 | C5/C6 mergen vor Bump/Tag |

### 13.4 Kurz-Delta-Präzisierungen (eingearbeitet)

- **R-07:** „15 ohne" → **11** echte Offender; `MatrixRenderer`/`CsvImport` sind Falsch-Positive (scope auf Folgezeile).
- **R-03:** `read_refresh_session_id` ruft zuerst `validate_refresh_token` (bzw. prüft `typ == "refresh"`); `read_refresh_amr` allein validiert nicht.
- **R-02:** „Echo toleriert" ist aus `field_validation.py` entfernt; der View filtert per Ist-Wert-Vergleich.
- **R-01:** Opt-in-Assertion liegt in `test_login_body_token_deprecation_696.py:83-94` und braucht nach dem Flip ein explizites `@override_settings(AUTH_LOGIN_INCLUDE_BODY_TOKEN=True)`.

### 13.5 Bewusst akzeptiert / offen

- **R-21:** C3-T3 bleibt der einzige Refactoring-Task; bei engem Fenster zuerst die sechs Kern-Dialoge.
- **R-22:** Speicher-Messwerte (968 MiB/744 MiB) und EXPLAIN-Aussagen sind Issue-/Phase-0-abhängig; die Commit-SHAs wurden lokal verifiziert.
- **#1247**, **#1669/#1670**, **#1703/#1704** und die Feature-Issues bleiben außerhalb dieses Releases (§12).
