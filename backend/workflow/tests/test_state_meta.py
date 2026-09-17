from workflow.definition_store import PRESET_SCHEMAS, get_state_meta


def test_get_state_meta_returns_flag_when_present():
    workflow_json = {
        "states": ["draft", "deprecated"],
        "transitions": [],
        "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
    }
    assert get_state_meta(workflow_json, "deprecated") == {
        "is_outdated_equivalent": True,
        "auto_approve_target": False,
    }


def test_get_state_meta_defaults_to_false_when_state_meta_missing():
    workflow_json = {"states": ["draft", "done"], "transitions": []}
    assert get_state_meta(workflow_json, "done") == {
        "is_outdated_equivalent": False,
        "auto_approve_target": False,
    }


def test_get_state_meta_defaults_to_false_for_unlisted_state():
    workflow_json = {
        "states": ["draft", "approved"],
        "transitions": [],
        "state_meta": {"approved": {"is_outdated_equivalent": False}},
    }
    assert get_state_meta(workflow_json, "draft") == {
        "is_outdated_equivalent": False,
        "auto_approve_target": False,
    }


def test_get_state_meta_returns_auto_approve_target_flag_when_present():
    """Phase 3: auto_approve_target is a distinct key alongside
    is_outdated_equivalent, and each state's meta entry merges cleanly with
    the shared defaults."""
    workflow_json = {
        "states": ["Draft", "In Review", "Approved"],
        "transitions": [],
        "state_meta": {"Approved": {"auto_approve_target": True}},
    }
    assert get_state_meta(workflow_json, "Approved") == {
        "is_outdated_equivalent": False,
        "auto_approve_target": True,
    }
    assert get_state_meta(workflow_json, "Draft") == {
        "is_outdated_equivalent": False,
        "auto_approve_target": False,
    }


def test_issue_default_preset_marks_resolved_as_auto_approve_target():
    """GH-370: review.approve() on an Issue must move it towards being
    fixed ("Resolved"), never towards the reject-equivalent "Wontfix" state.
    Mirrors adr_default's "Approved" and risk_default's "Mitigated"."""
    issue_default = PRESET_SCHEMAS["issue_default"]
    assert get_state_meta(issue_default, "Resolved") == {
        "is_outdated_equivalent": False,
        "auto_approve_target": True,
    }
    # Wontfix stays a rejection-equivalent state -- never the approve target.
    assert get_state_meta(issue_default, "Wontfix") == {
        "is_outdated_equivalent": True,
        "auto_approve_target": False,
    }
