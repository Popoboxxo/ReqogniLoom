# L2 RestApiAdapter Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** RestApiAdapterSystem (ARCH-L1-002)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** system (Leaf-AE — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-006 (primär), REQ-L1-007 (mitwirkend), REQ-L1-010 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-015 (mitwirkend), REQ-L1-016 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RA-EXT-IN-001 | input | data | HTTP/JSON-Requests von API-Clients mit Bearer Token |
| IF-RA-EXT-IN-002 | input | data | HTTP/JSON-Requests von ReactFrontend mit Bearer Token |
| IF-RA-EXT-OUT-001 | output | data | JSON-Responses mit HTTP-Statuscodes, Body, Headers |
| IF-RA-EXT-OUT-002 | output | data | OpenAPI-3.0-Spezifikation unter `/api/v1/schema/` |
| IF-RA-EXT-OUT-003 | output | data | Swagger-UI unter `/api/v1/schema/swagger-ui/` |
| IF-RA-EXT-OUT-004 | output | ARCH-L1-011 | data | Token-Validierung, Auth-Kontext |
| IF-RA-EXT-OUT-005 | output | ARCH-L1-004 | data | Use-Case-Methoden (In-Process Python) |
| IF-RA-EXT-OUT-006 | output | ARCH-L1-008 | data | Preset-Abfrage: `is_feature_enabled(key, workspace_id)` |

---

## L2 Subsystem-Anforderungen

### REQ-L2-RA-001: REST-CRUD-Endpunkte für alle Entitäten
Der RestApiAdapter SHALL vollständige CRUD-Endpunkte (GET list, GET detail, POST, PATCH, DELETE) unter `/api/v1/` für alle sieben Domain-Entitäten bereitstellen: Artifact, Requirement, ArchitectureElement, TestCase, TraceLink, Baseline und WorkflowDefinition.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Für jede der 7 Entitäten existieren GET (Liste + Detail), POST, PATCH, DELETE Endpunkte
- [ ] Integration-Test: POST `/api/v1/requirements/` → 201 + JSON
- [ ] GET `/api/v1/requirements/{id}/` → 200 + JSON
- [ ] PATCH → 200, DELETE → 204
- [ ] OpenAPI-Spec listet alle Endpunkte

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-005


**Traceability:** REQ-L1-006
**Rationale:** Programmatischer Zugriff auf alle Artefakttypen via REST ist die Grundlage für CI/CD-Integration.

---

### REQ-L2-RA-002: Auto-generierte OpenAPI-Spezifikation
Der RestApiAdapter SHALL eine vollständige, auto-generierte OpenAPI 3.0 Spezifikation unter `/api/v1/schema/` bereitstellen. Eine Swagger-UI SHALL unter `/api/v1/schema/swagger-ui/` zugänglich sein.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] GET `/api/v1/schema/` liefert valides OpenAPI-3.0-JSON mit allen CRUD-Endpunkten
- [ ] GET `/api/v1/schema/swagger-ui/` rendert interaktive API-Dokumentation
- [ ] OpenAPI-Client-Generator erzeugt fehlerfrei einen TypeScript-Client

**Interfaces:**
- Outgoing: IF-RA-EXT-OUT-002, IF-RA-EXT-OUT-003


**Traceability:** REQ-L1-006
**Rationale:** Maschinenlesbarer Kontext und Typ-sichere Client-Generierung.

---

### REQ-L2-RA-003: API-Response-Performance unter 200ms
Der RestApiAdapter SHALL auf Standard-Queries (GET list, GET detail) innerhalb von 200ms beim 95. Perzentil antworten — bei bis zu 10.000 Requirements, inklusive Serialization und Datenbank-Query, exklusive Netzwerk-Latenz. Voraussetzung für die Einhaltung dieses Latenz-Ziels ist die konsequente Vermeidung von N+1-Query-Mustern via `select_related` und `prefetch_related` (siehe REQ-L2-RA-013).

**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Lasttest: 10.000 Requirements, 100 gleichzeitige GET → p95 ≤ 200ms
- [ ] Datenbank-Indizes für Standard-Query-Pfade vorhanden
- [ ] Kein N+1-Query-Muster auf List- und Detail-Endpunkten (verifizierbar via Query-Count-Messung)

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001


**Traceability:** REQ-L1-026, REQ-L1-006 (mitwirkend)
**Rationale:** Performance ist entscheidend für die Akzeptanz der Zielgruppe. N+1-Vermeidung ist strukturelle Voraussetzung für das Latenz-Ziel bei verschachtelten Responses.

---

### REQ-L2-RA-004: Backend-Fehlermeldungen i18n (DE/EN)
Der RestApiAdapter SHALL alle API-Fehlermeldungen in Deutsch und Englisch bereitstellen. Die Sprache SHALL durch den `Accept-Language`-Header bestimmt werden (Fallback: Englisch). Fehlende Translation-Keys MÜSSEN als Build-Fehler behandelt werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Request mit `Accept-Language: de` → Fehlermeldung auf Deutsch
- [ ] Request mit `Accept-Language: en` → Fehlermeldung auf Englisch
- [ ] Request ohne Header → Englisch als Fallback
- [ ] CI: Neue Fehlermeldung ohne DE-Translation → Build-Fehler

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002 (Accept-Language Header)
- Outgoing: IF-RA-EXT-OUT-001 (Lokalisierte Fehlermeldung)


**Traceability:** REQ-L1-016
**Rationale:** REQ-L1-016 fordert zweiseitige Fehlermeldungen.

---

### REQ-L2-RA-005: Bearer-Token-Authentifizierung für alle Endpunkte
Der RestApiAdapter SHALL Bearer-Token-Authentifizierung auf allen API-Endpunkten unter `/api/v1/` erzwingen (Ausnahme: OpenAPI-Spec-Endpunkte). Requests ohne gültigen Token SHALL mit HTTP 401 abgewiesen werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Request ohne Token → HTTP 401
- [ ] Request mit ungültigem/expiriertem Token → HTTP 401
- [ ] OpenAPI-Spec-Endpunkte ohne Auth erreichbar
- [ ] Intern: Token-Validierung delegiert an ARCH-L1-011

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-004


**Traceability:** REQ-L1-006, REQ-L1-010 (mitwirkend)
**Rationale:** Token-basierte Auth ist Voraussetzung für sichere API-Nutzung und RBAC.

---

### REQ-L2-RA-006: RBAC-Enforcement auf API-Ebene
Der RestApiAdapter SHALL rollenbasierte Zugriffskontrolle für jede API-Operation und Ressource erzwingen. Vor der Delegation an den ApplicationService MUSS der Adapter prüfen, ob die Rollen des Nutzers die Operation erlauben. Unautorisierte Operationen SHALL mit HTTP 403 abgewiesen werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Viewer: GET erlaubt, POST/PATCH/DELETE → HTTP 403
- [ ] Editor: GET/POST/PATCH/DELETE auf eigene Workspace-Ressourcen
- [ ] Admin: Alle Operationen erlaubt
- [ ] Approver: Zusätzlich Workflow-Transitionen mit Ziel-State „approved“ (nur Extended)
- [ ] RBAC-Check vor Delegation an ApplicationService

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-004


**Traceability:** REQ-L1-010
**Rationale:** Rollenbasierte Zugriffskontrolle ist Voraussetzung für Approval-Workflows.

---

### REQ-L2-RA-007: Audit-Log-Auslösung bei Schreiboperationen
Der RestApiAdapter SHALL sicherstellen, dass jede Schreiboperation (POST, PATCH, DELETE) einen Audit-Log-Eintrag über den ApplicationService auslöst. Der Eintrag SHALL die authentifizierte Nutzer-Identität, Operationstyp, betroffene Entity-ID und Zeitstempel enthalten.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] POST → Audit-Log-Eintrag mit actor=User, op=create
- [ ] PATCH → Audit-Log-Eintrag mit actor=User, op=update
- [ ] DELETE → Audit-Log-Eintrag mit actor=User, op=delete
- [ ] GET-Operationen lösen keinen Audit-Log-Eintrag aus

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-005


**Traceability:** REQ-L1-011 (mitwirkend)
**Rationale:** Vollständige Auditierbarkeit aller Änderungen.

---

### REQ-L2-RA-008: Preset-basierte Endpunkt- und Feldsichtbarkeit
Der RestApiAdapter SHALL zur Laufzeit die PresetConfigEngine konsultieren, um zu bestimmen, welche Endpunkte und Felder basierend auf dem aktiven Workspace-Preset sichtbar/aktiv sind. Nicht erlaubte Endpunkte SHALL mit HTTP 404/403 beantwortet werden. Nicht erlaubte Felder SHALL aus der Serialization ausgeschlossen werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal-Preset: Baseline-Endpunkte → HTTP 404
- [ ] Extended-Preset: Approver-bezogene Endpunkte sichtbar
- [ ] Feld-Beispiel: `change_reason` Pflichtfeld im Extended → PATCH ohne → HTTP 400
- [ ] Preset-Abfrage pro Request via `is_feature_enabled(key, workspace_id)`

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-006


**Traceability:** REQ-L1-007 (mitwirkend)
**Rationale:** Configurable Rigor — Preset-Konfiguration steuert den Funktionsumfang.

---

### REQ-L2-RA-009: Standardisierte HTTP-Fehlercodes und Response-Format
Der RestApiAdapter SHALL standardisierte HTTP-Statuscodes und ein konsistentes JSON-Fehlerformat verwenden. Das Fehlerformat SHALL enthalten: machine-readable Error-Code, human-readable Message (lokalisiert), optionale Feld-Details.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] HTTP 200/201/204 für erfolgreiche Operationen
- [ ] HTTP 400/401/403/404/409/422/500 für Fehlerfälle
- [ ] Error-Format: `{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [...]}}`

**Interfaces:**
- Outgoing: IF-RA-EXT-OUT-001


**Traceability:** REQ-L1-006
**Rationale:** Vorhersehbare, typ-sichere API-Responses für Client-Integration.

---

### REQ-L2-RA-010: Pagination, Filtering, Sorting für Listen-Endpunkte
Der RestApiAdapter SOLLTE Pagination, Filtering und Sorting auf allen Listen-Endpunkten unterstützen. Pagination SHALL cursor- oder offset-basiert sein mit konfigurierbarer Page-Size.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] GET `?page=2&page_size=25` → 25 Ergebnisse, Seite 2
- [ ] GET `?workspace_id=<uuid>&workflow_state=draft` → gefilterte Ergebnisse
- [ ] GET `?ordering=-created_at` → sortiert absteigend
- [ ] Response enthält Pagination-Metadaten: `{"count", "next", "previous", "results"}`
- [ ] Default page_size: 25, Maximum: 100

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001


**Traceability:** REQ-L1-006
**Rationale:** Effiziente Navigation großer Datenmengen.

---

### REQ-L2-RA-011: Tenant-Kontext-Propagation
Der RestApiAdapter SHALL den aktiven Tenant aus dem authentifizierten Token extrahieren und in den Request-Kontext propagieren. Alle Datenbankabfragen MÜSSEN automatisch nach `tenant_id` gefiltert werden. Der Adapter DARF den Tenant-Filter nicht umgehen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bearer Token enthält Tenant-Information
- [ ] Adapter extrahiert Tenant-ID und übergibt sie im Auth-Kontext
- [ ] v1: Genau ein Default-Tenant
- [ ] Adapter manipuliert den Tenant-Filter nicht

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-004, IF-RA-EXT-OUT-005


**Traceability:** REQ-L1-015 (mitwirkend)
**Rationale:** Multi-Tenancy-Vorbereitung mit Row-Level-Isolation.

---

### REQ-L2-RA-012: Keine Geschäftslogik in der Adapter-Schicht
Der RestApiAdapter DARF KEINE Geschäftslogik implementieren. Der Adapter SHALL eine reine Translation-Schicht sein: HTTP-Request → validieren/serialisieren → an ApplicationService delegieren → serialisieren → HTTP-Response.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Adapter enthält keine `if`-Bedingungen für Geschäftsregeln
- [ ] Adapter enthält keine Workflow-Transition-Logik
- [ ] Adapter ruft ausschließlich ApplicationService-Methoden auf
- [ ] Ausnahmen: HTTP-spezifische Validierung, Serialization, Auth-Delegation

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-005


**Traceability:** REQ-L1-006
**Rationale:** Klare Schichtentrennung verhindert Duplizierung zwischen REST und MCP.

---

### REQ-L2-RA-013: N+1-Query-Vermeidung bei verschachtelten Responses
Der RestApiAdapter SHALL für alle List- und Detail-Endpunkte, die verschachtelte Entitäten liefern (TraceLinks, TestCases, Children-Artifacts), `select_related` für ForeignKey-Beziehungen und `prefetch_related` für ManyToMany- und Reverse-ForeignKey-Beziehungen im DRF-ViewSet-Queryset verwenden. Kein N+1-Query-Muster darf in Produktionscode vorhanden sein. Häufig gelesene verschachtelte Baumstrukturen (Artifact-Trees, vollständige Workspaces) SHALL serverseitig gecacht werden; der Cache MUSS bei Mutationen (POST/PATCH/DELETE auf betroffenen Entitäten) invalidiert werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle ViewSets mit verschachtelten Responses verwenden `select_related`/`prefetch_related` im `.get_queryset()`
- [ ] Query-Count-Messung via `django-silk` oder `django-debug-toolbar`: GET auf Requirement mit 50 TraceLinks → maximal 3 DB-Queries (kein lineares Wachstum mit Entitätszahl)
- [ ] Serverseitiges Caching (Django-Cache-Framework + Redis) für Artifact-Tree- und Workspace-Endpunkte
- [ ] Cache-Invalidierung: POST/PATCH/DELETE auf Requirement, TraceLink oder TestCase → betroffener Cache-Eintrag wird invalidiert
- [ ] Kein N+1-Pattern in Codebasis (automatisierbare Prüfung via Query-Count-Assertions in Tests)

**Interfaces:**
- Incoming: IF-RA-EXT-IN-001, IF-RA-EXT-IN-002
- Outgoing: IF-RA-EXT-OUT-001
- Internal: IF-RA-EXT-OUT-005


**Traceability:** REQ-L1-026 (primär), REQ-L1-006 (mitwirkend)
**Rationale:** DRF erzeugt bei verschachtelten Serialisierungen ohne explizite Queryset-Optimierung N+1-Queries. Bei 10.000 Requirements mit TraceLinks überschreitet dies das 200ms-Latenz-Ziel von REQ-L2-RA-003 um ein Vielfaches. Redis-Caching für Baumstrukturen reduziert die DB-Last bei häufig wiederholten Read-Zugriffen.

---

## Traceability-Matrix: REQ-L2-RA → REQ-L1

| REQ-L2-RA | Titel | REQ-L1 (primär) | REQ-L1 (mitwirkend) |
|-----------|-------|-----------------|---------------------|
| REQ-L2-RA-001 | REST-CRUD-Endpunkte | REQ-L1-006 | — |
| REQ-L2-RA-002 | OpenAPI-Spezifikation | REQ-L1-006 | — |
| REQ-L2-RA-003 | API-Performance | REQ-L1-026 | REQ-L1-006 |
| REQ-L2-RA-004 | i18n Fehlermeldungen | REQ-L1-016 | — |
| REQ-L2-RA-005 | Bearer-Token-Auth | REQ-L1-006 | REQ-L1-010 |
| REQ-L2-RA-006 | RBAC-Enforcement | REQ-L1-010 | — |
| REQ-L2-RA-007 | Audit-Log-Auslösung | REQ-L1-011 | — |
| REQ-L2-RA-008 | Preset-Sichtbarkeit | REQ-L1-007 | — |
| REQ-L2-RA-009 | HTTP-Fehlercodes | REQ-L1-006 | — |
| REQ-L2-RA-010 | Pagination/Filter/Sort | REQ-L1-006 | — |
| REQ-L2-RA-011 | Tenant-Propagation | REQ-L1-015 | — |
| REQ-L2-RA-012 | Keine Geschäftslogik | REQ-L1-006 | — |
| REQ-L2-RA-013 | N+1-Query-Vermeidung | REQ-L1-026 | REQ-L1-006 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-RA | 13 |
| Mandatory | 12 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-006, REQ-L1-026 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-007, REQ-L1-010, REQ-L1-011, REQ-L1-015, REQ-L1-016 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Rest → REQ-L2-RA, Template-Standardisierung*
*Designation: system (Leaf-AE) — decomposition_status: terminal*

---

## Erweiterung v2 — REQ-L2-RA-014..015 (aus REQ-L1-044 und REQ-L1-038)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-032 → REQ-L1-044, REQ-L0-026 → REQ-L1-038

---

### REQ-L2-RA-014: REST-Endpunkte für Semantisches Projekt-Glossar

**Implementation State:** Not Implemented
**Review Findings:** Keine API-Routen für Glossar vorhanden. Voraussetzung: REQ-L2-AS-033 (ApplicationService).
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-044 (← REQ-L0-032, SN-32). Companion zu REQ-L2-AS-033.

Der RestApiAdapter MUSS REST-Endpunkte für das Semantische Projekt-Glossar
(REQ-L2-AS-033) exponieren. Die Endpunkte MÜSSEN Authentifizierung (Bearer-Token)
und Workspace-Scoping (Mandanten-Isolation) durchsetzen.
Das Glossar MUSS für AI-Agenten als maschinenlesbares JSON-Array abrufbar sein.

**Endpunkte:**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `GET` | `/workspaces/{id}/glossary` | Alle Glossar-Einträge abrufen |
| `POST` | `/workspaces/{id}/glossary` | Neuen Term anlegen |
| `GET` | `/workspaces/{id}/glossary/{term_id}` | Einzelnen Term abrufen |
| `PATCH` | `/workspaces/{id}/glossary/{term_id}` | Term aktualisieren |
| `DELETE` | `/workspaces/{id}/glossary/{term_id}` | Term löschen |
| `POST` | `/workspaces/{id}/glossary/check-text` | Text auf unbekannte Begriffe prüfen |

**Akzeptanzkriterien:**
- AC1: `GET /workspaces/{id}/glossary` → JSON-Array aller Terme (maschinenlesbar)
- AC2: `POST` ohne Auth → HTTP 401
- AC3: `POST` in fremdem Workspace → HTTP 403
- AC4: `POST /glossary/check-text` → Liste unbekannter/inkonsistenter Begriffe (Warnung)
- AC5: Alle Endpunkte in OpenAPI-Spezifikation dokumentiert

**Verifikationsmethode:** API-Test (pytest + httpx) — alle Endpunkte, Auth + Scoping
**Verifikiert durch:** L2-RA-Test-014
**Abgeleitet von:** REQ-L1-044
**Übergeordnete REQ-L0:** REQ-L0-032

---

### REQ-L2-RA-015: REST-Endpunkte für Semantische Suche und Hybrid-Suche

**Implementation State:** Not Implemented
**Review Findings:** Keine `/search/semantic`- oder `/search/hybrid`-Endpunkte vorhanden.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-038 (← REQ-L0-026, SN-26). Companion zu REQ-L2-VS-001..003.

Der RestApiAdapter MUSS REST-Endpunkte für semantische und hybride Suche exponieren,
die intern an den VectorSearchService (REQ-L2-VS-001..003) delegieren.

**Endpunkte:**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `POST` | `/workspaces/{id}/search/semantic` | Semantische Vektorsuche |
| `POST` | `/workspaces/{id}/search/hybrid` | Hybrid-Suche (Vektor + Volltext) |
| `POST` | `/workspaces/{id}/vector-index/rebuild` | Admin: Vektorindex neu aufbauen |

**Akzeptanzkriterien:**
- AC1: `POST /search/semantic` → Top-N Ergebnisse mit Score innerhalb 500 ms
- AC2: `POST /search/hybrid` → kombinierte Ergebnisse mit konfigurierbarer Gewichtung
- AC3: Ohne Auth → HTTP 401
- AC4: Admin-Endpunkt `rebuild` → nur für Admin-Rolle (HTTP 403 sonst)
- AC5: Alle Endpunkte in OpenAPI-Spezifikation dokumentiert

**Verifikationsmethode:** API-Test + Latenztest (p95 < 500 ms)
**Verifikiert durch:** L2-RA-Test-015
**Abgeleitet von:** REQ-L1-038
**Übergeordnete REQ-L0:** REQ-L0-026

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-RA-014..015 aus REQ-L1-044, REQ-L1-038)*

---

## Erweiterung v3 — REQ-L2-RA-016..017 (aus REQ-L1-065 und REQ-L1-066)

> **Datum:** 2026-07-03 | **Quelle:** UI-Befund für Listen-Skalierbarkeit (REQ-L0-038, REQ-L0-040)

---

### REQ-L2-RA-016: REST-Endpunkte mit serverseitiger Paginierung

**Implementation State:** Not Implemented
**Review Findings:** Aktuell werden alle Daten ohne Limit geladen.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-065 (← REQ-L0-040, SN-40).

Der RestApiAdapter MUSS auf allen `GET list`-Routen für Artefakte (Requirements, ArchitectureElements, etc.) serverseitige Paginierung unterstützen.

**Akzeptanzkriterien:**
- AC1: `GET /workspaces/{id}/requirements/` unterstützt `page` und `page_size` Query-Parameter.
- AC2: API-Response-Format ist `{"count": N, "next": URL, "previous": URL, "results": [...]}`.
- AC3: Pagination-Parameter werden transparent an den DRF-Paginator durchgereicht.

**Verifikationsmethode:** API-Test mit > 100 Requirements (Prüfen ob nur page_size Elemente zurückkommen)
**Verifikiert durch:** L2-RA-Test-016
**Abgeleitet von:** REQ-L1-065
**Übergeordnete REQ-L0:** REQ-L0-040

---

### REQ-L2-RA-017: REST-Endpunkte mit serverseitigem Filter & Sort

**Implementation State:** Not Implemented
**Review Findings:** Keine DRF FilterBackends im Einsatz.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-066 (← REQ-L0-038, SN-38).

Der RestApiAdapter MUSS auf allen `GET list`-Routen Filterung nach Suchbegriffen, Status und Kategorie sowie Sortierung nach konfigurierbaren Feldern unterstützen.

**Akzeptanzkriterien:**
- AC1: `GET` akzeptiert `?search=...` für die Volltextsuche.
- AC2: `GET` akzeptiert `?status=...` und `?category=...` für exakte Filterung.
- AC3: `GET` akzeptiert `?ordering=...` (z.B. `?ordering=-created_at`) für aufsteigende/absteigende Sortierung.
- AC4: Diese Parameter werden via DjangoFilterBackend, SearchFilter und OrderingFilter von DRF verarbeitet.

**Verifikationsmethode:** API-Test mit Filter-Parametern
**Verifikiert durch:** L2-RA-Test-017
**Abgeleitet von:** REQ-L1-066
**Übergeordnete REQ-L0:** REQ-L0-038
