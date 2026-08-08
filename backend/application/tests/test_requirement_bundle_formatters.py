from __future__ import annotations

import csv
import io
from uuid import uuid4

from application.requirement_bundle_service import BundleItem, BundleResult
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)


def _sample_result() -> BundleResult:
    root_id = uuid4()
    return BundleResult(
        items=[
            BundleItem(
                requirement_id=uuid4(),
                found_under_element_id=root_id,
                depth=0,
                fields={"title": "First requirement", "status": "draft"},
            ),
            BundleItem(
                requirement_id=uuid4(),
                found_under_element_id=root_id,
                depth=1,
                fields={"title": "Second, with a comma", "status": "approved"},
            ),
        ],
        truncated_at_depth=False,
    )


class TestFormatBundleJson:
    def test_json_is_list_of_dicts_with_metadata(self):
        result = _sample_result()
        payload = format_bundle_json(result)
        assert payload["truncated_at_depth"] is False
        assert len(payload["items"]) == 2
        assert payload["items"][0]["fields"]["title"] == "First requirement"
        assert payload["items"][0]["depth"] == 0
        assert "requirement_id" in payload["items"][0]
        assert "found_under_element_id" in payload["items"][0]


class TestFormatBundleMarkdown:
    def test_markdown_contains_every_title_grouped_by_element(self):
        result = _sample_result()
        md = format_bundle_markdown(result)
        assert "First requirement" in md
        assert "Second, with a comma" in md
        assert md.startswith("#")


class TestFormatBundleCsv:
    def test_csv_has_one_row_per_item_and_escapes_commas(self):
        result = _sample_result()
        csv_text = format_bundle_csv(result)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[1]["title"] == "Second, with a comma"
        assert "found_under_element_id" in reader.fieldnames
        assert "depth" in reader.fieldnames

    def test_csv_with_no_items_still_has_header_only(self):
        empty = BundleResult(items=[], truncated_at_depth=False)
        csv_text = format_bundle_csv(empty)
        assert csv_text.strip() != ""
        reader = csv.DictReader(io.StringIO(csv_text))
        assert list(reader) == []
