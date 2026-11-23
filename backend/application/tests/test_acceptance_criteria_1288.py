"""#1288 — structured acceptance criteria through the application service.

The single-criterion write path (``GET/PATCH .../acceptance-criteria/{index}/``)
and the MCP ``set`` path both go through :class:`RequirementService`; this pins
the service behaviour directly (no HTTP) so a failure points at the service.
"""
from __future__ import annotations

import pytest

from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t-criteria", slug="t-criteria")
    TenantContext.set_tenant(tenant.id)
    try:
        owner = User.objects.create(
            tenant=tenant, username="crit-owner", email="crit@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
        )
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="R"
        )
        ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        yield {"tenant": tenant, "workspace": workspace, "requirement": requirement, "ctx": ctx}
    finally:
        TenantContext.clear_tenant()


def test_set_then_list_acceptance_criteria(env):
    service = RequirementService()
    result = service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [
            {"text": "must be fast", "fulfilled": False},
            {"text": "must be safe", "fulfilled": True},
        ],
    )
    assert result["total"] == 2
    listed = service.list_acceptance_criteria(env["requirement"].id, env["ctx"])
    assert [c["text"] for c in listed] == ["must be fast", "must be safe"]
    # #2012: the structured write materializes the legacy free-text mirror in
    # the same transaction (deterministic newline join of the stripped texts).
    env["requirement"].refresh_from_db()
    assert env["requirement"].acceptance_criteria == "must be fast\nmust be safe"


def test_set_materialization_preserves_fulfilled_and_evidence_ref(env):
    """#2012: re-materializing the text never rewrites the list's other fields."""
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [
            {
                "text": " signed off ",
                "fulfilled": True,
                "evidence_ref": "https://ci.example/build/1",
            },
            {"text": "pending", "fulfilled": False},
        ],
    )
    # Only the text is edited through the single-criterion path.
    result = service.update_acceptance_criterion(
        env["requirement"].id, env["ctx"], 0, text="signed off (v2)"
    )
    assert result["criterion"]["fulfilled"] is True
    assert result["criterion"]["evidence_ref"] == "https://ci.example/build/1"
    env["requirement"].refresh_from_db()
    items = env["requirement"].acceptance_criteria_items
    assert items[0] == {
        "text": "signed off (v2)",
        "fulfilled": True,
        "evidence_ref": "https://ci.example/build/1",
    }
    assert items[1] == {"text": "pending", "fulfilled": False, "evidence_ref": None}
    # The mirror follows the edited text only; the other fields are untouched.
    assert env["requirement"].acceptance_criteria == "signed off (v2)\npending"


def test_text_only_write_seeds_exactly_one_criterion(env):
    """#2012: a text-only create/update seeds one unchecked criterion."""
    service = RequirementService()
    service.update_requirement(
        env["requirement"].id,
        env["ctx"],
        acceptance_criteria="legacy free text",
        change_reason="#2012",
    )
    env["requirement"].refresh_from_db()
    assert env["requirement"].acceptance_criteria_items == [
        {"text": "legacy free text", "fulfilled": False, "evidence_ref": None}
    ]
    assert env["requirement"].acceptance_criteria == "legacy free text"


def test_materialized_mirror_respects_20k_limit(env):
    """#2012: the mirror is capped at the REST free-text field limit."""
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [{"text": "x" * 21_000, "fulfilled": False}],
    )
    env["requirement"].refresh_from_db()
    assert env["requirement"].acceptance_criteria == "x" * 20_000
    # The authoritative list keeps the full text.
    assert env["requirement"].acceptance_criteria_items[0]["text"] == "x" * 21_000


def test_join_boundary_does_not_create_a_false_scheme_token(env):
    """#2012: sanitize each criterion, not the synthesized joined projection.

    ``find_free_text_violation`` strips C0 controls (including the join's
    newline) before matching dangerous URI schemes. Two individually harmless
    texts must therefore stay acceptable even though their normalized join
    would spell ``javascript:``.
    """
    service = RequirementService()
    result = service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [
            {"text": "see java", "fulfilled": False},
            {"text": "script:alert(1)", "fulfilled": False},
        ],
    )
    assert result["total"] == 2
    env["requirement"].refresh_from_db()
    assert [c["text"] for c in env["requirement"].acceptance_criteria_items] == [
        "see java",
        "script:alert(1)",
    ]
    assert env["requirement"].acceptance_criteria == "see java\nscript:alert(1)"


def test_each_criterion_text_is_still_sanitized_individually(env):
    """#2012: per-text sanitization is not a bypass — real violations still 400."""
    service = RequirementService()
    with pytest.raises(ValidationError):
        service.set_acceptance_criteria(
            env["requirement"].id,
            env["ctx"],
            [{"text": "javascript:alert(1)", "fulfilled": False}],
        )
    with pytest.raises(ValidationError):
        service.set_acceptance_criteria(
            env["requirement"].id,
            env["ctx"],
            [{"text": "java\nscript:alert(1)", "fulfilled": False}],
        )


def test_get_acceptance_criterion_by_index(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [{"text": "a", "fulfilled": False}, {"text": "b", "fulfilled": False}],
    )
    item = service.get_acceptance_criterion(env["requirement"].id, env["ctx"], 1)
    assert item["index"] == 1
    assert item["criterion"]["text"] == "b"
    assert item["total"] == 2


def test_get_out_of_range_index_raises(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id, env["ctx"], [{"text": "a", "fulfilled": False}]
    )
    with pytest.raises(NotFoundError):
        service.get_acceptance_criterion(env["requirement"].id, env["ctx"], 5)


def test_check_off_a_single_criterion(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [{"text": "a", "fulfilled": False}, {"text": "b", "fulfilled": False}],
    )
    result = service.update_acceptance_criterion(
        env["requirement"].id, env["ctx"], 0, fulfilled=True
    )
    assert result["criterion"]["fulfilled"] is True
    listed = service.list_acceptance_criteria(env["requirement"].id, env["ctx"])
    assert listed[0]["fulfilled"] is True
    assert listed[1]["fulfilled"] is False
    # Checking a criterion off changes no text, so the mirror stays stable.
    env["requirement"].refresh_from_db()
    assert env["requirement"].acceptance_criteria == "a\nb"


def test_update_rejects_a_non_boolean_fulfilled(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id, env["ctx"], [{"text": "a", "fulfilled": False}]
    )
    with pytest.raises(ValidationError):
        service.update_acceptance_criterion(
            env["requirement"].id, env["ctx"], 0, fulfilled="yes"
        )


def test_set_rejects_a_malformed_list(env):
    service = RequirementService()
    with pytest.raises(ValidationError):
        service.set_acceptance_criteria(
            env["requirement"].id, env["ctx"], [{"text": "", "fulfilled": False}]
        )
