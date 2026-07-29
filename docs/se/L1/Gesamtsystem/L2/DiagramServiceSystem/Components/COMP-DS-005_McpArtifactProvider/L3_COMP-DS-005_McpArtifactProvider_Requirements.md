---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-21T23:20:00Z"
schema_version: "1.0.0"
---
# L3 McpArtifactProvider Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-DS-005_McpArtifactProvider
> **Parent:** L2_DiagramServiceSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der McpArtifactProvider übersetzt das standardisierte MCP (Model Context Protocol) Format auf die domänenspezifische API des DiagramManagers, sodass KI-Agenten Diagramme lesen können.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`McpArtifactProvider` (Klasse):** Implementiert das MCP-Tool-Interface.
- **`McpFormatter` (Modul):** Helferfunktion, um `RenderableDiagram` DTOs in lesbares Markdown für LLMs umzuwandeln.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MAP-001 (MCP Tool 'artifact.get' Adapter) | Registriert einen Callback für `artifact.get` im McpServer. Nimmt Argumente (`diagram_id`) entgegen. Ruft `DiagramManager.get()` auf. Formatiert den Rückgabewert als Markdown (z.B. innerhalb von ```mermaid...``` Blöcken), damit Agenten es nativ lesen können. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-L1-033:** Callback-Aufruf aus dem `McpServer` Framework.
- **Ausgänge (Outbound):**
  - **Internal:** Aufruf der `get(id)` Methode am `COMP-DS-001_DiagramManager`.

---

## 5. Architectural Rationale

**ADR-L3-MAP-01 — Spezifische Formatierung für LLMs**
*Entscheidung:* Der Provider liefert nicht einfach JSON-Rohdaten, sondern hüllt Diagramme explizit in Markdown-Codeblöcke.
*Rationale:* KI-Agenten (die Konsumenten von MCP) "verstehen" visuelle Syntax wie Mermaid besser, wenn sie syntaktisch korrekt ausgezeichnet ist. Das erleichtert der KI die Analyse von Diagrammen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
*Designation: component (terminal) — decomposition_status: terminal*
