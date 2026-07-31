"""
admin_ops — service-layer exceptions (REQ-L1-046).

Kept separate from the service modules so that other layers (future
REST views, MCP tools) can import the exception types without pulling
in Django or the model layer.
"""
from __future__ import annotations


class BackupNotFoundError(LookupError):
    """Raised when a requested :class:`BackupMetadata` row is not found
    or is not in a restorable state (status != 'completed').

    Mirrors the ``application.base.NotFoundError`` pattern but is
    defined locally so that the foundation does not depend on the
    ApplicationService package.
    """


class BackupStorageError(RuntimeError):
    """Raised when the backup directory cannot be created/written to
    (GitHub #37).

    Wraps the underlying ``OSError``/``PermissionError`` with an
    operator-actionable message instead of letting the raw filesystem
    error (which can read as ``"Permission denied: /app/backups/"``)
    propagate to REST/MCP callers as an unmapped 500/INTERNAL_ERROR.
    """


__all__ = ["BackupNotFoundError", "BackupStorageError"]
