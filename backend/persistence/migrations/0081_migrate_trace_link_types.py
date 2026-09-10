"""Hard migration of every TraceLink row to the new eight-type catalog.

Spec section 6, step 2. Runs after the schema migration that added
``Artifact.copied_from`` (``persistence/0080``) and after the link-type catalog
migrations, because ``check_link_pair`` starts rejecting the legacy types the
moment the catalog exists and the service is wired up.

Ends with a post-condition (``verify_migrated_links``): every surviving row
must still be creatable under the new catalog, or the migration raises and
rolls back. Because it is irreversible, a row that slipped through would be
permanently uncreatable rather than merely wrong.

Irreversible on purpose: the endpoint swap on ``satisfies``/``implements``
loses the information about which of the two a row used to be, so a faithful
reverse does not exist. Take a backup before deploying, and run
``manage.py check_copy_of_conflicts`` first to see which artifacts will lose
1:1 copy provenance.

RLS: every table this touches carries ``FORCE ROW LEVEL SECURITY``, which not
even the owner role is exempt from. ``SET LOCAL row_security = off`` turns a
blinded connection into a hard error instead of a migration that reports
success after rewriting nothing (the same guard ``persistence/0073``,
``0074`` and ``0078`` establish).

Deploy note — runtime and throughput
------------------------------------
This rewrites ``pl_tracelink`` row by row in Python inside a single
``atomic = True`` transaction. That is deliberate (an all-or-nothing rewrite
with a working rollback), but it means the whole table is locked for writes
for the duration and the cost scales linearly with the number of *rewritten*
rows.

Measured on this branch, against a ``seed_demo`` + ``seed_toothbrush`` database
(1974 ``TraceLink`` rows, PostgreSQL 16 in the project's own compose stack):

* 935 rows rewritten (``refines`` -> ``derives-from``, ``documents`` ->
  ``references``) in **1.30 s** — roughly **700 rewritten rows/second**, i.e.
  ~40 000 rows/minute. The per-row ``save()`` dominates.
* the ``verify_migrated_links`` post-condition pass over all 1974 surviving
  rows took **0.007 s** — it is a bulk read and is not the bottleneck.

At a few thousand rows this completes in well under a minute. For a
production ``TraceLink`` table in the six-figure-row range, budget on the
order of a minute per 40 000 rows that actually need rewriting, run it in a
maintenance window, and get the expected duration first by counting the
affected rows:

.. code-block:: sql

    SELECT link_type, count(*) FROM pl_tracelink
     WHERE link_type IN ('parent-child', 'satisfies', 'implements', 'refines',
                         'realizes', 'documents', 'traces', 'uses-term',
                         'copy-of')
     GROUP BY 1;

``manage.py check_copy_of_conflicts`` covers the ``copy-of`` half separately.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently migrating nothing under RLS."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def migrate_link_types(apps, schema_editor):
    from link_types.migration_ops import (
        migrate_copy_of_links,
        migrate_parent_child_links,
        migrate_renamed_links,
        verify_migrated_links,
    )

    _require_full_row_visibility(schema_editor)

    Artifact = apps.get_model("persistence", "Artifact")
    TraceLink = apps.get_model("persistence", "TraceLink")

    moved, downgraded = migrate_copy_of_links(Artifact, TraceLink)
    converted, deduplicated = migrate_parent_child_links(TraceLink)
    renamed = migrate_renamed_links(TraceLink)
    # Post-condition, not a formality: the rename is mechanical and can produce
    # an endpoint pair the new catalog does not allow. Raises, which rolls the
    # whole rewrite back (see the class comment) — the same guarantee-by-error
    # pattern persistence/0078 uses for its history copy.
    verified = verify_migrated_links(TraceLink)

    logger.info(
        "TraceLink type migration complete: copy-of moved=%d downgraded=%d, "
        "parent-child converted=%d deduplicated=%d, renamed=%s, verified=%d",
        moved,
        downgraded,
        converted,
        deduplicated,
        renamed,
        verified,
    )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a failure rolls the whole rewrite
    # back rather than leaving half the graph on the old catalog.
    atomic = True

    dependencies = [
        # Adds Artifact.copied_from, the destination of the copy-of links.
        ("persistence", "0080_tracelink_semantics_fields"),
        # The catalog leaf: the built-in types plus the grandfathered and
        # Goal/reference pairs the migrated rows have to be creatable under.
        ("link_types", "0005_backfill_goal_reference_pairs"),
    ]

    operations = [
        migrations.RunPython(migrate_link_types, migrations.RunPython.noop),
    ]
