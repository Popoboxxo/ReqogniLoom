"""Data-migration test for 0063_migrate_need_to_sysreq_n_placeholder.py.

Final-review finding #2 (prompt-variable-catalog branch): migration 0027
seeded ``need_to_sysreq`` PromptTemplate rows with the legacy ``{n}``
placeholder; Task 12 changed only the factory-default *constant*
(``persistence.models.DEFAULT_NEED_TO_SYSREQ``) to
``{max_requirements_per_need}``, leaving any row already persisted in the DB
on the old placeholder. This exercises the migration's pure
``_migrate_n_placeholder`` function directly (imported via ``importlib`` since
the migration module's filename starts with a digit and is not a valid dotted
import path), mirroring the precedent set by
``persistence/tests/test_prompt_template_migration.py`` for 0044 and
``workflow/tests/test_status_migration.py`` for a pure migration helper.
"""
from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps as django_apps

from persistence.models import PromptTemplate, Tenant
from persistence.tenancy import TenantContext

_mig = import_module("persistence.migrations.0063_migrate_need_to_sysreq_n_placeholder")
_migrate_n_placeholder = _mig._migrate_n_placeholder

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    t = Tenant.objects.create(name="Mig 0063 Tenant", slug="mig-0063-tenant")
    TenantContext.set_tenant(t.id)
    try:
        yield t
    finally:
        TenantContext.clear_tenant()


def test_replaces_the_legacy_placeholder_and_preserves_the_rest_of_the_content(tenant):
    """The {n} placeholder is replaced everywhere it occurs; unrelated
    admin-authored text around it (including a second occurrence) survives
    byte-for-byte — this must be a targeted string replace, not a wholesale
    overwrite with the new factory default."""
    row = PromptTemplate.objects.create(
        tenant=tenant,
        name="need_to_sysreq",
        content=(
            "Given the following stakeholder need, generate {n} system-level "
            "requirements. [Admin note: never exceed {n} items, ask Dana first.]"
        ),
        version=1,
        is_active=True,
    )

    _migrate_n_placeholder(django_apps, None)

    row.refresh_from_db()
    assert row.content == (
        "Given the following stakeholder need, generate "
        "{max_requirements_per_need} system-level requirements. [Admin note: "
        "never exceed {max_requirements_per_need} items, ask Dana first.]"
    )


def test_leaves_a_row_without_the_legacy_placeholder_untouched(tenant):
    row = PromptTemplate.objects.create(
        tenant=tenant,
        name="need_to_sysreq",
        content="Already on the new placeholder: {max_requirements_per_need}.",
        version=1,
        is_active=True,
    )

    _migrate_n_placeholder(django_apps, None)

    row.refresh_from_db()
    assert row.content == "Already on the new placeholder: {max_requirements_per_need}."


def test_leaves_other_slot_names_and_inactive_rows_untouched(tenant):
    """Only active ``need_to_sysreq`` rows are in scope: an inactive
    (superseded) ``need_to_sysreq`` version and an active row of a different
    slot name that happens to also contain ``{n}`` are both left alone."""
    other_active_version = PromptTemplate.objects.create(
        tenant=tenant,
        name="need_to_sysreq",
        content="current active version, no legacy placeholder here",
        version=2,
        is_active=True,
    )
    inactive_row = PromptTemplate.objects.create(
        tenant=tenant,
        name="need_to_sysreq",
        content="superseded v1 body with {n} in it",
        version=1,
        is_active=False,
    )
    unrelated_slot = PromptTemplate.objects.create(
        tenant=tenant,
        name="sysreq_to_arch_assign",
        content="a different slot that also happens to contain {n} literally",
        version=1,
        is_active=True,
    )

    _migrate_n_placeholder(django_apps, None)

    inactive_row.refresh_from_db()
    unrelated_slot.refresh_from_db()
    other_active_version.refresh_from_db()
    assert inactive_row.content == "superseded v1 body with {n} in it"
    assert (
        unrelated_slot.content
        == "a different slot that also happens to contain {n} literally"
    )
    assert other_active_version.content == "current active version, no legacy placeholder here"
