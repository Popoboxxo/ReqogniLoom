---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 AsyncTaskDispatcher Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-LA-005_AsyncTaskDispatcher
> **Parent:** L2_LlmAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der AsyncTaskDispatcher dispatcht langläufige LLM-Tasks (decompose_requirement, check_consistency) als Celery-Tasks in die Message-Queue (Redis/RabbitMQ). Er gibt sofort eine UUID-basierte task_id zurück (< 500ms), blockiert den aufrufenden WSGI/ASGI-Worker nicht und stellt `get_task_status(task_id)` für Statusabfragen bereit. Er verwaltet Celery-Broker-Konfiguration, Task-Timeouts und Fehlerbehandlung im Worker.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AsyncTaskDispatcher` (Klasse):** Zentrale Dispatch-API, Celery-Client-Wrapper.
- **`CeleryTaskResult` (Dataclass):** Repräsentiert Task-Status (pending, running, done, failed, not_found).
- **`TaskStatusResult` (Dataclass):** Strukturiertes Rückgabeformat für get_task_status.
- **`CeleryBrokerConfig` (Dataclass):** Kapselt Broker-URL, Auth-Parameter, Connection-Pool.
- **`CapabilityWorkerTask` (Celery-Task):** Konkrete Celery-Task-Definitionen für decompose_requirement, check_consistency.

### 2.2 Datenstrukturen

- **TaskStatusResult:**
  - `task_id`: str (UUID)
  - `status`: str (enum: "pending", "running", "done", "failed", "not_found")
  - `result`: dict | None (bei status="done", enthält LlmDecompositionResult/LlmConsistencyResult)
  - `error`: str | None (bei status="failed")

- **CeleryBrokerConfig:**
  - `broker_url`: str (env var `CELERY_BROKER_URL`)
  - `result_backend`: str (optional, default: broker_url)
  - `task_soft_time_limit`: int (seconds, env var `CELERY_TASK_SOFT_TIME_LIMIT`)
  - `task_time_limit`: int (seconds, env var `CELERY_TASK_TIME_LIMIT`)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-LA005-001 (Sofortiger Dispatch) | Methode `dispatch_async(capability, kwargs)`: Erstellt Celery-Task via celery.send_task() oder Decorator. Gibt sofort task_id (UUID) zurück (< 500ms). Thread wird nicht blockiert. |
| REQ-L3-LA005-002 (Task-Status-Abfrage) | Methode `get_task_status(task_id) -> TaskStatusResult`: Abfrage von Celery Result-Backend. Mögliche Status: pending, running, done, failed, not_found. Result/error gekapselt in TaskStatusResult. |
| REQ-L3-LA005-003 (Broker-Konfiguration) | Umgebungsvariablen: `CELERY_BROKER_URL` (Redis/RabbitMQ), `CELERY_TASK_SOFT_TIME_LIMIT` (Warning), `CELERY_TASK_TIME_LIMIT` (Hard-Kill). Bei fehlender Broker-URL: strukturierter Fehler `{"error": {"code": "BROKER_NOT_CONFIGURED"}}`. |
| REQ-L3-LA005-004 (Worker-Fehlerbehandlung) | CapabilityWorkerTask im Celery-Worker: Bei Fehler wird status=failed, error=<detail> gespeichert. SoftTimeLimitExceeded → status=failed, error="Task timed out". Keine Deadlock-States. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-LA-INT-005:** Aufruf vom CapabilityRouter: `dispatch_async(capability, kwargs) -> task_id` | `{"error": {...}}`.

- **Ausgänge (Outbound):**
  - **IF-LA-EXT-OUT-003:** Celery-Broker (Redis oder RabbitMQ) — Task-Dispatch via `celery.send_task()`.
  - **IF-LA-EXT-OUT-003 (Result Backend):** Celery Result-Backend (Redis/RabbitMQ/Dedicated Backend) — Task-Status-Abfrage.

---

## 5. Architectural Rationale

**ADR-L3-LA005-01 — Sofortige Task-ID-Rückgabe ohne Bestätigung**
*Entscheidung:* dispatch_async() gibt task_id sofort zurück, ohne auf Task-Broker-Bestätigung zu warten.
*Rationale:* Erfüllt REQ-L3-LA005-001 (< 500ms). Broker ist üblicherweise zuverlässig genug, dass eine Bestätigung unnötig ist. Fallback-Fehler würde nur auftreten, wenn Broker vollständig ausfällt.
*Alternative abgelehnt:* Auf Broker-Bestätigung warten — würde Latenz auf 1-2s erhöhen.

**ADR-L3-LA005-02 — Drei-Status-Modell (pending, running, done/failed)**
*Entscheidung:* Task-Status: pending (in Queue) → running (Worker aktiv) → done/failed (abgeschlossen).
*Rationale:* Klare Fortschrittsanzeige für Clients. Erfüllt REQ-L3-LA005-002.
*Alternative abgelehnt:* Nur done/failed — würde Zwischenfortschritt verbergen.

**ADR-L3-LA005-03 — Separate Soft/Hard-Timeouts für Celery**
*Entscheidung:* `CELERY_TASK_SOFT_TIME_LIMIT` (SoftTimeLimitExceeded-Signal) und `CELERY_TASK_TIME_LIMIT` (Hard-Kill).
*Rationale:* Soft-Limit gibt Task Chance zu graceful-shutdown, Hard-Limit garantiert Worker-Befreiung. Erfüllt REQ-L3-LA005-003.
*Alternative abgelehnt:* Nur Hard-Limit — würde graceful-shutdown verhindern.

**ADR-L3-LA005-04 — Fehler als Status-Feld, nicht Exception**
*Entscheidung:* Task-Fehler werden als `status=failed, error="..."` gespeichert, nicht als Exception propagiert.
*Rationale:* Clients können einfach abfragen und reagieren, ohne Exception-Handling. Erfüllt REQ-L3-LA005-004.
*Alternative abgelehnt:* Exception-Speicherung in Result-Backend — würde Komplexität beim Deserialisieren hinzufügen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
