"""Issue #2043 — an ArchitectureElement interview can collect a parent.

The definition-derived protocol now elicits ``parent_id`` as optional free
text: a blank answer asks for the single root (invariant I5 decides), a real
id is validated by the production service (I3/I1/I5). These tests pin the
protocol hint, the adapter's normalisation and the end-to-end behaviour -- in
particular that a second root is either attached under a chosen parent or
rejected with an actionable hint naming the interview question.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from application.base import ValidationError
from application.interview_artifact_adapters import (
    ARTIFACT_CREATION_ADAPTERS,
    _architecture_element,
)
from application.interview_protocol import protocol_from_definition
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant


def _attr(name: str, **over):
    base = {
        "name": name,
        "kind": "core",
        "type": "text",
        "section": "general",
        "order": 0,
        "ai_elicit": True,
        "visible": True,
        "options": [],
        "label": {"de": name, "en": name},
        "widget_key": None,
        "fields": [],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Protocol derivation
# ---------------------------------------------------------------------------


def test_parent_id_is_elicited_as_text_with_an_actionable_hint() -> None:
    protocol = protocol_from_definition(
        [
            _attr("title"),
            _attr("description"),
            _attr("element_type", type="enum",
                  options=[{"value": "component", "label_de": "C", "label_en": "C"}]),
            _attr("parent_id", type="reference"),
        ],
        "ArchitectureElement",
    )
    names = {f.name for phase in protocol.phases for f in phase.required_fields}
    assert {"title", "description", "element_type", "parent_id"} <= names
    by_name = {f.name: f for p in protocol.phases for f in p.required_fields}
    assert by_name["parent_id"].type == "text"
    hints = [p.prompt_fragment for p in protocol.phases if "parent_id" in p.prompt_fragment]
    assert hints, "the elicitation phase must explain the optional parent"
    assert "existing ArchitectureElement" in hints[0]
    assert "blank" in hints[0]


def test_no_parent_hint_for_other_types() -> None:
    protocol = protocol_from_definition([_attr("parent_id", type="reference")], "Issue")
    assert not any(
        "existing ArchitectureElement" in p.prompt_fragment for p in protocol.phases
    )


# ---------------------------------------------------------------------------
# Adapter normalisation (no DB)
# ---------------------------------------------------------------------------


def _call_adapter(fields: dict):
    """Call the real ArchitectureElement adapter against an autospec'd create."""
    fake_ctx = MagicMock()
    fake_element = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
    with patch(
        "application.interview_artifact_adapters.ArchitectureService."
        "create_architecture_element",
        autospec=True,
        return_value=fake_element,
    ) as mocked:
        ref = _architecture_element(
            {"title": "Child", **fields}, fake_ctx, "ws-1"
        )
    return mocked, ref


def test_blank_parent_is_dropped_so_a_root_can_be_created() -> None:
    mocked, _ = _call_adapter({"parent_id": ""})
    kwargs = mocked.call_args.kwargs
    assert "parent_id" not in kwargs, "blank must not be forwarded as ''"
    assert kwargs["title"] == "Child"


def test_whitespace_only_parent_is_dropped() -> None:
    mocked, _ = _call_adapter({"parent_id": "   "})
    assert "parent_id" not in mocked.call_args.kwargs


def test_valid_uuid_string_is_normalised_and_forwarded() -> None:
    parent_id = uuid.uuid4()
    mocked, _ = _call_adapter({"parent_id": str(parent_id)})
    assert mocked.call_args.kwargs["parent_id"] == parent_id
    assert isinstance(mocked.call_args.kwargs["parent_id"], uuid.UUID)


def test_malformed_parent_is_rejected_with_a_readable_error() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _call_adapter({"parent_id": "not-a-uuid"})
    assert "parent_id" in str(excinfo.value)
    assert "existing ArchitectureElement" in str(excinfo.value)


def test_i5_rejection_gets_an_actionable_interview_hint() -> None:
    fake_ctx = MagicMock()
    i5_error = ValidationError(
        "[I5] Workspace already has a root ArchitectureElement. A tree may "
        "have exactly one root (the System); attach this element under an "
        "existing element instead of making it a second root."
    )
    with patch(
        "application.interview_artifact_adapters.ArchitectureService."
        "create_architecture_element",
        autospec=True,
        side_effect=i5_error,
    ):
        with pytest.raises(ValidationError) as excinfo:
            _architecture_element({"title": "Second root", "parent_id": ""}, fake_ctx, "ws-1")
    message = str(excinfo.value)
    assert "[I5]" in message
    assert "parent_id" in message, "the error must name the interview question"


def test_non_i5_validation_error_is_not_rewritten() -> None:
    fake_ctx = MagicMock()
    original = ValidationError("[I1] Self-parent reference rejected")
    with patch(
        "application.interview_artifact_adapters.ArchitectureService."
        "create_architecture_element",
        autospec=True,
        side_effect=original,
    ):
        with pytest.raises(ValidationError) as excinfo:
            _architecture_element({"title": "X"}, fake_ctx, "ws-1")
    assert str(excinfo.value) == str(original)


def test_architecture_adapter_is_registered() -> None:
    assert ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"] is _architecture_element


# ---------------------------------------------------------------------------
# End-to-end through a bootstrapped, tier-2 interview
# ---------------------------------------------------------------------------


@pytest.fixture
def interview_setup(db):
    """Tenant + standard workspace + editor context with a bootstrapped definition."""
    from application.architecture_service import ArchitectureService
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(
        name="Arch Parent Interview 2043", slug=f"arch-parent-2043-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws-arch-parent-2043", preset={"name": "standard"}
        )
        user = User.objects.create(
            username="arch-parent-2043",
            email="arch-parent-2043@t.test",
            tenant=tenant,
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx, ArchitectureService()


def _answer_all(svc: InterviewService, ctx, session_id, parent_value: str) -> None:
    """Answer every missing field, giving ``parent_id`` the chosen value."""
    for _ in range(20):
        missing = svc.get_state(ctx, session_id)["missing_fields"]
        if not missing:
            return
        for field in missing:
            name = field["name"]
            if name == "parent_id":
                value = parent_value
            elif name == "element_type":
                value = (field.get("choices") or ["component"])[0]
            elif field["type"] == "enum":
                value = (field.get("choices") or [])[0]
            elif field["type"] == "number":
                value = 1
            else:
                value = f"Answer for {name}"
            svc.answer(ctx, session_id, name, value)
    raise AssertionError("protocol still reports missing fields after 20 phases")


def test_interview_attaches_element_under_chosen_parent(interview_setup) -> None:
    _, workspace, ctx, architecture = interview_setup
    root = architecture.create_architecture_element(
        workspace_id=workspace.id, title="System", ctx=ctx
    )
    svc = InterviewService()
    session = svc.start(ctx, "ArchitectureElement", workspace.id)
    _answer_all(svc, ctx, session.id, str(root.id))

    result = svc.formalize(ctx, session.id)

    created = architecture.get_architecture_element(
        uuid.UUID(result["resulting_artifact_ids"][0]), ctx
    )
    assert created.parent_id == root.id, "the collected parent must be honoured"


def test_second_root_via_interview_is_rejected_with_an_actionable_hint(interview_setup) -> None:
    """A blank parent when a root already exists must NOT create a forbidden
    second root; the rejection must tell the host to answer parent_id."""
    _, workspace, ctx, architecture = interview_setup
    root = architecture.create_architecture_element(
        workspace_id=workspace.id, title="System", ctx=ctx
    )
    before = len(architecture.list_architecture_elements(workspace.id, ctx))

    svc = InterviewService()
    session = svc.start(ctx, "ArchitectureElement", workspace.id)
    _answer_all(svc, ctx, session.id, "")  # blank = "no parent" -> root

    with pytest.raises(ValidationError) as excinfo:
        svc.formalize(ctx, session.id)
    message = str(excinfo.value)
    assert "[I5]" in message
    assert "parent_id" in message

    after = architecture.list_architecture_elements(workspace.id, ctx)
    assert len(after) == before == 1, "the rejected create must leave no trace"
    assert [el.id for el in after] == [root.id]


def test_first_element_can_still_be_created_as_a_root(interview_setup) -> None:
    """parent_id is optional: with no root in the workspace, a blank answer
    creates the single root instead of failing."""
    _, workspace, ctx, architecture = interview_setup
    svc = InterviewService()
    session = svc.start(ctx, "ArchitectureElement", workspace.id)
    _answer_all(svc, ctx, session.id, "")

    result = svc.formalize(ctx, session.id)

    created = architecture.get_architecture_element(
        uuid.UUID(result["resulting_artifact_ids"][0]), ctx
    )
    assert created.parent_id is None
    assert len(architecture.list_architecture_elements(workspace.id, ctx)) == 1


def test_malformed_parent_answer_is_rejected_without_creating_an_element(interview_setup) -> None:
    _, workspace, ctx, architecture = interview_setup
    svc = InterviewService()
    session = svc.start(ctx, "ArchitectureElement", workspace.id)
    _answer_all(svc, ctx, session.id, "not-a-uuid")

    with pytest.raises(ValidationError) as excinfo:
        svc.formalize(ctx, session.id)
    assert "parent_id" in str(excinfo.value)
    assert architecture.list_architecture_elements(workspace.id, ctx) == []
