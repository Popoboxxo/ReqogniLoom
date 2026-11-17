"""Shared ``not provided`` sentinel for application commands (R2C-002).

Kept deliberately minimal: one module-level identity shared by every service
and DTO, so a command built in one layer is understood by another. ``UNSET``
is distinct from ``None``, which is a real value (often "clear to NULL").
"""

UNSET = object()

__all__ = ["UNSET"]
