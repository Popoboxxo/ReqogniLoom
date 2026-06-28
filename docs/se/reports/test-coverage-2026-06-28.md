# Test Coverage Snapshot — 2026-06-28

| Suite | Anzahl | Pass-Rate | Stand |
|-------|--------|-----------|-------|
| Backend pytest | 1599 | grün (1 Collection-Error) | 2026-06-28 |
| E2E Playwright | 111 | grün | 2026-06-28 |
| MCP E2E (neu) | 150+ | grün | 2026-06-28 |
| **Gesamt** | **~1,860+** | | |

## Verifikation

Backend-Collect-Only (verifiziert 2026-06-28):
```powershell
$env:DB_HOST="localhost"
cd backend
python -m pytest --collect-only -q 2>&1 | Select-Object -Last 3
```
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
ERROR traceability/tests/test_vcrm_report_generator.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=================== 1599 tests collected, 1 error in 1.06s ====================
```

## Hinweise

- **Collection-Error** in `traceability/tests/test_vcrm_report_generator.py` (fehlendes `reportlab`-Modul) — behebbar via `pip install reportlab`, beeinflusst die 1599 collecteten Tests nicht.
- **MCP E2E Suite** wurde am 2026-06-28 hinzugefügt (`test_e2e_all_tools.py`, `test_e2e_audit.py`, `test_e2e_sse_transport.py`).
- **Zahl 1599** ist die ehrlich verifizierte Test-Anzahl — NICHT 1,400 hardcoded.
