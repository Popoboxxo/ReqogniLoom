"""App configuration for ARCH-L1-006 BaselineService."""
from django.apps import AppConfig


class BaselineConfig(AppConfig):
    """ARCH-L1-006 BaselineService — Immutable Snapshot Engine.

    Responsibilities:
    - Creates immutable baselines on 3 scopes: document / project / global (ADR-07).
    - Resolves scope, collects all affected item IDs + versions, persists atomically
      as JSON snapshot.
    - Provides baseline comparison (diff) operations.
    - Global baselines only in Extended preset (consults PresetConfigEngine, ARCH-L1-008).
    - Baseline snapshots include ICD versions (IF-L1-038, REQ-L1-028).

    See: docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md
    REQ-L1: REQ-L1-008 (Multi-level baselines)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "baseline"
    verbose_name = "ARCH-L1-006 BaselineService"
