# Daten-Lifecycle-Katalog (S5.3 WP-2)

> **Owner:** `database-engineer` · **Sunset-Koordination:** `devops-engineer`
> **Status:** interne Referenz (Ist-Zustand, kein Implementierungsauftrag) · **Stand:** Commit `f60697d`
> **Normreferenzen:** ISO 15489-1 (Records Management), DSGVO Art. 5(1)(e) (Speicherbegrenzung),
> [ADR-012](../../se/ADR/ADR-012_backup_wahrheit.md) (Backup als verbindliche Quelle),
> [ADR-014](../../se/ADR/ADR-014_import_erfolgssemantik_idempotenz.md) (Idempotenz/Outbox).

## Zweck

Dieser Katalog schließt die von der Deep-Dive-Auditierung 2026-11-16 benannte Lücke
„Data lifecycle / decommissioning policy": *„No dimension asks 'when does this go away?' …
Need a sunset register (owner, date, removal criterion) per API/flag/dep/artifact class."*
(`docs/audit/2026-11-16-deep-dive-findings.md:1139`). Er dokumentiert **nur** den bestehenden
Ist-Zustand. Es werden keine Löschlogik, keine Migrationen und keine Abhängigkeiten geändert.

Alle `file:line`-Angaben wurden am Base-Commit `f60697d` durch Lesen der Quellen verifiziert.

## Artefaktklassen

| Artefakt | Creator | Retention | Export-Pfad | Löschmechanismus (Command / Beat-Task + `file:line`) | Status | Owner | Entfernungskriterium (bei Deprecation) |
|---|---|---|---|---|---|---|---|
| **AuditLog / AuditEntry** | `audit/events.py:124` (`AuditableOperationOccurred.publish`); Modell `audit/models.py:88` | 2 Jahre (`AUDIT_RETENTION_YEARS`, Default 2; `audit/archive.py:54,73`); Export **vor** Löschung | Cold Storage via `ColdStorageAdapter` / `ExportOrchestrator` (`audit/archive.py:211,286`), `IF-AL-EXT-OUT-001` | Beat `audit-monthly-archive`, `crontab(day_of_month=1, hour=0, minute=0)` (`backend/reqogniloom/settings.py:1279-1282`); `ArchiveLifecycleManager.run_monthly_archive` (`audit/archive.py:406`); `PartitionDropper.drop_partition` → `SELECT audit_ops.purge_entries_before(%s)` (`audit/archive.py:346,349`); No-Op mit Warning ohne `AUDIT_COLD_STORAGE_BACKEND` (`audit/archive.py:418`) | **defective → S0.3 L0-001** (Audit-Finding `docs/audit/2026-11-16-deep-dive-findings.md:86,105`). Remediation-Code (Migration `audit/migrations/0020_retention_purge_function.py:1`, Test `audit/tests/test_archive_retention.py:105`) liegt im Base `f60697d`; Formalabschluss liegt bei **S0.3**, nicht bei diesem Katalog | `database-engineer` (Schema/Retention), `security-auditor` (Audit-Compliance) | n/a — nicht deprecated; Entfernung nur nach Ablauf der 2-Jahres-Frist und bestätigtem Export |
| **DomainEventOutbox** | `application/event_bus.py:577` (`publish`), `application/models.py:45` | Bis zum Dispatch; `published=True` + `published_at` (`event_bus.py:920`). Kein eigenständiger Purge für publizierte Zeilen | Kein Export; Replay/Wiederherstellung über `DomainEventDLQ` (`application/dlq_service.py`) | Beat `dispatch-outbox-events` alle 5 s (`settings.py:1275-1278`, Task `application/tasks.py:37`); DLQ-Move löscht die Outbox-Zeile (`event_bus.py:959`). **Keine Retention-Regel für `published=True`** | **works** (Dispatch) — Retention-Lücke ohne eigene Finding-ID; verwandt mit `docs/audit/2026-11-16-deep-dive-findings.md:1141` (Observability), von **S2.x** zu entscheiden | `application` / Architektur (COMP-AS-016) | n/a |
| **Baseline / BaselineSnapshot** | `baseline/models.py:37`, Service `baseline/services.py` | Unbegrenzt (bewusst, Audit-Trail); 3 Scopes Document/Project/Global (ADR-07); Soft-Delete via `lifecycle_status` | MCP `baseline.*` (Diff/Rollback), Snapshot-Diff in `baseline/services.py` | Keine automatische Löschung; `cleanup_e2e_artifacts` überspringt Workspaces **mit** Baseline (`persistence/management/commands/cleanup_e2e_artifacts.py:55-70`) | **works** (manuell, keine Auto-Löschung) | `database-engineer` / Baseline-Owner | n/a — historische Snapshots sind Aufbewahrungsgut nach ISO 15489-1 |
| **Requirement / ArchitectureElement / TestCase (generisches Artifact)** | `persistence/models.py:1291` (`Artifact`) | Lebenslang im Workspace; Soft-Delete via `outdate()` (`lifecycle_status`), kein automatisches Purge | REST `/api/v1/<entity>/` inkl. `/versions/`, `/history/`, `/workflow-history/` (`rest_api/mixins/workflow_transitions.py:645`); ReqIF 1.2 / CSV / PDF via `application/export_service.py:244` | Soft-Delete durch Workflow `outdate()`; Workspace-Löschung via `WorkspaceService.delete_workspace`; E2E-Workspaces via `cleanup_e2e_artifacts` (`persistence/management/commands/cleanup_e2e_artifacts.py:110,144`) | **works** | `application` / Backend | n/a |
| **MemoryEntry** | `memory/models.py:37` | Unbegrenzt; `superseded_by` markiert ersetzte Fakten ohne Löschung (`memory/models.py:63`). Konsolidierung (Dream) mit `MEMORY_CONSOLIDATION_INTERVAL_MINUTES`, `0` = OFF (`settings.py:1263-1272`, `memory/tasks.py:528,658`) | MCP `memory.digest` / `memory.search` / `memory.ask` / `memory.admin`; pgvector (optional Honcho/Qdrant) | Keine automatische Löschung; Konsolidierung erzeugt neue Fakten, löscht keine | **works** (Konsolidierung konfigurierbar, `0` = OFF; `settings.py:1310-1322`) | `memory` / AI | n/a |
| **API-Keys** | `auth_tenancy/models.py:113` (`ApiKey`), Präfix `reqlo_*` (niemals committen) | Bis Widerruf (`revoked_at`), dann 30 Tage (`cleanup_revoked_api_keys.py:58`) | Keine — Secrets werden nie exportiert | `python manage.py cleanup_revoked_api_keys --apply --older-than-days=30` (Dry-Run Default; `auth_tenancy/management/commands/cleanup_revoked_api_keys.py:62,85,110`); RLS-Preauth-GUC erforderlich (`:22`) | **works** | `auth_tenancy` / `security-auditor` | 30 Tage nach `revoked_at` |
| **Refresh-Tokens** | `auth_tenancy/models.py:198` (`RefreshToken`), `auth_tenancy/services/refresh_token_store.py` | Bis `expires_at` + 1 Tag Grace (`cleanup_expired_refresh_tokens.py:44`) | Keine | `python manage.py cleanup_expired_refresh_tokens --apply --grace-days=1` via `SECURITY DEFINER` `public.auth_purge_expired_refresh_tokens` (`auth_tenancy/management/commands/cleanup_expired_refresh_tokens.py:20,82`) | **works** | `auth_tenancy` / `security-auditor` | 1 Tag nach `expires_at` |
| **Idempotency-Records (`ImportIdempotencyRecord`)** | `application/import_idempotency.py:291`; Migration `application/migrations/0028_import_idempotency_record.py` | TTL 24 h (`IMPORT_IDEMPOTENCY_TTL_HOURS`, `import_idempotency.py:76`); ADR-014 | Keine | Beat `cleanup-import-idempotency`, `crontab(minute=0)` = stündlich (`settings.py:1289-1292`, ADR-014 §3); Task `application/tasks.py:312`; `purge_expired()` `application/import_idempotency.py:432,441` | **works** | `application` / `api-specialist` (ADR-014) | Nach `expires_at` (TTL × Rate, ADR-014) |
| **E2E-Artefakte (Test-Workspaces)** | E2E-Suite `e2e/helpers/auth.ts`, Namensprefix `e2e-` | Default 1 Tag (`cleanup_e2e_artifacts.py:106`) | Keine | `python manage.py cleanup_e2e_artifacts --apply --older-than-days=1 --name-prefix=e2e-` (Dry-Run Default; `persistence/management/commands/cleanup_e2e_artifacts.py:110,144`); überspringt Workspaces mit Baseline (`:69`) | **works** | `e2e-tester` / `devops-engineer` | 1 Tag nach `created_at` (nur Prefix `e2e-`) |
| **Workflow-/Workspace-Orphans** | Verwaiste `we_item_state` / `we_engine_definition` und Typ-Definitionen nach Workspace-Löschung | Keine Aufbewahrung — sofort bereinigbar | Keine (Archiv-Tabellen/rc-Kopie im Lösch-Transaction) | `python manage.py cleanup_workflow_orphans` (`workflow/management/commands/cleanup_workflow_orphans.py:65,100`, `DELETE … WHERE NOT EXISTS`, idempotent); `python manage.py cleanup_workspace_orphans --confirm-count=<n>` (Archiv + Delete, `workflow/management/commands/cleanup_workspace_orphans.py:92,196`) | **works** | `workflow` / `database-engineer` | Beim nächsten Cleanup-Lauf, wenn `NOT EXISTS`-Prüfung 0 Treffer meldet |
| **Generation-/Cache-Keys (Redis)** | `application/ai_derivation_service.py:557,561` (`llm_derivation`, `llm_derivation_ver`) | Result 1 h (`DERIVATION_CACHE_TTL_SECONDS = 3600`, `:545`); Generation-Counter 24 h (`DERIVATION_VERSION_TTL_SECONDS`, `:554`) | Keine | TTL-Expiry durch Redis; kein Beat-Task | **defective → S2.x PERF-009** (Audit-Finding `docs/audit/2026-11-16-deep-dive-findings.md:608`: `cache.set(..., None)` = never-expiring counter). Remediation (`DERIVATION_VERSION_TTL_SECONDS` + Test `application/tests/test_derivation_cache_ttl.py:62`) liegt im Base `f60697d`; Formalabschluss liegt bei **S2.x** | `performance-optimizer` / AI, **S2.x** | TTL von 24 h nach letzter Invalidation/letztem Read |
| **Datenbank-Backups (Sidecar)** | `postgres-backup`-Sidecar (`deploy/docker-compose.yml:408-427`), `pg_dump` → gzip | `BACKUP_RETENTION=7`, `BACKUP_INTERVAL=21600` s (6 h) → **42-h-Horizont** (`docs/se/ADR/ADR-012_backup_wahrheit.md:65`, `deploy/docker-compose.yml:418,422`) | Restore über `scripts/restore.sh` (ADR-012: Sidecar-Dump ist verbindliche Quelle) | Automatisches Pruning auf die neuesten `BACKUP_RETENTION` Dumps (`deploy/docker-compose.yml:362`); fehlgeschlagene Dumps werden verworfen (`:400`) | **works** (Restore 15/15 Tabellen verifiziert, ADR-012) | `database-engineer` / `devops-engineer` | Älter als `BACKUP_RETENTION` → automatisch geprunt; Off-Host-Kopie laut ADR-012 weiter offen |

### Hinweise zur Statusbewertung

- Die drei als **defective** markierten Einträge stammen aus dem Audit-Bericht 2026-11-16.
  Der Base-Commit `f60697d` enthält bereits Remediation-Commits (`7d6593a3`, `2fd379f1`,
  S5.1-Merge `#1916`) samt Regressionstests. **Dieser Katalog erklärt diese Findings nicht
  für geschlossen** — der Formalabschluss (Finding-Status im Audit-Tracking) liegt bei den
  Ownern **S0.3** (L0-001), **S2.x** (PERF-009) und **S5.1** (DEP-008). Defekte Mechanismen
  werden hier ausdrücklich **nicht** als „works" geführt.
- Die Einträge DomainEventOutbox / Baseline / MemoryEntry haben bewusst **keine** automatische
  Aufbewahrungsgrenze. Das ist eine fachliche Entscheidung (Audit-Trail / historische Fakten),
  keine Defektmeldung; eine spätere Retention-Policy ist von den jeweiligen Ownern zu definieren.

## Sunset-Register (Deprecated Items)

| Item | Deprecation-Nachweis | Sunset-Datum / -Regel | Entfernungskriterium | Owner / zuständiger Slice |
|---|---|---|---|---|
| `/api/v1/mcp/` (MCP-Alias) | `backend/reqogniloom/urls.py:81-87`; `Deprecation: true`, `Sunset`, `Link: </mcp/>; rel="alternate"` (`backend/mcp_server/views.py:102,119-123`) | `MCP_LEGACY_PATH_SUNSET`, Default `2027-04-01` (`mcp_server/views.py:102`) | Nach Ablauf des Sunset **und** 0 Traffic über den Alias (Reverse-Proxy-Logs) → `path("api/v1/mcp/", …)` in `urls.py` entfernen; kanonisch bleibt `/mcp/` | `devops-engineer` (Koordination) + `api-specialist` |
| `/health/` (Alias für `/health/ready`) | `backend/reqogniloom/urls.py:42`, ADR-010 §3 (`docs/se/ADR/ADR-010_health_vertrag.md`) | Kein hartes Datum | Keine gemeldeten Consumer mehr auf `/health/` → `HealthAliasView`-Route entfernen | `devops-engineer` |
| `headroom-ai` (ungenutzte Root-Dependency) | Audit-Finding **DEP-008** `docs/audit/2026-11-16-deep-dive-findings.md:509`; kein Code-Import | Bereits entfernt im Base `f60697d` (S5.1, PR #1916) | Erfüllt: aus `package.json`/`package-lock.json` entfernt; Guard `scripts/tests/test_root_manifest_hygiene.py:1,20` verhindert Regression. Formalabschluss durch **S5.1** | `devops-engineer` / **S5.1** |
| Stale SE-/Status-Dokumente | Audit-Findings **DOC-002 / DOC-006** `docs/audit/2026-11-16-deep-dive-findings.md:84,693,697` (`docs/features/mobile-and-pwa.md:10-11`, `docs/plans/mobile-baseline-2026-11.md:46-47`, `docs/superpowers/specs/index.md:17`, `docs/features/index.md:6,13-17`, `docs/plans/index.md:3-12`) | Beim nächsten Docs-Refresh | „pending commit"-Wording durch echte Commit-Hashes (`4aa5f956`, `fbb95e86`, `fe9ae303`) ersetzen; beide Indexe auf `1.9.0-beta.2` anheben | `documenter` / `knowledge-curator` |
| 143+ frontmatter-lose, unowned Dokumente | `docs/audit/2026-11-16-deep-dive-findings.md:1139` | Kein Datum — Inventar offen | Pro Dokument `owner`, `status`, `date` im Frontmatter ergänzen **oder** archivieren; danach aus dem Inventar streichen | `documenter` / `knowledge-curator` |
| Backup-Retention (42-h-Horizont) | ADR-012 `docs/se/ADR/ADR-012_backup_wahrheit.md:65`; `deploy/docker-compose.yml:362,418,422` | `BACKUP_RETENTION=7` × 6 h | Dumps älter als `BACKUP_RETENTION` werden automatisch geprunt; Off-Host-Kopie gem. ADR-012 separat zu entscheiden | `database-engineer` / `devops-engineer` |

## Verifikation

- Quellen aller zitierten `file:line`-Angaben am Commit `f60697d` gelesen (Base des Worktrees
  `fix/s5-3-ops-maturity`). Abweichungen zu den übermittelten Gate-Fakten: Memory-Konsolidierung
  ist `settings.py:1263-1272` / `1302-1322` (nicht `1263-1262`); MCP-Alias-Block ist
  `urls.py:81-87` (nicht exakt `82-86`). Alle anderen Angaben stimmen mit dem Code überein.
- **Keine** Code-, Löschlogik-, Migrations- oder Dependency-Änderung. Ausschließlich diese
  Datei wurde angelegt.
