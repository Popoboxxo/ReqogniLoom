---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-21T23:20:00Z"
schema_version: "1.0.0"
---
# L3 DiagramValidator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-DS-002_DiagramValidator
> **Parent:** L2_DiagramServiceSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der DiagramValidator ist zuständig für die syntaktische und typenspezifische Prüfung von Diagramm-Payloads, bevor diese vom DiagramManager gespeichert werden.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`DiagramValidator` (Klasse/Modul):** Bietet die Haupt-Einstiegsmethode `validate_payload(type, content) -> bool`.
- **`TypeParsers` (Strategien):** Für jeden unterstützten Diagramm-Typ (z.B. `MermaidParser`, `PlantUMLParser`) existiert ein eigener Parser, der die Syntax gegen bekannte Regeln oder Grammatiken prüft.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-DV-001 (Payload-Validierung nach Typ) | Die Methode routet den Content an den spezifischen Parser. Ein syntaktischer Fehler wirft eine typspezifische Exception (mit Zeilennummer), die gefangen und in eine lesbare Ablehnung übersetzt wird. |
| REQ-L3-DV-002 (Typenprüfung) | Ein Dictionary (Registry) mappt Typ-Strings auf Parser. Unbekannte Typ-Strings werfen sofort eine `UnsupportedDiagramTypeError`. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-DS-INT-001:** Synchroner In-Process Call durch `COMP-DS-001_DiagramManager`.

---

## 5. Architectural Rationale

**ADR-L3-DV-01 — Strategy Pattern für Validatoren**
*Entscheidung:* Einsatz des Strategy Patterns zur Entkopplung verschiedener Diagrammtypen.
*Rationale:* Da das System in Zukunft weitere Diagramm-Technologien (z.B. C4-PlantUML, D2) unterstützen soll, können neue Parser konfliktfrei als neue Strategien registriert werden (Open-Closed Principle).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
*Designation: component (terminal) — decomposition_status: terminal*
