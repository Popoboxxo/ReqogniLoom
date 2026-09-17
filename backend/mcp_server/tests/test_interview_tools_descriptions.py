"""The formalize tool description must not tell agents a working type is unsupported."""
from mcp_server.tools.interview import InterviewToolGroup


def _descriptions() -> dict:
    return {t["name"]: t["description"] for t in InterviewToolGroup().get_tool_schemas()}


def test_formalize_description_does_not_claim_requirement_only():
    text = _descriptions()["interview.formalize"]
    assert "Requirement only" not in text
    assert "only Requirement" not in text
    assert "so far" not in text


def test_formalize_description_names_the_supported_types():
    text = _descriptions()["interview.formalize"]
    for artifact_type in ("Requirement", "Risk", "Adr", "Goal"):
        assert artifact_type in text


def test_set_target_description_still_states_the_requirement_only_update_branch():
    """set_target IS still Requirement-only by design -- the description must
    keep saying so, and must not be swept up by the formalize fix."""
    text = _descriptions()["interview.set_target"]
    assert "Requirement" in text
