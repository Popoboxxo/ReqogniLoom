"""P2: seed the default tier ladder for every workspace and map legacy levels.

Each workspace gets the four default positions (``erste``, ``dazwischen``,
``vorletzte``, ``letzte``). Existing ``Requirement.level`` 1..4 is mapped onto
them so no requirement loses its published infrastructure; NULL stays NULL
(unresolved) and is filled by the backfill command, not guessed here.
"""
from __future__ import annotations

from django.db import migrations

_SEED = (
    ("erste", {"de": "Erste", "en": "First"}, "first", None),
    ("dazwischen", {"de": "Dazwischen", "en": "Middle"}, "middle", None),
    ("vorletzte", {"de": "Vorletzte", "en": "Second to last"}, "from_end", 1),
    ("letzte", {"de": "Letzte", "en": "Last"}, "from_end", 0),
)

_LEVEL_TO_KEY = {
    1: "erste",
    2: "dazwischen",
    3: "vorletzte",
    4: "letzte",
}


def _seed_tiers(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkspaceTier = apps.get_model("persistence", "WorkspaceTier")
    Requirement = apps.get_model("persistence", "Requirement")
    alias = schema_editor.connection.alias

    for workspace in Workspace.objects.using(alias).all().only("id", "tenant_id"):
        for position, (tier_key, name, rule, from_end) in enumerate(_SEED):
            WorkspaceTier.objects.using(alias).get_or_create(
                workspace_id=workspace.id,
                tier_key=tier_key,
                defaults={
                    "tenant_id": workspace.tenant_id,
                    "name": name,
                    "position": position,
                    "rule": rule,
                    "from_end": from_end,
                },
            )

    for level, tier_key in _LEVEL_TO_KEY.items():
        Requirement.objects.using(alias).filter(
            level=level, tier_key__isnull=True
        ).update(tier_key=tier_key)


def _unseed_tiers(apps, schema_editor):
    WorkspaceTier = apps.get_model("persistence", "WorkspaceTier")
    Requirement = apps.get_model("persistence", "Requirement")
    alias = schema_editor.connection.alias
    Requirement.objects.using(alias).update(tier_key=None)
    WorkspaceTier.objects.using(alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0134_allocation_intent_tier_ladder"),
    ]

    operations = [
        migrations.RunPython(_seed_tiers, _unseed_tiers),
    ]
