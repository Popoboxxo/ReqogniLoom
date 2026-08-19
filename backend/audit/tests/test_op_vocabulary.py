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

--------------------------------------------------------------------------

GitHub #539 adds a second ratchet for ``write_mcp_audit`` (mcp_server/tools/
base.py) call sites. That helper hits the exact same ``full_clean()``
validation as ``ServiceBase._audit``, but *swallows* the resulting
``ValidationError`` (logs it at ERROR, never re-raises) — so an undeclared
``operation=`` there does not fail loudly like #265 did; it silently drops
the audit row while the MCP tool call still reports ``success=True``. The
admin/user/permissions MCP tool groups fixed for #539 are covered below.

Scope note: this second ratchet intentionally scans only the tool-group
files fixed so far, not the whole ``mcp_server/tools/`` package —
``admin.py``, ``backup.py``, ``users.py``, ``permissions.py`` (#539) plus
``requirements.py`` and ``needs.py`` (#573). Widening the scan to all of
``mcp_server/tools/`` would make this ratchet fail on the gaps that are
still open: ``ai_derivation.py`` (six undeclared ops), ``audit.py``
(``"replay"``), ``architecture.py`` / ``diagram.py`` / ``tests.py``
(``"outdate"`` / ``"reactivate"``) and ``review.py`` (``"approve"`` /
``"reject"`` / ``"request_changes"``). Widen ``_MCP_TOOL_FILES`` as each
remaining tool group is fixed.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from audit.models import AuditEntry

# backend/audit/tests/ -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_ROOTS = (_BACKEND_ROOT / "application",)

# #539: MCP tool-group files whose write_mcp_audit(operation=...) call sites
# are covered by this ratchet. See scope note in the module docstring.
_MCP_TOOL_FILES = (
    _BACKEND_ROOT / "mcp_server" / "tools" / "admin.py",
    _BACKEND_ROOT / "mcp_server" / "tools" / "backup.py",
    _BACKEND_ROOT / "mcp_server" / "tools" / "users.py",
    _BACKEND_ROOT / "mcp_server" / "tools" / "permissions.py",
    # #573
    _BACKEND_ROOT / "mcp_server" / "tools" / "requirements.py",
    _BACKEND_ROOT / "mcp_server" / "tools" / "needs.py",
)


def _calls_with_operation_kwarg(
    paths: tuple[Path, ...], *, func_attr: str | None, func_name: str | None
) -> dict[str, list[str]]:
    """Map each ``operation=`` literal to the files whose matching call uses it.

    Exactly one of ``func_attr`` (``self.<func_attr>(...)``) or ``func_name``
    (bare ``<func_name>(...)``) must be given.
    """
    found: dict[str, list[str]] = {}
    for path in paths:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            matches = False
            if func_attr is not None:
                matches = (
                    isinstance(func, ast.Attribute)
                    and func.attr == func_attr
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                )
            elif func_name is not None:
                matches = isinstance(func, ast.Name) and func.id == func_name
            if not matches:
                continue
            for kw in node.keywords:
                if kw.arg == "operation" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        found.setdefault(kw.value.value, []).append(
                            path.relative_to(_BACKEND_ROOT).as_posix()
                        )
    return found


def _audited_operations() -> dict[str, list[str]]:
    """Map each ``operation=`` literal to the files whose ``self._audit`` uses it."""
    found: dict[str, list[str]] = {}
    for root in _SERVICE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "/tests/" in path.as_posix() or "/migrations/" in path.as_posix():
                continue
            found.update(
                {
                    op: found.get(op, []) + files
                    for op, files in _calls_with_operation_kwarg(
                        (path,), func_attr="_audit", func_name=None
                    ).items()
                }
            )
    return found


def _mcp_audited_operations() -> dict[str, list[str]]:
    """Map each ``operation=`` literal to the files whose ``write_mcp_audit`` uses it.

    Scoped to ``_MCP_TOOL_FILES`` — see module docstring scope note (#539).
    """
    return _calls_with_operation_kwarg(
        _MCP_TOOL_FILES, func_attr=None, func_name="write_mcp_audit"
    )


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


def test_mcp_admin_tool_audit_operations_are_declared_choices() -> None:
    """Every write_mcp_audit(operation=...) literal in the covered MCP tool
    groups must be a valid ``AuditEntry.op`` choice (#539).

    Unlike #265's ``self._audit``, an undeclared op here does not raise
    loudly — ``write_mcp_audit`` swallows the ``ValidationError`` and the
    MCP tool call still reports success while writing zero audit rows. This
    ratchet is the only thing that would have caught #539 before it shipped.
    """
    operations = _mcp_audited_operations()
    assert operations, (
        "no write_mcp_audit(operation=...) calls found in the covered MCP "
        "tool files — parser is broken or _MCP_TOOL_FILES is stale"
    )

    valid = {value for value, _label in AuditEntry.OP_CHOICES}
    unknown = {op: files for op, files in operations.items() if op not in valid}

    assert not unknown, (
        "these write_mcp_audit operations are missing from "
        "AuditEntry.OP_CHOICES — the MCP tool call would report success "
        f"while silently writing zero audit rows (#539): {unknown}"
    )


@pytest.mark.parametrize(
    "operation",
    ["workspace.delete", "clone", "assign"],
)
def test_regression_operations_are_declared(operation: str) -> None:
    """Explicit guard for the three ops that were missing when #265 was filed."""
    assert operation in {value for value, _label in AuditEntry.OP_CHOICES}


@pytest.mark.parametrize(
    "operation",
    [
        "admin.backup_create",
        "admin.restore",
        "permissions.set_rule",
        "permissions.revoke",
        "user.create",
        "user.assign_role",
        "user.deactivate",
    ],
)
def test_regression_mcp_admin_operations_are_declared(operation: str) -> None:
    """Explicit guard for the seven ops that were missing when #539 was filed.

    Before the fix these MCP admin/user/permissions tool calls reported
    ``success=True`` while ``write_mcp_audit`` silently wrote zero audit
    rows for exactly these operation values.
    """
    assert operation in {value for value, _label in AuditEntry.OP_CHOICES}


@pytest.mark.parametrize(
    "operation",
    ["ai.decompose", "ai.validate", "ai.check_consistency"],
)
def test_regression_mcp_ai_operations_are_declared(operation: str) -> None:
    """The three AI tool ops added for #573 must stay declared choices.

    ``requirement.decompose`` / ``requirement.validate`` /
    ``requirement.check_consistency`` used to pass the undeclared literals
    ``"decompose"`` / ``"validate"`` / ``"check_consistency"``.
    """
    assert operation in {value for value, _label in AuditEntry.OP_CHOICES}


@pytest.mark.parametrize(
    ("tool_file", "operation"),
    [
        ("mcp_server/tools/requirements.py", "delete"),
        ("mcp_server/tools/requirements.py", "transition"),
        ("mcp_server/tools/needs.py", "delete"),
        ("mcp_server/tools/needs.py", "transition"),
    ],
)
def test_regression_mcp_lifecycle_ops_reuse_rest_vocabulary(
    tool_file: str, operation: str
) -> None:
    """#573: MCP soft-delete/restore must audit under the REST pendant's op.

    ``requirement.outdate`` / ``needs.outdate`` used to pass ``"outdate"`` and
    ``*.reactivate`` used to pass ``"reactivate"`` — neither is a declared
    choice, so both wrote zero rows. Reusing ``delete`` / ``transition``
    (what ``RequirementService.delete_requirement`` and
    ``WorkflowFacade.reactivate`` write for the REST path) keeps one audit
    query able to answer "who removed this artifact" across both surfaces;
    this guard fails if someone re-introduces a tool-name-shaped op there.
    """
    operations = _mcp_audited_operations()
    assert tool_file in operations.get(operation, []), (
        f"{tool_file} no longer emits write_mcp_audit(operation={operation!r}) "
        f"— found: { {op: files for op, files in operations.items() if tool_file in files} }"
    )


def test_op_choices_fit_the_column_width() -> None:
    """A choice longer than ``max_length`` would fail at INSERT time."""
    max_length = AuditEntry._meta.get_field("op").max_length
    too_long = [value for value, _ in AuditEntry.OP_CHOICES if len(value) > max_length]
    assert not too_long, f"op choices exceed max_length={max_length}: {too_long}"
