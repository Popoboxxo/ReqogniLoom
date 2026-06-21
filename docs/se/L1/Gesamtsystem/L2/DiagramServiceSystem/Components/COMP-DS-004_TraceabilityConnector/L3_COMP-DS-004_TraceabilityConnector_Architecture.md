---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-21T23:20:00Z"
schema_version: "1.0.0"
---
# L3 TraceabilityConnector Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-DS-004_TraceabilityConnector
> **Parent:** L2_DiagramServiceSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TraceabilityConnector verknüpft Diagramme systematisch mit anderen System-Artefakten, indem er TraceLinks in der TraceabilityEngine anlegt.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`TraceabilityConnector` (Klasse):** Methode `create_document_link(diagram_id, target_id)`.
- **`TraceEngineClient` (Adapter):** Kapselt HTTP/RPC-Aufrufe an die externe TraceabilityEngine und standardisiert Fehler.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-TC-001 (Erstellung von Document-Links) | Formatiert einen Payload `{ "source_id": diagram_id, "target_id": target_id, "link_type": "documents" }` und sendet diesen per `TraceEngineClient` an die TraceabilityEngine. Wirft eine domänenspezifische Exception bei Fehlern. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-DS-INT-003:** Synchroner In-Process Call durch `COMP-DS-001_DiagramManager`.
- **Ausgänge (Outbound):**
  - **IF-L1-034:** HTTP POST Request an die TraceabilityEngine.

---

## 5. Architectural Rationale

**ADR-L3-TC-01 — Entkoppelte Adapter-Schicht**
*Entscheidung:* Der TraceabilityConnector kommuniziert nicht direkt via HTTP Requests im Code, sondern über einen separaten `TraceEngineClient`.
*Rationale:* Falls sich das Protokoll der TraceabilityEngine (z.B. von REST zu gRPC) ändert, muss nur der Client ausgetauscht werden, die Geschäftslogik in `create_document_link` bleibt unberührt.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
*Designation: component (terminal) — decomposition_status: terminal*
