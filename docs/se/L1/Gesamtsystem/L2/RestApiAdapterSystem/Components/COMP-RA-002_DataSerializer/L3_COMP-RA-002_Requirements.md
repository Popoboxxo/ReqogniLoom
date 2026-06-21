# L3 DataSerializer Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-002 — DataSerializer
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

JSON-Deserialisierung und Serialisierung, Input-Validierung, DTO-Konvertierung, Pagination/Filtering/Sorting sowie i18n-Fehlermeldungen. Optimiert Querysets via `select_related`/`prefetch_related` für alle verschachtelten Serializer und überwacht den Query-Count.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-001 | REST-CRUD-Endpunkte — Serialisierung der Domain-Entitäten |
| REQ-L2-RA-003 | API-Response-Performance unter 200ms (p95) |
| REQ-L2-RA-004 | Backend-Fehlermeldungen i18n (DE/EN) |
| REQ-L2-RA-008 | Preset-basierte Feld-Filterung |
| REQ-L2-RA-009 | Standardisiertes JSON-Fehlerformat |
| REQ-L2-RA-010 | Pagination, Filtering, Sorting für Listen-Endpunkte |
| REQ-L2-RA-012 | Keine Geschäftslogik — reine Serialisierung |
| REQ-L2-RA-013 | N+1-Query-Vermeidung bei verschachtelten Responses |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-003 | bidirektional | COMP-RA-001 (HttpEndpointController) | `SerializeRequest {json_body, query_params, entity_type, direction} -> ValidatedDTO \| ValidationError \| JSON_Response` |
| IF-RA-INT-004 | eingehend | COMP-RA-004 (PresetGuard) | `FieldFilter {permitted_fields, required_fields}` |
| IF-RA-INT-006 | eingehend | COMP-RA-005 (OpenApiGenerator) | `SerializerSchemas {entity_type, field_defs, validators}` |

## Externe Schnittstellen (Systemgrenze)

Keine direkten externen Schnittstellen; Kommunikation ausschließlich über COMP-RA-001.

## L3 Komponenten-Anforderungen

### REQ-L3-RA002-001: JSON-Deserialisierung, Input-Validierung und DTO-Konvertierung

Der DataSerializer SHALL eingehende JSON-Request-Bodies für alle sieben Domain-Entitäten deserialisieren, gegen das jeweilige Feldschema (Typen, Pflichtfelder, Format-Constraints) validieren und in typisierte DTOs für den ApplicationService konvertieren. Validierungsfehler SHALL er als strukturierten `ValidationError` mit feldspezifischen Details zurückgeben.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Invalid JSON body returns `ValidationError` with field-level detail, not an unhandled exception
- [ ] Missing required fields are reported individually per field name
- [ ] Unknown extra fields are either rejected (strict mode) or silently ignored (permissive mode) — mode is configurable
- [ ] Validated DTO types are statically typed (Pydantic or DRF Serializer) — no raw dict passed to ApplicationService

---

### REQ-L3-RA002-002: Lokalisierte Fehlermeldungen (DE/EN) via Accept-Language

Der DataSerializer SHALL alle Validierungs- und Fehlerausgaben in der durch den `Accept-Language`-Header angeforderten Sprache (Deutsch oder Englisch) zurückgeben. Fehlender oder unbekannter Header SHALL auf Englisch zurückfallen. Jeder neue Fehler-Key MUSS eine deutsche Übersetzung besitzen; fehlende Keys MÜSSEN als Build-Fehler behandelt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `Accept-Language: de` → all validation messages in German
- [ ] `Accept-Language: en` or absent header → all validation messages in English
- [ ] New error key without German translation causes CI build failure
- [ ] Translation lookup is unit-testable without HTTP context

---

### REQ-L3-RA002-003: Pagination, Filtering und Sorting auf Listen-Responses

Der DataSerializer SHALL für alle Listen-Endpunkte Pagination (offset-basiert, konfigurierbare Page-Size, Default 25, Maximum 100), Filtering nach mindestens `workspace_id` und `workflow_state` sowie Sorting über `ordering`-Query-Parameter unterstützen. Die Response SHALL Pagination-Metadaten (`count`, `next`, `previous`, `results`) enthalten.

**Priority:** desired
**Acceptance Criteria:**
- [ ] `?page=2&page_size=25` returns correct slice with pagination metadata
- [ ] `?workspace_id=<uuid>&workflow_state=draft` filters results correctly
- [ ] `?ordering=-created_at` sorts descending by creation date
- [ ] page_size exceeding 100 is capped or returns HTTP 400
- [ ] Pagination metadata fields `count`, `next`, `previous`, `results` are always present in list responses

---

### REQ-L3-RA002-004: Preset-gesteuerte Feld-Filterung in der Serialisierung

Der DataSerializer SHALL die von COMP-RA-004 (PresetGuard) über IF-RA-INT-004 gelieferte `FieldFilter`-Entscheidung auswerten und Felder, die nicht im aktiven Workspace-Preset erlaubt sind, aus der Serialisierungsausgabe ausschließen. Pflichtfelder des aktiven Presets, die im Request fehlen, SHALL als Validierungsfehler behandelt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Field absent in `permitted_fields` is not included in serialized response
- [ ] Field listed in `required_fields` but missing in PATCH body returns HTTP 400
- [ ] Serializer applies `FieldFilter` before generating response — not after
- [ ] Unit test: Extended-preset includes `change_reason`; Minimal-preset excludes it

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
