# L2 PersistenceLayer Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** PersistenceLayerSystem (ARCH-L1-010)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-015 (primär), REQ-L1-025 (primär), REQ-L1-026 (primär), REQ-L1-001..024 (mitwirkend — Persistenzbedarf), REQ-L1-018 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-PL-EXT-IN-001 | input | data | Django ORM-Aufrufe von ARCH-L1-004 (alle Entitäten) |
| IF-PL-EXT-IN-002 | input | data | Django ORM-Aufrufe von ARCH-L1-005 (WorkflowDefinition, WorkflowState) |
| IF-PL-EXT-IN-003 | input | data | Django ORM-Aufrufe von ARCH-L1-006 (Baseline) |
| IF-PL-EXT-IN-004 | input | data | Django ORM-Aufrufe von ARCH-L1-007 (TraceLink) |
| IF-PL-EXT-IN-005 | input | data | Django ORM-Aufrufe von ARCH-L1-008 (Workspace, Preset) |
| IF-PL-EXT-IN-006 | input | data | Django ORM-Aufrufe von ARCH-L1-011 (User, Role, Tenant) |
| IF-PL-EXT-IN-007 | input | data | Django ORM-Aufrufe von ARCH-L1-012 (AuditLogEntry) |
| IF-PL-EXT-IN-008 | input | control | Tenant-Kontext (tenant_id) via Request-Context |
| IF-PL-EXT-IN-009 | input | physical | PostgreSQL-Verbindung (TCP, .env) |
| IF-PL-EXT-OUT-001 | output | data | Query-Ergebnisse und Persistierung an PostgreSQL |

---

## L2 Subsystem-Anforderungen

### REQ-L2-PL-001: Tenant-Isolation via Custom Django Manager

Das PersistenceLayer MUSS einen Custom Django Manager (`TenantQuerySet`) auf allen Entitäten implementieren, der jede Abfrage automatisch mit `tenant_id` filtert. Kein Query DARF den Filter umgehen. Fehlt der Tenant-Kontext, MUSS die Query mit Exception abgebrochen werden. Als zweite Sicherheitsschicht ergänzt REQ-L2-PL-010 (PostgreSQL Row-Level Security) die applikationsseitige Isolation auf Datenbankebene.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 2 Tenants, 5 Requirements in T1, 3 in T2. T1-Kontext → `Requirement.objects.all()` liefert exakt 5
- [ ] Raw-Query via Manager → Manager injiziert T1-Filter
- [ ] Request ohne Tenant-Kontext → Exception `TenantContextNotSetError`
- [ ] Alle Entity-Modelle verwenden `TenantManager` (Code-Review)

**Interfaces:**
- Incoming: IF-PL-EXT-IN-008
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-015
**Rationale:** Row-Level-Isolation ist Voraussetzung für v2-SaaS (ADR-03). RLS (REQ-L2-PL-010) sichert die Isolation zusätzlich auf DB-Ebene.

---

### REQ-L2-PL-002: Transaktionale Konsistenz (ACID)

Das PersistenceLayer MUSS alle schreibenden Operationen innerhalb von Datenbank-Transaktionen ausführen. Multi-Entity-Operationen MÜSSEN in einer einzigen Transaktion gekapselt werden. Bei Fehlern: vollständiges Rollback.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `transaction.atomic()` umschließt alle Multi-Entity-Write-Operationen
- [ ] DB-Fehler nach INSERT Requirement → Rollback: kein Requirement und kein TraceLink persistiert
- [ ] Batch-Decomposition: Constraint-Verletzung bei Kind 7 → gesamter Batch rollbackt

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001..007
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-025
**Rationale:** Datenkonsistenz ist fundamentale Non-Functional-Anforderung.

---

### REQ-L2-PL-003: Performance-Indizes

Das PersistenceLayer MUSS PostgreSQL-Indizes für drei Query-Pfade bereitstellen:
1. Hierarchie: BTree auf `Artifact.parent_id`
2. TraceLink-Graph: GIST/GIN auf `source_id`, `target_id`
3. Full-Text-Search: `tsvector` auf `title` + `description` für Requirement, ArchitectureElement, TestCase

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Django-Migration enthält alle `CREATE INDEX` Statements
- [ ] `EXPLAIN ANALYZE` Tree-Query → Index-Scan
- [ ] `EXPLAIN ANALYZE` Full-Text-Search → tsvector-Index
- [ ] `EXPLAIN ANALYZE` TraceLink-Query → GIST/GIN-Index

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001, IF-PL-EXT-IN-004
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-026, REQ-L1-001 (mitwirkend), REQ-L1-003 (mitwirkend), REQ-L1-020 (mitwirkend)
**Rationale:** Indizes notwendig für < 200ms / < 500ms Performance-Ziele (ADR-09).

---

### REQ-L2-PL-004: Vollständigkeit des Entity-Schemas

Das PersistenceLayer MUSS Django ORM-Modelle für alle 13 Domain-Entitäten bereitstellen: Tenant, Workspace, Artifact, Requirement, ArchitectureElement, TraceLink, TestCase, Baseline, WorkflowDefinition, WorkflowState, AuditLogEntry, User, Role.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle 13 Entity-Modelle existieren als Django-Model-Klassen
- [ ] Foreign-Key-Beziehungen mit korrekten `on_delete`-Regeln
- [ ] Jede Entität enthält `tenant_id`-FK zu Tenant
- [ ] Schema-Check bestätigt alle Tabellen und Spalten

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001..007
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-001..015 (alle mit Persistenzbedarf)
**Rationale:** Vollständige Schemata sind Voraussetzung für alle Subsysteme.

---

### REQ-L2-PL-005: Audit-Felder auf allen schreibbaren Entitäten

Das PersistenceLayer MUSS auf allen schreibbaren Entitäten die Felder `created_by`, `created_at`, `modified_by`, `modified_at` und `version` bereitstellen. Automatische Befüllung bei Create/Update.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle schreibbaren Modelle erben von `AuditableModel`-Basisklasse
- [ ] Create → `created_at`, `created_by` gesetzt, `version` == 1
- [ ] Update → `modified_at` aktualisiert, `version` inkrementiert
- [ ] `created_at` ändert sich nicht bei Updates

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001..007
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-011, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend)
**Rationale:** Audit-Felder sind Voraussetzung für vollständigen Audit-Trail.

---

### REQ-L2-PL-006: Idempotente Datenbank-Migrationen

Das PersistenceLayer MUSS vollständige, idempotente Django-Migrationen bereitstellen. Jede Migration MUSS einen Vorwärts- und Rückwärtspfad haben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `makemigrations --check` ohne Fehler
- [ ] `migrate` auf leerer DB erzeugt vollständiges Schema
- [ ] Jede Migration hat `reverse_migration`
- [ ] CI: Migration + Rollback + Re-Migration fehlerfrei

**Interfaces:**
- Incoming: IF-PL-EXT-IN-009
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-018 (mitwirkend)
**Rationale:** Reproduzierbare Deployment-Pipeline für Docker-Compose.

---

### REQ-L2-PL-007: Datenbankverbindungs-Pooling

Das PersistenceLayer SOLLTE PostgreSQL-Verbindungen über einen Connection-Pool verwalten. Pool-Konfiguration über Umgebungsvariablen steuerbar.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `CONN_MAX_AGE` und Pool-Parameter konfiguriert
- [ ] Lasttest (50 gleichzeitige Requests): keine Connection-Exhaustion, Wiederverwendungsrate > 80%
- [ ] `DB_POOL_SIZE` steuert maximale Pool-Größe

**Interfaces:**
- Incoming: IF-PL-EXT-IN-009
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-026 (mitwirkend)
**Rationale:** Connection-Pooling notwendig für Performance unter Last.

---

### REQ-L2-PL-008: Performance-Latenzziele

Das PersistenceLayer MUSS folgende Latenzziele garantieren (10.000 Items, 50 gleichzeitige Nutzer):
1. Standard-Queries: < 200ms (p95)
2. TraceLink-Graph-Queries: < 200ms (p95)
3. Recursive CTE (500 Knoten): < 200ms (p95)
4. Volltextsuche (10.000 Items): < 500ms (p95)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Lasttest Standard-CRUD: p95 < 200ms
- [ ] Lasttest TraceLink-Upstream: p95 < 200ms
- [ ] Lasttest Recursive CTE: p95 < 200ms
- [ ] Lasttest Full-Text-Search: p95 < 500ms
- [ ] `EXPLAIN ANALYZE` zeigt Index-Nutzung

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001..007
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-026, REQ-L1-003 (mitwirkend), REQ-L1-020 (mitwirkend)
**Rationale:** DB-Latenz bestimmt die Gesamt-API-Latenz.

---

### REQ-L2-PL-009: Referentielle Integrität

Das PersistenceLayer MUSS referentielle Integrität über PostgreSQL FOREIGN-KEY-Constraints erzwingen. ON-DELETE-Regeln: CASCADE für Kinder, PROTECT für Eltern, SET NULL für optionale Verknüpfungen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle FK-Constraints mit korrektem `on_delete` definiert
- [ ] Lösche Artifact mit Kindern → CASCADE löscht Kinder + TraceLinks
- [ ] Lösche Tenant mit Requirements → PROTECT verhindert Löschung
- [ ] Lösche User mit Entities → SET NULL auf Audit-Feldern

**Interfaces:**
- Incoming: IF-PL-EXT-IN-001..007
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-025, REQ-L1-001 (mitwirkend)
**Rationale:** Letzte Verteidigungslinie gegen orphaned records.

---

### REQ-L2-PL-010: PostgreSQL Row-Level Security (RLS)

Das PersistenceLayer MUSS PostgreSQL Row-Level Security auf allen mandantenspezifischen Tabellen aktivieren. Eine Django-Middleware MUSS bei jedem HTTP- und MCP-Request die Session-Variable `app.current_tenant` via `SET LOCAL app.current_tenant = '<uuid>'` setzen. PostgreSQL-Policies MÜSSEN sicherstellen, dass Zeilen nur zurückgeliefert werden, wenn `tenant_id = current_setting('app.current_tenant')` gilt. Die DB-seitige Isolation DARF durch die Applikationsschicht nicht umgehbar sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Direkter DB-Zugriff (psql) ohne gesetztes `app.current_tenant` → leere Ergebnismenge für alle RLS-geschützten Tabellen
- [ ] `SET LOCAL app.current_tenant = '<T1-UUID>'` → nur T1-Zeilen sichtbar, T2-Zeilen nicht
- [ ] Django-Middleware setzt `app.current_tenant` bei jedem Request vor der Query-Ausführung
- [ ] `CREATE POLICY` existiert für alle mandantenspezifischen Tabellen (Migrations-Check)
- [ ] ORM-Bypass-Test: Raw SQL ohne App-Kontext liefert keine Fremddaten

**Interfaces:**
- Incoming: IF-PL-EXT-IN-008, IF-PL-EXT-IN-009
- Outgoing: IF-PL-EXT-OUT-001

**Traceability:** REQ-L1-015
**Rationale:** DB-seitige Isolation als zweite Sicherheitsschicht zu REQ-L2-PL-001 (Custom Django Manager). Verhindert Datenlecks auch bei Applikationsfehlern oder direktem DB-Zugriff (Handlungsempfehlung 1.1).

---

## Traceability-Matrix: REQ-L2-PL → REQ-L1

| REQ-L2-PL | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-PL-001 | REQ-L1-015 | — |
| REQ-L2-PL-002 | REQ-L1-025 | — |
| REQ-L2-PL-003 | REQ-L1-026 | REQ-L1-001, REQ-L1-003, REQ-L1-020 |
| REQ-L2-PL-004 | REQ-L1-001..015 | — |
| REQ-L2-PL-005 | REQ-L1-011 | REQ-L1-002, REQ-L1-009 |
| REQ-L2-PL-006 | REQ-L1-018 | — |
| REQ-L2-PL-007 | REQ-L1-026 | — |
| REQ-L2-PL-008 | REQ-L1-026 | REQ-L1-003, REQ-L1-020 |
| REQ-L2-PL-009 | REQ-L1-025 | REQ-L1-001 |
| REQ-L2-PL-010 | REQ-L1-015 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-PL | 10 |
| Mandatory | 9 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-015, REQ-L1-025, REQ-L1-026 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-001..024 (alle mit Persistenzbedarf) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Persist → REQ-L2-PL, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*
