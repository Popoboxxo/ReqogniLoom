# L3 AiDecompositionAgent Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AI-002 — AiDecompositionAgent
> **Parent-System:** AiOrchestrationSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Ein KI-Agent, der komplexe Anforderungen (Stakeholder Requirements) vertikal in technische Systemanforderungen (System Requirements) herunterbricht.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AI-005 | AI Decomposition & AI Test-Generation (Teil 1) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AI-INT-003 | eingehend | RestApiAdapterSystem | API Endpoint Trigger `/api/v1/agent/decompose` |
| IF-AI-INT-004 | ausgehend | RestApiAdapterSystem | POST `/api/v1/requirements` (SyReq creation) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AI002-001: Trigger und Kontext-Aufbau

Der Agent wird manuell über die API angestoßen. Er MUSS das als Ziel definierte `StakeholderRequirement` laden und den Business Context verstehen.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Agent liest Title, Description und Business Value des Parent-Requirements.

---

### REQ-L3-AI002-002: SyReq-Generierung und Schätzung

Das LLM MUSS angewiesen werden, die fachliche Anforderung in 1 bis N technische `SystemRequirements` zu zerlegen. Für jedes generierte SyReq MUSS das LLM:
- Einen `title` und `description` verfassen.
- Den passenden `req_type` (Functional, Non-Functional, Interface, Constraint) bestimmen.
- Die `complexity` (Fibonacci-Skala 1, 2, 3, 5, 8...) schätzen.
- Die `verification_method` vorschlagen.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Structured Output in Form einer Liste von SyReq-Objekten.
- [ ] Complexity ist zwingend eine Fibonacci-Zahl.

---

### REQ-L3-AI002-003: Artefakt-Anlage und Trace-Verknüpfung

Der Agent MUSS die generierten SyReqs über die REST-API im Status `Draft` anlegen und sofort einen Upstream-Trace (Typ: `derives to`) zum initialen StReq erstellen.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Neue Artefakte erscheinen im System als Drafts.
- [ ] Trace-Links zum Parent sind etabliert (Erfüllung der No-Orphan-Rule).
