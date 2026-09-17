"""SA-29 / SA-39 regressions — preset cache coherence and switch serialisation.

SA-29 (Systemaudit 2026-08-27 §4.1 #8): ``presets.gate`` memoises the resolved
tier and terminology mapping in module-level dicts. Invalidation used to be a
plain ``dict.pop`` in the process that performed the switch, so every *other*
Gunicorn/Celery worker kept serving the pre-switch configuration until it
restarted. A workspace downgraded to ``minimal`` on worker A therefore kept
offering Extended-only features on workers B..N — indefinitely, not for a TTL.

SA-39 (§4.1 #13): ``switch_preset`` is a read-modify-write. The *current* tier
decides whether the switch counts as a downgrade and therefore whether
``validate_downgrade`` runs at all, so a stale read is not merely a lost update.

"Another worker" is simulated the only way it can be in-process: by mutating the
database (and bumping the shared generation, which is what the real other worker
would do) *without* clearing this process's dicts. That is precisely the state a
second worker is in after a switch elsewhere.

req_id : REQ-L2-PC-013, REQ-L3-PC003-002, REQ-033
"""
from __future__ import annotations

import pytest
from django.core.cache import cache

from persistence import cache_generation as cachegen
from persistence.models import Tenant, Workspace
from presets import gate as gate_module
from presets.gate import FeatureGateService, _profile_cache, _tier_cache
from presets.models import WorkspacePresetConfig
from presets.registry import TIER_EXTENDED, TIER_MINIMAL, TIER_STANDARD
from presets.terminology import PROFILE_DEV_MODE, PROFILE_SE_MODE

from .conftest import active_tenant


@pytest.fixture(autouse=True)
def _isolated_caches():
    """Start every test with cold in-process caches and generation memo."""
    _tier_cache.clear()
    _profile_cache.clear()
    cachegen.reset_read_memo()
    cache.clear()
    yield
    _tier_cache.clear()
    _profile_cache.clear()
    cachegen.reset_read_memo()
    cache.clear()


@pytest.fixture(autouse=True)
def _no_generation_read_memo(monkeypatch):
    """Read the shared generation on every call.

    The 1s memo is a throughput optimisation, not part of the contract; leaving
    it on would make these tests assert the memo's timing rather than the
    invalidation itself.
    """
    monkeypatch.setattr(cachegen, "GENERATION_READ_TTL_SECONDS", 0.0)


@pytest.fixture
def gate() -> FeatureGateService:
    return FeatureGateService()


def _simulate_switch_on_another_worker(workspace, *, tier=None, profile=None):
    """Apply a switch the way a *different* process would.

    Two details make this a faithful simulation rather than a self-fulfilling one:

    * The row is written with a queryset ``.update()``, which does **not** emit
      ``post_save``. Using ``config.save()`` would fire
      ``application.cache_invalidation``'s handler *in this process*, popping the
      local dicts — so the test would pass even with the SA-29 fix reverted,
      because it would be observing local invalidation, not cross-worker
      invalidation.
    * The shared generation is bumped explicitly, which is what the other
      worker's ``_invalidate_workspace`` would have done over there.

    The result is precisely worker B's state: warm local caches, changed
    database, advanced shared counter.
    """
    fields = {}
    if tier is not None:
        fields["active_tier"] = tier
    if profile is not None:
        fields["terminology_profile"] = profile

    tier_before = dict(_tier_cache)
    profile_before = dict(_profile_cache)

    updated = WorkspacePresetConfig.unscoped.filter(workspace=workspace).update(
        **fields
    )
    assert updated == 1, "the preset config row to switch does not exist"

    assert _tier_cache == tier_before and _profile_cache == profile_before, (
        "the DB write cleared this process's caches — it fired a local "
        "invalidation signal, so the test would pass vacuously instead of "
        "observing cross-worker invalidation"
    )

    cachegen.bump_cache_generation(gate_module._CACHE_NAMESPACE, str(workspace.id))
    cachegen.reset_read_memo()


# ---------------------------------------------------------------------------
# SA-29 — cross-worker invalidation
# ---------------------------------------------------------------------------


def test_tier_cache_is_invalidated_by_a_switch_in_another_worker(
    gate, tenant, workspace_extended
) -> None:
    """A downgrade performed elsewhere must not keep serving Extended here.

    This is the security-adjacent half of SA-29: ``is_feature_enabled`` gates
    Extended-only functionality, so a stale cache keeps that functionality open
    on every worker that did not handle the switch.
    """
    with active_tenant(tenant):
        assert gate.get_preset(str(workspace_extended.id)).tier == TIER_EXTENDED
        assert str(workspace_extended.id) in _tier_cache, "cache did not warm"

        _simulate_switch_on_another_worker(workspace_extended, tier=TIER_MINIMAL)

        assert gate.get_preset(str(workspace_extended.id)).tier == TIER_MINIMAL, (
            "SA-29: this worker served a preset that another worker changed — "
            "the process-local cache has no cross-worker invalidation"
        )


def test_feature_gate_follows_the_cross_worker_downgrade(
    gate, tenant, workspace_extended
) -> None:
    """The observable consequence: a gated feature actually closes."""
    ws_key = str(workspace_extended.id)
    with active_tenant(tenant):
        extended_features = [
            key
            for key, enabled in gate.get_preset(ws_key).features.items()
            if enabled
        ]
        assert extended_features, "extended preset exposes no feature to test with"

        _simulate_switch_on_another_worker(workspace_extended, tier=TIER_MINIMAL)

        minimal = gate.get_preset(ws_key)
        newly_closed = [
            key for key in extended_features if not minimal.features.get(key, False)
        ]
        assert newly_closed, (
            "the minimal tier enables everything extended does — pick a "
            "different fixture, this test cannot observe the downgrade"
        )
        for key in newly_closed:
            assert gate.is_feature_enabled(key, ws_key) is False


def test_terminology_cache_is_invalidated_by_another_worker(
    gate, tenant, workspace_extended
) -> None:
    """Same guarantee for the terminology profile cache."""
    ws_key = str(workspace_extended.id)
    with active_tenant(tenant):
        assert gate.get_terminology(ws_key) is not None
        assert ws_key in _profile_cache, "cache did not warm"

        _simulate_switch_on_another_worker(
            workspace_extended, profile=PROFILE_DEV_MODE
        )

        mapping = gate.get_terminology(ws_key)
        assert mapping.profile_name == PROFILE_DEV_MODE, (
            "SA-29: stale terminology profile served after a switch elsewhere"
        )


def test_unrelated_workspaces_keep_their_cache(
    gate, tenant, workspace_extended, workspace_minimal
) -> None:
    """The generation is per workspace — a switch must not flush everything.

    Guards against "fixing" SA-29 by turning the cache off, which would trade a
    correctness bug for a latency regression on every request (REQ-L2-PC-013).
    """
    other_key = str(workspace_minimal.id)
    with active_tenant(tenant):
        gate.get_preset(other_key)
        cached_entry = _tier_cache[other_key]

        _simulate_switch_on_another_worker(workspace_extended, tier=TIER_STANDARD)

        gate.get_preset(other_key)
        assert _tier_cache[other_key] is cached_entry, (
            "an unrelated workspace's cache entry was discarded"
        )


def test_local_switch_is_visible_immediately(gate, tenant, workspace_extended) -> None:
    """The switching worker itself must not wait out the generation memo.

    ``_invalidate_workspace`` pops locally *and* bumps; this pins the local half,
    which the memo optimisation could otherwise mask.
    """
    ws_key = str(workspace_extended.id)
    with active_tenant(tenant):
        assert gate.get_preset(ws_key).tier == TIER_EXTENDED
        gate.switch_preset(ws_key, TIER_STANDARD)
        assert gate.get_preset(ws_key).tier == TIER_STANDARD


def test_generation_bump_is_recorded_in_the_shared_cache(
    gate, tenant, workspace_extended
) -> None:
    """The counter really lives in the shared backend, not in a local dict.

    If the bump did not reach ``django.core.cache``, every assertion above would
    still pass in-process while changing nothing for the other workers — the
    exact failure mode SA-29 describes.
    """
    ws_key = str(workspace_extended.id)
    namespace = gate_module._CACHE_NAMESPACE
    before = cachegen.cache_generation(namespace, ws_key)

    with active_tenant(tenant):
        gate.switch_preset(ws_key, TIER_STANDARD)

    cachegen.reset_read_memo()
    assert cachegen.cache_generation(namespace, ws_key) > before


def test_cache_generation_failure_does_not_break_reads(
    gate, tenant, workspace_extended, monkeypatch
) -> None:
    """A cache backend outage degrades to the old behaviour, it does not 500."""
    ws_key = str(workspace_extended.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(cache, "get", _boom)
    monkeypatch.setattr(cache, "add", _boom)

    with active_tenant(tenant):
        assert gate.get_preset(ws_key).tier == TIER_EXTENDED


# ---------------------------------------------------------------------------
# SA-39 — switch_preset serialisation
# ---------------------------------------------------------------------------


def test_switch_preset_locks_the_config_row(
    gate, tenant, workspace_extended, monkeypatch
) -> None:
    """The read-modify-write must run against a ``FOR UPDATE`` row.

    Asserted structurally rather than by racing two threads: the lock is what
    makes the downgrade decision (which reads ``active_tier``) trustworthy, and
    a future refactor that drops it would otherwise be invisible.

    Only the *first* read must lock. On the downgrade path ``validate_downgrade``
    re-reads the same row for its policy field; that read is unlocked by design
    and safe, because it runs inside the transaction that already holds the lock.
    """
    calls: list[bool] = []
    real_get_or_create = gate_module._get_or_create_preset_config

    def _record(workspace_id, *, for_update=False):
        calls.append(for_update)
        return real_get_or_create(workspace_id, for_update=for_update)

    monkeypatch.setattr(gate_module, "_get_or_create_preset_config", _record)

    with active_tenant(tenant):
        gate.switch_preset(str(workspace_extended.id), TIER_STANDARD)

    assert calls and calls[0] is True, (
        "SA-39: switch_preset read the preset config without locking it "
        f"(lock flags in call order: {calls})"
    )


def test_switch_terminology_profile_locks_the_config_row(
    gate, tenant, workspace_extended, monkeypatch
) -> None:
    """Same for the terminology switch — identical read-modify-write shape."""
    calls: list[bool] = []
    real_get_or_create = gate_module._get_or_create_preset_config

    def _record(workspace_id, *, for_update=False):
        calls.append(for_update)
        return real_get_or_create(workspace_id, for_update=for_update)

    monkeypatch.setattr(gate_module, "_get_or_create_preset_config", _record)

    with active_tenant(tenant):
        gate.switch_terminology_profile(
            str(workspace_extended.id), PROFILE_SE_MODE
        )

    assert calls and calls[0] is True, (
        f"SA-39: switch_terminology_profile did not lock (call order: {calls})"
    )


def test_read_path_does_not_take_a_lock(
    gate, tenant, workspace_extended, monkeypatch
) -> None:
    """``get_preset`` runs on nearly every request and must stay lock-free."""
    calls: list[bool] = []
    real_get_or_create = gate_module._get_or_create_preset_config

    def _record(workspace_id, *, for_update=False):
        calls.append(for_update)
        return real_get_or_create(workspace_id, for_update=for_update)

    monkeypatch.setattr(gate_module, "_get_or_create_preset_config", _record)

    with active_tenant(tenant):
        gate.get_preset(str(workspace_extended.id))

    assert calls == [False], "the hot read path must not lock the config row"


def test_switch_preset_still_enforces_the_downgrade_policy(
    gate, tenant, workspace_extended
) -> None:
    """Locking must not change the downgrade semantics (REQ-L2-PC-011)."""
    from baseline.models import BaselineSnapshot
    from presets.exceptions import DowngradeBlockedError

    ws_key = str(workspace_extended.id)
    BaselineSnapshot.unscoped.create(
        tenant=tenant,
        workspace_id=workspace_extended.id,
        name="global baseline",
        scope="global",
    )

    with active_tenant(tenant):
        with pytest.raises(DowngradeBlockedError):
            gate.switch_preset(ws_key, TIER_STANDARD)

        # ...and the blocked switch must not have been persisted.
        assert gate.get_preset(ws_key).tier == TIER_EXTENDED
