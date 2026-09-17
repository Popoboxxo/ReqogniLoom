"""``persistence/0081`` against the real-world rows of issue #893.

``link_types/tests/test_migration_ops.py`` covers the individual steps. This
covers the migration function itself — the thing a ``migrate`` container runs —
because the bug it reproduces was not in any single step but in what the last
one (``verify_migrated_links``) refuses: a QA database upgraded from beta.6 to
beta.7 carried two ``TraceLink`` triples that neither seeder writes, so the
migration raised, rolled back to 0080, and took the whole stack's start-up with
it.
"""
from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from persistence.tenancy import TenantContext

#: Cannot be imported with a plain ``import`` — the module name starts with a
#: digit.
_migration = importlib.import_module(
    "persistence.migrations.0081_migrate_trace_link_types"
)


class _SchemaEditor:
    """Minimal stand-in for the ``schema_editor`` a ``RunPython`` receives."""

    connection = connection


class _Apps:
    """Stand-in for the historical ``apps`` a ``RunPython`` receives.

    Historical models carry a plain manager; the live ones default to the
    tenant-scoped manager, which raises without a thread-local tenant. Mapping
    ``objects`` onto ``unscoped`` reproduces what the migration actually sees —
    an unfiltered queryset whose isolation comes from RLS alone.
    """

    @staticmethod
    def get_model(app_label: str, model_name: str):
        model = django_apps.get_model(app_label, model_name)
        return SimpleNamespace(objects=getattr(model, "unscoped", model.objects))


@pytest.fixture
def legacy_rows(db):
    """The two triples of issue #893, as they existed on the QA database."""
    from persistence.models import Artifact, Tenant, TraceLink, Workspace

    tenant = Tenant.objects.create(name="issue-893", slug=f"issue-893-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=kind
        )

    req_a, req_b = artifact("Requirement"), artifact("Requirement")
    risk, req_c = artifact("Risk"), artifact("Requirement")
    # 1. `traces` Requirement -> Requirement: renames into `references`
    #    Requirement -> Requirement, which no built-in pair allows.
    # 2. `verifies` Risk -> Requirement: no rename mapping at all, so it used
    #    to survive as `verifies` from a Risk, which no built-in pair allows.
    TraceLink.objects.create(
        tenant=tenant, source=req_a, target=req_b, link_type="traces"
    )
    TraceLink.objects.create(
        tenant=tenant, source=risk, target=req_c, link_type="verifies"
    )

    TenantContext.clear_tenant()
    yield SimpleNamespace(
        tenant=tenant,
        req_a=req_a,
        req_b=req_b,
        risk=risk,
        req_c=req_c,
        TraceLink=TraceLink,
    )
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_the_migration_completes_on_the_issue_893_rows(legacy_rows):
    """It raised RuntimeError here before the fix; both rows must survive."""
    _migration.migrate_link_types(_Apps(), _SchemaEditor())

    TenantContext.set_tenant(legacy_rows.tenant.id)
    rows = {
        (link_type, source, target)
        for link_type, source, target in legacy_rows.TraceLink.objects.values_list(
            "link_type", "source_id", "target_id"
        )
    }
    assert rows == {
        # grandfathered: a legacy `traces` carries no direction semantics, so
        # it is tolerated as a reference rather than re-typed into a claim.
        ("references", legacy_rows.req_a.id, legacy_rows.req_b.id),
        # re-typed: `mitigates` Risk -> Requirement is a built-in pair that
        # means what the row meant, so it is not grandfathered.
        ("mitigates", legacy_rows.risk.id, legacy_rows.req_c.id),
    }


@pytest.mark.django_db
def test_an_uncovered_triple_still_rolls_the_migration_back(legacy_rows):
    """The fix widens the allowlist; it must not disarm the post-condition."""
    from persistence.models import Artifact, TraceLink

    TenantContext.set_tenant(legacy_rows.tenant.id)
    stray = Artifact.objects.create(
        tenant=legacy_rows.tenant,
        workspace=legacy_rows.req_a.workspace,
        artifact_type="Requirement",
    )
    TraceLink.objects.create(
        tenant=legacy_rows.tenant,
        source=stray,
        target=legacy_rows.req_a,
        link_type="satisfies",
    )
    TenantContext.clear_tenant()

    with pytest.raises(RuntimeError, match="allocated-to"):
        _migration.migrate_link_types(_Apps(), _SchemaEditor())
