"""The status mirror is gone (Datenmodell-Konsolidierung Phase 1)."""
import inspect

import pytest

from workflow import lifecycle_manager
from workflow.lifecycle_manager import StateLifecycleManager


def test_mirror_map_is_removed():
    assert not hasattr(lifecycle_manager, "_STATUS_MIRROR_MODELS")
    assert not hasattr(lifecycle_manager, "_LAYER2_MODEL_MODULES")
    assert not hasattr(lifecycle_manager, "_resolve_mirror_model")


def test_sync_method_is_removed():
    assert not hasattr(StateLifecycleManager, "_sync_status_mirror")


def test_lifecycle_mirror_still_exists_until_phase_4():
    assert hasattr(lifecycle_manager, "_LIFECYCLE_MIRROR_MODELS")
    assert hasattr(StateLifecycleManager, "_sync_lifecycle_mirror")


def test_no_module_references_the_map():
    source = inspect.getsource(lifecycle_manager)
    assert "_STATUS_MIRROR_MODELS" not in source
