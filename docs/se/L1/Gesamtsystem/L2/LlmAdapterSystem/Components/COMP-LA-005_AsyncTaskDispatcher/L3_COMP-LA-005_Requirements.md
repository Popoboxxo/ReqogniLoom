# L3 AsyncTaskDispatcher Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-LA-005 — AsyncTaskDispatcher
> **Parent-System:** LlmAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Dispatcht LLM-Langlaeufer (`decompose_requirement`, `check_consistency`) als Celery-Tasks in die Queue. Gibt sofort eine `task_id` zurueck, ohne den WSGI/ASGI-Worker zu blockieren. Stellt `get_task_status(task_id)` fuer Statusabfragen bereit. Verwaltet Task-Ergebnisse im Celery Result-Backend. Bei Task-Fehler: Ergebnis als `{status: "failed", error: "..."}` speichern.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-LA-008 | Asynchrone LLM-Task-Ausführung via Celery |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-INT-005 | eingehend | COMP-LA-003 (CapabilityRouter) | `dispatch_async(capability, kwargs) -> task_id` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-EXT-OUT-003 | ausgehend | Celery-Task-Queue (Redis/RabbitMQ) | `dispatch_task(capability, kwargs) -> task_id`; `get_task_status(task_id) -> TaskStatusResult` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-LA005-001: Sofortiger Task-Dispatch mit task_id-Rueckgabe

Der AsyncTaskDispatcher SHALL bei Aufruf von `dispatch_async(capability, kwargs)` den LLM-Aufruf als Celery-Task in die Queue dispatchen und sofort eine UUID-basierte `task_id` zurueckgeben. Der Dispatch-Vorgang selbst SHALL den aufrufenden Thread nicht fuer die Dauer des LLM-Aufrufs blockieren. Die Rueckgabe der `task_id` MUSS innerhalb von 500 ms erfolgen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `dispatch_async("decompose_requirement", {"requirement_id": "x"})` returns `task_id` (UUID string) within 500ms
- [ ] `dispatch_async("check_consistency", {"workspace_id": "y"})` returns `task_id` within 500ms
- [ ] Celery broker receives task message immediately after dispatch
- [ ] Calling thread is not blocked for the duration of the LLM provider call

---

### REQ-L3-LA005-002: Task-Status-Abfrage und Ergebnisverwaltung

Der AsyncTaskDispatcher SHALL `get_task_status(task_id) -> TaskStatusResult` implementieren. Moegliche Status-Werte: `pending` (Task in Queue, noch nicht gestartet), `running` (Celery-Worker hat Task uebernommen), `done` (Task abgeschlossen, `result` enthalten), `failed` (Task fehlgeschlagen, `error` enthalten). Das Ergebnis SHALL im Celery Result-Backend (Redis/RabbitMQ) persistiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Immediately after dispatch → `get_task_status(task_id)` returns `{"status": "pending"}`
- [ ] During worker execution → `get_task_status(task_id)` returns `{"status": "running"}`
- [ ] After successful completion → `{"status": "done", "result": {...}}`
- [ ] After failure → `{"status": "failed", "error": "<message>"}`
- [ ] Unknown `task_id` → `{"status": "not_found"}` or documented error response
- [ ] Result persisted in Celery Result-Backend and retrievable after worker restart

---

### REQ-L3-LA005-003: Konfigurierbarer Celery-Broker und Task-Timeout

Der AsyncTaskDispatcher SHALL den Celery-Broker ueber die Umgebungsvariable `CELERY_BROKER_URL` konfigurieren. Sowohl Redis als auch RabbitMQ SHALL als Broker unterstuetzt werden. Task-Timeouts auf Worker-Ebene SOLLEN ueber `CELERY_TASK_SOFT_TIME_LIMIT` (Warning) und `CELERY_TASK_TIME_LIMIT` (Hard-Kill) konfigurierbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `CELERY_BROKER_URL=redis://localhost:6379/0` → tasks dispatched via Redis broker
- [ ] `CELERY_BROKER_URL=amqp://...` → tasks dispatched via RabbitMQ broker
- [ ] `CELERY_TASK_SOFT_TIME_LIMIT=120` → `SoftTimeLimitExceeded` raised in worker at 120s
- [ ] `CELERY_TASK_TIME_LIMIT=180` → worker process killed at 180s
- [ ] Missing `CELERY_BROKER_URL` → `dispatch_async` returns structured error `{"error": {"code": "BROKER_NOT_CONFIGURED"}}`

---

### REQ-L3-LA005-004: Fehlerbehandlung bei Task-Ausfuehrung im Celery-Worker

Der AsyncTaskDispatcher SHALL sicherstellen, dass Fehler waehrend der Task-Ausfuehrung im Celery-Worker als `{status: "failed", error: "<message>"}` im Result-Backend gespeichert werden. Unhandled Exceptions im Worker DUERFEN nicht zu einem dauerhaft haengenden Task-Status fuehren. Der AsyncTaskDispatcher-Task SHALL bei jedem Fehler (Provider-Error, Timeout, unerwartete Exception) den Status explizit auf `failed` setzen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Provider error in Celery worker → `get_task_status(task_id)` returns `{"status": "failed", "error": "<detail>"}`
- [ ] Worker timeout (`SoftTimeLimitExceeded`) → `{"status": "failed", "error": "Task timed out"}`
- [ ] Unexpected exception in worker → `{"status": "failed", "error": "<exception text>"}`
- [ ] No task remains permanently in `pending` or `running` state after worker completion (success or failure)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
