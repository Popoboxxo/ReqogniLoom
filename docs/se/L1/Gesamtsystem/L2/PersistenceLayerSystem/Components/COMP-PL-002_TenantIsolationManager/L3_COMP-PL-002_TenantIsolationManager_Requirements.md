---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:05:00Z"
schema_version: "1.0.0"
---
# L3 TenantIsolationManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PL-002_TenantIsolationManager
> **Parent:** L2_PersistenceLayerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der TenantIsolationManager implementiert die erste Sicherheitsschicht für Tenant-Isolation auf ORM-Ebene. Er stellt einen Custom Django Manager (`TenantQuerySet`) bereit, der automatisch und transparant `tenant_id`-Filter auf alle Abfragen anwendet. Kombiniert mit COMP-PL-006 (RLS Policy Enforcer) bildet er eine Defense-in-Depth-Architektur für Datenisolation.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TenantQuerySet` (Klasse):** Spezialisierte Django QuerySet-Subklasse, die alle Abfrage-Methoden überschreibt.
- **`TenantManager` (Klasse):** Django Manager, der `TenantQuerySet` als Standard-QuerySet verwendet.
- **`TenantContext` (Utility-Klasse):** Thread-Local Storage zur Verwaltung des aktuellen Tenant-Kontexts.
- **`TenantContextNotSetError` (Exception-Klasse):** Spezialisierte Exception, die signalisiert, dass kein Tenant-Kontext verfügbar ist.

### 2.2 Datenstrukturen

**TenantContext:**
- `_thread_local = threading.local()` — Thread-safe Storage
- `set_tenant(tenant_id: UUID)` — setzt `_thread_local.tenant_id = tenant_id`
- `get_tenant() -> UUID` — liest `_thread_local.tenant_id` oder wirft `TenantContextNotSetError`
- `clear_tenant()` — setzt `_thread_local.tenant_id = None` (z.B. für Test-Teardown)

**TenantQuerySet Methoden (überschrieben):**
- `get_queryset()` → prüft Tenant-Kontext, fügt `filter(tenant_id=<aktueller_tenant>)` ein
- `all()` → delegiert zu `get_queryset()`
- `filter(*args, **kwargs)` → validiert Kontext, dann erweitert Filter
- `get(*args, **kwargs)` → validiert Kontext, dann erweitert Filter
- `exclude(*args, **kwargs)` → validiert Kontext, dann erweitert Filter
- `using(alias)` → validiert Kontext vor Datenbank-Alias-Wechsel

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PL002-001 (Automatischer Tenant-Filter) | `TenantQuerySet` als `objects`-Manager auf allen TenantModel-basierten Entitäten. Jede Abfrage-Methode injiziert automatisch `WHERE tenant_id = <aktueller_tenant>`. |
| REQ-L3-PL002-002 (Kontext-Validierung) | `TenantContext.get_tenant()` wird in `TenantQuerySet.get_queryset()` aufgerufen. Fehlt der Kontext, wirft es `TenantContextNotSetError` BEVOR die Datenbank abgefragt wird. |
| REQ-L3-PL002-003 (Kein umgehbarer Filter) | `using()` und Chaining-Operationen (`filter().filter()`, `select_related()`, `prefetch_related()`) werden alle durch die `get_queryset()`-Override validiert. Direkter `super().get_queryset()`-Zugriff ist nicht möglich in normalem Code. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PL-EXT-IN-008:** AuthAndTenancy-Komponente setzt den Tenant-Kontext via `TenantContext.set_tenant(tenant_id)` am Anfang jedes HTTP-Requests (Middleware oder Decorator).

**Ausgänge (Outbound):**
- **IF-PL-INT-001:** `TenantQuerySet` ist der Standard-Manager auf allen von `TenantModel` ererbenden Modellen (bereitgestellt von COMP-PL-001).

---

## 5. Architectural Rationale

**ADR-L3-PL-002 — Thread-Local Tenant-Context statt Dependency Injection**

*Entscheidung:* Tenant-Kontext wird über Thread-Local Storage verwaltet, nicht per Dependency Injection in jede Abfrage.

*Alternative (abgelehnt):* Tenant-ID explizit an jede Abfrage-Methode übergeben. Grund: Würde erfordern, dass jeder Aufrufende den Tenant-Kontext mitbringt — höhere Fehlerwahrscheinlichkeit, mehr Boilerplate.

*Rationale:* REQ-L3-PL002-001 fordert automatische Filterung ohne explizite Übergaben. Thread-Local ist der Standard-Pattern in Django-Middleware für Request-Scope-Daten.

---

**ADR-L3-PL-003 — Kontext-Fehler vor DB-Zugriff werfen**

*Entscheidung:* `TenantContext.get_tenant()` wird in `get_queryset()` aufgerufen — BEVOR eine SQL-Abfrage erzeugt wird. Fehlt der Kontext, wird sofort eine Exception geworfen.

*Alternative (abgelehnt):* Fehler erst beim DB-Execute werfen. Grund: Wäre später erkannt, unkontrollierter, könnte zu teilweisen Datenexpositionen führen.

*Rationale:* REQ-L3-PL002-002 fordert explizit: „Fehlt der Kontext, MUSS eine Exception ausgelöst werden, bevor eine Datenbankabfrage ausgefuehrt wird." Frühe Fehler sind sicherer und leichter zu debuggen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
