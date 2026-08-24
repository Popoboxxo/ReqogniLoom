# backend/application/tests/test_interview_artifact_adapters.py
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError  # noqa: F401 -- guard: base errors exist
from application.interview_artifact_adapters import (
    ARTIFACT_CREATION_ADAPTERS,
    CreatedArtifactRef,
)


class TestArtifactCreationAdapters:
    def test_registry_has_all_nine_types(self):
        expected = {
            "Requirement", "StakeholderNeed", "ArchitectureElement", "Risk",
            "TestCase", "Adr", "Issue", "Goal", "GlossaryTerm",
        }
        assert set(ARTIFACT_CREATION_ADAPTERS.keys()) == expected

    def test_requirement_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            return_value=fake_requirement,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(workspace_id="ws-1", ctx=fake_ctx, title="T")
        # The ref carries the Artifact PK (obj.artifact_id), never the
        # subtype row id -- InterviewSessionArtifact.artifact / TraceLink
        # endpoints are Artifact FKs.
        assert ref == CreatedArtifactRef(
            artifact_id=fake_requirement.artifact_id, artifact_type="Requirement"
        )

    def test_stakeholder_need_adapter_normalizes_dto(self):
        fake_ctx = MagicMock()
        fake_dto = MagicMock(artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.StakeholderNeedService.create",
            return_value=fake_dto,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["StakeholderNeed"]({"title": "N"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(ctx=fake_ctx, workspace_id="ws-1", title="N")
        assert ref == CreatedArtifactRef(
            artifact_id=fake_dto.artifact_id, artifact_type="StakeholderNeed"
        )

    def test_goal_adapter_normalizes_dict_return(self):
        fake_ctx = MagicMock()
        goal_artifact_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GoalService.create_version",
            return_value={"id": uuid.uuid4(), "artifact_id": goal_artifact_id, "title": "G"},
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Goal"]({"title": "G"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(workspace_id="ws-1", title="G", ctx=fake_ctx)
        # "id" is the Goal version-row id; the ref must carry the Artifact PK.
        assert ref == CreatedArtifactRef(artifact_id=goal_artifact_id, artifact_type="Goal")

    def test_risk_adapter_requires_probability_and_impact(self):
        fake_ctx = MagicMock()
        with pytest.raises(KeyError):
            # probability/impact are required by RiskService.create_risk with no
            # default -- a proposal missing them must surface as a clear error,
            # not silently pass None through.
            ARTIFACT_CREATION_ADAPTERS["Risk"]({"title": "R"}, fake_ctx, "ws-1")
