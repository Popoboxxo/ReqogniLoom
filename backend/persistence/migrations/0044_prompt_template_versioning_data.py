# Phase 4 — PromptTemplate versioning, part 2/3: data migration.
#
# For every existing tenant singleton row (3 slot values on it), create 3 new
# rows in the new shape (name=<old slot name>, content=<old field value>,
# version=1, is_active=True, workspace_id=None), preserving each tenant's
# actual customized content exactly, then delete the old singleton row.
#
# Idempotent: skips a (tenant, workspace_id=None, name) combination that
# already exists before inserting, so a re-run after a partial failure is
# safe.
#
# Reverse is intentionally a no-op (irreversible) — see 0043's module
# docstring rationale, mirrored from 0027_add_prompt_template.py's
# ``_unseed_defaults`` (also a lossy delete-all on reverse, not a
# reconstruction).
from django.db import migrations


_OLD_SLOT_NAMES = (
    "need_to_sysreq",
    "sysreq_to_arch_assign",
    "sysreq_decompose_next_level",
)


def _split_singleton_rows(apps, schema_editor):
    """Turn each tenant's old 3-slot singleton row into 3 named v1 rows."""
    PromptTemplate = apps.get_model("persistence", "PromptTemplate")

    for old_row in PromptTemplate.objects.all():
        for slot_name in _OLD_SLOT_NAMES:
            content = getattr(old_row, slot_name, None)
            if content is None:
                continue
            already_exists = (
                PromptTemplate.objects.filter(
                    tenant_id=old_row.tenant_id,
                    workspace_id=None,
                    name=slot_name,
                )
                .exclude(pk=old_row.pk)
                .exists()
            )
            if already_exists:
                continue
            PromptTemplate.objects.create(
                tenant_id=old_row.tenant_id,
                workspace_id=None,
                name=slot_name,
                content=content,
                version=1,
                is_active=True,
            )
        old_row.delete()


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0043_prompt_template_versioning_schema"),
    ]

    operations = [
        migrations.RunPython(_split_singleton_rows, _noop_reverse),
    ]
