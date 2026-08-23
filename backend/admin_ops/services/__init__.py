"""
admin_ops — service layer (REQ-L1-046 Disaster Recovery foundation).

This package re-exports the public service surface for downstream
consumers:

    from admin_ops.services import (
        BackupService,
        AdminRestoreService,
        RestoreResult,
        BackupNotFoundError,
    )

See ``backend/admin_ops/services/INTERFACES.md`` for the full interface
contract that backs these exports.
"""
from __future__ import annotations

from .admin_restore_service import AdminRestoreService, RestoreResult
from .backup_service import BackupService
from .banner_service import BannerService
from .exceptions import BackupNotFoundError

__all__ = [
    "BackupService",
    "AdminRestoreService",
    "RestoreResult",
    "BackupNotFoundError",
    "BannerService",
]
