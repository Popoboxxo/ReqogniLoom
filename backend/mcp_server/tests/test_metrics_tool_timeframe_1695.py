"""#1695: the MCP metrics.get timeframe must match the REST enum.

The REST endpoint validated ``?timeframe=`` in #1613; the MCP tool kept
echoing any string. Both now read one tuple from ``se_metrics.registry`` and
the schema advertises the enum, so an unknown value fails at the door.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from mcp_server.tools import metrics as metrics_module
from mcp_server.tools.base import ParameterError
from mcp_server.tools.metrics import MetricsToolGroup
from rest_api.metrics_views import _VALID_TIMEFRAMES
from se_metrics.registry import VALID_METRIC_TIMEFRAMES


def _get_schema() -> dict:
    group = MetricsToolGroup()
    return next(
        schema for schema in group._TOOL_SCHEMAS if schema["name"] == "metrics.get"
    )


def test_schema_and_rest_share_the_same_enum() -> None:
    timeframe = _get_schema()["inputSchema"]["properties"]["timeframe"]
    assert timeframe["enum"] == list(VALID_METRIC_TIMEFRAMES)
    assert tuple(timeframe["enum"]) == _VALID_TIMEFRAMES


@pytest.mark.parametrize("value", ["P14D", "p30d", "P30", "quatsch"])
def test_unknown_timeframe_is_rejected(value: str) -> None:
    group = MetricsToolGroup()
    with pytest.raises(ParameterError, match="timeframe"):
        group._handle_get(
            params={"workspace_id": str(uuid4()), "timeframe": value},
            auth_context=None,  # not reached: validation happens first
            api_key="",
        )


def test_valid_timeframe_is_normalised_and_passed_through(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_values(**kwargs):
        captured.update(kwargs)
        return {"workspace_id": str(kwargs["workspace_id"]), "metrics": {}}

    monkeypatch.setattr(metrics_module, "get_metric_values", fake_values)
    MetricsToolGroup()._handle_get(
        params={"workspace_id": str(uuid4()), "timeframe": " P7D "},
        auth_context=None,
        api_key="",
    )
    assert captured["timeframe"] == "P7D"
