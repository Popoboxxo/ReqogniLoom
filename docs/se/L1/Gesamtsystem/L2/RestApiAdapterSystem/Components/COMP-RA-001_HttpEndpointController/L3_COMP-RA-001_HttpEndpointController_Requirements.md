---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:00:00Z"
schema_version: "1.0.0"
---

# L3 HttpEndpointController Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RA-001_HttpEndpointController
> **Parent:** L2_RestApiAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der HttpEndpointController ist der zentrale HTTP-Request-Einstiegspunkt des RestApiAdapterSystem. Er empfängt alle eingehenden HTTP-Requests, delegiert sie sequenziell an AuthEnforcer, PresetGuard und DataSerializer zur Validierung, dispatcht die Requests an den ApplicationService und assembliert die HTTP-Response aus dem zurückgegebenen DTO unter Berücksichtigung des Operationstyps (GET, POST, PATCH, DELETE). Der Controller enthält keine Geschäftslogik und handelt ausschließlich als HTTP-spezifischer Adapter.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`HttpEndpointController` (Klasse):** Zentrale Dispatcher-Klasse. Methodengruppen nach Entity-Typ (Requirement, Artifact, ArchitectureElement, TestCase, TraceLink, Baseline, WorkflowDefinition); Methoden `get_list()`, `get_detail()`, `post_create()`, `patch_update()`, `delete_remove()` pro Entity.
- **`RouteRegistry` (Klasse):** Verwaltet die Registrierung aller Routen (Pfad, Methode, Handler). Liefert die Schnittstelle IF-RA-INT-005 für den OpenApiGenerator.
- **`HttpStatusCodeMapper` (Klasse):** Statische Utility-Klasse für die Abbildung von Operationstyp → HTTP-Statuscode (200, 201, 204, 400, 401, 403, 404, 409, 422, 500).
- **`ErrorResponseFormatter` (Klasse):** Formatiert Exception-Objekte in standardisiertes JSON-Error-Format `{"error": {"code": "...", "message": "...", "details": [...]}}`.

### 2.2 Datenstrukturen

- **`RequestContext` (Pydantic Model):** Hält Metadaten des eingehenden Requests (method, path, headers, authenticated_user_id, tenant_id, workspace_id).
- **`OperationMetadata` (Dataclass):** Hält Audit-relevante Metadaten (operation_type: "create"|"update"|"delete"|"read", entity_type, entity_id wenn vorhanden).
- **`RouteDefinition` (Dataclass):** Registrierungseintrag {path: str, method: str, entity_type: str, operation: str, handler_fn: callable}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RA001-001 (CRUD-Routing) | RouteRegistry verwaltet alle 35 Routen (7 Entitäten × 5 Operationen). Router-Logik matched Request-Methode + Pfad gegen RouteDefinition-Einträge. Unbekannte Routen → HTTP 404. Registrierung via `@route` Decorator oder programmatisch. |
| REQ-L3-RA001-002 (HTTP-Statuscodes) | HttpStatusCodeMapper.get_status_code(operation_type) → {POST: 201, PATCH: 200, DELETE: 204, GET: 200}. ApplicationService-Exceptions (ValidationError, AuthError, NotFound) werden via ErrorResponseFormatter in HTTP-Fehlercodes mapped (400, 401, 403, 404, 409, 422, 500). |
| REQ-L3-RA001-003 (Audit-Log-Delegation) | POST/PATCH/DELETE delegieren mit `OperationMetadata` an ApplicationService. GET-Operationen erhalten `operation_type = "read"` nicht gesetzt. ApplicationService verantwortlich für Audit-Log-Eintrag. |
| REQ-L3-RA001-004 (Keine Geschäftslogik) | Controller-Methoden enthalten nur Validierungs-Delegation (zu AuthEnforcer, PresetGuard, DataSerializer), Routing und Response-Assembly. Alle Geschäftslogik bleibt im ApplicationService. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RA-EXT-IN-001:** HTTP-Requests von API-Clients mit Bearer Token im `Authorization`-Header.
- **IF-RA-EXT-IN-002:** HTTP-Requests von React-Frontend.

**Ausgänge (Outbound):**
- **IF-RA-INT-001:** Aufruf an COMP-RA-003 (AuthEnforcer): `auth_enforce(headers, path, method) -> AuthContext | AuthError`.
- **IF-RA-INT-002:** Aufruf an COMP-RA-004 (PresetGuard): `check_endpoint_visible(endpoint_id, workspace_id, method) -> PresetDecision | PresetError`.
- **IF-RA-INT-003:** Bidirektionaler Aufruf an COMP-RA-002 (DataSerializer): `deserialize(json_body, entity_type, direction="in") -> ValidatedDTO` und `serialize(dto, entity_type, direction="out") -> JSON_Response`.
- **IF-RA-INT-005:** Lieferung an COMP-RA-005 (OpenApiGenerator): RouteRegistry exportiert `EndpointRegistry {routes: RouteDef[]}`.
- **IF-RA-EXT-OUT-005:** In-Process Python-Methodenaufruf an ApplicationService (z.B. `app_service.create_requirement(dto, ctx)`).
- **IF-RA-EXT-OUT-001:** JSON-Response an API-Clients/Frontend.

---

## 5. Architectural Rationale

**ADR-L3-RA-01 — HTTP-Statuscode-Mapping zentral und explizit**

*Entscheidung:* HttpStatusCodeMapper verwaltet die vollständige Abbildung operationType → HTTP-Statuscode. Exceptions aus ApplicationService werden nicht direkt in HTTP-Codes konvertiert, sondern explizit mapped.

*Rationale:* Vermeidet verstreute Statuscode-Logik über mehrere Handler-Funktionen. Zentrale Konfiguration erleichtert Änderungen und Auditierbarkeit (REQ-L3-RA001-002). Alternative: direkter if/else-Baum im Handler → würde Komplexität O(N) pro Handler einführen, nicht wartbar bei 35 Routen.

---

**ADR-L3-RA-02 — Validierungsdelegation vor ApplicationService**

*Entscheidung:* AuthEnforcer, PresetGuard und DataSerializer sind obligatorische Stationen vor jeder ApplicationService-Delegation. Ihr Fehler → HTTP 4xx/5xx ohne ApplicationService-Aufruf.

*Rationale:* Erfüllt REQ-L3-RA001-004 (keine Geschäftslogik im Controller) und REQ-L3-RA001-001 (zuverlässiges Routing). Alternative: Validierungen im ApplicationService → würde HTTP-Concerns in die Business-Schicht ziehen, verstößt gegen Separation of Concerns.

---

**ADR-L3-RA-03 — RouteRegistry als explizites Datenmodell**

*Entscheidung:* RouteRegistry ist ein Datenmodell, nicht nur eine implizite Routing-Tabelle. Wird explizit an COMP-RA-005 (OpenApiGenerator) exportiert.

*Rationale:* Ermöglicht automatische API-Dokumentation (REQ-L3-RA001-001 verlangt "Route registration is verifiable via EndpointRegistry") und validierbare Vollständigkeit. Alternative: Implizite Route-Registrierung via Decorators → würde OpenApiGenerator dazu zwingen, zur Laufzeit zu introspizieren; schwer zu validieren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-RA001-U000: Auto-derived from REQ-L2-RES-014
Abgeleitet von: REQ-L2-RES-014

### REQ-L3-RA001-U001: Auto-derived from REQ-L2-RES-011
Abgeleitet von: REQ-L2-RES-011

### REQ-L3-RA001-U002: Auto-derived from REQ-L2-RES-001
Abgeleitet von: REQ-L2-RES-001

### REQ-L3-RA001-U003: Auto-derived from REQ-L2-RES-003
Abgeleitet von: REQ-L2-RES-003

### REQ-L3-RA001-U004: Auto-derived from REQ-L2-RES-010
Abgeleitet von: REQ-L2-RES-010

### REQ-L3-RA001-U005: Auto-derived from REQ-L2-RES-002
Abgeleitet von: REQ-L2-RES-002

### REQ-L3-RA001-U006: Auto-derived from REQ-L2-RES-013
Abgeleitet von: REQ-L2-RES-013

### REQ-L3-RA001-U007: Auto-derived from REQ-L2-RES-004
Abgeleitet von: REQ-L2-RES-004

### REQ-L3-RA001-U008: Auto-derived from REQ-L2-RES-009
Abgeleitet von: REQ-L2-RES-009

### REQ-L3-RA001-U009: Auto-derived from REQ-L2-RES-008
Abgeleitet von: REQ-L2-RES-008

### REQ-L3-RA001-U010: Auto-derived from REQ-L2-RES-006
Abgeleitet von: REQ-L2-RES-006

### REQ-L3-RA001-U011: Auto-derived from REQ-L2-RES-012
Abgeleitet von: REQ-L2-RES-012

### REQ-L3-RA001-U012: Auto-derived from REQ-L2-RES-005
Abgeleitet von: REQ-L2-RES-005

### REQ-L3-RA001-U013: Auto-derived from REQ-L2-RES-007
Abgeleitet von: REQ-L2-RES-007
