"""Multi-artifact interview protocol — prompt slot + proposal parsing (Plan Task 4)."""
import json

import pytest

from application.interview_multi_protocol import (
    normalize_proposal_items,
    parse_multi_proposal,
)
from application.interview_proposal_errors import ProposalValidationError


class TestParseMultiProposal:
    def test_parses_valid_proposal_block(self):
        raw = '''Here is my proposal:
```json
[
  {"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []},
  {"type": "Requirement", "title": "Req B", "fields": {"title": "Req B"}, "links": [{"from": 1, "to": 0, "type": "derives-from"}]}
]
```
Let me know if this looks right.'''
        proposal = parse_multi_proposal(raw)
        assert len(proposal) == 2
        assert proposal[1]["links"][0]["type"] == "derives-from"

    def test_returns_none_for_no_json_block(self):
        assert parse_multi_proposal("I have a few more questions before proposing anything.") is None

    def test_returns_none_for_malformed_json(self):
        raw = '''```json
[{"type": "StakeholderNeed", "fields": {"title": "Need A"}]
```'''
        assert parse_multi_proposal(raw) is None

    def test_rejects_oversized_title_at_parse_boundary(self):
        item = {"type": "Requirement", "fields": {"title": "x" * 10_000}, "links": []}
        raw = f"```json\n{json.dumps([item])}\n```"
        assert parse_multi_proposal(raw) is None

    def test_rejects_too_many_items_at_parse_boundary(self):
        item = {"type": "Requirement", "fields": {"title": "R"}, "links": []}
        raw = f"```json\n{json.dumps([item] * 51)}\n```"
        assert parse_multi_proposal(raw) is None

    def test_rejects_too_many_fields_at_parse_boundary(self):
        fields = {f"f{i}": "v" for i in range(51)}
        raw = f"```json\n{json.dumps([{'type': 'Requirement', 'fields': fields, 'links': []}])}\n```"
        assert parse_multi_proposal(raw) is None

    def test_accepts_proposal_within_limits(self):
        item = {"type": "Requirement", "fields": {"title": "ok"}, "links": []}
        raw = f"```json\n{json.dumps([item])}\n```"
        assert parse_multi_proposal(raw) == [item]

    def test_parse_boundary_swallows_rejections_but_normalise_stays_strict(self):
        """#1990 strict validation belongs at propose()/formalize(), not here.

        The raw LLM reply is untrusted: a shape or field rejection means "no
        proposal this turn" (``None``). The very same input still raises a
        machine-readable ``ProposalValidationError`` when a caller-supplied /
        stored proposal is normalised at the readout or write gate.
        """
        for item in (
            1,  # non-dict entry -> INVALID_PROPOSAL_SHAPE
            {"type": "Requirement", "fields": [], "links": []},  # fields not a dict
            {"type": "Requirement", "status": "approved", "fields": {}},  # RESERVED_FIELD
        ):
            raw = f"```json\n{json.dumps([item])}\n```"
            assert parse_multi_proposal(raw) is None
            with pytest.raises(ProposalValidationError):
                normalize_proposal_items([item])
