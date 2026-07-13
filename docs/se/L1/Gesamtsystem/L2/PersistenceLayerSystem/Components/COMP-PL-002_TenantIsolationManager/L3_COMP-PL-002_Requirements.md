# L3 TenantIsolationManager Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PL-002 — TenantIsolationManager
> **Parent-System:** PersistenceLayerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Custom Django Manager (`TenantQuerySet`), automatischer `tenant_id`-Filter auf allen Abfragen, Tenant-Context-Validierung. Erste Sicherheitsschicht der mandantenspezifischen Datenisolation; arbeitet in Kombination mit COMP-PL-006 (RLSPolicyEnforcer) als Defense-in-Depth-Schichtung.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PL-001 | Tenant-Isolation via Custom Django Manager |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PL-INT-001 | ausgehend | COMP-PL-001 | `TenantQuerySet` als Default-Manager auf allen Modellen registriert |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Vertrag |
|-------|----------|-------------|-----|---------|
| IF-PL-EXT-IN-008 | eingehend | AuthAndTenancy | Python Thread-Local | Tenant-Kontext (tenant_id) per Request |

## L3 Komponenten-Anforderungen

### REQ-L3-PL002-001: Automatischer Tenant-Filter auf allen QuerySets


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der TenantIsolationManager MUSS einen `TenantQuerySet` implementieren, der als Default-Manager (`objects`) auf allen mandantenspezifischen Modellen registriert wird. Jede QuerySet-Operation (`all()`, `filter()`, `get()`, `exclude()`) MUSS automatisch eine `WHERE tenant_id = <aktueller_tenant>` Bedingung einfuegen, ohne dass aufrufender Code diesen Filter explizit setzen muss.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `TenantQuerySet` is the `objects` manager on all tenant-specific models
- [ ] T1-context: `Requirement.objects.all()` returns only T1 rows (verified with 2 tenants, 5+3 rows)
- [ ] `filter()`, `get()`, `exclude()` all inject tenant filter automatically
- [ ] No calling code needs to pass `tenant_id` explicitly to standard ORM queries

---

### REQ-L3-PL002-002: Pflichtvalidierung des Tenant-Kontexts


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der TenantIsolationManager MUSS bei jeder QuerySet-Operation pruefen, ob ein gueltiger Tenant-Kontext (nicht-leere UUID) im aktuellen Thread-Local gesetzt ist. Fehlt der Kontext, MUSS eine `TenantContextNotSetError`-Exception ausgeloest werden, bevor eine Datenbankabfrage ausgefuehrt wird. Die Exception MUSS die QuerySet-Klasse und die aufgerufene Methode im Fehlermeldungstext enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Request without tenant context raises `TenantContextNotSetError` before DB hit
- [ ] Error message includes the calling model class name and method name
- [ ] No partial query is executed before the exception is raised
- [ ] `TenantContextNotSetError` is a subclass of `PermissionError`

---

### REQ-L3-PL002-003: Kein umgehbarer Filter durch Manager-Override-Ketten


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der TenantIsolationManager MUSS sicherstellen, dass `TenantQuerySet` auch bei Chaining (`filter().filter()`, `select_related()`, `prefetch_related()`) den Tenant-Filter behaelt. Aufrufe ueber `.using(alias)` MUESSEN den Tenant-Filter ebenfalls erzwingen. Direkter Zugriff auf `super().get_queryset()` ohne Tenant-Kontext MUSS blockiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Chained `filter().filter()` still includes `tenant_id` in final SQL
- [ ] `select_related()` and `prefetch_related()` do not bypass the tenant filter
- [ ] Accessing via `.using(alias)` still enforces tenant isolation
- [ ] Unit test: subclassed manager calling `super().get_queryset()` raises `TenantContextNotSetError`

---

---

### REQ-L3-PL002-004: Tenant-Isolation Enforcement (M-01)

Der TenantIsolationManager MUSS durchgehend eine Multi-Tenant Base-Class erzwingen, die sicherstellt, dass ohne explizite Tenant-ID keine Query abgesetzt werden kann. Cross-Tenant Leakage MUSS durch harte DB-RLS (Row Level Security) oder ein striktes Manager-Pattern (`get_queryset(tenant_id)`) auf unterster Ebene verhindert werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-01.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-PL-023

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
