# L3 TokenEndpoints Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-007 — TokenEndpoints
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

DRF ViewSet für das Routing von `/api/v1/auth/tokens`. Delegiert die eigentliche Token-Erzeugung und Validierung an das AuthAndTenancySystem, kümmert sich aber um die HTTP-Serialisierung (JSON-Responses).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-021 | API Endpoints für PAT-Verwaltung |

## L3 Komponenten-Anforderungen

### REQ-L3-RA007-001: Token CRUD ViewSet

Das ViewSet MUSS GET, POST und DELETE Methoden für Tokens bereitstellen.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] GET liefert ein Array von Objekten: `{id, name, created_at}` (ohne Secret).
- [ ] POST verlangt `{name: "..."}` und liefert `{id, name, created_at, token: "rf_klartext..."}`.
- [ ] DELETE verlangt `{id}` und liefert `204 No Content`.
