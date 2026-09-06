"""Drop the per-entity `lifecycle_status` mirror columns (Datenmodell-
Konsolidierung Phase 4, Task 24, spec §5).

`Artifact.lifecycle_status` (0074) is the single soft-delete flag now, and
every reader (GlossaryTermSerializer/GlossaryTermDTO, `baseline.state_capture`,
`ExportService`/`ImportService`'s CSV round-trip) was switched over to it in
this same task. No data migration is needed here: `outdate()`/`reactivate()`
have written the Artifact flag exclusively since 0074's backfill, so the
per-entity columns hold nothing that isn't already on the Artifact.

Pure schema cleanup: 3 composite tenant+lifecycle_status indexes
(StakeholderNeed/Requirement/ArchitectureElement had one each; GlossaryTerm
never did) plus the 4 `lifecycle_status` columns themselves.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0074_artifact_lifecycle_status'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='architectureelement',
            name='idx_archelem_tnt_lifecyc',
        ),
        migrations.RemoveIndex(
            model_name='requirement',
            name='idx_req_tnt_lifecycle',
        ),
        migrations.RemoveIndex(
            model_name='stakeholderneed',
            name='idx_sn_tnt_lifecycle',
        ),
        migrations.RemoveField(
            model_name='glossaryterm',
            name='lifecycle_status',
        ),
        migrations.RemoveField(
            model_name='architectureelement',
            name='lifecycle_status',
        ),
        migrations.RemoveField(
            model_name='requirement',
            name='lifecycle_status',
        ),
        migrations.RemoveField(
            model_name='stakeholderneed',
            name='lifecycle_status',
        ),
    ]
