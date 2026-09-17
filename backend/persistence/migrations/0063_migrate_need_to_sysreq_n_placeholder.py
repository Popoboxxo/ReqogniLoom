# Data migration — final-review finding #2 (prompt-variable-catalog branch).
#
# 0027_add_prompt_template.py seeded PromptTemplate rows for tenants that
# existed at the time with the legacy ``{n}`` placeholder for
# ``need_to_sysreq`` (later split into named rows by 0044). This branch's
# Task 12 changed only the factory-default *constant*
# (persistence.models.DEFAULT_NEED_TO_SYSREQ) to the new
# ``{max_requirements_per_need}`` placeholder — it never touched rows already
# persisted in the DB. Any tenant whose ``need_to_sysreq`` row predates that
# change (or was manually edited to still say ``{n}``) keeps rendering a
# prompt body the resolver can never fill in ``max_requirements_per_need``
# for, silently dead-ending the feature for that tenant.
#
# String-replaces the literal ``{n}`` placeholder inside ``content`` in place
# (not a wholesale overwrite with the new factory default) so any other admin
# customization on the same row survives untouched. Reverse is intentionally
# a no-op/irreversible — same rationale as 0044's ``_noop_reverse`` (the
# original ``{n}`` text is not recoverable from the replaced content, and
# reintroducing a known-stale placeholder on reverse would be actively wrong).
from django.db import migrations

_LEGACY_PLACEHOLDER = "{n}"
_NEW_PLACEHOLDER = "{max_requirements_per_need}"


def _migrate_n_placeholder(apps, schema_editor):
    """Replace the legacy ``{n}`` placeholder in active ``need_to_sysreq`` rows.

    Scoped to ``name="need_to_sysreq"`` (the only slot that ever used ``{n}``)
    and ``is_active=True`` (inactive/superseded versions are historical
    record, not something the resolver reads) and to rows that actually
    contain the literal substring (an unconditional ``.replace()`` on rows
    that don't contain it would be a no-op anyway, but filtering first avoids
    an unnecessary write + ``modified_at`` bump on every untouched row).
    """
    PromptTemplate = apps.get_model("persistence", "PromptTemplate")

    for row in PromptTemplate.objects.filter(
        name="need_to_sysreq",
        is_active=True,
        content__contains=_LEGACY_PLACEHOLDER,
    ):
        row.content = row.content.replace(_LEGACY_PLACEHOLDER, _NEW_PLACEHOLDER)
        row.save(update_fields=["content"])


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0062_add_prompt_variable"),
    ]

    operations = [
        migrations.RunPython(_migrate_n_placeholder, _noop_reverse),
    ]
