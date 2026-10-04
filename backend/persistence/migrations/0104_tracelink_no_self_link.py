# DATA-05 (audit-review 2026-09, findings 157 and 182):
# enforce non-self-link at the DB level and make an empty link_type impossible.
#
# Schema changes only:
#   * ck_tracelink_no_self_link      -> source_id <> target_id
#   * ck_tracelink_link_type_nonempty -> link_type <> ''
#
# Deliberate deviation from the plan's ``link_type DB-seitig eingeschränkt
# (CHECK/Enum/FK)`` wording: link types are a *tenant-extensible* catalog
# (``WorkspaceLinkTypeDefinition.key`` is a free string), so whitelisting the
# built-in keys in a CHECK would break every tenant extension, and a cross-table
# FK/CHECK to the catalog is not expressible in PostgreSQL. The safe equivalent
# implemented here is the non-empty invariant; catalog/pair semantics remain in
# ``link_types.catalog.validate_link_pair`` at the application layer. See the
# TraceLink model constraints for the full rationale.
#
# Rollback: ``RemoveConstraint`` is generated automatically for both additions.
# The data guard below only *reads*; it never deletes rows, so a failing
# migration leaves the database untouched and the reverse is a clean no-op.

from django.db import migrations, models


def assert_no_invalid_rows(apps, schema_editor):
    """Refuse to add the CHECKs while existing rows would violate them.

    Reads only. If any self-link or empty ``link_type`` exists, the migration
    aborts with the offending ids so an operator can decide how to clean the
    data — rather than silently deleting rows (0049-style) or adding a
    constraint that would fail on the next write.
    """
    TraceLink = apps.get_model("persistence", "TraceLink")

    self_links = list(
        TraceLink.objects.filter(source_id=models.F("target_id")).values_list(
            "id", flat=True
        )[:20]
    )
    empty_types = list(
        TraceLink.objects.filter(link_type="").values_list("id", flat=True)[:20]
    )

    if self_links or empty_types:
        raise RuntimeError(
            "DATA-05 migration aborted: existing pl_tracelink rows violate the "
            f"new constraints (self-links: {self_links}; empty link_type: "
            f"{empty_types}). Clean these rows, then re-run migrate."
        )


def noop_reverse(apps, schema_editor):
    """Nothing to undo — ``assert_no_invalid_rows`` does not write."""


class Migration(migrations.Migration):

    dependencies = [
        ('auth_tenancy', '0015_alter_apikey_scope'),
        ('persistence', '0103_goal_uq_goal_lineage_sequence'),
    ]

    operations = [
        migrations.RunPython(assert_no_invalid_rows, noop_reverse),
        migrations.AddConstraint(
            model_name='tracelink',
            constraint=models.CheckConstraint(condition=models.Q(('source', models.F('target')), _negated=True), name='ck_tracelink_no_self_link'),
        ),
        migrations.AddConstraint(
            model_name='tracelink',
            constraint=models.CheckConstraint(condition=models.Q(('link_type', ''), _negated=True), name='ck_tracelink_link_type_nonempty'),
        ),
    ]
