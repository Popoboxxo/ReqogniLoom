"""Plan B / WP B1 — the toothbrush seed fills the SE attributes (B1-T2/B1-T3).

The seed used to leave ``acceptance_criteria``, ``rationale``,
``verification_method``, ``owner`` and ``priority`` empty on every requirement,
so the E2E fixture demonstrated hierarchy and traceability but no SE content.
B1-T2 fills those fields on creation, B1-T3 backfills an existing workspace
without touching values a human already set.

Both tests run against a real ``Workspace``/``User`` pair (no synthetic ids):
the command resolves its tenant/user from the database and writes through the
same services the REST/MCP transports use.

COST: a full ``seed_toothbrush`` run is ~650 s — it creates ~880 requirements
and ~1 800 trace links, each with cycle detection and RLS-scoped artifact
lookups. The fixture therefore seeds with ``--max-needs 1``: the requirement
cascade (L1–L5) and every SE-attribute write path still run, but the fixture
drops to tens of requirements and seconds instead of minutes. The module scope
stays so the three tests share that one run. The seed therefore runs
**once per module**, inside one outer transaction that is rolled back when the
module finishes: the three tests share the seeded rows, each test still rolls
back its own changes (pytest-django nests its per-test atomic inside this one),
and nothing leaks into later test modules.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from django.db import transaction

from auth_tenancy.provisioning import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_USERNAME
from persistence.models import (
    Actor,
    Artifact,
    Requirement,
    Tenant,
    User,
    VerificationMethod,
    Workspace,
)

pytestmark = pytest.mark.django_db

WORKSPACE_NAME = "Zahnbürste SysEng Demo"


@pytest.fixture(scope="module")
def seed_tenant(django_db_setup, django_db_blocker) -> Tenant:
    """The tenant the seed command resolves from the (single) admin user."""
    with django_db_blocker.unblock():
        # Unique slug: the module-scoped fixture must survive a reused test DB
        # (``--reuse-db``) without colliding with a previous module's tenant.
        return Tenant.objects.create(
            name="Tenant A",
            slug=f"tenant-a-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )


@pytest.fixture(scope="module")
def seed_admin(seed_tenant, django_db_blocker) -> User:
    """The admin user the seed command picks up by its well-known username."""
    with django_db_blocker.unblock():
        # ``seed_toothbrush`` resolves the tenant from this well-known admin
        # user; a reused DB may already hold it, so reuse and re-home it.
        user, _ = User.objects.get_or_create(
            username=DEFAULT_ADMIN_USERNAME,
            defaults={"email": DEFAULT_ADMIN_EMAIL, "tenant": seed_tenant},
        )
        if user.tenant_id != seed_tenant.id:
            user.tenant = seed_tenant
            user.save(update_fields=["tenant"])
        return user


@pytest.fixture(scope="module")
def seeded(seed_tenant, seed_admin, django_db_blocker) -> Iterator[Workspace]:
    """Run the seed ONCE for the module, inside a transaction rolled back at the end.

    Production reaches this state through ``migrate``'s post_migrate self-init
    hook (or the explicit ``bootstrap_attribute_definitions`` step in the E2E
    workflow) *before* the seed writes owner/priority through the attribute
    definition, so the bootstrap belongs to the environment setup here, not to
    an assertion about the seed.

    The outer ``atomic`` is entered by hand rather than as a context manager
    because it has to stay open across the tests and be rolled back afterwards:
    pytest-django nests each test's own atomic inside it, so per-test changes
    still roll back individually and the seeded rows survive for the next test.
    """
    from django.core.management import call_command

    outer_atomic = transaction.atomic()
    entered = False
    try:
        with django_db_blocker.unblock():
            outer_atomic.__enter__()
            entered = True
            call_command(
                "bootstrap_attribute_definitions", tenant=str(seed_tenant.id)
            )
            # One need instead of twenty: the cascade still covers L1–L5 and
            # every SE attribute, but the full seed is ~880 requirements and
            # ~1 800 trace links (measured 648 s) — test-cost only.
            call_command("seed_toothbrush", max_needs=1)
            workspace = Workspace.unscoped.get(name=WORKSPACE_NAME)
        yield workspace
    finally:
        if entered:
            with django_db_blocker.unblock():
                transaction.set_rollback(True)
                outer_atomic.__exit__(None, None, None)


def _requirements(workspace: Workspace) -> list[Requirement]:
    return list(
        Requirement.unscoped.filter(artifact__workspace_id=workspace.id)
        .select_related("artifact")
        .order_by("id")
    )


def test_every_requirement_has_ac_vm_rationale_owner_priority(seeded):
    """B1-T2: no seeded requirement leaves an SE attribute empty."""
    requirements = _requirements(seeded)
    assert requirements, "seed created no requirements"

    allowed_methods = {choice.value for choice in VerificationMethod}
    allowed_priorities = {"low", "medium", "high", "critical"}

    for requirement in requirements:
        assert requirement.acceptance_criteria.strip(), requirement.title
        assert requirement.rationale.strip(), requirement.title
        assert requirement.verification_method in allowed_methods, requirement.title
        assert requirement.artifact.owner_id is not None, requirement.title
        assert requirement.artifact.priority in allowed_priorities, requirement.title
        # #1288/0113: the structured list mirrors the free text — one
        # unfulfilled criterion carrying exactly the seeded text.
        assert requirement.acceptance_criteria_items == [
            {
                "text": requirement.acceptance_criteria,
                "fulfilled": False,
                "evidence_ref": None,
            }
        ], requirement.title


def test_seed_is_still_idempotent(seeded):
    """B1-T2: a second run must not duplicate requirements or the workspace."""
    from django.core.management import call_command

    before = len(_requirements(seeded))
    call_command("seed_toothbrush", max_needs=1)
    after = len(_requirements(seeded))

    assert after == before
    assert Workspace.unscoped.filter(name=WORKSPACE_NAME).count() == 1


def test_backfill_fills_only_empty_fields(seeded, seed_admin, capsys):
    """B1-T3: only empty fields are filled, and a re-run reports zero."""
    from django.core.management import call_command

    requirements = _requirements(seeded)
    target = next(r for r in requirements if r.level == 3)
    manual = next(r for r in requirements if r.level == 1)

    Requirement.unscoped.filter(id=target.id).update(
        acceptance_criteria="",
        rationale="",
        verification_method=None,
        acceptance_criteria_items=[],
    )
    Artifact.unscoped.filter(id=target.artifact_id).update(owner=None, priority="")

    manual_ac = "Manuell gesetzte Abnahmekriterien bleiben erhalten."
    Requirement.unscoped.filter(id=manual.id).update(
        acceptance_criteria=manual_ac,
        rationale="",
        verification_method=None,
        acceptance_criteria_items=[
            {"text": manual_ac, "fulfilled": False, "evidence_ref": None}
        ],
    )
    Artifact.unscoped.filter(id=manual.artifact_id).update(owner=None, priority="")

    call_command("seed_toothbrush", "--backfill-se-attributes")
    first_run = capsys.readouterr().out
    assert f"Backfilled 2 requirements ({len(requirements) - 2} already complete)." in first_run

    from auth_tenancy.management.commands.seed_toothbrush import (
        PRIORITY_BY_LEVEL,
        SE_ATTRIBUTES_BY_TITLE,
        VERIFICATION_METHOD_BY_LEVEL,
    )

    target_after = Requirement.unscoped.select_related("artifact").get(id=target.id)
    acceptance_criteria, rationale = SE_ATTRIBUTES_BY_TITLE[target_after.title]
    assert target_after.acceptance_criteria == acceptance_criteria
    assert target_after.rationale == rationale
    assert (
        target_after.verification_method
        == VERIFICATION_METHOD_BY_LEVEL[target_after.level]
    )
    assert target_after.acceptance_criteria_items == [
        {"text": acceptance_criteria, "fulfilled": False, "evidence_ref": None}
    ]
    actor = Actor.unscoped.get(user_id=seed_admin.id)
    assert target_after.artifact.owner_id == actor.id
    assert (
        target_after.artifact.priority == PRIORITY_BY_LEVEL[target_after.level]
    )

    manual_after = Requirement.unscoped.select_related("artifact").get(id=manual.id)
    assert manual_after.acceptance_criteria == manual_ac
    assert manual_after.rationale == SE_ATTRIBUTES_BY_TITLE[manual_after.title][1]
    assert manual_after.artifact.owner_id == actor.id

    call_command("seed_toothbrush", "--backfill-se-attributes")
    second_run = capsys.readouterr().out
    assert f"Backfilled 0 requirements ({len(requirements)} already complete)." in second_run
