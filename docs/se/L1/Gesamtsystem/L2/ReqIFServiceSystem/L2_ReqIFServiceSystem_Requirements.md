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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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


**Traceability:** REQ-L1-034
**Rationale:** ReqIF-Import ermöglicht Migration aus DOORS/Polarion in regulierten Industrien.

---

### REQ-L2-RQ-002: ReqIF-Export
Der ReqIFService SHALL interne Artefakte (Requirements, ArchitectureElements, TraceLinks, Hierarchien) als ReqIF-Datei exportieren. Die exportierte Datei SHALL SpecObjects, SpecRelations und SpecHierarchies vollständig enthalten. Re-Import des exportierten ReqIF SHALL strukturgleiche Artefakte erzeugen (Roundtrip-Treue).

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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


**Traceability:** REQ-L1-034
**Rationale:** ReqIF-Export ermöglicht Austausch mit externen Tools in regulierten Projekten.

---

## Traceability-Matrix: REQ-L2-RQ → REQ-L1

---

## Erweiterung v2 — Vollständige Requirement-Beschreibungen (REQ-L2-RQ-001..002)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-023 → REQ-L1-034

---

### REQ-L2-RQ-001: ReqIF-Import (Hierarchische Anforderungsstrukturen einlesen)

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent. ReqIFService-Klasse ist geplant aber nicht umgesetzt.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-034 (← REQ-L0-023, SN-23). Priority: desired.

Der ReqIFService MUSS valide ReqIF-Dateien (`.reqif`, `.reqifz`) einlesen und die
enthaltenen Anforderungsobjekte (SpecObjects) mit ihren Hierarchiebeziehungen
(SpecHierarchy) verlustfrei in das ReqFlow-Datenmodell überführen.
TraceLinks zwischen Anforderungen (SpecRelations) MÜSSEN als ReqFlow-TraceLinks
importiert werden. Attribut-Mappings (ReqIF-Attribut → ReqFlow-Feld) MÜSSEN
konfigurierbar sein. Unbekannte Attribute SOLLTEN in einem `custom_attributes`-JSON-Feld
gespeichert werden (kein Datenverlust).

**Schnittstellen:**
- `POST /workspaces/{id}/import/reqif` — Multipart-Upload der .reqif/.reqifz Datei
- Body: `{ "attribute_mapping": { "ReqIF.Text": "description", "ReqIF.Name": "title" } }`
- Response: `{ "imported": N, "warnings": [...], "errors": [...] }`
- Interner Service-Call: `ReqIFParser.parse(file) → List[SpecObject]`

**Akzeptanzkriterien:**
- AC1: Valide .reqif-Datei → alle SpecObjects als Requirements importiert mit Hierarchie
- AC2: SpecRelations → TraceLinks vom Typ `derives-from` importiert
- AC3: Konfiguriertes Attribut-Mapping wird angewendet
- AC4: Unbekannte Attribute landen in `custom_attributes` (kein Datenverlust)
- AC5: Invalide .reqif-Datei (XML-Fehler) → HTTP 422 + Fehlerdetails
- AC6: Import-Report enthält Anzahl importierter Requirements, Warnungen, Fehler

**Verifikationsmethode:** Integrationstest mit Test-ReqIF-Datei (DOORS-Export-Beispiel)
**Verifikiert durch:** L2-RQ-Test-001
**Abgeleitet von:** REQ-L1-034
**Übergeordnete REQ-L0:** REQ-L0-023

---

### REQ-L2-RQ-002: ReqIF-Export (Anforderungsstrukturen als ReqIF ausgeben)

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-034 (← REQ-L0-023, SN-23). Priority: desired.

Der ReqIFService MUSS einen Workspace oder eine Baseline als valide ReqIF-Datei
exportieren können. Der Export MUSS die Anforderungshierarchie (parent-child),
TraceLinks (als SpecRelations) und alle Standard-Felder (title, description, status,
level) korrekt als ReqIF-SpecObjects und SpecHierarchy abbilden.
Der Export MUSS mit gängigen SE-Tools (DOORS Next, Polarion) kompatibel sein.

**Schnittstellen:**
- `GET /workspaces/{id}/export/reqif` → Download `.reqif`-Datei (Content-Type: application/reqif+xml)
- `GET /baselines/{id}/export/reqif` → Baseline-Stand als ReqIF
- Query-Parameter: `?include_tracelinks=true` (default: true)

**Akzeptanzkriterien:**
- AC1: Export enthält alle Requirements des Workspace als SpecObjects
- AC2: parent-child-Hierarchie korrekt als SpecHierarchy abgebildet
- AC3: TraceLinks als SpecRelations im Export enthalten (wenn `include_tracelinks=true`)
- AC4: Exportierte Datei ist valide XML (Schema-konform ReqIF 1.0.1)
- AC5: Baseline-Export enthält nur Requirements des Baseline-Stands
- AC6: Export-Datei ist mit DOORS Next re-importierbar (Kompatibilitätstest)

**Verifikationsmethode:** Integrationstest — Export + Schema-Validierung + Re-Import-Test
**Verifikiert durch:** L2-RQ-Test-002
**Abgeleitet von:** REQ-L1-034
**Übergeordnete REQ-L0:** REQ-L0-023

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-RQ-001..002 vollständig ausgearbeitet)*
