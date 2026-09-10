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
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Count

from link_types.builtin import (
    BUILTIN_LINK_TYPES,
    LEGACY_LINK_TYPE_MAPPING,
    SWAPPED_LEGACY_KEYS,
)
from link_types.catalog import normalize_artifact_type


def collect_observed_triples() -> List[Dict[str, Any]]:
    """Return the distinct post-migration triples with their row counts.

    Legacy keys are reported under their successor name, and rows of a
    ``SWAPPED_LEGACY_KEYS`` type are reported with source and target already
    exchanged — so the output describes the world *after* the data migration,
    which is the world validation has to accept.

    Retired-without-successor keys (``parent-child``, ``copy-of``) are skipped:
    they will not exist as links afterwards.

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
        raw_type = row["link_type"]
        if raw_type in LEGACY_LINK_TYPE_MAPPING:
            successor = LEGACY_LINK_TYPE_MAPPING[raw_type]
            if successor is None:
                continue
            link_type = successor
        else:
            link_type = raw_type

        source = normalize_artifact_type(row["source__artifact_type"])
        target = normalize_artifact_type(row["target__artifact_type"])
        if raw_type in SWAPPED_LEGACY_KEYS:
            source, target = target, source

        counter[(link_type, source, target)] += row["count"]

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
    """Return the observed triples no built-in ``allowed_pairs`` entry matches."""
    return [
        triple
        for triple in observed
        if not _is_covered(
            triple["link_type"], triple["source_type"], triple["target_type"]
        )
    ]


class Command(BaseCommand):
    help = (
        "Inventory the (link_type, source_type, target_type) triples in the "
        "TraceLink table, mapped through the new link-type catalog."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            dest="json_path",
            default=None,
            help="Write the full report to this path as JSON.",
        )

    def handle(self, *args, **options):
        observed = collect_observed_triples()
        uncovered = uncovered_triples(observed)

        self.stdout.write(f"Observed triples: {len(observed)}")
        for triple in observed:
            self.stdout.write(
                f"  {triple['link_type']}: {triple['source_type']} -> "
                f"{triple['target_type']}  ({triple['count']} rows)"
            )

        if uncovered:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(uncovered)} triple(s) are NOT covered by the built-in "
                    f"allowed_pairs and would be rejected once validation is "
                    f"always-on:"
                )
            )
            for triple in uncovered:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {triple['link_type']}: {triple['source_type']} -> "
                        f"{triple['target_type']}  ({triple['count']} rows)"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll observed triples are covered."))

        if options["json_path"]:
            payload = {"observed": observed, "uncovered": uncovered}
            with open(options["json_path"], "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            self.stdout.write(f"\nReport written to {options['json_path']}")
