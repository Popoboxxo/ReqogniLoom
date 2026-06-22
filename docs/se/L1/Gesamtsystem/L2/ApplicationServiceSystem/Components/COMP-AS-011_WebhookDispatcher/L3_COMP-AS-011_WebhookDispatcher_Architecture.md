---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 WebhookDispatcher Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-011_WebhookDispatcher
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der WebhookDispatcher sendet asynchrone Webhooks an konfigurierte externe URLs bei Eintritt vordefinierter Domain-Events (RequirementCreated/Updated, WorkflowTransitioned, BaselineCreated, etc.). Er funktioniert als asynchroner Worker-Subscriber des DomainEventBus und implementiert Retry-Logik mit exponentiellem Backoff sowie sichere Secret-Validierung (HMAC-SHA256). Der WebhookDispatcher verwaltet eine Dead-Letter-Queue für gescheiterte Webhooks und exponiert Metrics für operative Überwachung.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`WebhookDispatcher` (Worker/Task):** Asynchroner Worker, registriert als DomainEventBus-Subscriber für Event-Typen (RequirementCreated, RequirementUpdated, RequirementDeleted, WorkflowTransitioned, BaselineCreated).
  - `process_event(domain_event)`: Lädt Webhook-Konfigurationen, konstruiert JSON-Payload, sendet HTTP-POST mit Retry-Logik

- **`WebhookPayloadBuilder` (Klasse):** Konstruiert JSON-Payload mit event_type, entity_id, workspace_id, timestamp, entity_snapshot, HMAC-Header.

- **`WebhookHTTPClient` (Klasse):** Sendet HTTP-POST mit Timeout (10s), interpretiert Status-Codes, implementiert Retry-Logik (exponentieller Backoff).

- **`RetryScheduler` (Klasse):** Exponentieller Backoff: 1s, 2s, 4s, 8s, 16s. Nach 5 Retries: Webhook als "failed" markieren, in Dead-Letter-Queue verschieben.

- **`WebhookDLQ` (Model/Table):** Dead-Letter-Queue für gescheiterte Webhooks: webhook_id, event_id, workspace_id, event_type, error_message, retry_count, moved_at.

### 2.2 Datenstrukturen

- **WebhookConfig-Entity:** id, workspace_id, url, event_types[], enabled, secret (optional).

- **WebhookPayload (DTO):** event_type, entity_id, workspace_id, timestamp, entity_snapshot (JSON).

- **RetryRecord (DTO):** webhook_id, event_id, retry_count, next_retry_at (timestamp), error_message.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WHOOK-001 (Event-Subscription und Filterung) | Methode `subscribe_to_events()`: Registriere WebhookDispatcher als DomainEventBus-Subscriber für RequirementCreated, RequirementUpdated, RequirementDeleted, WorkflowTransitioned, BaselineCreated. Event-Filterung nach workspace_id und event_type (nicht abonnierte Events ignoriert). Subscriber kann dynamisch an-/abgemeldet werden. |
| REQ-L3-WHOOK-002 (Webhook-Konfiguration abrufen) | Methode `_load_webhook_configs(workspace_id, event_type)`: Query PersistenceLayer WHERE workspace_id = param AND event_type IN [...] AND enabled = true. Keine Webhooks → keine Dispatch-Versuche. Webhook-Config mit `enabled: false` übersprungen. |
| REQ-L3-WHOOK-003 (HTTP-POST-Payload-Konstruktion) | WebhookPayloadBuilder.build(domain_event) → JSON mit event_type, entity_id, workspace_id, timestamp (ISO 8601), entity_snapshot (title, description, state, etc.). Keine sensitiven Felder (Passwords, API-Keys). JSON-serialisiert und UTF-8 encoded. |
| REQ-L3-WHOOK-004 (Secret-basierte HMAC-Authentifizierung) | Falls Webhook-Config enthält `secret`: Berechne HMAC-SHA256(payload_bytes, secret). Header setzen: `X-Webhook-Signature: sha256=<hex_hmac>`. Webhooks ohne Secret: kein Signature-Header. Externe Systeme können mit Secret verifizieren. |
| REQ-L3-WHOOK-005 (HTTP-Request mit Retry-Logik) | WebhookHTTPClient.post(url, payload, secret): HTTP-POST mit 10s Timeout. Bei Fehler oder Timeout: exponentieller Backoff (1s, 2s, 4s, 8s, 16s). Max 5 Retries. Nach 5 Fehlschlägen: Webhook-Status "failed", in DLQ verschieben. Alarmierung (Log) bei wiederholten Fehlern. |
| REQ-L3-WHOOK-006 (HTTP-Status-Code-Semantik) | Status 2xx → Success, nicht erneut versuchen. Status 3xx (Redirect) → als Fehler behandeln, nicht folgen. Status 4xx (Client Error) → permanent failure, nicht wiederholen. Status 5xx (Server Error) → Retry-Logik. Timeout → wie 5xx behandeln. |
| REQ-L3-WHOOK-007 (Asynchrone Worker-Verarbeitung) | WebhookDispatcher läuft als asynchroner Worker (Django-Q oder Celery). Event vom DomainEventBus wird an Worker-Queue gestellt. Webhooks werden nicht im HTTP-Request-Thread gesendet. HTTP-Request kehrt sofort zurück (nach Event-Enqueuing). Worker-Timeout: 30s (konfigurierbar). |
| REQ-L3-WHOOK-008 (Monitoring und DLQ) | DLQ-Tabelle speichert gescheiterte Webhooks: webhook_id, event_id, error_message, retry_count. Metriken: Dispatch-Erfolgsquote, Retry-Count pro Webhook. Optional: Alert bei >5% Fehlerquote. Operatoren können DLQ inspizieren und manuell erneut versuchen. |
| REQ-L3-WHOOK-009 (Tenant-Isolation) | Webhook-URLs werden aus Konfiguration des gleichen Tenants/Workspace gelesen. Event workspace_id wird mit Webhook workspace_id abgeglichen. Keine Cross-Tenant-Webhook-Dispatch möglich. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-INT-013:** Domain-Event-Subscription vom DomainEventBus (async worker call für Events: RequirementCreated, RequirementUpdated, RequirementDeleted, WorkflowTransitioned, BaselineCreated).

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-007:** SELECT Queries an PersistenceLayer zur Webhook-Config-Abfrage (WHERE workspace_id, enabled=true, event_type).
  - **(external):** HTTP POST an konfigurierte Webhook-URLs (externe Systeme).

---

## 5. Architectural Rationale

**ADR-L3-WHOOK-01 — Asynchroner Worker statt Synchrone HTTP-Posts**

*Entscheidung:* WebhookDispatcher läuft als asynchroner Worker (nicht im HTTP-Request-Thread). Events werden in eine Worker-Queue gestellt, HTTP-Posts erfolgen asynchron.

*Rationale:* Webhooks können langsam sein oder Timeouts erzeugen. Synchrones Senden im Request-Thread würde API-Latenz erhöhen (10s+ für Webhook-Timeouts). Asynchron garantiert schnelle API-Responses (<100ms) und entkoppelt Webhook-Zuverlässigkeit von API-Verfügbarkeit. Alternative: Synchrone HTTP-Posts → API-Response verzögert, Fehlerbehandlung kompliziert. **Abgelehnt**: User Experience ist schlecht.

*Erfüllt Trigger:* REQ-L3-WHOOK-007 (asynchrone Worker-Verarbeitung).

---

**ADR-L3-WHOOK-02 — Exponentieller Backoff mit Hard-Limit (5 Retries)**

*Entscheidung:* Webhook-Fehler werden mit exponentiellem Backoff wiederholt (1s, 2s, 4s, 8s, 16s), max 5 Retries. Nach 5 Fehlschlägen: Webhook-Status "failed", in DLQ verschoben.

*Rationale:* Transiente Fehler (Netzwerk, kurzzeitiger Service-Ausfall) können sich selbst heilen. Exponentieller Backoff gibt externe Systeme Zeit zu recovery. Hard-Limit verhindert infinite Retries. Alternative: Unbegrenzte Retries → Ressourcen-Verschwendung, DLQ wächst unbegrenzt. **Abgelehnt**: Hard-Limit ist notwendig für operative Effizienz.

*Erfüllt Trigger:* REQ-L3-WHOOK-005 (Retry-Logik).

---

**ADR-L3-WHOOK-03 — HMAC-SHA256 für Secret-basierte Authentifizierung**

*Entscheidung:* Falls Webhook-Config ein Secret enthält, wird HMAC-SHA256(payload, secret) berechnet und als `X-Webhook-Signature`-Header gesendet.

*Rationale:* Externe Systeme können Webhook-Authentizität verifizieren, ohne API-Keys auszutauschen. HMAC-SHA256 ist Branchenstandardard (GitHub, Stripe). Alternative: Basic Auth oder API-Key im URL → sichtbar in Logs, unsicher bei HTTP (nur HTTPS hilft teilweise). **Abgelehnt**: HMAC ist sicherer und einfacher.

*Erfüllt Trigger:* REQ-L3-WHOOK-004 (Secret-Authentifizierung).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
