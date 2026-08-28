"""Realign ``Requirement.level`` with the documented V-model cascade (P1-9).

SYSTEMAUDIT_2026-08-27 P1-9. ``persistence.models.RequirementLevel`` spelled a
*physical* decomposition scale (``L0_SYSTEM=0 .. L4_MATERIAL=4``) that was
offset by one from — and used different words than — the cascade every other
part of the system documents and relies on (``REQ-L0``=Stakeholder Need,
``REQ-L1``=System, ``REQ-L2``=Subsystem, ``REQ-L3``=Component,
``L4``=Presentation). The enum is now ``L1_SYSTEM=1 .. L4_PRESENTATION=4``:
the stored integer *is* the cascade level, and L0 is absent because a
Stakeholder Need is a separate model, never a ``Requirement`` row.

Why a data migration is required
--------------------------------
``IntegerChoices`` labels are not stored — only the integer is. A pure
relabelling (same integers, new names) was evaluated first and rejected: it
would have produced ``L1_SYSTEM = 0``, i.e. a member whose name contradicts its
own value, which is the exact off-by-one confusion the audit item exists to
remove. Renumbering therefore changes what existing integers *mean*, and every
non-NULL row has to move with it or it silently acquires a wrong label.

Old value (old meaning)      ->  New value (new meaning)
    0  L0 System             ->      1  L1 System
    1  L1 Subsystem          ->      2  L2 Subsystem
    2  L2 Component          ->      3  L3 Component
    3  L3 Part               ->      4  L4 Presentation   (lossy, see below)
    4  L4 Material           ->      4  L4 Presentation
    NULL                     ->      NULL  (untouched — no backfill)

i.e. ``new = min(old + 1, 4)``.

Lossy edge, deliberately accepted: the old scale had five tiers, the cascade
has four below L0, so the two bottom tiers (Part, Material) both land on L4
Presentation. Reverse therefore cannot tell them apart and maps 4 back to 3
(Part). This is accepted because rows at old 3/4 are effectively nonexistent in
practice: the only bulk writer of ``level`` is
``application/management/commands/migrate_se_docs.py``, whose ``_REQ_LEVEL_MAP``
only ever wrote 0/1/2 (and is corrected to 1/2/3 in the same change), and the
REST/MCP boundaries only started exposing the field at all with issue #409.

No backfill: rows with ``level IS NULL`` stay NULL. That mirrors migration
``0040``, which introduced the column deliberately without a backfill ("a naming
convention cannot be mapped to a level reliably without human intent"), and it
mirrors the ``lifecycle_status`` precedent. ``RequirementService.decompose`` now
derives a child level only when the parent's is known, so NULL keeps meaning
"not yet assigned" rather than becoming a guess.

Reversible: the reverse operation restores the pre-change integers (1..4 ->
0..3) and the previous ``choices``/``help_text``. The AlterField pair is
schema-neutral — Django's ``choices`` are validation-only metadata and there is
no CHECK constraint on ``level`` (``Requirement.Meta.constraints`` constrains
``type`` and ``uid``, not ``level``), so no DDL beyond the state change is
emitted.
"""
from django.db import migrations, models

#: Old integer -> new integer. ``min(old + 1, 4)``, written out so the mapping
#: is greppable and the clamped pair is visible at a glance.
_FORWARD_LEVEL_MAP = {0: 1, 1: 2, 2: 3, 3: 4, 4: 4}

#: New integer -> old integer. Not a perfect inverse: old 3 (Part) and old 4
#: (Material) both mapped to 4, so 4 comes back as 3. See module docstring.
_REVERSE_LEVEL_MAP = {1: 0, 2: 1, 3: 2, 4: 3}


def _remap(apps, mapping):
    """Apply *mapping* to every non-NULL ``Requirement.level`` in one statement.

    A single ``UPDATE ... SET level = CASE level WHEN ... END``, not one
    ``UPDATE`` per mapped value. That is a correctness requirement, not an
    optimisation: sequential per-value updates read rows this migration has
    already written, so a shifting map re-shifts its own output. Forwards
    (``+1``) survives it if the values are processed in descending order, but
    backwards (``-1``) needs the opposite order, and getting that wrong
    collapses *every* row onto the lowest value. ``CASE`` sidesteps the
    ordering question entirely — PostgreSQL evaluates it against the
    pre-``UPDATE`` row, so each row is mapped exactly once regardless of
    direction.

    ``default=F("level")`` leaves anything outside *mapping* untouched (rather
    than nulling it): ``choices`` is not DB-enforced for this column, so an
    out-of-range value is possible in principle and silently rewriting it would
    destroy the evidence.

    ``Model.objects`` on a *historical* model is a plain, unfiltered
    ``models.Manager`` — ``TenantScopedModel.objects`` (``TenantManager``) does
    not set ``use_in_migrations``, so the runtime tenant filter is not carried
    into migration state and this update is correctly cross-tenant. Same idiom
    as migration ``0063``.
    """
    Requirement = apps.get_model("persistence", "Requirement")
    Requirement.objects.filter(level__isnull=False).update(
        level=models.Case(
            *[
                models.When(level=old, then=models.Value(new))
                for old, new in sorted(mapping.items())
                if old != new
            ],
            default=models.F("level"),
            output_field=models.PositiveSmallIntegerField(),
        )
    )


def forwards(apps, schema_editor):
    _remap(apps, _FORWARD_LEVEL_MAP)


def backwards(apps, schema_editor):
    _remap(apps, _REVERSE_LEVEL_MAP)


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0066_interview_multi_mode'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='requirement',
            name='level',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[
                    (1, 'L1 System'),
                    (2, 'L2 Subsystem'),
                    (3, 'L3 Component'),
                    (4, 'L4 Presentation'),
                ],
                help_text=(
                    'K3: V-model cascade level (1=System, 2=Subsystem, '
                    '3=Component, 4=Presentation). The integer is the cascade '
                    'level itself. L0 (Stakeholder Need) is a separate model '
                    'and never a Requirement. NULL until assigned explicitly.'
                ),
            ),
        ),
    ]
