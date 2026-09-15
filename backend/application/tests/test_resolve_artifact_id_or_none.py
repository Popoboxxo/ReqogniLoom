"""resolve_artifact_id_or_none wraps the public entity→Artifact resolver."""
import uuid
from unittest.mock import patch

import pytest

from application.trace_link_service import resolve_artifact_id_or_none
from persistence.errors import NotFoundError


@pytest.mark.django_db
def test_returns_none_for_an_unknown_id():
    with patch(
        "application.trace_link_service.TraceLinkService.resolve_entity_to_artifact_id",
        side_effect=NotFoundError("nope"),
    ):
        assert resolve_artifact_id_or_none(uuid.uuid4()) is None


@pytest.mark.django_db
def test_returns_the_resolved_id():
    target = uuid.uuid4()
    with patch(
        "application.trace_link_service.TraceLinkService.resolve_entity_to_artifact_id",
        return_value=target,
    ):
        assert resolve_artifact_id_or_none(uuid.uuid4()) == target
