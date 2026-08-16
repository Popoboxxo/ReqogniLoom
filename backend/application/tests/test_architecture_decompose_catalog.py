"""N1 decompose reads its prompt + caps from the catalog (spec §4)."""
from __future__ import annotations

import pytest

from application.architecture_decompose_service import (
    ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    ArchitectureDecomposeService,
)
from application.prompt_resolver import resolve_template_content
from application.prompt_slots import get_prompt_slots
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="AD Tenant", slug="ad-tenant")
    user = User.objects.create(username="ad-user", email="ad@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="AD WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _tree(breadth: int, depth: int) -> list:
    """Build a nested provider tree with *breadth* children on *depth* levels."""

    def _level(prefix: str, remaining: int) -> list:
        if remaining == 0:
            return []
        return [
            {
                "title": f"{prefix}{i}",
                "description": "d",
                "element_type": "component",
                "requirement": {"title": f"req {prefix}{i}"},
                "children": _level(f"{prefix}{i}.", remaining - 1),
            }
            for i in range(breadth)
        ]

    return _level("c", depth)


def test_the_decompose_prompt_is_a_registered_slot():
    assert "architecture_decompose_tree" in get_prompt_slots()


def test_the_slot_declares_element_title_as_its_data_variable():
    spec = get_prompt_slots()["architecture_decompose_tree"]

    assert spec.data_variables == ("element_title",)


def test_the_factory_body_references_the_two_config_caps():
    assert "{max_breadth}" in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{max_depth}" in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{breadth}" not in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{depth}" not in ARCH_DECOMPOSE_PROMPT_TEMPLATE


def test_the_caps_are_registered_config_variables():
    assert PROMPT_VARIABLE_DEFAULTS["max_breadth"].kind == "config"
    assert PROMPT_VARIABLE_DEFAULTS["max_breadth"].default_value == 5
    assert PROMPT_VARIABLE_DEFAULTS["max_depth"].default_value == 3


def test_the_slot_resolves_and_is_workspace_overridable(ctx_workspace):
    from application.prompt_template_versioning import publish_new_version

    ctx, workspace = ctx_workspace
    assert resolve_template_content(
        "architecture_decompose_tree", ctx, workspace.id
    ) == ARCH_DECOMPOSE_PROMPT_TEMPLATE

    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="architecture_decompose_tree",
        content="CUSTOM {element_title}",
        workspace_id=workspace.id,
    )

    assert (
        resolve_template_content("architecture_decompose_tree", ctx, workspace.id)
        == "CUSTOM {element_title}"
    )


def test_module_level_cap_constants_are_gone():
    import application.architecture_decompose_service as mod

    assert not hasattr(mod, "_MAX_BREADTH")
    assert not hasattr(mod, "_MAX_DEPTH")


def test_flatten_clamps_breadth_to_the_resolved_cap():
    nodes = ArchitectureDecomposeService()._flatten_tree(
        _tree(breadth=6, depth=1), max_breadth=2, max_depth=3
    )

    assert len(nodes) == 2


def test_flatten_clamps_depth_to_the_resolved_cap():
    nodes = ArchitectureDecomposeService()._flatten_tree(
        _tree(breadth=1, depth=4), max_breadth=5, max_depth=2
    )

    assert max(n.temp_id.count(".") for n in nodes) == 1


def test_the_prompt_carries_the_workspace_overridden_caps(ctx_workspace, monkeypatch):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_breadth", value=2, workspace_id=workspace.id
    )
    captured: dict = {}

    class _Provider:
        def complete(self, prompt, *, purpose, context):
            captured["prompt"] = prompt
            captured["context"] = context
            return "[]"

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda: _Provider()
    )

    ArchitectureDecomposeService()._complete_tree(
        ctx=ctx,
        workspace_id=workspace.id,
        element_title="Payment",
        max_breadth=2,
        max_depth=3,
        artifact_id="00000000-0000-0000-0000-000000000000",
    )

    assert "Payment" in captured["prompt"]
    assert "at most 2" in captured["prompt"]
    assert captured["context"]["max_breadth"] == 2
