"""Regression guards for the app-role migration's duplicate handling.

The xdist race (two workers, separate test DBs, one Postgres cluster) is
stochastic; these unit tests pin the error-reading helper instead. Django
wraps psycopg2 and keeps the SQLSTATE on ``__cause__`` — reading only the
wrapper is what made the previous savepoint guard fail open into a re-raise.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0048_app_role.py"


@pytest.fixture(scope="module")
def migration_module():
    spec = spec_from_file_location("m0048_app_role", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pgcode_reads_the_wrapper(migration_module) -> None:
    exc = type("Wrapper", (Exception,), {"pgcode": "42710"})()
    assert migration_module._duplicate_role_pgcode(exc) == "42710"


def test_pgcode_falls_back_to_the_psycopg2_cause(migration_module) -> None:
    cause = type("Cause", (Exception,), {"pgcode": "23505"})()
    exc = RuntimeError("wrapped")
    exc.__cause__ = cause
    assert migration_module._duplicate_role_pgcode(exc) == "23505"


def test_pgcode_is_none_for_unrelated_errors(migration_module) -> None:
    assert migration_module._duplicate_role_pgcode(RuntimeError("boom")) is None
