"""Report the link-type/endpoint triples that actually exist in the database.

Written for OFFENE FRAGE 1 of the Traceability-Semantik plan: the eight
built-in types cover Requirement / ArchitectureElement / TestCase /
StakeholderNeed / Adr / Risk / Diagram / GlossaryTerm / Icd, but **not**
Goal, MainGoal, Issue or Interview — all four of which are live artifact
types with real links today (Goal<->Requirement links are the reason
``TraceLinkService._resolve_artifact`` gained its Goal branch in fix #237).

Flipping validation to always-on without knowing what is out there would
reject existing, legitimate data. Run this first::

    python manage.py inventory_link_types --json /tmp/link_type_inventory.json

``observed`` lists every triple after applying the section-3.1 rename and
endpoint swap; ``uncovered`` is the subset that no built-in ``allowed_pairs``
entry matches — exactly the rows that would start failing.

``blocking`` is the pre-flight (issue #893): the subset that is not creatable
even *with* ``GRANDFATHERED_PAIRS``, i.e. the triples ``verify_migrated_links``
would refuse. Run this against a not-yet-upgraded database and a non-empty
``blocking`` list means ``persistence/0081`` will roll back and take the deploy
with it. That is the difference from ``uncovered``, which is the wider,
informational set: a triple in ``uncovered`` but not in ``blocking`` is already
tolerated by the grandfathered allowlist and needs no action.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.catalog import normalize_artifact_type
from link_types.migration_ops import is_creatable, predict_migrated_triple


def collect_observed_triples() -> List[Dict[str, Any]]:
    """Return the distinct post-migration triples with their row counts.

    Every row is put through ``migration_ops.predict_migrated_triple``, the
    same rule set ``persistence/0081`` rewrites by: legacy keys are reported
    under their successor name, rows of a ``SWAPPED_LEGACY_KEYS`` type with
    source and target already exchanged, and the endpoint exceptions
    (``satisfies`` at a StakeholderNeed, ``verifies`` from a Risk) under the
    type their endpoints actually mean. So the output describes the world
    *after* the data migration, which is the world validation has to accept.

    ``copy-of`` is skipped: it does not survive as a link at all (it moves into
    ``Artifact.copied_from``; a source with more than one is reported by
    ``manage.py check_copy_of_conflicts`` instead).

    This is a whole-database inventory, not a per-tenant one — it must see
    every tenant's rows in one pass, so it queries ``TraceLink.unscoped``
    (the tenant filter is dropped) inside a ``SET LOCAL row_security = off``
    transaction, exactly like ``check_artifact_backing`` does for the same
    reason: on the least-privilege app role this makes an RLS-blinded
    connection fail loudly instead of silently reporting "0 rows, all
    covered".
    """
    from persistence.models import TraceLink

    counter: Counter = Counter()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
        rows = list(
            TraceLink.unscoped.values(
                "link_type", "source__artifact_type", "target__artifact_type"
            )
            .annotate(count=Count("id"))
            .order_by()
        )
    for row in rows:
        predicted = predict_migrated_triple(
            row["link_type"],
            normalize_artifact_type(row["source__artifact_type"]),
            normalize_artifact_type(row["target__artifact_type"]),
        )
        if predicted is None:
            continue
        counter[predicted] += row["count"]

    return [
        {
            "link_type": link_type,
            "source_type": source,
            "target_type": target,
            "count": count,
        }
        for (link_type, source, target), count in sorted(counter.items())
    ]


def _is_covered(link_type: str, source: str, target: str) -> bool:
    definition = BUILTIN_LINK_TYPES.get(link_type)
    if definition is None:
        return False
    for pair in definition["allowed_pairs"]:
        if pair["source_type"] in ("*", source) and pair["target_type"] in ("*", target):
            return True
    return False


def uncovered_triples(observed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the observed triples no built-in ``allowed_pairs`` entry matches.

    Built-ins only, deliberately: this is the list that decides what has to go
    into ``GRANDFATHERED_PAIRS``, so it must not consult it. For "would the
    migration refuse this database?" use :func:`blocking_triples`.
    """
    return [
        triple
        for triple in observed
        if not _is_covered(
            triple["link_type"], triple["source_type"], triple["target_type"]
        )
    ]


def blocking_triples(observed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the observed triples ``verify_migrated_links`` would refuse.

    The pre-flight of issue #893: built-ins **plus** ``GRANDFATHERED_PAIRS``,
    evaluated with the migration's own predicate, so a clean run here means
    ``persistence/0081`` will not roll the deploy back on this data.
    """
    return [
        triple
        for triple in observed
        if not is_creatable(
            triple["link_type"], triple["source_type"], triple["target_type"]
        )
    ]


class Command(BaseCommand):
    help = (
        "Inventory the (link_type, source_type, target_type) triples in the "
        "TraceLink table, mapped through the new link-type catalog. Exits "
        "non-zero if any triple would make the data migration "
        "persistence/0081 roll back — run it before upgrading."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            dest="json_path",
            default=None,
            help="Write the full report to this path as JSON.",
        )

    def _write_triples(self, triples, style) -> None:
        for triple in triples:
            self.stdout.write(
                style(
                    f"  {triple['link_type']}: {triple['source_type']} -> "
                    f"{triple['target_type']}  ({triple['count']} rows)"
                )
            )

    def handle(self, *args, **options):
        observed = collect_observed_triples()
        uncovered = uncovered_triples(observed)
        blocking = blocking_triples(observed)

        self.stdout.write(f"Observed triples: {len(observed)}")
        self._write_triples(observed, str)

        if uncovered:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(uncovered)} triple(s) are NOT covered by the built-in "
                    f"allowed_pairs and would be rejected once validation is "
                    f"always-on:"
                )
            )
            self._write_triples(uncovered, self.style.WARNING)
        else:
            self.stdout.write(self.style.SUCCESS("\nAll observed triples are covered."))

        if options["json_path"]:
            payload = {
                "observed": observed,
                "uncovered": uncovered,
                "blocking": blocking,
            }
            with open(options["json_path"], "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            self.stdout.write(f"\nReport written to {options['json_path']}")

        # Pre-flight verdict last, so the report above is complete (and
        # written) even when this aborts. Non-zero exit on purpose: this is
        # what a deploy script gates on (issue #893).
        if blocking:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{len(blocking)} triple(s) are not creatable even with "
                    f"GRANDFATHERED_PAIRS — migration persistence/0081 will "
                    f"refuse to finish and roll back:"
                )
            )
            self._write_triples(blocking, self.style.ERROR)
            raise CommandError(
                f"{len(blocking)} blocking triple(s). Re-type the offending "
                "rows, or extend link_types.grandfathered.GRANDFATHERED_PAIRS "
                "with them (and add a backfill migration in the shape of "
                "link_types/0007 so already-seeded catalogs get the pairs too), "
                "before upgrading."
            )
        self.stdout.write(
            self.style.SUCCESS("Pre-flight: migration persistence/0081 can run.")
        )
