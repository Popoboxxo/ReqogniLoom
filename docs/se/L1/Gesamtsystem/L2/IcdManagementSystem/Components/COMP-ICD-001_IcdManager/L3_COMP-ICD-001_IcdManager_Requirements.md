# L3 COMP-ICD-001_IcdManager Requirements

> **Level:** L3 (Component-Anforderungen)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Component:** COMP-ICD-001_IcdManager
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-ICD-001, REQ-L2-ICD-005
- Architektur-Komponente: COMP-ICD-001_IcdManager aus L2_IcdManagementSystem_Architecture.md

---

## Komponenten-Zweck

Die Komponente IcdManager koordiniert die CRUD-Operationen für Interface Control Documents (ICDs). Sie stellt sicher, dass jede Änderung an einem ICD zu einer neuen, unveränderlichen Version führt. Ferner delegiert sie Prüfungen an den ContractValidator, Traceability-Updates an den TraceabilityConnector und Audit-Einträge an den AuditLogger. Zudem verarbeitet sie Anfragen für Baseline-Snapshots.

---

## Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-037 | input | control | `create_icd`, `update_icd`, `validate_compatibility`, `get_icd_history` vom ApplicationService |
| IF-L1-038 | input | control | `get_icd_versions(workspace_id)` vom BaselineService |
| IF-L1-040 | output | data | Persistierung der Icd-Entity und IcdVersion-Entity an PersistenceLayer |
| IF-ICD-INT-001 | output | control/data | Delegation der Vertragsprüfung an ContractValidator |
| IF-ICD-INT-002 | output | control/data | Delegation der TraceLink-Erstellung an TraceabilityConnector |
| IF-ICD-INT-003 | output | control/data | Delegation des Audit-Loggings an AuditLogger |

---

## L3 Anforderungen

### REQ-L3-ICD-001-001: ICD CRUD Koordination und Versionierung
Die Komponente IcdManager SHALL alle eingehenden CRUD-Anfragen (IF-L1-037) verarbeiten und für jede Änderung an einem ICD eine neue, unveränderliche Version (`IcdVersion`) generieren sowie an den PersistenceLayer (IF-L1-040) übergeben.
**Domain:** software
**Priority:** mandatory
**Traceability:** REQ-L2-ICD-001
**Acceptance Criteria:**
- [ ] Bei der Erstellung wird Version 1 persistiert.
- [ ] Bei jedem Update wird eine neue Version generiert und persistiert.
- [ ] Existierende Versionen werden niemals überschrieben.

### REQ-L3-ICD-001-002: Delegation der Kompatibilitätsprüfung
Die Komponente IcdManager SHALL bei jedem ICD-Update den ContractValidator (IF-ICD-INT-001) aufrufen, um die neue Version gegen die alte Version auf Breaking Changes zu prüfen.
**Domain:** software
**Priority:** mandatory
**Traceability:** REQ-L2-ICD-001, REQ-L2-ICD-003
**Acceptance Criteria:**
- [ ] Vor der Persistierung eines Updates wird IF-ICD-INT-001 aufgerufen.
- [ ] Bei erkannten Breaking Changes wird der AuditLogger (IF-ICD-INT-003) asynchron getriggert.

### REQ-L3-ICD-001-003: Delegation der TraceLink-Erstellung
Die Komponente IcdManager SHALL bei erfolgreicher Erstellung eines ICDs den TraceabilityConnector (IF-ICD-INT-002) aufrufen, um das ICD mit den jeweiligen Architekturelementen zu verknüpfen.
**Domain:** software
**Priority:** mandatory
**Traceability:** REQ-L2-ICD-004
**Acceptance Criteria:**
- [ ] Nach erfolgreicher Speicherung eines neuen ICDs wird IF-ICD-INT-002 mit `icd_id`, `source_id`, `target_id` aufgerufen.

### REQ-L3-ICD-001-004: Baseline Snapshot Integration
Die Komponente IcdManager SHALL den Endpunkt `get_icd_versions` (IF-L1-038) bereitstellen und anhand der `workspace_id` die zu diesem Zeitpunkt gültigen, unveränderlichen ICD-Versionen zurückliefern.
**Domain:** software
**Priority:** mandatory
**Traceability:** REQ-L2-ICD-005
**Acceptance Criteria:**
- [ ] Aufruf von IF-L1-038 liefert alle aktuellen ICD-Versionen für den übergebenen Scope zurück.

---

*Erstellt durch se-requirements-Agent | 2026-06-21*
