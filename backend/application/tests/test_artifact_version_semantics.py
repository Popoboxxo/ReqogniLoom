"""
Regression tests for issue #213 — ``version`` is a lock counter, not history.

``AuditableModel.version`` is a pure optimistic-concurrency counter. It was
also used as the addressing token for the ``/versions/`` and ``/diff/``
endpoints, where every non-zero version silently resolved to the *current*
row. That made the API claim things that are not true:

  - ``diff(from=1, to=2)`` on an entity currently at version 5 reported
    "no changes" — comparing the current row against itself — even though
    the content did change between those two writes.
  - ``list_versions()`` advertised ``Current (v5)``, implying five retrievable
    revisions, while only the current row is actually stored.

The fix keeps ``version`` as an internal concurrency-control counter and makes
the user-facing surface honest about which versions have a stored snapshot.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.artifact_diff_service import ArtifactDiffService
from application.base import NotFoundError

pytestmark = pytest.mark.django_db


ARTIFACT_ID = uuid.uuid4()
ENTITY_ID = uuid.uuid4()
WS_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_ctx():
    ctx = MagicMock()
    ctx.active_roles = ("editor",)
    ctx.tenant_id = TENANT_ID
    ctx.user_id = uuid.uuid4()
    ctx.has_role = lambda role: role == "editor"
    return ctx


def _make_requirement_mock(version: int):
    req = MagicMock()
    req.id = ENTITY_ID
    req.title = "Current title"
    req.description = "Current description"
    req.category = "functional"
    req.status = "draft"
    req.version = version
    req.modified_at = None
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.workspace_id = WS_ID
    req.artifact = artifact
    req.artifact_id = ARTIFACT_ID
    return req


def _make_artifact_mock():
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.artifact_type = "Requirement"
    artifact.workspace_id = WS_ID
    return artifact


def _patched_model(req_mock):
    model = MagicMock()
    model.objects.select_related.return_value.filter.return_value.first.return_value = (
        req_mock
    )
    model.objects.filter.return_value.first.return_value = req_mock
    return model


# ---------------------------------------------------------------------------
# diff must not pretend two historical lock-counter values are comparable
# ---------------------------------------------------------------------------


class TestDiffRejectsUnstoredVersions:
    """Issue #213: intermediate lock-counter values have no stored snapshot."""

    def test_diff_between_two_historical_versions_raises_not_found(self):
        """diff(1, 2) on an entity at v5 must not report "no changes"."""
        svc = ArtifactDiffService()
        ctx = _make_ctx()
        req_mock = _make_requirement_mock(version=5)

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact_mock()
                )
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": _patched_model(req_mock)},
                ):
                    with pytest.raises(NotFoundError):
                        svc.diff(
                            artifact_id=ARTIFACT_ID,
                            from_version=1,
                            to_version=2,
                            ctx=ctx,
                        )

    def test_diff_from_unstored_version_to_current_carries_note(self):
        """from=1 has no snapshot → the response documents the limitation."""
        svc = ArtifactDiffService()
        ctx = _make_ctx()
        req_mock = _make_requirement_mock(version=5)

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact_mock()
                )
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": _patched_model(req_mock)},
                ):
                    result = svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=1,
                        to_version=5,
                        ctx=ctx,
                    )

        assert "note" in result
        assert result["from_version"] == 1
        assert result["to_version"] == 5

    def test_diff_for_entity_between_historical_versions_raises_not_found(self):
        """Same guarantee on the entity-based (no artifact FK) code path."""
        svc = ArtifactDiffService()
        ctx = _make_ctx()
        req_mock = _make_requirement_mock(version=4)

        with patch.object(svc, "_set_tenant_context"):
            with patch.dict(
                "application.artifact_diff_service._ENTITY_MODELS",
                {"Requirement": _patched_model(req_mock)},
            ):
                with pytest.raises(NotFoundError):
                    svc.diff_for_entity(
                        entity_type="Requirement",
                        entity_id=ENTITY_ID,
                        from_version=1,
                        to_version=3,
                        ctx=ctx,
                    )


# ---------------------------------------------------------------------------
# list_versions must flag which versions actually have stored content
# ---------------------------------------------------------------------------


class TestListVersionsContentAvailability:
    """Issue #213: the version list must not imply N retrievable revisions."""

    def test_list_versions_flags_content_availability(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()
        req_mock = _make_requirement_mock(version=7)

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact_mock()
                )
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": _patched_model(req_mock)},
                ):
                    versions = svc.list_versions(artifact_id=ARTIFACT_ID, ctx=ctx)

        assert [v["version"] for v in versions] == [0, 7]
        assert versions[0]["content_available"] is False
        assert versions[1]["content_available"] is True
        # The lock counter must not be rendered as a revision number.
        assert "v7" not in versions[1]["label"]

    def test_list_versions_for_entity_flags_content_availability(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()
        req_mock = _make_requirement_mock(version=3)

        with patch.object(svc, "_set_tenant_context"):
            with patch.dict(
                "application.artifact_diff_service._ENTITY_MODELS",
                {"Requirement": _patched_model(req_mock)},
            ):
                versions = svc.list_versions_for_entity(
                    entity_type="Requirement",
                    entity_id=ENTITY_ID,
                    ctx=ctx,
                )

        assert [v["version"] for v in versions] == [0, 3]
        assert versions[0]["content_available"] is False
        assert versions[1]["content_available"] is True
        assert "v3" not in versions[1]["label"]


# ---------------------------------------------------------------------------
# Model-level naming: the counter is addressable under an unambiguous name
# ---------------------------------------------------------------------------


class TestLockVersionAlias:
    """``lock_version`` states the intent that ``version`` obscures."""

    def test_lock_version_mirrors_version(self):
        from persistence.models import Requirement

        req = Requirement(title="t", description="d")
        req.version = 9
        assert req.lock_version == 9
