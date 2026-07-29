---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:05:00Z"
schema_version: "1.0.0"
---

# L3 DataSerializer Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RA-002_DataSerializer
> **Parent:** L2_RestApiAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der DataSerializer ist der zentrale Adapter für JSON-Serialisierung und Deserialisierung sowie Input-Validierung. Er deserialisiert eingehende JSON-Request-Bodies in typisierte DTOs, validiert gegen Feldschema und Businessregeln, unterstützt Pagination/Filtering/Sorting, lokalisiert Fehlermeldungen (DE/EN), wendet Preset-basierte Feldfiltration an und serialisiert Ausgaben zu JSON. Er ist damit der Schnittstellen-Isolator zwischen HTTP-JSON und typisiertem Backend.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`BaseSerializer` (Abstrakte Klasse):** Basis-Template für Entity-Serializer. Definiert die Methoden `deserialize(json_dict, direction)`, `serialize(dto, direction)`, `validate(data)`.
- **Entity-Serializer-Klassen:** Für jede der 7 Domain-Entitäten eine Serializer-Klasse (z.B. `RequirementSerializer`, `ArtifactSerializer`, etc.). Erbt von `BaseSerializer`.
- **`PaginationHelper` (Klasse):** Utility für Pagination. Parst Query-Parameter (`page`, `page_size`, `ordering`), liefert `PaginationMetadata {count, next, previous, page_size}`.
- **`FieldFilterApplier` (Klasse):** Wendet `FieldFilter` (von PresetGuard) auf Serializer an. Excludiert nicht-erlaubte Felder aus Serialisierung. Validiert Pflichtfelder beim Deserialisieren.
- **`I18nMessageLookup` (Klasse):** Lokalisiert Fehlermeldungen basierend auf `Accept-Language` Header.
- **`QuerysetOptimizer` (Klasse):** Orchestriert `select_related()` und `prefetch_related()` Aufrufe zur N+1-Query-Vermeidung.

### 2.2 Datenstrukturen

- **`SerializationRequest` (Pydantic Model):** Input-Parameter {json_body, query_params, entity_type, direction ("in"|"out")}.
- **`ValidationError` (Exception):** {field_name, message (lokalisiert), error_code}.
- **`PaginatedResponse` (Pydantic Model):** {results: [DTO], count: int, next: str|None, previous: str|None, page_size: int}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RA002-001 (Deserialisierung & Validierung) | Entity-Serializer nutzen Pydantic-Schemas mit Type Hints und Validatoren. Ungültige JSON → `ValidationError` mit feldspezifischen Details. Unbekannte Felder → Configurable Modus (strict: reject, permissive: ignore). |
| REQ-L3-RA002-002 (i18n Fehlermeldungen) | I18nMessageLookup liest `Accept-Language`-Header. Fehler-Keys in separater Translations-Datei (de.json, en.json). Fehlende Keys → CI-Fehler via Build-Hook. Default: Englisch. |
| REQ-L3-RA002-003 (Pagination/Filtering/Sorting) | PaginationHelper parst Query-Parameter. offset-basierte Pagination mit Default 25, Max 100. Filtering nach workspace_id und workflow_state. Sorting via ordering-Parameter. Response: {results, count, next, previous}. |
| REQ-L3-RA002-004 (Preset-Feldfiltration) | FieldFilterApplier nimmt FieldFilter (von PresetGuard) und excludiert Felder nicht in `permitted_fields`. Pflichtfelder aus `required_fields` werden beim Deserialisieren validiert. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RA-INT-003:** Bidirektional mit COMP-RA-001 (HttpEndpointController): `deserialize(request) -> ValidatedDTO | ValidationError` und `serialize(dto) -> JSON_Response`.
- **IF-RA-INT-004:** Von COMP-RA-004 (PresetGuard): `FieldFilter {permitted_fields, required_fields}`.
- **IF-RA-INT-006:** Von COMP-RA-005 (OpenApiGenerator): `SerializerSchemas {entity_type, field_defs, validators}`.

**Ausgänge (Outbound):**
- **IF-RA-INT-007:** Anfordern von QuerysetOptimizer: `get_optimized_queryset(entity_type, nested_fields) -> QuerySet` und `invalidate_cache(entity_type, entity_id)`.

---

## 5. Architectural Rationale

**ADR-L3-RA2-01 — Pydantic-basierte Serializer statt Django-REST-Framework-allein**

*Entscheidung:* Entity-Serializer nutzen Pydantic-Schemas (mit Type Hints) als Primary Data Model, zusammen mit Django ORM für Datenbankzugriff.

*Rationale:* Erfüllt REQ-L3-RA002-001 (strikte Typisierung, feldspezifische Validierungsfehler). Pydantic bietet bessere Fehlerbehandlung und i18n-Unterstützung als DRF-Serializer allein. Alternative: Nur DRF-Serializer → würde keine feldspezifischen Details bei Fehler 400 liefern.

---

**ADR-L3-RA2-02 — FieldFilter als explizites Konzept**

*Entscheidung:* PresetGuard liefert FieldFilter-Objekt, das Serializer vor Serialisierung anwendet (nicht nach).

*Rationale:* Erfüllt REQ-L3-RA002-004 und verhindert Sicherheitslücken durch versehentliches Durchlassen verbotener Felder in der Response. Alternative: Feldfilterung nach Serialisierung → könnten Daten zwischenzeitig in nicht-gefilterte Form fließen.

---

**ADR-L3-RA2-03 — I18n via CI-überprüfte Translation-Dateien**

*Entscheidung:* Alle Error-Keys müssen in de.json und en.json existieren. Fehlende Übersetzung → Build-Fehler.

*Rationale:* Erfüllt REQ-L3-RA002-002 vollständig. Verhindert Laufzeit-Überraschungen durch fehlende Übersetzungen. Alternative: Zur Laufzeit defaulten → würde inkonsistente Fehlermeldungen erlauben.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
