# L2 AiOrchestration Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** AiOrchestrationSystem
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-07-03
> **Status:** formalisiert
> **Designation:** subsystem (Leaf-AE — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-069, REQ-L1-074
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AI-EXT-IN-001 | input | data | Interne Events (z.B. ArtifactUpdated) via Event Bus |
| IF-AI-EXT-IN-002 | input | data | LLM-Inferenz-Antworten (Cloud / Local) |
| IF-AI-EXT-OUT-001 | output | data | API-Aufrufe an Cloud-LLMs (OpenAI, Anthropic) |
| IF-AI-EXT-OUT-002 | output | data | API-Aufrufe an lokale LLMs (Ollama) |
| IF-AI-EXT-OUT-003 | output | data | REST/GraphQL-Aufrufe an das eigene Backend |

---

## L2 Subsystem-Anforderungen

### REQ-L2-AI-001: Semantic Router (Hybrid AI)
Das AiOrchestrationSystem MUSS einen Semantic Router bereitstellen, der eingehende KI-Tasks anhand von konfigurierbaren Regeln (Datenschutz-Level des Workspaces, Token-Größe, Task-Komplexität) dynamisch an den passenden Provider (Cloud LLM vs. Local LLM) weiterleitet.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-069

---

### REQ-L2-AI-002: Semantic Trace Healing Agent
Das System MUSS einen Hintergrund-Agenten bereitstellen, der auf Status-Änderungen an TraceLinks (insbesondere "Suspect"-Markierungen) lauscht. Der Agent MUSS das semantische Delta des Upstream-Artefakts analysieren und einen konkreten Patch-Vorschlag (Text/Code) für das Downstream-Artefakt generieren, den der Nutzer mit einem Klick übernehmen kann.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-074

---

### REQ-L2-AI-003: Interface Consistency Agent
Das System MUSS einen Agenten betreiben, der bei Änderungen an `Interface`-Definitionen oder assoziierten Architektur-Komponenten proaktiv den Graphen traversiert, um Inkonsistenzen bei allen verbundenen Knoten zu identifizieren und entsprechende Issues/Tasks zu generieren.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** desired
**Abgeleitet von:** REQ-L1-074

---

## Erweiterung v2 — REQ-L2-AI-004..005 (Event-Driven AI Automation)

> **Datum:** 2026-07-03 | **Quelle:** User-Request "Deep Dive"

---

### REQ-L2-AI-004: AI Quality Gate bei Status-Übergang

Das AiOrchestrationSystem MUSS auf das Event `ArtifactStateTransitionRequested` reagieren, speziell beim Übergang `Draft ➔ In Review`.
Der Agent lädt die Beschreibung (`description`) des Artefakts und validiert diese gegen INCOSE-Regeln (Messbarkeit, Eindeutigkeit).
- Fällt die Prüfung positiv aus, gibt der Agent den Statuswechsel per API (Callback) frei.
- Fällt die Prüfung negativ aus, lehnt der Agent den Wechsel ab und hinterlegt einen Kommentar mit konkreten Verbesserungsvorschlägen am Artefakt.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-080
**Übergeordnete REQ-L0:** REQ-L0-049

---

### REQ-L2-AI-005: AI Decomposition & AI Test-Generation

Das System MUSS zwei spezialisierte Agenten-Rollen für den Hardcore-SE-Modus bereitstellen:
1. **Decomposition Agent:** Reagiert auf einen manuellen Nutzer-Trigger an einem StReq (im Status `Draft`). Der Agent erzeugt Entwürfe (Drafts) für abgeleitete SyReqs, berechnet Fibonacci-Complexity-Schätzungen und befüllt das `Req. Type` Feld.
2. **Verification Agent:** Reagiert auf das Event `ArtifactStateTransitioned(SyReq, Approved)`. Der Agent analysiert die Requirement-Description und die `Verification Method`. Er generiert vollautomatisch einen Test Case (TC) im Status `Draft`, verknüpft ihn mit dem SyReq (`verifies`) und füllt `Pre-Conditions` sowie `Expected Result`.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** desired
**Abgeleitet von:** REQ-L1-080
**Übergeordnete REQ-L0:** REQ-L0-046
