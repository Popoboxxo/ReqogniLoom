"""Suspect propagation dispatches on each link type's suspect_rule."""
from __future__ import annotations

import uuid

import pytest

from application.trace_link_service import TraceLinkService
from link_types.workspace_store import provision_workspace_link_types
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        Tenant,
        TestCase,
        Workspace,
    )

    tenant = Tenant.objects.create(name="suspect")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def requirement(title="req"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, workspace=ws, artifact=art, title=title, suspect=False
        )

    def testcase(title="tc"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="TestCase"
        )
        return TestCase.objects.create(
            tenant=tenant, artifact=art, title=title, suspect=False
        )

    def architecture(title="arch"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="ArchitectureElement"
        )
        return ArchitectureElement.objects.create(
            tenant=tenant, artifact=art, title=title, suspect=False
        )

    def adr(title="adr"):
        """An artifact type that carries no ``suspect`` column at all."""
        from persistence.models import Adr

        art = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Adr")
        return Adr.objects.create(
            tenant=tenant,
            workspace_id=ws.id,
            artifact=art,
            title=title,
            description="d",
        )

    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=ws.id,
    )
    yield {
        "tenant": tenant,
        "ctx": ctx,
        "requirement": requirement,
        "testcase": testcase,
        "architecture": architecture,
        "adr": adr,
    }
    TenantContext.clear_tenant()


def _link(env, source, target, link_type):
    from persistence.models import TraceLink

    return TraceLink.objects.create(
        tenant=env["tenant"],
        source_id=source.artifact_id,
        target_id=target.artifact_id,
        link_type=link_type,
    )


@pytest.mark.django_db
def test_target_change_flags_source_verifies(env):
    """Requirement changes -> its verifying TestCase becomes suspect."""
    req, tc = env["requirement"](), env["testcase"]()
    _link(env, tc, req, "verifies")

    flagged = TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    tc.refresh_from_db()
    assert flagged == 1
    assert tc.suspect is True


@pytest.mark.django_db
def test_source_change_flags_target_allocated_to(env):
    """Requirement changes -> the ArchitectureElement it is allocated to."""
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, req, arch, "allocated-to")

    flagged = TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    arch.refresh_from_db()
    assert flagged == 1
    assert arch.suspect is True


@pytest.mark.django_db
def test_allocated_to_does_not_propagate_backwards(env):
    """The ArchitectureElement changing must NOT flag the Requirement."""
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, req, arch, "allocated-to")

    flagged = TraceLinkService().propagate_suspect_status(arch.artifact_id, env["ctx"])

    req.refresh_from_db()
    assert flagged == 0
    assert req.suspect is False


@pytest.mark.django_db
def test_parent_change_flags_children_decomposes(env):
    parent, child = env["requirement"]("parent"), env["requirement"]("child")
    _link(env, parent, child, "decomposes")

    flagged = TraceLinkService().propagate_suspect_status(
        parent.artifact_id, env["ctx"]
    )

    child.refresh_from_db()
    assert flagged == 1
    assert child.suspect is True


@pytest.mark.django_db
def test_a_child_change_does_not_flag_its_parent(env):
    parent, child = env["requirement"]("parent"), env["requirement"]("child")
    _link(env, parent, child, "decomposes")

    assert (
        TraceLinkService().propagate_suspect_status(child.artifact_id, env["ctx"]) == 0
    )
    parent.refresh_from_db()
    assert parent.suspect is False


@pytest.mark.django_db
def test_rule_none_propagates_nothing(env):
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, arch, req, "references")

    assert (
        TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"]) == 0
    )
    arch.refresh_from_db()
    assert arch.suspect is False


@pytest.mark.django_db
def test_propagation_is_one_hop_only(env):
    """grandparent -> parent -> child: changing the grandparent stops at parent."""
    grand, parent, child = (
        env["requirement"]("g"),
        env["requirement"]("p"),
        env["requirement"]("c"),
    )
    _link(env, grand, parent, "decomposes")
    _link(env, parent, child, "decomposes")

    flagged = TraceLinkService().propagate_suspect_status(grand.artifact_id, env["ctx"])

    parent.refresh_from_db()
    child.refresh_from_db()
    assert flagged == 1
    assert parent.suspect is True
    assert child.suspect is False


@pytest.mark.django_db
def test_the_link_records_when_and_why_it_flagged(env):
    from persistence.models import TraceLink

    req, tc = env["requirement"](), env["testcase"]()
    link = _link(env, tc, req, "verifies")
    audit_id = uuid.uuid4()

    TraceLinkService().propagate_suspect_status(
        req.artifact_id, env["ctx"], audit_entry_id=audit_id
    )

    link.refresh_from_db()
    assert link.suspect_flagged_at is not None
    assert link.suspect_source_change == audit_id


@pytest.mark.django_db
def test_links_that_did_not_fire_keep_a_null_marker(env):
    from persistence.models import TraceLink

    req, arch = env["requirement"](), env["architecture"]()
    quiet = _link(env, arch, req, "references")

    TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    quiet.refresh_from_db()
    assert quiet.suspect_flagged_at is None


@pytest.mark.django_db
def test_a_link_to_a_non_flaggable_type_is_not_stamped(env):
    """A matched rule is not a flag — only three models carry ``suspect``.

    ``Adr``/``Risk``/``StakeholderNeed``/``Goal``/``Issue`` have no ``suspect``
    column, so nothing gets flagged through such a link. Stamping it anyway
    wrote ``suspect_flagged_at``/``suspect_source_change`` — whose own
    help_text says "when this link caused the other endpoint to be flagged
    suspect" — for a flag that never happened.
    """
    req, adr = env["requirement"](), env["adr"]()
    # target_change_flags_source: the Requirement changing points the rule at
    # the Adr on the source side.
    link = _link(env, adr, req, "derives-from")
    audit_id = uuid.uuid4()

    flagged = TraceLinkService().propagate_suspect_status(
        req.artifact_id, env["ctx"], audit_entry_id=audit_id
    )

    assert flagged == 0
    link.refresh_from_db()
    assert link.suspect_flagged_at is None
    assert link.suspect_source_change is None


@pytest.mark.django_db
def test_a_link_to_an_already_suspect_artifact_is_not_stamped(env):
    """Same rule, second symptom: no transition, no provenance marker."""
    req, tc = env["requirement"](), env["testcase"]()
    tc.suspect = True
    tc.save(update_fields=["suspect"])
    link = _link(env, tc, req, "verifies")

    flagged = TraceLinkService().propagate_suspect_status(
        req.artifact_id, env["ctx"], audit_entry_id=uuid.uuid4()
    )

    assert flagged == 0
    link.refresh_from_db()
    assert link.suspect_flagged_at is None


@pytest.mark.django_db
def test_only_the_link_that_flagged_is_stamped(env):
    """Two links fire the same rule; only the one that flagged is marked."""
    req, tc, adr = env["requirement"](), env["testcase"](), env["adr"]()
    flagging = _link(env, tc, req, "verifies")
    inert = _link(env, adr, req, "derives-from")

    flagged = TraceLinkService().propagate_suspect_status(
        req.artifact_id, env["ctx"], audit_entry_id=uuid.uuid4()
    )

    flagging.refresh_from_db()
    inert.refresh_from_db()
    assert flagged == 1
    assert flagging.suspect_flagged_at is not None
    assert inert.suspect_flagged_at is None


@pytest.mark.django_db
def test_the_changed_artifact_is_never_flagged_itself(env):
    req = env["requirement"]()
    _link(env, req, req, "derives-from")

    TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    req.refresh_from_db()
    assert req.suspect is False


@pytest.mark.django_db
def test_an_unknown_artifact_id_is_a_no_op(env):
    assert (
        TraceLinkService().propagate_suspect_status(uuid.uuid4(), env["ctx"]) == 0
    )


@pytest.mark.django_db
def test_a_deactivated_link_type_stops_propagating(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    req, tc = env["requirement"](), env["testcase"]()
    _link(env, tc, req, "verifies")

    disabled = builtin_definition("verifies")
    disabled["active"] = False
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, req.workspace_id, "verifies", disabled
    )

    assert (
        TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"]) == 0
    )
    tc.refresh_from_db()
    assert tc.suspect is False
