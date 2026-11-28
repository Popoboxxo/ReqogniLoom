"""Deterministic severity for change-impact findings (D16, spec §4.2.4).

The severity of a ``ChangeImpactFinding`` is derived **exclusively** from the
deterministic edge data of its chain: the aggregated ``weight``, the shortest
``hop_distance`` to the change set, whether the chain is coverage-relevant and
whether any edge is suspect-flagged. The LLM may never raise or lower it — it
only supplies the ``rationale`` (spec §4.2.4, D16).

Rejected heuristic (explicitly **not** implemented): treating a target
artifact type such as ``TestCase``/``Icd`` as a proxy for ``blocking``. The
classification takes no artifact/entity type at all.

This module is deliberately pure and DB-free so it can be unit-tested without
Django and imported by the future chain engine (S4) exactly as-is.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Named thresholds (calibration from S0.6; keep as module constants).
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCKING = "blocking"

#: ``blocking`` requires at least this aggregated weight.
BLOCKING_MIN_WEIGHT = Decimal("0.50")
#: ``blocking`` additionally requires the finding within this hop distance.
BLOCKING_MAX_HOP_DISTANCE = 2
#: ``warning`` requires at least this aggregated weight …
WARNING_MIN_WEIGHT = Decimal("0.20")
#: … unless the finding is within this hop distance (a close edge is worth a
#: warning even when the aggregate weight has decayed).
WARNING_MAX_HOP_DISTANCE = 3
#: Lower weight floor; weights below it never escalate on weight alone.
MIN_WEIGHT_FLOOR = Decimal("0.05")

#: Semantic edges are capped at this rank; ``origin="semantic"`` is never
#: ``blocking`` (spec §4.2.4 invariant).
_SEMANTIC_MAX_RANK = 1

_QUANTUM = Decimal("0.0001")
_RANK = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_BLOCKING: 2}


def severity_rank(value: str) -> int:
    """Return the ordered rank of a severity (info=0, warning=1, blocking=2)."""
    try:
        return _RANK[value]
    except KeyError:
        raise ValueError(f"Unknown severity: {value!r}") from None


def _normalise_weight(weight: Decimal | float | str) -> Decimal:
    """Clamp *weight* to ``[0, 1]`` and quantize it to four decimal places."""
    if isinstance(weight, Decimal):
        value = weight
    else:
        # ``str`` first so a float does not smuggle in binary noise.
        value = Decimal(str(weight))
    value = max(Decimal("0"), min(Decimal("1"), value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def classify_severity(
    *,
    weight: Decimal | float | str,
    hop_distance: int,
    coverage_relevant: bool = False,
    suspect: bool = False,
    origin: str = "deterministic",
    min_weight: Decimal = MIN_WEIGHT_FLOOR,
) -> str:
    """Classify a change-impact finding's severity deterministically.

    Precedence (first matching rule wins):

    1. ``weight`` is clamped to ``[0, 1]`` and quantized to four decimals;
       ``hop_distance < 1`` raises :class:`ValueError` (a finding is always at
       least one hop away from the change set).
    2. **info floor:** ``weight < max(min_weight, WARNING_MIN_WEIGHT)`` and
       ``hop_distance > WARNING_MAX_HOP_DISTANCE`` and not ``suspect`` → info.
    3. **blocking:** ``weight >= BLOCKING_MIN_WEIGHT`` **and**
       ``hop_distance <= BLOCKING_MAX_HOP_DISTANCE`` **and**
       (``coverage_relevant`` or ``suspect``) → blocking.
    4. **warning:** ``weight >= WARNING_MIN_WEIGHT`` or
       ``hop_distance <= WARNING_MAX_HOP_DISTANCE`` or ``suspect`` → warning.
    5. otherwise info.
    6. **semantic cap:** ``origin="semantic"`` is capped at ``warning``; a
       semantic edge can never be blocking.

    The artifact/entity type is never consulted.
    """
    normalised_weight = _normalise_weight(weight)
    if hop_distance < 1:
        raise ValueError(
            f"hop_distance must be >= 1, got {hop_distance!r}"
        )

    if (
        normalised_weight < max(min_weight, WARNING_MIN_WEIGHT)
        and hop_distance > WARNING_MAX_HOP_DISTANCE
        and not suspect
    ):
        severity = SEVERITY_INFO
    elif (
        normalised_weight >= BLOCKING_MIN_WEIGHT
        and hop_distance <= BLOCKING_MAX_HOP_DISTANCE
        and (coverage_relevant or suspect)
    ):
        severity = SEVERITY_BLOCKING
    elif (
        normalised_weight >= WARNING_MIN_WEIGHT
        or hop_distance <= WARNING_MAX_HOP_DISTANCE
        or suspect
    ):
        severity = SEVERITY_WARNING
    else:
        severity = SEVERITY_INFO

    if origin == "semantic" and severity_rank(severity) > _SEMANTIC_MAX_RANK:
        severity = SEVERITY_WARNING

    return severity
