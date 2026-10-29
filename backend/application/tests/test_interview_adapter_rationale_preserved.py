"""Review finding R-B1-1: ``build_adapter_fields`` must never drop an answer.

The rationale -> description alias used to ``continue`` when ``description`` was
already collected, silently discarding the ``rationale`` value the user gave.
``Requirement`` accepts both kwargs, so both answers must reach
``create_requirement()``.
"""
from __future__ import annotations

from application.interview_artifact_adapters import build_adapter_fields


def test_rationale_survives_when_description_collected() -> None:
    assert build_adapter_fields(
        {"title": "T", "description": "D", "rationale": "R"}
    ) == {"title": "T", "description": "D", "rationale": "R"}
