"""Issue #276, finding 1 — machine-seeded LlmSettings rows must not shadow ``.env``.

``0026_add_llm_settings`` used to seed a ``provider="mock"`` row for every
tenant that existed when it was applied. ``llm_adapter.providers.
_apply_db_settings`` gives an existing row unconditional precedence over the
environment, so from then on the deployment's ``LLM_PROVIDER`` was silently
ignored and every AI feature returned mock placeholders — with no error
anywhere.

The fix restores the documented "env is the fallback" architecture by making
row *existence* mean "an admin explicitly configured this tenant":

  * 0026 no longer seeds anything (guarded by
    :func:`test_migration_0026_does_not_seed_rows`);
  * 0056 removes the rows the old seed left behind on existing deployments,
    but only the pristine ones — a row an admin actually touched is kept.

The 0056 data function is imported directly from the migration file (its
module name starts with a digit, so it cannot be reached via a dotted import)
and called against the real model, mirroring
``test_prompt_template_migration.py``. That keeps the pristine-row predicate
— the risky part of the migration — under test without re-running schema
migrations.
"""
from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest
from django.db import migrations

from persistence.models import LlmSettings, Tenant
from persistence.tests.conftest import active_tenant

_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "migrations"


def _load_migration(name: str):
    """Load a migration module by file name (digit-prefixed → importlib)."""
    spec = importlib.util.spec_from_file_location(
        f"_{name}_under_test", _MIGRATIONS_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fake_apps() -> SimpleNamespace:
    """Stand in for the migration's ``apps`` registry.

    The historical model 0026 recorded uses plain (non tenant-scoped) managers,
    so the migration's ``LlmSettings.objects`` sees every row. The real model's
    ``objects`` manager is tenant-scoped, hence ``unscoped`` here — the tests
    below still activate a tenant context so Row-Level Security lets the rows
    through.
    """
    proxy = SimpleNamespace(objects=LlmSettings.unscoped)
    return SimpleNamespace(get_model=lambda *_args, **_kwargs: proxy)


def _run_unseed() -> None:
    module = _load_migration("0056_unseed_default_llm_settings")
    module.remove_seeded_default_rows(_fake_apps(), None)


# ---------------------------------------------------------------------------
# 0026 must not seed
# ---------------------------------------------------------------------------


def test_migration_0026_does_not_seed_rows() -> None:
    """0026 must contain no data step — a fresh install starts row-free."""
    module = _load_migration("0026_add_llm_settings")

    run_python_ops = [
        op
        for op in module.Migration.operations
        if isinstance(op, migrations.RunPython)
    ]

    assert run_python_ops == [], (
        "0026 must not seed LlmSettings rows: a machine-created row takes "
        "unconditional precedence over LLM_PROVIDER (issue #276)."
    )


# ---------------------------------------------------------------------------
# 0056 removes only pristine rows
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unseed_removes_pristine_mock_row(tenant: Tenant) -> None:
    """A row identical to the old seed default is removed."""
    with active_tenant(tenant):
        LlmSettings.objects.create(tenant=tenant, provider="mock")

        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_unseed_keeps_row_with_non_mock_provider(tenant: Tenant) -> None:
    """An admin-selected provider is real configuration — never delete it."""
    with active_tenant(tenant):
        LlmSettings.objects.create(tenant=tenant, provider="anthropic")

        _run_unseed()

        assert LlmSettings.objects.get(tenant=tenant).provider == "anthropic"


@pytest.mark.django_db
def test_unseed_keeps_mock_row_with_api_key(tenant: Tenant) -> None:
    """provider=mock plus a stored credential means the row was configured."""
    with active_tenant(tenant):
        LlmSettings.objects.create(
            tenant=tenant, provider="mock", api_key="sk-user-set"
        )

        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_unseed_keeps_mock_row_with_model_name(tenant: Tenant) -> None:
    """Any non-default field marks the row as touched by a human."""
    with active_tenant(tenant):
        LlmSettings.objects.create(
            tenant=tenant, provider="mock", model_name="llama3.1"
        )

        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_unseed_keeps_mock_row_with_base_url(tenant: Tenant) -> None:
    """Same for a configured base_url."""
    with active_tenant(tenant):
        LlmSettings.objects.create(
            tenant=tenant, provider="mock", base_url="http://localhost:11434"
        )

        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_unseed_keeps_mock_row_with_bumped_version(tenant: Tenant) -> None:
    """version > 1 means the row was written again after its creation."""
    with active_tenant(tenant):
        LlmSettings.objects.create(tenant=tenant, provider="mock", version=2)

        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_unseed_is_idempotent(tenant: Tenant) -> None:
    """Re-running the migration on an already-cleaned database is a no-op."""
    with active_tenant(tenant):
        LlmSettings.objects.create(tenant=tenant, provider="mock")

        _run_unseed()
        _run_unseed()

        assert LlmSettings.objects.filter(tenant=tenant).count() == 0
