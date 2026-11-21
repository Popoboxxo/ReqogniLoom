"""
admin_ops — internal path utilities (REQ-L1-046).

The DR foundation writes one gzip-compressed JSON dump per backup
(``<id>.json.gz``, issue #823) under a directory resolved in this order
(GitHub #37):

* ``BACKUP_DIR`` environment variable, if set — an operator-configurable
  override so a deployment can point backups at a writable mount
  independent of ``MEDIA_ROOT``/``BASE_DIR`` (e.g. when the default
  container path is not writable).
* If ``settings.MEDIA_ROOT`` is set, the file lives at
  ``<MEDIA_ROOT>/backups/<id>.json.gz``.
* Otherwise we fall back to ``<BASE_DIR>/backups/<id>.json.gz`` (and then
  to the bare ``backups/`` directory if neither is configured). This
  keeps the foundation usable in tests that strip Django settings.

R1/P5 (D14b) adds the parallel ``export_root()`` / ``absolute_export_path()``
helpers for artifact-transfer ZIP snapshots under ``EXPORT_DIR`` (or
``MEDIA_ROOT/exports``), sharing the same resolution order.

These helpers are private to the ``admin_ops.services`` package.
"""
from __future__ import annotations

import os

from django.conf import settings

_BACKUP_SUBDIR = "backups"
_BACKUP_DIR_ENV_VAR = "BACKUP_DIR"

# R1/P5 (D14b): versioned ZIP snapshots live next to the DR backups, under a
# separate directory so retention/TTL cleanup can never delete a backup.
_EXPORT_SUBDIR = "exports"
_EXPORT_DIR_ENV_VAR = "EXPORT_DIR"


def export_root() -> str:
    """Return the absolute directory that holds export ZIP files (D14b).

    Mirrors :func:`backup_root` exactly, with ``EXPORT_DIR`` as the
    operator-configurable override: ``EXPORT_DIR`` > ``MEDIA_ROOT/exports`` >
    ``BASE_DIR/exports`` > bare ``exports``. Never raises, so a test that
    strips Django settings still resolves a usable path.
    """
    export_dir_env = os.environ.get(_EXPORT_DIR_ENV_VAR, "").strip()
    if export_dir_env:
        return export_dir_env
    media_root = getattr(settings, "MEDIA_ROOT", "") or ""
    if media_root:
        return os.path.join(str(media_root), _EXPORT_SUBDIR)
    base_dir = getattr(settings, "BASE_DIR", "") or ""
    if base_dir and os.path.isdir(str(base_dir)):
        return os.path.join(str(base_dir), _EXPORT_SUBDIR)
    return _EXPORT_SUBDIR


def absolute_export_path(relative_path: str) -> str:
    """Resolve a path stored on :class:`ExportSnapshotMetadata` to an absolute path."""
    return os.path.join(export_root(), relative_path)


def backup_root() -> str:
    """Return the absolute directory that holds backup JSON files.

    Never raises; falls back to the bare subdirectory name if neither
    ``BACKUP_DIR``, ``MEDIA_ROOT`` nor ``BASE_DIR`` is set.
    """
    backup_dir_env = os.environ.get(_BACKUP_DIR_ENV_VAR, "").strip()
    if backup_dir_env:
        return backup_dir_env
    media_root = getattr(settings, "MEDIA_ROOT", "") or ""
    if media_root:
        return os.path.join(str(media_root), _BACKUP_SUBDIR)
    base_dir = getattr(settings, "BASE_DIR", "") or ""
    if base_dir and os.path.isdir(str(base_dir)):
        return os.path.join(str(base_dir), _BACKUP_SUBDIR)
    return _BACKUP_SUBDIR


def absolute_backup_path(relative_path: str) -> str:
    """Resolve a path stored on :class:`BackupMetadata` back to an absolute path."""
    return os.path.join(backup_root(), relative_path)


__all__ = [
    "absolute_backup_path",
    "absolute_export_path",
    "backup_root",
    "export_root",
]
