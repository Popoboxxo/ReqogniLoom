"""R-3 static guard: every ``ApiKey`` / ``UserRole`` ``.unscoped`` reader is known.

Issue #1184 (residual R-3 of the staged-RLS spec
``docs/audit/2026-10/1136-rls-coverage-spec.md``): before ``RLS_PREAUTH_ENFORCED``
is flipped on, every production ``.unscoped`` reader of ``at_api_key`` /
``at_user_role`` must be verified, because a reader that runs without a tenant
context would be *silently emptied* by the staged policy. The reviewed inventory
lives in ``docs/audit/2026-10/1136-r3-unscoped-inventory.md``.

This test is STATIC and database-free: it parses the production Python files
under ``backend/`` with :mod:`ast` and collects every attribute access
``<Model>.unscoped`` for the tracked models. Parsing (rather than a raw regex)
deliberately ignores the many docstring/comment mentions of
``ApiKey.unscoped`` / ``UserRole.unscoped`` — only real code accesses count.

The discovered reader set is compared against :data:`_UNSCOPED_ALLOWLIST`, an
explicit, reviewed table of ``(relative_path, enclosing_symbol, model)`` keys,
each with its expected occurrence count and a one-line justification. A NEW
reader (a new key, or one more access inside an allowlisted symbol) fails the
test with instructions to either remove it or add a justified allowlist entry —
so the R-3 inventory cannot drift silently. A second assertion keeps the
documented inventory in sync with the allowlist. Following
``backend/persistence/tests/test_rls_coverage.py``, nothing here imports Django.
"""
from __future__ import annotations

import ast
from pathlib import Path

#: Models whose ``.unscoped`` manager is tracked. ``UserRole`` is listed so a
#: reintroduced production read fails too, even though the reviewed inventory
#: expects zero of them (the role read is the SECURITY DEFINER function
#: ``public.auth_resolve_roles``).
_TRACKED_MODELS: frozenset[str] = frozenset({"ApiKey", "UserRole"})

#: Directory names that are never production code.
_EXCLUDED_DIR_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})

#: File names that are never production code.
_EXCLUDED_FILE_NAMES: frozenset[str] = frozenset({"conftest.py"})

#: The backend package root (``.../backend`` on the host, ``/app`` in the
#: ``backend-test`` container, where only ``./backend`` is bind-mounted). This
#: file is ``backend/auth_tenancy/tests/<this>``, so ``parents[2]`` is the
#: directory that contains ``auth_tenancy`` — stable in both layouts.
_BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]

#: Where the ``docs/`` tree may be rooted: next to ``backend`` on the host, or
#: directly under the backend mount in the test container (``./docs:/app/docs``).
_DOCS_ROOTS: tuple[Path, ...] = (_BACKEND_ROOT.parent, _BACKEND_ROOT)

#: Relative path (from the docs root) of the human-readable R-3 inventory this
#: guard is the machine check for.
_INVENTORY_DOC_RELPATH: str = "docs/audit/2026-10/1136-r3-unscoped-inventory.md"

#: Stable, environment-independent prefix used as the first allowlist tuple
#: element. Production paths are reported as ``backend/<path under backend>``
#: regardless of where the backend tree is mounted.
_RELATIVE_PATH_PREFIX = "backend"


def _inventory_doc_path() -> Path:
    """Return the R-3 inventory document path (first existing candidate)."""
    candidates = tuple(root / _INVENTORY_DOC_RELPATH for root in _DOCS_ROOTS)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


# ---------------------------------------------------------------------------
# Reviewed allowlist — issue #1184 (R-3)
# ---------------------------------------------------------------------------
# Key:  (relative_path, enclosing_symbol, model).
# Value: (expected number of ``.unscoped`` accesses inside that symbol, one-line
#         justification naming the tenant-context status).
#
# This is the authoritative "known, verified" set. Removing an entry requires
# reworking that code path; adding one requires a review of the new reader's
# tenant-context behaviour under ``RLS_PREAUTH_ENFORCED=on``. Each path here
# MUST also appear in the inventory document (asserted below).
_UNSCOPED_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {
    (
        "backend/auth_tenancy/services/authentication.py",
        "AuthenticationService.create_api_key",
        "ApiKey",
    ): (
        2,
        (
            "Active-key cap: one READ count + one CREATE on an authenticated REST "
            "request where AuthTenancyAuthentication has armed the tenant context."
        ),
    ),
    (
        "backend/auth_tenancy/services/authentication.py",
        "AuthenticationService.list_api_keys",
        "ApiKey",
    ): (
        1,
        (
            "Self-scoped metadata listing, only from ApiKeyViewSet behind "
            "AuthTenancyAuthentication, so the tenant context is armed."
        ),
    ),
    (
        "backend/auth_tenancy/services/authentication.py",
        "AuthenticationService.revoke_api_key",
        "ApiKey",
    ): (
        1,
        (
            "Self-scoped revoke READ; armed from REST. The tenant-less CLI caller is "
            "stopped upstream by the loud-failing Command._resolve_key."
        ),
    ),
    (
        "backend/auth_tenancy/management/commands/revoke_api_key.py",
        "Command._resolve_key",
        "ApiKey",
    ): (
        2,
        (
            "Privileged cross-tenant resolve WITHOUT a tenant context; under ON it "
            "fails loud (CommandError 'No API key matches'), never silently."
        ),
    ),
    (
        "backend/auth_tenancy/management/commands/inventory_api_keys.py",
        "collect_inventory",
        "ApiKey",
    ): (
        1,
        (
            "Read-only cross-tenant inventory guarded by SET LOCAL row_security = "
            "off; on the app role the read raises under ON instead of returning 0."
        ),
    ),
    (
        "backend/auth_tenancy/management/commands/cleanup_revoked_api_keys.py",
        "Command.handle",
        "ApiKey",
    ): (
        1,
        (
            "Cross-tenant maintenance without a tenant context, like the canon "
            "collect_inventory: guarded by SET LOCAL row_security = off, so on "
            "the app role the read raises instead of silently deleting 0."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _base_name(node: ast.expr) -> str | None:
    """Return the last name of an attribute/name chain (``models.ApiKey`` -> ``ApiKey``)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _UnscopedReaderVisitor(ast.NodeVisitor):
    """Collect ``<tracked_model>.unscoped`` accesses keyed by enclosing symbol."""

    def __init__(self, relative_path: str) -> None:
        self._relative_path = relative_path
        self._scope: list[str] = []
        self.usages: dict[tuple[str, str, str], int] = {}

    def _qualified_symbol(self) -> str:
        return ".".join(self._scope) if self._scope else "<module>"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Attribute(self, node: ast.Attribute) -> None:
        model = _base_name(node.value)
        if node.attr == "unscoped" and model in _TRACKED_MODELS:
            key = (self._relative_path, self._qualified_symbol(), model)
            self.usages[key] = self.usages.get(key, 0) + 1
        self.generic_visit(node)


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


def _discover_unscoped_usages() -> dict[tuple[str, str, str], int]:
    """Map ``(relative_path, enclosing_symbol, model) -> occurrence count``."""
    discovered: dict[tuple[str, str, str], int] = {}
    for path in _iter_production_files():
        relative_path = (
            f"{_RELATIVE_PATH_PREFIX}/{path.relative_to(_BACKEND_ROOT).as_posix()}"
        )
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        visitor = _UnscopedReaderVisitor(relative_path)
        visitor.visit(tree)
        for key, count in visitor.usages.items():
            discovered[key] = discovered.get(key, 0) + count
    return discovered


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unscoped_readers_match_the_reviewed_allowlist() -> None:
    """Every production ``ApiKey``/``UserRole`` ``.unscoped`` reader is reviewed.

    Fails when a reader is added (new key or extra occurrence), removed, or when
    a ``UserRole.unscoped`` reader reappears in production — each of which must
    be a deliberate, reviewed change to :data:`_UNSCOPED_ALLOWLIST`.
    """
    discovered = _discover_unscoped_usages()
    allowlist = _UNSCOPED_ALLOWLIST

    unknown = sorted(set(discovered) - set(allowlist))
    assert not unknown, (
        "NEW unreviewed `.unscoped` reader(s) of ApiKey/UserRole in production "
        "code:\n"
        + "\n".join(
            f"  - {model}.unscoped in {relative_path}::{symbol} "
            f"({discovered[(relative_path, symbol, model)]} access(es))"
            for relative_path, symbol, model in unknown
        )
        + "\n\nUnder RLS_PREAUTH_ENFORCED=on an unscoped reader without a tenant "
        "context is silently emptied. Remove the `.unscoped` usage (route it "
        "through the SECURITY DEFINER function or arm the tenant context), or "
        "add a justified entry for it to _UNSCOPED_ALLOWLIST and document it in "
        "docs/audit/2026-10/1136-r3-unscoped-inventory.md."
    )

    stale = sorted(set(allowlist) - set(discovered))
    assert not stale, (
        "Stale _UNSCOPED_ALLOWLIST entr(y/ies) — the reader is gone:\n"
        + "\n".join(
            f"  - {model}.unscoped in {relative_path}::{symbol}"
            for relative_path, symbol, model in stale
        )
        + "\n\nRemove the stale allowlist entry and its row in "
        "docs/audit/2026-10/1136-r3-unscoped-inventory.md."
    )

    count_mismatch = sorted(
        (key, allowlist[key][0], discovered[key])
        for key in set(allowlist) & set(discovered)
        if allowlist[key][0] != discovered[key]
    )
    assert not count_mismatch, (
        "`.unscoped` access count changed inside an allowlisted symbol:\n"
        + "\n".join(
            f"  - {model}.unscoped in {relative_path}::{symbol}: "
            f"expected {expected}, found {actual}"
            for (relative_path, symbol, model), expected, actual in count_mismatch
        )
        + "\n\nA second access inside an already-reviewed symbol is still a new "
        "reader: review it and update _UNSCOPED_ALLOWLIST and the inventory doc."
    )


def test_inventory_document_exists_and_covers_every_allowlisted_path() -> None:
    """The R-3 inventory doc exists and names every allowlisted production path.

    Keeps the human-readable inventory (issue #1184, deliverable 1) and this
    machine guard in sync: an allowlist entry whose path is not documented is a
    documentation gap, not a green guard.
    """
    inventory_doc = _inventory_doc_path()
    assert inventory_doc.is_file(), (
        f"R-3 inventory document is missing. Looked for {_INVENTORY_DOC_RELPATH!r} "
        f"under: {[root.as_posix() for root in _DOCS_ROOTS]}. It is the documented "
        "half of issue #1184 (residual R-3)."
    )

    text = inventory_doc.read_text(encoding="utf-8")
    missing = sorted(
        relative_path
        for relative_path in {key[0] for key in _UNSCOPED_ALLOWLIST}
        if relative_path not in text
    )
    assert not missing, (
        "Inventory document does not mention allowlisted path(s):\n"
        + "\n".join(f"  - {path}" for path in missing)
        + f"\n\nAdd a row/entry for each path to {inventory_doc.as_posix()}."
    )
