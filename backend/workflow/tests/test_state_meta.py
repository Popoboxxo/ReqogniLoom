from workflow.definition_store import get_state_meta


def test_get_state_meta_returns_flag_when_present():
    workflow_json = {
        "states": ["draft", "deprecated"],
        "transitions": [],
        "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
    }
    assert get_state_meta(workflow_json, "deprecated") == {"is_outdated_equivalent": True}


def test_get_state_meta_defaults_to_false_when_state_meta_missing():
    workflow_json = {"states": ["draft", "done"], "transitions": []}
    assert get_state_meta(workflow_json, "done") == {"is_outdated_equivalent": False}


def test_get_state_meta_defaults_to_false_for_unlisted_state():
    workflow_json = {
        "states": ["draft", "approved"],
        "transitions": [],
        "state_meta": {"approved": {"is_outdated_equivalent": False}},
    }
    assert get_state_meta(workflow_json, "draft") == {"is_outdated_equivalent": False}
