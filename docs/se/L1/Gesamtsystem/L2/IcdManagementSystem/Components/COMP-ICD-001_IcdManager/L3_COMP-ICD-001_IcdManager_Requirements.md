decomposition_status: terminal

# L3 COMP-ICD-001_IcdManager Architecture

> **Level:** L3 (Component internal design)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Component:** COMP-ICD-001_IcdManager
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further architecture decomposition.

---

## 1. Verantwortlichkeit

Die Komponente `IcdManager` implementiert die zentrale Koordinationslogik für Interface Control Documents (ICDs). Sie nimmt CRUD-Operationen entgegen, stellt die Unveränderlichkeit von ICD-Versionen sicher und delegiert spezifische Aufgaben wie Vertragsprüfung, TraceLink-Erstellung und Audit-Logging an die benachbarten Komponenten.

---

## 2. Internal White-Box Design (Klassen & Datenstrukturen)

Da diese Komponente terminal ist, wird hier ihr internes Software-Design (Klassen und Methoden) spezifiziert.

### 2.1 Klassen und Hauptmethoden

**Klasse `IcdManager`**
Zentrale Service-Klasse zur Verarbeitung der Use-Cases.

- `create_icd(payload: IcdCreateDTO) -> IcdEntity`
  - Validiert Input, erzeugt ein initiales `IcdEntity` mit Version 1.
  - Ruft den `TraceabilityConnector` auf, um die Architektur-Verknüpfungen herzustellen.
  - Persistiert das Ergebnis über den `PersistenceLayer`.
- `update_icd(icd_id: str, payload: IcdUpdateDTO) -> IcdEntity`
  - Lädt die aktuellste Version des ICD.
  - Ruft `ContractValidator.validate_contract()` auf.
  - Wenn Breaking Changes erkannt werden, wird `AuditLogger.log_breaking_change()` asynchron getriggert.
  - Erzeugt ein neues `IcdVersion`-Objekt (Version inkrementiert) und persistiert es unveränderlich (Append-Only).
- `get_icd_history(icd_id: str) -> list[IcdVersion]`
  - Liest alle Versionen eines ICDs aus dem `PersistenceLayer`.
- `get_icd_versions(workspace_id: str) -> list[IcdVersion]`
  - Implementiert den Baseline-Snapshot-Endpunkt für den `BaselineService`. Filtert nach dem aktuellen Gültigkeitsstand im `workspace_id`.

### 2.2 Datenstrukturen

- `IcdEntity`: Repräsentiert die logische Identität der Schnittstelle (ID, Name, Source-ID, Target-ID).
- `IcdVersion`: Immutable Value Object, das die vertraglichen Details (Richtung, Typ, Payload, Vor-/Nachbedingungen, Invarianten) zu einer bestimmten Revisionsnummer enthält.
- `IcdCreateDTO` / `IcdUpdateDTO`: Datentransferobjekte für die Eingabeschnittstellen.

---

## 3. Erfüllung der L3 Anforderungen

| REQ-ID | Erfüllung durch Design |
|--------|------------------------|
| REQ-L3-ICD-001-001 | Die Methode `update_icd` modifiziert niemals bestehende `IcdVersion`-Objekte, sondern hängt streng neue an (Append-Only) und nutzt IF-L1-040 zur Speicherung. |
| REQ-L3-ICD-001-002 | `update_icd` injiziert den `ContractValidator` (IF-ICD-INT-001) und wertet dessen `ValidationResult` aus. Bei Breaking Changes wird der `AuditLogger` asynchron gerufen. |
| REQ-L3-ICD-001-003 | `create_icd` ruft den `TraceabilityConnector` (IF-ICD-INT-002) auf, sobald das Objekt im Speicher instanziiert ist. |
| REQ-L3-ICD-001-004 | Die Methode `get_icd_versions` filtert den Persistence-Store nach `workspace_id` und liefert die Snapshot-Menge zurück (IF-L1-038). |

---

## 4. Schnittstellen Mapping

| IF-ID | Implementierung in Code |
|-------|-------------------------|
| IF-L1-037 | REST/GraphQL-Controller der Applikation ruft die Methoden von `IcdManager` auf. |
| IF-L1-038 | BaselineService nutzt die Methode `get_icd_versions()`. |
| IF-L1-040 | Aufruf von `save()` an einem injizierten Repository (`PersistenceLayer`). |
| IF-ICD-INT-001 | Direkter Methodenaufruf an `ContractValidator`. |
| IF-ICD-INT-002 | Direkter Methodenaufruf an `TraceabilityConnector`. |
| IF-ICD-INT-003 | Fire-and-Forget Methodenaufruf (z.B. Celery-Task oder Background-Thread) an `AuditLogger`. |

---

*Erstellt durch se-architect-Agent | 2026-06-21*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-ICD001-U000: Auto-derived from REQ-L2-ICD-011
Abgeleitet von: REQ-L2-ICD-011

### REQ-L3-ICD001-U001: Auto-derived from REQ-L2-ICD-010
Abgeleitet von: REQ-L2-ICD-010

### REQ-L3-ICD001-U002: Auto-derived from REQ-L2-ICD-007
Abgeleitet von: REQ-L2-ICD-007

### REQ-L3-ICD001-U003: Auto-derived from REQ-L2-ICD-014
Abgeleitet von: REQ-L2-ICD-014

### REQ-L3-ICD001-U004: Auto-derived from REQ-L2-ICD-016
Abgeleitet von: REQ-L2-ICD-016

### REQ-L3-ICD001-U005: Auto-derived from REQ-L2-ICD-009
Abgeleitet von: REQ-L2-ICD-009

### REQ-L3-ICD001-U006: Auto-derived from REQ-L2-ICD-002
Abgeleitet von: REQ-L2-ICD-002

### REQ-L3-ICD001-U007: Auto-derived from REQ-L2-ICD-015
Abgeleitet von: REQ-L2-ICD-015

### REQ-L3-ICD001-U008: Auto-derived from REQ-L2-ICD-012
Abgeleitet von: REQ-L2-ICD-012

### REQ-L3-ICD001-U009: Auto-derived from REQ-L2-ICD-013
Abgeleitet von: REQ-L2-ICD-013

### REQ-L3-ICD001-U010: Auto-derived from REQ-L2-ICD-005
Abgeleitet von: REQ-L2-ICD-005

### REQ-L3-ICD001-U011: Auto-derived from REQ-L2-ICD-006
Abgeleitet von: REQ-L2-ICD-006

### REQ-L3-ICD001-U012: Auto-derived from REQ-L2-ICD-004
Abgeleitet von: REQ-L2-ICD-004

### REQ-L3-ICD001-U013: Auto-derived from REQ-L2-ICD-003
Abgeleitet von: REQ-L2-ICD-003

### REQ-L3-ICD001-U014: Auto-derived from REQ-L2-ICD-001
Abgeleitet von: REQ-L2-ICD-001

### REQ-L3-ICD001-U015: Auto-derived from REQ-L2-ICD-008
Abgeleitet von: REQ-L2-ICD-008
