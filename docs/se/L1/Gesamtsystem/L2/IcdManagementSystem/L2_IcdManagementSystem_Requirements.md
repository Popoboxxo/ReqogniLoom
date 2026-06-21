# L2 IcdManagement Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** LEAF (terminal, keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-028 (primär), REQ-L1-003 (mitwirkend), REQ-L1-008 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-ICD-EXT-IN-001 | input | data | `create_icd`, `update_icd`, `validate_compatibility`, `get_icd_history` von ApplicationService (IF-L1-037) |
| IF-ICD-EXT-IN-002 | input | data | `get_icd_versions(workspace_id)` von BaselineService für Snapshot-Inklusion (IF-L1-038) |
| IF-ICD-EXT-OUT-001 | output | data | TraceLink `realizes` an TraceabilityEngine (ARCH-L1-007) (IF-L1-039) |
| IF-ICD-EXT-OUT-002 | output | data | Persistenz von Icd-Entity und IcdVersion-Entity (immutable) an PersistenceLayer (ARCH-L1-010) (IF-L1-040) |
| IF-ICD-EXT-OUT-003 | output | control | Breaking-Change-Events und schreibende Operationen an AuditLog (ARCH-L1-012) (IF-L1-041) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-ICD-001: ICD-Lebenszyklus — Erstellen und Metadaten

Der IcdManagementService SHALL vollständiges CRUD für Interface Control Documents (ICDs) zwischen ArchitectureElements bereitstellen. Jeder ICD SHALL mindestens folgende Metadatenfelder enthalten: eindeutige UUID, `source_element_id`, `target_element_id`, `direction` (`unidirectional` | `bidirectional`), `interface_type` (semantische Klassifikation, z.B. `data`, `control`, `energy`, `physical`), `title`, `description` und eine nicht-leere `version`-Kennung. Das System SHALL jeden ICD nach der Erstellung mit dem Versionszähler `1` initialisieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_icd(source=A, target=B, direction=unidirectional, type=data, title="...", description="...")` → ICD mit UUID, version=1, created_at
- [ ] `create_icd` ohne `source_element_id` → Fehler `"source_element_id is required"`
- [ ] `create_icd` ohne `direction` → Fehler `"direction is required"`
- [ ] `get_icd(icd_id)` → vollständige ICD-Daten inklusive aktueller Version und Metadaten
- [ ] `list_icds(workspace_id)` → alle ICDs im Workspace, sortiert nach created_at DESC

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028
**Rationale:** ICDs als strukturierte, versionierte Schnittstellenverträge erfordern ein vollständiges Lifecycle-Management mit klar definierten Pflichtfeldern.

---

### REQ-L2-ICD-002: ICD-Versionierung — Unveränderlichkeit freigegebener Versionen

Der IcdManagementService SHALL sicherstellen, dass jede veröffentlichte ICD-Version (Zustand `released`) unveränderlich ist. Eine Änderung an einem ICD mit Status `released` SHALL automatisch eine neue ICD-Version erzeugen, wobei die vorherige Version mit ihren vollständigen Feldinhalten erhalten bleibt. Der Versionszähler SHALL bei jeder Änderungsoperation inkrementiert werden. Eine direkte Mutation eines bestehenden `released`-Versionsdatensatzes SHALL abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] ICD Version 1 (released) → `update_icd(...)` → neue Version 2 erzeugt; Version 1 unverändert abrufbar
- [ ] Direkter Schreibzugriff auf IcdVersion-Entität mit `status=released` → Fehler `"Released ICD versions are immutable"`
- [ ] `get_icd_history(icd_id)` → Liste aller Versionen (1, 2, …) mit jeweiligen Feldinhalten und Zeitstempeln
- [ ] Version 1 nach Erstellung von Version 2 → Version 1 vollständig abrufbar mit unverändertem Inhalt

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028
**Rationale:** Unveränderlichkeit freigegebener ICD-Versionen ist Voraussetzung für formale Schnittstellenverträge und reproduzierbare Integrationsnachweise.

---

### REQ-L2-ICD-003: ICD-Lebenszyklusstatus — Freigabe- und Sperr-Workflow

Der IcdManagementService SHALL einen konfigurierbaren Lebenszyklusstatus für ICDs verwalten mit mindestens den Zuständen `draft`, `released` und `deprecated`. Status-Übergänge SHALL gegen eine definierte Transitionstabelle validiert werden: `draft → released` (Freigabe), `released → deprecated` (Ablösung), `released → draft` (Rückziehung, nur als neue Version). Ein ICD mit Status `deprecated` DARF NICHT als aktive Schnittstelle referenziert werden; das System SHALL bei Referenzierungsversuchen eine Warnung zurückgeben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `transition(icd_id, target=released)` von `draft` → OK, ICD in Version mit status=released
- [ ] `transition(icd_id, target=released)` von `deprecated` → Fehler `"Invalid transition: deprecated → released"`
- [ ] Neues ArchitectureElement referenziert ICD mit status=deprecated → Warnung `"Referenced ICD is deprecated"`
- [ ] `transition(icd_id, target=deprecated)` von `released` → OK; `get_icd` gibt status=deprecated zurück

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-002, IF-ICD-EXT-OUT-003

**Traceability:** REQ-L1-028
**Rationale:** Strukturierter Lifecycle verhindert den Einsatz veralteter Schnittstellenverträge und erzwingt explizite Freigabe- und Ablöseprozesse.

---

### REQ-L2-ICD-004: Design-by-Contract — Preconditions, Postconditions und Invarianten

Der IcdManagementService SHALL für jeden ICD optionale Design-by-Contract-Felder unterstützen: `preconditions` (Liste natürlichsprachlicher oder formaler Vorbedingungen), `postconditions` (Liste natürlichsprachlicher oder formaler Nachbedingungen) und `invariants` (Liste unveränderlicher Eigenschaften der Schnittstelle). Diese Felder SOLLEN im strukturierten Format (Liste von Zeichenketten) gespeichert werden. Das System SHALL keine syntaktische Validierung des Inhalts dieser Felder vornehmen — die Verantwortung für die inhaltliche Korrektheit liegt beim Ersteller.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_icd(..., preconditions=["Datenrate >= 100 kB/s"], postconditions=["Antwort innerhalb 50ms"], invariants=["Protokoll: CAN-Bus"])` → ICD mit DbC-Feldern gespeichert
- [ ] `get_icd(icd_id)` → DbC-Felder vollständig zurückgegeben
- [ ] `create_icd` ohne DbC-Felder → OK (Felder optional, leere Liste als Default)
- [ ] Neue Version eines ICD → DbC-Felder der Vorgängerversion in Versionshistorie erhalten

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028
**Rationale:** Design-by-Contract-Felder ermöglichen formale Vertragsausdrücke auf Schnittstellenebene und sind die Grundlage für semantische Kompatibilitätsprüfungen.

---

### REQ-L2-ICD-005: Semantische Kompatibilitätsprüfung — Breaking-Change-Detection

Der IcdManagementService SHALL bei jeder ICD-Aktualisierung eine semantische Kompatibilitätsanalyse zwischen der vorherigen und der neuen Version durchführen. Das System SHALL eine Änderung als Breaking Change klassifizieren, wenn mindestens eines der folgenden Kriterien erfüllt ist: (a) `direction` geändert, (b) `interface_type` geändert, (c) mindestens eine `precondition` entfernt oder inhaltlich verändert, (d) mindestens eine `invariant` entfernt oder inhaltlich verändert, (e) `source_element_id` oder `target_element_id` geändert. Das System SHALL bei erkanntem Breaking Change eine strukturierte Warnung mit `breaking_change: true`, einer Liste der geänderten Felder und dem Schweregrad (`critical` | `warning`) zurückgeben. Ein Breaking Change SHALL die Erstellung der neuen Version NICHT blockieren, aber im AuditLog protokolliert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Änderung von `direction` von `unidirectional` auf `bidirectional` → Response enthält `breaking_change: true`, `changed_fields: ["direction"]`, `severity: "critical"`
- [ ] Entfernen einer `invariant` → `breaking_change: true`, `changed_fields: ["invariants"]`, `severity: "critical"`
- [ ] Hinzufügen einer neuen `postcondition` (keine Entfernung) → `breaking_change: false`
- [ ] Änderung von `description` ohne DbC-Feld-Änderung → `breaking_change: false`
- [ ] Jeder Breaking Change → AuditLog-Eintrag mit `operation: "breaking_change_detected"`, `icd_id`, `version_from`, `version_to`

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-002, IF-ICD-EXT-OUT-003

**Traceability:** REQ-L1-028
**Rationale:** Semantische Breaking-Change-Detection ist die Kernfunktionalität des IcdManagementSystems — sie hebt ICDs von generischen TraceLinks ab und ermöglicht kontrollierte Schnittstellenentwicklung.

---

### REQ-L2-ICD-006: Explizite Kompatibilitätsprüfung (validate_compatibility)

Der IcdManagementService SHALL eine explizit aufrufbare Operation `validate_compatibility(icd_id, candidate_payload)` bereitstellen, die eine vorgeschlagene ICD-Aktualisierung gegen die aktuelle Version prüft, ohne eine neue Version zu erzeugen. Das Ergebnis SHALL dieselbe Struktur wie die implizite Breaking-Change-Detection (REQ-L2-ICD-005) zurückgeben: `compatible: true/false`, `breaking_change: true/false`, `changed_fields`, `severity`. Diese Operation SOLL als Pre-Flight-Prüfung vor tatsächlichen Schreiboperationen verwendbar sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `validate_compatibility(icd_id=X, candidate={direction: "bidirectional", ...})` → `{compatible: false, breaking_change: true, changed_fields: ["direction"], severity: "critical"}` ohne Persistierung
- [ ] `validate_compatibility` mit identischem Payload wie aktuelle Version → `{compatible: true, breaking_change: false}`
- [ ] `validate_compatibility` für nicht existierende ICD → Fehler `"ICD not found"`

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001

**Traceability:** REQ-L1-028
**Rationale:** Pre-Flight-Kompatibilitätsprüfung ermöglicht Clients (ApplicationService, MCP-Tools), Kompatibilität zu prüfen, bevor schreibende Operationen ausgeführt werden.

---

### REQ-L2-ICD-007: Traceability — Verknüpfung mit ArchitectureElements

Der IcdManagementService SHALL für jeden ICD genau einen TraceLink vom Typ `realizes` zwischen dem ICD und dem `source_element_id`-ArchitectureElement sowie einen weiteren TraceLink `realizes` zum `target_element_id`-ArchitectureElement erzeugen und über die TraceabilityEngine (IF-ICD-EXT-OUT-001) persistieren. Bei Erstellung einer neuen ICD-Version SHALL der TraceLink auf die neue Version zeigen; TraceLinks zu veralteten Versionen SOLLEN als `version_ref`-annotierte historische Links erhalten bleiben. Das System SHALL keine ICD anlegen können, wenn `source_element_id` oder `target_element_id` keinem existierenden ArchitectureElement entspricht.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_icd(source=A, target=B, ...)` → zwei TraceLinks `realizes` (ICD → A, ICD → B) in TraceabilityEngine
- [ ] TraceLink-Query auf ArchitectureElement A → enthält ICD als `realizes`-Relation
- [ ] `create_icd(source=NONEXISTENT, ...)` → Fehler `"source_element_id does not reference a valid ArchitectureElement"`
- [ ] Neue ICD-Version 2 erzeugt → `realizes`-TraceLink zeigt auf Version 2; Version-1-Link mit `version_ref: 1` erhalten

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-001, IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028, REQ-L1-003 (mitwirkend)
**Rationale:** TraceLinks vom Typ `realizes` verankern ICDs im Traceability-Graphen und ermöglichen Impact-Analysen auf Schnittstellenebene.

---

### REQ-L2-ICD-008: Baseline-Fähigkeit — ICD-Versionen in Baselines einbindbar

Der IcdManagementService SHALL die Operation `get_icd_versions(workspace_id)` exponieren, die für jeden ICD im angegebenen Workspace die jeweils aktuelle Version mit vollständigem Feldinhalt zurückgibt. Diese Operation MUSS von BaselineService (IF-ICD-EXT-IN-002) aufrufbar sein und dient der Aufnahme der ICD-Versionen in den Baseline-Snapshot. Der zurückgegebene Snapshot-Anteil SOLL `icd_id`, `version`, `status`, `direction`, `interface_type`, `preconditions`, `postconditions` und `invariants` je ICD enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_icd_versions(workspace_id=W)` → Liste von ICD-Versionsobjekten mit allen Feldern für alle ICDs in W
- [ ] `get_icd_versions` mit workspace_id ohne ICDs → leere Liste (kein Fehler)
- [ ] Baseline-Snapshot nach `create_icd` + `create_baseline` → Snapshot enthält ICD-Version im Abschnitt `icd_versions`
- [ ] Nachträgliche ICD-Änderung → existierender Baseline-Snapshot enthält weiterhin ursprüngliche ICD-Version
- [ ] `get_icd_versions` mit nicht existierender workspace_id → Fehler `"Workspace not found"` (kein partieller Snapshot)

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-002
- Outgoing: IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028, REQ-L1-008 (mitwirkend)
**Rationale:** Baseline-Fähigkeit von ICDs ist explizit in REQ-L1-028 gefordert und stellt sicher, dass Schnittstellenverträge in Anforderungsbaselines reproduzierbar dokumentiert werden.

---

### REQ-L2-ICD-009: Konsistenz-Validierung über mehrere ICDs

Der IcdManagementService SHALL auf Anfrage eine workspace-weite Konsistenz-Prüfung über alle ICDs durchführen und folgende Inkonsistenzklassen erkennen: (a) `direction`-Konflikte — ICD A→B mit `unidirectional` und ICD B→A mit `unidirectional` zwischen denselben Elementen, (b) verwaiste ICDs — `source_element_id` oder `target_element_id` referenziert ein nicht mehr existierendes ArchitectureElement, (c) `deprecated` ICDs, die noch als aktive `realizes`-Relation in der TraceabilityEngine eingetragen sind. Das Ergebnis SOLL eine strukturierte Liste von Inkonsistenz-Einträgen mit `icd_id`, `inconsistency_type` und `description` enthalten.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `validate_workspace_consistency(workspace_id)` → strukturierter Bericht mit `inconsistencies: [...]`
- [ ] Zwei ICDs zwischen A und B mit `unidirectional` in entgegengesetzten Richtungen → Inkonsistenz vom Typ `direction_conflict` gemeldet
- [ ] ICD mit `source_element_id` auf gelöschtem ArchitectureElement → Inkonsistenz vom Typ `orphaned_reference` gemeldet
- [ ] ICD mit `status=deprecated` und aktivem TraceLink → Inkonsistenz vom Typ `deprecated_active_reference` gemeldet
- [ ] Workspace ohne Inkonsistenzen → `{inconsistencies: [], status: "consistent"}`

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001
- Outgoing: IF-ICD-EXT-OUT-001, IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028
**Rationale:** Workspace-weite Konsistenzprüfung ermöglicht systematisches Qualitäts-Screening aller Schnittstellenverträge — insbesondere vor formalen Meilensteinen und Baseline-Erstellungen.

---

### REQ-L2-ICD-010: Audit-Trail für ICD-Operationen

Der IcdManagementService SHALL alle schreibenden Operationen (Erstellen, Aktualisieren, Status-Übergänge, Deprecation) mit Akteur (`created_by`, `modified_by`), Zeitstempel (`created_at`, `modified_at`), ICD-ID, Version und Operation-Typ im AuditLog (IF-ICD-EXT-OUT-003) protokollieren. Breaking-Change-Events SOLLEN als gesonderte Audit-Einträge mit `operation: "breaking_change_detected"` und den geänderten Feldern erfasst werden. Das System SHALL sicherstellen, dass kein schreibender Vorgang ohne korrespondierenden AuditLog-Eintrag abgeschlossen werden kann.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_icd(...)` → AuditLog-Eintrag `{operation: "icd_created", actor, icd_id, version: 1, timestamp}`
- [ ] `update_icd(...)` mit Breaking Change → zwei AuditLog-Einträge: `icd_updated` + `breaking_change_detected`
- [ ] `transition(icd_id, target=released)` → AuditLog-Eintrag `{operation: "icd_status_changed", from: "draft", to: "released"}`
- [ ] `deprecate_icd(icd_id)` → AuditLog-Eintrag mit `operation: "icd_deprecated"`, `actor`, `icd_id`, `timestamp` vorhanden; kein schreibender Vorgang bleibt ohne AuditLog-Eintrag

**Interfaces:**
- Outgoing: IF-ICD-EXT-OUT-003

**Traceability:** REQ-L1-028, REQ-L1-011 (mitwirkend)
**Rationale:** Vollständige Auditierbarkeit aller ICD-Operationen ist Voraussetzung für Compliance-Nachweise und die Nachvollziehbarkeit von Schnittstellenentwicklungen.

---

### REQ-L2-ICD-011: Atomare Persistierung mit transaktionalen Garantien

Der IcdManagementService SHALL sicherstellen, dass zusammengehörige Schreiboperationen atomar ausgeführt werden: Bei Erstellung einer neuen ICD-Version SHALL sowohl die IcdVersion-Entität als auch die zugehörigen TraceLink-Operationen in derselben Transaktion persistiert werden. Bei Fehler in einem Teilschritt SHALL ein vollständiges Rollback erfolgen — kein partiell geschriebener Zustand darf in der Datenbasis verbleiben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Fehler beim TraceLink-Schreiben nach IcdVersion-INSERT → vollständiges Rollback: keine neue IcdVersion in DB
- [ ] Fehler beim AuditLog-Schreiben → vollständiges Rollback der ICD-Operation
- [ ] Erfolgreiche `create_icd` → IcdVersion und TraceLinks atomar und konsistent in DB

**Interfaces:**
- Outgoing: IF-ICD-EXT-OUT-001, IF-ICD-EXT-OUT-002, IF-ICD-EXT-OUT-003

**Traceability:** REQ-L1-028, REQ-L1-025 (mitwirkend)
**Rationale:** ACID-Konsistenz ist fundamental — ein ICD ohne zugehörige TraceLinks würde den Traceability-Graphen korrumpieren.

---

### REQ-L2-ICD-012: Performance-Anforderung für ICD-Operationen

Der IcdManagementService SHALL Standard-Lese- und Schreiboperationen (create, get, list, update) für ICDs innerhalb der übergreifenden Latenz-SLAs halten: < 200 ms für Standard-Queries bei bis zu 10.000 Requirements im Workspace. Die `validate_workspace_consistency`-Operation (REQ-L2-ICD-009) SOLL für bis zu 500 ICDs pro Workspace innerhalb von 2 Sekunden abgeschlossen sein.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `get_icd(icd_id)` → < 200 ms (p95) bei Workspace mit 10.000 Requirements und 500 ICDs
- [ ] `list_icds(workspace_id)` mit 500 ICDs → < 200 ms (p95)
- [ ] `validate_workspace_consistency(workspace_id)` mit 500 ICDs → < 2 s (p95)
- [ ] `get_icd_versions(workspace_id)` mit 500 ICDs → < 500 ms (p95)

**Interfaces:**
- Incoming: IF-ICD-EXT-IN-001, IF-ICD-EXT-IN-002
- Outgoing: IF-ICD-EXT-OUT-002

**Traceability:** REQ-L1-028, REQ-L1-026 (mitwirkend)
**Rationale:** Performance-Konformität ist Voraussetzung für die Akzeptanz des Systems in der SE-Praxis; die Konsistenzprüfung hat ein großzügigeres Budget aufgrund ihrer aggregativen Natur.

---

## Traceability-Matrix: REQ-L2-ICD → REQ-L1

| REQ-L2-ICD | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|------------|----------------|---------------------|
| REQ-L2-ICD-001 | REQ-L1-028 | — |
| REQ-L2-ICD-002 | REQ-L1-028 | — |
| REQ-L2-ICD-003 | REQ-L1-028 | — |
| REQ-L2-ICD-004 | REQ-L1-028 | — |
| REQ-L2-ICD-005 | REQ-L1-028 | — |
| REQ-L2-ICD-006 | REQ-L1-028 | — |
| REQ-L2-ICD-007 | REQ-L1-028 | REQ-L1-003 |
| REQ-L2-ICD-008 | REQ-L1-028 | REQ-L1-008 |
| REQ-L2-ICD-009 | REQ-L1-028 | — |
| REQ-L2-ICD-010 | REQ-L1-028 | REQ-L1-011 |
| REQ-L2-ICD-011 | REQ-L1-028 | REQ-L1-025 |
| REQ-L2-ICD-012 | REQ-L1-028 | REQ-L1-026 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-ICD | 12 |
| Mandatory | 10 |
| Desired | 2 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-028 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-003, REQ-L1-008, REQ-L1-011, REQ-L1-025, REQ-L1-026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Revidiert durch se-critic-Agent | Audit HOFF-20260621-002 | 2026-06-21*
*Abgeleitet von: REQ-L1-028 (ARCH-L1-014 IcdManagement)*
*Designation: LEAF (terminal, keine L3-Zerlegung)*
