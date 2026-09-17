from __future__ import annotations

import csv
import datetime
import io
import json
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

    def test_json_payload_is_stdlib_serialisable(self):
        """Regression: filter_mode='all'/'visible' put raw UUID (id,
        workspace_id) and datetime (created_at, modified_at) objects straight
        from QuerySet.values() into the payload. DRF's renderer tolerates
        those; the MCP transport's stdlib json.dumps does not, and the
        resulting TypeError surfaced as an unhandled 500 on the export tool's
        *default* invocation.
        """
        result = BundleResult(
            items=[
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={
                        "id": uuid4(),
                        "workspace_id": uuid4(),
                        "created_at": datetime.datetime(2026, 8, 9, 12, 0, 0),
                        "modified_at": datetime.datetime(2026, 8, 9, 12, 30, 0),
                        "title": "T",
                    },
                )
            ],
            truncated_at_depth=False,
        )
        payload = format_bundle_json(result)

        json.dumps(payload)  # must not raise

        fields = payload["items"][0]["fields"]
        assert isinstance(fields["id"], str)
        assert isinstance(fields["workspace_id"], str)
        assert fields["created_at"] == "2026-08-09T12:00:00"


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

    def test_csv_neutralises_spreadsheet_formulas(self):
        """CSV injection guard: any editor-role tenant user can write a
        Requirement title, and the bundle is served as text/csv straight into
        Excel/LibreOffice. Cells starting with =, +, -, @, TAB or CR must be
        exported with a leading single quote so they stay literal text.
        """
        payloads = [
            "=cmd|'/c calc'!A1",
            "+HYPERLINK(\"http://evil\",\"click\")",
            "-2+3+cmd|'/c calc'!A0",
            "@SUM(1+1)",
        ]
        result = BundleResult(
            items=[
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={"title": payload, "status": "draft"},
                )
                for payload in payloads
            ],
            truncated_at_depth=False,
        )

        rows = list(csv.DictReader(io.StringIO(format_bundle_csv(result))))

        assert len(rows) == len(payloads)
        for row, payload in zip(rows, payloads):
            assert row["title"] == "'" + payload

        # TAB/CR triggers: asserted on the raw text rather than a DictReader
        # round trip, since CR is part of the CSV line terminator and its
        # round-trip representation depends on the reader's newline handling.
        whitespace = BundleResult(
            items=[
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={"title": "\tleading tab"},
                ),
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={"title": "\rleading cr"},
                ),
            ],
            truncated_at_depth=False,
        )
        raw = format_bundle_csv(whitespace)
        assert "'\tleading tab" in raw
        assert "'\rleading cr" in raw

        # A benign title must not be touched.
        benign = BundleResult(
            items=[
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={"title": "Normal title"},
                )
            ],
            truncated_at_depth=False,
        )
        benign_rows = list(csv.DictReader(io.StringIO(format_bundle_csv(benign))))
        assert benign_rows[0]["title"] == "Normal title"

    def test_csv_stringifies_uuid_and_datetime_fields(self):
        req_id, ws_id = uuid4(), uuid4()
        result = BundleResult(
            items=[
                BundleItem(
                    requirement_id=uuid4(),
                    found_under_element_id=uuid4(),
                    depth=0,
                    fields={
                        "workspace_id": ws_id,
                        "created_at": datetime.datetime(2026, 8, 9, 12, 0, 0),
                        "id": req_id,
                    },
                )
            ],
            truncated_at_depth=False,
        )
        rows = list(csv.DictReader(io.StringIO(format_bundle_csv(result))))
        assert rows[0]["workspace_id"] == str(ws_id)
        assert rows[0]["created_at"] == "2026-08-09T12:00:00"

    def test_csv_with_no_items_still_has_header_only(self):
        empty = BundleResult(items=[], truncated_at_depth=False)
        csv_text = format_bundle_csv(empty)
        assert csv_text.strip() != ""
        reader = csv.DictReader(io.StringIO(csv_text))
        assert list(reader) == []
