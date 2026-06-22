---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:00:00Z"
schema_version: "1.0.0"
---
# L3 EntitySchemaManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PL-001_EntitySchemaManager
> **Parent:** L2_PersistenceLayerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der EntitySchemaManager definiert die zentralen Django ORM-Modelle für alle 13 Domain-Entitäten des Systems. Er ist die Datenschicht-Definition und wird von allen anderen Komponenten des PersistenceLayerSystem referenziert. Der Manager stellt sicher, dass alle Modelle vollständig mit korrekten Feldtypien, Foreign-Key-Constraints mit semantisch passenden `on_delete`-Regeln, Audit-Feldern und Tenant-Isolation ausgestattet sind.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`AuditableModel` (abstrakte Basisklasse):** Bereitstellt automatisch verwaltete Audit-Felder (`created_at`, `created_by`, `modified_at`, `modified_by`, `version`).
- **`TenantModel` (abstrakte Basisklasse):** Erbt von `AuditableModel` und fügt `tenant` FK-Feld mit `db_index=True` und `on_delete=PROTECT` ein.
- **13 Django Model-Klassen:**
  - `Tenant` (erbt direkt von `AuditableModel`, kein `tenant`-Feld)
  - `User` (erbt direkt von `AuditableModel`, kein `tenant`-Feld)
  - `Role`, `Workspace`, `Artifact`, `Requirement`, `ArchitectureElement`, `TraceLink`, `TestCase`, `Baseline`, `WorkflowDefinition`, `WorkflowState`, `AuditLogEntry` (alle erben von `TenantModel`)

### 2.2 Datenstrukturen

**AuditableModel-Felder:**
- `created_at: DateTimeField(auto_now_add=True)` — automatisch gesetzt bei Erstellung
- `created_by: ForeignKey(User, on_delete=SET_NULL, null=True)`
- `modified_at: DateTimeField(auto_now=True)` — automatisch aktualisiert bei jedem Save
- `modified_by: ForeignKey(User, on_delete=SET_NULL, null=True)`
- `version: IntegerField(default=1)` — manuell inkrementiert via `F('version') + 1`

**TenantModel-Felder (zusätzlich zu AuditableModel):**
- `tenant: ForeignKey(Tenant, on_delete=PROTECT, db_index=True)` — nicht nullable

**13 Entity-Modelle (Grundgerüst):**
- `Tenant`: `id (PK), name (CharField), ...`
- `User`: `id (PK), username, email, tenant (NULL), ...`
- `Workspace`: `id (PK), name, tenant (FK), ...`
- `Artifact`: `id (PK), parent_id (FK, nullable), artifact_type, tenant (FK), ...`
- `Requirement`: `id (PK), artifact_id (FK), title, description, category, status, tenant (FK), ...`
- `ArchitectureElement`: `id (PK), artifact_id (FK), element_type, description, tenant (FK), ...`
- `TraceLink`: `id (PK), source_id (FK), target_id (FK), link_type, tenant (FK), ...`
- `TestCase`: `id (PK), artifact_id (FK), title, description, steps, tenant (FK), ...`
- `Baseline`: `id (PK), artifact_id (FK), scope, definition, tenant (FK), ...`
- `WorkflowDefinition`: `id (PK), artifact_id (FK), workflow_json, tenant (FK), ...`
- `WorkflowState`: `id (PK), requirement_id (FK), current_state, tenant (FK), ...`
- `AuditLogEntry`: `id (PK), action, object_type, object_id, user_id (FK), tenant (FK), ...`
- `Role`: `id (PK), name, permissions (JSON), tenant (FK), ...`

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PL001-001 (Vollständige Entity-Modell-Definition) | 13 Django Model-Klassen in `requirements_app/models.py`. Jedes Modell hat explizite `Meta.db_table`-Benennung. `python manage.py check` bestätigt Validität. |
| REQ-L3-PL001-002 (Audit-Basisklasse) | `AuditableModel` abstrakte Basisklasse mit 5 Audit-Feldern. `created_at/modified_at` mit Auto-Update. `version` startet bei 1. Alle schreibbaren Entitäten erben davon. |
| REQ-L3-PL001-003 (FK-Constraints mit on_delete-Regeln) | Alle FK-Definitionen explizit mit `on_delete`-Parameter: CASCADE für Kind-Entitäten (z.B. Requirement → TraceLink), PROTECT für Stammdaten (z.B. Tenant), SET_NULL für optionale Audit-Referenzen. |
| REQ-L3-PL001-004 (Tenant-ID auf mandantenspezifischen Entitäten) | 11 Entitäten (alle außer Tenant, User) haben `tenant` FK mit `on_delete=PROTECT`, `db_index=True`, nicht nullable. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PL-EXT-IN-001 bis IF-PL-EXT-IN-007:** ORM-CRUD von ApplicationService, WorkflowEngine, BaselineService, TraceabilityEngine, PresetConfigEngine, AuthAndTenancy, AuditLog via Django ORM direkt auf den Modellen.

**Ausgänge (Outbound):**
- **IF-PL-INT-001:** `TenantQuerySet` als Default-Manager registriert (wird von COMP-PL-002 bereitgestellt und auf allen TenantModel-Modellen verwendet).
- **IF-PL-INT-002:** Modelle unterstützen `transaction.atomic()` Context-Manager (Django native Funktionalität).
- **IF-PL-INT-003:** Django-Migrationen generiert aus diesen Modellen (COMP-PL-004).
- **IF-PL-INT-005:** `Meta.indexes` und `Index`-Klasse in Modell-Definitionen (für COMP-PL-005).
- **IF-PL-INT-006:** RLS-Policies referenzieren die Tabellennamen (für COMP-PL-006).
- **IF-PL-EXT-OUT-001:** PostgreSQL via psycopg2 / Django Database Backend.

---

## 5. Architectural Rationale

**ADR-L3-PL-001 — Abstrakte Basisklassen für Audit und Tenant-Isolation**

*Entscheidung:* Statt Audit-Felder in jedes Modell zu kopieren, wird eine `AuditableModel`-Basisklasse verwendet. Ebenso wird `TenantModel` als spezialisierte Subklasse erstellt, die `tenant`-Feld automatisch hinzufügt.

*Alternative (abgelehnt):* Audit-Felder in jedem Modell hardcodieren. Grund: Wartungslast, Fehleranfälligkeit bei Änderungen, Wiederholung von Logik.

*Rationale:* Erfüllt REQ-L3-PL001-002 und REQ-L3-PL001-004 mit minimalem Code-Duplication. DRY-Prinzip unterstützt die wartbarkeit.

---

**ADR-L3-PL-002 — Explizite `on_delete`-Regeln statt Django-Defaults**

*Entscheidung:* Keine FK-Definition ohne explizit angegebenes `on_delete`-Parameter. Semantik wird dokumentiert: CASCADE für Kind-Entitäten, PROTECT für Stammdaten, SET_NULL für Audit-Felder.

*Alternative (abgelehnt):* Django's Standardverhalten (CASCADE als Default) verwenden. Grund: Stilluversicherheit — Fehler könnten zu unerwarteten Kaskaden-Löschungen führen.

*Rationale:* Erfüllt REQ-L3-PL001-003. Explizite Aussagen über Constraints reduzieren das Risiko unerwarteter Verhaltensweisen bei Datenlöschungen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
