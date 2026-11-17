"""Multi-artifact interview protocol — prompt slot + proposal parsing (Plan Task 4)."""
import json

from application.interview_multi_protocol import parse_multi_proposal


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
