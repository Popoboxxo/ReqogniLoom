# L3 AiDerivationService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AI-004 — AiDerivationService
> **Parent-System:** AiOrchestrationSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Der AiDerivationService implementiert die Draft/Accept-Infrastruktur für KI-Flows (z.B. StakeholderNeed → SysReq, SysReq → Architecture). Ergebnisse werden als Entwürfe (Drafts) markiert und nicht automatisch vom System übernommen, bevor sie nicht vom Benutzer geprüft und explizit akzeptiert wurden.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AI-007 | AI Derivation Service — Draft/Accept-Infrastruktur |
| REQ-L2-AI-008 | AI Derivation Flows — Konkrete Ableitungsschritte |

## Interne Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-AI-INT-001 | ausgehend | COMP-AI-002 AiDecompositionAgent | `trigger_decomposition(flow_type, item_id)` |

## Externe Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-AI-EXT-IN-003 | eingehend | ApplicationService | REST und MCP Endpunkte zur Triggerung |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AI004-001: Draft/Accept-Infrastruktur

Der AiDerivationService MUSS alle von KI-Modellen generierten Artefakte oder Relationen zunächst in einen dedizierten `Draft`-Status versetzen. Eine automatische Übernahme (Auto-Accept) in den aktiven Datenbestand ist untersagt. Der Service MUSS Endpunkte bereitstellen, um diese Drafts abzurufen, zu akzeptieren oder zu verwerfen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Generierte Requirements haben initiale `status=Draft`.
- [ ] UI/MCP können Entwürfe abfragen, verwerfen oder in aktive Artefakte umwandeln.

---

### REQ-L3-AI004-002: Implementierung der 3 Derivation-Flows

Der AiDerivationService MUSS drei spezifische Flows bereitstellen:
1. StakeholderNeed → SysReq
2. SysReq → ArchitectureElement (Zuordnungs-Vorschlag)
3. SysReq (+ Architecture) → SysReq (Level n+1)

Diese Flows MÜSSEN über den ApplicationService (REST/MCP) auslösbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] API Endpunkt `/api/ai/derive/need-to-sysreq/` existiert.
- [ ] API Endpunkt `/api/ai/derive/sysreq-to-arch/` existiert.
- [ ] API Endpunkt `/api/ai/derive/sysreq-to-sysreq-next-level/` existiert.
- [ ] Jeder Flow resultiert in Draft-Entitäten, die via REQ-L3-AI004-001 validiert werden.

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-07-12*
