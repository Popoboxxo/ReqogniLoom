# Generated for issue #123.
#
# Context: migration 0020 removed 'StReq' from Requirement.type choices (and
# dropped Requirement.moscow_priority) without a RunPython data migration.
# Django `choices` are app-level validation only, not a DB constraint, so a
# pre-existing row with type='StReq' would have silently survived with an
# invalid value and no longer been reachable by current app code.
#
# Verified against the current database (2026-07-29): 0 Requirement rows
# with type outside {SyReq, UseCase, FeatureReq} exist, and the audit log is
# empty, so no historical moscow_priority values are recoverable and no
# orphaned StReq rows need backfilling here. This migration adds a DB-level
# CHECK constraint so the invariant is enforced going forward and this class
# of silent-drift bug cannot recur for future SE-mask splits.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0049_tracelink_unique_edge"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="requirement",
            # ``condition=`` (not ``check=``): renamed in Django 5.1, the old
            # spelling warns under 5.2 and is removed in 6.0. Behaviour-neutral
            # for this historical migration — since 5.1 both kwargs populate the
            # same ``condition`` attribute and deconstruct identically, so the
            # recorded state and the generated CHECK SQL are unchanged.
            constraint=models.CheckConstraint(
                condition=models.Q(type__in=["SyReq", "UseCase", "FeatureReq"]),
                name="ck_requirement_type_valid",
            ),
        ),
    ]
