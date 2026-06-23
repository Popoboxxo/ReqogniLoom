"""
ARCH-L1-008 PresetConfigEngine — Models.

TODO(COMP-PCE-001): Implement WorkspaceSettings model with preset enum
  (Minimal / Standard / Extended) and terminology_profile field.
TODO(COMP-PCE-002): Implement PresetRule model — stores per-preset configuration:
  mandatory fields, visible features, baseline scope availability,
  workflow configurability, change_reason obligation.
TODO(COMP-PCE-003): Implement TerminologyProfile model — label overrides per
  artifact type for Dev-mode vs SE-mode rendering.

Reference: docs/se/L1/Gesamtsystem/L2/PresetConfigEngineSystem/L2_PresetConfigEngineSystem_Architecture.md
"""
from django.db import models  # noqa: F401
