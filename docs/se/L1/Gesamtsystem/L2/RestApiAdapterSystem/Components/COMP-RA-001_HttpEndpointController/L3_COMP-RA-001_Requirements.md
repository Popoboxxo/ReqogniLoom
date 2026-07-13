# L3 HttpEndpointController Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-001 — HttpEndpointController
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

HTTP-Request-Routing, Method-Dispatch, HTTP-Statuscode-Selektion, Response-Assembly und Delegation an den ApplicationService. Der Controller ist der zentrale Einstiegspunkt für alle eingehenden HTTP-Requests innerhalb des RestApiAdapterSystem.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-001 | REST-CRUD-Endpunkte für alle sieben Domain-Entitäten unter `/api/v1/` |
| REQ-L2-RA-003 | API-Response-Performance unter 200ms (p95) |
| REQ-L2-RA-007 | Audit-Log-Auslösung bei Schreiboperationen |
| REQ-L2-RA-009 | Standardisierte HTTP-Fehlercodes und Response-Format |
| REQ-L2-RA-012 | Keine Geschäftslogik in der Adapter-Schicht |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-001 | ausgehend / eingehend | COMP-RA-003 (AuthEnforcer) | `AuthRequest {headers, path, method} -> AuthContext \| AuthError` |
| IF-RA-INT-002 | ausgehend / eingehend | COMP-RA-004 (PresetGuard) | `PresetRequest {endpoint_id, workspace_id, method} -> PresetDecision \| PresetError` |
| IF-RA-INT-003 | bidirektional | COMP-RA-002 (DataSerializer) | `SerializeRequest {json_body, query_params, entity_type, direction} -> ValidatedDTO \| ValidationError \| JSON_Response` |
| IF-RA-INT-005 | eingehend | COMP-RA-005 (OpenApiGenerator) | `EndpointRegistry {routes: RouteDef[]}` |
| IF-RA-INT-007 | eingehend | COMP-RA-006 (QuerysetOptimizer) | `get_optimized_queryset(entity_type, nested_fields) -> QuerySet; invalidate_cache(entity_type, entity_id)` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-RA-EXT-IN-001 | eingehend | API-Clients | HTTP/JSON-Requests mit Bearer Token |
| IF-RA-EXT-IN-002 | eingehend | ReactFrontend | HTTP/JSON-Requests mit Bearer Token |
| IF-RA-EXT-OUT-001 | ausgehend | API-Clients / ReactFrontend | JSON-Responses mit HTTP-Statuscodes |
| IF-RA-EXT-OUT-005 | ausgehend | ApplicationService | Use-Case-Methoden (In-Process Python) |

## L3 Komponenten-Anforderungen

### REQ-L3-RA001-001: CRUD-Routing für alle sieben Domain-Entitäten


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der HttpEndpointController SHALL vollständige CRUD-Routen (GET list, GET detail, POST, PATCH, DELETE) für alle sieben Domain-Entitäten (Artifact, Requirement, ArchitectureElement, TestCase, TraceLink, Baseline, WorkflowDefinition) unter dem Basis-Pfad `/api/v1/` registrieren und korrekt dispatchen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] All seven entities have registered routes for GET (list), GET (detail), POST, PATCH, DELETE
- [ ] Incoming request method and path are matched to exactly one handler without ambiguity
- [ ] Unknown routes return HTTP 404 with standard error body
- [ ] Route registration is verifiable via `EndpointRegistry` delivered through IF-RA-INT-005

---

### REQ-L3-RA001-002: HTTP-Statuscodes und Response-Assembly nach Operationstyp


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der HttpEndpointController SHALL nach jeder Delegation an den ApplicationService den korrekten HTTP-Statuscode auswählen (200 für GET/PATCH, 201 für POST, 204 für DELETE) und die JSON-Response aus dem zurückgegebenen DTO assemblen. Fehlersituationen SHALL er in standardisierte HTTP-Fehlercodes übersetzen (400, 401, 403, 404, 409, 422, 500).

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] POST operations return HTTP 201 with serialized entity body
- [ ] PATCH operations return HTTP 200 with updated entity body
- [ ] DELETE operations return HTTP 204 with empty body
- [ ] ApplicationService exceptions are mapped to the correct HTTP error code without leaking stack traces
- [ ] Error responses follow the format `{"error": {"code": "...", "message": "...", "details": [...]}}`

---

### REQ-L3-RA001-003: Audit-Log-Delegation bei Schreiboperationen


**Implementation State:** Not Implemented
**Review Findings:** Nur Tests gefunden, aber keine Implementierung.
**Test Status:** Covered
**Remarks:** Implementierung prüfen.


Der HttpEndpointController SHALL für jede Schreiboperation (POST, PATCH, DELETE) sicherstellen, dass der ApplicationService-Aufruf die authentifizierte Nutzer-Identität, den Operationstyp und die betroffene Entity-ID miterhält, sodass ein Audit-Log-Eintrag erzeugt werden kann. GET-Operationen SHALL keinen Audit-Log-Eintrag auslösen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] POST call to ApplicationService carries actor identity and operation type `create`
- [ ] PATCH call to ApplicationService carries actor identity, entity ID and operation type `update`
- [ ] DELETE call to ApplicationService carries actor identity, entity ID and operation type `delete`
- [ ] GET operations pass no audit metadata to ApplicationService

---

### REQ-L3-RA001-004: Keine Geschäftslogik im Controller


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der HttpEndpointController SHALL ausschließlich HTTP-spezifische Aufgaben (Routing, Dispatch, Statuscodes, Response-Assembly) ausführen. Jegliche Geschäftslogik, Workflow-Transition-Logik und Validierung von Businessregeln SHALL vollständig an den ApplicationService delegiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Controller code contains no conditional branches for business rules
- [ ] Controller code contains no workflow state machine logic
- [ ] All non-HTTP validation failures originate from ApplicationService, not Controller
- [ ] Code review checklist item: "no business logic in Controller" is verifiable per file

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
