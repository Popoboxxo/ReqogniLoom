# L2 AuditLog Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** AuditLogSystem (ARCH-L1-012)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** subsystem (Leaf — keine L3-Zerlegung, ADR-10)

---

## Traceability

- Abgeleitet von: REQ-L1-011 (primär), REQ-L1-002 (mitwirkend), REQ-L1-005 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-015 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AL-EXT-IN-001 | input | data | `log_write(actor, actor_type, op, entity_type, entity_id, version, change_reason?, ctx)` von ApplicationService |
| IF-AL-EXT-IN-002 | input | data | Query-Anfrage mit Filter-Parametern |
| IF-AL-EXT-OUT-001 | output | data | Persistenz an PersistenceLayer (ARCH-L1-010) |
| IF-AL-EXT-OUT-002 | output | data | Export komprimierter JSON-Archive in Cold Storage (konfigurierbar, z.B. S3 Glacier) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-AL-001: Vollständige Audit-Einträge für alle Schreiboperationen

Das AuditLog-System SHALL für jede schreibende Operation (Create, Update, Delete) auf Requirement, ArchitectureElement, TestCase und TraceLink einen Audit-Eintrag persistieren mit: `actor`, `actor_type` (user | agent), `operation`, `entity_type`, `entity_id`, `timestamp` (ISO-8601 UTC), `version`, `change_reason` (optional).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstelle Requirement via REST → AuditLog: `{actor: user_id, actor_type: "user", operation: "create", entity_type: "requirement", version: 1}`
- [ ] Update Requirement → Eintrag: `{operation: "update", version: 2}`
- [ ] Delete via MCP → Eintrag: `{operation: "delete"}`
- [ ] Workflow-Transition mit change_reason → Eintrag enthält `change_reason`

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001
- Outgoing: IF-AL-EXT-OUT-001, IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-011, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend)
**Rationale:** Vollständige Auditierbarkeit ist explizite Non-Functional-Anforderung.

---

### REQ-L2-AL-002: MCP-Audit-Anreicherung mit Agent-Identität und API-Key-Hash

Das AuditLog-System SHALL bei MCP-Schreiboperationen zusätzlich `client_name` und `api_key_hash` (SHA-256, Prefix `sha256:`) erfassen. `source`-Feld: `mcp` oder `rest`. API-Key NIEMALS im Klartext.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] MCP `requirement.create` mit API-Key → `{actor_type: "agent", client_name: "claude-code/1.0", api_key_hash: "sha256:...", source: "mcp"}`
- [ ] REST-Operation → `{actor_type: "user", source: "rest", client_name: null}`
- [ ] DB-Check: kein Eintrag enthält Roh-API-Key

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001 (erweiterter Kontext)
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-011, REQ-L1-005 (mitwirkend)
**Rationale:** Unterscheidung manueller/agentengesteuerter Änderungen ist Voraussetzung für sicheren Agenten-Schreibzugriff.

---

### REQ-L2-AL-003: Unveränderlichkeit des Audit-Logs (Append-Only)

Das AuditLog-System SHALL Audit-Einträge ausschließlich append-only persistieren. Nach dem Schreiben DARF ein Eintrag NICHT verändert oder gelöscht werden. Erzwingung auf Datenbankebene.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Write → erfolgreich
- [ ] Versuch UPDATE → DB-Constraint-Fehler
- [ ] Versuch DELETE → DB-Constraint-Fehler
- [ ] API bietet keine `update_entry()` oder `delete_entry()` Methode

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001 (INSERT akzeptiert, UPDATE/DELETE rejected)
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-011
**Rationale:** Unveränderlichkeit ist fundamentale Vertrauensgrundlage eines Audit-Logs.

---

### REQ-L2-AL-004: Atomare Konsistenz mit auslösender Operation

Das AuditLog-System SHALL die Persistierung in dieselbe Datenbank-Transaktion wie die auslösende Operation integrieren. Geschäftstransaktion fehlschlägt → Audit-Eintrag zurückgerollt. Audit-Persistierung fehlschlägt → gesamte Transaktion zurückgerollt.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstelle Requirement → Requirement UND Audit-Eintrag in DB
- [ ] DB-Fehler nach INSERT → Rollback: weder Requirement noch Audit-Eintrag
- [ ] Audit-INSERT-Fehler → Requirement nicht persistiert
- [ ] `AuditLogEntry.objects.count()` entspricht exakt der Anzahl erfolgreicher Schreiboperationen

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001 (im Transaktionskontext)
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-025 (mitwirkend)
**Rationale:** Partiell persistierte Audit-Einträge erzeugen inkonsistente Zustände.

---

### REQ-L2-AL-005: Query- und Retrieval-Fähigkeit

Das AuditLog-System SOLLTE eine Query-Schnittstelle bereitstellen mit Filtern: `entity_id`, `actor`, `operation`, `entity_type`, `timestamp`-Bereich, `source`. Paginierte Ergebnisse (Default: 50, max: 200), sortiert nach `timestamp` DESC.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Query `entity_id=X` → exakt die Einträge für X
- [ ] Query `actor=agent_1&operation=delete&source=mcp` → nur Delete-Operationen von agent_1 via MCP
- [ ] Timestamp-Bereich-Filter funktioniert
- [ ] Pagination: `page_size=10, page=3` → Einträge 21–30
- [ ] Chronologisch absteigend sortiert

**Interfaces:**
- Incoming: IF-AL-EXT-IN-002
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-011
**Rationale:** Audit-Logs sind nur wertvoll, wenn sie effizient abfragbar sind.

---

### REQ-L2-AL-006: Tenant-Isolation für Audit-Einträge

Das AuditLog-System SHALL jeden Audit-Eintrag mit `tenant_id` versehen. Queries SÜLLEN ausschließlich Einträge des aktiven Tenants zurückliefern. Tenant-Isolation über Custom Django Manager.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 5 Einträge in T1, 3 in T2. Query T1 → exakt 5
- [ ] Query T2 → exakt 3
- [ ] AuditLogEntry-Model hat `tenant_id`-FK
- [ ] Custom Manager injiziert Filter automatisch

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001, IF-AL-EXT-IN-002
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-015 (mitwirkend)
**Rationale:** Tenant-Leak über Audit-Einträge wäre kritischer Sicherheitsvorfall.

---

### REQ-L2-AL-007: Performance-Anforderungen

Das AuditLog-System SOLLTE folgende Performance-Ziele einhalten:
- Audit-INSERT: +10ms maximal zur API-Gesamtantwortzeit
- Query nach `entity_id`: < 50ms (p95) bei 100.000 Einträgen
- Query nach Filterkombination: < 200ms (p95) bei 100.000 Einträgen

Indizes mindestens auf: `entity_id`, `(tenant_id, timestamp)`, `(actor, operation)`. Die Performance-Ziele werden durch die monatliche Table-Partitionierung (REQ-L2-AL-008) zusätzlich unterstützt.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 1.000 Schreiboperationen → durchschnittliches INSERT-Delta < 10ms
- [ ] 100.000 Einträge → Query `entity_id` < 50ms (p95)
- [ ] Filterkombination < 200ms (p95)
- [ ] EXPLAIN ANALYZE zeigt Index-Nutzung

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001, IF-AL-EXT-IN-002
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-026 (mitwirkend)
**Rationale:** Audit-Schreiboperationen liegen im kritischen Pfad.

---

### REQ-L2-AL-008: Table-Partitionierung der Audit-Tabelle

Die `AuditLogEntry`-Tabelle MUSS per PostgreSQL-RANGE-Partitionierung auf dem Feld `timestamp` in monatliche Partitionen aufgeteilt werden. Neue Partitionen MÜSSEN automatisch zu Monatsbeginn erzeugt werden. Queries mit Timestamp-Filter MÜSSEN Partition-Pruning nutzen, d.h. ausschließlich die relevante(n) Partition(en) lesen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Neue Partition wird automatisch am 1. eines Monats erstellt
- [ ] EXPLAIN ANALYZE für Query auf Monat X zeigt ausschließlich Zugriff auf Partition X (kein Seq-Scan über alle Partitionen)
- [ ] Bestehende Indizes (entity_id, tenant_id, timestamp, actor, operation) sind pro Partition aktiv
- [ ] Partition-Setup ist via Django-Migration oder Migrations-Script reproduzierbar

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001, IF-AL-EXT-IN-002
- Outgoing: IF-AL-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-026 (primär), REQ-L1-011 (mitwirkend)
**Rationale:** Partition-Pruning reduziert den Scan-Aufwand bei Timestamp-gefilterten Queries erheblich und sichert die Performance-Ziele aus REQ-L2-AL-007 auch bei wachsendem Datenvolumen.

---

### REQ-L2-AL-009: Cold-Storage-Archivierung (Datenlebenszyklus)

Ein konfigurierbarer Data-Lifecycle-Job SOLL Audit-Einträge, die älter als 2 Jahre sind, periodisch (monatlich via Celery-Beat) als komprimierte JSON-Archive in ein konfigurierbares Cold-Storage-Ziel (z.B. AWS S3 Glacier) exportieren und anschließend aus der Primärdatenbank löschen. Der Löschvorgang DARF ERST nach erfolgreich bestätigtem Export erfolgen (fail-safe).

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Export-Datei enthält alle Pflichtfelder (actor, actor_type, operation, entity_type, entity_id, timestamp, version, tenant_id, source)
- [ ] Nach erfolgreichem Export: Einträge nicht mehr in der Primär-DB vorhanden
- [ ] Bei Export-Fehler (z.B. S3 nicht erreichbar): kein Löschen aus Primär-DB; Job bricht ab und loggt Fehler
- [ ] Archiv-Format: JSON komprimiert (z.B. gzip), Dateiname enthält Zeitraum (z.B. `auditlog_2024-01.json.gz`)
- [ ] Cold-Storage-Ziel ist per Konfiguration (Environment-Variable oder Django-Setting) steuerbar

**Interfaces:**
- Incoming: IF-AL-EXT-IN-001 (Primär-DB als Quelle)
- Outgoing: IF-AL-EXT-OUT-001 (Löschen aus Primär-DB nach Export), IF-AL-EXT-OUT-002 (Export-Ziel Cold Storage)

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-011 (primär)
**Rationale:** Langfristiger Datenzuwachs ohne Archivierungsstrategie beeinträchtigt Performance und widerspricht Compliance-Anforderungen (IEC 61508 v2). REQ-L2-AL-003 (Append-Only) gilt für den laufenden Betrieb; der Cold-Storage-Export ist kein Modifikationsvorgang, sondern ein kontrollierter Archivierungs- und Bereinigungsschritt.

---

## Explizite Abgrenzung: v1 vs. v2 (ADR-10)

v1: Operation-Level-Granularität. **Feld-Level-Diffs** sind explizit v2.

---

## Traceability-Matrix: REQ-L2-AL → REQ-L1

| REQ-L2-AL | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-AL-001 | REQ-L1-011 | REQ-L1-002, REQ-L1-009 |
| REQ-L2-AL-002 | REQ-L1-011 | REQ-L1-005 |
| REQ-L2-AL-003 | REQ-L1-011 | — |
| REQ-L2-AL-004 | REQ-L1-025 | — |
| REQ-L2-AL-005 | REQ-L1-011 | — |
| REQ-L2-AL-006 | REQ-L1-015 | — |
| REQ-L2-AL-007 | REQ-L1-026 | — |
| REQ-L2-AL-008 | REQ-L1-026 | REQ-L1-011 |
| REQ-L2-AL-009 | REQ-L1-011 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-AL | 9 |
| Mandatory | 6 |
| Desired | 3 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-011, REQ-L1-026 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, -005, -009, -011, -015, -025, -026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-AuditLog → REQ-L2-AL, Template-Standardisierung*
*Designation: subsystem (Leaf) — decomposition_status: terminal*
