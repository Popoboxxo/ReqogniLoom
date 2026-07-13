---
step: implementation
agent: se-developer
status: done
timestamp: "2026-06-24T00:00:00Z"
schema_version: "1.0.0"
---

# L2 ApplicationServiceSystem — Step 2 Implementation

**Scope:** COMP-AS-006..011 (Step 2 of 3)  
**Branch:** feat/se-implementation  
**req_id:** REQ-L1-018, REQ-L1-019, REQ-L1-020, REQ-L1-021, REQ-L1-023, REQ-L1-024

## Artifacts

| File | Component | Description |
|------|-----------|-------------|
| `backend/application/baseline_facade.py` | COMP-AS-006 | BaselineFacade — delegates to baseline.services, scope gate, audit |
| `backend/application/workflow_facade.py` | COMP-AS-007 | WorkflowFacade — transition + initialize_workflow_states, change-reason gate |
| `backend/application/export_service.py` | COMP-AS-008 | ExportService — JSON/CSV/Markdown; PDF stub (NotImplementedError, TODO-PDF) |
| `backend/application/import_service.py` | COMP-AS-009 | ImportService — atomic CSV import, 1000-row limit, full error report |
| `backend/application/search_service.py` | COMP-AS-010 | SearchService — PostgreSQL FTS via tsvector/tsquery, pagination |
| `backend/application/webhook_dispatcher.py` | COMP-AS-011 | WebhookDispatcher — HMAC-SHA256, retry/backoff, DLQ logging |
| `backend/application/models.py` | COMP-AS-011 | WebhookSubscription + WebhookDeliveryLog models added |
| `backend/application/migrations/0002_webhook_models.py` | COMP-AS-011 | DB migration for new Webhook tables |
| `backend/application/services_step2.py` | All | Bundle re-export + registry hooks |
| `backend/application/services.py` | All | One-line `from services_step2 import *` added |

## Test Coverage

| Test file | Coverage target |
|-----------|-----------------|
| `backend/application/tests/test_baseline_facade.py` | COMP-AS-006: delegation, scope gate, audit, event, exception remapping |
| `backend/application/tests/test_workflow_facade.py` | COMP-AS-007: delegation, change-reason gate, role gate, audit, event |
| `backend/application/tests/test_export_service.py` | COMP-AS-008: JSON/CSV/MD format, terminology embed, PDF stub |
| `backend/application/tests/test_import_service.py` | COMP-AS-009: parsing, validation, atomicity (1000 rows), rollback |
| `backend/application/tests/test_search_service.py` | COMP-AS-010: QueryParser ops, type filter, pagination, tenant isolation |
| `backend/application/tests/test_webhook_dispatcher.py` | COMP-AS-011: subscribe, payload, HMAC, retry, 4xx no-retry, DLQ |

## Escalations / TODOs

- **TODO-PDF (COMP-AS-008):** `ExportService.export_pdf()` raises `NotImplementedError`. Install `reportlab` or `weasyprint` and implement `_render_pdf()`. REQ-L1-023.
- **TODO-ASYNC (COMP-AS-011):** `WebhookDispatcher._dispatch_with_retry()` is synchronous. Future integration with ResilienceOrchestrator (ARCH-L1-016) via Celery/Django-Q. REQ-L3-WHOOK-007.
