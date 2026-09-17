"""
SE-Auditor rule package — importing it self-registers every rule.

The RuleEngine imports this package once at construction time; each submodule
below registers its rule(s) via ``@register_rule`` as an import side effect.
A new rule-implementer agent adds its module here (one ``from . import ...``
line per new rule file) — see the guide in ``traceability/audit/registry.py``.

Fully implemented (§2.2 Pflichtmatrix): TRACE-P1/P1b/P2/P3
(trace_derivation_allocation), TRACE-P4/P5/ARCH-003 (decomposition_consistency),
TRACE-P6/VERIF-P8/CONS-P9/CONS-P10 (coverage_consistency), and TRACE-P7
(trace_p7, baseline-scope consistency).

Beyond §2.2: CONS-P11 (level_progression) — added by SYSTEMAUDIT_2026-08-27
P1-9 together with the RequirementLevel cascade realignment.
"""
from __future__ import annotations

from . import coverage_consistency  # noqa: F401  (registration side effect)
from . import decomposition_consistency  # noqa: F401  (registration side effect)
from . import level_progression  # noqa: F401  (registration side effect)
from . import trace_derivation_allocation  # noqa: F401  (registration side effect)
from . import trace_p7  # noqa: F401  (registration side effect)

__all__ = [
    "coverage_consistency",
    "decomposition_consistency",
    "level_progression",
    "trace_derivation_allocation",
    "trace_p7",
]
