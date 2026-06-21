# L2 ResilienceOrchestrator Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** ResilienceOrchestratorSystem (ARCH-L1-016)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-032 (primär)
- Ziel: terminal (keine L3-Zerlegung)

---

## Systemzweck

Das ResilienceOrchestratorSystem ist der zentrale Resilienz-Manager für alle externen Aufrufe (LLM-Adapter, Webhook-Dispatcher, GitHub-Integration). Es entkoppelt das System asynchron und implementiert Timeouts, Retry-Logik (Exponential Backoff) sowie Circuit-Breaker-Mechanismen, um zu garantieren, dass Ausfälle bei optionalen Subsystemen die Kernverfügbarkeit des ReqFlow-Systems (CRUD, Traceability, Baselines) nicht beeinträchtigen (Graceful Degradation).

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-049 | input | control | `execute_optional(operation, target, payload, policy)` vom ApplicationService (ARCH-L1-004) |
| IF-L1-050 | input | control | Wrapping aller HTTPS-Outbound-Calls vom LlmAdapter (ARCH-L1-009) |
| IF-L1-051 | output | control | Delegierter Aufruf nach Policy-Anwendung an LlmAdapter / Webhook / GitHub |
| IF-L1-052 | output | data | Degradation-Events, Retry-Logs, Circuit-State-Changes an AuditLog (ARCH-L1-012) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-RO-001: Asynchrone Entkopplung

Das ResilienceOrchestratorSystem SHALL externe Aufrufe asynchron über eine Queue (z.B. Celery) ausführen, sodass synchrone Request-Threads im ApplicationService nicht blockiert werden.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Optionaler Subsystem-Call wird in eine Queue eingereiht.
- [ ] Aufrufer erhält sofortige Rückmeldung über Entgegennahme.

**Interfaces:**
- Incoming: IF-L1-049
- Outgoing: IF-L1-051

**Traceability:** REQ-L1-032
**Rationale:** Verhindert Thread-Erschöpfung bei hängenden externen Services.

---

### REQ-L2-RO-002: Konfigurierbare Timeouts

Das ResilienceOrchestratorSystem SHALL für jeden externen Aufruf eine konfigurierbare Timeout-Policy anwenden. Wird der Timeout überschritten, MUSS der Aufruf abgebrochen werden.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Timeout-Schwelle kann pro Service konfiguriert werden.
- [ ] Aufruf wird bei Überschreitung abgebrochen.

**Interfaces:**
- Outgoing: IF-L1-051

**Traceability:** REQ-L1-032
**Rationale:** Schützt das System vor unendlich hängenden Requests.

---

### REQ-L2-RO-003: Retry-Logik mit Exponential Backoff

Das ResilienceOrchestratorSystem SHALL bei transienten Fehlern mindestens einen Retry ausführen. Die Retry-Strategie MUSS ein Exponential Backoff verwenden.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Fehlgeschlagene Requests werden automatisch wiederholt (außer bei expliziten Non-Retryable Errors wie 400).
- [ ] Wartezeit vergrößert sich exponentiell zwischen Retries.

**Interfaces:**
- Outgoing: IF-L1-051

**Traceability:** REQ-L1-032
**Rationale:** Erhöht die Erfolgsquote bei temporären Netzwerkproblemen.

---

### REQ-L2-RO-004: Circuit-Breaker-Logik

Das ResilienceOrchestratorSystem SHALL einen Circuit-Breaker implementieren, der bei einer definierbaren Fehlerquote in den Zustand "Open" wechselt und nachfolgende Aufrufe direkt blockiert, bis eine "Half-Open" Recovery erfolgreich ist.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nach N konsekutiven Fehlern wird Circuit-Breaker "Open".
- [ ] Aufrufe schlagen bei "Open" direkt fehl, ohne externes Subsystem zu belasten.

**Interfaces:**
- Outgoing: IF-L1-051

**Traceability:** REQ-L1-032
**Rationale:** Verhindert Kaskadeneffekte und gibt externen Systemen Zeit zur Erholung.

---

### REQ-L2-RO-005: Graceful Degradation und Kernverfügbarkeit

Das ResilienceOrchestratorSystem SHALL sicherstellen, dass Fehler in externen Subsystemen isoliert bleiben. Die Kernverfügbarkeit des restlichen Systems (CRUD, Baselines) MUSS bei Ausfall > 99,5 % bleiben.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Kompletter Ausfall von GitHub/LLM beeinträchtigt nicht das ReqFlow-Backend für Anforderungs-CRUD.
- [ ] Graceful Degradation Responses geben dem Frontend an, dass ein optionales Subsystem temporär inaktiv ist.

**Interfaces:**
- Incoming: IF-L1-049, IF-L1-050

**Traceability:** REQ-L1-032
**Rationale:** Produktionsstabilität darf nicht von optionalen Drittsystemen abhängen.

---

### REQ-L2-RO-006: Audit-Logging für Resilienz-Events

Das ResilienceOrchestratorSystem SHALL Degradation-Events, Retry-Logs und Statuswechsel des Circuit-Breakers im AuditLog protokollieren.

**Domain:** system
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Circuit-Breaker-Öffnung wird im AuditLog protokolliert.
- [ ] Degradation-Vorfälle sind nachvollziehbar.

**Interfaces:**
- Outgoing: IF-L1-052

**Traceability:** REQ-L1-032
**Rationale:** Sichtbarkeit für Administratoren zur Fehlerdiagnose bei externen Systemen.

---

## Traceability-Matrix: REQ-L2-RO → REQ-L1

| REQ-L2-RO | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-RO-001 | REQ-L1-032 | — |
| REQ-L2-RO-002 | REQ-L1-032 | — |
| REQ-L2-RO-003 | REQ-L1-032 | — |
| REQ-L2-RO-004 | REQ-L1-032 | — |
| REQ-L2-RO-005 | REQ-L1-032 | — |
| REQ-L2-RO-006 | REQ-L1-032 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-RO | 6 |
| Mandatory | 6 |
| Desired | 0 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 1 (REQ-L1-032) |
| Abgedeckte REQ-L1 (mitwirkend) | 0 |
| Referenzierte Interfaces | IF-L1-049..IF-L1-052 (alle 4) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Handoff: HOFF-20260621-002 | Parent: REQ-L1-032 | Architektur-Referenz: ARCH-L1-016*
*Designation: component (terminal) — decomposition_status: terminal*
