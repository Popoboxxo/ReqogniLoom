decomposition_status: terminal

# L3 CapabilityInterface Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-LA-001 — CapabilityInterface
> **Parent-System:** LlmAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Stabile abstrakte Schnittstelle (`LlmCapabilityInterface`) mit drei Operationen; standardisierte Ergebnisdatenklassen (`LlmResult`, `LlmDecompositionResult`, `LlmConsistencyResult`). Kein Domain-Modul darf den konkreten Provider kennen — der Vertrag ist ausschliesslich über dieses Interface definiert.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-LA-001 | LLM-Capability-Interface mit Provider-Abstraktion |
| REQ-L2-LA-004 | Standardisiertes LLM-Ergebnisformat |
| REQ-L2-LA-010 | PromptTemplate — Admin-editierbare Prompt-Slots |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-INT-001 | eingehend | COMP-LA-003 (CapabilityRouter) | `execute_capability(capability_name, **kwargs)` |
| IF-LA-INT-003 | eingehend | COMP-LA-002 (ProviderRegistry) | Klassenimplementierung (Vererbung): `validate_artifact`, `decompose_requirement`, `check_consistency` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

Keine direkten externen Schnittstellen; Systemgrenze wird vom CapabilityRouter gehalten.

---

## L3 Komponenten-Anforderungen

### REQ-L3-LA001-001: Abstrakte LLM-Capability-Schnittstelle


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die CapabilityInterface-Komponente SHALL eine abstrakte Basisklasse `LlmCapabilityInterface` bereitstellen mit den drei Operationen `validate_artifact(artifact_id: str) -> LlmResult`, `decompose_requirement(requirement_id: str) -> LlmDecompositionResult` und `check_consistency(workspace_id: str) -> LlmConsistencyResult`. Konkrete Provider-Klassen MÜSSEN alle drei Operationen implementieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Abstract base class `LlmCapabilityInterface` exists with all three abstract methods
- [ ] Instantiating `LlmCapabilityInterface` directly raises `TypeError`
- [ ] A concrete provider subclass that omits one method raises `TypeError` on instantiation
- [ ] Method signatures match defined contracts (parameter names, return type annotations)

---

### REQ-L3-LA001-002: Standardisierte Ergebnisdatenklassen


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die CapabilityInterface-Komponente SHALL die Datenklassen `LlmResult`, `LlmDecompositionResult` und `LlmConsistencyResult` definieren. `LlmResult` enthält: `score` (float, 0.0–1.0), `suggestions` (list[str]), `provider` (str), `model` (str), `token_usage` (int | None). `LlmDecompositionResult` erweitert `LlmResult` um `children` (list[dict]). `LlmConsistencyResult` erweitert `LlmResult` um `issues` (list[dict]). Ein `score`-Wert ausserhalb [0.0, 1.0] SHALL `ValueError` auslösen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `LlmResult(score=0.0, suggestions=[], provider="x", model="y", token_usage=None)` creates successfully
- [ ] `LlmResult(score=1.0, ...)` creates successfully
- [ ] `LlmResult(score=1.5, ...)` raises `ValueError`
- [ ] `LlmResult(score=-0.1, ...)` raises `ValueError`
- [ ] `LlmDecompositionResult` has `children` attribute; `LlmConsistencyResult` has `issues` attribute
- [ ] All three classes are importable from a single module without provider dependencies

---

### REQ-L3-LA001-003: Provider-Isolation durch Interface-Vertrag


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die CapabilityInterface-Komponente SHALL ausschliesslich abstrakte Typen und Datenklassen enthalten. Kein Import von Provider-Bibliotheken (anthropic, openai, ollama, azure) DARF direkt oder transitiv in diesem Modul vorkommen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Module dependency tree of `capability_interface` contains no provider SDK imports
- [ ] `import capability_interface` succeeds in an environment without any provider SDK installed
- [ ] Static analysis (e.g., `import-linter`) passes without provider-library violations

---

### REQ-L3-LA001-004: PromptTemplate-Erweiterung im Interface

Die CapabilityInterface-Komponente SHALL Methoden-Signaturen für `decompose_requirement` und `check_consistency` so erweitern, dass kontextspezifische PromptTemplates als Argumente (`prompt_template: str`) entgegengenommen werden können, anstatt sie hart in den Provider-Klassen zu verdrahten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `LlmCapabilityInterface.decompose_requirement` akzeptiert optionalen `prompt_template` Parameter.
- [ ] Provider-Implementierungen verwenden diesen Parameter zur Formatierung des finalen LLM-Prompts.

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-LA001-005: L3 Context Generators Implementation

Derives from REQ-L2-LLM-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-LA001-006: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-LLM-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.


## Derived L3 Requirements for Unmapped L2

### REQ-L3-LA001-U000: Auto-derived from REQ-L2-LLM-001
Abgeleitet von: REQ-L2-LLM-001

### REQ-L3-LA001-U001: Auto-derived from REQ-L2-LLM-008
Abgeleitet von: REQ-L2-LLM-008

### REQ-L3-LA001-U002: Auto-derived from REQ-L2-LLM-013
Abgeleitet von: REQ-L2-LLM-013

### REQ-L3-LA001-U003: Auto-derived from REQ-L2-LLM-006
Abgeleitet von: REQ-L2-LLM-006

### REQ-L3-LA001-U004: Auto-derived from REQ-L2-LLM-003
Abgeleitet von: REQ-L2-LLM-003

### REQ-L3-LA001-U005: Auto-derived from REQ-L2-LLM-004
Abgeleitet von: REQ-L2-LLM-004

### REQ-L3-LA001-U006: Auto-derived from REQ-L2-LLM-012
Abgeleitet von: REQ-L2-LLM-012

### REQ-L3-LA001-U007: Auto-derived from REQ-L2-LLM-014
Abgeleitet von: REQ-L2-LLM-014

### REQ-L3-LA001-U008: Auto-derived from REQ-L2-LLM-010
Abgeleitet von: REQ-L2-LLM-010

### REQ-L3-LA001-U009: Auto-derived from REQ-L2-LLM-007
Abgeleitet von: REQ-L2-LLM-007

### REQ-L3-LA001-U010: Auto-derived from REQ-L2-LLM-011
Abgeleitet von: REQ-L2-LLM-011

### REQ-L3-LA001-U011: Auto-derived from REQ-L2-LLM-009
Abgeleitet von: REQ-L2-LLM-009

### REQ-L3-LA001-U012: Auto-derived from REQ-L2-LLM-005
Abgeleitet von: REQ-L2-LLM-005

### REQ-L3-LA001-U013: Auto-derived from REQ-L2-LLM-002
Abgeleitet von: REQ-L2-LLM-002
