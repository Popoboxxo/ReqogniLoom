"""T-A3-3: TraceLink and Icd are searchable (fulltext + lexical + semantic).

Both types are in :data:`SEARCHABLE_ARTIFACT_TYPES` now, so ``artifact.search``
can return them:

* ``Icd`` — ``icd_icd``, title ``name``, description ``semantic_description``;
* ``TraceLink`` — ``pl_tracelink`` joined to both endpoint artifacts, workspace
  scoped through the *source* artifact, with a synthetic
  ``<link_type>: <source uid> → <target uid>`` title.

Two rules that only apply to these two ``_TableSpec`` paths are pinned here:

* every hit is checked for READ through :class:`EffectivePermissionService`
  (item-level ``none`` rules must drop it) and soft-deleted rows are dropped;
* the **target** uid of a TraceLink is only shown when the caller holds READ in
  the target workspace — otherwise the synthetic title carries ``'—'``.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from application.search_service import SEARCHABLE_ARTIFACT_TYPES, SearchService
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, TraceLink
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

_ICD_NAME = "Power Bus Interface"
_ICD_DESCRIPTION = "Delivers the 48V rail from the battery to the motor inverter."


def _make_icd(tenant, workspace, *, name=_ICD_NAME, description=_ICD_DESCRIPTION):
    """Create an Icd with its backing Artifact (required for permission checks)."""
    from icd.models import Icd

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Icd"
    )
    return Icd.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace_id=workspace.id,
        name=name,
        semantic_description=description,
        source_element_id=uuid4(),
        target_element_id=uuid4(),
    )


def _make_link(tenant, source_req, target_req, *, link_type="references"):
    """Create a TraceLink between two Requirements' backing Artifacts."""
    return TraceLink.objects.create(
        tenant=tenant,
        source_id=source_req.artifact_id,
        target_id=target_req.artifact_id,
        link_type=link_type,
    )


@pytest.mark.django_db
class TestTraceLinkAndIcdSearchable:
    def test_icd_searchable_by_name_and_semantic(self, monkeypatch):
        """The ICD is findable by its interface name (lexical) and by its
        embedding (semantic), i.e. both new passes reach the new _TableSpec."""
        vector = [0.4] * EMBEDDING_VECTOR_DIMENSIONS
        monkeypatch.setattr(
            "application.search_service.generate_embedding", lambda text: vector
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            icd = _make_icd(tenant, ws)
            icd.embedding = vector
            icd.save(update_fields=["embedding"])

            by_name = SearchService().search(
                "Power Bus",
                ctx,
                workspace_id=ws.id,
                type_filter=["Icd"],
                mode="keyword",
            )
            by_semantics = SearchService().search(
                "electrical power delivery",
                ctx,
                workspace_id=ws.id,
                type_filter=["Icd"],
                mode="vector",
            )

        assert "Icd" in SEARCHABLE_ARTIFACT_TYPES
        sampled = [hit for hit in by_name.results if hit.id == str(icd.id)]
        assert sampled, "ICD was not found by its name"
        assert sampled[0].artifact_type == "Icd"
        assert sampled[0].title == _ICD_NAME
        assert [hit.id for hit in by_semantics.results] == [str(icd.id)]

    def test_tracelink_title_is_synthetic_and_workspace_scoped(self):
        """The link gets a synthetic endpoint title; a search from another
        workspace never returns it (no workspace leak)."""
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            src = make_requirement(ws_a, title="Source requirement", uid="REQ-A-1")
            tgt = make_requirement(ws_a, title="Target requirement", uid="REQ-A-2")
            link = _make_link(tenant, src, tgt)
            ctx_a = editor_ctx(tenant, ws_a)
            ctx_b = editor_ctx(tenant, ws_b)

            in_a = SearchService().search(
                "references",
                ctx_a,
                workspace_id=ws_a.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )
            in_b = SearchService().search(
                "references",
                ctx_b,
                workspace_id=ws_b.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )

        assert "TraceLink" in SEARCHABLE_ARTIFACT_TYPES
        hits = [hit for hit in in_a.results if hit.id == str(link.id)]
        assert hits, "trace link was not found in its source workspace"
        assert hits[0].artifact_type == "TraceLink"
        assert hits[0].title == "references: REQ-A-1 → REQ-A-2"
        assert in_b.total_count == 0

    def test_search_tracelink_hides_target_title_of_unreadable_workspace(self):
        """A caller who can read the source but not the target workspace gets
        the synthetic title with the target uid masked as '—'."""
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            src = make_requirement(ws_a, title="Source requirement", uid="REQ-A-1")
            tgt = make_requirement(ws_b, title="Foreign target", uid="REQ-B-9")
            link = _make_link(tenant, src, tgt)
            # Only a role in ws_a: ws_b is unreadable for this caller.
            ctx = editor_ctx(tenant, ws_a)

            result = SearchService().search(
                "references",
                ctx,
                workspace_id=ws_a.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )

        hits = [hit for hit in result.results if hit.id == str(link.id)]
        assert hits, "a readable source link must still be returned"
        assert hits[0].title == "references: REQ-A-1 → —"
        assert "REQ-B-9" not in hits[0].title

    def test_tracelink_survives_outdated_target_in_unreadable_workspace(self):
        """Review finding S1: the target's lifecycle is only enforced when the
        caller can read that target.

        The outdated-endpoint drop ran *before* the READ check, so retiring an
        artifact in a workspace the caller cannot even read silently removed a
        perfectly readable link from the source workspace. Two consequences:
        the legitimately visible link vanished depending on someone else's
        lifecycle state, and the difference was a 1-bit oracle over the
        lifecycle of artifacts in a workspace the caller has no access to.
        """
        from persistence.models import LifecycleStatus

        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            src = make_requirement(ws_a, title="Source requirement", uid="REQ-A-1")
            tgt = make_requirement(ws_b, title="Foreign retired target", uid="REQ-B-9")
            tgt.artifact.lifecycle_status = LifecycleStatus.OUTDATED
            tgt.artifact.save(update_fields=["lifecycle_status"])
            link = _make_link(tenant, src, tgt)
            # Only a role in ws_a: the target's workspace stays unreadable.
            ctx = editor_ctx(tenant, ws_a)

            result = SearchService().search(
                "references",
                ctx,
                workspace_id=ws_a.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )

        hits = [hit for hit in result.results if hit.id == str(link.id)]
        assert hits, (
            "the link disappeared even though its source is readable — the "
            "target's lifecycle was enforced without a READ on the target"
        )
        assert hits[0].title == "references: REQ-A-1 → —"
        assert "REQ-B-9" not in hits[0].title

    def test_icd_without_backing_artifact_is_dropped(self):
        """Review finding S2: a NULL backing Artifact is fail-closed.

        ``icd_icd.artifact_id`` is ``SET_NULL``, so removing the shadow
        Artifact leaves an ICD row with nothing to run the soft-delete and
        item-permission checks against. Such a row used to bypass both and stay
        searchable forever; it is dropped instead.
        """
        from icd.models import Icd

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            orphan = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Orphan Bus Interface",
                semantic_description="Its backing artifact is gone.",
            )

            result = SearchService().search(
                "Orphan Bus",
                ctx,
                workspace_id=ws.id,
                type_filter=["Icd"],
                mode="keyword",
            )

        assert orphan.artifact_id is None, (
            "precondition: this test is about the artifact_id IS NULL case"
        )
        assert str(orphan.id) not in [hit.id for hit in result.results]

    def test_search_icd_item_permission_none_is_dropped(self):
        """An explicit item-level ``none`` rule removes the ICD from search,
        while an unruled sibling stays visible."""
        from auth_tenancy.models import ItemPermission

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            blocked = _make_icd(tenant, ws, name="Blocked Bus Interface")
            visible = _make_icd(tenant, ws, name="Visible Bus Interface")
            ItemPermission.objects.create(
                tenant=tenant,
                user_id=ctx.user_id,
                workspace=ws,
                artifact_id=blocked.artifact_id,
                permission_level="none",
            )

            result = SearchService().search(
                "Bus Interface",
                ctx,
                workspace_id=ws.id,
                type_filter=["Icd"],
                mode="keyword",
            )

        ids = [hit.id for hit in result.results]
        assert str(visible.id) in ids
        assert str(blocked.id) not in ids

    def test_search_drops_soft_deleted_rows(self):
        """Soft-deleted rows are not searchable: an outdated ICD artifact and a
        link with one outdated endpoint are both dropped."""
        from persistence.models import LifecycleStatus

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            icd = _make_icd(tenant, ws, name="Retired Bus Interface")
            icd.artifact.lifecycle_status = LifecycleStatus.OUTDATED
            icd.artifact.save(update_fields=["lifecycle_status"])

            src = make_requirement(ws, title="Source requirement", uid="REQ-A-1")
            tgt = make_requirement(ws, title="Retired target", uid="REQ-A-2")
            tgt.artifact.lifecycle_status = LifecycleStatus.OUTDATED
            tgt.artifact.save(update_fields=["lifecycle_status"])
            link = _make_link(tenant, src, tgt)

            icd_hits = SearchService().search(
                "Retired Bus",
                ctx,
                workspace_id=ws.id,
                type_filter=["Icd"],
                mode="keyword",
            )
            link_hits = SearchService().search(
                "references",
                ctx,
                workspace_id=ws.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )

        assert str(icd.id) not in [hit.id for hit in icd_hits.results]
        assert str(link.id) not in [hit.id for hit in link_hits.results]
