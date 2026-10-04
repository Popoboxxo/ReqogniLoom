---
type: PLAN
scope: audit-review-2026-09-data-recovery
status: final
date: 2026-10-01
author_agent: planner
epic: DATA — Datenintegrität & Recovery
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic DATA — Datenintegrität & Recovery

> Detailplan. `345` wird ausschließlich als Duplikat von `123` geführt. **Aufwand:**
> verbindliche PT-Spannen in `plan/EFFORT_ESTIMATES.md` §1; die `Aufwand: S/M/L`-Angaben
> hier sind nur Groborientierung.

## DATA-01 — ADR + Restore-Pfad funktionsfähig & atomar (P0, W1)

- **Findings:** 123, 127, 345 (=123)
- **Ort:** `scripts/restore.sh:183,186,198-201` (Datei nie in Container kopiert; `psql -f`
  liest Datei statt stdin); `:183,198,206` (`--clean --if-exists` in-place, nicht atomar)
- **Zielverhalten:** **ADR (iii) entscheidet** Quelle; danach: Restore kopiert die Backup-Datei
  in den Container bzw. streamt korrekt, spielt atomar in eine Zieldatenbank, mit
  definiertem Formatvertrag. `REQ-L2-BL-011` wird bis dahin ehrlich auf `Not Implemented`
  gesetzt (Zuordnung in `DOC-01`).
- **Akzeptanz:** `restore.sh`-Smoke reproduziert **15/15** Tabellenzahlen aus einem Sidecar-Backup;
  ein absichtlicher Fehler lässt keine halb-restaurierte DB zurück.
- **Test:** CI-Restore-Smoke gegen Test-Stack; Regressionstest fängt den `/tmp/backup.*`-Fehler.
- **Aufwand:** M · **Risiko/Rollback:** Restore überschreibt Daten → Test-DB/Volume,
  Bundle vorher; reversibel. · **Deps:** ADR iii · **ADR:** schreibt (iii)

## DATA-02 — Backup-Format/Ort, Off-Host, Retention, Medien (P0, W1)

- **Findings:** 122, 124, 128 (345/122-Kontext)
- **Ort:** `scripts/backup.sh:84-87` (`exit 1`, toter Legacy-Pfad);
  `scripts/restore.sh:49,116` (`./backups` `.dump`/`.sql`) vs. `compose.yml:372,405`
  (`.sql.gz` im Volume); `compose.yml:357,361` (42-h, kein Off-Host), 0 Medien-Volume
- **Zielverhalten:** Format-/Ortsvertrag definiert; `backup.sh` entweder repariert oder als
  deprecated entfernt; Retention/Off-Host/Verschlüsselung konfigurierbar; Medien/Uploads
  im Scope.
- **Akzeptanz:** Backup erscheint am dokumentierten Ort im erwarteten Format; Restore findet
  es; ein Off-Host-Ziel ist konfigurierbar.
- **Test:** CI-Backup-/Restore-Smoke; Format-Assertion.
- **Aufwand:** M · **Risiko/Rollback:** Retention/Off-Host-Fehlkonfiguration → Defaults,
  reversibel. · **Deps:** DATA-01 · **ADR:** iii

## DATA-03 — State-Bypass + Version-Bump (P0, W1)

- **Findings:** 167, 168, 169, 170, N7, 282
- **Ort:** `application/import_service.py:714-722` (CSV `WorkflowItemState.create` ohne Transition);
  `reqif_import_service.py:789-793` (kein `version`-Bump trotz State-Änderung);
  `rest_api/interview_views.py:245-257` + `interview_service.py:269-293,336-344,354,367-369`
  (GET mutiert, `except Exception`, Version-Bump ohne Stateänderung);
  `lifecycle_manager.py:416-477` (`force_transition` ohne Rolle/Gate);
  `views.py:6063` (`/adrs/{pk}/supersede/`) und `:7471` (`/change-requests/{pk}/transition/`)
  (kein `expected_version`)
- **Zielverhalten:** State-Übergänge laufen über die Transition-Validierung oder setzen
  mindestens `version` CAS-korrekt; GET ist nebenwirkungsfrei; `force_transition` erzwingt
  Rolle/Begründung; die zwei Sonderrouten akzeptieren `expected_version` (kein
  Last-writer-wins).
- **Akzeptanz:** ReqIF-/CSV-Import erhöht `version`; `GET /interviews/{id}/state/` ändert
  keinen DB-Zustand; Sonderrouten liefern bei Versionskonflikt **409**.
- **Test:** pytest (je Pfad ein Regressionstest, der den Bypass fixiert).
- **Aufwand:** L · **Risiko/Rollback:** zu strenge Gates brechen Importe → schrittweise,
  Test-Workspace. · **Deps:** — · **ADR:** —

## DATA-04 — `Goal.sequence_number` UNIQUE + Lock (P0, W1)

- **Findings:** 281
- **Ort:** `persistence/models.py:3376-3381` (`Goal.Meta` ohne `constraints`);
  `application/goal_service.py:134-149` (`MAX+1` ohne `select_for_update`); Live kein UNIQUE
- **Zielverhalten:** `UNIQUE(lineage_id, sequence_number)` analog `as_main_goal` + Lock beim
  Ziehen der nächsten Nummer.
- **Akzeptanz:** Migration angelegt; paralleler Doppel-Insert erzeugt keinen doppelten Wert;
  DB-Constraint live nachweisbar.
- **Test:** pytest (Race-Simulation) + DB-Constraint-`SELECT`.
- **Aufwand:** S–M · **Risiko/Rollback:** Bestandsdaten mit Duplikaten → Daten-Audit vor
  Migration, reversibel. · **Deps:** — · **ADR:** —

## DATA-05 — Self-Link + `link_type`-CHECK (P1, W2)

- **Findings:** 157, 182
- **Ort:** `traceability/trace_link_manager.py:372-377` (Zyklus pro Typ, kein Self-Guard);
  `link_types/catalog.py:98-152`; live `pl_tracelink` ohne `CHECK(source_id<>target_id)`
- **Zielverhalten:** Self-Links werden abgelehnt (App + DB-CHECK); `link_type` DB-seitig
  eingeschränkt (CHECK/Enum/FK).
- **Akzeptanz:** Self-Link ⇒ 4xx; `pg_constraint` enthält den CHECK.
- **Test:** pytest + DB-Constraint-`SELECT`. · **Aufwand:** S · **Risiko/Rollback:**
  Bestands-Self-Links → Datenprüfung, reversibel. · **Deps:** — · **ADR:** —

## DATA-06 — `we_item_state` Workspace-FK + State-CHECK (P1, W2)

- **Findings:** 171, 180, 186, 227
- **Ort:** live `we_item_state` ohne `workspace_id`-FK und ohne `CHECK(current_state∈states)`;
  `pl_artifact`/`pl_requirement` **haben** FK (180-Prämisse widerlegt — nur die übrigen
  zentralen Tabellen nachrüsten)
- **Zielverhalten:** `we_item_state` (und benannte Leidtragende) erhält Workspace-FK;
  State-CHECK gegen die Definition.
- **Akzeptanz:** `pg_constraint` zeigt FK + CHECK; Test weist ungültigen State ab.
- **Test:** pytest + DB-`SELECT`. · **Aufwand:** M · **Risiko/Rollback:** Bestandsverletzer →
  Datenmigration mit Prüfung, reversibel. · **Deps:** SEC-01 (ii) · **ADR:** ii

## DATA-07 — RLS-Deckung (P1, W2)

- **Findings:** 184, 227, 185, N1
- **Ort:** `as_domain_event_outbox`, `as_domain_event_dlq`, `as_webhook_subscription`,
  `as_webhook_delivery_log` (kein `tenant_id`, keine RLS); `at_api_key`/`at_user_role`/`audit_entry`
  dokumentierte Ausnahmen (`auth_tenancy/migrations/0011:43-64`); `bl_delta_index_entry`
  **hat** RLS (184-Korrektur)
- **Zielverhalten:** Ausnahmen bleiben benannt (Pre-Auth-Chicken-Egg), aber Webhook-/Outbox-Tabellen
  erhalten Tenant-Zuordnung + RLS; `RLS_EXEMPT_TABLES` bleibt zentral gepflegt.
- **Akzeptanz:** `pg_class.relrowsecurity` deckt die 4 as_*-Tabellen; Ausnahmeliste und
  `test_rls_coverage.py` konsistent.
- **Test:** pytest (RLS-Coverage-Test) + Live-`pg_class`. · **Aufwand:** M ·
  **Risiko/Rollback:** RLS auf Pre-Auth-Tabellen = Outage → sorgfältige Trennung,
  reversibel. · **Deps:** SEC-01 (ii), SEC-04 (N1) · **ADR:** ii

## DATA-08 — TestCase-Tag-Rückstände + Frontend-Route (P1, W2)

- **Findings:** 181, 189
- **Ort:** `persistence/migrations/0093:76-78`; `mcp_server/tools/tests.py:206`;
  `frontend/src/utils/artifactRoutes.ts:17-44,50-52`
- **Zielverhalten:** `TestCase:<Type>`-Tags migrieren/konsistent halten; Frontend-Route mappt
  getaggte TestCases auf `/testcases`.
- **Akzeptanz:** 0 verbleibende getaggte Artefakte bzw. dokumentierter Bestand; Route zeigt
  korrekt. · **Test:** pytest + Frontend-Unit-Test. · **Aufwand:** S · **Risiko/Rollback:**
  Datenmigration → reversibel per Migration. · **Deps:** — · **ADR:** —

## DATA-09 — Outbox-Idempotenz der 3 realen Abonnenten (P1, W2)

- **Findings:** N3
- **Ort:** `application/event_bus.py:476-479` (at-least-once gefordert); Abonnenten
  `ContextGraphProjector`, `MemoryProjector`, `WebhookDispatcher`
- **Zielverhalten:** Doppel-Zustellung desselben `event_id` erzeugt keinen zweiten
  Schreibeffekt (`get_or_create`/Dedup-Fenster).
- **Akzeptanz:** Test injiziert dasselbe Event 2× je Abonnent ⇒ genau 1 Wirkung.
- **Test:** pytest (je Abonnent). · **Aufwand:** M · **Risiko/Rollback:** verpasste
  Zustellung bei zu strengem Dedup → Fenster/Retention, reversibel. · **Deps:** ADR v ·
  **ADR:** v

## DATA-10 — Preset-SSOT / Fail-open-Gate (P1, W3)

- **Findings:** 160, 162, 161, 175
- **Ort:** `presets/registry.py:13` (SSOT-Docstring), `:129`; `presets/gate.py:536-549`
  (`except: pass`); `stage_matrix.py:41-45,887,907,921,926`; ≥6 Module
- **Zielverhalten:** **ADR (vi) entscheidet** SSOT-Grad; der Downgrade-Blocker geht auf
  **fail-closed**; Docstring wird wahr.
- **Akzeptanz:** Fehler im Persistence-Layer führt **nicht** zum stillen Überspringen des
  Downgrade-Checks; `gate.py`-Test deckt den Ausfall ab.
- **Test:** pytest (Gate-Fehler → blockiert). · **Aufwand:** M · **Risiko/Rollback:**
  fail-closed kann legitime Testkontexte brechen → explizite Test-Konfiguration. ·
  **Deps:** ADR vi · **ADR:** vi
