---
type: PLAN
title: "Deep-Dive 2026-11-16 — Remediation in 24 Schnitten (S0–S6)"
status: proposed
date: 2026-11-16
author_agent: planner
language: de
audit: "docs/audit/2026-11-16-deep-dive-findings.md"
branch_basis: "origin/main d097ef06 · Audit-Branch docs/deep-dive-audit (PR #1891)"
pipeline_stages:
  implement: 1
---

# Deep-Dive-Remediation — Umsetzungsplan

**Ziel:** Die **186 Findings** aus
[`docs/audit/2026-11-16-deep-dive-findings.md`](../../audit/2026-11-16-deep-dive-findings.md)
in überprüfbare, einzeln mergebare Schnitte überführen — Sicherheits- und Datenintegritätsrisiken
zuerst, danach Verträge, Struktur, Testqualität und Doku. Jeder Schnitt liefert **Code + Regressionstest +
Doku-Update**; kein Schnitt ist ein „Refactoring ohne Befund".

**Leitlinie (unser Vorgehen):**
1. **Ein Schnitt = ein PR** auf `feat/*`/`fix/*`/`docs/*`, nie direkt auf `main`.
2. **Ein Finding ohne Regressionstest gilt als nicht behoben.** Jeder Schnitt nennt den Test, der
   vorher rot und nachher grün ist (bzw. den Guard, der den Zustand dauerhaft hält).
3. **Keine Drive-by-Änderungen.** Wer beim Fix ein neues Problem findet, legt ein Finding/Issue an,
   statt es im selben PR mitzunehmen (Ausnahme: der Fix ist ohne die Nebenänderung nicht korrekt).
4. **Risikoreiche Änderungen hinter Flag/Rollout**, mit dokumentiertem Rollback (RLS, Release-Gates,
   History-Rewrite, Schema).
5. **Ratchets und Gates bleiben die Wächter**: bestehende Tests, Drift-Gates, `tsc`, ESLint,
   `check-nginx-headers.sh`, Playwright-Shards dürfen nicht abgeschwächt werden.
6. **Ehrliche Statusführung**: erledigte Findings werden im Audit als `fixed in <commit>` markiert,
   Teilfixes bleiben `Teilweise` mit Restgrund (kein „Done" auf dem Papier).

**Nicht-Ziele:** neue Features; erneuter Audit; vollständiger Rewrite von `views.py` oder der
SplitView; Beseitigung aller technischen Schuld (Ratchets bleiben inkrementell); Lizenzwechsel
ohne Rechtsprüfung; Performance-Optimierung ohne Messung.

**Grundlage:** Pass 1 (Korrektheit/Sicherheit/Performance/Doku, 126 Findings) und Pass 2
(Coding Best Practices + Meta-Review, 60 Findings). Der Meta-Review hat die 12 kritischsten
Pass-1-Findings gegengeprüft: 9 bestätigt, 2 überzeichnet (OPS-001, DEP-001), 1 wahrscheinlich
(AI-001), 0 False Positives. Drei Präzisierungen sind eingearbeitet (DOC-001-Zahl, RLS-Default-
Widerspruch, OPS-001/DEP-001-Ausmaß).

---

## 0. Globale Constraints

- **Layer-Disziplin (ADR-01):** Fixes in `application/` bleiben die einzige Domain-Fassade;
  `rest_api`/`mcp_server` rufen keine Models. Neue Brüche sind ein Finding, kein Muster.
- **Tenant-Isolation (ADR-03):** Jede query-berührende Änderung braucht den Nachweis, dass
  `TenantContext` **und** RLS-GUC gesetzt sind bzw. bewusst `.unscoped` mit Begründung.
- **Keine Rohwerte:** Farben/Größen aus `tokens.css`; neue `@media`-Werte nur als dokumentierte Tokens.
- **i18n:** DE/EN-Schlüssel für jede neue UI-Zeichenkette; keine Literale in Komponenten.
- **`data-testid`** auf neuen interaktiven Elementen (E2E-Pflicht).
- **Tool-Zahl ist ein Gate:** Jede MCP-Änderung zieht `tool-manifest.json` + Drift-Test nach.
- **DB-Migrationen:** expand/contract, rückwärts sicher oder ausdrücklich „one-way" dokumentiert;
  keine Datenverluste im Reverse (L0-002 ist der Präzedenzfall).
- **Doku:** interne Doku Deutsch, Code/Kommentare/Commits Englisch; Status nur in Statusfeldern,
  nicht im Fließtext (DOC-005).

## 1. Schnitt-Übersicht

| # | Schnitt | Findings | Agent | Depends on | Aufwand |
|---|---|---|---|---|---|
| S0.1 | Secret-Incident & Security-Baseline | SEC-001, SEC-003, SEC-004, SEC-005, SEC-006, SEC-007, OPS-003 | security-auditor + devops-engineer | — | 2,5 d |
| S0.2 | Tenant-/RLS-Korrektheit | APP-001, SEC-002, EXT-001, L1-006, EXT-006 | backend-reviewer | S0.1 | 3 d |
| S0.3 | Datenintegrität (Audit, Baseline, Graph) | L0-001, L0-002, L0-003, L1-001…L1-005, L1-007, L1-008 | senior-developer | S0.2 | 3 d |
| S0.4 | Release-Gates & Lock | OPS-001, OPS-002, OPS-004, DEP-001, DEP-002, DEP-004 | devops-engineer | — | 1,5 d |
| S1.1 | REST-Vertrag & Fehlerbild | API-001, API-006, R2A-001, R2A-002, R2A-006…R2A-008 | api-specialist | S0.4 | 2 d |
| S1.2 | MCP-Protokoll & Tool-Vertrag | API-002…API-005, API-007, API-008, R2A-003, R2A-004 | backend-reviewer | S0.4 | 3 d |
| S1.3 | Service-Fail-open & Governance | APP-002…APP-006, EXT-004, EXT-005, EXT-007, EXT-008 | backend-reviewer | S0.2 | 2 d |
| S1.4 | AI-Sicherheit (Injection, Budget, SSRF) | AI-001…AI-007 | ai-security-guardian | S0.2 | 3 d |
| S1.5 | Prompt-/Agent-Assets | R2P-001…R2P-010 | prompt-engineer | S1.4 | 2 d |
| S2.1 | Backend-Performance | PERF-001, PERF-002, PERF-003, PERF-010, PERF-011 | performance-optimizer | S1.3 | 3 d |
| S2.2 | DB-Handwerk & Indizes | PERF-005, PERF-006, PERF-008, PERF-009, R2D-001…R2D-008 | database-engineer | S0.3 | 3 d |
| S2.3 | Frontend-Performance | PERF-004, PERF-007, UI-009, R2F-004, R2F-006 | frontend-reviewer | S3.1 | 2 d |
| S3.1 | Client, Auth, i18n, PWA | FE-001…FE-008, R2F-001, R2F-003, R2F-005, R2F-007, R2F-008 | frontend-component-engineer | S0.4 | 2,5 d |
| S3.2 | Komponenten-Verträge | R2F-002, UI-001, UI-002, UI-003, UI-006 | senior-developer | S3.1 | 3 d |
| S3.3 | Barrierefreiheit | A11Y-001…A11Y-006 | accessibility-specialist | S3.2 | 3 d |
| S3.4 | UI-Design-Schuld | UI-004, UI-005, UI-007, UI-008 | ui-reviewer | S3.2 | 1,5 d |
| S4.1 | Clean Code / SOLID Backend | R2C-001…R2C-009 | refactoring-specialist | S1.3 | 4 d |
| S4.2 | Struktur, Zyklen, Layer | R2S-001…R2S-010 | refactoring-specialist | S4.1 | 6 d |
| S4.3 | Testqualität | TEST-001…TEST-012, R2T-001…R2T-007 | tester | S3.1 | 3 d |
| S5.1 | Supply Chain | DEP-003, DEP-005…DEP-010, EXT-002, EXT-003 | dependency-auditor | S0.4 | 2 d |
| S5.2 | CI/Compose/Ops-Härtung | OPS-005…OPS-011 | devops-engineer | S0.4 | 3 d |
| S5.3 | Betriebsreife (Meta-Lücken) | Meta-Review (keine eigenen IDs) | sre-engineer | S5.2 | 3 d |
| S6.1 | Doku-Wahrheit & Status | DOC-002…DOC-008 | technical-writer | — | 1,5 d |
| S6.2 | SE-/ADR-Lifecycle | DOC-001, DOC-009, DOC-010, DOC-011 | documenter | S6.1 | 2 d |
| S6.3 | Sprach-/Link-Hygiene | DOC-012 | knowledge-gardener | S6.1 | 0,5 d |

**Summe:** ≈ 66 Personentage. Durch die fünf Tracks (Security/Data, Contracts/AI, Perf/DB,
Frontend/Tests, Structure/Ops/Docs) sind **3–4 Kalenderwochen** bei paralleler Besetzung realistisch.
**MVP-Empfehlung:** S0.1–S0.4 + S1.1/S1.2 + S3.1 ≈ 15 Tage; damit sind die P0-Risiken und die
kaputten Release-Gates weg, bevor Strukturarbeit beginnt.

---

## 2. Welle 0 — Sofortmaßnahmen (P0)

### S0.1 Secret-Incident & Security-Baseline
**Findings:** SEC-001 (echte `SECRET_KEY`/`DB_PASSWORD` in der Git-History), SEC-003 (Admin-MFA default `optional`),
SEC-004 (Rate-Limiter fail-open), SEC-005 (DIY-JWT), SEC-006 (Secret-Scan zu eng), SEC-007
(Honcho-Default-Passwort), OPS-003 (gitleaks nur mit `--enable-rule`).
**Ziel:** Kein gültiges Geheimnis mehr in History/Config; der Scan findet künftig auch fremde
Secret-Typen.

- [ ] Incident-Fenster festlegen, betroffene Deployments identifizieren; `SECRET_KEY`,
      `DB_PASSWORD`, abgeleitete Session-/Reset-Tokens rotieren; alle Sessions invalidieren.
- [ ] History-Bereinigung mit `git filter-repo` (oder BFG) auf einem **Spiegel**, Forks/Caches
      informieren, Force-Push nur nach Freigabe; Rotationsnachweis im Incident-Report.
- [ ] gitleaks: zusätzlicher Blocking-Lauf mit Default-Regelsatz (kein `--enable-rule`), Fixtures
      per `[[allowlists]]` mit Begründung; Canary für einen Nicht-`reqlo`-Secret-Typ.
- [ ] `SEC-006`-Rule-Set erweitern; `.env.example`/Compose-Defaults prüfen (`SEC-007`).
- [ ] SEC-003: `MFA_STAFF_ENFORCEMENT=required` in Produktion, Cutover per `mfa_enforce_cutover`.
- [ ] SEC-004: Rate-Limiter bei Redis-Ausfall fail-closed (oder dokumentierter, alarmierter Fallback).
- [ ] SEC-005: DIY-JWT durch etablierte Bibliothek/Claims-Validierung ersetzen **oder** als
      bewusste Entscheidung mit Begründung im Audit schließen.

**Tests/Guards:** Canary-PR mit AWS-/PEM-Muster muss rot werden; History-Scan läuft über `--all`.
**DoD:** Rotation belegt, History bereinigt (oder dokumentiert blockiert), Scan-Canary grün/rot wie
erwartet, Incident-Report in `docs/audit/`.
**Risiko:** History-Rewrite bricht offene Forks/PRs — Zeitfenster und Kommunikation nötig.

### S0.2 Tenant-/RLS-Korrektheit
**Findings:** APP-001 (Sweep setzt nur Thread-Local), SEC-002 (RLS default permissiv),
EXT-001 (Memory-Consent liest ohne RLS), L1-006, EXT-006 (Tenant-Defence-in-Depth).
**Ziel:** Jede Hintergrund-/Service-Query hat beide Isolationsschichten oder einen begründeten
`.unscoped`-Pfad.

- [ ] `quality_auto_assess.run_sweep` analog `artifact_summary_sweep` armen: `set_request_tenant`
      im `try`, Restore im `finally`; Regressionstest prüft die GUC.
- [ ] RLS-Rollout-Entscheidung: `RLS_AS_ENFORCED`/`RLS_PREAUTH_ENFORCED`/`hard_enforced` in
      Produktion aktivieren (Owner-only), Deploy-Compose + `.env.example` nachziehen.
- [ ] `memory/injection_policy.py` auf tenant-gescopte Query umstellen (EXT-001).
- [ ] L1-006/EXT-006: fehlende Tenant-Filter ergänzen, Test mit fremdem Tenant (404/leer).
- [ ] Meta-Präzisierung: alle RLS-abhängigen Findings unter Default-Flags erneut bewerten und im
      Audit als „conditional on rollout" markieren.

**Tests:** Zwei-Tenant-Fixture, Hintergrund-Task-Test mit RLS-Role, Negativtests (fremde ID → 404).
**DoD:** Sweep verarbeitet unter RLS echte Zeilen; kein Service-Pfad ohne Tenant-Arming; Flags
dokumentiert und im Deployment gesetzt.
**Risiko:** RLS-Enforcement kann bestehende Deployments brechen → schrittweiser Rollout mit
Feature-Flag und Monitoring.

### S0.3 Datenintegrität (Audit, Baseline, Graph)
**Findings:** L0-001 (Audit-Retention durch Append-only-Trigger blockiert), L0-002 (Migration-0141-
Reverse löscht alle Allocations), L0-003 (MCP-Audit schluckt Validierungsfehler), L1-001
(Baseline-Reconstructor liefert Live-Stand), L1-002 (Zyklus-Race), L1-003 (Update umgeht Vertrag),
L1-004 (Definitions-Cache ohne Generation), L1-005 (force_transition-Gate), L1-007/008.

- [ ] L0-001: Partition-Drop über echtes DDL oder kontrollierten Maintenance-Pfad; Integrationstest
      gegen migrierte DB (Trigger aktiv).
- [ ] L0-002: Reverse auf backfill-eigene Zeilen begrenzen oder `RunPython.noop` + Guard-Test.
- [ ] L0-003: `write_mcp_audit` re-raised Validierungsfehler; gemeinsame Op-Registry anstreben.
- [ ] L1-001: Baseline-Reconstruction aus `BaselineDeltaIndexEntry.state` zuerst, Live-Fallback nur
      für Legacy; Regressionstest „baseline → edit → alter Titel".
- [ ] L1-002: Graph-Schreibpfade per `pg_advisory_xact_lock` (tenant-scoped) serialisieren;
      Zwei-Thread-Test, der den Zyklus ablehnt.
- [ ] L1-003: gemeinsame Validierung aus `create()` in `update()` wiederverwenden; Level-Recompute.
- [ ] L1-004: Definitions-Cache an die bestehende Cache-Generation koppeln.
- [ ] L1-005/007/008: Gate härten, Coverage-Aggregation korrigieren, Doku-Drift schließen.

**Tests:** Integrations-/Concurrency-Tests, Baseline-Regression, Audit-Retention-Job.
**DoD:** Retention löscht nachweislich; Rollback zerstört keine Fremddaten; Baseline liefert
zeitrichtige Werte; parallele Graph-Writes können keinen Zyklus erzeugen.
**Risiko:** Advisory-Lock erhöht Write-Latenz — Messung vor Rollout.

### S0.4 Release-Gates & Lock
**Findings:** OPS-001 (prod-Healthcheck nutzt fehlendes `curl`), OPS-002 (E2E blockt Publishing
nicht), OPS-004 (`secrets: inherit` zu breit), DEP-001 (`requirements.lock` driftet), DEP-002
(Floor-Gate prüft falsche Konstanten), DEP-004 (nginx-Gate 1.27 vs 1.31).
**Ziel:** Ein Release kann nicht mehr mit rotem E2E, falschem Lock oder ungesundem Container
publiziert werden.

- [ ] Healthcheck auf BusyBox `wget` umstellen oder `curl` installieren; CI-Smoke prüft
      `docker inspect … .State.Health.Status`.
- [ ] `playwright.yml` als reusable Workflow (`workflow_call`) in die Release-Gate-Kette hängen.
- [ ] `secrets: inherit` durch explizite Secret-Map ersetzen.
- [ ] Lock mit dem echten Runtime-Interpreter (3.15) regenerieren; CI-Gate „direct dep floor vs
      lock" + Plattform-Header-Check.
- [ ] `required_floors` aus `requirements.txt` ableiten statt zu duplizieren.
- [ ] nginx-Gate auf das produktive Image (1.31) heben.

**Tests:** Negativ-Canary (roter E2E blockt Publish), Lock-Drift-Test, Healthcheck-Smoke.
**DoD:** Release-Pipeline rot bei jedem der drei Fehlerbilder; Lock konsistent; Healthcheck `healthy`.
**Risiko:** Zusätzliche E2E-Stufe verlängert Releases — Budget/Fail-fast definieren.

---

## 3. Welle 1 — Verträge, Service-Härtung, AI

### S1.1 REST-Vertrag & Fehlerbild
**Findings:** API-001 (500 auf `/transitions/`), API-006 (OpenAPI unvollständig), R2A-001
(Envelope-Drift), R2A-002 (OpenAPI-Version), R2A-005 (Client-Wrapper-Duplikation), R2A-006
(Client-Fehlertypen), R2A-007/008 (Deprecation-Signal, Pagination-Links).
- [ ] API-001: `.unscoped`-Read bzw. Facade-Arming + Fail-open-Enrichment; Regressionstest ohne
      manuell gesetzten Tenant.
- [ ] `COMMON_ERROR_RESPONSES` aus `_STATUS_TO_CODE` ableiten (405/409/412/415/429/503).
- [ ] `request_id` tatsächlich emittieren oder aus der Doku entfernen; Envelope in einem Contract-
      Test über alle Fehlerklassen.
- [ ] OpenAPI-Version aus `VERSION` beziehen; Deprecation-Header/Alias markieren.
- [ ] Client: ein Fehlertyp-Modell, absolute `next`-URLs normalisieren; Pagination-Walker und
      Query-Wrapper zusammenführen (R2A-005).

**DoD:** `/transitions/` liefert 200 bei „proposed"; Schema enthält alle realen Fehlerstatus;
Envelope-Test deckt REST+Client.

### S1.2 MCP-Protokoll & Tool-Vertrag
**Findings:** API-002 (Session-ID in URL/DELETE ohne Bindung), API-003 (Notifications ohne `id`
abgelehnt), API-004 (Transport-Fehler ohne `code`), API-005 (Manifest dedupliziert still),
API-007 (SSE ohne 503-Fallback), API-008 (keine zentrale inputSchema-Validierung), R2A-003/004
(Tool-Naming/Beschreibungen).
- [ ] `Mcp-Session-Id` als Primärkanal, Query-Fallback entfernen; DELETE nur mit gebundener Key.
- [ ] JSON-RPC-Notification-Regel (`method.startswith("notifications/")` → kein `id` nötig).
- [ ] `error.code` in Transport-Envelopes; `error_code` als Alias behalten.
- [ ] `build_manifest` wirft bei Duplikaten; Kollisionstest gegen Rohliste.
- [ ] SSE-Rate-Limit-Fehler als 503; zentrale Schema-Validierung am Dispatch (oder Ratchet).
- [ ] Tool-Naming (`get`/`read`, `list`/`query`) harmonisieren; Beschreibungen generieren/prüfen.

**Tests:** JSON-RPC-Contract-Tests, Session-Binding-Test, Manifest-Kollisionstest.
**DoD:** Standard-MCP-Client (initialize/notifications/tools) läuft ohne Protokollfehler.

### S1.3 Service-Fail-open & Governance
**Findings:** APP-002 (Freeze-Check schluckt Fehler), APP-003 (Change-Reason-Gate fail-open),
APP-004/005/006 (Sortier-/Auswahl-Instabilität), EXT-004 (Restore-Vertrag), EXT-005 (SE-Metrik),
EXT-007 (Resilience-Audit), EXT-008 (Config-Propagation).
- [ ] Freeze-Check: Fehler loggen, „unbekannt" ≠ „nicht gesperrt", fail-closed.
- [ ] Change-Reason: `CrossTenantWorkspaceError` re-raisen, sonst fail-closed + Warnung.
- [ ] Sortierungen mit Unique-Tie-Breaker (`id`), Baseline-Auswahl deterministisch.
- [ ] Restore: `RestoreResult` füllen, echtes Rollback statt Overlay oder Vertrag korrigieren.
- [ ] SE-Metrik: Mandatory-Status korrekt ableiten; Resilience-Audit konkurrenzsicher.
- [ ] Config-Propagation: Änderungen erreichen laufende Worker (Cache-Generation/Signal).

**DoD:** Kein Governance-Gate fällt bei Exception auf „erlaubt"; Sortierung paginierbar stabil.

### S1.4 AI-Sicherheit
**Findings:** AI-001 (Memory-Poisoning), AI-002 (Budget-/Audit-Bypass), AI-003 (SSRF-Lücke env),
AI-004 (keine System/User-Trennung), AI-005 (Modellausgabe im Write-Path), AI-006 (Resume-Fehler),
AI-007 (AI-Lock-Drift).
- [ ] `interaction_text` in Datenblock + „untrusted data"-Direktive; `scope` serverseitig ableiten;
      Längen-/Extraktionslimits.
- [ ] `_call_llm` über den geschützten Pfad (Budget → Audit → Token-Usage → Timeout) führen.
- [ ] `validate_outbound_url` zentral für env- und DB-Quellen; Private-Netze nur per Allowlist.
- [ ] AI-005: Feld-Schema-Validierung vor jedem Write; unbekannte Felder verwerfen/ablehnen.
- [ ] AI-006/007: Resume-Fehler degradieren sauber; Lock konsistent halten.

**Tests:** Prompt-Injection-Fixture, Budget-Bypass-Test, SSRF-Test gegen env-URL, Schema-Reject-Test.
**DoD:** Ein präparierter Chat-Turn kann keine dauerhafte Anweisung im Memory verankern; kein Call
ohne Budget-/Audit-Eintrag.

### S1.5 Prompt-/Agent-Assets
**Findings:** R2P-001 (veraltete Link-Typen in `DOMAIN_MODEL.md`), R2P-002 (drei Output-Vokabulare),
R2P-003 (keine Few-Shots), R2P-004 (Boilerplate-Duplikation), R2P-005 (nur Interpolations-Tests),
R2P-006 (DE/EN-Mix), R2P-007 (Locale-Drift), R2P-008 (Provenance nicht geloggt), R2P-009
(JSON-Parser 5×), R2P-010 (drei Daten-Grenzen).
- [ ] Ground Truth aus `link_types/builtin.py` generieren statt handpflegen; Drift-Test.
- [ ] Ein Output-Schema pro Prompt-Familie; Parser zentralisieren (R2P-009).
- [ ] Few-Shot-Fälle + Output-Contract-Tests in promptfoo (nicht nur Interpolation).
- [ ] Sprache der Agent-Assets vereinheitlichen; Provenance im LLM-Audit loggen.

**DoD:** `DOMAIN_MODEL.md` nennt exakt die realen Link-Typen; promptfoo bricht bei Output-Drift.

---

## 4. Welle 2 — Performance, DB, Frontend

### S2.1 Backend-Performance
**Findings:** PERF-001 (Allocation-View materialisiert Workspace), PERF-002 (VCRM 2R-Queries),
PERF-003 (Tenant-Search-Fan-out), PERF-010 (unbounded rows), PERF-011 (Serialisierung/Sort).
- [ ] Allocation-View: Filter in den QuerySet, `order_by("sort_key","id")`, DB-Pagination, Counts per
      SQL-Aggregat.
- [ ] VCRM: zwei Batch-Queries + `(source_id, link_type, tenant_id)`-Index.
- [ ] Search: ein `query_entities`-Call pro Workspace über alle Typen, bounded parallel.
- [ ] Unbounded Loads kappen; Serialisierung/Sortierung messen und begrenzen.

**Tests:** Query-Count-Assertions (`assertNumQueries`), `EXPLAIN`-Beleg, Lastprofil vor/nach.
**DoD:** Query-Zahl unabhängig von Workspace-Größe bzw. linear zur Seite; messbare Verbesserung
dokumentiert (keine „gefühlte" Optimierung).

### S2.2 DB-Handwerk & Indizes
**Findings:** PERF-005 (Full Table Scan), PERF-006 (Permission-N+1), PERF-008 (Pooling),
PERF-009 (Cache-Keyspace), R2D-001…R2D-008 (Datenmigrationen, RLS-DDL-Duplikate, Backfills,
Doku-Drift, Choice-Vokabular).
- [ ] Fehlende Indizes ergänzen (mit `CREATE INDEX CONCURRENTLY`-Muster).
- [ ] Permission-Checks batchen.
- [ ] `CONN_MAX_AGE`/Pooler-Entscheidung dokumentieren und messen.
- [ ] Cache-Keyspace begrenzen (TTL/Präfix/Eviction).
- [ ] Migrationen: keine Live-Helfer in Datenmigrationen, RLS-DDL-Helper, Backfill batchen,
      Reverse sicher, Docstrings korrigieren, Choices zentralisieren.

**DoD:** Query-Plan ohne Seq Scan auf heißen Pfaden; Migrationen rückwärts getestet.

### S2.3 Frontend-Performance
**Findings:** PERF-004 (Doppel-Hydration), PERF-007 (Precache lädt alle Lazy-Chunks), UI-009
(Re-Renders), R2F-004 (Index-Keys), R2F-006 (Effekt-Reset).
- [ ] Precache auf App-Shell + tatsächlich genutzte Routen begrenzen; schwere Editoren lazy halten.
- [ ] Doppelte Hydration entfernen (ein Fetch pro Scope).
- [ ] `emphasise`-Callback stabilisieren, Zeilen memoizen; Index-Keys durch stabile IDs ersetzen.
- [ ] Workspace-Wechsel per `key` statt Reset-Effekt.

**DoD:** Bundle-/Precache-Größe messbar reduziert; kein Re-Render der ganzen Liste bei Hover.

---

## 5. Welle 3 — Frontend-Korrektheit, A11Y, UI

### S3.1 Client, Auth, i18n, PWA
**Findings:** FE-001 (Retry bei 403/422), FE-002 (Workspace-Race nach Logout), FE-003 (CSRF-Banner
DE), FE-004 (Install-Prompt-Rejection), FE-005 (i18n-Baselines), FE-006 (`any`-Typen), FE-007
(Update-Banner vor Erfolg), FE-008 (Test-Polyfill), R2F-001/003/005/007/008.
- [ ] Retry-Policy: 4xx außer 408/429 nicht wiederholen; `status` am Fehler.
- [ ] Workspace-Reload mit Generation-Token; keine State-Writes nach Cleanup.
- [ ] CSRF-Banner + ErrorBoundary-Labels i18n; `missingKeyHandler` dev-only.
- [ ] Install/Update-Pfade mit `try/catch/finally`; UI erst nach Erfolg zurücksetzen.
- [ ] Unsound Casts (`as unknown as`, Preset-Cast) durch Guards/Unions ersetzen.
- [ ] Test-Polyfill auf `SubmitEvent` umstellen; Typen statt `any` in Mocks.

**DoD:** Logout während laufendem `listAll` hinterlässt keinen aktiven Workspace; 403 wird nicht
retryt; kein Crash bei unbekanntem Preset.

### S3.2 Komponenten-Verträge
**Findings:** R2F-002 (28-Prop-Boolean-Trap), UI-001 (SplitView-Doppelimplementierung), UI-002
(God-Components), UI-003 (Breakpoint-Vokabular), UI-006 (klickbare Divs).
- [ ] `ArtifactFormActions` auf diskriminierte `mode`-Union umbauen.
- [ ] SplitView: eine Implementierung (Concept) + Legacy-Adapter, dann Legacy löschen.
- [ ] God-Components in Hooks/Präsentationskomponenten zerlegen (Reihenfolge nach Churn).
- [ ] Breakpoints auf 640/768/1024/1600 vereinheitlichen; Ausnahmen dokumentieren.
- [ ] `ClickableRegion`-Primitiv statt handgerollter role/tabIndex/keydown-Trias.

**DoD:** Kein unmöglicher Props-Zustand kompilierbar; ein SplitView-Pfad; Breakpoint-Scan grün.

### S3.3 Barrierefreiheit
**Findings:** A11Y-001 (Lock-Icon ohne SR-Name), A11Y-002 (Gate scannt nur 3 States), A11Y-003
(Link nur per Farbe), A11Y-004 (Fokusring-Kontrast), A11Y-005 (16px-Chevron), A11Y-006
(Checkboxen ohne Namen).
- [ ] SR-Namen/`aria-describedby` für gesperrte Zeilen; Checkbox-Labels.
- [ ] Gate auf alle Routen × 5 Themes × `wcag22aa` erweitern; serious+critical blocken.
- [ ] Links mit Unterstreichung/Nicht-Farbe-Signal; Fokusring-Token kontrastfest.
- [ ] Touch-Ziele ≥ 24/44 px (Tokens), Chevron vergrößern.
- [ ] Manuelle NVDA/VoiceOver- und 400 %-Zoom-Prüfung dokumentieren.

**DoD:** axe-Sweep deckt alle Themes/Routen; manuelle Prüfung protokolliert; Gate kann nicht mehr
„nur 3 States" grün sein.

### S3.4 UI-Design-Schuld
**Findings:** UI-004 (Rohfarben), UI-005 (Print-CSS / `!important`), UI-007 (Inline-Styles),
UI-008 (Hover-only-Kanten).
- [ ] Fehlende Alpha-Tokens ergänzen, WorkflowEditor-Literale ersetzen, Baseline-Eintrag löschen.
- [ ] Print-Token-Paar einführen; `!important` reduzieren.
- [ ] Export-Panel auf CSS-Modul umstellen.
- [ ] Kanten auch per Fokus/Selektion hervorheben.

**DoD:** Ratchet-Baselines sinken; Print bleibt token-konform.

---

## 6. Welle 4 — Struktur, Clean Code, Tests

### S4.1 Clean Code / SOLID Backend
**Findings:** R2C-001 (LLM-Plumbing 4×), R2C-002 (CRUD-Quartett 13×), R2C-003 (19-Parameter-Update),
R2C-004 (72-Methoden-Service), R2C-005 (tote Handler-Parameter), R2C-006 (333-Zeilen-Funktion),
R2C-007 (tote Parameter/lügende Kommentare), R2C-008 (Lookup-Duplikate), R2C-009 (Policy-Metadaten).
- [ ] LLM-Provider-Auflösung/`_complete` zentralisieren; Test-Equivalenz.
- [ ] CRUD-Bausteine als generische Helper/Mixin mit klarer Grenze.
- [ ] `update_requirement`-Parameterobjekt (Command/DTO) einführen.
- [ ] God-Service in fachliche Services zerlegen, Fassade behalten.
- [ ] Tote Parameter/Kommentare entfernen; Lookup-Helper zusammenführen.

**DoD:** Duplikate messbar reduziert (Clone-Report), Fassade unverändert, alle Tests grün.

### S4.2 Struktur, Zyklen, Layer
**Findings:** R2S-001 (`views.py` 15,6k), R2S-002 (Fassade/echte Zyklen), R2S-003 (MCP→Persistence),
R2S-004 (Layer-0→Layer-2), R2S-005 (2.012-Zeilen-Tree), R2S-006 (Viewport-Duplikate), R2S-007
(Model-/Serializer-Monolithen), R2S-008 (LLM-JSON-Parser), R2S-009 (latente Zyklen), R2S-010
(God-Services).
- [ ] `views.py` in ViewSet-Module schneiden (mechanisch, verhaltensgleich, ein PR pro Domäne).
- [ ] Fassade konsolidieren: `services_stepN`-Shims entfernen, echte Zyklen brechen.
- [ ] MCP nutzt ausschließlich die Layer-2-Fassade; Architektur-Test verschärfen.
- [ ] Layer 0 darf Layer 2 nicht importieren (Import-Linter + CI-Ratchet).
- [ ] Tree-Komponente zerlegen; Viewport-State an einer Stelle.
- [ ] Modelle/Serializer je Domäne splitten; JSON-Parser zentralisieren.

**DoD:** Import-Linter/Cycle-Check grün; `views.py` < 3k Zeilen; Architekturtests decken die
Layer-Regeln ab.

### S4.3 Testqualität
**Findings:** TEST-001 (Skip maskiert Features), TEST-002 (Mega-Spec), TEST-003 (fehlende Isolation),
TEST-004/005 (mobile Visual/Seed), TEST-006 (Helper-Duplikate), TEST-007 (catch-and-ignore),
TEST-008 (A11Y-Gate), TEST-009 (Shard-Balance), TEST-010 (fixed sleeps), TEST-011 (Error-Paths),
TEST-012 (MCP/API-Blindspot), R2T-001…R2T-007 (Always-green, Over-Mocking, `as any`, CSS-Assertions,
Sleeps, Tautologien, schwache Fehler-Asserts).
- [ ] Skips durch echte Asserts ersetzen; Preconditions deterministisch seeden.
- [ ] Mega-Spec in unabhängige Tests mit API-Fixtures zerlegen.
- [ ] Jede state-mutierende Spec mit isoliertem Workspace + verifiziertem Cleanup.
- [ ] Unit-Tests: Mock-Interaktionen nur wo Vertrag; `as any` durch typisierte Fixtures ersetzen.
- [ ] Fixed sleeps → `expect.poll`/Locator-Assertions.
- [ ] MCP-/API-Negativpfade ergänzen; Shard-Balance messen.

**DoD:** Kein `test.skip(true, "feature missing")` ohne Ticket; Cleanup-Fehler schlägt fehl;
Fehlerpfade haben Assertions.

---

## 7. Welle 5 — Supply Chain, Ops, Betriebsreife

### S5.1 Supply Chain
**Findings:** DEP-003 (First-Party-Images nur Tag), DEP-005 (Dependency-Confusion), DEP-006
(Audit-Scope), DEP-007 (MPL-2.0), DEP-008/009/010, EXT-002, EXT-003 (False Positive dokumentiert).
- [ ] Erste-Partei-Images mit `@sha256` pinnen; Dependabot/Digest-Update.
- [ ] `--extra-index-url` entfernen/absichern; Audit-Scope auf e2e/root/promptfoo erweitern.
- [ ] Lizenzprüfung: MPL-2.0-Abhängigkeit ersetzen oder Entscheidung dokumentieren.
- [ ] SBOM für alle Lockfiles erzeugen; CI-Gate für Lock-vs-Manifest.

**DoD:** Kein unpinned `ghcr.io`-Image; Lizenzmatrix konsistent; Audit deckt alle Ökosysteme.

### S5.2 CI/Compose/Ops-Härtung
**Findings:** OPS-005…OPS-011 (Image-Pinning, Overlay, Environment-Gates, Header-Test, Permissions,
Migration-Ordering, Ressourcenlimits).
- [ ] Compose-Images pinnen; Dev-Overlay nicht in Produktion zulassen.
- [ ] Environment-Klassifikation + Approval-Gates (prod).
- [ ] Header-Test gegen produktive nginx-Version; Workflow-Permissions minimieren.
- [ ] Migrations-Ordering/Pre-Deploy-Job; Ressourcenlimits/Requests.

**DoD:** Prod-Deploy nur mit klassifiziertem Environment und gepinnten Images; Header-Gate testet
die echte Version.

### S5.3 Betriebsreife (Meta-Lücken)
**Findings:** Meta-Review „Missing Dimensions": Configuration Management, Data Lifecycle/
Decommissioning, Domain-Event-Observability, Migration-Safety-Governance, CI-Feedback-Integrität.
- [ ] Config-Katalog (eine Quelle für Env-Vars/Defaults/Secrets) + Startup-Validierung.
- [ ] Datenlebenszyklus: Retention/Löschung/Export für alle Artefakttypen dokumentiert und getestet.
- [ ] Domain-Events observierbar (Metriken/Tracing für Outbox, DLQ, Worker).
- [ ] Migrations-Safety-Runbook (expand/contract, Reverse-Test, Locking).
- [ ] CI-Feedback: Flake-Rate, Shard-Dauer, Gate-Latenz als Metriken.

**DoD:** Jede der fünf Lücken hat ein Artefakt (Katalog/Runbook/Metrik) und einen Owner.

---

## 8. Welle 6 — Dokumentation

### S6.1 Doku-Wahrheit & Status
**Findings:** DOC-002 („pending commit" trotz Merge), DOC-003 (REQ-209…215 im historischen Dokument),
DOC-004 (falsche Auth-Aussage), DOC-005 („Done" ohne Messung), DOC-006 (Index-Stale), DOC-007
(Versionswiderspruch), DOC-008 (falsche Zahlen).
- [ ] „pending commit"-Stellen durch Commit-Hashes ersetzen; Verifikationsstatus nachziehen.
- [ ] REQ-209…215 entweder in die SE-Kaskade überführen oder REQUIREMENTS.md als autoritativ
      deklarieren + Matrix verlinken.
- [ ] CODEBASE_OVERVIEW Auth-Aussage korrigieren; Zahlen aus Messung/Generat erzeugen.
- [ ] Indizes (specs/plans/features) gegen Realität prüfen und aktualisieren.
- [ ] Status nur in Statusfeldern; REQ-211/212/215 bleiben `Teilweise` bis Nachweis.

**DoD:** Keine Doku behauptet etwas, das der Code widerlegt; Zahlen sind reproduzierbar.

### S6.2 SE-/ADR-Lifecycle
**Findings:** DOC-001 (fehlendes Frontmatter/`open_adrs`), DOC-009 (ADR-Namens-/Heading-Verstoß),
DOC-010 (Reviews `open` seit 2 Wochen), DOC-011 (tote Links).
- [ ] Frontmatter für die betroffenen SE-Dokumente ergänzen (oder Regel präzisieren + CI-Check).
- [ ] `open_adrs` in betroffenen REQs nachziehen; ADR-025/026-Status klären.
- [ ] ADR-DS-02 umbenennen/korrigieren; Review-Protokolle schließen.
- [ ] Tote Links reparieren; Link-Check in CI.

**DoD:** Schema-/Frontmatter-Check grün; keine offenen Review-Protokolle ohne Status.

### S6.3 Sprach-/Link-Hygiene
**Findings:** DOC-012 (EN in internen Indizes).
- [ ] Interne Index-Dokumente auf Deutsch umstellen (externe bleiben Englisch).
- [ ] Sprachregel-Check als leichten CI-Lint (nur Indizes/Docs, keine Code-Kommentare).

**DoD:** Sprachregel-Tabelle aus AGENTS.md ist maschinell geprüft.

---

## 9. Abhängigkeiten & Parallelisierung

```
S0.1 ──► S0.2 ──► S0.3 ──► S2.2
  │         │        │
  │         └──► S1.3 ──► S2.1 ──► S4.1 ──► S4.2
  │         └──► S1.4 ──► S1.5
  └──► S0.4 ──► S1.1 ──► S3.1 ──► S3.2 ──► S3.3/S3.4
                └──► S1.2          └──► S2.3 ──► S4.3
  S0.4 ──► S5.1/S5.2 ──► S5.3
  S6.1 ──► S6.2/S6.3   (unabhängig, sofort startbar)
```

**Fünf parallele Tracks:** (A) Security/Data S0.1–S0.3, (B) Contracts/AI S1.1–S1.5,
(C) Perf/DB S2.x, (D) Frontend/Tests S3.x+S4.3, (E) Structure/Ops/Docs S4.1–S4.2, S5, S6.
Kritischer Pfad: S0.1 → S0.2 → S0.3 → S4.2 (Struktur) ≈ 15 Tage.

## 10. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| History-Rewrite (SEC-001) bricht Forks/PRs | Koordinationsaufwand, Force-Push | Wartungsfenster, Mirror, Ankündigung, Rotation zuerst |
| RLS-Enforcement bricht bestehende Deployments | Ausfälle, Supportlast | Staged Rollout, Feature-Flag, Monitoring, Rollback-Plan |
| `views.py`-Split erzeugt Merge-Konflikte | Stillstand | mechanisch, ein PR pro Domäne, Freeze-Fenster |
| E2E-Gate verlängert Releases | Lieferverzug | Shard-Budget, Fail-fast, nur Required-Suite blocken |
| Struktur-Refactors ohne Messung | Regressionsrisiko | Ratchets, Query-Count-/Bundle-Messung, Feature-Flags |
| Doku-Korrekturen werden erneut stale | Vertrauensverlust | Generatoren statt Handzahlen, CI-Drift-Checks |

## 11. Offene Entscheidungen (vor Start zu klären)

| # | Entscheidung | Optionen | blockiert |
|---|---|---|---|
| E1 | History-Rewrite jetzt oder Rotation zuerst? | (a) Rotation + Rewrite im Fenster, (b) Rotation jetzt, Rewrite später | S0.1 |
| E2 | RLS-Enforcement produktiv | (a) sofort enforced, (b) gestaffelt mit Flag + Coverage-Gate | S0.2 |
| E3 | `views.py`-Split | (a) mechanisch je Domäne, (b) nur neue Endpunkte auslagern, Altbestand einfrieren | S4.2 |
| E4 | Legacy-SplitView | (a) migrieren + löschen, (b) Adapter behalten | S3.2 |
| E5 | `docs/REQUIREMENTS.md` | (a) als autoritativ deklarieren, (b) REQs in SE-Kaskade überführen | S6.1 |
| E6 | MPL-2.0-Abhängigkeit | (a) ersetzen, (b) mit Rechtsprüfung behalten | S5.1 |
| E7 | Prompt-Sprache der Agent-Assets | (a) Englisch, (b) Deutsch intern, Englisch extern | S1.5 |

## 12. Traceability (Finding → Schnitt)

| Finding-Bereich | Schnitt(e) |
|---|---|
| SEC-001, SEC-003, SEC-004, SEC-005, SEC-006, SEC-007, OPS-003 | S0.1 |
| APP-001, SEC-002, EXT-001, L1-006, EXT-006 | S0.2 |
| L0-001, L0-002, L0-003, L1-001…L1-005, L1-007, L1-008 | S0.3 |
| OPS-001, OPS-002, OPS-004, DEP-001, DEP-002, DEP-004 | S0.4 |
| API-001, API-006, R2A-001, R2A-002, R2A-005…R2A-008 | S1.1 |
| API-002…API-005, API-007, API-008, R2A-003, R2A-004 | S1.2 |
| APP-002…APP-006, EXT-004, EXT-005, EXT-007, EXT-008 | S1.3 |
| AI-001…AI-007 | S1.4 |
| R2P-001…R2P-010 | S1.5 |
| PERF-001, PERF-002, PERF-003, PERF-010, PERF-011 | S2.1 |
| PERF-005, PERF-006, PERF-008, PERF-009, R2D-001…R2D-008 | S2.2 |
| PERF-004, PERF-007, UI-009, R2F-004, R2F-006 | S2.3 |
| FE-001…FE-008, R2F-001, R2F-003, R2F-005, R2F-007, R2F-008 | S3.1 |
| R2F-002, UI-001, UI-002, UI-003, UI-006 | S3.2 |
| A11Y-001…A11Y-006 | S3.3 |
| UI-004, UI-005, UI-007, UI-008 | S3.4 |
| R2C-001…R2C-009 | S4.1 |
| R2S-001…R2S-010 | S4.2 |
| TEST-001…TEST-012, R2T-001…R2T-007 | S4.3 |
| DEP-003, DEP-005…DEP-010, EXT-002, EXT-003 | S5.1 |
| OPS-005…OPS-011 | S5.2 |
| Meta-Lücken (Config, Lifecycle, Observability, Migration-Safety, CI-Feedback) | S5.3 |
| DOC-002…DOC-008 | S6.1 |
| DOC-001, DOC-009, DOC-010, DOC-011 | S6.2 |
| DOC-012 | S6.3 |

**Abdeckung:** 186/186 Findings sind genau einem Schnitt zugeordnet; keine Doppelzuordnung.

## 13. Definition of Done (pro Schnitt)

1. Finding(s) behoben oder bewusst als „nicht reproduzierbar/akzeptiert" mit Begründung geschlossen.
2. Regressionstest existiert und war vor dem Fix rot (im PR nachvollziehbar).
3. `npm test`, `tsc`, ESLint, betroffene Backend-Tests, Playwright-Smoke grün.
4. Doku/Status aktualisiert (Audit-Zeile `fixed in <commit>`), keine neue Doku-Schuld.
5. Keine Abschwächung bestehender Gates/Ratchets.
6. Reviewer-Approval für sicherheits-/datenkritische Schnitte (S0.x, S1.4, S5.1).
