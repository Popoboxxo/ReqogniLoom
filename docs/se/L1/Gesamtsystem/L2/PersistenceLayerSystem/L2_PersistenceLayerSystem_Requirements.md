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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

---

## Erweiterung v2 — REQ-L2-PL-011 (aus REQ-L1-025 + System-Check-Befund)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L1-025 (Connection-Pooling) + Systemprüfungsbefund

---

### REQ-L2-PL-011: Datenbankverbindungs-Pooling (Connection-Pool-Konfiguration)


Die Persistenzschicht MUSS Datenbankverbindungen über einen konfigurierbaren
Connection-Pool verwalten. Die maximale Poolgröße, minimale Poolgröße und
Connection-Timeout MÜSSEN über Umgebungsvariablen konfigurierbar sein.
Bei erschöpftem Pool MUSS eine definierte Timeout-Strategie angewendet werden
(kein stilles Hängen). Das Pooling MUSS mit PostgreSQL kompatibel sein.
Empfohlene Implementierung: `django-db-geventpool` oder `pgbouncer` (technologieneutral).

**Konfiguration (Umgebungsvariablen):**
- `DB_CONN_MAX_AGE` — Max. Verbindungsalter in Sekunden (default: 60)
- `DB_POOL_MAX_CONNECTIONS` — Max. Pool-Größe (default: 20)
- `DB_POOL_TIMEOUT` — Timeout beim Warten auf freie Verbindung in ms (default: 5000)

**Schnittstellen:**
- Intern: Django `DATABASES`-Konfiguration mit Pool-Backend
- Monitoring: Pool-Metriken (aktive/wartende/freie Verbindungen) über `/health`-Endpunkt

**Akzeptanzkriterien:**
- AC1: Gleichzeitige Requests über Pool-Kapazität hinaus → definierter Timeout, kein Crash
- AC2: `DB_POOL_MAX_CONNECTIONS=5` unter Last → max. 5 gleichzeitige DB-Verbindungen
- AC3: `/health`-Endpunkt liefert Pool-Metriken (aktiv, wartend, frei)
- AC4: Verbindungsaufbau nach Pool-Exhaustion → HTTP 503 mit Retry-After Header

**Verifikationsmethode:** Lasttest — gleichzeitige Requests, Pool-Metriken und Fehlerverhalten
**Verifikiert durch:** L2-PL-Test-011
**Abgeleitet von:** REQ-L1-025
**Übergeordnete REQ-L0:** REQ-L0-002 (Skalierbarkeit)

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-PL-011 aus System-Check-Befund, REQ-L1-025)*

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.



---

## Erweiterung v3 — System Audit Data Integrity & Performance (M-01 bis M-12)

> **Datum:** 2026-07-13 | **Quelle:** SYSTEM_AUDIT.md

---

### REQ-L2-PL-012: Vollständige Tenant-Isolation

Das PersistenceLayer MUSS die `TenantScopedModel`-Vererbung oder einen expliziten Tenant-FK für alle Applikationsmodelle erzwingen, die mandantenbezogene Daten speichern. Dies umfasst explizit die Modelle `Adr`, `Risk`, `Issue` (App `icd`), die Event-Modelle `DomainEvent`, `DomainEventOutbox`, `DomainEventDLQ`, `WebhookSubscription`, sowie die Metrik-Modelle `MetricCache` und `WorkspaceThresholdConfig`. Datenlecks zwischen Tenants MÜSSEN durch diese strukturelle Isolation ausgeschlossen werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-01.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-098

---

### REQ-L2-PL-013: Datenbank-Migrationen & Konsistenz

Das PersistenceLayer MUSS sicherstellen, dass alle Datenbank-Migrationen konsistent in der Versionskontrolle verfolgt werden (Behebung von Migration 0029). Die Verwendung von `unique_together` MUSS durch das moderne `UniqueConstraint` in der Meta-Klasse ersetzt werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-02, M-08.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-098

---

### REQ-L2-PL-014: Datenbank-Performance & Indizes

Das PersistenceLayer MUSS geeignete Indizes bereitstellen, um schnelle Lookups und referenzielle Rückwärts-Suchen zu ermöglichen:
- `db_index=True` oder zusammengesetzte Indizes auf `(tenant, uid)` für `Requirement`, `StakeholderNeed`, `ArchitectureElement`.
- Ein Index auf der Zielspalte (`target`) von `TraceLink`.
- Ein Index auf `(status, created_at)` für die `DomainEventDLQ`.
- Die N+1-Level-Ableitung in `ArchitectureElement.get_level()` MUSS durch Materialisierung (z.B. Pfad-Cache oder denormalisiertes Feld) performant gelöst werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-03, M-04, M-10, M-11.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-099

---

### REQ-L2-PL-015: Modell-Konsolidierung & Typisierung

Das PersistenceLayer MUSS redundante Datenstrukturen konsolidieren:
- Die parallelen Audit-Logs (`persistence.AuditLogEntry` und `audit.AuditEntry`) MÜSSEN auf eine einzige Wahrheit (`audit.AuditEntry`) migriert werden.
- Die Legacy-Workflow-Status-Tabellen MÜSSEN in die aktuelle State-Machine migriert und gelöscht werden.
- Die `AttributeVisibilityConfig` MUSS normalisiert werden, um Feldduplizierungen zu vermeiden.
- CSV-String-Antipatterns (wie `WebhookSubscription.event_types`) MÜSSEN in relationale Formate (z.B. Postgres `ArrayField` oder Join-Tabelle) überführt werden.
- Alle Modelle, insbesondere `GlossaryTermVersion`, MÜSSEN eine lesbare `__str__`-Repräsentation definieren.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-05, M-06, M-07, M-09, M-12.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-098

---

## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-PL-001 | REQ-L1-015 |
| REQ-L2-PL-002 | REQ-L1-025 |
| REQ-L2-PL-003 | REQ-L1-026, REQ-L1-001 (mitwirkend), REQ-L1-003 (mitwirkend), REQ-L1-020 (mitwirkend) |
| REQ-L2-PL-004 | REQ-L1-001..015 (alle mit Persistenzbedarf) |
| REQ-L2-PL-005 | REQ-L1-011, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend) |
| REQ-L2-PL-006 | REQ-L1-018 (mitwirkend) |
| REQ-L2-PL-007 | REQ-L1-026 (mitwirkend) |
| REQ-L2-PL-008 | REQ-L1-026, REQ-L1-003 (mitwirkend), REQ-L1-020 (mitwirkend) |
| REQ-L2-PL-009 | REQ-L1-025, REQ-L1-001 (mitwirkend) |
| REQ-L2-PL-010 | REQ-L1-015 |

