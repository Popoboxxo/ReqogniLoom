"""Preflight for the copy-of -> Artifact.copied_from migration.

``copied_from`` is 1:1; a ``copy-of`` link was N:M. An artifact with more than
one ``copy-of`` link therefore cannot be represented faithfully and has to be
looked at before the migration runs (spec section 7). The migration itself
resolves conflicts by "newest wins, the rest survive as references" — this
command exists so the decision is seen rather than discovered afterwards.

Like ``inventory_link_types``, this is a whole-database report, not a
per-tenant one: it reads through the ``unscoped`` managers inside a
``SET LOCAL row_security = off`` transaction so an RLS-blinded connection
(the least-privilege app role) fails loudly instead of reporting a reassuring
"no conflicts" it never had the rows to see.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from link_types.migration_ops import find_copy_of_conflicts


class Command(BaseCommand):
    help = "List artifacts carrying more than one copy-of TraceLink."

    def handle(self, *args, **options):
        from persistence.models import Artifact, TraceLink

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL row_security = off")
            # find_copy_of_conflicts reads ``.objects``, which is the historical
            # (unscoped) manager under a migration but the tenant-filtered one
            # here. Hand it the unscoped manager under that name.
            conflicts = find_copy_of_conflicts(
                SimpleNamespace(objects=TraceLink.unscoped)
            )
            types = dict(
                Artifact.unscoped.filter(id__in=conflicts).values_list(
                    "id", "artifact_type"
                )
            )

        if not conflicts:
            self.stdout.write(
                self.style.SUCCESS("No copy-of conflicts: every source has at most one.")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"{len(conflicts)} artifact(s) have multiple copy-of links:")
        )
        for source_id, link_ids in conflicts.items():
            # Artifact has no title column — the title lives on the typed
            # sibling row, which this generic report deliberately does not join.
            self.stdout.write(
                f"  {source_id} [{types.get(source_id, '(missing)')}]: "
                f"{len(link_ids)} links"
            )
        self.stdout.write(
            "\nMigration policy: newest link wins and becomes copied_from; "
            "the others are preserved as 'references' links."
        )
