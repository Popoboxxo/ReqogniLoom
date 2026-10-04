---
title: Bugfix-Runde — Umsetzungsplan
date: 2026-10-04
branch_base: main @ 968cfc00
author_agent: planner
status: proposed
scope: alle offenen bug-/qa-Issues (27 triagiert)
---

# Bugfix-Runde — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert **nichts** selbst. Er beschreibt
> Reihenfolge, Wellen, Fix-Ansätze und Akzeptanzkriterien für die Abarbeitung der
> 27 triagierten Issues.
>
> **Faktenbasis:** Der Triage-Block (Severity, Typ, Dateien/Symbole, Abhängigkeiten)
> wurde extern verifiziert und wird hier **verbatim** übernommen. Alle als
> „verifiziert" gekennzeichneten Angaben stammen daraus. Angaben, die in dieser Runde
> erst noch bestätigt werden müssen, sind explizit als **Annahme** oder
> **zu verifizieren** markiert.

---

## 0. Legende

| Kürzel | Bedeutung |
|---|---|
| **S** | Kleiner Aufwand (Single-File / Config / reine Verifikation) |
| **M** | Mittlerer Aufwand (mehrere Dateien oder neue Tests) |
| **L** | Großer Aufwand (Feature-Umfang oder mehrere Schichten) |
| **DP** | Decision-Pending — Fix blockiert bis Entscheidung (siehe §7) |
| **NI** | Needs-Info — blockiert bis Eingang fehlender Informationen |
| **BLOCK** | Blockiert nachfolgende Issues |

**Phasen-Grundsatz:** Jede Welle ist **unabhängig shippbar** und wird auf einem
eigenen `fix/*`-Branch off `main` umgesetzt. Keine Commits auf `main` (Branch-Guard).

---

## 1. Triage-Tabelle

### In-Scope Bugs (18)

| Issue | Severity | Typ | Betroffene Schicht / Datei (verifiziert) | Aufwand | Abhängigkeiten |
|---|---|---|---|---|---|
| **1145** | HIGH | Bug (CI/Release) | `.github/workflows/docker-publish.yml` (`GITHUB_SHA`), `scripts/build.sh:100` (`git rev-parse HEAD`), `deploy/docker-compose.yml:668-672/977-999` | M | **BLOCK** für 1146–1154 |
| **1146** | MED | Bug (Backend/Migration) | `backend/application/attribute_migration_service.py:938` (`_resolve_workspaces`) | S | dep 1145 |
| **1147** | MED | Bug (MCP) | `backend/mcp_server/tools/generic.py:660` (`_handle_query`) | M | dep 1145 |
| **1148** | LOW | Bug (LLM-Adapter) | `backend/llm_adapter/router.py:209-223` | S | dep 1145 |
| **1149** | MED | Bug (LLM-Adapter/Test-Infra) | `backend/llm_adapter/embedding_service.py:166/185`, `llm_adapter/checks.py:79-146` | M | dep 1145 |
| **1150** | LOW | Bug (Audit) | `backend/application/audit_service.py:242` (:293 `to_dict`, :942 `AuditReport`) | S | dep 1145; **vermutlich bereits implementiert → verifizieren** |
| **1151** | LOW | Bug (MCP) | `backend/mcp_server/tools/tests.py:365/366`, Handler `:778-786` | S | dep 1145 |
| **1152** | LOW | Bug (Plugin/Frontend) | `integrations/hermes-plugin/reqogniloom/src/state.ts:325` (`cancelInterview`) | S | dep 1155/1156 |
| **1153** | MED | Bug (Honcho/Config) | `deploy/docker-compose.yml:149-163` (`DIALECTIC_LEVELS`), `:72-142` (`x-honcho-env`) | M–L | dep 1155; **DP** (Config-Key vs. Upstream-Defekt) |
| **1154** | MED | Bug/Feature (MCP/Memory) | `backend/mcp_server/tools/memory.py` (kein `ask`), `tool-manifest.json` | M | dep 1153/1155; **REQ nötig** vor Fix |
| **1128** | HIGH | Bug (Security) | `backend/application/import_idempotency.py:66-106/137-158`, `backend/rest_api/views.py:8301-8316/8545/8566`, `frontend/src/components/CsvImport/CsvImport.tsx:299-301` | M | dep ADR-014; **DP** (HMAC vs. SHA-256; IMPORT_CONTRACT_V2 default) |
| **1129** | MED | Bug (MCP) | `backend/mcp_server/tools/goals.py:721/755-783/984-1006` | S | keine |
| **1130** | MED | Bug (Resilience/Backend) | `backend/reqogniloom/bounded_dns.py:40-47/235-261/277-284` | M | keine |
| **1131** | HIGH | Bug (Security) | `backend/auth_tenancy/resource_scope.py:54-61/898-910` | M | **DP** (uniform-404 vs. ADR-013 akzeptieren) |
| **988** | MED | Bug (Frontend/Bluepencil) | `frontend/public/bluepencil/latest/latest.json`, `frontend/src/bluepencil/loader.ts` | S | **DP** (commit+close); reine Verifikation |
| **1112** | MED | Bug (Attribute-Defs) | `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py:1217` (`_append_missing`) | M | dep Familie #940 |
| **1115** | LOW | Bug (Test-Debt/E2E) | `e2e/helpers/auth.ts:56-78` (`getWorkspaceId`, `apiTransition`) | S | keine |
| **1116** | MED | Bug (Dev-Env) | `deploy/docker-compose.override.yml:70-72` (migrate als app-Rolle) | S | keine |

### Out-of-Scope (kein Bugfix-Bestandteil, 7)

| Issue | Severity | Typ | Betroffene Schicht / Datei (verifiziert) | Aufwand | Abhängigkeiten |
|---|---|---|---|---|---|
| **801** | — | Enhancement (UI) — **out-of-scope** | `frontend/src/components/**` (History/Diff-Inspector) | L | eigene Roadmap |
| **1097** | — | Enhancement (MCP) — **out-of-scope** | `backend/mcp_server/tools/goals.py`, `docs/api/MCP-SURFACE.md` | M | **DP** (Rolle/Governance) |
| **1102** | — | Enhancement (Test-Infra) — **out-of-scope** | `backend/mcp_server/tests/test_mcp_api_key_roles.py:81-90` | S | **Duplikat von 1133** |
| **1103** | — | Enhancement (Test-Infra) — **out-of-scope** | drei Ratchets / drei Re-Baseline-Mechanismen | M | eigene Roadmap |
| **1113** | — | Enhancement (Test-Tooling) — **out-of-scope** | `e2e/tests/**`, `frontend/src` (statischer `data-testid`-Check) | M | eigene Roadmap |
| **1133** | — | Enhancement (Test-Infra) — **out-of-scope** | `backend/mcp_server/tests/test_mcp_api_key_roles.py:278-305` | S | überlappt 1102 |
| **1117** | — | Doku/Test-Debt — **out-of-scope** | 3 unbenannte Frontend-Failures | S | **NI** (Namen fehlen) |

### Deliberate Security-Enhancements (nicht Bugfix, 2)

| Issue | Severity | Typ | Betroffene Schicht / Datei | Aufwand | Abhängigkeiten |
|---|---|---|---|---|---|
| **1135** | — | Security-Enhancement — **out-of-scope** | Django-Admin Brute-Force-Schutz (`django-axes` fehlt) | — | **HARD STOP** — Dependency-Sign-off nötig |
| **1136** | — | Security-Enhancement — **out-of-scope** | RLS-Coverage pre-auth/webhook | L | ADR-Kandidat |

> **Summe:** 18 In-Scope-Bugs + 7 Out-of-Scope + 2 Security-Enhancements = **27 triagierte Issues**.

---

## 2. Wellen / Phasen

Die Wellen sind so geschnitten, dass **Welle 0 zuerst** läuft (Release-/CI-Blocker),
weil sie die Re-Validierung aller übrigen Fixes blockiert. Wellen 1–4 sind
grundsätzlich unabhängig, sofern die Wave-internen Dateien disjunkt sind (§4).

### Welle 0 — Release-/CI-Blocker

- **Ziel:** CI/Release-Vertrauen wiederherstellen; image-SHA == Git-Tag erzwingen;
  `celery-beat` healthy; `/health/live|ready` liefern 200 statt 404.
- **Enthalten:** **1145** (+ neues CI-Gate „image-SHA == tag").
- **Risiko:** Mittel. Änderungen an Compose-/CI-Dateien können andere Services
  tangieren; Health-Endpoint-Routing berührt `urls.py`-Ebene (`zu verifizieren`,
  im Triage nicht als Datei benannt).
- **Rollback:** Branch verwerfen; `main @ 968cfc00` bleibt unberührt. Kein
  Daten-migrierender Schritt.
- **Begründung Vorrang:** Ohne belastbare Version-/Health-Signatur sind alle
  Re-Validierungen aus Welle 1–4 **messunsicher** (§7).

### Welle 1 — beta.18 bestätigte Bugs

- **Ziel:** die im beta.18 verifizierten Funktionsbugs abarbeiten.
- **Enthalten:** **1146**, **1147**, **1148**, **1150** (vermutlich bereits
  implementiert → Verifikation), **1151** (alle S), danach **1149** (M).
- **Risiko:** Niedrig. Abgegrenzte Backend-/MCP-/LLM-Adapter-Änderungen mit
  vorhandenen Tests.
- **Rollback:** pro Fix eigener Commit; Branch verwerfen oder einzelne Commits
  revertieren (`git revert <sha>`).
- **Hinweis:** 1146 ist datenmigrierend wirksam (Attribut-Migration). Vor Merge
  prüfen, ob bereits „applied"-markierte Läufe rückabgewickelt werden müssen
  (`zu verifizieren`).

### Welle 2 — Security / Residuen (Backend + MCP)

- **Ziel:** Sicherheits- und Resilienz-Residuen schließen.
- **Enthalten:** **1129** (S, keine Deps), **1130** (M, keine Deps),
  **1128** (M, **DP**), **1131** (**DP**).
- **Risiko:** Hoch für 1128/1131 (Security, AuthZ-Semantik). 1129/1130 isoliert.
- **Rollback:** 1129/1130 einzeln revertierbar. 1128/1131 erst nach Entscheidung
  aus §7 starten; bei AuthZ-Semantikwechsel (1131) zusätzlich Doku/ADR-Update.
- **Reihenfolge intern:** 1129 + 1130 parallel; 1128/1131 erst nach
  Entscheidungs-Sign-off.

### Welle 3 — Dev / Test / Daten

- **Ziel:** Dev-Umgebung, Test-Schulden und Daten-Bootstrap stabilisieren.
- **Enthalten:** **1116** (S), **1115** (S), **1112** (M), **988** (S, Verify).
- **Risiko:** Niedrig. 1112 kann Bestandsdaten (Attribute-Definitionen) verändern —
  Additivität prüfen; 988 reine Verifikation.
- **Rollback:** Branch verwerfen; keine destruktiven Migrations ohne Downgrade-Pfad.

### Welle 4 — Honcho / Memory + Decision-Pending

- **Ziel:** Honcho-/Memory-Themen und entscheidungsabhängige Issues abschließen.
- **Enthalten:** **1153** (DP), **1154** (REQ nötig), **1135**/**1136** nur nach
  Entscheidung.
- **Risiko:** Mittel–Hoch. 1153 kann Upstream-Defekt sein; 1154 ist Feature-Anteil
  mit Governance-Bedarf; 1135 HARD STOP (fehlende Dependency).
- **Rollback:** Nichts starten, solange Entscheidung/REQ aussteht.
- **Nicht-Bestandteil:** 801, 1097, 1103, 1113 (Enhancements) bleiben eigene
  Roadmap-Punkte, werden hier **nicht** eingeplant.

---

## 3. Issue-Fix-Spezifikation

> Für jeden In-Scope-Bug: Lösungsansatz → betroffene Dateien (verifiziert) →
> Teststrategie → testbares Akzeptanzkriterium.

### 1145 — CI/Release: SHA-Label-Mismatch, celery-beat unhealthy, Health-404

- **Lösungsansatz:**
  1. SHA-Quelle vereinheitlichen: CI (`GITHUB_SHA`) und Build (`git rev-parse HEAD`)
     müssen **denselben** Commit liefern; `GIT_COMMIT_SHA` als Build-Arg/Label konsistent
     durchreichen.
  2. `celery-beat` Healthcheck im Compose korrigieren (`deploy/docker-compose.yml:977-999`)
     inkl. Abhängigkeit `:668-672` (`depends_on`/Healthcheck-Gate).
  3. `/health/live` und `/health/ready` im URL-Routing registrieren (Datei
     `zu verifizieren`; vermutlich `backend/reqogniloom/urls.py`).
  4. CI-Gate hinzufügen: image-SHA-Label **==** Git-Tag-SHA, sonst Fail.
- **Betroffene Dateien:** `.github/workflows/docker-publish.yml`, `scripts/build.sh:100`,
  `deploy/docker-compose.yml:668-672/977-999`; Health-Routing `zu verifizieren`.
- **Teststrategie:** pytest (`backend/tests/test_version.py`,
  `reqogniloom/tests/test_health_contract_adr010.py`), Playwright
  (`e2e/tests/health-contract.spec.ts`), + CI-Gate.
- **Akzeptanzkriterium:** `test_version` + `test_health_contract_adr010` und
  `health-contract.spec.ts` grün; CI-Gate schlägt fehl, wenn image-SHA ≠ Tag-SHA;
  `celery-beat` meldet `healthy`; `/health/live` und `/health/ready` → HTTP 200.

### 1146 — `_resolve_workspaces` matcht 0 Workspaces, meldet aber `applied`

- **Lösungsansatz:** `preset.get("name","")` gegen das tatsächlich gesendete
  `preset={"tier":...}` alignen (Tier statt Name lesen); bei 0 Matches darf der
  Status **nicht** `applied` sein → Fehler/No-Op-Status mit Diagnose.
- **Betroffene Datei:** `backend/application/attribute_migration_service.py:938`.
- **Teststrategie:** pytest `backend/application/tests/test_attribute_migration_service.py`.
- **Akzeptanzkriterium:** Testfall mit `preset={"tier": ...}` matcht die erwarteten
  Workspaces (`>0`); 0-Match erzeugt nicht-`applied`-Status + aussagekräftige Meldung.

### 1147 — `_handle_query` ohne `count`, inkonsistente Result-Keys, `uid` verworfen

- **Lösungsansatz:** Response-Envelope vereinheitlichen (`count` ergänzen, einheitlicher
  Result-Key statt `items` vs. `requirements`); übergebenes `uid` in die Query
  übernehmen statt still zu verwerfen.
- **Betroffene Datei:** `backend/mcp_server/tools/generic.py:660`.
- **Teststrategie:** pytest `backend/mcp_server/tests/test_generic_tool_group.py:509`,
  `test_tool_groups.py`; ggf. Manifest-Drift-Gate prüfen.
- **Akzeptanzkriterium:** Antwort enthält `count` und einen konsistenten Result-Key;
  `uid`-Filter wirkt nachweislich (Test weist gefiltertes Ergebnis nach).

### 1148 — Capability-disabled meldet `LLM_NOT_CONFIGURED`

- **Lösungsansatz:** eigenen, unterscheidbaren Fehlercode für „Capability disabled"
  einführen (z. B. `LLM_CAPABILITY_DISABLED`) statt Wiederverwendung von
  `LLM_NOT_CONFIGURED`.
- **Betroffene Datei:** `backend/llm_adapter/router.py:209-223`.
- **Teststrategie:** pytest `backend/llm_adapter/tests/test_llm_adapter.py:461-469`.
- **Akzeptanzkriterium:** Deaktivierte Capability liefert den neuen Code; echte
  Nicht-Konfiguration liefert weiterhin `LLM_NOT_CONFIGURED` (beide Fälle getestet).

### 1149 — Embedding-Dim 384 vs. .env 768; Image-Tests nicht lauffähig

- **Lösungsansatz:** Dimension nicht hart auf 384 (`embedding_service.py:166/185`),
  sondern aus Konfiguration/.env (768) beziehen; Image-Test-Suite lauffähig machen
  (Test-Module ergänzen, DB-Rolle mit `CREATEDB`).
- **Betroffene Dateien:** `backend/llm_adapter/embedding_service.py:166/185`,
  `backend/llm_adapter/checks.py:79-146`; Test:
  `backend/llm_adapter/tests/test_embedding_providers.py:45`.
- **Teststrategie:** pytest; zusätzlich `llm_adapter/checks.py`-Konsistenzprüfung.
- **Akzeptanzkriterium:** Embedding-Vektorlänge entspricht der konfigurierten
  Dimension (768); Test-Suite läuft in der Image-Umgebung durch (kein Skip wegen
  fehlender Module/CREATEDB).

### 1150 — `total_blockers_available` wird beim Waive nicht dekrementiert

- **Lösungsansatz (Verifikation zuerst):** Feld und Tests existieren laut Triage
  bereits → prüfen, ob die Dekrementierung **schon implementiert** ist. Falls ja:
  Issue mit Testbeleg schließen. Falls nein: Zähler bei Waive (`audit_service.py:242`
  Feld, `:293` `to_dict`, `:942` `AuditReport`) korrekt reduzieren.
- **Betroffene Datei:** `backend/application/audit_service.py:242/293/942`.
- **Teststrategie:** pytest `backend/application/tests/test_audit_service.py:219/239/288`.
- **Akzeptanzkriterium:** Nach einem Waive sinkt `total_blockers_available` um exakt 1;
  `to_dict()` und `AuditReport` spiegeln den reduzierten Wert. **Oder:** Testbeleg, dass
  bereits implementiert → Issue schließen (kein Code-Change).

### 1151 — `type` ohne Enum vs. `test_type` mit Enum; Handler liest beide

- **Lösungsansatz:** Schema vereinheitlichen — entweder `type` auf Enum umstellen oder
  `test_type` als kanonisch festlegen und `type` als Alias sauber dokumentieren;
  Handler (`:778-786`) auf **einen** Pfad reduzieren.
- **Betroffene Datei:** `backend/mcp_server/tools/tests.py:365/366` + Handler `:778-786`.
- **Teststrategie:** pytest `backend/mcp_server/tests/test_testcase_status_lowercase_453.py`.
- **Akzeptanzkriterium:** Beide Eingabeformen (`type` / `test_type`) werden konsistent
  validiert (gleiche Enum-Prüfung); ungültiger Wert wird in beiden Fällen abgewiesen.

### 1152 — `cancelInterview` setzt nur lokalen State

- **Lösungsansatz:** `cancelInterview` an den tatsächlichen Server-/Plugin-Flow binden
  (Aufruf des mutierenden Endpunkts statt reiner lokaler State-Mutation); irreführenden
  Kommentar korrigieren (Aussage „`interview.abandon` fehlt" prüfen und richtigstellen).
- **Betroffene Datei:** `integrations/hermes-plugin/reqogniloom/src/state.ts:325`.
- **Teststrategie:** Vitest `src/__tests__/state.test.ts:417`,
  `InterviewFormView.test.tsx:171`.
- **Akzeptanzkriterium:** Nach `cancelInterview` ist der Serverzustand persistiert
  (Mock-Verifikation des Aufrufs) und die lokale Sicht konsistent; Tests grün.

### 1153 — Honcho: Dialectic-Path ohne Env-Header → HTTP 500

- **Lösungsansatz:** `DIALECTIC_LEVELS` (`deploy/docker-compose.yml:149-163`) und
  `x-honcho-env`-Header (`:72-142`) auch auf dem Dialectic-Pfad anwenden, sodass
  `MissingSessionID` (400) nicht als 500 eskaliert. **Voraussetzung:** Entscheidung,
  ob Config-Key fehlt oder Upstream-Defekt (§7).
- **Betroffene Datei:** `deploy/docker-compose.yml:72-142/149-163`.
- **Teststrategie:** kein automatisierter Test vorhanden → **Config-Verify** (Compose
  rendern, Header-Präsenz prüfen) + manueller Dialectic-Smoke; ggf. neuer Smoke-Test.
- **Akzeptanzkriterium:** Dialectic-Aufruf liefert kein 500 mehr; ohne Session-ID
  erfolgt eine definierte 400-Antwort; Header sind im gerenderten Compose nachweisbar.

### 1154 — MCP `memory.ask` fehlt (Feature-Anteil)

- **Lösungsansatz:** neues Tool `memory.ask` implementieren, das `peer.chat` aufruft;
  `tool-manifest.json` aktualisieren. **Voraussetzung:** REQ-ID via `requirements`
  (Feature-Anteil, kein reiner Bugfix).
- **Betroffene Dateien:** `backend/mcp_server/tools/memory.py`,
  `docs/agent-templates/tool-manifest.json`.
- **Teststrategie:** neu `backend/mcp_server/tests/test_memory_tool_group.py`.
- **Akzeptanzkriterium:** `memory.ask` ist registriert (Manifest + Drift-Gate grün),
  ruft `peer.chat` auf und liefert eine strukturierte Antwort; Test deckt Erfolgs- und
  Fehlerfall ab.

### 1128 — Import-Idempotenz: tenant-limit, unkeyed SHA-256, `randomUUID` ohne Feature-Detect (Security)

- **Lösungsansatz:** Fingerprint mit **Keyed Hash (HMAC)** statt unkeyed SHA-256
  (`import_idempotency.py:137-158`); Tenant-Limit korrekt durchsetzen (`:66-106`);
  REST-Pfade (`views.py:8301-8316/8545/8566`) konsistent absichern; Frontend
  `crypto.randomUUID` feature-detecten + Fallback (`CsvImport.tsx:299-301`).
  **Voraussetzung:** ADR-014-Entscheidung (HMAC vs. SHA-256; IMPORT_CONTRACT_V2-Default).
- **Betroffene Dateien:** `backend/application/import_idempotency.py:66-106/137-158`,
  `backend/rest_api/views.py:8301-8316/8545/8566`,
  `frontend/src/components/CsvImport/CsvImport.tsx:299-301`.
- **Teststrategie:** pytest `application/tests/test_import_idempotency.py`, `rest_api/tests/`,
  Frontend Vitest.
- **Akzeptanzkriterium:** Fingerprint ist keyed und über Läufe stabil; Tenant-Limit
  blockt Überschreitung; Frontend importiert ohne `crypto.randomUUID` (Fallback greift);
  alle zugehörigen Tests grün.

### 1129 — MCP `goals`: fehlendes `expected_version` (last-writer-wins)

- **Lösungsansatz:** `expected_version` (optimistic locking) für `_archive` (`:721`),
  delete/outdate/reactivate (`:755-783`) und `_handle_approve` (`:984-1006`) erzwingen;
  Konflikt → definierter Fehler statt Overwrite.
- **Betroffene Datei:** `backend/mcp_server/tools/goals.py:721/755-783/984-1006`.
- **Teststrategie:** pytest `mcp_server/tests/test_goal_tools.py`,
  `test_goal_lifecycle_issue346.py`, `test_goal_query_delete.py`.
- **Akzeptanzkriterium:** Mutation mit veralteter Version wird abgelehnt (kein
  Last-Writer-Wins); korrekte Version mutiert erfolgreich.

### 1130 — Bounded-DNS: `rediss://` nicht abgefangen, Read-Stall, `from_url`

- **Lösungsansatz:** `rediss://`-Scheme ebenfalls durch Bounded-DNS leiten
  (`bounded_dns.py:40-47`); `_BoundedDnsMixin._connect` gegen Read-Stall absichern
  (`:235-261`); `from_url` korrekt verdrahten (`:277-284`).
- **Betroffene Datei:** `backend/reqogniloom/bounded_dns.py:40-47/235-261/277-284`.
- **Teststrategie:** pytest `backend/reqogniloom/tests/test_cache_dns_bound_res01.py`.
- **Akzeptanzkriterium:** `rediss://`-URLs werden mit DNS-Bound aufgelöst; kein
  Hänger im Connect-Pfad (Test mit Timeout); `from_url` erzeugt gebundene Verbindung.

### 1131 — `resource_scope` ADR-013: 403 vs. 404, `/permissions/?user_id=` liefert 200

- **Lösungsansatz:** Object-Route-Enforcement (`resource_scope.py:898-910`) und
  ADR-013-Semantik (`:54-61`) angleichen; `/permissions/?user_id=` muss bei
  unberechtigtem Zugriff **403** liefern (nicht 200). **Voraussetzung:** Entscheidung
  uniform-404 vs. ADR-013 akzeptieren (§7).
- **Betroffene Datei:** `backend/auth_tenancy/resource_scope.py:54-61/898-910`.
- **Teststrategie:** pytest `rest_api/tests/test_resource_scope_coverage.py`,
  `auth_tenancy/tests/test_workspace_scope.py`, `test_authorization.py`.
- **Akzeptanzkriterium:** Cross-Tenant-/Cross-User-Zugriff auf `/permissions/?user_id=`
  liefert den entschiedenen Status (403 oder uniform 404); Object-Routes konsistent.

### 988 — Bluepencil `latest.json` re-vendored; Test-Fixture stale

- **Lösungsansatz (reine Verifikation):** prüfen, dass `latest.json` (0.1.0-alpha.2)
  mit dem Loader (`loader.ts`) kompatibel ist; stale Fixture (alpha.1) aktualisieren
  oder Test an neue Version anpassen. Kein Produktionscode-Fix erwartet.
- **Betroffene Dateien:** `frontend/public/bluepencil/latest/latest.json`,
  `frontend/src/bluepencil/loader.ts`; Test:
  `frontend/src/test/bluepencil-loader.test.ts:230`.
- **Teststrategie:** Vitest.
- **Akzeptanzkriterium:** Loader-Test grün gegen 0.1.0-alpha.2; Fixture/Version
  konsistent. **Oder:** Nachweis, dass Fix bereits erfolgt → Issue schließen.

### 1112 — `_append_missing` rein additiv; `field_kind`/`origin_link` nicht migriert

- **Lösungsansatz:** `_append_missing`
  (`bootstrap_attribute_definitions.py:1217`) um Migration bestehender
  `field_kind`/`origin_link`-Werte erweitern (idempotent, ohne Duplikate).
- **Betroffene Datei:**
  `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py:1217`.
- **Teststrategie:** pytest `attribute_definitions/tests/test_bootstrap_command.py:344`,
  `test_bootstrap_relabel_1090.py`.
- **Akzeptanzkriterium:** Erneuter Bootstrap-Lauf migriert vorhandene `field_kind`/
  `origin_link`-Werte; keine Duplikate; Tests grün; dep Familie #940 berücksichtigt.

### 1115 — E2E-Auth-Helper: `items[0]`-Fallback + `apiTransition` ignoriert 400

- **Lösungsansatz:** `getWorkspaceId` (`e2e/helpers/auth.ts:56-78`) ohne blinden
  `items[0]`-Fallback (expliziter Match/Fehler); `apiTransition` muss HTTP 400
  berücksichtigen statt zu ignorieren.
- **Betroffene Datei:** `e2e/helpers/auth.ts:56-78`.
- **Teststrategie:** Playwright (indirekt über E2E-Suite; kein dedizierter Test laut Triage).
- **Akzeptanzkriterium:** Helper schlägt bei fehlendem Workspace explizit fehl statt
  falsches Element zu wählen; `apiTransition` behandelt 400 deterministisch.

### 1116 — Dev-Env: migrate als app-Rolle → Ownership-Crash-Loop

- **Lösungsansatz:** `deploy/docker-compose.override.yml:70-72` so anpassen, dass
  `migrate` mit der privilegierten/owner-Rolle ausgeführt wird (nicht app-Rolle),
  sodass `must be owner of table pl_artifact` nicht auftritt.
- **Betroffene Datei:** `deploy/docker-compose.override.yml:70-72`.
- **Teststrategie:** **Config-Verify** (Compose rendern/`docker compose config`) +
  `make up` Smoke; kein automatisierter Test vorhanden.
- **Akzeptanzkriterium:** `migrate`-Service läuft ohne Ownership-Fehler durch; kein
  Crash-Loop; Dev-Stack kommt hoch.

---

## 4. Reihenfolge & Abhängigkeiten

### Harte Abhängigkeiten

```
1145 (Welle 0) ── BLOCK ──► 1146, 1147, 1148, 1149, 1150, 1151, 1152, 1153, 1154
1155/1156 ──► 1152, 1153, 1154
1153 ──► 1154
1128 ◄── ADR-014 (Decision)
1131 ◄── ADR-013-Entscheidung (Decision)
1112 ◄── Familie #940
988, 1150 ◄── reine Verifikation
```

### Parallelisierbarkeit (Datei-Disjunktheit)

| Gruppe | Issues | Gemeinsame Dateien? | Parallel? |
|---|---|---|---|
| Welle 0 | 1145 | — (allein) | nein (blockt Rest) |
| Welle 1a | 1146, 1147, 1148, 1150, 1151 | disjunkt (verschiedene Module) | **ja** |
| Welle 1b | 1149 | disjunkt zu 1a | **ja** (nach 1145) |
| Welle 2a | 1129, 1130 | disjunkt | **ja** |
| Welle 2b | 1128, 1131 | beide `rest_api/` tangiert (`views.py` vs. `resource_scope.py`) — **disjunkt genug** | unter Entscheidung, danach ja |
| Welle 3 | 1116, 1115, 1112, 988 | disjunkt | **ja** |
| Welle 4 | 1153, 1154 | beide Honcho/Memory-Kontext → **sequenziell** 1153 → 1154 | nein |

**Regel:** Innerhalb einer Welle dürfen nur Issues parallel laufen, deren
Datei-Mengen disjunkt sind. `1128` (`rest_api/views.py`) und `1131`
(`auth_tenancy/resource_scope.py`) überlappen nicht direkt, aber beide berühren
`rest_api/`-Tests → Test-Merge-Konflikte einplanen.

**Wichtigste Abhängigkeit:** **1145 blockiert 1146–1154.** Solange SHA-/Health-/
celery-beat-Signale nicht verlässlich sind, ist die Re-Validierung der Folge-Fixes
messunsicher (§7). Welle 0 daher zwingend zuerst mergen.

---

## 5. Verifikation / DoD

### Globale Kommandos (pro Welle vor Merge)

| Zweck | Kommando |
|---|---|
| Backend-Tests | `cd backend && python -m pytest` |
| Backend-Health-Check | `cd backend && python manage.py check` |
| Backend-Lint | `cd backend && ruff check .` |
| Frontend-Tests | `cd frontend && npm test` |
| Frontend-Lint | `cd frontend && npm run lint` |
| Frontend-Typecheck | `cd frontend && npm run typecheck` |
| E2E | `npx playwright test` |
| Compose-Config-Verify | `docker compose -f deploy/docker-compose.yml config` |

> Kommando-Varianten (`ruff` vs. `python -m ruff`, `npm test` = Vitest-Run) je
> Projekt-Setup `zu verifizieren`.

### DoD pro Fix

1. **Reproduktion:** bestehender/neu geschriebener Test schlägt **vor** dem Fix fehl.
2. **Fix:** minimaler, fokussierter Change; keine Kollateral-Refactorings.
3. **Nachweis:** derselbe Test ist grün; zusätzlich die im Triage genannten
   Testdateien grün (Proof pro Fix).
4. **Regression-Guard:** bestehende Suite (`pytest` / `npm test` / `npx playwright test`)
   ohne neue Fehler.
5. **Lint/Typecheck:** `ruff`, `npm run lint`, `npm run typecheck` sauber.
6. **Config-Fixes** (1116, 1153, 1145-Compose): Config-Verify + Smoke statt Unit-Test.
7. **Security-Fixes** (1128, 1131): zusätzlich Secret-Scan vor Commit; bei
   AuthZ-Semantikwechsel Doku/ADR-Referenz aktualisieren.
8. **Manifest-Drift** (1147, 1154): `test_tool_manifest_drift.py` grün.

### Per-Fix Proof-Matrix (Auszug)

| Issue | Proof-Test | Typ |
|---|---|---|
| 1145 | `backend/tests/test_version.py`, `reqogniloom/tests/test_health_contract_adr010.py`, `e2e/tests/health-contract.spec.ts` | pytest + Playwright + CI-Gate |
| 1146 | `application/tests/test_attribute_migration_service.py` | pytest |
| 1147 | `mcp_server/tests/test_generic_tool_group.py:509`, `test_tool_groups.py` | pytest |
| 1148 | `llm_adapter/tests/test_llm_adapter.py:461-469` | pytest |
| 1149 | `llm_adapter/tests/test_embedding_providers.py:45` | pytest |
| 1150 | `application/tests/test_audit_service.py:219/239/288` | pytest |
| 1151 | `mcp_server/tests/test_testcase_status_lowercase_453.py` | pytest |
| 1152 | `src/__tests__/state.test.ts:417`, `InterviewFormView.test.tsx:171` | Vitest |
| 1153 | Config-Verify + manueller Smoke | Config/Methodik |
| 1154 | neuer `mcp_server/tests/test_memory_tool_group.py` | pytest |
| 1128 | `application/tests/test_import_idempotency.py`, `rest_api/tests/`, CsvImport Vitest | pytest + Vitest |
| 1129 | `mcp_server/tests/test_goal_tools.py`, `test_goal_lifecycle_issue346.py`, `test_goal_query_delete.py` | pytest |
| 1130 | `reqogniloom/tests/test_cache_dns_bound_res01.py` | pytest |
| 1131 | `rest_api/tests/test_resource_scope_coverage.py`, `auth_tenancy/tests/test_workspace_scope.py`, `test_authorization.py` | pytest |
| 988 | `frontend/src/test/bluepencil-loader.test.ts:230` | Vitest |
| 1112 | `attribute_definitions/tests/test_bootstrap_command.py:344`, `test_bootstrap_relabel_1090.py` | pytest |
| 1115 | E2E-Suite | Playwright |
| 1116 | Compose-Config-Verify + `make up` Smoke | Config/Methodik |

---

## 6. Branch-/Commit-Strategie

- **Branch-Basis:** `main @ 968cfc00`. **Nie** direkt auf `main`/`master` committen
  (Branch-Guard).
- **Ein `fix/*`-Branch pro Welle** off `main`:

| Welle | Branch-Vorschlag |
|---|---|
| Welle 0 | `fix/wave0-ci-release-blocker` |
| Welle 1 | `fix/wave1-beta18-bugs` |
| Welle 2 | `fix/wave2-security-residuals` |
| Welle 3 | `fix/wave3-dev-test-data` |
| Welle 4 | `fix/wave4-honcho-memory` |

- **Commits:** Conventional Commits, Beschreibung Englisch, Imperativ, ≤72 Zeichen
  erste Zeile.
  - Mit REQ-Bezug: `fix(REQ-xxx): ...`
  - Ohne REQ (reine Bugfixes): `fix: ...`
  - Bei 1154 (Feature-Anteil): erst REQ-ID via `requirements`, dann `feat(REQ-xxx): ...`.
- **Commit-Granularität:** ein logischer Fix pro Commit; Tests im selben Commit wie
  der Fix (TDD-Nachweis).
- **PR pro Welle** gegen `main`; PR-Beschreibung verlinkt die enthaltenen Issue-Nummern
  (`Fixes #<nr>` / `Closes #<nr>`) gemäß Issue-Lifecycle.
- **Push/Tag/Branch-Management:** ausschließlich Aufgabe des `git`-Agenten (nicht
  Bestandteil dieses Plans).
- **Secret-Scan** vor jedem Commit (Security Paved Road `secret-scanning`); ein Fund
  blockiert den Commit und ist zu melden.

---

## 7. Risiken & offene Entscheidungen

### 7.1 Decision-Pending (Owner / benötigter Input)

| Issue | Entscheidung | Benötigter Input | Auswirkung bei Verzögerung |
|---|---|---|---|
| **1128** | HMAC vs. SHA-256; IMPORT_CONTRACT_V2 als Default? | ADR-014-Entscheidung + Migrations-Strategie für bestehende Fingerprints | Fix blockiert; Welle 2b wartet |
| **1131** | uniform-404 vs. ADR-013-Semantik akzeptieren? | ADR-013-Interpretation (Security/Owner) | Fix blockiert; Welle 2b wartet |
| **1135** | Django-Admin Brute-Force-Schutz (Dependency `django-axes` fehlt) | **HARD STOP** — Dependency-Sign-off nötig | nicht eingeplant |
| **1136** | RLS-Coverage pre-auth/webhook | ADR-Kandidat + Design-Entscheidung | nicht eingeplant |
| **1097** | MCP `main_goal.query` (Rolle/Governance) | Governance-Entscheidung | out-of-scope |
| **988** | Commit + Close? | Bestätigung, dass Fix bereits erfolgt | reine Verifikation |
| **1153** | Config-Key fehlt vs. Upstream-Defekt | Root-Cause-Analyse Honcho/Dialectic | Welle 4 wartet |

### 7.2 Needs-Info

| Issue | Fehlende Information | Blockiert |
|---|---|---|
| **1117** | Namen der 3 Frontend-Failures (sonst nicht reproduzierbar) | Issue-Triage; out-of-scope |

### 7.3 Duplikate / Cluster

- **1102 ⇔ 1133:** Duplikat (beide `test_mcp_api_key_roles.py`). Ein Issue schließen,
  das andere als Test-Infra-Enhancement führen (nicht Bugfix).
- **1153 / 1154 → #1155:** beide hängen an #1155; 1154 zusätzlich REQ-pflichtig.
- **1146 ⇔ 1112:** gleiche Familie (#940 / Attribut-Migration); Abhängigkeit
  berücksichtigen.
- **1145 blockiert 1146–1154:** zentrale Abhängigkeit (s. §4).

### 7.4 Die 1145-induzierte Messunsicherheit

Solange **1145** (SHA-Label-Mismatch, celery-beat unhealthy, Health-404) offen ist,
sind Version-, Health- und Build-Signale **nicht verlässlich**. Folge:

- Re-Validierung der Fixes aus Welle 1–4 kann **falsch-positiv** (grün auf falschem
  Build/SHA) oder **falsch-negativ** (404 auf funktionierendem Endpoint) ausfallen.
- Deshalb: **Welle 0 zuerst mergen und verifizieren**, bevor Wellen 1–4 als
  „bestätigt" gelten. Bis dahin sind alle Folge-Verifikationen **vorläufig**.

### 7.5 Weitere Risiken

| Risiko | Issue(s) | Gegenmaßnahme |
|---|---|---|
| Daten-migrierende Wirkung (Attribut-Migration) | 1146, 1112 | Idempotenz-Tests; Rollback-Pfad prüfen |
| AuthZ-Semantikwechsel bricht Clients | 1131 | Contract-Doku aktualisieren; breite Testmatrix |
| Compose-/CI-Änderung tangiert andere Services | 1145, 1153, 1116 | Config-Verify + Smoke vor Merge |
| Feature-Anteil ohne REQ | 1154 | REQ via `requirements` vor Implementierung |
| Fehlendes Security-Paket | 1135 | HARD STOP; nicht ohne Sign-off starten |

---

## 8. Self-Review des Plans

- **Vollständigkeit:** Alle 27 triagierten Issues sind in §1 erfasst; die 9
  nicht-Bugfix-Kandidaten sind explizit als `out-of-scope` markiert.
- **Fakten vs. Annahmen:** Dateien/Symbole sind verbatim aus dem verifizierten Triage
  übernommen; unsichere Pfade sind als `zu verifizieren` markiert (Health-Routing bei
  1145; Kommando-Varianten in §5).
- **Messbarkeit:** Jeder In-Scope-Bug hat ein testbares Akzeptanzkriterium (§3) mit
  Proof-Test (§5).
- **Abhängigkeiten:** 1145-Blockade, 1153→1154, Decision-Pending und Duplikate sind in
  §4 und §7 abgebildet.
- **Wellen-Shippability:** Jede Welle ist eigenständig auf eigenem `fix/*`-Branch
  off `main` mergebar; keine Commits auf `main`.
- **Nicht implementiert:** Dieser Plan enthält **keine** Code-Änderungen und löst
  **keine** Commits/Pushes aus.
