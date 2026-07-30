"""REQ-165/REQ-166: Goal/MainGoal workflow preset registration.

Pure in-memory checks against the module-level preset/registration dicts —
no DB access needed (mirrors the other *_default preset registration tests
in this package).

Note on deviations from the original task brief's sample: the brief's sample
used dict-shaped states (``{"name": ..., "is_initial": ...}``) and
``"from"``/``"to"`` transition keys, and assumed a ``_ENTITY_MODEL_MAP`` dict
in ``lifecycle_manager.py``. Neither matches this codebase's actual
conventions: ``PRESET_SCHEMAS[...]["states"]`` is a plain list[str] (consumed
as ``WorkflowDefinitionDTO.states: tuple[str, ...]``, with ``states[0]`` used
verbatim as ``initial_state``, and via ``set(...)`` in
``check_downgrade_compatibility``/``check_downgrade_compatibility``-adjacent
code), transitions use ``from_state``/``to_state``/``allowed_roles``/
``requires_change_reason``/``signature_gate`` keys (see e.g. ``adr_default``),
and the entity->model map used by ``StateLifecycleManager._sync_status_mirror``
is named ``_STATUS_MIRROR_MODELS``. This test follows the actual codebase
conventions so the registration is functionally correct for Task 4's
``initialize_workflow_states`` / transition flow, not just superficially
dict-shaped.
"""
from workflow.definition_store import PRESET_SCHEMAS
from workflow.services import _ENTITY_DEFAULT_PRESET
from workflow.lifecycle_manager import _STATUS_MIRROR_MODELS


def test_goal_default_preset_has_three_states():
    preset = PRESET_SCHEMAS["goal_default"]
    state_names = set(preset["states"])
    assert state_names == {"Entwurf", "Freigegeben", "Archiviert"}


def test_main_goal_default_preset_has_three_states():
    preset = PRESET_SCHEMAS["main_goal_default"]
    state_names = set(preset["states"])
    assert state_names == {"Entwurf", "Freigegeben", "Archiviert"}


def test_goal_and_main_goal_registered_in_entity_default_preset():
    assert _ENTITY_DEFAULT_PRESET["Goal"] == "goal_default"
    assert _ENTITY_DEFAULT_PRESET["MainGoal"] == "main_goal_default"


def test_goal_and_main_goal_registered_in_status_mirror_models():
    assert _STATUS_MIRROR_MODELS["Goal"] == ("application.models", "Goal")
    assert _STATUS_MIRROR_MODELS["MainGoal"] == ("application.models", "MainGoal")
