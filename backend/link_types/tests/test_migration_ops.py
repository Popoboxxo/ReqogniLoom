"""The hard TraceLink migration: rename, swap, dedup, copy-of relocation."""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from link_types.migration_ops import (
    find_copy_of_conflicts,
    migrate_copy_of_links,
    migrate_parent_child_links,
    migrate_renamed_links,
    verify_migrated_links,
)
from persistence.tenancy import TenantContext

#: Base for the synthetic ``created_at`` stamps handed out by the ``link``
#: helper below.
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def env(db):
    from persistence.models import Artifact, Tenant, TraceLink, Workspace

    tenant = Tenant.objects.create(name="migration-ops", slug="migration-ops")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    clock = itertools.count()

    def artifact(kind: str = "Requirement", title: str = "a") -> Artifact:
        # `title` is a readability label only: Artifact carries no title column
        # (the typed sibling row does), so it is deliberately not persisted.
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind
        )

    def link(source, target, link_type) -> TraceLink:
        row = TraceLink.objects.create(
            tenant=tenant, source=source, target=target, link_type=link_type
        )
        # `created_at` is auto_now_add, so two links created inside one test can
        # share a timestamp and leave "newest wins" to be decided by a random
        # uuid4 tiebreak. Force a strictly increasing stamp instead.
        stamp = _EPOCH + timedelta(seconds=next(clock))
        TraceLink.objects.filter(id=row.id).update(created_at=stamp)
        row.created_at = stamp
        return row

    yield {
        "tenant": tenant,
        "artifact": artifact,
        "link": link,
        "Artifact": Artifact,
        "TraceLink": TraceLink,
    }
    TenantContext.clear_tenant()


# ---------- renames + endpoint swap ----------


@pytest.mark.django_db
def test_satisfies_is_renamed_and_its_endpoints_swapped(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "satisfies")

    counts = migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="allocated-to")
    assert counts["satisfies"] == 1
    assert row.source_id == req.id
    assert row.target_id == arch.id


@pytest.mark.django_db
def test_implements_is_renamed_and_swapped_too(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "implements")

    migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="allocated-to")
    assert row.source_id == req.id


@pytest.mark.django_db
def test_refines_becomes_derives_from_without_swapping(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "refines")

    migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="derives-from")
    assert row.source_id == a.id
    assert row.target_id == b.id


@pytest.mark.django_db
def test_realizes_becomes_decomposes(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "realizes")
    migrate_renamed_links(env["TraceLink"])
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("legacy", ["documents", "traces", "uses-term"])
def test_documentation_types_collapse_into_references(env, legacy):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, legacy)
    migrate_renamed_links(env["TraceLink"])
    assert env["TraceLink"].objects.filter(link_type="references").count() == 1


@pytest.mark.django_db
def test_a_rename_that_would_duplicate_an_existing_edge_deletes_the_loser(env):
    """documents + traces between the same pair both become references."""
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "documents")
    env["link"](a, b, "traces")

    migrate_renamed_links(env["TraceLink"])

    assert env["TraceLink"].objects.filter(link_type="references").count() == 1


@pytest.mark.django_db
def test_the_eight_surviving_types_are_untouched(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "verifies")
    counts = migrate_renamed_links(env["TraceLink"])
    assert "verifies" not in counts
    assert env["TraceLink"].objects.get(link_type="verifies").source_id == a.id


# ---------- satisfies is two relations under one key ----------


@pytest.mark.django_db
@pytest.mark.parametrize("need_type", ["StakeholderNeed", "StakeholderNeed:business"])
def test_satisfies_to_stakeholder_need_becomes_derives_from_unswapped(env, need_type):
    """The second legacy `satisfies` pair is a derivation, not an allocation.

    Legacy ``SE_LINK_SEMANTICS['satisfies']`` was
    ``{(ArchitectureElement, Requirement), (Requirement, StakeholderNeed)}``.
    Only the first is an allocation; swapping the second would produce
    ``allocated-to StakeholderNeed -> Requirement``, which is neither a
    built-in pair nor true (see ``link_types.grandfathered``, 40 such rows).
    """
    req, need = env["artifact"]("Requirement"), env["artifact"](need_type)
    env["link"](req, need, "satisfies")

    counts = migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="derives-from")
    assert counts["satisfies:StakeholderNeed"] == 1
    assert "satisfies" not in counts
    assert row.source_id == req.id  # NOT swapped
    assert row.target_id == need.id


@pytest.mark.django_db
def test_one_run_splits_satisfies_by_target_type(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    need = env["artifact"]("StakeholderNeed")
    env["link"](arch, req, "satisfies")
    env["link"](req, need, "satisfies")

    counts = migrate_renamed_links(env["TraceLink"])

    assert counts["satisfies"] == 1
    assert counts["satisfies:StakeholderNeed"] == 1
    allocation = env["TraceLink"].objects.get(link_type="allocated-to")
    derivation = env["TraceLink"].objects.get(link_type="derives-from")
    assert (allocation.source_id, allocation.target_id) == (req.id, arch.id)
    assert (derivation.source_id, derivation.target_id) == (req.id, need.id)


# ---------- parent-child ----------


@pytest.mark.django_db
def test_parent_child_becomes_decomposes(env):
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "parent-child")

    converted, deduplicated = migrate_parent_child_links(env["TraceLink"])

    assert (converted, deduplicated) == (1, 0)
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1


@pytest.mark.django_db
def test_a_parent_child_duplicating_an_existing_decomposes_is_dropped(env):
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "decomposes")
    env["link"](parent, child, "parent-child")

    converted, deduplicated = migrate_parent_child_links(env["TraceLink"])

    assert (converted, deduplicated) == (0, 1)
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1
    assert not env["TraceLink"].objects.filter(link_type="parent-child").exists()


# ---------- copy-of ----------


@pytest.mark.django_db
def test_copy_of_moves_into_the_artifact_field_and_the_link_is_deleted(env):
    copy, original = env["artifact"](title="copy"), env["artifact"](title="original")
    env["link"](copy, original, "copy-of")

    moved, downgraded = migrate_copy_of_links(env["Artifact"], env["TraceLink"])

    copy.refresh_from_db()
    assert (moved, downgraded) == (1, 0)
    assert copy.copied_from_id == original.id
    assert not env["TraceLink"].objects.filter(link_type="copy-of").exists()


@pytest.mark.django_db
def test_multiple_copy_of_links_are_reported_as_a_conflict(env):
    copy = env["artifact"](title="copy")
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](copy, a, "copy-of")
    env["link"](copy, b, "copy-of")

    conflicts = find_copy_of_conflicts(env["TraceLink"])

    assert copy.id in conflicts
    assert len(conflicts[copy.id]) == 2


@pytest.mark.django_db
def test_no_conflict_is_reported_for_a_single_copy_of(env):
    copy, original = env["artifact"](title="copy"), env["artifact"](title="original")
    env["link"](copy, original, "copy-of")
    assert find_copy_of_conflicts(env["TraceLink"]) == {}


@pytest.mark.django_db
def test_the_newest_copy_of_wins_and_the_rest_become_references(env):
    copy = env["artifact"](title="copy")
    older, newer = env["artifact"](title="older"), env["artifact"](title="newer")
    env["link"](copy, older, "copy-of")
    env["link"](copy, newer, "copy-of")

    moved, downgraded = migrate_copy_of_links(env["Artifact"], env["TraceLink"])

    copy.refresh_from_db()
    assert (moved, downgraded) == (1, 1)
    assert copy.copied_from_id == newer.id
    assert env["TraceLink"].objects.filter(
        link_type="references", target_id=older.id
    ).exists()


@pytest.mark.django_db
def test_check_copy_of_conflicts_command_lists_them(env):
    """The preflight reads through the *unscoped* managers, not ``objects``."""
    from io import StringIO

    from django.core.management import call_command

    copy = env["artifact"]("Requirement", title="copy")
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](copy, a, "copy-of")
    env["link"](copy, b, "copy-of")

    out = StringIO()
    call_command("check_copy_of_conflicts", stdout=out)
    report = out.getvalue()

    assert "1 artifact(s) have multiple copy-of links" in report
    assert f"{copy.id} [Requirement]: 2 links" in report


@pytest.mark.django_db
def test_migration_ops_are_idempotent(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "satisfies")
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "parent-child")

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])
    total = env["TraceLink"].objects.count()

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])

    assert env["TraceLink"].objects.count() == total


# ---------- collision accounting ----------


@pytest.mark.django_db
def test_a_dropped_duplicate_is_counted_apart_from_the_rewritten_rows(env):
    """The migration log is the only record; a deleted row is not a rewrite."""
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "documents")
    env["link"](a, b, "traces")

    counts = migrate_renamed_links(env["TraceLink"])

    assert counts["documents"] == 1
    assert counts["traces:dropped"] == 1
    assert "traces" not in counts


# ---------- post-condition ----------


@pytest.mark.django_db
def test_the_post_condition_accepts_built_in_and_grandfathered_pairs(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    adr = env["artifact"]("Adr")
    env["link"](arch, req, "satisfies")  # -> allocated-to Requirement -> Arch
    env["link"](adr, arch, "documents")  # -> references Adr -> Arch (grandfathered)

    migrate_renamed_links(env["TraceLink"])

    assert verify_migrated_links(env["TraceLink"]) == 2


@pytest.mark.django_db
def test_a_satisfies_between_two_requirements_fails_the_post_condition(env):
    """The blanket swap can produce a pair no catalog entry allows.

    ``_migrate_satisfies_to_stakeholder_needs`` only rescues rows whose target
    is a StakeholderNeed; every other ``satisfies`` row is swapped into
    ``allocated-to``, which allows Requirement -> ArchitectureElement and
    nothing else. Such a row would exist but could never be recreated, so the
    migration has to fail (persistence/0078's RuntimeError pattern) rather
    than write it.
    """
    source, target = env["artifact"]("Requirement"), env["artifact"]("Requirement")
    link = env["link"](source, target, "satisfies")

    migrate_renamed_links(env["TraceLink"])
    assert env["TraceLink"].objects.filter(link_type="allocated-to").exists()

    with pytest.raises(RuntimeError) as excinfo:
        verify_migrated_links(env["TraceLink"])

    message = str(excinfo.value)
    assert "'allocated-to' Requirement -> Requirement" in message
    assert str(link.id) in message
    assert "inventory_link_types" in message


@pytest.mark.django_db
def test_a_surviving_legacy_type_also_fails_the_post_condition(env):
    """A retired key is not in the catalog at all, so it cannot be creatable."""
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "parent-child")  # skipped: only the parent-child step converts it

    with pytest.raises(RuntimeError, match="parent-child"):
        verify_migrated_links(env["TraceLink"])


@pytest.mark.django_db
def test_sub_typed_artifact_types_are_normalized_before_matching(env):
    """``"TestCase:System"`` has to match the built-in ``TestCase`` pair."""
    case, req = env["artifact"]("TestCase:System"), env["artifact"]("Requirement")
    env["link"](case, req, "verifies")

    assert verify_migrated_links(env["TraceLink"]) == 1


@pytest.mark.django_db
def test_no_retired_link_type_survives_the_full_run(env):
    from link_types.builtin import LEGACY_LINK_TYPE_MAPPING

    a = env["artifact"](title="a")
    for legacy in LEGACY_LINK_TYPE_MAPPING:
        env["link"](a, env["artifact"](title=f"t-{legacy}"), legacy)

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])

    survivors = set(
        env["TraceLink"].objects.values_list("link_type", flat=True)
    )
    assert survivors & set(LEGACY_LINK_TYPE_MAPPING) == set()
