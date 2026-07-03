# L3 AiQualityGateAgent Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AI-001 — AiQualityGateAgent
> **Parent-System:** AiOrchestrationSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Ein ereignisgesteuerter KI-Agent, der als Qualitäts-Gatekeeper fungiert. Er lauscht auf Statusübergänge (`Draft -> In Review`) und validiert die fachliche Qualität von Anforderungen (SyReq, StReq) gegen INCOSE-Regeln, bevor der Statuswechsel im System propagiert wird.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AI-004 | AI Quality Gate bei Status-Übergang |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AI-INT-001 | eingehend | Message Broker | `Event: ArtifactStateTransitionRequested` |
| IF-AI-INT-002 | ausgehend | RestApiAdapterSystem | `PATCH /api/v1/artifacts/{id} (State Update / Comments)` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AI001-001: Event-Subscription und Trigger

Der Agent MUSS den Message Broker abonnieren und ausschließlich auf das Event `ArtifactStateTransitionRequested` für die Artefakttypen `StakeholderRequirement` und `SystemRequirement` reagieren, wenn das Zielfeld `workflow_state` den Wert `In Review` annimmt.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Listener ignoriert Events für Architektur-Elemente und Testfälle.
- [ ] Listener triggert den LLM-Job asynchron.

---

### REQ-L3-AI001-002: INCOSE-Validierung via LLM-Prompt

Der Agent MUSS das Feld `description` an das konfigurierte LLM übergeben. Der System-Prompt MUSS die Validierung auf Basis von INCOSE-Kriterien erzwingen:
- Messbarkeit (Metriken statt Füllwörter wie "schnell", "gut").
- Eindeutigkeit (Keine Konjunktionen wie "und/oder", die die Anforderung aufweichen).
- Vorhandensein eines starken Modalverbs ("MUSS", "SOLL").

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Structured Output (JSON) vom LLM mit den Feldern `passed: boolean`, `reason: string`, `suggestions: string[]`.

---

### REQ-L3-AI001-003: Freigabe oder Ablehnung (API-Callback)

Abhängig vom LLM-Ergebnis MUSS der Agent den Statuswechsel finalisieren oder blockieren.
- Bei `passed == true`: Führt einen `PATCH` Request aus, der den `workflow_state` auf `In Review` setzt.
- Bei `passed == false`: Belässt den Status auf `Draft` und legt via `POST /api/v1/comments` das Feedback (`reason` + `suggestions`) am Artefakt ab.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Akzeptierte Anforderungen springen auf `In Review`.
- [ ] Abgelehnte Anforderungen bekommen einen Kommentar vom User "System-AI".
