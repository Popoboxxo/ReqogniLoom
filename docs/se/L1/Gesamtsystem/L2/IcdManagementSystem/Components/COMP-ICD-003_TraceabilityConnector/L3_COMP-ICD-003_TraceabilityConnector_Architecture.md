# L3 COMP-ICD-003_TraceabilityConnector Architecture

> **Level:** L3 (Component internal design)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Component:** COMP-ICD-003_TraceabilityConnector
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further architecture decomposition.

---

## 1. Verantwortlichkeit

Die Komponente `TraceabilityConnector` ist ein technischer Adapter. Sie entkoppelt den `IcdManager` von der spezifischen Implementierung der externen `TraceabilityEngine` und transformiert ICD-Identitäten in gerichtete TraceLinks.

---

## 2. Internal White-Box Design (Klassen & Datenstrukturen)

Da diese Komponente terminal ist, wird hier ihr internes Software-Design spezifiziert.

### 2.1 Klassen und Hauptmethoden

**Klasse `TraceabilityConnector`**
Ein Adapter/Facade-Service zur Kommunikation mit der TraceabilityEngine.

- `link_to_architecture(icd_id: str, source_id: str, target_id: str) -> None`
  - Konstruiert zwei TraceLink-Entitäten (oder einen bidirektionalen/komplexen Graphen-Link).
  - Ein Link geht vom `source_id` zum `icd_id` (Typ: `implements/realizes`).
  - Ein Link geht vom `target_id` zum `icd_id` (Typ: `implements/realizes`).
  - Führt den externen RPC-/API-Aufruf zur TraceabilityEngine aus.

### 2.2 Datenstrukturen

- `TraceLinkDTO`:
  - `source: str` (z.B. die ID des Architecture Elements)
  - `target: str` (die `icd_id`)
  - `link_type: str` (Konstante `"realizes"`)

---

## 3. Erfüllung der L3 Anforderungen

| REQ-ID | Erfüllung durch Design |
|--------|------------------------|
| REQ-L3-ICD-003-001 | Die Methode `link_to_architecture` generiert exakt die geforderten TraceLink-DTOs und delegiert sie synchron oder asynchron an die externe Engine via IF-L1-039. |

---

## 4. Schnittstellen Mapping

| IF-ID | Implementierung in Code |
|-------|-------------------------|
| IF-ICD-INT-002 | `IcdManager` nutzt diese In-Process-Methode. |
| IF-L1-039 | Ausgehender HTTP/gRPC-Aufruf oder Message-Queue-Publish an die `TraceabilityEngine`. |

---

*Erstellt durch se-architect-Agent | 2026-06-21*
