# L2 IcdManagement Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-028 (primär)
- Ziel: terminal (keine L3-Zerlegung)

---

## Systemzweck

Das IcdManagementSystem verwaltet Schnittstellen zwischen ArchitectureElements als versionierte Interface Control Documents (ICDs). Es setzt Design-by-Contract durch, indem es Vorbedingungen, Nachbedingungen und Invarianten als semantische Verträge speichert. Es prüft Änderungen auf Kompatibilität, meldet Breaking-Change-Warnungen und integriert sich in die Baseline-Erstellung, um Schnittstellenverträge in Snapshots einzufrieren.

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-037 | input | control | `create_icd`, `update_icd`, `validate_compatibility`, `get_icd_history` vom ApplicationService (ARCH-L1-004) |
| IF-L1-038 | input | control | `get_icd_versions(workspace_id)` für Snapshot vom BaselineService (ARCH-L1-006) |
| IF-L1-039 | output | data | TraceLink `realizes` zwischen ICD und ArchitectureElement an TraceabilityEngine (ARCH-L1-007) |
| IF-L1-040 | output | data | Icd-Entity, IcdVersion-Entity (immutable) an PersistenceLayer (ARCH-L1-010) |
| IF-L1-041 | output | data | Breaking-Change-Events an AuditLog (ARCH-L1-012) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-ICD-001: ICD CRUD und Versionierung

Das IcdManagementSystem SHALL vollständiges CRUD für Interface Control Documents bereitstellen. Jede Änderung eines ICDs MUSS eine neue, unveränderliche Version (IcdVersion) erzeugen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Erstellen eines ICD erzeugt Version 1.
- [ ] Jedes Update erzeugt eine neue Version.
- [ ] Versionen können nicht nachträglich modifiziert werden.

**Interfaces:**
- Incoming: IF-L1-037
- Outgoing: IF-L1-040

**Traceability:** REQ-L1-028
**Rationale:** Unveränderliche Schnittstellenverträge sind essenziell für Systemintegration.

---

### REQ-L2-ICD-002: Design-by-Contract Modellierung

Das IcdManagementSystem SHALL ICDs mit Feldern für Richtung, Typ, semantische Beschreibung, Vorbedingungen (Preconditions), Nachbedingungen (Postconditions) und Invarianten verwalten.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] ICD-Entität unterstützt alle geforderten Felder.
- [ ] Leere Felder sind erlaubt, Struktur muss jedoch vorgehalten werden.

**Interfaces:**
- Incoming: IF-L1-037
- Outgoing: IF-L1-040

**Traceability:** REQ-L1-028
**Rationale:** Setzt das vertragsbasierte Schnittstellendesign nach Systems Engineering Standards um.

---

### REQ-L2-ICD-003: Breaking-Change Erkennung

Das IcdManagementSystem SHALL bei jedem Update eine semantische Kompatibilitätsprüfung durchführen. Inkompatible Änderungen (z.B. Verschärfung von Vorbedingungen, Aufweichung von Nachbedingungen) MÜSSEN erkannt und als Breaking-Change-Warnung gemeldet werden.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Update mit Breaking-Change liefert eine spezifische Warnung im Response-Payload zurück.

**Interfaces:**
- Incoming: IF-L1-037

**Traceability:** REQ-L1-028
**Rationale:** Verhindert unbeabsichtigte Zerstörung von Systemintegrationen durch Schnittstellenänderungen.

---

### REQ-L2-ICD-004: Traceability-Verknüpfung (Typ: realizes)

Das IcdManagementSystem SHALL bei Erstellung eines ICD die Verknüpfung zu den betroffenen ArchitectureElements (Source und Target) über den TraceLink-Typ `realizes` in der TraceabilityEngine anlegen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] TraceLink `realizes` wird zwischen ICD und ArchitectureElement erstellt.

**Interfaces:**
- Incoming: IF-L1-037
- Outgoing: IF-L1-039

**Traceability:** REQ-L1-028
**Rationale:** ICDs verknüpfen Architekturkomponenten und müssen im Traceability-Graph navigierbar sein.

---

### REQ-L2-ICD-005: Baseline-Integration

Das IcdManagementSystem SHALL aktuelle ICD-Versionen für den Baseline-Snapshot auf Anfrage bereitstellen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `get_icd_versions` liefert die korrekten Versionen für den Snapshot-Scope.

**Interfaces:**
- Incoming: IF-L1-038

**Traceability:** REQ-L1-028
**Rationale:** Schnittstellenverträge müssen Teil von reproduzierbaren Projekt-Baselines sein.

---

### REQ-L2-ICD-006: Audit-Logging für Breaking Changes

Das IcdManagementSystem SHALL erkannte Breaking-Change-Events in das AuditLog schreiben.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Bei Breaking-Change wird ein dedizierter AuditLog-Eintrag generiert.

**Interfaces:**
- Outgoing: IF-L1-041

**Traceability:** REQ-L1-028
**Rationale:** Erhöhte Sichtbarkeit und Nachverfolgbarkeit für kritische Schnittstellenbrüche.

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

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-ICD | 6 |
| Mandatory | 0 |
| Desired | 6 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 1 (REQ-L1-028) |
| Abgedeckte REQ-L1 (mitwirkend) | 0 |
| Referenzierte Interfaces | IF-L1-037..IF-L1-041 (alle 5) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Handoff: HOFF-20260621-002 | Parent: REQ-L1-028 | Architektur-Referenz: ARCH-L1-014*
*Designation: component (terminal) — decomposition_status: terminal*
