"""Shared CSV/spreadsheet-formula-injection mitigation (OWASP CSV Injection).

Used by:
  - :func:`application.export_service._csv_cell` (generic entity CSV export)
  - :func:`application.requirement_bundle_formatters._csv_safe` (requirement
    bundle CSV export)

SYSTEMAUDIT-2026-08-27 AP-6 L-4: both call sites previously kept their own,
byte-for-byte identical copy of the trigger tuple and the same one-line
"prefix with a quote" check. Centralised here so a future change to the
trigger set or the escaping strategy has exactly one place to change instead
of two that must be kept in sync by hand.
"""
from __future__ import annotations

from typing import Any

#: Leading characters a spreadsheet application (Excel, LibreOffice Calc,
#: Google Sheets) interprets as the start of a formula rather than literal
#: text. A cell beginning with any of these is prefixed with a single quote
#: on export — the OWASP-documented CSV-injection mitigation.
CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def neutralize_csv_formula(value: Any) -> Any:
    """Prefix *value* with a single quote if it looks like a spreadsheet formula.

    Requirement/ArchitectureElement/... titles and descriptions are free text
    written by any editor-role tenant user, and CSV exports are served
    directly as ``text/csv`` for the caller to open in a spreadsheet
    application — an unescaped ``=cmd|'/c calc'!A1`` title would otherwise
    execute on whoever opens the file.

    Non-string values are returned unchanged; callers handle their own
    stringification/JSON-encoding for lists/dicts/bools independently.

    Args:
        value: A candidate CSV cell value.

    Returns:
        The original value, or the string prefixed with ``'`` if it starts
        with one of :data:`CSV_FORMULA_TRIGGERS`.
    """
    if isinstance(value, str) and value.startswith(CSV_FORMULA_TRIGGERS):
        return "'" + value
    return value


__all__ = ["CSV_FORMULA_TRIGGERS", "neutralize_csv_formula"]
