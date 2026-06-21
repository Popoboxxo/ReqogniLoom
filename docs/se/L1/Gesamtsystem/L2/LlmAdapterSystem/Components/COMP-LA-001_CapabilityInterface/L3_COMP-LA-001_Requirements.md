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

Die CapabilityInterface-Komponente SHALL eine abstrakte Basisklasse `LlmCapabilityInterface` bereitstellen mit den drei Operationen `validate_artifact(artifact_id: str) -> LlmResult`, `decompose_requirement(requirement_id: str) -> LlmDecompositionResult` und `check_consistency(workspace_id: str) -> LlmConsistencyResult`. Konkrete Provider-Klassen MÜSSEN alle drei Operationen implementieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Abstract base class `LlmCapabilityInterface` exists with all three abstract methods
- [ ] Instantiating `LlmCapabilityInterface` directly raises `TypeError`
- [ ] A concrete provider subclass that omits one method raises `TypeError` on instantiation
- [ ] Method signatures match defined contracts (parameter names, return type annotations)

---

### REQ-L3-LA001-002: Standardisierte Ergebnisdatenklassen

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

Die CapabilityInterface-Komponente SHALL ausschliesslich abstrakte Typen und Datenklassen enthalten. Kein Import von Provider-Bibliotheken (anthropic, openai, ollama, azure) DARF direkt oder transitiv in diesem Modul vorkommen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Module dependency tree of `capability_interface` contains no provider SDK imports
- [ ] `import capability_interface` succeeds in an environment without any provider SDK installed
- [ ] Static analysis (e.g., `import-linter`) passes without provider-library violations

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
