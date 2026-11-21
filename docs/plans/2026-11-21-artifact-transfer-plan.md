---
type: PLAN
title: "Import/Export, Backup/Restore und vollständige Workspace-Kopie für alle Artefakte"
status: in_progress
date: 2026-11-21
author_agent: planner
language: de
branch_basis: "origin/main d000094f (v1.9.0-beta.5)"
---

# Import/Export, Backup/Restore und vollständige Workspace-Kopie für alle Artefakte

**Goal:** Jeder Artefakttyp im System ist exportierbar und wieder importierbar — in denselben Workspace (aktualisierend/überschreibend) oder in einen neuen Workspace als echte Datenkopie. Backup/Restore wird zu einem geprüften Ziel-Instanz-Restore ausgebaut.

**Architecture:** Django 6.1+/DRF (Application-Services als einzige Domänefassade), React 19 SPA, Celery für große Exporte, `ARTIFACT_TYPE_MODELS` als kanonische Typ-Registry, `ENTITY_FIELD_SPECS` als heutiges Import/Export-Feldregister, ReqIF 1.2 als standardkonformes Interchange-Format, versioniertes ZIP als Voll-Snapshot.

**Tech Stack:** Python/Django ORM + `dumpdata`/`loaddata`, DRF, drf-spectacular, Celery/Redis, pytest, Playwright (4 Shards), Vitest, ReqIF 1.2 (OMG formal/16-07-01).

---

## 1. Auftrag und Zielbild

1. Export: jeder der 24 REST/MCP-Entitäten ist über mindestens einen erreichbaren Transport exportierbar — mit den Feldern und Relationen, die einen Rückimport erlauben.
2. Import: jeder exportierte Typ ist wieder importierbar, in denselben oder einen neuen Workspace, als Datenkopie mit ID-/FK-Remapping.
3. Kopie: `clone_workspace` kopiert alle Entitäten und alle Relationen in einen neuen oder vorhandenen Workspace.
4. Backup/Restore: konsistenter, checksum-geprüfter Round-Trip; Restore in eine Zielinstanz mit definierten Optionen; `pg_dump`-Sidecar bleibt DR-Wahrheit (ADR-012).

## 2. Verifizierte Ist-Analyse

### 2.1 Type-Registries (Drift)

| Registry | Ort | Umfang |
|---|---|---|
| `ARTIFACT_TYPE_MODELS` | `backend/persistence/artifact_backing.py:33` | 15 artefaktgestützte Typen (kanonisch) |
| `ITEM_TYPES` | `backend/attribute_definitions/_schema_vocabulary.py:20` | 12 |
| `ENTITY_FIELD_SPECS` | `backend/application/export_service.py:110` | 7 (CSV/JSON/MD/PDF + Import) |
| REST CSV-Import | `backend/rest_api/views_io.py:777` | 3 |
| REST CSV-Export | `backend/rest_api/views_io.py:1061` | 4 |
| REST ReqIF | `backend/rest_api/views_io.py:1278` | 4 akzeptiert, 2 wirksam |
| Frontend | `frontend/src/components/CsvImport/CsvImport.tsx:57` | 3 Import / 3 Export |
| `ENTITY_SPECS` | `backend/mcp_server/tests/entity_surface_matrix.py:85` | 24 REST/MCP-Entitäten |

Folge: StakeholderNeed, Adr, Risk, Issue sind im Service exportierbar, aber per REST/UI nicht importierbar. Goal, Icd, GlossaryTerm, ChangeRequest, Document, MainGoal, Diagram, WorkItem haben keinen CSV-Pfad. Es existiert kein Gate-Test, der die Listen abgleicht.

### 2.2 Import

- CSV: `ImportService` (`backend/application/import_service.py:843,903`) — 7 Typen, atomar, 1000 Zeilen, Idempotency-Key (v2-gegatet), kein Dry-Run (`:407` hardcodet `dry_run: False`), Duplikate werden geskippt (`:1125`).
- ReqIF: `backend/application/reqif_import_service.py:982` — nur StakeholderNeed + Requirement (+ SPEC-RELATION → TraceLink), 5000 SPEC-OBJECTS, per-Item-Savepoints (Teilerfolg 207), Dry-Run vorhanden (`:900`), stillschweigendes Update bei divergentem Identifier (`:857`).
- Bundle: export-only (`backend/application/requirement_bundle_service.py`); MCP: kein Artefakt-Import; Admin-Restore: destruktiver Full-DB-`loaddata`.
- ReqIF-Feldverlust: `ATTR-TIER-KEY`/`ATTR-TIER-NAME` (`reqif_export_service.py:260`) sind nicht im Import-Mapping (`reqif_import_service.py:212`); zusätzlich `level`, `complexity_fibonacci`, `suspect`, `lifecycle_status`, Identität/Audit.

### 2.3 Export

- `ExportService` (`backend/application/export_service.py:322-536`): JSON/CSV/Markdown/PDF, aber JSON/MD/PDF ohne Transport; `list(qs)` ohne Row-Cap (`:616`).
- ReqIF (`reqif_export_service.py`): Need + Requirement + TraceLinks untereinander, Custom-Fields als opakes JSON, Hierarchie-Flattening.
- PDF-Report (`backend/traceability/pdf_report_generator.py`): Req/AE/TC/TraceLinks, 2 Layouts.
- Requirement-Bundle: nur Requirement, extended/custom explizit ausgeschlossen (`requirement_bundle_service.py:560`).
- Memory/VCRM/Diagram/Config-Exporte sind Spezialpfade, keine Artefakt-Exporte.
- ~17 Entitäten ohne Exportpfad: TestRun, GlossaryTerm, Goal, MainGoal, ChangeRequest, Icd, Document, WorkItem, Milestone, InterviewSession, Baseline, Comment, Notification, QualityAssessment, Suggestion, Artifact(self), WorkspaceLinkType.

### 2.4 Backup/Restore

- App-Backup (`backend/admin_ops/services/backup_service.py:56-198`): `dumpdata` → gzip → `.json.gz`, SHA-256, `BackupMetadata` (pending/completed/failed), REST `/api/v1/admin/backups/`, MCP `admin.backup_*`, UI, Django-Admin. Deckt alle DB-Zeilen ab (auch Secrets, Audit, Embeddings).
- App-Restore (`backend/admin_ops/services/admin_restore_service.py:10-29,131-270`): `loaddata` als **PK-Upsert-Overlay in dieselbe Instanz** — keine Löschung neuerer Zeilen, kein Ziel-Parameter, kein ID-Remapping, kein Dry-Run, Checksum wird nicht geprüft, `restore_type` nur advisory. Finding **EXT-004** (`docs/audit/2026-11-16-deep-dive-findings.md:252`).
- Kein echter Round-Trip-Test: `fake_loaddata` stubbt den Schreibpfad (`backend/admin_ops/tests/test_admin_restore_service.py:44`), der „loadable"-Test nutzt ein leeres Array (`backend/admin_ops/tests/test_backup_service.py:179`).
- Sidecar (`deploy/docker-compose.yml:357-507`, `docs/se/ADR/ADR-012_backup_wahrheit.md`) ist laut ADR-012 die DR-Wahrheit (`pg_dump`, Retention, Offhost, Atomar-Restore-Runbook) — parallele App-Pfad-Exposition ist „zwei Wahrheiten".
- `WorkspaceService.clone_workspace` (`backend/application/workspace_service.py:406-618`) kopiert nur Workspace+PresetConfig, Creator-Rolle, Defaults, Artifact, Requirement, ArchitectureElement, TestCase, TraceLink. Alle anderen Typen fehlen.

### 2.5 ReqIF-Standard (Best Practice)

OMG ReqIF 1.2 ist ein **Austauschformat für Organisationen ohne gemeinsames Repository**, kein Synchronisationsprotokoll. Der Standard definiert Datenmodell (SpecObject/SpecRelation/Specification, GUIDs) und einen Workflow zur Statusübermittlung zwischen Partnern; Merge/Delete/Replace sind werkzeugseitig. Es gibt keinen standardisierten „lösche alles, was nicht im File vorkommt". Daher: nie physisch löschen, sondern GUID-basiert wiedererkennen und Status übermitteln.

## 3. Findings

| ID | Priorität | Finding |
|---|---|---|
| F1 | P0 | Vier auseinanderdriftende Allowlists; kein Konsistenz-Gate |
| F2 | P0 | 4 Service-Typen per REST nicht importierbar; ~18 Typen ohne Importpfad; ReqIF-Feldverlust; kein CSV-Dry-Run; uneinheitliche Overwrite-Semantik |
| F3 | P0 | ~17 Typen ohne Exportpfad; JSON/MD/PDF ohne Transport; keine Fidelity für Relationen/Embeddings/Historie; kein Row-Cap/Streaming |
| F4 | P0 | App-Restore ist Upsert-Overlay ohne Ziel/Checksum/Dry-Run/RLS-Test (EXT-004) |
| F5 | P0 | Clone kopiert nur 6 Entitätstypen — keine Datenkopie „aller Artefakte" |
| F6 | P1 | Keine Matrix-Tests „Typ × Format × Zielmodus"; keine E2E für CSV/ReqIF-Download, Snapshot, Copy, Restore |

## 4. Getroffene Entscheidungen

| ID | Entscheidung |
|---|---|
| D1 | Upsert-Schlüssel: `uid` + Typ + Workspace, `id` bevorzugt bei Identität |
| D2 | Konflikte: `version-guard` Default, `update` explizit, `skip`/`error` optional |
| D3/D3b | **Nie löschen**; `reconcile_status` mit typ-spezifischem Status (z. B. Requirement→`outdated`, TestCase→`deprecated`) + `not_in_source`-Flag |
| D4 | Fehlt `target_workspace_id`: neuer Workspace wie `clone_workspace` (Preset/Workflow-Defaults + Creator-Admin) |
| D5 | Dry-Run optional, Pflicht bei Rekonziliation/Cross-Tenant, voller Diff (`counts`, `conflicts[]`, `planned_remaps[]`) |
| D6 | All-or-nothing Default, `partial=true` explizit; ein `ImportResult`-Envelope |
| D7 | Idempotenz pro `(target_workspace, key)`, Fingerprint inkl. Ziel |
| D8 | Umfang: **alle 24 REST/MCP-Entitäten** |
| D9 | Neue IDs + `source_id` (Remap aller FKs/M2M) |
| D10 | **Alle Relationen**, inkl. Comments und TestRuns |
| D11 | Custom Fields validieren; Attribute-Definitionen nur bei neuem Workspace mitkopieren |
| D12 | Alle exportierten Felder autoritativ; **D12b**: `tenant_id`/`workspace_id`/`artifact_id`/FK-Ziele werden immer remappt |
| D13 | Ausschluss: Audit, Secrets, globale Definitionen, externe Stores |
| D14 | ReqIF standardkonform; ZIP-Voll-Snapshot; alle anderen Formate für alle Typen; große Daten |
| D14a | ZIP: `manifest.json` + JSONL pro Entität + Relationen + Medien + SHA-256 |
| D14b | `EXPORT_DIR` wie `BACKUP_DIR`; `ExportSnapshotMetadata` (status/checksum/size/owner/tenant/`expires_at`); Download mit Rechten; TTL/Cleanup |
| D14c | Async Celery-Job + Status + Download-Link, Streaming im Worker |
| D14d | ReqIF-Mapping zusätzlich TestCase + Icd als SpecObject (standardkonform) |
| D15 | editor = Merge; admin = `update`/`reconcile_status` (+ ADMIN-API-Key-Scope) |
| D16/D16b | Cross-tenant beliebig, aber Quell-LESEN + Ziel-ADMIN + Dry-Run-Pflicht + beidseitiges Audit |
| D17 | App-Restore → Ziel-Instanz-Restore; Sidecar bleibt DR-Wahrheit; ADR-012 Update |
| D18 | CSV/ReqIF bleiben, neue UI-Seite „Datenübernahme" mit Vorschau |

## 5. Zielarchitektur

**Ein Transfer-Contract** (`ArtifactTransferSpec`) pro Entität mit `scope`, `formats`, `fields`, `relations`, `status_map`, `exclusions`, `remap_rules`.

- **Einzelformate:** CSV/JSON/Markdown/PDF für alle 24 Typen; Allowlists aus dem Contract.
- **ReqIF:** Need, Requirement, TestCase, Icd + SpecRelations; Mapping-Tabelle + XSD-Gate.
- **ZIP-Snapshot:** versioniert, streambar, async, `EXPORT_DIR` oder Download; vollständiger Relationengraph.
- **Import-Ziele:** bestehender Workspace (version-guard/reconcile_status) oder neuer Workspace (Clone-Semantik).
- **Kopie:** alle Entitäten + Relationen, neue IDs + `source_id`, Cross-Tenant-Gates.
- **Restore:** Zielinstanz mit `target_*`, Dry-Run, Checksum, RLS-armed Kontext.

## 6. Umsetzungspakete

| Paket | Inhalt | DoD |
|---|---|---|
| **P1 — Contract & Ratchet** | `ArtifactTransferSpec`-Registry für 24 Entitäten; Gate-Test gegen `ARTIFACT_TYPE_MODELS`, `ENTITY_SPECS`, `ENTITY_FIELD_SPECS` | Matrix-Test rot→grün; neue Typen fallen nicht mehr still aus |
| **P2 — Alle Einzelformate** | generischer Export-Service; CSV/JSON/MD/PDF für alle Typen; REST/MCP/UI-Allowlists aus Contract | parametrisierter Test 24 × 4; E2E je Format |
| **P3 — ReqIF-Fidelity** | Tier/Level/Status zurückführen; TestCase + Icd SpecObjects; SpecRelation-Mapping; XSD-Test | Roundtrip Need/Req/TC/Icd + Links, XSD-valid |
| **P4 — Import-Semantik** | CSV-Dry-Run, version-guard, `update`, `reconcile_status`, autoritative Felder (außer Identity/Remap), Idempotenz | Unit/REST/E2E für Konflikt, Statuswechsel, Retry |
| **P5 — ZIP-Snapshot** | async Export/Import (Celery), `EXPORT_DIR` + Metadata, JSONL-Streaming, Checksum, Formatversion, Download-Link, Cross-Tenant-Gates | Export→Import in beide Ziele, 24 Typen, große Daten, Checksum-Fehler |
| **P6 — Vollständige Kopie** | `clone_workspace` auf 24 Entitäten + alle Relationen; generischer FK/M2M-Remap; `source_id`; Dry-Run; Exclusions | Copy-Test mit jedem Typ + allen Relationen; keine UID-Kollision; Cross-Tenant-Audit |
| **P7 — Backup/Restore** | Checksum-Verifikation, `format_version`, Dry-Run, RLS-Kontext, echter Round-Trip inkl. pgvector, `target_*`, ADR-012/EXT-004 | Round-Trip gegen echte Test-DB; RLS-Test; UI/MCP-Parität |
| **P8 — E2E & Ops** | Seite „Datenübernahme"; E2E Snapshot/Copy/ReqIF/Restore; `deploy/README.md`, `DATA_LIFECYCLE.md`, ADRs | 4 CI-Shards grün; Runbook „alle Artefakte in neuen Workspace" |

Reihenfolge: P1 → P2/P3/P4 (parallel) → P5 → P6 → P7 → P8. Jedes Paket: eigener PR, Review, CI 30/30, Merge-Commit.

## 7. Testmatrix (verbindlich)

Für **jede** der 24 Entitäten: `export(format)` → `import(target=new)` → Feld- und Relativenvergleich · `import(target=existing, version-guard)` · `conflict → update` · `reconcile_status` · `dry_run` · `idempotent replay`. Zusätzlich: Cross-Tenant-Gates, RLS, Checksum-Fehler, große Daten (≥100k Zeilen), ADR-012-Round-Trip.

## 8. Risiken

- **D12:** Quell-`version`/`created_at` überschreiben Zielwerte — bewusst, mit `source_*`-Provenance im Audit.
- **D16:** Cross-tenant technisch offen, nie unautorisiert; RLS muss beim Schreiben explizit bewaffnet werden.
- **D8/D10:** 24 Entitäten + alle Relationen ist der größte Aufwand; P5/P6 sind entsprechend groß.
- **ReqIF TC/Icd:** standardkonform nur über SpecObject-Typen/Attribute; XSD-Gate verhindert Schemadrift.
- **`EXPORT_DIR`:** Diskwachstum/TTL/Cleanup müssen betrieblich überwacht werden (analog Backup-Retention).

## 9. Referenzen

- `backend/persistence/artifact_backing.py`, `backend/application/export_service.py`, `backend/application/import_service.py`
- `backend/application/reqif_export_service.py`, `backend/application/reqif_import_service.py`
- `backend/admin_ops/services/backup_service.py`, `backend/admin_ops/services/admin_restore_service.py`
- `backend/application/workspace_service.py`, `backend/rest_api/views_io.py`
- `backend/mcp_server/tests/entity_surface_matrix.py`
- `docs/se/ADR/ADR-012_backup_wahrheit.md`, `docs/audit/2026-11-16-deep-dive-findings.md`
- OMG ReqIF 1.2 (`https://www.omg.org/spec/ReqIF/1.2/`)
