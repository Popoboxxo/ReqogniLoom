"""Endpoint pairs that exist in live data but no built-in type allows.

Populated from ``python manage.py inventory_link_types --json ...`` run
against production-shaped data — **not** invented. See OFFENE FRAGE 1 of
docs/superpowers/plans/2026-09-03-traceability-semantik.md: the spec's eight
built-in types describe the *target* semantics, but the ``TraceLink`` rows
that exist today were written under the old, looser matrix. Without this
file, flipping validation to always-on (Task 11) would make every one of
those rows uncreatable.

Every entry here is a documented compromise, not a design statement: the pair
is allowed because it already exists, and it should be revisited whenever the
owning artifact type gets a proper semantic home.

Provenance of the current contents (Task 10, 2026-09-09)
--------------------------------------------------------
Two live runs of ``inventory_link_types``, both as the DB owner role (the
least-privilege app role is blinded by RLS and the command fails loudly there
rather than reporting a false "0 rows, all covered"):

1. The dev database (196 artifacts, 2 ``TraceLink`` rows) — 1 observed
   triple, 0 uncovered. Too thin to be evidence on its own.
2. A scratch database migrated to the current head and seeded with
   ``seed_demo`` + ``seed_toothbrush`` (the only seeder in this repo that
   writes ``TraceLink`` rows) — 8 observed triples / 1974 rows, of which the
   4 below were uncovered.

The four entries, with the legacy key each one arrives from:

==================================================  =======  ==================
observed triple (post section-3.1 rename)           rows     legacy origin
==================================================  =======  ==================
allocated-to  StakeholderNeed -> Requirement            40   ``satisfies``
references    Adr -> ArchitectureElement                12   ``documents``
references    Issue -> ArchitectureElement              55   ``traces``
references    Risk -> Requirement                       22   ``traces``
==================================================  =======  ==================

``allocated-to  StakeholderNeed -> Requirement`` is the one that carries a
warning. ``builtin.SWAPPED_LEGACY_KEYS`` assumes every ``satisfies`` row ran
ArchitectureElement -> Requirement; the real data also uses it as
Requirement -> StakeholderNeed, which the swap turns into
StakeholderNeed -> Requirement — an inverted ``derives-from``, not an
allocation. Grandfathering keeps those 40 rows creatable; re-typing them is a
separate data question for Task 16, deliberately not decided here.

**Limitation, stated rather than papered over:** this list is only as complete
as the databases it was taken from. The Goal / MainGoal / Issue / Interview
artifact types named in OFFENE FRAGE 1 produced no *uncovered* triples in
either run (Issue did, via ``references``, and is in the list; Goal, MainGoal
and Interview had no ``TraceLink`` rows at all). The plan says "do not guess
the contents", so nothing was added for them. An installation whose data
differs must re-run ``inventory_link_types`` before applying migration
``0004`` and extend this dict with its own ``uncovered`` list.

Second round (issue #893, 2026-09-10)
-------------------------------------
The limitation above stopped being theoretical on the first beta.6 -> beta.7
upgrade of a QA database with UI/MCP-authored data: two triples that neither
seeder writes made ``persistence/0081`` refuse to finish.

===============================================  =======  ===================
observed triple (post section-3.1 rename)        rows     legacy origin
===============================================  =======  ===================
references    Requirement -> Requirement              1   ``traces``
mitigates     Risk -> Requirement                     1   ``verifies`` [#]_
===============================================  =======  ===================

.. [#] Only the first one is grandfathered here. ``verifies`` Risk ->
   Requirement is *retyped* by the migration instead
   (``migration_ops._ENDPOINT_EXCEPTIONS``): ``mitigates`` Risk -> Requirement
   is a built-in pair that means exactly that relation, so grandfathering
   ``verifies`` would have legalized a second, wrongly named spelling of an
   existing built-in for every tenant. Grandfathering tolerates legacy data;
   it also makes the pair creatable again, which is the reason not to reach
   for it when a correct built-in home exists.

``references Requirement -> Requirement`` has no such home: legacy ``traces``
carried no direction semantics, so re-typing it to ``derives-from`` (which
declares source=child, target=parent) would invent a claim the data does not
make. It is grandfathered rather than promoted to a built-in for the same
reason: ``references`` targets a *reference entity*, and a Requirement is not
one.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

#: link-type key -> additional allowed pairs, verbatim from the inventory run
#: documented in this module's docstring. Never hand-written: regenerate with
#: ``manage.py inventory_link_types --json`` and paste the ``uncovered`` list.
GRANDFATHERED_PAIRS: Dict[str, List[Dict[str, str]]] = {
    "allocated-to": [
        # legacy `satisfies` Requirement -> StakeholderNeed, endpoints swapped
        # by SWAPPED_LEGACY_KEYS; 40 rows.
        {"source_type": "StakeholderNeed", "target_type": "Requirement"},
    ],
    "references": [
        # legacy `documents`; 12 rows.
        {"source_type": "Adr", "target_type": "ArchitectureElement"},
        # legacy `traces`; 55 rows.
        {"source_type": "Issue", "target_type": "ArchitectureElement"},
        # legacy `traces`; 22 rows.
        {"source_type": "Risk", "target_type": "Requirement"},
        # legacy `traces`; issue #893, 1 row on the QA database. No built-in
        # `references` pair puts a Requirement on the target side, and no other
        # built-in type fits a directionless legacy trace.
        {"source_type": "Requirement", "target_type": "Requirement"},
    ],
}


def apply_grandfathered_pairs(definition: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Return a copy of *definition* with the grandfathered pairs appended.

    Additive and duplicate-free: a built-in pair is never dropped, and a pair
    already covered is not repeated.
    """
    extra = GRANDFATHERED_PAIRS.get(key)
    if not extra:
        return copy.deepcopy(definition)

    merged = copy.deepcopy(definition)
    pairs = merged.setdefault("allowed_pairs", [])
    seen = {(p["source_type"], p["target_type"]) for p in pairs}
    for pair in extra:
        signature = (pair["source_type"], pair["target_type"])
        if signature not in seen:
            pairs.append(dict(pair))
            seen.add(signature)
    return merged


__all__ = ["GRANDFATHERED_PAIRS", "apply_grandfathered_pairs"]
