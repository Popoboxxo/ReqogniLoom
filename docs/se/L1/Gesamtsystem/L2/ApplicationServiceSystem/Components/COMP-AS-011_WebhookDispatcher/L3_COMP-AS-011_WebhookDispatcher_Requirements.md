---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 WebhookDispatcher Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-011_WebhookDispatcher
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-017 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der WebhookDispatcher sendet asynchrone Webhooks an konfigurierte externe URLs bei Eintritt vordefinierter Events (Requirement created/modified, status transition, baseline created). Er funktioniert als Subscriber des DomainEventBus und implementiert Retry-Logik mit exponentiellem Backoff sowie sichere Secret-Validierung für Webhook-Authentifizierung.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-INT-013 | input | event | Domain-Event Subscription vom DomainEventBus (async worker call) |
| IF-AS-EXT-OUT-007 | output | data | Webhook-Konfigurationen abrufen vom PersistenceLayer |
| (external) | output | data | HTTP POST an konfigurierte Webhook-URLs |

---

## L3 Component-Anforderungen

### REQ-L3-WHOOK-001: Event-Subscription und Filterung

Der WebhookDispatcher SHALL als Subscriber des DomainEventBus registriert sein und Events nach konfigurierten Event-Typen filtern:
- Unterstützte Event-Typen: RequirementCreated, RequirementUpdated, RequirementDeleted, WorkflowTransitioned, BaselineCreated

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] WebhookDispatcher abonniert IF-AS-INT-013 vom DomainEventBus
- [ ] Event-Filterung nach workspace_id und event_type
- [ ] Nicht abonnierte Events werden ignoriert (keine Fehler)
- [ ] Subscriber kann dynamisch an-/abgemeldet werden

**Interfaces:** IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Asynchrone Event-Verarbeitung ohne Blockierung des Domain-Services.

---

### REQ-L3-WHOOK-002: Webhook-Konfiguration abrufen

Der WebhookDispatcher SHALL bei Eintritt eines relevanten Events die konfigurierten Webhook-URLs aus dem PersistenceLayer abrufen (gefiltert nach Workspace und Event-Typ).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Webhook-Config wird aus DB gelesen (nicht hard-coded)
- [ ] Filterung nach workspace_id und event_type
- [ ] Webhook mit `enabled: false` werden übersprungen
- [ ] Keine Webhooks für Workspace → keine Dispatch-Versuche

**Interfaces:** IF-AS-EXT-OUT-007, IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Konfigurierbare Webhook-Verwaltung.

---

### REQ-L3-WHOOK-003: HTTP-POST-Payload-Konstruktion

Der WebhookDispatcher SHALL für jeden konfigurierten Webhook einen JSON-Payload konstruieren:
```json
{
  "event_type": "RequirementCreated",
  "entity_id": "uuid-xxx",
  "workspace_id": "uuid-yyy",
  "timestamp": "2026-06-22T14:30:00Z",
  "entity_snapshot": {...}
}
```

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Payload ist gültiges JSON
- [ ] event_type, entity_id, timestamp sind vorhanden
- [ ] entity_snapshot enthält relevante Felder (title, description, state)
- [ ] Keine sensiblen Felder (Passwords, API-Keys) in Payload

**Interfaces:** IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Standardisierte Webhook-Payload für externe Systeme.

---

### REQ-L3-WHOOK-004: Secret-basierte HMAC-Authentifizierung

Der WebhookDispatcher SHALL für Webhooks mit konfiguriertem Secret einen HMAC-SHA256-Header generieren:
- Header: `X-Webhook-Signature: sha256=<hmac>`
- HMAC wird über Raw-Payload-Body berechnet
- Externe Systeme können Authentizität verifizieren

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Secret wird aus Webhook-Config gelesen
- [ ] HMAC-SHA256 über Payload-Body berechnet
- [ ] Header wird als `X-Webhook-Signature` gesendet
- [ ] Webhooks ohne Secret haben keinen Signature-Header

**Interfaces:** IF-AS-INT-013, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Sicherheit durch Webhook-Authentifizierung.

---

### REQ-L3-WHOOK-005: HTTP-Request mit Timeout und Retry-Logik

Der WebhookDispatcher SHALL für jeden Webhook-Dispatch:
1. HTTP-POST mit Timeout von 10s senden
2. Bei Fehler oder Timeout: Exponentieller Backoff mit Retry (max 5 Versuche)
3. Retry-Schedule: 1s, 2s, 4s, 8s, 16s (exponentiell)
4. Nach 5 fehlgeschlagenen Versuchen: Webhook als "failed" markieren (nicht erneut versuchen)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] HTTP-POST mit 10s Timeout
- [ ] Retry bei 5xx, Connection-Error, Timeout
- [ ] Exponentieller Backoff implementiert (1s, 2s, 4s, 8s, 16s)
- [ ] Max 5 Retries, dann Webhook-Status "failed"
- [ ] Alarmierung bei wiederholten Fehlern (Log oder Metrics)

**Interfaces:** IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Zuverlässige Delivery mit Retry bei transienten Fehlern.

---

### REQ-L3-WHOOK-006: HTTP-Status-Code-Semantik

Der WebhookDispatcher SHALL folgende HTTP-Status-Codes interpretieren:
- 2xx (Success): Dispatch erfolgreich, nicht erneut versuchen
- 3xx (Redirect): Nicht folgen, als Fehler behandeln
- 4xx (Client Error): Nicht wiederholen (permanent failure)
- 5xx (Server Error): Wiederholen mit Exponentieller Backoff

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 2xx wird als Success interpretiert
- [ ] 4xx wird nicht wiederholt (permanent failure)
- [ ] 5xx triggert Retry-Logik
- [ ] Timeout wird wie 5xx behandelt

**Interfaces:** IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Intelligent Retry basierend auf HTTP-Semantik.

---

### REQ-L3-WHOOK-007: Asynchrone Worker-Verarbeitung

Der WebhookDispatcher SHALL als asynchroner Worker laufen (z.B. Django-Q, Celery):
- Event vom DomainEventBus wird an Worker-Queue gestellt
- Webhooks werden nicht im HTTP-Request-Thread gesendet
- HTTP-Request kehrt sofort zurück (nach Domain-Event-Enqueuing)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Webhook-Dispatch ist nicht-blockierend
- [ ] Worker-Queue ist persistent (z.B. DB, Redis)
- [ ] Keine Webhook-Fehler beeinflussen Client-Response
- [ ] Worker-Timeout ist konfigurierbar (default 30s pro Webhook)

**Interfaces:** IF-AS-INT-013
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Schnelle API-Antworten trotz langsamer webhooks.

---

### REQ-L3-WHOOK-008: Monitoring und Dead-Letter-Queue

Der WebhookDispatcher SHALL gescheiterte Webhooks in einer Dead-Letter-Queue (DLQ) sammeln und Fehler-Metriken exponieren:
- DLQ enthält Webhook-ID, Event-ID, Status, Error-Nachricht
- Metriken: Dispatch-Erfolgsquote, Retry-Count pro Webhook
- Optional: AlertinG bei >5% Fehlerquote

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Gescheiterte Webhooks werden in DLQ persistent gespeichert
- [ ] Metriken sind abrufbar (via Endpoint oder Logging)
- [ ] Operatoren können DLQ inspizieren und manuell erneut versuchen
- [ ] Alert bei hoher Fehlerquote (konfigurierbar)

**Interfaces:** IF-AS-EXT-OUT-007, (metrics/monitoring)
**Traceability:** REQ-L2-AppSvc-017
**Rationale:** Operationale Überwachung und Debugging.

---

### REQ-L3-WHOOK-009: Tenant-Isolation bei Event-Dispatch

Der WebhookDispatcher SHALL garantieren, dass Webhooks nur innerhalb der gleichen Workspace/Tenant gesendet werden. Keine Cross-Tenant-Webhook-Dispatch möglich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Webhook-URL wird aus Konfiguration des gleichen Tenants gelesen
- [ ] Keine Webhook-URLs aus anderen Tenants werden verwendet
- [ ] Event workspace_id wird mit Webhook workspace_id abgeglichen

**Interfaces:** IF-AS-INT-013, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

## Traceability-Matrix: REQ-L3-WHOOK → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-WHOOK-001 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-002 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-003 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-004 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-005 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-006 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-007 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-008 | REQ-L2-AppSvc-017 |
| REQ-L3-WHOOK-009 | REQ-L2-AppSvc-022 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
