---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 CapabilityInterface Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-LA-001_CapabilityInterface
> **Parent:** L2_LlmAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die CapabilityInterface-Komponente definiert die stabile abstrakte Schnittstelle für alle LLM-Provider. Sie bietet die abstrakte Basisklasse `LlmCapabilityInterface` mit drei Operationen (`validate_artifact`, `decompose_requirement`, `check_consistency`) und drei standardisierte Ergebnisdatenklassen (`LlmResult`, `LlmDecompositionResult`, `LlmConsistencyResult`). Sie stellt sicher, dass kein Domain-Modul den konkreten Provider kennt — der Vertrag ist ausschließlich über dieses Interface definiert. Provider-Bibliotheken werden nicht importiert.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`LlmCapabilityInterface` (Abstract Base Class):** Definiert die drei abstrakten Methoden (kein Implementierung, keine Provider-Abhängigkeit).
- **`LlmResult` (Dataclass):** Standard-Ergebnisformat mit score, suggestions, provider, model, token_usage.
- **`LlmDecompositionResult` (Dataclass):** Erweitert LlmResult um children (list of decomposed sub-items).
- **`LlmConsistencyResult` (Dataclass):** Erweitert LlmResult um issues (list of identified inconsistencies).

### 2.2 Datenstrukturen

- **LlmResult:**
  - `score`: float (0.0–1.0, validated)
  - `suggestions`: list[str]
  - `provider`: str (z.B. "anthropic", "openai", "azure")
  - `model`: str (z.B. "claude-3-opus", "gpt-4")
  - `token_usage`: int | None (total tokens or None if not available)

- **LlmDecompositionResult (extends LlmResult):**
  - `children`: list[dict] — each dict contains decomposed sub-item data (id, title, type, etc.)

- **LlmConsistencyResult (extends LlmResult):**
  - `issues`: list[dict] — each dict contains issue details (id, severity, description)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-LA001-001 (Abstrakte Interface) | Abstrakte Basisklasse mit drei @abstractmethod deklarationen. Konkrete Provider-Subklassen müssen alle drei implementieren. Direktes Instanziieren wirft TypeError. |
| REQ-L3-LA001-002 (Datenklassen) | Drei Dataclasses (Python 3.7+) mit field-Validierung. `score` wird in __post_init__ validiert (0.0–1.0), andernfalls ValueError. `LlmDecompositionResult` und `LlmConsistencyResult` erweitern LlmResult. |
| REQ-L3-LA001-003 (Provider-Isolation) | Keine Imports von anthropic, openai, ollama, azure in diesem Modul. Nur Standard-Library und Typing-Imports. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - Keine direkten externen Schnittstellen. Wird von CapabilityRouter (IF-LA-INT-001) indirekt verwendet.

- **Ausgänge (Outbound):**
  - **IF-LA-INT-003:** ProviderRegistry-Implementierungen erben von dieser Basisklasse (keine direkten Aufrufe).

---

## 5. Architectural Rationale

**ADR-L3-LA001-01 — Abstrakte Basisklasse statt Protokoll/Interface**
*Entscheidung:* Verwendung von Python ABC (Abstract Base Class) statt strukturellem Typing (Protokoll).
*Rationale:* Explizite Verträge sind leichter zu validieren und zu dokumentieren. Fehlerbehandlung ist klarer (TypeError bei unvollständiger Implementierung). Erfüllt REQ-L3-LA001-001.
*Alternative abgelehnt:* typing.Protocol (strukturelles Typing) — würde zulassen, dass inkomplette Implementierungen zur Laufzeit fehlschlagen.

**ADR-L3-LA001-02 — Score-Validierung in __post_init__**
*Entscheidung:* Dataclass-Validierung erfolgt in __post_init__, nicht in Setter oder Custom-Descriptor.
*Rationale:* Pythonic und standardmäßig für Dataclasses. Verhindert ungültige Instanzen direkt nach Erstellung. Erfüllt REQ-L3-LA001-002.
*Alternative abgelehnt:* Property-basierte Validierung — komplexer, nicht pythonic für Dataclasses.

**ADR-L3-LA001-03 — Datenklassen ohne Provider-Abhängigkeit**
*Entscheidung:* LlmResult und Subklassen sind reine Datenklassen, importieren keine Provider-Bibliotheken.
*Rationale:* Garantiert, dass dieses Modul in Umgebungen ohne Provider-SDKs importierbar ist. Erfüllt REQ-L3-LA001-003 vollständig.
*Alternative abgelehnt:* Conditional Imports von Provider-Bibliotheken — würde Abhängigkeitsauflösung komplizieren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
