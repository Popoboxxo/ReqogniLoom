# L2 ReqIFService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** ReqIFServiceSystem (NEU)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-27
> **Status:** formalisiert
> **Designation:** system (L3-Zerlegung erforderlich)

---

## Traceability

- Abgeleitet von: REQ-L1-034 (primär)
- Ziel: L3-Zerlegung in COMP-RQ-001 (ReqIFParser) und COMP-RQ-002 (ReqIFSerializer)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RQ-EXT-IN-001 | input | data | Import/Export-Request vom ApplicationService (ReqIF-Datei oder internes Modell) |
| IF-RQ-EXT-OUT-001 | output | data | Persistenz an PersistenceLayer (Artefakte, Hierarchien) |
| IF-RQ-EXT-OUT-002 | output | data | TraceLink-CRUD an TraceabilityEngine (SpecRelations → TraceLinks) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-RQ-001: ReqIF-Import

Der ReqIFService SHALL ReqIF-Dateien (.reqif) importieren und SpecObjects, SpecRelations und SpecHierarchies auf das interne Datenmodell abbilden. SpecObjects SHALL als Requirements oder ArchitectureElements (abhängig vom SpecType) erzeugt werden. SpecRelations SHALL als TraceLinks abgebildet werden. SpecHierarchies SHALL als Parent-Child-Hierarchie abgebildet werden. Validierungsfehler SHALL mit Elementreferenz und Ursache zurückgemeldet werden.

**Domain:** software
**Priority:** desired
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Import einer ReqIF-Datei mit 100+ SpecObjects erzeugt korrespondierende interne Artefakte
- [ ] SpecRelations werden als TraceLinks (Typ: `derives-from` oder `satisfies`) abgebildet
- [ ] SpecHierarchies werden als Parent-Child-Beziehungen abgebildet
- [ ] ReqIF-Datei mit fehlerhafter Struktur → Fehlermeldung mit Elementreferenz + Ursache
- [ ] Import über synchrone Web-API und UI triggerbar

**Interfaces:**
- Incoming: IF-RQ-EXT-IN-001
- Outgoing: IF-RQ-EXT-OUT-001, IF-RQ-EXT-OUT-002

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L1-034
**Rationale:** ReqIF-Import ermöglicht Migration aus DOORS/Polarion in regulierten Industrien.

---

### REQ-L2-RQ-002: ReqIF-Export

Der ReqIFService SHALL interne Artefakte (Requirements, ArchitectureElements, TraceLinks, Hierarchien) als ReqIF-Datei exportieren. Die exportierte Datei SHALL SpecObjects, SpecRelations und SpecHierarchies vollständig enthalten. Re-Import des exportierten ReqIF SHALL strukturgleiche Artefakte erzeugen (Roundtrip-Treue).

**Domain:** software
**Priority:** desired
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Export eines Workspace als ReqIF enthält alle SpecObjects, SpecRelations und SpecHierarchies
- [ ] Re-Import des exportierten ReqIF erzeugt strukturgleiche Artefakte (Roundtrip-Test)
- [ ] Export über synchrone Web-API und UI triggerbar
- [ ] ReqIF-Datei ist valide gegen das ReqIF-Schema
- [ ] Attribute werden als ReqIF-Attribute-Typen abgebildet

**Interfaces:**
- Incoming: IF-RQ-EXT-IN-001
- Outgoing: IF-RQ-EXT-OUT-001, IF-RQ-EXT-OUT-002

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L1-034
**Rationale:** ReqIF-Export ermöglicht Austausch mit externen Tools in regulierten Projekten.

---

## Traceability-Matrix: REQ-L2-RQ → REQ-L1

| REQ-L2-RQ | Titel | REQ-L1 | Priorität |
|-----------|-------|--------|-----------|
| REQ-L2-RQ-001 | ReqIF-Import | REQ-L1-034 | desired |
| REQ-L2-RQ-002 | ReqIF-Export | REQ-L1-034 | desired |

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
*Designation: system — decomposition_status: L3-Zerlegung erforderlich*
