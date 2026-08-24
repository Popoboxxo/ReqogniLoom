"""Multi-artifact interview protocol — prompt slot + proposal parsing (Plan Task 4)."""
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
