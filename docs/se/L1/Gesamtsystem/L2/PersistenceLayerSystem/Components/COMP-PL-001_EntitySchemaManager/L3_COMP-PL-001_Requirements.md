# L3 EntitySchemaManager Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PL-001 — EntitySchemaManager
> **Parent-System:** PersistenceLayerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Django ORM-Modelle fuer alle 13 Domain-Entitaeten, Audit-Felder, Foreign-Key-Constraints mit semantisch korrekten `on_delete`-Regeln. Zentrale Datendefinition des gesamten PersistenceLayerSystem; alle anderen Komponenten referenzieren die hier definierten Modell-Klassen.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PL-004 | Vollstaendigkeit des Entity-Schemas (alle 13 Entitaeten) |
| REQ-L2-PL-005 | Audit-Felder auf allen schreibbaren Entitaeten |
| REQ-L2-PL-009 | Referentielle Integritaet via FK-Constraints |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PL-INT-001 | eingehend | COMP-PL-002 | `TenantQuerySet` als Default-Manager auf allen Modellen |
| IF-PL-INT-002 | eingehend | COMP-PL-003 | `transaction.atomic()` Context-Manager umschliess ORM-Write-Operationen |
| IF-PL-INT-003 | eingehend | COMP-PL-004 | Django-Migrationen generiert aus `models.py` |
| IF-PL-INT-005 | eingehend | COMP-PL-005 | `Meta.indexes` und `Index`-Klasse in Modell-Definitionen |
| IF-PL-INT-006 | eingehend | COMP-PL-006 | `CREATE POLICY`-Statements auf allen Modell-Tabellen; RLS aktiviert via `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Vertrag |
|-------|----------|-------------|-----|---------|
| IF-PL-EXT-IN-001 | eingehend | ApplicationService | Django ORM | CRUD auf allen Entitaeten |
| IF-PL-EXT-IN-002 | eingehend | WorkflowEngine | Django ORM | WorkflowDefinition, WorkflowState |
| IF-PL-EXT-IN-003 | eingehend | BaselineService | Django ORM | Baseline |
| IF-PL-EXT-IN-004 | eingehend | TraceabilityEngine | Django ORM | TraceLink |
| IF-PL-EXT-IN-005 | eingehend | PresetConfigEngine | Django ORM | Workspace, Preset-Konfiguration |
| IF-PL-EXT-IN-006 | eingehend | AuthAndTenancy | Django ORM | User, Role, Tenant |
| IF-PL-EXT-IN-007 | eingehend | AuditLog | Django ORM | AuditLogEntry |
| IF-PL-EXT-OUT-001 | ausgehend | PostgreSQL | TCP / psycopg2 | SQL, DDL-Statements |

## L3 Komponenten-Anforderungen

### REQ-L3-PL001-001: Vollstaendige Entity-Modell-Definition

Der EntitySchemaManager MUSS fuer alle 13 Domain-Entitaeten (Tenant, Workspace, Artifact, Requirement, ArchitectureElement, TraceLink, TestCase, Baseline, WorkflowDefinition, WorkflowState, AuditLogEntry, User, Role) je eine Django-Model-Klasse in `requirements_app/models.py` bereitstellen. Jede Modell-Klasse MUSS eine explizite `Meta.db_table`-Benennung und alle semantisch notwendigen Felder enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Exactly 13 Django Model classes exist in `requirements_app/models.py`
- [ ] Each model has `Meta.db_table` set
- [ ] `python manage.py check` passes without errors
- [ ] `python manage.py inspectdb` returns all 13 tables after migration

---

### REQ-L3-PL001-002: Audit-Basisklasse mit automatischer Befuellung

Der EntitySchemaManager MUSS eine abstrakte Django-Basisklasse `AuditableModel` bereitstellen, die die Felder `created_at`, `created_by`, `modified_at`, `modified_by` und `version` (Integer, Startwert 1) definiert. `created_at` und `modified_at` MUESSEN als `DateTimeField(auto_now_add)` bzw. `DateTimeField(auto_now)` implementiert sein. Alle schreibbaren Domain-Entitaeten MUESSEN von `AuditableModel` erben. `version` MUSS bei jedem Update via `F('version') + 1` atomar inkrementiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `AuditableModel` abstract base class exists with all 5 audit fields
- [ ] Create: `created_at`, `created_by` set, `version == 1`
- [ ] Update: `modified_at` refreshed, `version` incremented atomically
- [ ] `created_at` unchanged after any number of updates
- [ ] All writable entity models inherit from `AuditableModel`

---

### REQ-L3-PL001-003: Semantisch korrekte FK-Constraints und Kaskadenregeln

Der EntitySchemaManager MUSS alle Foreign-Key-Beziehungen zwischen den 13 Entitaeten mit expliziten `on_delete`-Regeln deklarieren: CASCADE fuer Kinder-Entitaeten (z.B. Requirement loescht TraceLinks), PROTECT fuer uebergeordnete Stammdaten (z.B. Tenant), SET_NULL fuer optionale Verknuepfungen auf Audit-Felder (`created_by`, `modified_by`). Keine FK-Beziehung DARF ohne explizites `on_delete` deklariert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] No `ForeignKey` definition without an explicit `on_delete` parameter
- [ ] Delete Artifact with children: CASCADE removes children and associated TraceLinks
- [ ] Delete Tenant with active Requirements: PROTECT raises `ProtectedError`
- [ ] Delete User: `created_by`/`modified_by` set to NULL on related entities

---

### REQ-L3-PL001-004: Tenant-ID-Pflichtfeld auf mandantenspezifischen Entitaeten

Der EntitySchemaManager MUSS auf allen mandantenspezifischen Entitaeten (alle ausser Tenant selbst) ein `tenant` ForeignKey-Feld zu `Tenant` mit `on_delete=PROTECT` und `db_index=True` bereitstellen. Das Feld DARF nicht nullable sein. Tenant- und User-Modell sind von dieser Pflicht ausgenommen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] All tenant-specific models have a non-nullable `tenant` FK field
- [ ] `db_index=True` on `tenant` FK confirmed via `python manage.py sqlmigrate`
- [ ] `on_delete=PROTECT` on all `tenant` FK fields
- [ ] `Tenant` model itself has no `tenant` FK field

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
