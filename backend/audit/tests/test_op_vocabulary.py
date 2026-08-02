"""The audit ``op`` vocabulary must cover every operation services emit (#265).

``AuditLogWriter.write`` validates ``AuditEntry.op`` against
``AuditEntry.OP_CHOICES`` via ``full_clean``, and ``ServiceBase._audit``
re-raises the resulting ``ValidationError``. A service auditing an operation
that is missing from ``OP_CHOICES`` therefore aborts its own transaction with
an HTTP 500 — which is exactly how ``POST /api/v1/workspaces/{id}/delete/``
broke (GitHub #265): the delete itself worked, the audit write killed it.

This is a static ratchet: it parses every ``self._audit(...)`` call in the
service layer and asserts its ``operation=`` literal is a declared choice.

leaf_id : COMP-AL-001 (AuditLogWriter)
req_id  : REQ-L2-AL-004 / GitHub #265
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from audit.models import AuditEntry

# backend/audit/tests/ -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_ROOTS = (_BACKEND_ROOT / "application",)


def _audited_operations() -> dict[str, list[str]]:
    """Map each ``operation=`` literal to the files whose ``self._audit`` uses it."""
    found: dict[str, list[str]] = {}
    for root in _SERVICE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "/tests/" in path.as_posix() or "/migrations/" in path.as_posix():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "_audit"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                ):
                    continue
                for kw in node.keywords:
                    if kw.arg == "operation" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, str):
                            found.setdefault(kw.value.value, []).append(
                                path.relative_to(_BACKEND_ROOT).as_posix()
                            )
    return found


def test_service_layer_audit_operations_are_declared_choices() -> None:
    """Every audited operation string must be a valid ``AuditEntry.op`` choice."""
    operations = _audited_operations()
    assert operations, "no self._audit(operation=...) calls found — parser is broken"

    valid = {value for value, _label in AuditEntry.OP_CHOICES}
    unknown = {op: files for op, files in operations.items() if op not in valid}

    assert not unknown, (
        "these audited operations are missing from AuditEntry.OP_CHOICES and "
        "would make their service call fail with a 500 after the business "
        f"mutation already succeeded (#265): {unknown}"
    )


@pytest.mark.parametrize(
    "operation",
    ["workspace.delete", "clone", "assign"],
)
def test_regression_operations_are_declared(operation: str) -> None:
    """Explicit guard for the three ops that were missing when #265 was filed."""
    assert operation in {value for value, _label in AuditEntry.OP_CHOICES}


def test_op_choices_fit_the_column_width() -> None:
    """A choice longer than ``max_length`` would fail at INSERT time."""
    max_length = AuditEntry._meta.get_field("op").max_length
    too_long = [value for value, _ in AuditEntry.OP_CHOICES if len(value) > max_length]
    assert not too_long, f"op choices exceed max_length={max_length}: {too_long}"
