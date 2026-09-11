"""Issue #831 — Glossary must expose the artifact-consistent ``status`` field.

Every other workflow-backed artifact serializer (Requirement, StakeholderNeed,
TestCase, Adr, Risk, Issue, ChangeRequest, Goal, MainGoal) exposes its
lifecycle state under the wire key ``status`` via
``WorkflowStateSerializerMixin``. ``GlossaryTermSerializer`` was the lone
outlier, exposing ``lifecycle_status`` for the same concept — so an API
consumer had to special-case Glossary for a field name the rest of the
artifact API calls ``status``.

These tests pin the rename end-to-end at the serializer/DTO boundary: the
public wire key is ``status``, and the retired ``lifecycle_status`` name no
longer appears on any glossary payload (no backwards-compatible alias — see
the #831 decision note; the SPA is the only consumer and was updated in the
same change).
"""
from __future__ import annotations

import uuid

from application.glossary_service import GlossaryTermDTO
from rest_api.serializers import GlossaryTermSerializer


def _dto(**overrides: object) -> GlossaryTermDTO:
    """Build a GlossaryTermDTO with all serializer-visible fields populated."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "term": "Requirement",
        "definition": "A stated need.",
        "synonyms": [],
        "abbreviation": "REQ",
        "version": 1,
        "status": "active",
    }
    defaults.update(overrides)
    return GlossaryTermDTO(**defaults)  # type: ignore[arg-type]


class TestGlossaryStatusFieldName:
    """#831: ``status`` is the single glossary lifecycle wire key."""

    def test_serializer_exposes_status_not_lifecycle_status(self) -> None:
        fields = GlossaryTermSerializer().fields
        assert "status" in fields
        assert "lifecycle_status" not in fields

    def test_dto_exposes_status_not_lifecycle_status(self) -> None:
        dto_fields = GlossaryTermDTO.__dataclass_fields__
        assert "status" in dto_fields
        assert "lifecycle_status" not in dto_fields

    def test_serialized_payload_uses_status_and_omits_the_retired_name(self) -> None:
        data = GlossaryTermSerializer(_dto(status="outdated")).data
        assert data["status"] == "outdated"
        assert "lifecycle_status" not in data
