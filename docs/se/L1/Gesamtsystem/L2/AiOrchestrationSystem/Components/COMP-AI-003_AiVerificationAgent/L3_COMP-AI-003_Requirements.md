# L3 AiVerificationAgent Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AI-003 — AiVerificationAgent
> **Parent-System:** AiOrchestrationSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Ein ereignisgesteuerter KI-Agent, der basierend auf freigegebenen System Requirements (`Approved`) vollautomatisch erste Entwürfe für zugehörige Testfälle (Test Cases) generiert.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AI-005 | AI Decomposition & AI Test-Generation (Teil 2) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AI-INT-005 | eingehend | Message Broker | `Event: ArtifactStateTransitioned(To: Approved)` |
| IF-AI-INT-006 | ausgehend | RestApiAdapterSystem | POST `/api/v1/test-cases` (TC creation) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AI003-001: Event-Abonnement (Approved SyReqs)

Der Agent MUSS den Message Broker abonnieren und auf `ArtifactStateTransitioned` lauschen. Der Trigger löst nur aus, wenn der Typ `SystemRequirement` ist und der neue Status `Approved` lautet.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Agent ignoriert `StReq`, `ArchE`.
- [ ] Agent ignoriert Übergänge zu `In Review` oder `Draft`.

---

### REQ-L3-AI003-002: Testfall-Generierung

Der Agent analysiert die Requirement-`description` und das Feld `verification_method`. Das LLM MUSS angewiesen werden, einen Test Case im Status `Draft` zu entwerfen.
Dabei MÜSSEN folgende Felder befüllt werden:
- `test_type` (abgeleitet aus der Verification Method).
- `pre_conditions` (Was muss im Systemzustand gegeben sein?).
- `test_steps` (Schritt-für-Schritt).
- `expected_result` (Genaues Akzeptanzkriterium).

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Structured Output (JSON) für ein TestCase-DTO.

---

### REQ-L3-AI003-003: Persistenz und Verlinkung

Der Agent MUSS den generierten Test Case über die REST-API anlegen (`POST`) und einen TraceLink (Typ: `verifies`) vom Test Case zum auslösenden SyReq erstellen.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Test Case wird als `Draft` angelegt.
- [ ] Verknüpfung `verifies` wird etabliert.
