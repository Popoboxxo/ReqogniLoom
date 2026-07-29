---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:20:00Z"
schema_version: "1.0.0"
---

# L3 OpenApiGenerator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RA-005_OpenApiGenerator
> **Parent:** L2_RestApiAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der OpenApiGenerator erzeugt automatisch eine valide OpenAPI-3.0-Spezifikation aus den registrierten Routen (von COMP-RA-001) und Serializer-Schemata (von COMP-RA-002). Die Spezifikation wird als JSON unter `/api/v1/schema/` bereitgestellt und eine interaktive Swagger-UI unter `/api/v1/schema/swagger-ui/`. Die Spezifikation muss maschinenlesbar sein und TypeScript-Client-Generierung ohne Fehler ermöglichen.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`OpenApiGenerator` (Klasse):** Hauptklasse mit Methoden `generate_spec() -> dict` und `serve_spec() -> JSON Response`.
- **`SpecBuilder` (Klasse):** Konstruiert OpenAPI 3.0 Struktur schrittweise (info, paths, components/schemas, securitySchemes).
- **`SchemaBuilder` (Klasse):** Konvertiert Pydantic-Serializer-Schemata in JSON-Schema-Format.
- **`PathItemBuilder` (Klasse):** Konvertiert RouteDefinition-Einträge in OpenAPI Paths.
- **`SwaggerUIRenderer` (Klasse):** Rendert HTML-Seite unter `/api/v1/schema/swagger-ui/`. Einbindung von Swagger-UI-Bibliothek.

### 2.2 Datenstrukturen

- **`OpenAPISpec` (Pydantic Model):** OpenAPI 3.0 Struktur {openapi: "3.0.0", info, paths, components, security}.
- **`PathItem` (Pydantic Model):** {get, post, patch, delete, parameters, requestBody, responses}.
- **`ResponseObject` (Pydantic Model):** {description, content}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RA005-001 (OpenAPI 3.0 Spec) | SpecBuilder erzeugt vollständige OpenAPI 3.0 Struktur. Paths enthalten alle 35 CRUD-Endpunkte (7 Entitäten × 5 Operationen). Request/Response-Schemata aus Serializer-Schemata. SecuritySchemes: Bearer Token. Validiert gegen openapi-spec-validator. |
| REQ-L3-RA005-002 (Swagger-UI) | SwaggerUIRenderer serviert HTML mit Swagger-UI-JavaScript-Bibliothek. Lädt Spec von `/api/v1/schema/`. Try-it-out für alle Operationen. Keine Authentifizierung erforderlich. |
| REQ-L3-RA005-003 (TypeScript-Client-Generierung) | OpenAPI-Spec muss vom Standard-Generator (openapi-typescript-codegen) ohne Fehler verarbeitbar sein. CI-Pipeline führt Client-Generierung als Build-Schritt aus. Schema-Regression (Feld removed/renamed) → Build-Fehler. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RA-INT-005:** Von COMP-RA-001 (HttpEndpointController): `EndpointRegistry {routes: RouteDef[]}`.
- **IF-RA-INT-006:** Von COMP-RA-002 (DataSerializer): `SerializerSchemas {entity_type, field_defs, validators}`.

**Ausgänge (Outbound):**
- **IF-RA-EXT-OUT-002:** `/api/v1/schema/` → JSON-Response mit OpenAPI-Spezifikation.
- **IF-RA-EXT-OUT-003:** `/api/v1/schema/swagger-ui/` → HTML mit Swagger-UI.

---

## 5. Architectural Rationale

**ADR-L3-RA5-01 — Spec-Generation zur Startup-Zeit, nicht zur Request-Zeit**

*Entscheidung:* OpenAPI-Spezifikation wird beim Anwendungsstart einmal generiert und zwischengespeichert, nicht bei jedem Request neu gebaut.

*Rationale:* Erfüllt Performance-Anforderungen und Idempotenz. Änderungen an Routen/Schemata erfordern Neustart. Alternative: On-demand-Generierung → würde bei jedem Schema-Request CPU verbrauchen.

---

**ADR-L3-RA5-02 — Direkte Pydantic → JSON-Schema Konvertierung**

*Entscheidung:* SchemaBuilder konvertiert Pydantic-Serializer-Schemas direkt in OpenAPI-kompatible JSON-Schemas, nicht über DRF-Introspection.

*Rationale:* Pydantic-Schemas sind bereits JSON-Schema-kompatibel. Ermöglicht direkte Kontrolle und Validierbarkeit. Alternative: DRF-getriebene Introspection → würde weniger kontrolliert sein.

---

**ADR-L3-RA5-03 — CI-Pipeline muss Client-Generierung validieren**

*Entscheidung:* Build-Schritt führt `openapi-typescript-codegen` aus. Fehler (Schema-Regression, Ungültigkeit) → Build schlägt fehl.

*Rationale:* Erfüllt REQ-L3-RA005-003 ("A schema regression (removed or renamed field) is detected as a CI failure"). Verhindert Breaking-Changes ohne Bewusstsein. Alternative: Client-Generierung nur lokal → würde Regressions-Schutz schwächen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
