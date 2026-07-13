# L3 OpenApiGenerator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-005 — OpenApiGenerator
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Automatische Generierung der OpenAPI-3.0-Spezifikation aus den registrierten Routen und Serializer-Schemata sowie Bereitstellung der Swagger-UI unter dem konfigurierten Endpunkt.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-002 | Auto-generierte OpenAPI-3.0-Spezifikation und Swagger-UI |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-005 | ausgehend | COMP-RA-001 (HttpEndpointController) | `EndpointRegistry {routes: RouteDef[]}` |
| IF-RA-INT-006 | ausgehend | COMP-RA-002 (DataSerializer) | `SerializerSchemas {entity_type, field_defs, validators}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-RA-EXT-OUT-002 | ausgehend | API-Clients / ReactFrontend | OpenAPI-3.0-Spezifikation unter `/api/v1/schema/` |
| IF-RA-EXT-OUT-003 | ausgehend | API-Clients / ReactFrontend | Swagger-UI unter `/api/v1/schema/swagger-ui/` |

## L3 Komponenten-Anforderungen

### REQ-L3-RA005-001: Valide OpenAPI-3.0-Spezifikation für alle CRUD-Endpunkte


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der OpenApiGenerator SHALL unter `/api/v1/schema/` eine vollständige, maschinenlesbare OpenAPI-3.0-Spezifikation im JSON-Format bereitstellen. Die Spezifikation SHALL alle registrierten CRUD-Endpunkte aller sieben Domain-Entitäten, deren Request- und Response-Schemata sowie Security-Scheme (Bearer Token) enthalten. Die Spezifikation MUSS mit einem OpenAPI-3.0-Validator fehlerfrei validierbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] GET `/api/v1/schema/` returns HTTP 200 with `Content-Type: application/json`
- [ ] OpenAPI spec passes validation with an OpenAPI 3.0 conformant validator (e.g. `openapi-spec-validator`)
- [ ] All seven entity endpoints with all CRUD operations are present in `paths`
- [ ] `components/schemas` contains all entity request and response schemas
- [ ] `securitySchemes` defines Bearer token authentication
- [ ] Schema endpoint is accessible without authentication

---

### REQ-L3-RA005-002: Swagger-UI für interaktive API-Exploration


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der OpenApiGenerator SHALL unter `/api/v1/schema/swagger-ui/` eine interaktive Swagger-UI bereitstellen, die die unter `/api/v1/schema/` generierte Spezifikation rendert. Die Swagger-UI SHALL ohne Authentifizierung erreichbar sein und alle Endpunkte mit „Try it out"-Funktion darstellen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] GET `/api/v1/schema/swagger-ui/` returns HTTP 200 with HTML content
- [ ] Swagger-UI renders all entity endpoints with operation descriptions
- [ ] "Try it out" functionality is available for at least GET operations
- [ ] Swagger-UI is reachable without a Bearer token

---

### REQ-L3-RA005-003: TypeScript-Client-Generierung ohne Fehler


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der OpenApiGenerator SHALL eine OpenAPI-Spezifikation erzeugen, aus der ein OpenAPI-Client-Generator (z.B. `openapi-typescript-codegen` oder äquivalent) einen TypeScript-Client fehlerfrei generieren kann. Build-Fehler bei der Client-Generierung SHALL als Regressionsfehler im CI behandelt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Running a standard OpenAPI TypeScript generator against `/api/v1/schema/` exits with code 0
- [ ] Generated TypeScript client compiles without errors
- [ ] CI pipeline includes TypeScript client generation as a build step
- [ ] A schema regression (removed or renamed field) is detected as a CI failure

---

### REQ-L3-RA005-004: OpenAPI Spec Konsistenz & Fehlerformate (A-05, A-07, A-08, A-11, A-12, A-14, A-15)

Der OpenApiGenerator MUSS sicherstellen, dass Custom-Actions mit `@extend_schema` dokumentiert sind. Fehlerformate (wie z.B. in `ApiKeyViewSet`) MÜSSEN zwingend die standardisierte `build_error_response()`-Funktion nutzen. Stubs (wie `TraceLinkViewSet.retrieve`) MÜSSEN implementiert oder aus der Spec entfernt werden. Status-Codes (wie 405 statt 403 für immutable Ressourcen) MÜSSEN projektweit konsistent sein. Fehlende Lookup-Keys (bei `needs`) MÜSSEN sicher abgefangen werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von A-05, A-07, A-08, A-11, A-12, A-14, A-15.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-RA-027

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
