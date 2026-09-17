"""Shared fixtures for the ``application`` service test suite.

See the root ``conftest.py`` for the convention: cross-cutting fixtures live in
the per-app conftest closest to the tests that use them.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from application.artifact_version_service import ArtifactVersionService
from persistence.tenancy import TenantContextNotSetError


def _is_real_artifact_id(value: Any) -> bool:
    """True when *value* can address a real ``Artifact`` row."""
    if isinstance(value, uuid.UUID):
        return True
    if isinstance(value, str):
        try:
            uuid.UUID(value)
        except ValueError:
            return False
        return True
    return False


@pytest.fixture(autouse=True)
def _skip_revision_recording_for_mocked_entities() -> Iterator[None]:
    """Neutralise revision recording when the entity is a test double.

    Datenmodell-Konsolidierung Phase 5 (Task 27): every service create/update
    path now appends an ``ArtifactVersion`` row. A large part of this suite
    exercises those paths with the whole ORM mocked away
    (``patch("application.adr_service.Adr.objects")`` and friends) while still
    carrying ``pytest.mark.django_db``, so the entity's ``artifact_id`` is a MagicMock
    and there is no ``Artifact`` row to hang a revision on.

    The discriminator is the environment, not the test name: a call that can
    reach a real ``Artifact`` row runs the real recorder, so every DB-backed
    test in this suite still exercises the recording sites. Only the two
    conditions a mocked-ORM test produces are short-circuited: a non-UUID id,
    and an unarmed tenant context (``_set_tenant_context`` patched out).
    Everything else — including ``NotFoundError`` for an id with no row behind
    it, which ``test_artifact_version_service`` asserts on — propagates.

    End-to-end coverage of the recording sites themselves, with real rows and
    no stubbing at all, lives in ``test_revision_recording.py``.
    """
    real_record = ArtifactVersionService.record

    def _record(self, artifact_id, payload, ctx, **kwargs):
        if not _is_real_artifact_id(artifact_id):
            return 1
        try:
            return real_record(self, artifact_id, payload, ctx, **kwargs)
        except TenantContextNotSetError:
            return 1

    with patch.object(ArtifactVersionService, "record", _record):
        yield
