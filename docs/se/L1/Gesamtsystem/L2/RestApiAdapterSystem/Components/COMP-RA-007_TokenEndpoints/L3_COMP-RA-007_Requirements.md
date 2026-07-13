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

**Implementation State:** Erfüllt durch bestehende Komponente (kein separates COMP-RA-007 erforderlich)
**Priority:** mandatory
**Acceptance Criteria:**
- [x] GET liefert ein Array von Objekten: `{id, name, created_at}` (ohne Secret). → `ApiKeyViewSet.list()` (`backend/rest_api/api_key_views.py`), Route `/api/v1/api-keys/`.
- [x] POST verlangt `{name: "..."}` und liefert `{id, name, created_at, token: "rf_klartext..."}`. → `ApiKeyViewSet.create()`, Response-Feld heißt `plaintext` statt `token`, Präfix `rf_` identisch.
- [x] DELETE verlangt `{id}` und liefert `204 No Content`. → `ApiKeyViewSet.destroy()`.

> **Architektur-Entscheidung (2026-07-04):** Route weicht von der Spezifikation ab (`/api/v1/api-keys/` statt `/api/v1/auth/tokens`), der Vertrag ist aber funktional identisch. **COMP-RA-007 wird nicht als eigene Komponente implementiert** — eine zweite ViewSet/Route für dieselbe Ressource würde Clients verwirren und Wartungsaufwand duplizieren. Traceability zeigt auf den bestehenden `ApiKeyViewSet` (bislang nicht in einer eigenen L2/L3-Komponente dokumentiert; Doku-Nachtrag empfohlen, siehe `docs/REQUIREMENTS.md`).
