# backend/application/tests/test_interview_artifact_adapters.py
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.interview_artifact_adapters import (
    ARTIFACT_CREATION_ADAPTERS,
    CreatedArtifactRef,
    build_adapter_fields,
)


def _assert_called_once_with_kwargs(mocked, expected: dict) -> None:
    """Assert an ``autospec=True``-patched service method's kwargs.

    With ``autospec=True`` the patch binds against the real signature (so a
    kwarg the service does not accept raises TypeError instead of being
    swallowed, which is the whole point -- see
    ``test_architecture_element_adapter_rejects_unknown_field_name``). The
    price is that the unbound function records the instance as its first
    positional argument, so ``assert_called_once_with(**kwargs)`` can no
    longer be used directly; check the kwargs alone.
    """
    assert mocked.call_count == 1
    assert mocked.call_args[1] == expected


class TestArtifactCreationAdapters:
    def test_registry_has_all_nine_types(self):
        expected = {
            "Requirement", "StakeholderNeed", "ArchitectureElement", "Risk",
            "TestCase", "Adr", "Issue", "Goal", "GlossaryTerm",
        }
        assert set(ARTIFACT_CREATION_ADAPTERS.keys()) == expected

    def test_requirement_adapter_carries_both_id_spaces(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            autospec=True,
            return_value=fake_requirement,
        ):
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        # The two ids are distinct UUIDs (Requirement.artifact is a
        # OneToOneField with its own pk) -- provenance rows/TraceLinks use
        # artifact_id, resulting_artifact_ids uses entity_id (issue #736).
        assert ref.artifact_id == fake_requirement.artifact_id
        assert ref.entity_id == fake_requirement.id
        assert ref.artifact_id != ref.entity_id

    def test_goal_adapter_entity_id_is_the_version_row_id(self):
        fake_ctx = MagicMock()
        goal_artifact_id = uuid.uuid4()
        goal_version_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GoalService.create_version",
            autospec=True,
            return_value={
                "id": goal_version_id,
                "artifact_id": goal_artifact_id,
                "title": "G",
            },
        ):
            ref = ARTIFACT_CREATION_ADAPTERS["Goal"]({"title": "G"}, fake_ctx, "ws-1")
        assert ref.artifact_id == goal_artifact_id
        assert ref.entity_id == goal_version_id

    def test_requirement_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            autospec=True,
            return_value=fake_requirement,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        _assert_called_once_with_kwargs(
            mocked, {"workspace_id": "ws-1", "ctx": fake_ctx, "title": "T"}
        )
        # The ref carries the Artifact PK (obj.artifact_id), never the
        # subtype row id -- InterviewSessionArtifact.artifact / TraceLink
        # endpoints are Artifact FKs.
        assert ref == CreatedArtifactRef(
            artifact_id=fake_requirement.artifact_id,
            artifact_type="Requirement",
            entity_id=fake_requirement.id,
        )

    def test_stakeholder_need_adapter_normalizes_dto(self):
        fake_ctx = MagicMock()
        fake_dto = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.StakeholderNeedService.create",
            autospec=True,
            return_value=fake_dto,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["StakeholderNeed"]({"title": "N"}, fake_ctx, "ws-1")
        _assert_called_once_with_kwargs(
            mocked, {"ctx": fake_ctx, "workspace_id": "ws-1", "title": "N"}
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_dto.artifact_id,
            artifact_type="StakeholderNeed",
            entity_id=fake_dto.id,
        )

    def test_goal_adapter_normalizes_dict_return(self):
        fake_ctx = MagicMock()
        goal_artifact_id = uuid.uuid4()
        goal_version_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GoalService.create_version",
            autospec=True,
            return_value={
                "id": goal_version_id, "artifact_id": goal_artifact_id, "title": "G"
            },
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Goal"]({"title": "G"}, fake_ctx, "ws-1")
        _assert_called_once_with_kwargs(
            mocked, {"workspace_id": "ws-1", "title": "G", "ctx": fake_ctx}
        )
        # "id" is the Goal version-row id; the ref must carry the Artifact PK.
        assert ref == CreatedArtifactRef(
            artifact_id=goal_artifact_id, artifact_type="Goal", entity_id=goal_version_id
        )

    def test_architecture_element_adapter_uses_the_real_signature(self):
        """A bare MagicMock accepts any kwargs, so a wrong field name would
        stay invisible. `autospec=True` makes the patch bind against the real
        signature, so a kwarg the service does not accept raises TypeError
        here."""
        fake_ctx = MagicMock()
        fake_element = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters."
            "ArchitectureService.create_architecture_element",
            autospec=True,
            return_value=fake_element,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"](
                {"title": "Sensor Unit"}, fake_ctx, "ws-1"
            )
        _assert_called_once_with_kwargs(
            mocked, {"workspace_id": "ws-1", "ctx": fake_ctx, "title": "Sensor Unit"}
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_element.artifact_id,
            artifact_type="ArchitectureElement",
            entity_id=fake_element.id,
        )

    def test_architecture_element_adapter_rejects_unknown_field_name(self):
        """`name` is not a create_architecture_element kwarg -- with autospec
        the mismatch surfaces as TypeError, which _formalize_single/_multi
        convert into a clean ValidationError (never a 500)."""
        fake_ctx = MagicMock()
        with patch(
            "application.interview_artifact_adapters."
            "ArchitectureService.create_architecture_element",
            autospec=True,
        ):
            with pytest.raises(TypeError):
                ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"](
                    {"name": "Sensor Unit"}, fake_ctx, "ws-1"
                )

    def test_test_case_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_case = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.TestService.create_test_case",
            autospec=True,
            return_value=fake_case,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["TestCase"]({"title": "TC-1"}, fake_ctx, "ws-1")
        _assert_called_once_with_kwargs(
            mocked, {"workspace_id": "ws-1", "ctx": fake_ctx, "title": "TC-1"}
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_case.artifact_id, artifact_type="TestCase", entity_id=fake_case.id
        )

    def test_adr_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_adr = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.AdrService.create_adr",
            autospec=True,
            return_value=fake_adr,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Adr"](
                {"title": "ADR-1", "description": "Why"}, fake_ctx, "ws-1"
            )
        # title/description are explicit kwargs on AdrService.create_adr --
        # the call must not duplicate them through **fields.
        _assert_called_once_with_kwargs(
            mocked,
            {
                "workspace_id": "ws-1",
                "title": "ADR-1",
                "description": "Why",
                "ctx": fake_ctx,
            },
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_adr.artifact_id, artifact_type="Adr", entity_id=fake_adr.id
        )

    def test_issue_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_issue = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.IssueService.create_issue",
            autospec=True,
            return_value=fake_issue,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Issue"]({"title": "BUG-1"}, fake_ctx, "ws-1")
        _assert_called_once_with_kwargs(
            mocked, {"workspace_id": "ws-1", "ctx": fake_ctx, "title": "BUG-1"}
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_issue.artifact_id, artifact_type="Issue", entity_id=fake_issue.id
        )

    def test_glossary_term_adapter_normalizes_dto(self):
        # Datenmodell-Konsolidierung Phase 3: GlossaryTerm gained a backing
        # Artifact row, so the adapter creates a real term instead of
        # rejecting the proposal.
        fake_ctx = MagicMock()
        fake_dto = MagicMock(id=uuid.uuid4())
        fake_artifact_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GlossaryService.create",
            autospec=True,
            return_value=fake_dto,
        ) as mocked, patch(
            "application.interview_artifact_adapters.GlossaryTerm.objects"
        ) as mocked_qs:
            mocked_qs.values_list.return_value.get.return_value = fake_artifact_id
            ref = ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"](
                {"term": "X", "definition": "Y"}, fake_ctx, "ws-1"
            )
        _assert_called_once_with_kwargs(
            mocked,
            {
                "ctx": fake_ctx,
                "workspace_id": "ws-1",
                "term": "X",
                "definition": "Y",
                "synonyms": None,
                "abbreviation": "",
            },
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_artifact_id, artifact_type="GlossaryTerm", entity_id=fake_dto.id
        )

    def test_glossary_term_adapter_requires_the_term_field(self):
        """``term`` is GlossaryService.create()'s own kwarg and the only name
        this adapter accepts. GlossaryTerm is not in IN_SCOPE_ARTIFACT_TYPES
        (single-kind start() rejects it) and the multi-mode prompt does not
        propose it, so the sole reachable caller is a hand-built
        confirmed_proposal -- which names create_X() kwargs directly. A
        missing key is a clean KeyError, which _formalize_multi converts into
        a ValidationError."""
        fake_ctx = MagicMock()
        with pytest.raises(KeyError):
            ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"](
                {"title": "X", "definition": "Y"}, fake_ctx, "ws-1"
            )

    def test_risk_adapter_requires_probability_and_impact(self):
        fake_ctx = MagicMock()
        with pytest.raises(KeyError):
            # probability/impact are required by RiskService.create_risk with no
            # default -- a proposal missing them must surface as a clear error,
            # not silently pass None through.
            ARTIFACT_CREATION_ADAPTERS["Risk"]({"title": "R"}, fake_ctx, "ws-1")


class TestBuildAdapterFields:
    def test_renames_rationale_to_description(self):
        assert build_adapter_fields({"title": "T", "rationale": "Because"}) == {
            "title": "T",
            "description": "Because",
        }

    def test_passes_unknown_protocol_fields_through_untouched(self):
        # A workspace-custom protocol picks its own field names; forwarding
        # them means a name the service accepts works, and a name it does not
        # accept raises TypeError -> ValidationError, rather than being
        # silently dropped.
        assert build_adapter_fields(
            {"title": "R", "probability": "high", "impact": "low"}
        ) == {"title": "R", "probability": "high", "impact": "low"}

    def test_explicit_description_wins_over_rationale(self):
        # If a protocol declares `description` directly, it is authoritative --
        # the rationale rename must not clobber it.
        assert build_adapter_fields(
            {"title": "A", "description": "Direct", "rationale": "Indirect"}
        ) == {"title": "A", "description": "Direct"}

    def test_empty_rationale_still_maps_to_empty_description(self):
        # create_requirement's own default is "" -- never None, which would
        # violate the NOT NULL on description.
        assert build_adapter_fields({"title": "T", "rationale": None}) == {
            "title": "T",
            "description": "",
        }

    def test_does_not_mutate_the_input(self):
        collected = {"title": "T", "rationale": "R"}
        build_adapter_fields(collected)
        assert collected == {"title": "T", "rationale": "R"}
