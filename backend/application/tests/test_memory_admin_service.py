"""Tests for MemoryAdminService (Memory Admin UI Phase 1 + Phase 5)."""
import numpy as np
import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.memory_admin_service import (
    MemoryAdminService,
    _deterministic_sample,
)
from auth_tenancy.models import TenantRole
from memory.backends import get_memory_backend
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)

_EMBEDDING_DIM = 384


def _unit_vector(index: int, *, tilt: float = 0.0, tilt_index: int = 1) -> list[float]:
    """Return a 384-dim one-hot vector, optionally tilted towards another axis.

    ``tilt=0`` gives axis-aligned vectors, which are mutually orthogonal
    (cosine similarity 0 — far below ``CLUSTER_SIMILARITY_THRESHOLD``). A
    small ``tilt`` produces a near-identical neighbour (cosine ~0.999).
    """
    vec = [0.0] * _EMBEDDING_DIM
    vec[index] = 1.0
    if tilt:
        vec[tilt_index] = tilt
    return vec


def _system_admin_ctx(tenant):
    admin_user = make_user(tenant)
    TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
    return ctx_for_user(tenant, admin_user, roles=("admin",))


def _make_ws_memory(tenant, workspace, content, *, embedding=None):
    return WorkspaceMemory.objects.create(
        tenant=tenant, workspace=workspace, content=content, embedding=embedding
    )


def _make_user_memory(tenant, user, content, *, embedding=None):
    return UserTenantMemory.objects.create(
        tenant=tenant, user=user, content=content, embedding=embedding
    )


@pytest.mark.django_db
class TestMemoryAdminServiceListOverview:
    def test_lists_workspace_with_zero_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Empty WS")
            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["workspace_name"] == "Empty WS"
            assert row["enabled"] is True
            assert row["workspace_entry_count"] == 0
            assert row["user_entry_count"] == 0
            assert row["last_consolidated_at"] is None

    def test_counts_both_tiers_and_respects_disabled_flag(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Busy WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            WorkspaceMemorySettings.objects.create(tenant=tenant, workspace=ws, enabled=False)

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact one")
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact two")
            backend.upsert(tenant.id, "user", member.id, "user fact one")

            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["enabled"] is False
            assert row["workspace_entry_count"] == 2
            assert row["user_entry_count"] == 1
            assert row["last_consolidated_at"] is not None

    def test_excludes_non_member_user_memory(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Isolated WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)  # never assigned a role in ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "user", member.id, "member fact")
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["user_entry_count"] == 1

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_workspace_overview(ctx)

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        """A ``UserRole(role="admin")`` in ONE workspace (no ``TenantRole``
        anywhere) must NOT satisfy the System-Admin check — regression test
        for the workspace_scope narrowing bug (see
        ``MemoryAdminService._assert_system_admin``'s docstring).
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("admin",))

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_workspace_overview(ctx)


@pytest.mark.django_db
class TestMemoryAdminServiceDelete:
    def test_deletes_both_tiers_for_current_members_only(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)  # not a member of ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            backend.upsert(tenant.id, "user", member.id, "member fact")
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            result = MemoryAdminService().delete_workspace_memory(ctx, ws.id)

            assert result["workspace_memory_deleted"] == 1
            assert result["user_memory_deleted"] == 1
            assert WorkspaceMemory.objects.filter(workspace_id=ws.id).count() == 0
            assert UserTenantMemory.objects.filter(user_id=member.id).count() == 0
            # Outsider's memory is untouched.
            assert UserTenantMemory.objects.filter(user_id=outsider.id).count() == 1

    def test_raises_not_found_for_unknown_workspace(self):
        with active_tenant() as tenant:
            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))
            import uuid

            with pytest.raises(NotFoundError):
                MemoryAdminService().delete_workspace_memory(ctx, uuid.uuid4())

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().delete_workspace_memory(ctx, ws.id)

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        """A ``UserRole(role="admin")`` in ONE workspace (no ``TenantRole``
        anywhere) must NOT satisfy the System-Admin check — regression test
        for the workspace_scope narrowing bug (see
        ``MemoryAdminService._assert_system_admin``'s docstring).
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("admin",))

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().delete_workspace_memory(ctx, ws.id)

    def test_suspended_member_excluded_from_delete(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            suspended_member = make_user(tenant)
            assign_role(suspended_member, ws, "editor", suspended=True)

            backend = get_memory_backend()
            backend.upsert(tenant.id, "user", suspended_member.id, "suspended member fact")

            admin_user = make_user(tenant)
            TenantRole.unscoped.create(tenant=tenant, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            result = MemoryAdminService().delete_workspace_memory(ctx, ws.id)

            assert result["user_memory_deleted"] == 0
            assert UserTenantMemory.objects.filter(user_id=suspended_member.id).count() == 1

    def test_delete_does_not_touch_other_tenant_workspace(self):
        other_ws_id = None

        # Create workspace in tenant_b first
        with active_tenant() as tenant_b:
            other_ws = make_workspace(tenant_b)
            other_ws_id = other_ws.id

        # Then try to delete it as admin in tenant_a
        with active_tenant() as tenant_a:
            admin_user = make_user(tenant_a)
            TenantRole.unscoped.create(tenant=tenant_a, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = ctx_for_user(tenant_a, admin_user, roles=("admin",))

            with pytest.raises(NotFoundError):
                MemoryAdminService().delete_workspace_memory(ctx, other_ws_id)


@pytest.mark.django_db
class TestMemoryAdminServiceListEntries:
    """``list_entries`` — Memory Admin UI Phase 5 (spec 2026-08-26)."""

    def test_workspace_scope_returns_both_tiers_for_members_only(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Target WS")
            other_ws = make_workspace(tenant, name="Other WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)

            _make_ws_memory(tenant, ws, "target workspace fact")
            _make_ws_memory(tenant, other_ws, "other workspace fact")
            _make_user_memory(tenant, member, "member fact")
            _make_user_memory(tenant, outsider, "outsider fact")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(ctx, scope="workspace", workspace_id=ws.id)

            contents = {row["content"] for row in page["results"]}
            assert contents == {"target workspace fact", "member fact"}
            assert page["count"] == 2

    def test_owner_labels_are_workspace_name_and_user_email(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Labelled WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")

            _make_ws_memory(tenant, ws, "ws fact")
            _make_user_memory(tenant, member, "user fact")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(ctx, scope="workspace", workspace_id=ws.id)

            by_type = {row["owner_type"]: row for row in page["results"]}
            assert by_type["workspace"]["owner_label"] == "Labelled WS"
            assert by_type["workspace"]["owner_id"] == str(ws.id)
            assert by_type["user"]["owner_label"] == member.email
            assert by_type["user"]["owner_id"] == str(member.id)

    def test_global_scope_returns_every_live_entry_in_tenant(self):
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            unrelated_user = make_user(tenant)  # member of no workspace

            _make_ws_memory(tenant, ws_a, "a fact")
            _make_ws_memory(tenant, ws_b, "b fact")
            _make_user_memory(tenant, unrelated_user, "orphan user fact")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(ctx, scope="global")

            assert page["count"] == 3
            assert {row["content"] for row in page["results"]} == {
                "a fact",
                "b fact",
                "orphan user fact",
            }

    def test_global_scope_never_crosses_tenant_boundary(self):
        with active_tenant() as other_tenant:
            other_ws = make_workspace(other_tenant)
            _make_ws_memory(other_tenant, other_ws, "foreign tenant fact")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _make_ws_memory(tenant, ws, "own tenant fact")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(ctx, scope="global")

            assert page["count"] == 1
            assert page["results"][0]["content"] == "own tenant fact"

    def test_q_filters_content_case_insensitively(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")

            _make_ws_memory(tenant, ws, "Prefers DARK mode")
            _make_ws_memory(tenant, ws, "Uses metric units")
            _make_user_memory(tenant, member, "dark theme for the editor")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(
                ctx, scope="workspace", workspace_id=ws.id, q="dark"
            )

            assert page["count"] == 2
            assert {row["content"] for row in page["results"]} == {
                "Prefers DARK mode",
                "dark theme for the editor",
            }

    def test_superseded_entries_are_excluded(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            newer = _make_ws_memory(tenant, ws, "the current fact")
            older = _make_ws_memory(tenant, ws, "the outdated fact")
            older.superseded_by = newer
            older.save(update_fields=["superseded_by"])

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(ctx, scope="workspace", workspace_id=ws.id)

            assert page["count"] == 1
            assert page["results"][0]["content"] == "the current fact"

    def test_pagination_splits_results_without_overlap(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            for i in range(5):
                _make_ws_memory(tenant, ws, f"fact {i}")

            ctx = _system_admin_ctx(tenant)
            service = MemoryAdminService()
            first = service.list_entries(
                ctx, scope="workspace", workspace_id=ws.id, page=1, page_size=2
            )
            second = service.list_entries(
                ctx, scope="workspace", workspace_id=ws.id, page=2, page_size=2
            )
            third = service.list_entries(
                ctx, scope="workspace", workspace_id=ws.id, page=3, page_size=2
            )

            assert [first["count"], second["count"], third["count"]] == [5, 5, 5]
            assert len(first["results"]) == 2
            assert len(second["results"]) == 2
            assert len(third["results"]) == 1
            ids = [row["id"] for page in (first, second, third) for row in page["results"]]
            assert len(set(ids)) == 5

    def test_page_beyond_last_returns_empty_results_but_full_count(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _make_ws_memory(tenant, ws, "only fact")

            ctx = _system_admin_ctx(tenant)
            page = MemoryAdminService().list_entries(
                ctx, scope="workspace", workspace_id=ws.id, page=9, page_size=25
            )

            assert page["results"] == []
            assert page["count"] == 1

    def test_out_of_range_page_never_fetches_rows(self):
        """The out-of-range short-circuit is also the bound on the per-tier
        ``[:end]`` slice: without it a huge ``page`` would make ``end`` an
        effectively unbounded LIMIT and load the whole table into Python.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            for i in range(3):
                _make_ws_memory(tenant, ws, f"fact {i}")
            ctx = _system_admin_ctx(tenant)

            with CaptureQueriesContext(connection) as captured:
                page = MemoryAdminService().list_entries(
                    ctx, scope="global", page=10_000_000, page_size=200
                )

            assert page["results"] == []
            assert page["count"] == 3
            # The two COUNT(*) queries never select the content column; a row
            # fetch would. Anchored on the memory tables so an unrelated
            # auth/tenant lookup cannot satisfy the assertion by accident.
            row_fetches = [
                sql
                for sql in (q["sql"] for q in captured.captured_queries)
                if "mem_workspace_memory" in sql or "mem_user_tenant_memory" in sql
                if "content" in sql
            ]
            assert row_fetches == []

    def test_workspace_scope_without_workspace_id_raises_validation_error(self):
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            with pytest.raises(ValidationError):
                MemoryAdminService().list_entries(ctx, scope="workspace")

    def test_unknown_scope_raises_validation_error(self):
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            with pytest.raises(ValidationError):
                MemoryAdminService().list_entries(ctx, scope="galaxy")

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_entries(ctx, scope="workspace", workspace_id=ws.id)

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("admin",))

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_entries(ctx, scope="global")


class TestDeterministicSample:
    """Pure-function sampling helper (Phase 5 plan Ruling 9) — unit-tested in
    isolation so the >5000-entry path needs no 5000-row DB fixture.
    """

    def test_returns_input_untouched_below_limit(self):
        rows = list(range(10))
        sample, sampled = _deterministic_sample(rows, 10)
        assert sample == rows
        assert sampled is False

    def test_takes_every_nth_row_above_limit(self):
        rows = list(range(10))
        sample, sampled = _deterministic_sample(rows, 5)
        assert sampled is True
        assert sample == [0, 2, 4, 6, 8]

    def test_never_exceeds_the_limit_for_awkward_ratios(self):
        for total in (5001, 7777, 10001, 123457):
            sample, sampled = _deterministic_sample(list(range(total)), 5000)
            assert sampled is True
            assert len(sample) <= 5000

    def test_is_deterministic_across_calls(self):
        rows = list(range(1000))
        assert _deterministic_sample(rows, 300)[0] == _deterministic_sample(rows, 300)[0]

    def test_does_not_undersample_just_above_the_limit(self):
        # Regression: a ceil-rounded stride previously halved the sample
        # (~2501 rows) the moment total exceeded max_size by even one row.
        sample, sampled = _deterministic_sample(list(range(5001)), 5000)
        assert sampled is True
        assert len(sample) == 5000


@pytest.mark.django_db
class TestMemoryAdminServiceProjection:
    """``get_projection`` — Memory Admin UI Phase 5 (spec 2026-08-26).

    Assertions target cluster membership and relative structure only, never
    absolute ``x``/``y`` values: the sign of an SVD singular vector is not
    deterministic across numpy/BLAS builds, so a coordinate snapshot would be
    flaky (Phase 5 plan Global Constraints).
    """

    def test_similar_vectors_cluster_together_dissimilar_one_apart(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            near_a = _make_ws_memory(tenant, ws, "near a", embedding=_unit_vector(0))
            near_b = _make_ws_memory(
                tenant, ws, "near b", embedding=_unit_vector(0, tilt=0.05)
            )
            far = _make_ws_memory(tenant, ws, "far", embedding=_unit_vector(200))

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            clusters = {p["id"]: p["cluster_id"] for p in result["points"]}
            assert clusters[str(near_a.id)] == clusters[str(near_b.id)]
            assert clusters[str(far.id)] != clusters[str(near_a.id)]
            assert result["total_size"] == 3
            assert result["sampled"] is False
            assert result["excluded_no_embedding"] == 0

    def test_projection_places_similar_points_closer_than_dissimilar_ones(self):
        """Relative-distance check — still no absolute-coordinate assertion."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            near_a = _make_ws_memory(tenant, ws, "near a", embedding=_unit_vector(0))
            near_b = _make_ws_memory(
                tenant, ws, "near b", embedding=_unit_vector(0, tilt=0.05)
            )
            far = _make_ws_memory(tenant, ws, "far", embedding=_unit_vector(200))

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )
            coords = {p["id"]: np.array([p["x"], p["y"]]) for p in result["points"]}

            near_distance = np.linalg.norm(coords[str(near_a.id)] - coords[str(near_b.id)])
            far_distance = np.linalg.norm(coords[str(near_a.id)] - coords[str(far.id)])
            assert near_distance < far_distance

    def test_entries_without_embedding_are_excluded_and_counted(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            embedded = _make_ws_memory(tenant, ws, "embedded", embedding=_unit_vector(0))
            _make_ws_memory(tenant, ws, "not embedded yet", embedding=None)

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert [p["id"] for p in result["points"]] == [str(embedded.id)]
            assert result["excluded_no_embedding"] == 1
            assert result["total_size"] == 1

    def test_superseded_entries_are_excluded(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            live = _make_ws_memory(tenant, ws, "live", embedding=_unit_vector(0))
            stale = _make_ws_memory(tenant, ws, "stale", embedding=_unit_vector(5))
            stale.superseded_by = live
            stale.save(update_fields=["superseded_by"])

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert [p["id"] for p in result["points"]] == [str(live.id)]

    def test_empty_dataset_returns_no_points(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _system_admin_ctx(tenant)

            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert result == {
                "points": [],
                "sampled": False,
                "sample_size": 0,
                "total_size": 0,
                "excluded_no_embedding": 0,
            }

    def test_single_entry_short_circuits_without_svd(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            only = _make_ws_memory(tenant, ws, "only", embedding=_unit_vector(3))
            ctx = _system_admin_ctx(tenant)

            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert result["points"] == [
                {
                    "id": str(only.id),
                    "x": 0.0,
                    "y": 0.0,
                    "cluster_id": 0,
                    "owner_type": "workspace",
                    "owner_id": str(ws.id),
                    "owner_label": ws.name,
                }
            ]

    def test_sampling_reports_sample_and_total_size(self, monkeypatch):
        """Uses a monkeypatched cap instead of seeding 5000 real rows — the
        sampling maths itself is covered by ``TestDeterministicSample``.
        """
        monkeypatch.setattr(
            "application.memory_admin_service.MAX_PROJECTION_POINTS", 2, raising=True
        )
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            for i in range(5):
                _make_ws_memory(tenant, ws, f"fact {i}", embedding=_unit_vector(i * 10))

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert result["sampled"] is True
            assert result["total_size"] == 5
            assert result["sample_size"] == 2
            assert len(result["points"]) == 2

    def test_both_tiers_appear_with_owner_labels(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Mixed WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            _make_ws_memory(tenant, ws, "ws fact", embedding=_unit_vector(0))
            _make_user_memory(tenant, member, "user fact", embedding=_unit_vector(100))

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            labels = {p["owner_type"]: p["owner_label"] for p in result["points"]}
            assert labels == {"workspace": "Mixed WS", "user": member.email}

    def test_cache_is_invalidated_by_a_new_entry(self):
        """The watermark in the cache key must react to a changed dataset —
        otherwise the 300s TTL would hide brand-new entries entirely.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _make_ws_memory(tenant, ws, "first", embedding=_unit_vector(0))
            ctx = _system_admin_ctx(tenant)
            service = MemoryAdminService()

            first = service.get_projection(ctx, scope="workspace", workspace_id=ws.id)
            assert first["total_size"] == 1

            _make_ws_memory(tenant, ws, "second", embedding=_unit_vector(50))
            second = service.get_projection(ctx, scope="workspace", workspace_id=ws.id)

            assert second["total_size"] == 2

    def test_workspace_scope_excludes_non_member_user_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)
            _make_user_memory(tenant, member, "member fact", embedding=_unit_vector(0))
            _make_user_memory(tenant, outsider, "outsider fact", embedding=_unit_vector(1))

            ctx = _system_admin_ctx(tenant)
            result = MemoryAdminService().get_projection(
                ctx, scope="workspace", workspace_id=ws.id
            )

            assert [p["owner_id"] for p in result["points"]] == [str(member.id)]

    def test_unknown_scope_raises_validation_error(self):
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            with pytest.raises(ValidationError):
                MemoryAdminService().get_projection(ctx, scope="nowhere")

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().get_projection(ctx, scope="workspace", workspace_id=ws.id)

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("admin",))

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().get_projection(ctx, scope="global")
