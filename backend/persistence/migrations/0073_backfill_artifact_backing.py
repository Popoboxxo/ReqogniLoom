"""Create one Artifact row per unbacked Diagram/Icd/GlossaryTerm/ChangeRequest.

Datenmodell-Konsolidierung Phase 3, spec section 4.2 (Milestone M3). Task 19
wired ``ensure_artifact()`` into the four CREATE paths, so every *new* row is
Artifact-backed from birth; this migration closes the gap for every row that
predates that commit.

Rows whose workspace is NULL cannot be backed (``Artifact.workspace`` is a
non-nullable FK) and are left as-is; ``manage.py check_artifact_backing``
reports them as skipped, never as failures.

Runs against the historical model registry, so it deliberately does **not**
import ``persistence.artifact_backing.ensure_artifact``: that helper resolves
the row lock through the live ``TenantManager`` (``type(entity).objects``),
which requires an ambient ``TenantContext`` that no migration has. The
historical registry hands out plain ``django.db.models.Manager`` instances
instead, which is exactly the unscoped, cross-tenant access a backfill needs.

Idempotent by construction: only rows matching ``artifact IS NULL`` are
touched, so a re-run (e.g. after an interrupted deploy) is a no-op and can
never create a second Artifact for the same row.
"""
from django.db import migrations
from django.db.models import Count

#: (app_label, model_name, Artifact.artifact_type value)
TARGETS = [
    ("diagram", "Diagram", "Diagram"),
    ("icd", "Icd", "Icd"),
    ("persistence", "GlossaryTerm", "GlossaryTerm"),
    ("persistence", "ChangeRequest", "ChangeRequest"),
]


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently backfilling nothing under RLS.

    Every target table has ``FORCE ROW LEVEL SECURITY`` with a policy keyed on
    the ``app.current_tenant`` session GUC, which no migration sets. FORCE
    means even the table *owner* is subject to the policy, so a migration run
    as anything other than a superuser / ``BYPASSRLS`` role reads an **empty**
    table and reports ``OK`` after changing nothing — the exact silent no-op
    that cost a previous backfill (#103) a debugging session.

    ``row_security = off`` inverts that failure mode: Postgres raises
    "query would be affected by row-level security policy" rather than
    quietly filtering rows away. For a superuser / ``BYPASSRLS`` connection no
    policy is ever applied, so the setting is a no-op and the backfill sees
    every tenant's rows.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def backfill(apps_registry, schema_editor):
    """Give every workspace-owning, unbacked target row its Artifact."""
    _require_full_row_visibility(schema_editor)

    Artifact = apps_registry.get_model("persistence", "Artifact")
    for app_label, model_name, artifact_type in TARGETS:
        model = apps_registry.get_model(app_label, model_name)
        # ``workspace_id`` is the attname for GlossaryTerm's ``workspace`` FK
        # and the field name for the plain UUIDField the other three use, so a
        # single attribute access covers both shapes.
        for row in model.objects.filter(artifact__isnull=True).iterator():
            if row.workspace_id is None:
                continue
            artifact = Artifact.objects.create(
                artifact_type=artifact_type,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
            )
            model.objects.filter(pk=row.pk).update(artifact=artifact)


def verify(apps_registry, schema_editor):
    """Fail the migration if the result violates the one-Artifact invariant."""
    _require_full_row_visibility(schema_editor)

    for app_label, model_name, _artifact_type in TARGETS:
        model = apps_registry.get_model(app_label, model_name)
        leftover = (
            model.objects.filter(artifact__isnull=True)
            .exclude(workspace_id__isnull=True)
            .count()
        )
        if leftover:
            raise RuntimeError(
                f"{model_name}: {leftover} backable rows are still unbacked."
            )
        shared = (
            model.objects.exclude(artifact__isnull=True)
            .values("artifact_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        if shared:
            raise RuntimeError(
                f"{model_name}: {shared} Artifact rows are shared by two rows."
            )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError from ``verify``
    # rolls the whole backfill back rather than leaving it half-applied.
    atomic = True

    dependencies = [
        ("persistence", "0072_glossary_changerequest_artifact_fk"),
        ("icd", "0009_icd_artifact_fk"),
        ("diagram", "0008_diagram_rls_policies"),
    ]

    operations = [
        # Irreversible on purpose: a backfilled Artifact is indistinguishable
        # from one created afterwards by ensure_artifact(), so a reverse that
        # deleted rows would destroy live data. Unapplying is a no-op.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
