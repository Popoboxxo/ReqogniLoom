"""L1-001 — reconstruct from captured state, never from the live edited entity.

The delta index records ``Artifact.version``, which does not move when a
subtype row (Requirement, ArchitectureElement, …) is edited — see
``baseline.diff_engine`` and issue #398. A baseline therefore used to return the
LIVE, edited title as soon as a live entity still carried the recorded artifact
version. Since REQ-L2-BL-012 the baseline stores a full field-state snapshot;
this module pins that it is authoritative, and that the LRU cache cannot alias
two baselines that share an artifact version.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from baseline.types import ItemPayload
from baseline.version_reconstructor import LruPayloadCache, VersionReconstructor


class _StateStore:
    """Minimal BaselineStore stand-in with per-baseline captured states.

    ``versions`` lets a test force the same recorded ``Artifact.version`` for
    two different baselines — the collision shape of L1-001.
    """

    def __init__(
        self,
        states: dict[uuid.UUID, dict[str, dict | None]],
        versions: dict[uuid.UUID, int] | None = None,
    ) -> None:
        self._states = states
        self._versions = versions or {}

    def lookup_item_version(
        self, baseline_id: uuid.UUID, item_id: str, tenant_id: uuid.UUID
    ) -> int:
        return self._versions.get(baseline_id, 1)

    def load_states(
        self,
        baseline_id: uuid.UUID,
        tenant_id: uuid.UUID,
        item_ids: list[str] | None = None,
    ) -> dict[str, dict | None]:
        states = self._states[baseline_id]
        if item_ids is None:
            return dict(states)
        return {k: v for k, v in states.items() if k in item_ids}


def _live_payload(item_id: str, title: str, version: int = 9) -> ItemPayload:
    """Stand-in for a live/audit payload carrying a post-baseline edit."""
    return ItemPayload(item_id=item_id, version=version, title=title)


def test_edit_after_baseline_returns_the_captured_title() -> None:
    """(a) Baseline → edit Requirement title → old title is returned.

    Pre-fix the reconstructor trusted the live entity (its artifact version
    still matched) and returned ``"Edited after baseline"``.
    """
    tenant_id = uuid.uuid4()
    baseline_id = uuid.uuid4()
    item_id = str(uuid.uuid4())
    store = _StateStore(
        {
            baseline_id: {
                item_id: {
                    "title": "Title at baseline",
                    "description": "captured description",
                    "version": 3,
                }
            }
        }
    )
    reconstructor = VersionReconstructor(store=store)
    # These must never run on the state-first path.
    reconstructor._try_live_entity = MagicMock(
        return_value=_live_payload(item_id, "Edited after baseline")
    )
    reconstructor._load_from_audit_log = MagicMock(
        return_value=_live_payload(item_id, "Edited after baseline")
    )

    payload = reconstructor.get_item_at_baseline(baseline_id, item_id, tenant_id)

    assert payload.title == "Title at baseline"
    assert payload.description == "captured description"
    assert payload.version == 3  # entity version from the snapshot, not Artifact's
    reconstructor._try_live_entity.assert_not_called()
    reconstructor._load_from_audit_log.assert_not_called()


def test_two_baselines_same_artifact_version_keep_their_own_titles() -> None:
    """(b) Same artifact version, different captured titles → no cache alias.

    Both baselines record artifact version 1; their snapshots carry entity
    versions 3 and 4 with different titles. Pre-fix the cache was keyed only
    on ``(item_id, version)`` so the second lookup returned the first baseline's
    payload.
    """
    tenant_id = uuid.uuid4()
    baseline_a, baseline_b = uuid.uuid4(), uuid.uuid4()
    item_id = str(uuid.uuid4())
    store = _StateStore(
        {
            baseline_a: {item_id: {"title": "Title A", "version": 3}},
            baseline_b: {item_id: {"title": "Title B", "version": 4}},
        },
        versions={baseline_a: 1, baseline_b: 1},
    )
    reconstructor = VersionReconstructor(store=store)
    # Force the pre-fix failure to be an assertion about the wrong payload
    # rather than a missing-Django-model error in the fallback helpers.
    reconstructor._try_live_entity = MagicMock(
        return_value=_live_payload(item_id, "LIVE")
    )
    reconstructor._load_from_audit_log = MagicMock(
        return_value=_live_payload(item_id, "LIVE")
    )

    payload_a = reconstructor.get_item_at_baseline(baseline_a, item_id, tenant_id)
    payload_b = reconstructor.get_item_at_baseline(baseline_b, item_id, tenant_id)

    assert (payload_a.title, payload_b.title) == ("Title A", "Title B")
    assert (payload_a.version, payload_b.version) == (3, 4)


def test_cache_key_includes_baseline_id() -> None:
    """Direct cache-level pin of the L1-001 key change."""
    baseline_a, baseline_b = uuid.uuid4(), uuid.uuid4()
    item_id = str(uuid.uuid4())
    cache = LruPayloadCache()
    cache.put(_live_payload(item_id, "A", 1), baseline_id=baseline_a)
    cache.put(_live_payload(item_id, "B", 1), baseline_id=baseline_b)

    assert cache.get(item_id, 1, baseline_id=baseline_a).title == "A"
    assert cache.get(item_id, 1, baseline_id=baseline_b).title == "B"


def test_legacy_null_state_still_uses_audit_log_with_recorded_version() -> None:
    """A legacy (state NULL) entry keeps the fallback contract."""
    tenant_id = uuid.uuid4()
    baseline_id = uuid.uuid4()
    item_id = str(uuid.uuid4())
    store = _StateStore({baseline_id: {item_id: None}})
    reconstructor = VersionReconstructor(store=store)
    from_audit = _live_payload(item_id, "Historical title", 7)
    reconstructor._try_live_entity = MagicMock(return_value=None)
    reconstructor._load_from_audit_log = MagicMock(return_value=from_audit)

    payload = reconstructor.get_item_at_baseline(baseline_id, item_id, tenant_id)

    assert payload is from_audit
    reconstructor._load_from_audit_log.assert_called_once_with(item_id, 1, tenant_id)


@pytest.mark.django_db
def test_legacy_baseline_matches_artifact_version_not_entity_version() -> None:
    """Legacy (state NULL) baselines compare Artifact.version, not req.version.

    Regression for the L1-001 over-reach. The recorded delta-index version is
    ``Artifact.version``. Making ``_try_live_entity`` match the subtype's own
    ``version`` raised ``VersionNotFoundError`` for every legacy baseline whose
    ``req.version`` had moved independently of ``artifact.version`` (the normal
    #398 shape). Reaching the assertions below proves no such error is raised
    and the historical payload is returned. Entity-version matching belongs
    exclusively to the captured-state path.
    """
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant_id = uuid.uuid4()
    TenantContext.set_tenant(tenant_id)
    try:
        tenant = Tenant.objects.create(
            id=tenant_id, name="Legacy Tenant", slug="legacy-tenant"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="Legacy WS")
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            version=2,
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title="Title at baseline",
            version=9,  # deliberately != artifact.version
        )

        item_id = str(artifact.id)
        baseline_id = uuid.uuid4()
        store = _StateStore(
            {baseline_id: {item_id: None}},
            versions={baseline_id: artifact.version},
        )
        reconstructor = VersionReconstructor(store=store)

        payload = reconstructor.get_item_at_baseline(baseline_id, item_id, tenant_id)

        assert payload.title == "Title at baseline"
        assert payload.version == artifact.version
    finally:
        TenantContext.clear_tenant()
