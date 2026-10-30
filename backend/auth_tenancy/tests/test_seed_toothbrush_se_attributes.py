"""Plan B / WP B1 — the toothbrush seed fills the SE attributes (B1-T2/B1-T3).

The seed used to leave ``acceptance_criteria``, ``rationale``,
``verification_method``, ``owner`` and ``priority`` empty on every requirement,
so the E2E fixture demonstrated hierarchy and traceability but no SE content.
B1-T2 fills those fields on creation, B1-T3 backfills an existing workspace
without touching values a human already set.

Both tests run against a real ``Workspace``/``User`` pair (no synthetic ids):
the command resolves its tenant/user from the database and writes through the
same services the REST/MCP transports use.
"""
from __future__ import annotations

import pytest

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


@pytest.fixture
def seed_tenant(db) -> Tenant:
    """The tenant the seed command resolves from the (single) admin user."""
    return Tenant.objects.create(name="Tenant A", slug="tenant-a", is_active=True)


@pytest.fixture
def seed_admin(db, seed_tenant) -> User:
    """The admin user the seed command picks up by its well-known username."""
    return User.objects.create(
        username=DEFAULT_ADMIN_USERNAME,
        email=DEFAULT_ADMIN_EMAIL,
        tenant=seed_tenant,
    )


@pytest.fixture
def seeded(db, seed_tenant, seed_admin) -> Workspace:
    """Run the seed on a tenant whose attribute definitions are bootstrapped.

    Production reaches the same state through ``migrate``'s post_migrate
    self-init hook (or the explicit ``bootstrap_attribute_definitions`` step in
    the E2E workflow) *before* the seed writes owner/priority through the
    attribute gateway, so the bootstrap belongs to the environment setup here,
    not to an assertion about the seed.
    """
    from django.core.management import call_command

    call_command("bootstrap_attribute_definitions", tenant=str(seed_tenant.id))
    call_command("seed_toothbrush")
    return Workspace.unscoped.get(name=WORKSPACE_NAME)


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
    call_command("seed_toothbrush")
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
