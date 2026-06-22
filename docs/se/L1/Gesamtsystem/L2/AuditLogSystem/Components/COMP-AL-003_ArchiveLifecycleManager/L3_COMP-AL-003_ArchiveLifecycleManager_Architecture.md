---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 ArchiveLifecycleManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AL-003_ArchiveLifecycleManager
> **Parent:** L2_AuditLogSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der ArchiveLifecycleManager ist ein asynchroner, zeitgestuerter Job für Audit-Log-Archivierung. Er ist verantwortlich für:
- Periodische Ausführung (monatlich) via Celery-Beat
- Fail-Safe Export älter Einträge (>2 Jahre) zu Cold Storage
- Gzip-Kompression und JSON-Formatierung
- Partition-Drop nach bestätigtem Export
- Fehlerbehandlung und Logging

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ArchiveLifecycleManager` (Hauptklasse):** Celery-Beat-Task-Einstiegspunkt, `run_monthly_archive()`.
- **`ExportOrchestrator` (Module):** Orchestriert Lesezugriff via AuditLogQuery, Formatierung, Cold-Storage-Upload.
- **`ColdStorageAdapter` (Module):** Abstrahiert Cloud-Storage (S3, GCS, etc.) — Konfigurierbar via Setting.
- **`PartitionDropper` (Module):** Führt `ALTER TABLE ... DROP PARTITION` aus nach bestätigtem Export.
- **`ArchiveLogger` (Module):** Strukturiertes Logging aller Export-Attempts.

### 2.2 Datenstrukturen

- **Archiv-Dateiformat:**
  - Dateiname: `audit_YYYY_MM.json.gz` (z.B. `audit_2024_01.json.gz`)
  - Inhalt: Gzip-komprimierte JSON-Lines
    ```json
    {"actor": "...", "actor_type": "...", "op": "...", "entity_type": "...", "entity_id": "...", "timestamp": "...", "version": ..., "tenant_id": "...", "source": "..."}
    {"actor": "...", ...}
    ```

- **ArchiveJobLog (interne Struktur):**
  ```json
  {
    "job_id": "uuid",
    "timestamp": "2026-06-22T...",
    "partition": "audit_2024_01",
    "entry_count": 50000,
    "outcome": "success",
    "error_details": null,
    "cold_storage_location": "s3://bucket/audit_2024_01.json.gz"
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AL003-001 (Periodische Ausführung via Celery-Beat) | Celery Beat Schedule: `'run-monthly-archive': {'task': '...ArchiveLifecycleManager.run_monthly_archive', 'schedule': crontab(0, 0, 1, '*', '*')}` — Monatlich am 1. um 00:00. Einstellungen via `AUDIT_COLD_STORAGE_BACKEND`, `AUDIT_RETENTION_YEARS` (Default 2). |
| REQ-L3-AL003-002 (Fail-Safe Export vor Löschung) | ExportOrchestrator: (1) AuditLogQuery.get_entries_before() aufrufen, (2) In JSON-Lines formatieren, (3) Zu Cold Storage exportieren, (4) Erfolgs-Confirmation erhalten, (5) DANN PartitionDropper.drop_partition(). Bei Fehler in (2-4): Abort, keine Partition-Drop. |
| REQ-L3-AL003-003 (Archiv-Format und Datei-Konvention) | Dateiname: `audit_YYYY_MM.json.gz`. Inhalt: gzip-komprimiertes JSON. Jeder Eintrag hat alle 9 Pflichtfelder. Keine Secrets. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **Celery-Beat-Scheduler** — Monatliche Task-Trigger

- **Ausgänge (Outbound):**
  - **IF-AL-INT-002:** `COMP-AL-002` (AuditLogQuery) — `get_entries_before(cutoff, page_size)` für Export
  - **IF-AL-EXT-OUT-001:** Django ORM — `ALTER TABLE ... DROP PARTITION` nach erfolgreichem Export
  - **IF-AL-EXT-OUT-002:** Cold Storage (S3, konfigurierbar) — PUT `audit_YYYY_MM.json.gz`

---

## 5. Architectural Rationale

**ADR-L3-AL003-01 — Celery-Beat für zeitgesteuerte, entkoppelte Ausführung**

*Entscheidung:* Archivierung läuft als asynchroner Celery-Beat-Job monatlich, nicht als Synchronous-Call in der Application.

*Rationale:*
- **Annahme:** REQ-L3-AL003-001 fordert periodische Ausführung. Archivierung ist zeitintensiv (I/O zu Cold Storage).
- **Gewählter Ansatz:** Celery-Beat mit Cron-Scheduling, entkoppelt von Request-Cycle.
- **Abgelehnte Alternative:** Synchrone Archivierung im ApplicationService → blockiert Business-Ops.
- **Erfüllt REQ-L3-AL003-001:** Entkopplung und Zuverlässigkeit.

---

**ADR-L3-AL003-02 — Fail-Safe Export-vor-Löschung mit Checkpoint-Bestätigung**

*Entscheidung:* Partition-Drop erfolgt ERST nach bestätigtem Cold-Storage-Upload. Partielle Uploads gelten als Fehler (komplettes Rollback).

*Rationale:*
- **Annahme:** REQ-L3-AL003-002 fordert Fail-Safe-Semantik. Data Loss ist inakzeptabel.
- **Gewählter Ansatz::** Upload (1) im Staging/Temp-Pfad, (2) Vollständigkeit prüfen, (3) Rename zu Final, (4) DB-Partition-Drop. Bei Fehler in (1-3): Abort ohne Drop.
- **Abgelehnte Alternative:** Upload + Drop in parallel → Race Condition, Data Loss möglich.
- **Erfüllt REQ-L3-AL003-002:** Data Loss wird eliminiert.

---

**ADR-L3-AL003-03 — Konfigurierbare Cold-Storage und Retention-Parameter**

*Entscheidung:* Cold-Storage-Ziel und Retention-Periode sind via Django-Settings konfigurierbar (z.B. `AUDIT_COLD_STORAGE_BACKEND = "s3://my-bucket"`, `AUDIT_RETENTION_YEARS = 2`).

*Rationale:*
- **Annahme:** Verschiedene Deployments (Dev, Staging, Prod) haben unterschiedliche Storage-Backends und Compliance-Anforderungen.
- **Gewählter Ansatz:** Django-Settings + ColdStorageAdapter abstrahiert Backend (S3, GCS, etc.).
- **Abgelehnte Alternative:** Hardcoded S3 → nicht flexibel.
- **Erfüllt REQ-L3-AL003-001:** Konfigurierbarkeit ist gewährleistet.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
