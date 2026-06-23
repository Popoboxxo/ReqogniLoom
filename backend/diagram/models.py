"""
ARCH-L1-013 DiagramService — Models.

TODO(COMP-DS-001): Implement Diagram model.
  Fields: id, tenant_id, workspace_id, name, diagram_type (enum: block/flow/context/...),
  current_version_id (FK → DiagramVersion), created_at, created_by, artifact metadata.
TODO(COMP-DS-002): Implement DiagramVersion model — immutable per change.
  Fields: id, diagram_id (FK), version_number, payload_format (mermaid/plantuml/json),
  payload (TextField/JSONField), created_at, created_by.
  No update/delete path — append-only.
TODO(COMP-DS-003): Implement PayloadValidator — validates payload syntax
  per diagram_type and payload_format.

Reference: docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/L2_DiagramServiceSystem_Architecture.md
"""
from django.db import models  # noqa: F401
