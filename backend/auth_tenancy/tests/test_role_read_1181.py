"""Role read primitive: normalisation, suspension, RLS-armed read, static guard.

Issue #1181 (residual R-9 of the staged-RLS spec
``docs/audit/2026-10/1136-rls-coverage-spec.md``): promote the ad-hoc inline
pre-auth role read into the named, tenant-agnostic primitive
:func:`auth_tenancy.services.role_read.resolve_roles_for_user`. Behaviour must
stay byte-identical to the pre-#1181 output (the login/refresh JWT ``roles``
claim), so these tests pin:

* the exact dedup/sort/lower normalisation **without** a database,
* the ``suspended_at IS NULL`` filter,
* that the read still returns the user's roles when the staged pre-auth policy
  is ARMED for the app role and ``app.current_tenant`` points at a DIFFERENT
  tenant (the R-9 tenant-agnostic boundary),
* that no other production module inlines ``auth_resolve_roles`` or a
  ``UserRole.unscoped`` role read (static AST scan, database-free).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.db import connection
from django.utils import timezone

from auth_tenancy.models import UserRole
from auth_tenancy.services.role_read import (
    ROLES_SQL,
    normalize_roles,
    resolve_roles_for_user,
)
from persistence.db_roles import APP_DB_ROLE

# ---------------------------------------------------------------------------
# Normalisation — pure, no database (deliverable 1: separable DB call)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["ADMIN", "approver", "admin"], ("admin", "approver")),
        (["Editor", "EDITOR", "editor"], ("editor",)),
        (["zeta", "alpha", "mu"], ("alpha", "mu", "zeta")),
        (["approver", "admin"], ("admin", "approver")),
        ([], ()),
    ],
)
def test_normalize_roles_dedups_sorts_and_lowercases(raw, expected):
    """The normalisation is exactly dedup + sort + lower-case (F4/AC-22)."""
    assert normalize_roles(raw) == expected


def test_normalize_roles_coerces_non_string_values():
    """Non-string DB values go through ``str(...)`` before lowering, as before."""
    assert normalize_roles([b"Admin".decode(), "admin"]) == ("admin",)


# ---------------------------------------------------------------------------
# Suspension filtering (live DB, unarmed)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_roles_for_user_filters_suspended_assignments(
    tenant_a, user_a, workspace_a
):
    """``suspended_at IS NULL`` is enforced by the read, so suspended roles drop."""
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=workspace_a, role="admin"
    )
    UserRole.unscoped.create(
        tenant=tenant_a,
        user=user_a,
        workspace=workspace_a,
        role="approver",
        suspended_at=timezone.now(),
    )

    assert resolve_roles_for_user(user_a.id) == ("admin",)


# ---------------------------------------------------------------------------
# R-9 boundary: tenant-agnostic under the armed app role
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_read_is_tenant_agnostic_under_armed_app_role(
    tenant_a, tenant_b, user_a, workspace_a
):
    """With the staged pre-auth policy ARMED and ``app.current_tenant`` pointing
    at a DIFFERENT tenant, the ``SECURITY DEFINER`` read still returns the user's
    tenant-A roles.

    This pins residual R-9: the primitive filters only ``user_id`` (+
    suspension), never ``tenant_id``. The contrast assertion below confirms the
    policy really is armed (a plain direct read of ``at_user_role`` sees nothing
    for the foreign tenant), so the role result genuinely comes from the
    owner-privileged function and not from a disabled policy.
    """
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=workspace_a, role="Admin"
    )

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_preauth_enforced = 'on'")
        cursor.execute("SET app.rls_as_enforced = 'on'")
        cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
    try:
        roles = resolve_roles_for_user(user_a.id)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.at_user_role WHERE user_id = %s",
                [user_a.id],
            )
            rls_visible = cursor.fetchone()[0]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET app.rls_preauth_enforced")
            cursor.execute("RESET app.rls_as_enforced")
            cursor.execute("RESET ROLE")

    assert roles == ("admin",)
    assert rls_visible == 0, (
        "the staged pre-auth policy is not armed, so this test would not prove "
        "the tenant-agnostic boundary"
    )


# ---------------------------------------------------------------------------
# Static guard — one sanctioned inline of auth_resolve_roles, no UserRole.unscoped
# ---------------------------------------------------------------------------

#: Backend package root: ``.../backend`` on the host, ``/app`` in the
#: ``backend-test`` container. ``parents[2]`` is stable in both layouts.
_BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]

#: Directory names that are never production code.
_EXCLUDED_DIR_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})

#: File names that are never production code.
_EXCLUDED_FILE_NAMES: frozenset[str] = frozenset({"conftest.py"})

#: The only production module allowed to inline the ``auth_resolve_roles`` call.
_SOLE_SANCTIONED_MODULE = "backend/auth_tenancy/services/role_read.py"

#: SQL-identifier marker the guard scans for in string literals.
_MARKER = "auth_resolve_roles"


def _iter_production_files() -> list[Path]:
    """Every production ``*.py`` file under ``backend/`` (tests/migrations excluded)."""
    files: list[Path] = []
    for path in sorted(_BACKEND_ROOT.rglob("*.py")):
        if any(part in _EXCLUDED_DIR_PARTS for part in path.parts):
            continue
        if path.name in _EXCLUDED_FILE_NAMES:
            continue
        files.append(path)
    return files


def _relative_backend_path(path: Path) -> str:
    return f"backend/{path.relative_to(_BACKEND_ROOT).as_posix()}"


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Ids of string nodes that are docstrings (module/class/function first stmt)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _production_modules_inlining_marker(marker: str) -> set[str]:
    """Production modules with a non-docstring string constant naming ``marker``."""
    callers: set[str] = set()
    for path in _iter_production_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        docstrings = _docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and marker in node.value
            ):
                callers.add(_relative_backend_path(path))
                break
    return callers


def _production_modules_with_userrole_unscoped() -> set[str]:
    """Production modules that use ``UserRole.unscoped`` directly."""
    callers: set[str] = set()
    for path in _iter_production_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "unscoped"
                and isinstance(node.value, ast.Name)
                and node.value.id == "UserRole"
            ):
                callers.add(_relative_backend_path(path))
                break
    return callers


def test_only_the_primitive_inlines_auth_resolve_roles() -> None:
    """`auth_resolve_roles` is inlined in exactly one production module.

    A second inline (or the SQL drifting back into
    ``password_authentication.py``) would reintroduce the ad-hoc read R-9 asks
    to replace; a disappeared call means the primitive is no longer the read
    path. Either way the reviewed surface must be updated deliberately.
    """
    callers = _production_modules_inlining_marker(_MARKER)
    assert callers == {_SOLE_SANCTIONED_MODULE}, (
        "The `auth_resolve_roles` call must live in exactly one production "
        f"module ({_SOLE_SANCTIONED_MODULE}), but found: {sorted(callers)}"
    )
    assert "auth_resolve_roles" in ROLES_SQL


def test_no_production_userrole_unscoped_role_read() -> None:
    """R-9: the production role read no longer uses ``UserRole.unscoped``.

    The broader ``.unscoped`` inventory lives in
    ``tests/test_unscoped_readers_guard_1184.py``; this focused assertion keeps
    the R-9 guarantee self-contained (zero production ``UserRole.unscoped``
    accesses).
    """
    callers = _production_modules_with_userrole_unscoped()
    assert not callers, (
        "Production code reads roles via `UserRole.unscoped`, bypassing the "
        f"single sanctioned primitive: {sorted(callers)}"
    )


def test_password_service_delegates_to_the_primitive() -> None:
    """``PasswordAuthenticationService.resolve_roles`` contains no raw SQL and
    calls the named primitive (no duplicated inline read)."""
    path = (
        _BACKEND_ROOT / "auth_tenancy" / "services" / "password_authentication.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PasswordAuthenticationService":
            for child in node.body:
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name == "resolve_roles"
                ):
                    target = child
    assert target is not None, "PasswordAuthenticationService.resolve_roles not found"

    called = {
        node.func.id
        if isinstance(node.func, ast.Name)
        else getattr(node.func, "attr", None)
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
    }
    assert "resolve_roles_for_user" in called, (
        "resolve_roles no longer delegates to resolve_roles_for_user"
    )

    inline_sql = [
        node.value
        for node in ast.walk(target)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "SELECT" in node.value.upper()
    ]
    assert not inline_sql, f"resolve_roles still contains inline SQL: {inline_sql}"

    uses_connection = any(
        isinstance(node, ast.Name) and node.id == "connection"
        for node in ast.walk(target)
    )
    assert not uses_connection, "resolve_roles still touches the DB connection directly"
