"""Interview protocol configuration — spec §3.1."""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from application.interview_protocol import (
    INTERVIEW_PROTOCOL_DEFAULTS,
    ProtocolValidationError,
    get_protocol,
    parse_protocol_yaml,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import PromptTemplate, Tenant, User, Workspace

VALID_YAML = """\
phases:
  - name: elicitation
    required_fields:
      - name: title
        type: text
      - name: rationale
        type: textarea
    prompt_fragment: "Ask for the requirement's title and rationale."
  - name: approval
    prompt_fragment: "Present the drafted requirement for approval."
  - name: formalization
    prompt_fragment: "Confirm and formalize."
"""


class TestParseProtocolYaml:
    def test_parses_phases_and_fields(self):
        protocol = parse_protocol_yaml(VALID_YAML)

        assert [p.name for p in protocol.phases] == ["elicitation", "approval", "formalization"]
        elicitation = protocol.phases[0]
        assert [f.name for f in elicitation.required_fields] == ["title", "rationale"]
        assert elicitation.required_fields[1].type == "textarea"

    def test_field_type_defaults_to_text(self):
        protocol = parse_protocol_yaml(
            "phases:\n"
            "  - name: elicitation\n"
            "    required_fields:\n"
            "      - name: title\n"
            "    prompt_fragment: 'x'\n"
        )
        assert protocol.phases[0].required_fields[0].type == "text"

    def test_rejects_malformed_yaml(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("not: [valid, yaml: structure")

    def test_rejects_missing_phases_key(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("phase_list: []\n")

    def test_rejects_empty_phases_list(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("phases: []\n")

    def test_rejects_null_phases(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("phases:\n")

    def test_rejects_enum_field_without_choices(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml(
                "phases:\n"
                "  - name: elicitation\n"
                "    required_fields:\n"
                "      - name: element_type\n"
                "        type: enum\n"
                "    prompt_fragment: 'x'\n"
            )


class TestInterviewProtocolDefaults:
    @pytest.mark.parametrize(
        "artifact_type",
        [
            "Requirement", "ArchitectureElement", "StakeholderNeed", "Risk",
            "TestCase", "Adr", "Issue", "Goal",
        ],
    )
    def test_every_in_scope_artifact_type_has_a_default(self, artifact_type):
        name = f"interview.protocol.{artifact_type}"
        assert name in INTERVIEW_PROTOCOL_DEFAULTS
        # Must itself be valid YAML per the parser above -- a broken factory
        # default would silently break interview.start for every workspace
        # that never overrides it.
        parse_protocol_yaml(INTERVIEW_PROTOCOL_DEFAULTS[name])

    def test_main_goal_has_no_default(self):
        assert "interview.protocol.MainGoal" not in INTERVIEW_PROTOCOL_DEFAULTS


@pytest.fixture
def protocol_test_ctx(db):
    """Tenant + workspace + AuthContext for get_protocol tests."""
    tenant = Tenant.objects.create(name="Protocol Test", is_active=True)
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="Test Workspace"
    )
    user = User.objects.create(
        username="protocoluser", email="protocol@t.test", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield ctx, tenant, workspace
    finally:
        clear_request_tenant()


class TestGetProtocol:
    """Tests for the 3-level resolution chain in get_protocol."""

    def test_falls_back_to_factory_default_when_no_row_exists(self, protocol_test_ctx):
        """No PromptTemplate row → falls back to INTERVIEW_PROTOCOL_DEFAULTS."""
        ctx, tenant, workspace = protocol_test_ctx

        protocol = get_protocol(ctx, "Requirement", workspace.id)

        # Should resolve to factory default
        assert len(protocol.phases) == 3
        assert protocol.phases[0].name == "elicitation"
        assert [f.name for f in protocol.phases[0].required_fields] == ["title", "rationale"]

    def test_tenant_global_row_overrides_factory_default(self, protocol_test_ctx):
        """Tenant-global PromptTemplate row (workspace_id=None) wins over factory default."""
        ctx, tenant, workspace = protocol_test_ctx

        # Create a tenant-global override
        tenant_global_content = (
            "phases:\n"
            "  - name: custom_phase\n"
            "    prompt_fragment: 'Custom tenant-global protocol'\n"
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content=tenant_global_content,
            version=1,
            is_active=True,
            workspace_id=None,  # Tenant-global scope
        )

        protocol = get_protocol(ctx, "Requirement", workspace.id)

        # Should use the tenant-global row, not factory default
        assert len(protocol.phases) == 1
        assert protocol.phases[0].name == "custom_phase"

    def test_workspace_scoped_row_wins_over_all(self, protocol_test_ctx):
        """Workspace-scoped row wins over both tenant-global and factory default."""
        ctx, tenant, workspace = protocol_test_ctx

        # Create tenant-global override
        tenant_global_content = (
            "phases:\n"
            "  - name: tenant_phase\n"
            "    prompt_fragment: 'Tenant-global protocol'\n"
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content=tenant_global_content,
            version=1,
            is_active=True,
            workspace_id=None,
        )

        # Create workspace-scoped override
        workspace_content = (
            "phases:\n"
            "  - name: workspace_phase\n"
            "    prompt_fragment: 'Workspace-specific protocol'\n"
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content=workspace_content,
            version=2,
            is_active=True,
            workspace_id=workspace.id,  # Workspace-specific scope
        )

        protocol = get_protocol(ctx, "Requirement", workspace.id)

        # Should use the workspace-scoped row
        assert len(protocol.phases) == 1
        assert protocol.phases[0].name == "workspace_phase"

    def test_unknown_artifact_type_with_no_factory_default_raises_error(self, protocol_test_ctx):
        """Unknown artifact_type with no row and no factory default raises ProtocolValidationError."""
        ctx, tenant, workspace = protocol_test_ctx

        with pytest.raises(ProtocolValidationError) as exc_info:
            get_protocol(ctx, "UnknownArtifactType", workspace.id)

        assert "UnknownArtifactType" in str(exc_info.value)

    def test_invalid_yaml_in_db_row_raises_validation_error(self, protocol_test_ctx):
        """Even if a row exists, invalid YAML content raises ProtocolValidationError."""
        ctx, tenant, workspace = protocol_test_ctx

        # Create a row with invalid YAML
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content="phases: [1, 2, 3]",  # Invalid: list items must be dicts
            version=1,
            is_active=True,
            workspace_id=workspace.id,
        )

        # Even though the row exists, parsing should fail
        with pytest.raises(ProtocolValidationError):
            get_protocol(ctx, "Requirement", workspace.id)

    def test_tenant_global_used_when_workspace_id_is_none(self, protocol_test_ctx):
        """When workspace_id=None is passed, only tenant-global + factory default are checked."""
        ctx, tenant, workspace = protocol_test_ctx

        # Create tenant-global override
        tenant_global_content = (
            "phases:\n"
            "  - name: tenant_only_phase\n"
            "    prompt_fragment: 'Only accessible when workspace_id=None'\n"
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content=tenant_global_content,
            version=1,
            is_active=True,
            workspace_id=None,
        )

        # Create workspace-scoped row (should be ignored when workspace_id=None)
        workspace_content = (
            "phases:\n"
            "  - name: workspace_phase\n"
            "    prompt_fragment: 'Should not be used'\n"
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            name="interview.protocol.Requirement",
            content=workspace_content,
            version=2,
            is_active=True,
            workspace_id=workspace.id,
        )

        # Query with workspace_id=None
        protocol = get_protocol(ctx, "Requirement", None)

        # Should use tenant-global, not workspace-scoped
        assert protocol.phases[0].name == "tenant_only_phase"


class TestParseProtocolYamlEdgeCases:
    """Additional edge case tests for parse_protocol_yaml."""

    def test_rejects_list_items_that_are_not_dicts(self):
        """Non-dict list items (e.g., integers) should raise ProtocolValidationError."""
        malformed_yaml = "phases: [1, 2, 3]\n"
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml(malformed_yaml)
