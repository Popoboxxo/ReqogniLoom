"""Interview protocol configuration — spec §3.1."""
from __future__ import annotations

import pytest

from application.interview_protocol import (
    INTERVIEW_PROTOCOL_DEFAULTS,
    ProtocolValidationError,
    parse_protocol_yaml,
)

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
