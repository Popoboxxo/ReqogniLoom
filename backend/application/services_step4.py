"""
ApplicationService Step 4 — Re-export surface for COMP-AS-017..018, COMP-AS-021.

leaf_id : COMP-AS-017, COMP-AS-018, COMP-AS-021
req_id  : REQ-L2-AS-030 (Test-Run-Protokollierung),
          REQ-L2-AS-031 (Automatisierte Test-Ergebnis-Einspeisung),
          REQ-157 (Change Request CCB Workflow)

Downstream consumers import from here OR from application.services
(after the one-line re-export added to that file).

Import paths::

    from application.services_step4 import (
        TestRunService,
        VALID_RESULT_STATUSES,
        ChangeRequestService,
        ChangeRequestDTO,
    )
"""
from __future__ import annotations

# COMP-AS-017
from application.test_run_service import VALID_RESULT_STATUSES, TestRunService  # noqa: F401

# COMP-AS-021
from application.change_request_service import (  # noqa: F401
    ChangeRequestService,
    ChangeRequestDTO,
    ChangeRequestValidator,
)

# ---------- Registry hook (services.py extension pattern) ----------
from application.services import _registry  # noqa: E402

_registry["TestRunService"] = TestRunService
_registry["ChangeRequestService"] = ChangeRequestService

# ---------- Public surface ----------

__all__ = [
    "TestRunService",
    "VALID_RESULT_STATUSES",
    "ChangeRequestService",
    "ChangeRequestDTO",
    "ChangeRequestValidator",
]
